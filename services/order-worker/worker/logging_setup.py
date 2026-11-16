"""JSON-lines logging (contracts/logging.md): one object per line, UTC timestamps."""

import json
import logging
import sys
from datetime import datetime, timezone

SERVICE = "order-worker"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "service": SERVICE,
            "message": record.getMessage(),
        }
        # Structured fields are passed as extra={"fields": {...}}.
        line.update(getattr(record, "fields", {}))
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def setup_logging(level: str = "INFO", log_file: str | None = None) -> logging.Logger:
    formatter = JsonFormatter()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    for handler in handlers:
        handler.setFormatter(formatter)

    logger = logging.getLogger(SERVICE)
    # Replace handlers so calling this twice (tests) does not duplicate lines.
    for old in list(logger.handlers):
        logger.removeHandler(old)
        old.close()
    for handler in handlers:
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False

    # psycopg pool reconnect warnings go through the same JSON handlers so
    # every line on stdout stays parseable.
    psycopg_logger = logging.getLogger("psycopg")
    psycopg_logger.handlers = list(handlers)
    psycopg_logger.propagate = False

    return logger
