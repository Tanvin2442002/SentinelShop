import pytest
from prometheus_client import REGISTRY, generate_latest

from worker import metrics
from worker.config import ConfigError, load_settings
from worker.queue import BRPOP_TIMEOUT_SECONDS, make_redis
from worker.store import Store


def test_config_requires_db_and_redis_but_not_secret_key():
    with pytest.raises(ConfigError) as exc:
        load_settings({"DATABASE_URL": "postgresql://x"})
    assert "REDIS_URL" in str(exc.value)

    s = load_settings({"DATABASE_URL": "postgresql://x", "REDIS_URL": "redis://y",
                       "LOG_FILE": "/var/log/shop/worker.json"})
    assert s.log_level == "INFO"
    assert s.log_file == "/var/log/shop/worker.json"


def test_metrics_names_match_contract():
    text = generate_latest(REGISTRY).decode()
    assert 'orders_processed_total{result="completed"}' in text
    assert 'orders_processed_total{result="failed"}' in text
    assert "order_processing_seconds_bucket" in text
    assert "process_resident_memory_bytes" in text
    assert metrics.METRICS_PORT == 9100


def test_redis_timeouts_longer_than_brpop_block():
    kwargs = make_redis("redis://redis:6379/0").connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == 2 and kwargs["socket_connect_timeout"] == 2
    assert kwargs["socket_timeout"] > BRPOP_TIMEOUT_SECONDS
    assert kwargs["retry"].get_retries() == 0


class RecordingPool:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def connection(self):
        pool = self

        class Conn:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                pool.calls.append((sql, params))
                return self

            def fetchone(self):
                return pool.row

        return Conn()


def test_set_status_uses_bound_parameters_and_in_flight_guard():
    pool = RecordingPool(row=(1,))
    assert Store(pool).set_status(1, "COMPLETED") is True
    sql, params = pool.calls[0]
    assert params == ("COMPLETED", 1)
    assert "%s" in sql and "COMPLETED" not in sql
    assert "status IN ('PENDING', 'PROCESSING')" in sql

    assert Store(RecordingPool(row=None)).set_status(1, "COMPLETED") is False


def test_bad_log_level_rejected():
    env = {"DATABASE_URL": "postgresql://x", "REDIS_URL": "redis://y"}
    with pytest.raises(ConfigError) as exc:
        load_settings({**env, "LOG_LEVEL": "verbose"})
    assert "LOG_LEVEL" in str(exc.value)
    assert load_settings({**env, "LOG_LEVEL": "debug"}).log_level == "DEBUG"


def test_config_error_exits_2(monkeypatch, capsys):
    from worker.main import main

    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("REDIS_URL", "redis://y")
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    assert main() == 2
    assert "LOG_LEVEL must be one of" in capsys.readouterr().err
