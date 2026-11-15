import json

import pytest
from prometheus_client import REGISTRY

from worker.main import BadMessage, parse_message


def processed(result):
    return REGISTRY.get_sample_value("orders_processed_total", {"result": result}) or 0.0


def processing_count():
    return REGISTRY.get_sample_value("order_processing_seconds_count") or 0.0


def test_happy_path_processing_then_completed(worker, store, queue, logs, sleeps):
    store.status[7] = "PENDING"
    queue.lpush_order(7, "trace-123")
    completed_before, count_before = processed("completed"), processing_count()

    worker.run_once()

    assert store.writes == [(7, "PROCESSING"), (7, "COMPLETED")]
    assert store.status[7] == "COMPLETED"
    assert sleeps == [1.5]  # the simulated 1-2 s of work
    assert processed("completed") == completed_before + 1
    assert processing_count() == count_before + 1

    picked, = logs.find("order picked")
    assert picked["trace_id"] == "trace-123" and picked["order_id"] == 7
    done, = logs.find("order completed")
    for field in ("timestamp", "level", "service", "message", "trace_id", "order_id", "duration_ms"):
        assert field in done
    assert done["service"] == "order-worker"
    assert done["result"] == "completed"
    assert done["level"] == "INFO"


def test_default_work_time_is_between_1_and_2_seconds(store, queue, logs):
    import logging

    from worker.main import Worker

    w = Worker(store, queue, logging.getLogger("order-worker"))
    for _ in range(200):
        assert 1 <= w.work_seconds() <= 2


@pytest.mark.parametrize("failing_write", ["PROCESSING", "COMPLETED"])
def test_db_failure_after_pop_pushes_message_back(worker, store, queue, logs, failing_write):
    store.status[3] = "PENDING"
    queue.lpush_order(3)
    original = list(queue.items)
    store.fail_on = {failing_write}
    completed_before, failed_before = processed("completed"), processed("failed")

    worker.run_once()

    # Back on the queue, at the end BRPOP takes from, unchanged.
    assert queue.items == original
    assert processed("completed") == completed_before
    assert processed("failed") == failed_before  # not final: it will be retried
    line, = logs.find("order failed")
    assert line["result"] == "requeued" and line["order_id"] == 3

    # DB back: the same message completes on the next pass.
    store.fail_on = set()
    worker.run_once()
    assert store.status[3] == "COMPLETED"
    assert queue.items == []


def test_db_and_redis_down_logs_raw_message(worker, store, queue, logs):
    store.status[4] = "PENDING"
    queue.lpush_order(4)
    raw = queue.items[0]
    store.fail_on = {"PROCESSING"}
    queue.push_down = True
    failed_before = processed("failed")

    worker.run_once()

    line, = logs.find("order failed")
    assert line["level"] == "ERROR"
    assert line["queue_message"] == raw.decode()
    assert processed("failed") == failed_before + 1


def test_order_not_in_flight_is_failed_not_requeued(worker, store, queue, logs):
    store.status[5] = "FAILED"  # e.g. the API marked it FAILED after an LPUSH timeout
    queue.lpush_order(5)
    failed_before = processed("failed")

    worker.run_once()

    assert store.status[5] == "FAILED"
    assert queue.items == []
    assert processed("failed") == failed_before + 1
    assert logs.find("order failed")[0]["result"] == "failed"


def test_bad_message_is_dropped_and_counted(worker, store, queue, logs):
    queue.items = [b"not json"]
    failed_before = processed("failed")

    worker.run_once()

    assert store.writes == []
    assert queue.items == []
    assert processed("failed") == failed_before + 1
    assert logs.find("order failed")[0]["level"] == "ERROR"


def test_redis_down_keeps_worker_alive(worker, queue, logs, sleeps):
    queue.down = True
    worker.run_once()  # must not raise
    worker.run_once()
    assert logs.messages() == ["queue unavailable", "queue unavailable"]
    assert sum(sleeps) == pytest.approx(2.0)  # 1 s pause each time, no busy loop


def test_empty_queue_does_nothing(worker, store, logs):
    worker.run_once()
    assert store.writes == []
    assert logs.messages() == []


def test_parse_message():
    assert parse_message(json.dumps({"order_id": 9, "trace_id": "t1"})) == (9, "t1")
    # Missing trace_id: a fresh one, so the order still moves.
    order_id, trace_id = parse_message(b'{"order_id": 9}')
    assert order_id == 9 and len(trace_id) == 32
    for bad in (b"[]", b"{", b'{"order_id": true}', b'{"order_id": 0}', b'{"order_id": "9"}'):
        with pytest.raises(BadMessage):
            parse_message(bad)
