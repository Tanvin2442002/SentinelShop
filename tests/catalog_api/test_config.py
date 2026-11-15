import pytest

from app.config import ConfigError, load_settings

BASE = {"DATABASE_URL": "postgresql://x", "REDIS_URL": "redis://x", "SECRET_KEY": "k"}


def test_required_vars_missing_fails_fast():
    with pytest.raises(ConfigError) as err:
        load_settings({"DATABASE_URL": "postgresql://x"})
    assert "REDIS_URL" in str(err.value) and "SECRET_KEY" in str(err.value)


def test_empty_secret_counts_as_missing():
    with pytest.raises(ConfigError):
        load_settings({**BASE, "SECRET_KEY": ""})


def test_optional_defaults():
    s = load_settings(BASE)
    assert s.log_level == "INFO"
    assert s.log_file is None
    assert s.token_ttl_seconds == 3600


def test_bad_ttl_rejected():
    with pytest.raises(ConfigError):
        load_settings({**BASE, "TOKEN_TTL_SECONDS": "abc"})


def test_bad_log_level_rejected():
    with pytest.raises(ConfigError) as err:
        load_settings({**BASE, "LOG_LEVEL": "verbose"})
    assert "LOG_LEVEL" in str(err.value)
    assert load_settings({**BASE, "LOG_LEVEL": "warning"}).log_level == "WARNING"


def test_config_error_exits_2_without_traceback(monkeypatch, capsys):
    from app.main import create_app

    for name, value in {**BASE, "LOG_LEVEL": "verbose"}.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit) as exit_info:
        create_app()
    assert exit_info.value.code == 2
    assert "LOG_LEVEL must be one of" in capsys.readouterr().err
