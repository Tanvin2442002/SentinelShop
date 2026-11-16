import json

from prometheus_client import REGISTRY


def _created():
    return REGISTRY.get_sample_value("orders_created_total") or 0.0


def _log_lines(settings):
    with open(settings.log_file) as f:
        return [json.loads(line) for line in f if line.strip()]


def test_create_order_returns_201_and_enqueues(client, store, fake_redis):
    before = _created()
    tid = "0123456789abcdef0123456789abcdef"
    r = client.post("/orders", json={"product_id": 1, "quantity": 2}, headers={"X-Trace-Id": tid})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "status": "PENDING"}
    assert store.orders[1]["status"] == "PENDING"
    queued = fake_redis.lists["orders:pending"]
    assert [json.loads(m) for m in queued] == [{"order_id": 1, "trace_id": tid}]
    assert _created() == before + 1


def test_create_order_unknown_product_is_404(client, fake_redis):
    r = client.post("/orders", json={"product_id": 999, "quantity": 1})
    assert r.status_code == 404
    assert r.json() == {"detail": "product not found"}
    assert "orders:pending" not in fake_redis.lists


def test_create_order_bad_body_is_422(client):
    for body in ({"product_id": 0, "quantity": 1},
                 {"product_id": 1, "quantity": 0},
                 {"product_id": 1, "quantity": 101},
                 {"product_id": "x", "quantity": 1},
                 {"quantity": 1}):
        r = client.post("/orders", json=body)
        assert r.status_code == 422, body
        assert isinstance(r.json()["detail"], str)


def test_create_order_queue_down_is_503_and_row_failed(client, store, fake_redis, settings):
    fake_redis.down = True
    before = _created()
    r = client.post("/orders", json={"product_id": 1, "quantity": 1})
    assert r.status_code == 503
    assert "queue" in r.json()["detail"]
    assert store.orders[1]["status"] == "FAILED"
    assert _created() == before
    failed = [l for l in _log_lines(settings) if l["message"] == "order creation failed"]
    assert failed[-1]["level"] == "ERROR"
    assert failed[-1]["order_id"] == 1
    assert failed[-1]["trace_id"] == r.headers["X-Trace-Id"]


def test_get_order(client):
    client.post("/orders", json={"product_id": 2, "quantity": 3})
    r = client.get("/orders/1")
    assert r.status_code == 200
    assert r.json() == {"id": 1, "product_id": 2, "quantity": 3, "status": "PENDING"}


def test_get_order_missing_is_404(client):
    r = client.get("/orders/42")
    assert r.status_code == 404


def test_order_route_template_in_metrics(client):
    labels = {"method": "GET", "route": "/orders/{id}", "status": "404"}
    before = REGISTRY.get_sample_value("http_requests_total", labels) or 0.0
    client.get("/orders/42")
    assert REGISTRY.get_sample_value("http_requests_total", labels) == before + 1


def test_create_order_db_down_is_503_and_logged(client, store, fake_redis, settings):
    store.create_fails = True
    before = _created()
    r = client.post("/orders", json={"product_id": 1, "quantity": 1})
    assert r.status_code == 503
    assert r.json() == {"detail": "order service unavailable, try again later"}
    assert "orders:pending" not in fake_redis.lists
    assert _created() == before
    failed = [l for l in _log_lines(settings) if l["message"] == "order creation failed"][-1]
    assert failed["level"] == "ERROR"
    assert failed["trace_id"] == r.headers["X-Trace-Id"]
    assert "order_id" not in failed  # no row was created


def test_queue_and_db_down_is_503_not_500(client, store, fake_redis, settings):
    fake_redis.down = True
    store.mark_fails = True
    r = client.post("/orders", json={"product_id": 1, "quantity": 1})
    assert r.status_code == 503
    failed = [l for l in _log_lines(settings) if l["message"] == "order creation failed"][-1]
    assert failed["order_id"] == 1
    assert "could not mark order FAILED" in failed["reason"]
    assert not [l for l in _log_lines(settings) if l["message"] == "unhandled error"]


def test_create_order_rejects_non_strict_ints(client, store):
    for body in ({"product_id": True, "quantity": 1},
                 {"product_id": "1", "quantity": 1},
                 {"product_id": 1.0, "quantity": 1},
                 {"product_id": 1, "quantity": "2"},
                 {"product_id": 1, "quantity": 1.5},
                 {"product_id": 1, "quantity": False}):
        r = client.post("/orders", json=body)
        assert r.status_code == 422, body
    assert store.orders == {}
