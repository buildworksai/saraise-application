"""Transactional service behavior and tenant/concurrency safeguards."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from src.modules.budget_management.integrations import ApprovalRequest, ApprovalStep, configure_integrations
from src.modules.budget_management.models import BudgetApprovalDecision, BudgetCommitment, BudgetLine, VarianceAlert
from src.modules.budget_management.services import (
    BudgetControlService,
    BudgetDomainError,
    BudgetService,
    VarianceAlertService,
    _clean_text,
    _date,
    _datetime,
    _decimal,
    _percent,
)


@pytest.fixture(autouse=True)
def reset_adapters():
    previous = configure_integrations()
    yield
    configure_integrations(
        accounting=previous.accounting, workflow=previous.workflow, notification=previous.notification
    )


@dataclass
class WorkflowAdapter:
    approvers: tuple[uuid.UUID, ...]
    workflow_request_id: uuid.UUID = uuid.uuid4()

    def create_approval_request(self, tenant_id, *, budget, submitter_id, idempotency_key):
        del tenant_id, budget, submitter_id, idempotency_key
        return ApprovalRequest(
            workflow_request_id=self.workflow_request_id,
            steps=tuple(
                ApprovalStep(approver_id=approver, approval_level=index + 1)
                for index, approver in enumerate(self.approvers)
            ),
        )

    def get_approval_status(self, tenant_id, workflow_request_id):
        del tenant_id, workflow_request_id
        return "pending"

    def health_state(self):
        return "closed"


@dataclass
class AccountingAdapter:
    calls: list[tuple[uuid.UUID, tuple[str, ...]]]

    def validate_accounts(self, tenant_id, account_codes):
        self.calls.append((tenant_id, tuple(account_codes)))

    def fetch_actuals(self, tenant_id, budget, periods):
        del tenant_id, budget, periods
        raise AssertionError("fetch_actuals is not used by these service tests")

    def health_state(self):
        return "closed"


@dataclass
class NotificationAdapter:
    evidence: str = "queued-notification"

    def enqueue_budget_notification(
        self, tenant_id, *, notification_type, aggregate_id, recipient_ids, idempotency_key
    ):
        del tenant_id, notification_type, aggregate_id, recipient_ids, idempotency_key
        return self.evidence

    def health_state(self):
        return "closed"


def _budget(tenant, actor, code="FLOW", ceiling="100.00"):
    return BudgetService.create_budget(
        tenant,
        actor,
        budget_code=code,
        budget_name=f"{code} budget",
        fiscal_year=2025,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        budget_type="operating",
        currency="USD",
        budget_ceiling=ceiling,
    )


def _line(tenant, actor, budget, amount="100.00", account="6000"):
    return BudgetService.create_line(
        tenant,
        budget.id,
        actor,
        {"account_code": account, "period_type": "annual", "period_number": 1, "budget_amount": amount},
    )


def _approved_budget(tenant, actor, approver):
    budget = _budget(tenant, actor, "APPROVED")
    _line(tenant, actor, budget)
    configure_integrations(workflow=WorkflowAdapter((approver,)))
    BudgetService.submit_for_approval(tenant, budget.id, actor, idempotency_key="submit-approved")
    return BudgetService.approve_budget(tenant, budget.id, approver, idempotency_key="approve-approved")


@pytest.mark.django_db
def test_create_replace_total_variance_and_availability_are_decimal_and_tenant_scoped() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    budget = BudgetService.create_budget(
        tenant,
        actor,
        budget_code=" ops-25 ",
        budget_name="Operations",
        fiscal_year=2025,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        budget_type="operating",
        currency="usd",
        budget_ceiling="100.00",
    )
    budget = BudgetService.replace_allocations(
        tenant,
        budget.id,
        actor,
        [{"account_code": "6000", "period_type": "annual", "period_number": 1, "budget_amount": "100.00"}],
        expected_updated_at=budget.updated_at,
    )
    assert budget.budget_code == "OPS-25"
    assert budget.total_budget == Decimal("100.00")
    line = BudgetLine.objects.get(tenant_id=tenant, budget=budget)
    assert line.variance == Decimal("100.00")
    report = BudgetControlService.calculate_variance(tenant, budget.id)
    assert report.variance == Decimal("100.00")


@pytest.mark.django_db
def test_optimistic_concurrency_and_cross_tenant_parent_fail_closed() -> None:
    tenant, other, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    budget = BudgetService.create_budget(
        tenant,
        actor,
        budget_code="A",
        budget_name="A",
        fiscal_year=2025,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        budget_type="operating",
        currency="USD",
    )
    with pytest.raises(BudgetDomainError, match="changed"):
        BudgetService.update_budget(
            tenant, budget.id, actor, expected_updated_at="2024-01-01T00:00:00Z", changes={"budget_name": "B"}
        )
    with pytest.raises(BudgetDomainError) as exc:
        BudgetService.create_line(
            other,
            budget.id,
            actor,
            {"account_code": "6000", "period_type": "annual", "period_number": 1, "budget_amount": "1.00"},
        )
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.django_db
def test_commitment_ledger_is_idempotent_and_release_cannot_underflow() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    budget = BudgetService.create_budget(
        tenant,
        actor,
        budget_code="C",
        budget_name="C",
        fiscal_year=2025,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        budget_type="operating",
        currency="USD",
    )
    line = BudgetService.create_line(
        tenant,
        budget.id,
        actor,
        {"account_code": "6100", "period_type": "annual", "period_number": 1, "budget_amount": "50.00"},
    )
    source_id = uuid.uuid4()
    BudgetControlService.record_commitment(tenant, line.id, "10.00", source_id=source_id, idempotency_key="reserve")
    repeated = BudgetControlService.record_commitment(
        tenant, line.id, "10.00", source_id=source_id, idempotency_key="reserve"
    )
    assert repeated.committed_amount == Decimal("10.00")
    assert BudgetCommitment.objects.filter(tenant_id=tenant, budget_line=line).count() == 1
    with pytest.raises(BudgetDomainError) as exc:
        BudgetControlService.release_commitment(
            tenant, line.id, "11.00", source_id=source_id, idempotency_key="release"
        )
    assert exc.value.code == "COMMITMENT_UNDERFLOW"


@pytest.mark.django_db
def test_actual_sync_without_accounting_is_explicitly_unavailable() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    budget = BudgetService.create_budget(
        tenant,
        actor,
        budget_code="S",
        budget_name="Sync",
        fiscal_year=2025,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        budget_type="operating",
        currency="USD",
    )
    with pytest.raises(Exception) as exc:
        BudgetControlService.request_actuals_sync(tenant, budget.id, actor, idempotency_key="sync-1")
    assert getattr(exc.value, "code", None) == "CAPABILITY_UNAVAILABLE"


def test_value_helpers_reject_ambiguous_temporal_and_numeric_inputs() -> None:
    assert _date("2025-02-28", "start_date") == date(2025, 2, 28)
    with pytest.raises(BudgetDomainError) as date_exc:
        _date("2025-02-30", "start_date")
    assert date_exc.value.code == "INVALID_DATE"

    with pytest.raises(BudgetDomainError) as timestamp_exc:
        _datetime("2025-02-28T10:00:00", "expected_updated_at")
    assert timestamp_exc.value.code == "INVALID_TIMESTAMP"

    assert _decimal("10.1", "budget_amount") == Decimal("10.10")
    for value in (True, 1.25, "1.234", "-0.01"):
        with pytest.raises(BudgetDomainError):
            _decimal(value, "budget_amount")
    with pytest.raises(BudgetDomainError) as positive_exc:
        _decimal("0", "budget_amount", positive=True)
    assert positive_exc.value.code == "INVALID_AMOUNT"

    assert _percent("10000.00") == Decimal("10000.00")
    with pytest.raises(BudgetDomainError) as percent_exc:
        _percent("10000.01")
    assert percent_exc.value.code == "INVALID_PERCENTAGE"

    assert _clean_text(" ops ", "budget_code", upper=True, max_length=3) == "OPS"
    with pytest.raises(BudgetDomainError) as text_exc:
        _clean_text("    ", "budget_code")
    assert text_exc.value.code == "REQUIRED"


@pytest.mark.django_db
def test_workflow_approval_requires_independent_ordered_approvers_and_is_idempotent() -> None:
    tenant, submitter = uuid.uuid4(), uuid.uuid4()
    level_one, level_two = uuid.uuid4(), uuid.uuid4()
    budget = _budget(tenant, submitter, "WFLOW")
    _line(tenant, submitter, budget)
    configure_integrations(workflow=WorkflowAdapter((level_one, level_two)))

    submitted = BudgetService.submit_for_approval(tenant, budget.id, submitter, idempotency_key="submit-flow")

    assert submitted.status == "pending_approval"
    assert submitted.submitted_by == submitter
    with pytest.raises(BudgetDomainError) as exc:
        BudgetService.approve_budget(tenant, budget.id, submitter, idempotency_key="self-approval")
    assert exc.value.code == "SELF_APPROVAL_FORBIDDEN"
    with pytest.raises(BudgetDomainError) as exc:
        BudgetService.approve_budget(tenant, budget.id, level_two, idempotency_key="approve-level-two-early")
    assert exc.value.code == "APPROVAL_LEVEL_PENDING"

    still_pending = BudgetService.approve_budget(tenant, budget.id, level_one, idempotency_key="approve-level-one")
    approved = BudgetService.approve_budget(tenant, budget.id, level_two, idempotency_key="approve-level-two")
    replay = BudgetService.approve_budget(tenant, budget.id, level_two, idempotency_key="approve-level-two")

    assert still_pending.status == "pending_approval"
    assert approved.status == "approved"
    assert replay.id == approved.id
    assert BudgetApprovalDecision.objects.filter(tenant_id=tenant, budget=budget, status="approved").count() == 2


@pytest.mark.django_db
def test_rejection_cancels_remaining_approvals_and_revision_clears_rejection_state() -> None:
    tenant, submitter = uuid.uuid4(), uuid.uuid4()
    rejector, pending_approver = uuid.uuid4(), uuid.uuid4()
    budget = _budget(tenant, submitter, "REJECT")
    _line(tenant, submitter, budget)
    configure_integrations(workflow=WorkflowAdapter((rejector, pending_approver)))
    BudgetService.submit_for_approval(tenant, budget.id, submitter, idempotency_key="submit-reject")

    rejected = BudgetService.reject_budget(
        tenant,
        budget.id,
        rejector,
        idempotency_key="reject-once",
        reason="Missing evidence",
    )
    revised = BudgetService.revise_budget(tenant, budget.id, submitter, idempotency_key="revise-rejected")

    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "Missing evidence"
    assert BudgetApprovalDecision.objects.filter(tenant_id=tenant, budget=budget, status="cancelled").count() == 1
    assert revised.status == "revision"
    assert revised.rejected_at is None
    assert revised.rejection_reason == ""


@pytest.mark.django_db
def test_actuals_snapshot_is_evidenced_idempotent_and_rejects_mismatched_lines() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    budget = _budget(tenant, actor, "ACTUAL")
    line = _line(tenant, actor, budget)

    applied = BudgetControlService.apply_actuals_snapshot(
        tenant,
        budget.id,
        [{"account_code": "6000", "period_type": "annual", "period_number": 1, "actual_amount": "125.00"}],
        source_evidence="gl-close-2025",
    )
    replay = BudgetControlService.apply_actuals_snapshot(
        tenant,
        budget.id,
        [{"account_code": "6000", "period_type": "annual", "period_number": 1, "actual_amount": "50.00"}],
        source_evidence="gl-close-2025",
    )
    line.refresh_from_db()

    assert applied.id == replay.id
    assert line.actual_amount == Decimal("125.00")
    assert line.variance == Decimal("-25.00")
    with pytest.raises(BudgetDomainError) as exc:
        BudgetControlService.apply_actuals_snapshot(
            tenant,
            budget.id,
            [{"account_code": "9999", "period_type": "annual", "period_number": 1, "actual_amount": "1.00"}],
            source_evidence="gl-missing-line",
        )
    assert exc.value.code == "ACTUAL_IDENTITY_MISMATCH"


@pytest.mark.django_db
def test_variance_alert_generation_dispatch_and_acknowledgement_paths() -> None:
    tenant, submitter, approver = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    budget = _approved_budget(tenant, submitter, approver)
    line = BudgetLine.objects.get(tenant_id=tenant, budget=budget)
    BudgetControlService.apply_actuals_snapshot(
        tenant,
        budget.id,
        [{"account_code": "6000", "period_type": "annual", "period_number": 1, "actual_amount": "115.00"}],
        source_evidence="alert-evidence",
    )
    BudgetControlService.record_commitment(tenant, line.id, "5.00", source_id=uuid.uuid4(), idempotency_key="alert-cmt")

    generated = VarianceAlertService.generate_alerts(
        tenant,
        threshold_percentage="10.00",
        alert_type="over_budget",
        alert_date=date(2025, 12, 31),
    )
    duplicate = VarianceAlertService.generate_alerts(
        tenant,
        threshold_percentage="10.00",
        alert_type="over_budget",
        alert_date=date(2025, 12, 31),
    )

    assert len(generated) == 1
    assert duplicate == []
    assert VarianceAlert.objects.filter(tenant_id=tenant, budget=budget).count() == 1
    with pytest.raises(BudgetDomainError) as exc:
        VarianceAlertService.dispatch_alert(tenant, generated[0].id, idempotency_key="dispatch-unavailable")
    assert exc.value.code == "CAPABILITY_UNAVAILABLE"
    generated[0].refresh_from_db()
    assert generated[0].notification_status == "unavailable"

    configure_integrations(workflow=WorkflowAdapter((approver,)), notification=NotificationAdapter())
    job = VarianceAlertService.dispatch_alert(tenant, generated[0].id, idempotency_key="dispatch-alert")
    acknowledged = VarianceAlertService.acknowledge_alert(tenant, generated[0].id, submitter)
    replay = VarianceAlertService.acknowledge_alert(tenant, generated[0].id, uuid.uuid4())

    assert job.command == "budget_management.dispatch_variance_alert"
    assert acknowledged.acknowledged_by == submitter
    assert replay.acknowledged_by == submitter
