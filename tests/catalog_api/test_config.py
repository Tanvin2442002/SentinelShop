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
