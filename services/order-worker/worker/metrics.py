"""Prometheus metrics (contracts/metrics.md). Names and labels are frozen."""

from prometheus_client import Counter, Histogram, start_http_server

METRICS_PORT = 9100

# Normal orders take 1-2 s; CHAOS_SLOW_DB adds about 4 s, so the buckets are
# finer around 1-10 s than the API's request buckets.
BUCKETS = (0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10, 15, 30)

ORDERS_PROCESSED = Counter(
    "orders_processed_total",
    "Orders that reached a final result",
    ["result"],
)
ORDER_PROCESSING = Histogram(
    "order_processing_seconds",
    "Time from queue pop to the final DB update",
    buckets=BUCKETS,
)

# Create both series at 0 so rate() works before the first failure happens.
for _result in ("completed", "failed"):
    ORDERS_PROCESSED.labels(_result)


def start_metrics_server() -> None:
    # The default registry already includes the process collector, which
    # provides process_resident_memory_bytes (required by the contract).
    start_http_server(METRICS_PORT)
