from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, JobStatus, OutboxEvent
from src.core.async_jobs.services import JobExecutionError, enqueue, execute, recover_stale_jobs
from src.modules.accounting_finance.jobs import (
    AR_MARK_OVERDUE_COMMAND,
    JOURNAL_IMPORT_COMMAND,
    REPORT_GENERATE_COMMAND,
    AccountingJobCapabilityUnavailable,
    AccountingJobPayloadError,
    ar_mark_overdue_handler,
    handlers_ready,
    journal_import_handler,
    report_generate_handler,
)


def _job(command: str, payload: dict[str, object]) -> AsyncJob:
    return AsyncJob(
        tenant_id=uuid4(),
        actor_id="actor-1",
        command=command,
        idempotency_key=f"test-{uuid4()}",
        payload=payload,
        correlation_id=str(uuid4()),
    )


def test_accounting_handlers_are_registered() -> None:
    assert handlers_ready() is True


@pytest.mark.django_db
def test_enqueue_is_durable_and_tenant_idempotent() -> None:
    tenant = uuid4()
    first = enqueue(
        tenant,
        "actor-1",
        REPORT_GENERATE_COMMAND,
        {"report_type": "trial_balance", "parameters": {"as_of_date": "2026-07-23"}},
        "report-1",
    )
    duplicate = enqueue(
        tenant,
        "actor-1",
        REPORT_GENERATE_COMMAND,
        {"report_type": "trial_balance", "parameters": {"as_of_date": "2026-07-23"}},
        "report-1",
    )
    assert duplicate.id == first.id
    assert OutboxEvent.objects.filter(tenant_id=tenant, aggregate_id=first.id, event_type="async_job.enqueued").count() == 1


@pytest.mark.django_db
def test_report_handler_propagates_correlation_and_duplicate_delivery(monkeypatch) -> None:
    from src.modules.accounting_finance.services import FinancialReportingService

    seen = {}

    def trial_balance(tenant_id, *, as_of_date):
        from src.core.observability import get_task_context
        from src.core.tenancy import get_current_tenant_id

        seen["tenant"] = get_current_tenant_id()
        seen["context"] = get_task_context()
        return {
            "as_of_date": as_of_date,
            "currency": "USD",
            "debit_total": Decimal("10.00"),
            "credit_total": Decimal("10.00"),
        }

    monkeypatch.setattr(FinancialReportingService, "trial_balance", trial_balance)
    tenant = uuid4()
    job = enqueue(
        tenant,
        "actor-1",
        REPORT_GENERATE_COMMAND,
        {"report_type": "trial_balance", "parameters": {"as_of_date": "2026-07-23"}},
        "report-execute-1",
    )
    completed = execute(job.id, tenant)
    redelivered = execute(job.id, tenant)
    assert completed.status == JobStatus.SUCCEEDED
    assert redelivered.id == completed.id
    assert redelivered.attempts == 1
    assert completed.result["report"]["debit_total"] == "10.00"
    assert seen["tenant"] == tenant
    assert str(seen["context"].correlation_id) == job.correlation_id


def test_report_handler_rejects_non_allowlisted_payload() -> None:
    job = _job(
        REPORT_GENERATE_COMMAND,
        {
            "report_type": "trial_balance",
            "parameters": {"as_of_date": "2026-07-23"},
            "access_token": "must-not-persist",
        },
    )
    with pytest.raises(AccountingJobPayloadError):
        report_generate_handler(job)


def test_journal_import_fails_explicitly_without_import_capability(monkeypatch) -> None:
    from src.modules.accounting_finance.services import JournalEntryService

    monkeypatch.delattr(JournalEntryService, "execute_batch_import", raising=False)
    with pytest.raises(AccountingJobCapabilityUnavailable):
        journal_import_handler(_job(JOURNAL_IMPORT_COMMAND, {"file_reference": "managed-file:123"}))
    with pytest.raises(AccountingJobPayloadError):
        journal_import_handler(_job(JOURNAL_IMPORT_COMMAND, {"file_reference": "https://example.test/secret"}))


def test_mark_overdue_handler_delegates_inside_tenant(monkeypatch) -> None:
    from src.modules.accounting_finance.services import ARInvoiceService

    observed = {}

    def mark_overdue(tenant_id, *, as_of_date, actor_id):
        observed.update(tenant_id=tenant_id, as_of_date=as_of_date, actor_id=actor_id)
        return 3

    monkeypatch.setattr(ARInvoiceService, "mark_overdue", mark_overdue)
    job = _job(AR_MARK_OVERDUE_COMMAND, {"as_of_date": "2026-07-23"})
    result = ar_mark_overdue_handler(job)
    assert result == {"schema_version": "1.0", "transitioned": 3, "as_of_date": "2026-07-23"}
    assert observed["tenant_id"] == job.tenant_id


@pytest.mark.django_db
def test_execute_rejects_foreign_tenant_and_records_redacted_failure() -> None:
    tenant = uuid4()
    job = enqueue(
        tenant,
        "actor-1",
        REPORT_GENERATE_COMMAND,
        {"report_type": "unknown", "parameters": {}},
        "invalid-report-1",
    )
    with pytest.raises(ObjectDoesNotExist):
        execute(job.id, uuid4())
    with pytest.raises(JobExecutionError):
        execute(job.id, tenant)
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert "unknown" not in job.error_message
    assert "unsupported" in job.error_message.lower()


@pytest.mark.django_db
def test_stale_job_recovery_is_tenant_scoped() -> None:
    tenant, foreign = uuid4(), uuid4()
    stale = AsyncJob.objects.create(
        tenant_id=tenant,
        actor_id="actor-1",
        command=AR_MARK_OVERDUE_COMMAND,
        idempotency_key="stale-1",
        payload={"as_of_date": "2026-07-23"},
        correlation_id=str(uuid4()),
        status=JobStatus.RUNNING,
    )
    AsyncJob.objects.filter(pk=stale.id).update(updated_at=timezone.now() - timedelta(hours=1))
    other = AsyncJob.objects.create(
        tenant_id=foreign,
        actor_id="actor-2",
        command=AR_MARK_OVERDUE_COMMAND,
        idempotency_key="stale-2",
        payload={"as_of_date": date.today().isoformat()},
        correlation_id=str(uuid4()),
        status=JobStatus.RUNNING,
    )
    AsyncJob.objects.filter(pk=other.id).update(updated_at=timezone.now() - timedelta(hours=1))
    recovered = recover_stale_jobs(tenant, stale_before=timezone.now() - timedelta(minutes=5))
    assert [item.id for item in recovered] == [stale.id]
    other.refresh_from_db()
    assert other.status == JobStatus.RUNNING
