"""Fakes for Postgres and Redis so the worker can be tested without the stack."""

import json
import sys
from pathlib import Path

import psycopg
import pytest
import redis

# Make `import worker` resolve to services/order-worker/worker without packaging it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "order-worker"))

from worker.logging_setup import setup_logging  # noqa: E402
from worker.main import Worker  # noqa: E402


class FakeStore:
    def __init__(self):
        self.status = {}
        # Status names that raise a DB error when written, e.g. {"COMPLETED"}.
        self.fail_on = set()
        self.writes = []

    def set_status(self, order_id, status):
        self.writes.append((order_id, status))
        if status in self.fail_on:
            raise psycopg.OperationalError("db down")
        if self.status.get(order_id) not in ("PENDING", "PROCESSING"):
            return False
        self.status[order_id] = status
        return True


class FakeQueue:
    """Redis list semantics: LPUSH at the left, BRPOP/RPUSH at the right."""

    def __init__(self):
        self.items = []
        self.down = False
        self.push_down = False
        self.pops = 0

    def brpop(self, key, timeout):
        self.pops += 1
        if self.down:
            raise redis.exceptions.ConnectionError("redis down")
        if not self.items:
            return None
        return key.encode(), self.items.pop()

    def rpush(self, key, value):
        if self.push_down:
            raise redis.exceptions.ConnectionError("redis down")
        self.items.append(value)

    def lpush_order(self, order_id, trace_id="trace-abc"):
        self.items.insert(0, json.dumps({"order_id": order_id, "trace_id": trace_id}).encode())


class Logs:
    def __init__(self, path):
        self.path = path

    def lines(self):
        return [json.loads(line) for line in self.path.read_text().splitlines()]

    def messages(self):
        return [line["message"] for line in self.lines()]

    def find(self, message):
        return [line for line in self.lines() if line["message"] == message]


@pytest.fixture
def logs(tmp_path):
    path = tmp_path / "worker.json"
    setup_logging("DEBUG", str(path))
    return Logs(path)


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def queue():
    return FakeQueue()


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def worker(store, queue, logs, sleeps):
    import logging

    return Worker(store, queue, logging.getLogger("order-worker"),
                  sleep=sleeps.append, work_seconds=lambda: 1.5)
