"""Structured logging (structlog) with automatic redaction of sensitive fields."""

from __future__ import annotations

import logging
from typing import Any

import structlog

# Any log key containing one of these fragments has its value replaced.
# `code` is redacted defensively: submitted source code must never reach the logs.
_SENSITIVE_FRAGMENTS = ("password", "token", "secret", "authorization", "cookie", "api_key")
_SENSITIVE_EXACT = {"code", "source_code", "hidden_input", "expected_output"}
_REDACTED = "[REDACTED]"


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return lowered in _SENSITIVE_EXACT or any(fragment in lowered for fragment in _SENSITIVE_FRAGMENTS)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (_REDACTED if isinstance(k, str) and _is_sensitive(k) else _redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    return value


def redact_sensitive(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return _redact(event_dict)


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive,
        structlog.processors.StackInfoRenderer(),
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: Any = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Route uvicorn through our handler; access logs come from RequestContextMiddleware instead.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)
