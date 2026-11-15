"""Worker configuration, read only from environment variables (contracts/stack.md)."""

import os
from dataclasses import dataclass

# No defaults: a missing connection string must stop the worker at startup.
# SECRET_KEY is not required here; the worker never signs or checks tokens.
REQUIRED = ("DATABASE_URL", "REDIS_URL")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    log_file: str | None = None


def load_settings(env=None) -> Settings:
    env = os.environ if env is None else env

    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        # Only names are reported, never values.
        raise ConfigError("missing required environment variables: " + ", ".join(missing))

    return Settings(
        database_url=env["DATABASE_URL"],
        redis_url=env["REDIS_URL"],
        log_level=env.get("LOG_LEVEL", "INFO").upper(),
        log_file=env.get("LOG_FILE") or None,
    )
