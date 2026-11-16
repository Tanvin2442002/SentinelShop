"""A Redis that accepts TCP connections but never answers must not hang the API."""

import socket
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.queue import make_redis

# Contract-driven budget: 2 s Redis timeout plus a little slack.
FAIL_FAST_SECONDS = 2.5


@pytest.fixture
def silent_redis_url():
    # The kernel completes the TCP handshake (listen backlog), but nothing ever
    # reads or replies, so every Redis command waits for the socket timeout.
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(16)
    yield f"redis://127.0.0.1:{server.getsockname()[1]}/0"
    server.close()


def test_redis_client_has_2s_timeouts_and_no_retries():
    client = make_redis("redis://redis:6379/0")
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["socket_connect_timeout"] == 2
    assert kwargs["socket_timeout"] == 2
    assert kwargs["retry"].get_retries() == 0


@pytest.fixture
def slow_queue_client(settings, store, silent_redis_url):
    app = create_app(settings=settings, store=store, redis_client=make_redis(silent_redis_url))
    with TestClient(app) as c:
        yield c


def test_readyz_fails_fast_when_redis_hangs(slow_queue_client):
    start = time.monotonic()
    r = slow_queue_client.get("/readyz")
    elapsed = time.monotonic() - start

    assert r.status_code == 503
    assert r.json() == {"status": "not_ready", "failing": ["queue"]}
    assert elapsed < FAIL_FAST_SECONDS


def test_post_order_fails_fast_when_redis_hangs(slow_queue_client, store):
    start = time.monotonic()
    r = slow_queue_client.post("/orders", json={"product_id": 1, "quantity": 1})
    elapsed = time.monotonic() - start

    assert r.status_code == 503
    assert elapsed < FAIL_FAST_SECONDS
    assert store.orders[1]["status"] == "FAILED"
