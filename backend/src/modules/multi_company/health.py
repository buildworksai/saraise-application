"""Readiness probes for the multi-company financial control plane.

Only stable check codes leave this module. Exceptions, SQL details, tenant data,
provider credentials and row counts are intentionally never returned.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, JobStatus, OutboxEvent
from src.core.async_jobs.services import enqueue, get_handler
from src.core.tenancy import get_current_tenant_id

from .integrations import integrations
from .models import Company, MultiCompanyConfigurationVersion

REQUIRED_COMMANDS = (
    "multi_company.transaction.post",
    "multi_company.transaction.reverse",
    "multi_company.consolidation.execute",
    "multi_company.transaction.expire_drafts",
)


def _dependency_state(adapter: Any | None) -> str:
    if adapter is None:
        return "not_configured"
    callback = getattr(adapter, "health_state", None)
    if not callable(callback):
        return "configured"
    try:
        value = str(callback()).lower()
    except Exception:
        return "unknown"
    return value if value in {"closed", "open", "half_open", "configured"} else "unknown"


def _active_stale_job_seconds(tenant_id: UUID) -> int | None:
    config = MultiCompanyConfigurationVersion.objects.for_tenant(tenant_id).filter(status="active").order_by("-created_at").first()
    if config is None:
        return None
    timeout = config.settings.get("job_timeout_seconds")
    retries = config.settings.get("job_max_retries")
    if not isinstance(timeout, int) or timeout <= 0 or not isinstance(retries, int) or retries < 0:
        return None
    return timeout * (retries + 1)


def get_module_health(tenant_id: UUID) -> dict[str, Any]:
    """Return non-sensitive readiness state for one authenticated tenant."""

    checks: dict[str, str] = {}
    critical_failure = False
    optional_degraded = False

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("database probe failed")
        checks["database"] = "ready"
    except Exception:
        checks["database"] = "unavailable"
        critical_failure = True

    try:
        active_tenant = get_current_tenant_id()
        if active_tenant != tenant_id:
            raise RuntimeError("tenant context mismatch")
        Company.objects.for_tenant(tenant_id).filter(pk=uuid.UUID(int=0)).exists()
        checks["tenant_isolation"] = "ready"
    except Exception:
        checks["tenant_isolation"] = "unavailable"
        critical_failure = True

    if connection.vendor == "postgresql":
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT c.relrowsecurity AND c.relforcerowsecurity "
                    "FROM pg_class c WHERE c.oid = 'multi_company_companies'::regclass"
                )
                row = cursor.fetchone()
            if row != (True,):
                raise RuntimeError("RLS policy inactive")
            checks["rls"] = "ready"
        except Exception:
            checks["rls"] = "unavailable"
            critical_failure = True
    else:
        checks["rls"] = "not_applicable"

    try:
        applied = set(
            MigrationRecorder.Migration.objects.filter(app="multi_company").values_list("name", flat=True)
        )
        if not applied or "0001_initial" not in applied:
            raise RuntimeError("module migrations absent")
        checks["migrations"] = "ready"
    except Exception:
        checks["migrations"] = "unavailable"
        critical_failure = True

    try:
        with transaction.atomic():
            enqueue(
                tenant_id,
                "multi-company-health",
                "multi_company.transaction.expire_drafts",
                {},
                f"health:{uuid.uuid4()}",
            )
            transaction.set_rollback(True)
        checks["job_persistence"] = "ready"
    except Exception:
        checks["job_persistence"] = "unavailable"
        critical_failure = True

    try:
        for command in REQUIRED_COMMANDS:
            get_handler(command)
        checks["job_dispatch"] = "ready"
    except Exception:
        checks["job_dispatch"] = "unavailable"
        critical_failure = True

    stale_seconds = _active_stale_job_seconds(tenant_id)
    if stale_seconds is None:
        checks["stale_jobs"] = "configuration_unavailable"
        critical_failure = True
    else:
        stale_before = timezone.now() - timedelta(seconds=stale_seconds)
        stale = AsyncJob.objects.for_tenant(tenant_id).filter(
            command__startswith="multi_company.",
            status__in=(JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING),
            updated_at__lt=stale_before,
        ).exists()
        checks["stale_jobs"] = "detected" if stale else "ready"
        optional_degraded = optional_degraded or stale

    pending_outbox = OutboxEvent.objects.for_tenant(tenant_id).filter(
        event_type__startswith="multi_company.", available_at__lt=timezone.now()
    ).exists()
    checks["outbox"] = "backlog" if pending_outbox else "ready"
    optional_degraded = optional_degraded or pending_outbox

    ledger_state = _dependency_state(integrations.ledger)
    rate_state = _dependency_state(integrations.exchange_rates)
    checks["ledger"] = ledger_state
    checks["exchange_rates"] = rate_state
    if ledger_state not in {"configured", "closed"} or rate_state not in {"configured", "closed"}:
        critical_failure = True

    for name, adapter in (
        ("workflow", integrations.workflow),
        ("notifications", integrations.notifications),
        ("reports", integrations.reports),
    ):
        state = _dependency_state(adapter)
        checks[name] = state
        optional_degraded = optional_degraded or state not in {"configured", "closed"}

    overall = "unhealthy" if critical_failure else "degraded" if optional_degraded else "healthy"
    return {"status": overall, "checked_at": timezone.now(), "checks": checks}


__all__ = ["get_module_health"]
