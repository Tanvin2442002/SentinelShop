import signal

import pytest


@pytest.fixture
def sigterm_to(worker):
    previous = signal.signal(signal.SIGTERM, worker.request_stop)
    yield
    signal.signal(signal.SIGTERM, previous)


def test_sigterm_mid_order_finishes_it_then_exits_0(worker, store, queue, logs, sigterm_to):
    store.status.update({1: "PENDING", 2: "PENDING"})
    queue.lpush_order(1)
    queue.lpush_order(2)

    def work_then_sigterm(seconds):
        # A real SIGTERM delivered to this process while order 1 is in its
        # 1-2 s of work.
        signal.raise_signal(signal.SIGTERM)

    worker.sleep = work_then_sigterm

    assert worker.run() == 0

    assert store.status[1] == "COMPLETED"  # the current order was finished
    assert store.status[2] == "PENDING"  # no new message was taken
    assert len(queue.items) == 1 and queue.pops == 1
    assert logs.messages() == ["order picked", "shutdown requested",
                               "order completed", "shutdown complete"]
    assert logs.find("shutdown requested")[0]["signal"] == "SIGTERM"


def test_sigterm_while_idle_exits_within_one_brpop(worker, queue, logs, sigterm_to):
    original_brpop = queue.brpop

    def brpop_then_sigterm(key, timeout):
        assert timeout <= 1  # so an idle worker notices SIGTERM within ~1 s
        signal.raise_signal(signal.SIGTERM)
        return original_brpop(key, timeout)

    queue.brpop = brpop_then_sigterm
    assert worker.run() == 0
    assert queue.pops == 1
    assert logs.messages() == ["shutdown requested", "shutdown complete"]


def test_sigterm_during_outage_pause_stops_quickly(worker, queue, logs, sigterm_to):
    queue.down = True
    calls = []

    def sleep(seconds):
        calls.append(seconds)
        signal.raise_signal(signal.SIGTERM)

    worker.sleep = sleep
    assert worker.run() == 0
    assert calls == [0.1]  # the 1 s pause was cut short
