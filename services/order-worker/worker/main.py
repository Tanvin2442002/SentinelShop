"""The worker loop: BRPOP an order, mark it PROCESSING, work 1-2 s, mark it COMPLETED.

Shutdown (contracts/api.md): on SIGTERM stop taking new messages, finish the
current order, exit 0. If a DB write fails after a pop, the message is pushed
back so the order is not lost.
"""

import json
import logging
import random
import signal
import sys
import time
import uuid

import psycopg
import redis

from . import metrics
from .config import ConfigError, load_settings
from .logging_setup import setup_logging
from .queue import BRPOP_TIMEOUT_SECONDS, QUEUE_KEY, make_redis
from .store import Store, make_pool

# Redis failures can surface as redis-py errors or plain socket errors.
QUEUE_ERRORS = (redis.exceptions.RedisError, OSError)
# psycopg.Error also covers psycopg_pool.PoolTimeout (no connection / DB down).
DB_ERRORS = (psycopg.Error,)

# Pause after a Redis or DB error so an outage does not become a busy loop
# that floods the logs (and, for DB errors, pops the same message over and over).
ERROR_PAUSE_SECONDS = 1.0
PAUSE_STEP_SECONDS = 0.1

# Chaos values from contracts/chaos.md. The names are frozen; the numbers may
# be tuned to meet the calibration requirement there.
CHAOS_DB_DELAY_SECONDS = 2.0
CHAOS_LEAK_BYTES = 2 * 1024 * 1024
# CHAOS_MEMORY_LEAK keeps chunks here forever. A module-level list is never
# freed, which is exactly the bug being simulated.
_leaked: list[bytes] = []


class BadMessage(ValueError):
    pass


def parse_message(raw) -> tuple[int, str]:
    """Return (order_id, trace_id) from a queue message {"order_id":int,"trace_id":"..."}."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        raise BadMessage("message is not JSON") from None
    if not isinstance(data, dict):
        raise BadMessage("message is not a JSON object")

    order_id = data.get("order_id")
    # bool is a subclass of int in Python; true must not become order 1.
    if not isinstance(order_id, int) or isinstance(order_id, bool) or order_id <= 0:
        raise BadMessage("order_id missing or not a positive integer")

    trace_id = data.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id:
        # Keep the order moving; it just will not join up with the API's logs.
        trace_id = uuid.uuid4().hex
    return order_id, trace_id[:64]


class Worker:
    def __init__(self, store, queue, logger: logging.Logger,
                 sleep=time.sleep, work_seconds=lambda: random.uniform(1, 2),
                 slow_db=False, memory_leak=False):
        self.store = store
        self.queue = queue
        self.logger = logger
        # Injected so unit tests run instantly.
        self.sleep = sleep
        self.work_seconds = work_seconds
        self.stopping = False
        self.slow_db = slow_db
        self.memory_leak = memory_leak

    # --- shutdown ---------------------------------------------------------

    def request_stop(self, signum=None, frame=None) -> None:
        """Signal handler. Only sets a flag; the loop checks it between orders."""
        if self.stopping:
            return
        self.stopping = True
        name = signal.Signals(signum).name if signum else "-"
        self.logger.info("shutdown requested", extra={"fields": {"signal": name}})

    def _pause(self, seconds: float) -> None:
        # Short steps so a SIGTERM during an outage pause is acted on quickly.
        # Counted as whole steps: adding 0.1 ten times is not exactly 1.0.
        for _ in range(round(seconds / PAUSE_STEP_SECONDS)):
            if self.stopping:
                return
            self.sleep(PAUSE_STEP_SECONDS)

    # --- main loop --------------------------------------------------------

    def run(self) -> int:
        while not self.stopping:
            self.run_once()
        self.logger.info("shutdown complete")
        return 0

    def run_once(self) -> None:
        try:
            item = self.queue.brpop(QUEUE_KEY, timeout=BRPOP_TIMEOUT_SECONDS)
        except QUEUE_ERRORS as exc:
            # Redis down: stay up and keep trying (no crash loop).
            self.logger.warning("queue unavailable",
                                extra={"fields": {"error": type(exc).__name__}})
            self._pause(ERROR_PAUSE_SECONDS)
            return
        if item is None:
            return  # BRPOP timed out on an empty queue
        _key, raw = item
        # A message popped just as SIGTERM arrived is still processed: it is
        # already off the queue, and finishing it is how it avoids being lost.
        self.handle(raw)

    # --- one order --------------------------------------------------------

    def handle(self, raw) -> None:
        start = time.perf_counter()
        try:
            order_id, trace_id = parse_message(raw)
        except BadMessage as exc:
            # Pushing a malformed message back would make it fail forever.
            self._failed(start, None, None, reason=str(exc), level=logging.ERROR)
            return

        self.logger.info("order picked",
                         extra={"fields": {"trace_id": trace_id, "order_id": order_id}})
        if self.memory_leak:
            # Repeating a non-zero byte writes every page, so it really counts
            # toward RSS. bytes(n) could be lazily zeroed pages that cost nothing.
            _leaked.append(b"\xa5" * CHAOS_LEAK_BYTES)
        try:
            if not self._set_status(order_id, "PROCESSING"):
                self._failed(start, trace_id, order_id,
                             reason="order not found or already final")
                return
            self.sleep(self.work_seconds())
            if not self._set_status(order_id, "COMPLETED"):
                self._failed(start, trace_id, order_id,
                             reason="order changed to a final status while processing")
                return
        except DB_ERRORS:
            self._requeue(raw, start, trace_id, order_id)
            return

        duration = time.perf_counter() - start
        metrics.ORDER_PROCESSING.observe(duration)
        metrics.ORDERS_PROCESSED.labels("completed").inc()
        self.logger.info("order completed", extra={"fields": {
            "trace_id": trace_id, "order_id": order_id,
            "duration_ms": round(duration * 1000, 2), "result": "completed"}})

    def _set_status(self, order_id: int, status: str) -> bool:
        if self.slow_db:
            # Before EACH update: two updates per order, so ~4 s extra per order.
            self.sleep(CHAOS_DB_DELAY_SECONDS)
        return self.store.set_status(order_id, status)

    def _failed(self, start, trace_id, order_id, reason, level=logging.WARNING) -> None:
        metrics.ORDERS_PROCESSED.labels("failed").inc()
        self.logger.log(level, "order failed", extra={"fields": {
            "trace_id": trace_id, "order_id": order_id,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            "result": "failed", "reason": reason}})

    def _requeue(self, raw, start, trace_id, order_id) -> None:
        fields = {"trace_id": trace_id, "order_id": order_id,
                  "duration_ms": round((time.perf_counter() - start) * 1000, 2)}
        try:
            # RPUSH puts it back at the end BRPOP takes from, so it is retried
            # next and keeps its place in line.
            self.queue.rpush(QUEUE_KEY, raw)
        except QUEUE_ERRORS:
            # DB and Redis both down: the order cannot be saved anywhere. Log the
            # raw message so a human can re-queue it; the row stays in flight.
            metrics.ORDERS_PROCESSED.labels("failed").inc()
            self.logger.error("order failed", extra={"fields": {
                **fields, "result": "failed",
                "reason": "database unavailable and push back failed",
                "queue_message": raw.decode("utf-8", "replace")}})
            return
        # Not a final result, so orders_processed_total is not incremented.
        self.logger.warning("order failed", extra={"fields": {
            **fields, "result": "requeued", "reason": "database unavailable"}})
        self._pause(ERROR_PAUSE_SECONDS)


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"order-worker: {exc}", file=sys.stderr)
        return 2

    logger = setup_logging(settings.log_level, settings.log_file)
    store = Store(make_pool(settings.database_url))
    store.open()
    worker = Worker(store, make_redis(settings.redis_url), logger,
                    slow_db=settings.chaos_slow_db, memory_leak=settings.chaos_memory_leak)

    signal.signal(signal.SIGTERM, worker.request_stop)
    signal.signal(signal.SIGINT, worker.request_stop)
    metrics.start_metrics_server()
    logger.info("worker started", extra={"fields": {"metrics_port": metrics.METRICS_PORT}})

    try:
        return worker.run()
    finally:
        store.close()
