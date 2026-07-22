"""Structural and financial-integrity tests for multi-company models."""

from datetime import date
from decimal import Decimal
import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.modules.multi_company.models import (
    Company,
    CompanyAccessGrant,
    ConfigurationAuditRecord,
    ConsolidationRun,
    EliminationEntry,
    IntercompanyApproval,
    IntercompanyTransaction,
    MultiCompanyConfigurationVersion,
    TransferPricingRule,
)
from src.modules.multi_company.state_machines import (
    CONSOLIDATION_STATES,
    TRANSACTION_STATES,
    consolidation_state_machine,
    transaction_state_machine,
)


def company(tenant_id: uuid.UUID, code: str, **overrides) -> Company:
    values = {
        "tenant_id": tenant_id,
        "company_code": code,
        "company_name": f"{code} Company",
        "legal_name": f"{code} Legal",
        "currency": "USD",
        "created_by": "tester",
        "updated_by": "tester",
        "correlation_id": uuid.uuid4().hex,
    }
    values.update(overrides)
    return Company.objects.create(**values)


@pytest.mark.django_db
class TestCompanyModel:
    """Test Company model."""

    def test_create_company(self):
        """Test creating a company."""
        tenant_id = uuid.uuid4()
        company = Company.objects.create(
            tenant_id=tenant_id,
            company_code="COMP-001",
            company_name="Test Company",
        )
        assert company.company_code == "COMP-001"
        assert company.company_name == "Test Company"
        assert company.is_active is True

    def test_normalises_code_currency_and_legal_name(self):
        item = Company.objects.create(
            tenant_id=uuid.uuid4(), company_code="  uk-01 ", company_name="UK Trading", currency="gbp"
        )
        assert item.company_code == "UK-01"
        assert item.currency == "GBP"
        assert item.legal_name == "UK Trading"

    def test_explicit_tenant_scope_and_cross_tenant_uniqueness(self):
        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        first = company(tenant_a, "SHARED")
        second = company(tenant_b, "SHARED")
        assert list(Company.objects.for_tenant(tenant_a)) == [first]
        assert list(Company.objects.for_tenant(tenant_b)) == [second]
        with pytest.raises(IntegrityError), transaction.atomic():
            company(tenant_a, "SHARED")

    def test_mutation_increments_optimistic_version(self):
        item = company(uuid.uuid4(), "VERSIONED")
        item.company_name = "Changed"
        item.save()
        item.refresh_from_db()
        assert item.version == 2

    def test_company_check_constraints(self):
        tenant_id = uuid.uuid4()
        parent = company(tenant_id, "PARENT")
        with pytest.raises(IntegrityError), transaction.atomic():
            company(tenant_id, "BAD-MONTH", fiscal_year_start_month=13)
        with pytest.raises(IntegrityError), transaction.atomic():
            company(tenant_id, "BAD-OWNERSHIP", ownership_percentage=Decimal("100.01"))
        parent.parent_company = parent
        with pytest.raises(IntegrityError), transaction.atomic():
            parent.save()


@pytest.mark.django_db
def test_access_grant_window_constraint():
    tenant_id = uuid.uuid4()
    entity = company(tenant_id, "ACCESS")
    now = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        CompanyAccessGrant.objects.create(
            tenant_id=tenant_id,
            company=entity,
            subject_id="subject",
            role="viewer",
            valid_from=now,
            valid_until=now,
            granted_by="grantor",
        )


@pytest.mark.django_db
def test_financial_constraints_and_state_graphs():
    tenant_id = uuid.uuid4()
    source = company(tenant_id, "SOURCE")
    with pytest.raises(IntegrityError), transaction.atomic():
        IntercompanyTransaction.objects.create(
            tenant_id=tenant_id,
            created_by="actor",
            updated_by="actor",
            correlation_id="corr",
            reference="SELF",
            source_company=source,
            target_company=source,
            transaction_type="sale",
            original_amount=Decimal("1"),
            amount=Decimal("1"),
            currency="USD",
            transaction_date=date.today(),
        )
    assert set(IntercompanyTransaction.Status.values) == TRANSACTION_STATES
    assert set(ConsolidationRun.Status.values) == CONSOLIDATION_STATES
    assert transaction_state_machine.terminal_states == frozenset({"eliminated", "cancelled", "expired"})
    assert consolidation_state_machine.terminal_states == frozenset({"published", "cancelled"})


@pytest.mark.django_db
def test_approval_is_append_only_and_rejection_requires_reason():
    tenant_id = uuid.uuid4()
    source, target = company(tenant_id, "AP-S"), company(tenant_id, "AP-T")
    item = IntercompanyTransaction.objects.create(
        tenant_id=tenant_id,
        created_by="creator",
        updated_by="creator",
        correlation_id="corr",
        reference="APPROVAL-1",
        source_company=source,
        target_company=target,
        transaction_type="service",
        original_amount=Decimal("10"),
        amount=Decimal("10"),
        currency="USD",
        transaction_date=date.today(),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        IntercompanyApproval.objects.create(
            tenant_id=tenant_id,
            transaction=item,
            side="source",
            attempt=1,
            approver_id="approver",
            decision="rejected",
            reason="",
            decided_at=timezone.now(),
        )
    approval = IntercompanyApproval.objects.create(
        tenant_id=tenant_id,
        transaction=item,
        side="source",
        attempt=1,
        approver_id="approver",
        decision="approved",
        decided_at=timezone.now(),
    )
    approval.reason = "tamper"
    with pytest.raises(ValidationError):
        approval.save()
    with pytest.raises(ValidationError):
        IntercompanyApproval.objects.filter(pk=approval.pk).update(reason="tamper")
    with pytest.raises(ValidationError):
        approval.delete()


@pytest.mark.django_db
def test_elimination_and_configuration_audit_are_immutable():
    tenant_id = uuid.uuid4()
    source, target = company(tenant_id, "EL-S", consolidation_group="G"), company(
        tenant_id, "EL-T", consolidation_group="G"
    )
    run = ConsolidationRun.objects.create(
        tenant_id=tenant_id,
        created_by="actor",
        updated_by="actor",
        correlation_id="corr",
        name="January",
        consolidation_group="G",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        reporting_currency="USD",
        translation_method="current_rate",
    )
    entry = EliminationEntry.objects.create(
        tenant_id=tenant_id,
        created_by="actor",
        correlation_id="corr",
        consolidation_run=run,
        elimination_type="intercompany_balance",
        source_company=source,
        target_company=target,
        debit_account="1000",
        credit_account="2000",
        amount=Decimal("10"),
        currency="USD",
        sequence=1,
    )
    with pytest.raises(ValidationError):
        entry.delete()
    audit = ConfigurationAuditRecord.objects.create(
        tenant_id=tenant_id,
        correlation_id="corr",
        actor_id="operator",
        environment="development",
        action="activate",
        to_version=1,
        after={"schema_version": "1.0"},
    )
    with pytest.raises(ValidationError):
        ConfigurationAuditRecord.objects.filter(pk=audit.pk).delete()


@pytest.mark.django_db
def test_configuration_has_one_active_version_per_environment():
    tenant_id = uuid.uuid4()
    values = {
        "tenant_id": tenant_id,
        "created_by": "operator",
        "correlation_id": "corr",
        "environment": "development",
        "status": "active",
        "schema_version": "1.0",
        "settings": {"default_currency": "USD"},
        "change_summary": "bootstrap",
    }
    MultiCompanyConfigurationVersion.objects.create(version=1, **values)
    with pytest.raises(IntegrityError), transaction.atomic():
        MultiCompanyConfigurationVersion.objects.create(version=2, **values)
