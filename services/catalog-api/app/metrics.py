"""Prometheus metrics (contracts/metrics.md). Names and labels are frozen."""

from prometheus_client import Counter, Gauge, Histogram

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

# Defined once at import time: the default registry refuses duplicate names.
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests handled",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
    buckets=BUCKETS,
)
ORDERS_CREATED = Counter("orders_created_total", "Orders created")
QUEUE_DEPTH = Gauge("order_queue_depth", "Length of the orders:pending Redis list")

QUEUE_KEY = "orders:pending"


def refresh_queue_depth(redis_client) -> None:
    """Set order_queue_depth from LLEN; NaN when Redis is unreachable."""
    try:
        QUEUE_DEPTH.set(redis_client.llen(QUEUE_KEY))
    except Exception:
        QUEUE_DEPTH.set(float("nan"))
