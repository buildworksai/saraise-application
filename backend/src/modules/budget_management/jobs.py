"""Durable, tenant-bound workers for budget-management commands."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker

from .integrations import ActualsSnapshot, CapabilityUnavailable, InvalidIntegrationResponse, require_accounting, require_notification
from .models import Budget, VarianceAlert
from .services import BudgetControlService, BudgetDomainError, VarianceAlertService


def _uuid(value: Any, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidIntegrationResponse(
            f"Durable job contains an invalid {field_name}", dependency="async_jobs"
        ) from exc


@tenant_context_worker
def sync_actuals_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, Any]:
    """Fetch and apply an evidenced accounting snapshot exactly once."""

    budget_id = _uuid(job.payload.get("budget_id"), "budget_id")
    try:
        budget = Budget.objects.get(tenant_id=tenant_id, id=budget_id, is_deleted=False)
    except Budget.DoesNotExist as exc:
        raise BudgetDomainError("NOT_FOUND", "Budget not found", http_status=404) from exc
    periods = list(
        budget.lines.filter(tenant_id=tenant_id, is_deleted=False)
        .values("account_code", "period_type", "period_number")
        .order_by("account_code", "period_type", "period_number")
    )
    adapter = require_accounting()
    snapshot = adapter.fetch_actuals(tenant_id, budget, periods)
    if not isinstance(snapshot, ActualsSnapshot) or not snapshot.evidence or not isinstance(snapshot.lines, tuple):
        raise InvalidIntegrationResponse("Accounting returned an invalid actuals snapshot", dependency="accounting")
    BudgetControlService.apply_actuals_snapshot(
        tenant_id,
        budget.id,
        snapshot.lines,
        source_evidence=snapshot.evidence,
    )
    return {"budget_id": str(budget.id), "applied_lines": len(snapshot.lines), "evidence": snapshot.evidence}


@tenant_context_worker
def generate_alerts_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, Any]:
    """Generate alerts with database-backed de-duplication."""

    alerts = VarianceAlertService.generate_alerts(
        tenant_id,
        threshold_percentage=str(job.payload.get("threshold_percentage", "")),
        alert_type=str(job.payload.get("alert_type", "")),
        alert_date=str(job.payload.get("alert_date", "")),
    )
    return {"created": len(alerts), "alert_ids": [str(alert.id) for alert in alerts]}


@tenant_context_worker
def dispatch_submission_notification_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, Any]:
    """Dispatch a workflow notification only after provider evidence exists."""

    budget_id = _uuid(job.payload.get("budget_id"), "budget_id")
    raw_recipients = job.payload.get("recipient_ids")
    if not isinstance(raw_recipients, list) or not raw_recipients:
        raise InvalidIntegrationResponse("Notification job has no recipients", dependency="async_jobs")
    recipients = tuple(_uuid(value, "recipient_id") for value in raw_recipients)
    evidence = require_notification().enqueue_budget_notification(
        tenant_id,
        notification_type="budget.submitted",
        aggregate_id=budget_id,
        recipient_ids=recipients,
        idempotency_key=str(job.id),
    )
    if not isinstance(evidence, str) or not evidence.strip():
        raise InvalidIntegrationResponse("Notification provider returned no evidence", dependency="notification")
    return {"budget_id": str(budget_id), "provider_evidence": evidence}


@tenant_context_worker
def dispatch_variance_alert_worker(*, tenant_id: UUID, job: AsyncJob) -> dict[str, Any]:
    """Dispatch one alert and persist its provider-confirmed delivery state."""

    alert_id = _uuid(job.payload.get("alert_id"), "alert_id")
    try:
        alert = VarianceAlert.objects.get(tenant_id=tenant_id, id=alert_id)
    except VarianceAlert.DoesNotExist as exc:
        raise BudgetDomainError("NOT_FOUND", "Variance alert not found", http_status=404) from exc
    try:
        evidence = require_notification().enqueue_budget_notification(
            tenant_id,
            notification_type="budget.variance_alerted",
            aggregate_id=alert.id,
            recipient_ids=(),
            idempotency_key=str(job.id),
        )
        if not isinstance(evidence, str) or not evidence.strip():
            raise InvalidIntegrationResponse("Notification provider returned no evidence", dependency="notification")
    except CapabilityUnavailable:
        VarianceAlert.objects.filter(tenant_id=tenant_id, id=alert.id).update(notification_status="unavailable")
        raise
    except Exception:
        VarianceAlert.objects.filter(tenant_id=tenant_id, id=alert.id).update(notification_status="failed")
        raise
    VarianceAlert.objects.filter(tenant_id=tenant_id, id=alert.id).update(notification_status="sent")
    return {"alert_id": str(alert.id), "provider_evidence": evidence}


def _sync_actuals_handler(job: AsyncJob) -> dict[str, Any]:
    return sync_actuals_worker(tenant_id=job.tenant_id, job=job)


def _generate_alerts_handler(job: AsyncJob) -> dict[str, Any]:
    return generate_alerts_worker(tenant_id=job.tenant_id, job=job)


def _submission_notification_handler(job: AsyncJob) -> dict[str, Any]:
    return dispatch_submission_notification_worker(tenant_id=job.tenant_id, job=job)


def _variance_alert_handler(job: AsyncJob) -> dict[str, Any]:
    return dispatch_variance_alert_worker(tenant_id=job.tenant_id, job=job)


register_handler("budget_management.sync_actuals", _sync_actuals_handler, replace=True)
register_handler("budget_management.generate_variance_alerts", _generate_alerts_handler, replace=True)
register_handler("budget_management.dispatch_submission_notification", _submission_notification_handler, replace=True)
register_handler("budget_management.dispatch_variance_alert", _variance_alert_handler, replace=True)


__all__ = [
    "dispatch_submission_notification_worker",
    "dispatch_variance_alert_worker",
    "generate_alerts_worker",
    "sync_actuals_worker",
]
