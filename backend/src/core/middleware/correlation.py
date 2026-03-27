"""
Correlation ID middleware for distributed request tracing.

SARAISE-17007: All requests MUST carry a correlation_id for observability.

Generates a unique correlation_id per request, propagates it via:
- Request attribute (request.correlation_id)
- Response header (X-Correlation-ID)
- Logging context (structlog/logging filter)
- ContextVar for async propagation across Celery tasks

If the client sends X-Correlation-ID header, it is reused (trusted in SaaS
mode from platform, untrusted from external clients — validated format).
"""

from __future__ import annotations

import contextvars
import logging
import re
import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("saraise.middleware.correlation")

# ContextVar for async propagation (Celery, threads)
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")

# Valid correlation_id format: UUID v4 or prefixed UUID (e.g., "req_abc123...")
_CORRELATION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")

HEADER_NAME = "X-Correlation-ID"


def get_correlation_id() -> str:
    """Get current correlation_id from context. Safe to call from anywhere."""
    return correlation_id_var.get("")


def _generate_correlation_id() -> str:
    """Generate a new correlation_id."""
    return f"req_{uuid.uuid4().hex[:24]}"


class CorrelationIdMiddleware:
    """
    Django middleware that assigns and propagates correlation IDs.

    Order: Should be placed early in MIDDLEWARE stack (after SecurityMiddleware).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Extract or generate correlation_id
        incoming_id = request.META.get(f"HTTP_{HEADER_NAME.upper().replace('-', '_')}", "")

        if incoming_id and _CORRELATION_ID_PATTERN.match(incoming_id):
            cid = incoming_id
        else:
            cid = _generate_correlation_id()

        # Set on request object
        request.correlation_id = cid  # type: ignore[attr-defined]

        # Set in ContextVar for async propagation
        token = correlation_id_var.set(cid)

        try:
            response = self.get_response(request)
        finally:
            # Reset ContextVar
            correlation_id_var.reset(token)

        # Set response header
        response[HEADER_NAME] = cid

        return response


class CorrelationIdFilter(logging.Filter):
    """
    Logging filter that injects correlation_id into log records.

    Usage in LOGGING config:
        "filters": {
            "correlation_id": {
                "()": "src.core.middleware.correlation.CorrelationIdFilter",
            }
        }
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get("no-correlation-id")  # type: ignore[attr-defined]
        return True
