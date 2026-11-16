"""Chaos flags for order-worker (contracts/chaos.md): off by default, on changes behaviour."""

import logging

import pytest

from worker import main as worker_main
from worker.config import ConfigError, load_settings
from worker.main import CHAOS_LEAK_BYTES, Worker

BASE = {"DATABASE_URL": "postgresql://x", "REDIS_URL": "redis://y"}


@pytest.fixture(autouse=True)
def empty_leak():
    # The leak list is global on purpose; reset it so tests do not see each other.
    worker_main._leaked.clear()
    yield
    worker_main._leaked.clear()


def chaos_worker(store, queue, sleeps, **flags):
    return Worker(store, queue, logging.getLogger("order-worker"),
                  sleep=sleeps.append, work_seconds=lambda: 1.5, **flags)


# --- config ---------------------------------------------------------------

def test_chaos_flags_off_by_default():
    s = load_settings(BASE)
    assert s.chaos_slow_db is False
    assert s.chaos_memory_leak is False


def test_chaos_flags_read_from_env():
    s = load_settings({**BASE, "CHAOS_SLOW_DB": "true", "CHAOS_MEMORY_LEAK": "TRUE"})
    assert s.chaos_slow_db is True and s.chaos_memory_leak is True
    s = load_settings({**BASE, "CHAOS_SLOW_DB": "false", "CHAOS_MEMORY_LEAK": ""})
    assert s.chaos_slow_db is False and s.chaos_memory_leak is False


@pytest.mark.parametrize("name", ["CHAOS_SLOW_DB", "CHAOS_MEMORY_LEAK"])
def test_typo_in_flag_rejected(name):
    with pytest.raises(ConfigError) as err:
        load_settings({**BASE, name: "ture"})
    assert name in str(err.value)


# --- CHAOS_SLOW_DB --------------------------------------------------------

def test_slow_db_off_only_work_sleep(worker, store, queue, sleeps):
    store.status[1] = "PENDING"
    queue.lpush_order(1)
    worker.run_once()
    assert sleeps == [1.5]


def test_slow_db_on_sleeps_2s_before_each_update(store, queue, sleeps, logs):
    w = chaos_worker(store, queue, sleeps, slow_db=True)
    store.status[1] = "PENDING"
    queue.lpush_order(1)
    w.run_once()
    # 2 s before PROCESSING, the 1.5 s of work, 2 s before COMPLETED.
    assert sleeps == [2.0, 1.5, 2.0]
    assert store.status[1] == "COMPLETED"
    completed, = logs.find("order completed")
    assert "chaos" not in str(completed).lower()


# --- CHAOS_MEMORY_LEAK ----------------------------------------------------

def test_memory_leak_off_keeps_nothing(worker, store, queue):
    store.status[1] = "PENDING"
    queue.lpush_order(1)
    worker.run_once()
    assert worker_main._leaked == []


def test_memory_leak_on_keeps_2mb_filled_per_order(store, queue, sleeps, logs):
    w = chaos_worker(store, queue, sleeps, memory_leak=True)
    for order_id in (1, 2, 3):
        store.status[order_id] = "PENDING"
        queue.lpush_order(order_id)
        w.run_once()
    assert len(worker_main._leaked) == 3
    chunk = worker_main._leaked[0]
    assert len(chunk) == CHAOS_LEAK_BYTES == 2 * 1024 * 1024
    # Filled with a non-zero byte, not lazily zeroed memory.
    assert chunk.count(0) == 0
    # Orders still complete normally; only memory grows.
    assert all(store.status[i] == "COMPLETED" for i in (1, 2, 3))


# --- nothing reveals a flag -----------------------------------------------

class NullStore:
    def __init__(self, pool):
        pass

    def open(self):
        pass

    def close(self):
        pass


def test_startup_with_flags_on_never_mentions_chaos(monkeypatch, tmp_path):
    import json

    log_file = tmp_path / "worker.json"
    env = {**BASE, "CHAOS_SLOW_DB": "true", "CHAOS_MEMORY_LEAK": "true",
           "LOG_FILE": str(log_file)}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    built = []
    # Stub out everything that needs the real stack; run() returns at once.
    monkeypatch.setattr(worker_main, "make_pool", lambda url: None)
    monkeypatch.setattr(worker_main, "Store", NullStore)
    monkeypatch.setattr(worker_main, "make_redis", lambda url: None)
    monkeypatch.setattr(worker_main.metrics, "start_metrics_server", lambda: None)
    monkeypatch.setattr(worker_main.signal, "signal", lambda *a: None)
    monkeypatch.setattr(Worker, "run", lambda self: built.append(self) or 0)

    assert worker_main.main() == 0
    # The flags did reach the worker...
    assert built[0].slow_db is True and built[0].memory_leak is True
    # ...but no log line says so.
    lines = [json.loads(l) for l in log_file.read_text().splitlines()]
    assert lines, "expected at least the startup line"
    assert "chaos" not in json.dumps(lines).lower()
