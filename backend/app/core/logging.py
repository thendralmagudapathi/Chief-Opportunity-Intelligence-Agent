"""Structured logging.

JSON in production, human-readable in development. A redaction processor drops
secret-bearing keys before anything reaches a handler, because logs are the most
common accidental exfiltration path for profile data.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

from app.core.config import Settings

REDACTED = "***redacted***"

# Matched case-insensitively against the *end* of a key as well, so
# ``user_password`` and ``hashed_password`` are both covered.
SENSITIVE_KEY_PARTS: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "token",
        "authorization",
        "api_key",
        "apikey",
        "cookie",
        "session",
        "private_key",
        "credential",
    }
)


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_sensitive(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if _is_sensitive(key):
            event_dict[key] = REDACTED
        elif isinstance(event_dict[key], dict):
            event_dict[key] = {
                k: (REDACTED if _is_sensitive(k) else v) for k, v in event_dict[key].items()
            }
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Configure structlog and route stdlib logging through it."""
    level = getattr(logging, settings.observability.log_level)

    shared_processors: list[structlog.typing.Processor] = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        redact_sensitive,
    ]

    renderer: structlog.typing.Processor
    if settings.observability.log_format == "json":
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Tame the noisy libraries; uvicorn access logging is replaced by our own
    # middleware so that every access line carries the request id.
    logging.basicConfig(level=level, stream=sys.stderr, format="%(message)s")
    for name, lib_level in (
        ("uvicorn.access", logging.WARNING),
        ("uvicorn.error", logging.INFO),
        ("sqlalchemy.engine", logging.WARNING),
        ("alembic", logging.INFO),
    ):
        logging.getLogger(name).setLevel(lib_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a logger with the module name bound as a field.

    The name is bound rather than derived by ``structlog.stdlib.add_logger_name``
    because that processor requires a stdlib-backed logger, and this
    configuration writes directly to stderr.
    """
    logger = structlog.get_logger()
    return logger.bind(logger=name) if name else logger  # type: ignore[no-any-return]


__all__ = [
    "bind_contextvars",
    "clear_contextvars",
    "configure_logging",
    "get_logger",
    "redact_sensitive",
]
