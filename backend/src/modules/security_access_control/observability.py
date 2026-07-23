"""Fail-fast structured logging contract for security access control."""

from __future__ import annotations

import logging

from django.core.exceptions import ImproperlyConfigured

from src.core.observability.logging import JSONFormatter, ObservabilityContextFilter

SECURITY_LOGGER_NAME = "saraise.security_access_control"


def _effective_handlers(logger: logging.Logger) -> tuple[logging.Handler, ...]:
    """Return handlers that can emit records from ``logger``."""
    handlers: list[logging.Handler] = []
    current: logging.Logger | None = logger
    while current is not None:
        handlers.extend(current.handlers)
        if not current.propagate:
            break
        current = current.parent
    return tuple(handlers)


def enforce_security_json_logging(logger: logging.Logger | None = None) -> logging.Logger:
    """Stop startup unless every security log sink is JSON and context-aware."""
    target = logger or logging.getLogger(SECURITY_LOGGER_NAME)
    handlers = _effective_handlers(target)
    if not handlers:
        raise ImproperlyConfigured(f"{SECURITY_LOGGER_NAME} has no configured logging handler")
    for handler in handlers:
        if not isinstance(handler.formatter, JSONFormatter):
            raise ImproperlyConfigured(
                f"{SECURITY_LOGGER_NAME} handler {type(handler).__name__} must use JSONFormatter"
            )
        if not any(isinstance(item, ObservabilityContextFilter) for item in handler.filters):
            raise ImproperlyConfigured(
                f"{SECURITY_LOGGER_NAME} handler {type(handler).__name__} must use ObservabilityContextFilter"
            )
    return target


__all__ = ["SECURITY_LOGGER_NAME", "enforce_security_json_logging"]
