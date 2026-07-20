"""Backward-compatible imports for the observability correlation foundation."""

from __future__ import annotations

import uuid

from src.core.observability import correlation as _correlation
from src.core.observability.logging import ObservabilityContextFilter

HEADER_NAME = _correlation.CORRELATION_HEADER
CorrelationIdMiddleware = _correlation.CorrelationIdMiddleware
CorrelationIdFilter = ObservabilityContextFilter
correlation_id_var = _correlation.correlation_id_var
get_correlation_id = _correlation.get_correlation_id


def _generate_correlation_id() -> str:
    """Return a canonical UUID for legacy callers."""
    return str(uuid.uuid4())
