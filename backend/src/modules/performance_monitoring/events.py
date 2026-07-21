"""Allowlisted durable monitoring domain events."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Final
from uuid import UUID

from src.core.async_jobs.models import OutboxEvent
from src.core.observability import get_correlation_id

EVENT_TYPES: Final = frozenset(
    {
        "metric.recorded",
        "alert.fired",
        "alert.acknowledged",
        "alert.resolved",
        "sla.breach",
        "sla.compliance_checked",
        "sla.report_generated",
    }
)
SAFE_KEYS: Final = frozenset(
    {
        "metric_name",
        "value",
        "alert_id",
        "alert_rule_id",
        "severity",
        "status",
        "sla_id",
        "is_compliant",
        "actual_value",
        "report_id",
        "period",
    }
)


def publish_domain_event(
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    *,
    payload: Mapping[str, object] | None = None,
    created_by: UUID | None = None,
) -> OutboxEvent:
    if event_type not in EVENT_TYPES:
        raise ValueError("Unsupported monitoring event type.")
    safe_payload = dict(payload or {})
    unsafe = set(safe_payload) - SAFE_KEYS
    if unsafe:
        raise ValueError(f"Unsafe monitoring event fields: {', '.join(sorted(unsafe))}")
    event_id = uuid.uuid4()
    envelope = {
        "event_id": str(event_id),
        "schema_version": 1,
        "tenant_id": str(tenant_id),
        "event_type": event_type,
        "module": "performance_monitoring",
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "correlation_id": get_correlation_id() or str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "created_by": str(created_by or UUID(int=0)),
        "payload": safe_payload,
    }
    return OutboxEvent.objects.create(
        id=event_id,
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=envelope,
    )


def consume_request_completed(
    tenant_id: UUID,
    *,
    event_id: UUID,
    module: str,
    duration_ms: float,
    tags: Mapping[str, str] | None = None,
) -> object:
    from .services import MetricsCollectionService

    return MetricsCollectionService().record_metric(
        tenant_id,
        f"{module}.request.duration_ms",
        duration_ms,
        tags=tags,
        metric_type="histogram",
        source_module=module,
        idempotency_key=f"request.completed:{event_id}",
    )


def consume_error_occurred(tenant_id: UUID, *, event_id: UUID, module: str, session_id: str) -> object:
    from .models import MetricDataPoint
    from .services import MetricsCollectionService

    name = f"{module}.error.count"
    latest = (
        MetricDataPoint.objects.for_tenant(tenant_id)
        .filter(metric__metric_name=name, session_id=session_id)
        .order_by("-timestamp")
        .first()
    )
    value = float(latest.value) + 1 if latest else 1
    return MetricsCollectionService().record_metric(
        tenant_id,
        name,
        value,
        metric_type="counter",
        source_module=module,
        session_id=session_id,
        idempotency_key=f"error.occurred:{event_id}",
    )


def consume_job_completed(
    tenant_id: UUID,
    *,
    event_id: UUID,
    module: str,
    duration_ms: float,
) -> object:
    from .services import MetricsCollectionService

    return MetricsCollectionService().record_metric(
        tenant_id,
        f"{module}.job.duration_ms",
        duration_ms,
        metric_type="histogram",
        source_module=module,
        idempotency_key=f"job.completed:{event_id}",
    )


__all__ = [
    "EVENT_TYPES",
    "consume_error_occurred",
    "consume_job_completed",
    "consume_request_completed",
    "publish_domain_event",
]
