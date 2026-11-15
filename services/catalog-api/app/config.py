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

    return Settings(
        database_url=env["DATABASE_URL"],
        redis_url=env["REDIS_URL"],
        secret_key=env["SECRET_KEY"],
        log_level=log_level,
        log_file=env.get("LOG_FILE") or None,
        token_ttl_seconds=ttl,
    )
