"""Durable worker handlers for multi-company financial commands."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker

from .integrations import (
    DualJournalRequest, IntegrationError, JournalLine, JournalRequest,
    PartialPostingError, integrations,
)
from .models import Company, ConsolidationRun, IntercompanyTransaction
from .services import (
    CompanyRegistryService, ConsolidationService, MultiCompanyConfigurationService,
    _event, _transition, runtime_environment,
)
from .state_machines import consolidation_state_machine, transaction_state_machine

POST_TRANSACTION = "multi_company.transaction.post"
REVERSE_TRANSACTION = "multi_company.transaction.reverse"
EXECUTE_CONSOLIDATION = "multi_company.consolidation.execute"
EXPIRE_DRAFTS = "multi_company.transaction.expire_drafts"


def _payload_id(job: AsyncJob, key: str) -> str:
    value = job.payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Job payload requires {key}")
    return value


@tenant_context_worker
def _post_transaction(job: AsyncJob, *, tenant_id: Any) -> dict[str, Any]:
    transaction_id = _payload_id(job, "transaction_id")
    with transaction.atomic():
        record = IntercompanyTransaction.objects.for_tenant(tenant_id).select_for_update().get(pk=transaction_id)
        if record.status == "posted":
            if not record.source_journal_id or not record.target_journal_id:
                raise RuntimeError("Posted transaction lacks dual journal evidence")
            return {"transaction_id": str(record.id), "source_journal_id": str(record.source_journal_id), "target_journal_id": str(record.target_journal_id)}
        if record.status != "posting":
            raise RuntimeError(f"Transaction is not posting (state={record.status})")

    ledger = integrations.require_ledger()
    correlation_id = str(job.payload.get("correlation_id") or job.correlation_id)
    # Account mappings are operational configuration, not embedded business
    # policy. Absence fails before any external mutation.
    config = MultiCompanyConfigurationService.get_active(tenant_id, runtime_environment()).settings
    accounts = config.get("ledger_accounts")
    if not isinstance(accounts, dict) or set(accounts) < {"intercompany_receivable", "intercompany_payable", "intercompany_revenue", "intercompany_expense"}:
        raise RuntimeError("CAPABILITY_UNAVAILABLE: ledger account mapping is not configured")
    amount = record.amount
    target_amount = record.target_amount if record.target_amount is not None else amount
    request = DualJournalRequest(
        transaction_id=record.id,
        source=JournalRequest(
            company_id=record.source_company_id, external_key=f"{record.id}:source",
            transaction_date=record.transaction_date, currency=record.currency,
            lines=(
                JournalLine(str(accounts["intercompany_receivable"]), debit=amount),
                JournalLine(str(accounts["intercompany_revenue"]), credit=amount),
            ),
        ),
        target=JournalRequest(
            company_id=record.target_company_id, external_key=f"{record.id}:target",
            transaction_date=record.transaction_date, currency=record.currency,
            lines=(
                JournalLine(str(accounts["intercompany_expense"]), debit=target_amount),
                JournalLine(str(accounts["intercompany_payable"]), credit=target_amount),
            ),
        ),
        correlation_id=correlation_id,
    )
    result = ledger.post_dual_journals(tenant_id, request)
    if not (result.source_accepted and result.target_accepted and result.source_journal_id and result.target_journal_id):
        compensations: list[str] = []
        for company_id, journal_id in ((record.source_company_id, result.source_journal_id), (record.target_company_id, result.target_journal_id)):
            if journal_id:
                reversal = ledger.reverse_journal(tenant_id, company_id, journal_id, "Compensate partial intercompany posting", correlation_id)
                if reversal.verified:
                    compensations.append(str(reversal.reversal_journal_id))
        with transaction.atomic():
            locked = IntercompanyTransaction.objects.for_tenant(tenant_id).select_for_update().get(pk=record.pk)
            IntercompanyTransaction.objects.filter(pk=locked.pk).update(
                compensation_journal_ids=compensations, failure_code="PARTIAL_POSTING",
                failure_detail="One ledger rejected the reciprocal journal; accepted journals were compensated.",
            )
            _transition(transaction_state_machine, locked, "posting_failed", tenant_id=tenant_id, actor_id=job.actor_id, correlation_id=correlation_id, transition_key=f"job:{job.id}:failed")
            _event(tenant_id, locked, "multi_company.transaction.failed", job.actor_id, correlation_id, job_id=str(job.id), failure_code="PARTIAL_POSTING")
        raise PartialPostingError("Dual journal posting was partially accepted and compensated", result=result)

    source_check = ledger.verify_journal(tenant_id, record.source_company_id, result.source_journal_id, correlation_id)
    target_check = ledger.verify_journal(tenant_id, record.target_company_id, result.target_journal_id, correlation_id)
    if not all((source_check.exists, source_check.balanced, source_check.posted, target_check.exists, target_check.balanced, target_check.posted)):
        raise IntegrationError("Ledger journal verification failed", dependency="ledger", retryable=False)
    with transaction.atomic():
        locked = IntercompanyTransaction.objects.for_tenant(tenant_id).select_for_update().get(pk=record.pk)
        IntercompanyTransaction.objects.filter(pk=locked.pk).update(
            source_journal_id=result.source_journal_id, target_journal_id=result.target_journal_id,
            posted_date=timezone.localdate(), failure_code="", failure_detail="",
        )
        completed = _transition(transaction_state_machine, locked, "posting_succeeded", tenant_id=tenant_id, actor_id=job.actor_id, correlation_id=correlation_id, transition_key=f"job:{job.id}:succeeded")
        _event(tenant_id, completed, "multi_company.transaction.posted", job.actor_id, correlation_id, job_id=str(job.id), source_journal_id=str(result.source_journal_id), target_journal_id=str(result.target_journal_id))
    return {"transaction_id": str(record.id), "source_journal_id": str(result.source_journal_id), "target_journal_id": str(result.target_journal_id)}


@register_handler(POST_TRANSACTION)  # type: ignore[arg-type]
def post_transaction_handler(job: AsyncJob) -> dict[str, Any]:
    return _post_transaction(job, tenant_id=job.tenant_id)


@tenant_context_worker
def _reverse_transaction(job: AsyncJob, *, tenant_id: Any) -> dict[str, Any]:
    record = IntercompanyTransaction.objects.for_tenant(tenant_id).get(pk=_payload_id(job, "transaction_id"))
    original = record.reversed_transaction
    if original is None or not original.source_journal_id or not original.target_journal_id:
        raise RuntimeError("Original transaction has no reversible dual-journal evidence")
    ledger = integrations.require_ledger()
    correlation_id = str(job.payload.get("correlation_id") or job.correlation_id)
    source = ledger.reverse_journal(tenant_id, original.source_company_id, original.source_journal_id, record.description, correlation_id)
    target = ledger.reverse_journal(tenant_id, original.target_company_id, original.target_journal_id, record.description, correlation_id)
    if not source.verified or not target.verified:
        raise IntegrationError("Reversal journal verification failed", dependency="ledger", retryable=False)
    IntercompanyTransaction.objects.for_tenant(tenant_id).filter(pk=record.pk).update(
        source_journal_id=source.reversal_journal_id, target_journal_id=target.reversal_journal_id,
        posted_date=timezone.localdate(), status="posted",
    )
    return {"transaction_id": str(record.id), "source_journal_id": str(source.reversal_journal_id), "target_journal_id": str(target.reversal_journal_id)}


@register_handler(REVERSE_TRANSACTION)  # type: ignore[arg-type]
def reverse_transaction_handler(job: AsyncJob) -> dict[str, Any]:
    return _reverse_transaction(job, tenant_id=job.tenant_id)


@tenant_context_worker
def _execute_consolidation(job: AsyncJob, *, tenant_id: Any) -> dict[str, Any]:
    run_id = _payload_id(job, "run_id")
    correlation_id = str(job.payload.get("correlation_id") or job.correlation_id)
    run = ConsolidationRun.objects.for_tenant(tenant_id).get(pk=run_id)
    run = _transition(consolidation_state_machine, run, "start", tenant_id=tenant_id, actor_id=job.actor_id, correlation_id=correlation_id, transition_key=f"job:{job.id}:start")
    ConsolidationRun.objects.filter(pk=run.pk).update(started_at=timezone.now(), executed_by=job.actor_id)
    ledger = integrations.require_ledger()
    members = CompanyRegistryService.get_consolidation_group(tenant_id, run.consolidation_group)
    balances: list[dict[str, str]] = []
    try:
        for company in members:
            if not ledger.is_period_closed(tenant_id, company.id, run.period_end):
                raise RuntimeError(f"Accounting period is open for company {company.id}")
            for line in ledger.get_trial_balance(tenant_id, company.id, run.period_start, run.period_end, correlation_id):
                balances.append({"company_id": str(company.id), "account": line.account, "debit": str(line.debit), "credit": str(line.credit)})
        eliminations = ConsolidationService.generate_eliminations(tenant_id, run.id, job.actor_id, correlation_id)
        elimination_total = sum((item.amount for item in eliminations), Decimal("0"))
        minority = sum((item.amount * (Decimal("100") - (item.source_company.ownership_percentage or Decimal("100"))) / Decimal("100") for item in eliminations), Decimal("0"))
        report = {"schema_version": "1.0", "run_id": str(run.id), "period_start": run.period_start.isoformat(), "period_end": run.period_end.isoformat(), "reporting_currency": run.reporting_currency, "companies": [str(item.id) for item in members], "trial_balance": balances, "elimination_total": str(elimination_total), "minority_interest_total": str(minority)}
        with transaction.atomic():
            locked = ConsolidationRun.objects.for_tenant(tenant_id).select_for_update().get(pk=run.pk)
            ConsolidationRun.objects.filter(pk=locked.pk).update(total_eliminations=len(eliminations), elimination_total=elimination_total, minority_interest_total=minority, report_snapshot=report, completed_at=timezone.now())
            completed = _transition(consolidation_state_machine, locked, "complete", tenant_id=tenant_id, actor_id=job.actor_id, correlation_id=correlation_id, transition_key=f"job:{job.id}:complete")
            _event(tenant_id, completed, "multi_company.consolidation.completed", job.actor_id, correlation_id, job_id=str(job.id))
        return report
    except Exception as exc:
        with transaction.atomic():
            locked = ConsolidationRun.objects.for_tenant(tenant_id).select_for_update().get(pk=run.pk)
            ConsolidationRun.objects.filter(pk=locked.pk).update(failure_code=getattr(exc, "code", "CONSOLIDATION_FAILED"), failure_step="execution", failure_detail="Consolidation dependency or reconciliation failed.")
            failed = _transition(consolidation_state_machine, locked, "fail", tenant_id=tenant_id, actor_id=job.actor_id, correlation_id=correlation_id, transition_key=f"job:{job.id}:fail")
            _event(tenant_id, failed, "multi_company.consolidation.failed", job.actor_id, correlation_id, job_id=str(job.id), failure_code=getattr(exc, "code", "CONSOLIDATION_FAILED"))
        raise


@register_handler(EXECUTE_CONSOLIDATION)  # type: ignore[arg-type]
def consolidation_handler(job: AsyncJob) -> dict[str, Any]:
    return _execute_consolidation(job, tenant_id=job.tenant_id)


@tenant_context_worker
def _expire_drafts(job: AsyncJob, *, tenant_id: Any) -> dict[str, int]:
    environment = str(job.payload.get("environment", runtime_environment()))
    hours = int(MultiCompanyConfigurationService.get_active(tenant_id, environment).settings["draft_expiry_hours"])
    cutoff = timezone.now() - timedelta(hours=hours)
    candidates = list(IntercompanyTransaction.objects.for_tenant(tenant_id).filter(status="draft", is_deleted=False, created_at__lt=cutoff).values_list("id", flat=True)[:500])
    expired = 0
    for transaction_id in candidates:
        with transaction.atomic():
            record = IntercompanyTransaction.objects.for_tenant(tenant_id).select_for_update().get(pk=transaction_id)
            if record.status != "draft" or record.created_at >= cutoff:
                continue
            _transition(transaction_state_machine, record, "expire", tenant_id=tenant_id, actor_id=job.actor_id, correlation_id=job.correlation_id, transition_key=f"job:{job.id}:expire:{record.id}")
            expired += 1
    return {"expired": expired}


@register_handler(EXPIRE_DRAFTS)  # type: ignore[arg-type]
def expire_drafts_handler(job: AsyncJob) -> dict[str, int]:
    return _expire_drafts(job, tenant_id=job.tenant_id)


__all__ = ["EXECUTE_CONSOLIDATION", "EXPIRE_DRAFTS", "POST_TRANSACTION", "REVERSE_TRANSACTION"]
