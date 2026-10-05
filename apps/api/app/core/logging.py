"""Structured JSON logging with structlog (OBS-1).

Every log line is JSON on stdout with `request_id` (bound by the middleware). String
values pass through `redact()` so personal identifiers never reach the logs.
"""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.redact import redact


def _redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = redact(value)
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog and route stdlib logging (uvicorn) through the same JSON format."""
    log_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_processor,
    ]

    structlog.configure(
        processors=[
            *shared,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # The request middleware logs every request, so uvicorn's access log would duplicate it.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
