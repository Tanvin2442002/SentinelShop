"""Service configuration, read only from environment variables (contracts/stack.md)."""

import os
from dataclasses import dataclass

# Required settings have NO default in code: a missing secret must stop the
# service at startup instead of silently running with a weak value.
REQUIRED = ("DATABASE_URL", "REDIS_URL", "SECRET_KEY")

# An unknown level would make logging.setLevel raise deep inside startup;
# checking here turns it into a clear config error instead of a crash loop.
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    secret_key: str
    log_level: str = "INFO"
    log_file: str | None = None
    token_ttl_seconds: int = 3600
    # Chaos flags (contracts/chaos.md). 0 means off, which is the default.
    # Never logged or exposed anywhere: the blind drill must find them from
    # symptoms only.
    chaos_latency_ms: int = 0
    chaos_error_rate: float = 0.0


def load_settings(env=None) -> Settings:
    env = os.environ if env is None else env

    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        # Only names are reported, never values.
        raise ConfigError("missing required environment variables: " + ", ".join(missing))

    try:
        ttl = int(env.get("TOKEN_TTL_SECONDS", "3600"))
    except ValueError:
        raise ConfigError("TOKEN_TTL_SECONDS must be an integer") from None

    log_level = env.get("LOG_LEVEL", "INFO").upper()
    if log_level not in LOG_LEVELS:
        raise ConfigError("LOG_LEVEL must be one of: " + ", ".join(LOG_LEVELS))

    # Empty counts as unset, so "CHAOS_LATENCY_MS=" in an env file means off.
    try:
        latency_ms = int(env.get("CHAOS_LATENCY_MS") or "0")
    except ValueError:
        raise ConfigError("CHAOS_LATENCY_MS must be an integer") from None
    if latency_ms < 0:
        raise ConfigError("CHAOS_LATENCY_MS must be 0 or more")

    try:
        error_rate = float(env.get("CHAOS_ERROR_RATE") or "0")
    except ValueError:
        raise ConfigError("CHAOS_ERROR_RATE must be a number between 0 and 1") from None
    # "not 0 <= x <= 1" also rejects nan, which no comparison is true for.
    if not 0 <= error_rate <= 1:
        raise ConfigError("CHAOS_ERROR_RATE must be a number between 0 and 1")

    return Settings(
        database_url=env["DATABASE_URL"],
        redis_url=env["REDIS_URL"],
        secret_key=env["SECRET_KEY"],
        log_level=log_level,
        log_file=env.get("LOG_FILE") or None,
        token_ttl_seconds=ttl,
        chaos_latency_ms=latency_ms,
        chaos_error_rate=error_rate,
    )
