"""Worker configuration, read only from environment variables (contracts/stack.md)."""

import os
from dataclasses import dataclass

# No defaults: a missing connection string must stop the worker at startup.
# SECRET_KEY is not required here; the worker never signs or checks tokens.
REQUIRED = ("DATABASE_URL", "REDIS_URL")

# An unknown level would make logging.setLevel raise deep inside startup;
# checking here turns it into a clear config error instead of a crash loop.
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# Accepted spellings for on/off flags. Anything else is a config error, so a
# typo like "ture" fails loudly instead of silently leaving the flag off.
TRUE_WORDS = ("true", "1", "yes", "on")
FALSE_WORDS = ("false", "0", "no", "off", "")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    log_file: str | None = None
    # Chaos flags (contracts/chaos.md), off by default. Never logged or
    # exposed anywhere: the blind drill must find them from symptoms only.
    chaos_slow_db: bool = False
    chaos_memory_leak: bool = False


def _flag(env, name: str) -> bool:
    value = env.get(name, "").strip().lower()
    if value in TRUE_WORDS:
        return True
    if value in FALSE_WORDS:
        return False
    raise ConfigError(f"{name} must be true or false")


def load_settings(env=None) -> Settings:
    env = os.environ if env is None else env

    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        # Only names are reported, never values.
        raise ConfigError("missing required environment variables: " + ", ".join(missing))

    log_level = env.get("LOG_LEVEL", "INFO").upper()
    if log_level not in LOG_LEVELS:
        raise ConfigError("LOG_LEVEL must be one of: " + ", ".join(LOG_LEVELS))

    return Settings(
        database_url=env["DATABASE_URL"],
        redis_url=env["REDIS_URL"],
        log_level=log_level,
        log_file=env.get("LOG_FILE") or None,
        chaos_slow_db=_flag(env, "CHAOS_SLOW_DB"),
        chaos_memory_leak=_flag(env, "CHAOS_MEMORY_LEAK"),
    )
