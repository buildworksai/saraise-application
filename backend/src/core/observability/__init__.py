"""Structured logging and distributed correlation primitives for SARAISE.

The public imports in this package are intentionally small and stable. Paid
modules can bind richer tenant or actor metadata without depending on Django or
Celery implementation details.
"""

from src.core.observability.correlation import (
    CORRELATION_HEADER,
    REQUEST_HEADER,
    CorrelationContext,
    CorrelationMiddleware,
    TaskContext,
    bind_correlation_context,
    bind_task_context,
    get_correlation_context,
    get_correlation_id,
    get_task_context,
)
from src.core.observability.logging import JSONFormatter, ObservabilityContextFilter

__all__ = [
    "CORRELATION_HEADER",
    "REQUEST_HEADER",
    "CorrelationContext",
    "CorrelationMiddleware",
    "JSONFormatter",
    "ObservabilityContextFilter",
    "TaskContext",
    "bind_correlation_context",
    "bind_task_context",
    "get_correlation_context",
    "get_correlation_id",
    "get_task_context",
]
