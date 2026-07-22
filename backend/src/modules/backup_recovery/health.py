"""Tenant-safe readiness checks without record counts or raw exceptions."""

from __future__ import annotations

import uuid
from typing import Any

from django.db import connection
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.tenancy import tenant_context

from .metrics import ADAPTER_HEALTH
from .models import (
    BackupArchive,
    BackupJob,
    BackupRetentionPolicy,
    BackupSchedule,
    BackupStorageTarget,
    BackupVerification,
)
from .services import _adapter_for


def _dependency(key: str, healthy: bool, *, detail: str = "") -> dict[str, object]:
    result: dict[str, object] = {
        "key": key,
        "status": "healthy" if healthy else "unavailable",
        "critical": True,
    }
    if detail:
        result["detail"] = detail
    return result


def check_module_health(tenant_id: uuid.UUID | str) -> dict[str, Any]:
    checked_at = timezone.now()
    critical_failure = False
    with tenant_context(tenant_id) as tenant:
        catalog_ready = False
        async_ready = False
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            available_tables = set(connection.introspection.table_names())
            catalog_ready = {
                model._meta.db_table
                for model in (
                    BackupStorageTarget,
                    BackupRetentionPolicy,
                    BackupSchedule,
                    BackupJob,
                    BackupArchive,
                    BackupVerification,
                )
            }.issubset(available_tables)
            async_ready = {AsyncJob._meta.db_table, OutboxEvent._meta.db_table}.issubset(available_tables)
            database_component = _dependency("database", catalog_ready)
            async_component = _dependency("async_jobs", async_ready)
            critical_failure = not (catalog_ready and async_ready)
        except Exception:
            database_component = _dependency("database", False, detail="Database schema is unavailable.")
            async_component = _dependency("async_jobs", False, detail="Durable async-job schema is unavailable.")
            critical_failure = True

        if connection.vendor == "postgresql":
            try:
                catalog_tables = [
                    model._meta.db_table
                    for model in (
                        BackupStorageTarget,
                        BackupRetentionPolicy,
                        BackupSchedule,
                        BackupJob,
                        BackupArchive,
                        BackupVerification,
                    )
                ]
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT relname, relrowsecurity, relforcerowsecurity " "FROM pg_class WHERE relname = ANY(%s)",
                        [catalog_tables],
                    )
                    rows = cursor.fetchall()
                rls_ready = len(rows) == len(catalog_tables) and all(row[1] and row[2] for row in rows)
            except Exception:
                rls_ready = False
            if not rls_ready:
                database_component = _dependency(
                    "database", False, detail="Row-level security is not enabled and forced."
                )
                critical_failure = True

        adapter_degraded = False
        adapters: list[dict[str, object]] = []
        try:
            targets = (
                list(BackupStorageTarget.objects.filter(tenant_id=tenant, is_active=True)) if catalog_ready else []
            )
        except Exception:
            targets = []
            critical_failure = True
        for target in targets:
            try:
                result = _adapter_for(target).health()
                adapters.append(
                    {
                        "key": target.adapter_key,
                        "status": "healthy" if result.healthy else "degraded",
                        "critical": target.is_default,
                        "detail": result.message,
                    }
                )
                ADAPTER_HEALTH.labels(adapter_key=target.adapter_key).set(1 if result.healthy else 0)
                adapter_degraded = adapter_degraded or not result.healthy
            except Exception:
                adapters.append(
                    {
                        "key": target.adapter_key,
                        "status": "degraded",
                        "critical": target.is_default,
                        "detail": "Provider capability is unavailable.",
                    }
                )
                ADAPTER_HEALTH.labels(adapter_key=target.adapter_key).set(0)
                adapter_degraded = True

        oldest_age: int | None = None
        try:
            oldest = (
                OutboxEvent.objects.filter(tenant_id=tenant, status="pending")
                .order_by("created_at")
                .values_list("created_at", flat=True)
                .first()
            )
            oldest_age = max(0, int((checked_at - oldest).total_seconds())) if oldest else 0
            outbox_healthy = oldest_age < 300
            outbox_component = _dependency(
                "outbox", outbox_healthy, detail=f"Oldest pending event is {oldest_age} seconds old."
            )
            critical_failure = critical_failure or not outbox_healthy
        except Exception:
            outbox_component = _dependency("outbox", False, detail="Transactional outbox is unavailable.")
            critical_failure = True

        try:
            active_schedules = (
                catalog_ready and BackupSchedule.objects.filter(tenant_id=tenant, is_active=True).exists()
            )
            latest_scan = (
                AsyncJob.objects.filter(tenant_id=tenant, command="backup_recovery.schedule_due")
                .order_by("-created_at")
                .values_list("created_at", flat=True)
                .first()
                if async_ready
                else None
            )
            scheduler_fresh = (
                catalog_ready
                and async_ready
                and (
                    not active_schedules
                    or (latest_scan is not None and (checked_at - latest_scan).total_seconds() < 300)
                )
            )
        except Exception:
            active_schedules = False
            latest_scan = None
            scheduler_fresh = False
        scheduler_detail = (
            f"Last due-schedule scan: {latest_scan.isoformat()}."
            if latest_scan
            else (
                "No scan is required because no schedule is active."
                if not active_schedules
                else "No recent due-schedule scan is recorded."
            )
        )
        scheduler_component = _dependency("scheduler", scheduler_fresh, detail=scheduler_detail)
        critical_failure = critical_failure or not scheduler_fresh

    overall = "unavailable" if critical_failure else "degraded" if adapter_degraded else "healthy"
    return {
        "status": overall,
        "ready": not critical_failure,
        "checked_at": checked_at,
        "database": database_component,
        "async_jobs": async_component,
        "outbox": outbox_component,
        "scheduler": scheduler_component,
        "adapters": adapters,
        "oldest_pending_outbox_seconds": oldest_age,
    }
