"""Chaos flags for catalog-api (contracts/chaos.md): off by default, on changes behaviour."""

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, load_settings
from app.main import create_app

BASE = {"DATABASE_URL": "postgresql://x", "REDIS_URL": "redis://x", "SECRET_KEY": "k"}


def make_client(settings, store, fake_redis, rolls, sleeps):
    """App whose random() returns the values in `rolls` in turn and whose sleep is recorded."""
    rolls = iter(rolls)
    app = create_app(settings=settings, store=store, redis_client=fake_redis,
                     chaos_random=lambda: next(rolls), chaos_sleep=sleeps.append)
    return TestClient(app)


def log_lines(settings):
    with open(settings.log_file) as f:
        return [json.loads(line) for line in f]


# --- config ---------------------------------------------------------------

def test_chaos_flags_off_by_default():
    s = load_settings(BASE)
    assert s.chaos_latency_ms == 0
    assert s.chaos_error_rate == 0.0


def test_chaos_flags_read_from_env():
    s = load_settings({**BASE, "CHAOS_LATENCY_MS": "1500", "CHAOS_ERROR_RATE": "0.4"})
    assert s.chaos_latency_ms == 1500
    assert s.chaos_error_rate == 0.4
    # Empty value (e.g. "CHAOS_LATENCY_MS=" in an env file) means off.
    assert load_settings({**BASE, "CHAOS_LATENCY_MS": "", "CHAOS_ERROR_RATE": ""}).chaos_latency_ms == 0


@pytest.mark.parametrize("name,value", [
    ("CHAOS_LATENCY_MS", "slow"), ("CHAOS_LATENCY_MS", "-5"),
    ("CHAOS_ERROR_RATE", "lots"), ("CHAOS_ERROR_RATE", "1.5"),
    ("CHAOS_ERROR_RATE", "-0.1"), ("CHAOS_ERROR_RATE", "nan"),
])
def test_bad_chaos_values_rejected(name, value):
    with pytest.raises(ConfigError) as err:
        load_settings({**BASE, name: value})
    assert name in str(err.value)


# --- nothing reveals a flag -----------------------------------------------

def test_flags_on_leave_no_trace_in_logs_or_metrics(settings, store, fake_redis):
    on = replace(settings, chaos_latency_ms=1500, chaos_error_rate=0.4)
    with make_client(on, store, fake_redis, [0.0, 0.0], []) as c:
        c.get("/products/1")
        c.post("/orders", json={"product_id": 1, "quantity": 1})
        metrics_text = c.get("/metrics").text
    logs_text = open(settings.log_file).read()
    for text in (logs_text, metrics_text):
        assert "chaos" not in text.lower()


# --- CHAOS_LATENCY_MS -----------------------------------------------------

def test_latency_off_never_sleeps(settings, store, fake_redis):
    sleeps = []
    # Rolls of 0.0 would trigger the delay if the flag were on.
    with make_client(settings, store, fake_redis, [0.0] * 5, sleeps) as c:
        for _ in range(5):
            assert c.get("/products/1").status_code == 200
    assert sleeps == []


def test_latency_on_delays_about_30_percent_of_product_reads(settings, store, fake_redis):
    on = replace(settings, chaos_latency_ms=1500)
    sleeps = []
    # Below 0.3 is delayed, at or above is not.
    with make_client(on, store, fake_redis, [0.1, 0.29, 0.3, 0.9], sleeps) as c:
        for _ in range(4):
            assert c.get("/products/1").status_code == 200
    assert sleeps == [1.5, 1.5]


def test_latency_only_affects_product_by_id(settings, store, fake_redis):
    on = replace(settings, chaos_latency_ms=1500)
    sleeps = []
    with make_client(on, store, fake_redis, [], sleeps) as c:
        # An empty rolls iterator would raise if any of these asked for a roll.
        assert c.get("/products").status_code == 200
        assert c.get("/search", params={"q": "mouse"}).status_code == 200
        assert c.post("/orders", json={"product_id": 1, "quantity": 1}).status_code == 201
    assert sleeps == []


# --- CHAOS_ERROR_RATE -----------------------------------------------------

def test_error_rate_off_orders_succeed(settings, store, fake_redis):
    with make_client(settings, store, fake_redis, [0.0] * 3, []) as c:
        for _ in range(3):
            assert c.post("/orders", json={"product_id": 1, "quantity": 1}).status_code == 201


def test_error_rate_on_returns_500_for_that_fraction(settings, store, fake_redis):
    on = replace(settings, chaos_error_rate=0.4)
    with make_client(on, store, fake_redis, [0.1, 0.39, 0.4, 0.8], []) as c:
        codes = [c.post("/orders", json={"product_id": 1, "quantity": 1}).status_code
                 for _ in range(4)]
    assert codes == [500, 500, 201, 201]
    # Failed orders leave no row and no queue message behind.
    assert len(store.orders) == 2
    assert len(fake_redis.lists["orders:pending"]) == 2


def test_error_rate_500_looks_like_a_real_bug(settings, store, fake_redis):
    on = replace(settings, chaos_error_rate=1.0)
    with make_client(on, store, fake_redis, [0.5], []) as c:
        resp = c.post("/orders", json={"product_id": 1, "quantity": 1},
                      headers={"X-Trace-Id": "abc123"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "internal error"}

    lines = log_lines(settings)
    failed, = [l for l in lines if l["message"] == "order creation failed"]
    assert failed["level"] == "ERROR"
    assert failed["trace_id"] == "abc123"
    access, = [l for l in lines if l["message"] == "request" and l["path"] == "/orders"]
    assert access["status"] == 500 and access["level"] == "ERROR"

    # Contract: nothing a viewer sees during the drill may mention chaos.
    assert "chaos" not in resp.text.lower()
    assert "chaos" not in json.dumps(lines).lower()
