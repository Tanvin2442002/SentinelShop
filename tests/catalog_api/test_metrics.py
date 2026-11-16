import math

from prometheus_client import REGISTRY


def _value(name, labels=None):
    v = REGISTRY.get_sample_value(name, labels or {})
    return 0.0 if v is None else v


def test_request_counter_uses_route_template(client):
    labels = {"method": "GET", "route": "/products/{id}", "status": "200"}
    before = _value("http_requests_total", labels)
    client.get("/products/1")
    client.get("/products/2")
    assert _value("http_requests_total", labels) == before + 2
    # The raw path must never become a label value.
    assert REGISTRY.get_sample_value(
        "http_requests_total", {"method": "GET", "route": "/products/1", "status": "200"}
    ) is None


def test_unknown_path_counted_as_unmatched(client):
    labels = {"method": "GET", "route": "unmatched", "status": "404"}
    before = _value("http_requests_total", labels)
    client.get("/does/not/exist")
    assert _value("http_requests_total", labels) == before + 1


def test_duration_histogram_has_contract_buckets(client):
    client.get("/products")
    for le in ("0.005", "0.25", "10.0", "+Inf"):
        assert REGISTRY.get_sample_value(
            "http_request_duration_seconds_bucket",
            {"method": "GET", "route": "/products", "le": le},
        ) is not None


def test_metrics_endpoint_exposes_contract_names(client, fake_redis):
    fake_redis.lists["orders:pending"] = ["a", "b", "c"]
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    text = r.text
    for name in ("http_requests_total", "http_request_duration_seconds_bucket",
                 "orders_created_total", "order_queue_depth"):
        assert name in text
    assert _value("order_queue_depth") == 3


def test_queue_depth_nan_when_redis_down(client, fake_redis):
    fake_redis.down = True
    r = client.get("/metrics")
    assert r.status_code == 200
    assert math.isnan(REGISTRY.get_sample_value("order_queue_depth"))
