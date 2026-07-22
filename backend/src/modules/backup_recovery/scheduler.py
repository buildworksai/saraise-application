"""Durable entry point used by the platform scheduler."""

from __future__ import annotations

import uuid
from datetime import datetime

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import enqueue
from src.core.tenancy import tenant_context


def enqueue_due_schedule_scan(tenant_id: uuid.UUID | str, *, due_at: datetime) -> AsyncJob:
    """Enqueue one idempotent schedule scan for a tenant and UTC instant."""

    with tenant_context(tenant_id) as tenant:
        key = f"schedule-scan:{tenant}:{due_at.isoformat()}"
        return enqueue(
            tenant,
            "scheduler",
            "backup_recovery.schedule_due",
            {"tenant_id": str(tenant), "due_at": due_at.isoformat()},
            key,
        )
