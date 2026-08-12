"""
Service tests for Multi-Company module.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob
from src.core.state_machine import IdempotencyConflictError, IllegalTransitionError, TerminalStateError
from src.modules.multi_company import jobs as multi_company_jobs
from src.modules.multi_company import services as multi_company_services
from src.modules.multi_company.models import (
    Company,
    CompanyAccessGrant,
    ConfigurationAuditRecord,
    ConsolidationRun,
    IntercompanyApproval,
    IntercompanyTransaction,
    TransferPricingRule,
)
from src.modules.multi_company.services import (
    DEFAULT_SETTINGS,
    CompanyAccessService,
    CompanyRegistryService,
    CompanyService,
    ConfigurationUnavailable,
    ConflictError,
    ConsolidationService,
    IntercompanyTransactionService,
    MultiCompanyConfigurationService,
    NotFoundError,
    TransferPricingService,
    runtime_environment,
)


def _activate_configuration(tenant_id, *, settings=None, environment="development"):
    draft = MultiCompanyConfigurationService.create_draft(
        tenant_id,
        "config-author",
        "corr-config",
        environment,
        settings or DEFAULT_SETTINGS,
        "Enable governed multi-company defaults",
    )
    return MultiCompanyConfigurationService.activate(tenant_id, draft.id, "config-approver", "corr-activate")


def _company(tenant_id, code, **overrides):
    data = {
        "tenant_id": tenant_id,
        "company_code": code,
        "company_name": f"{code} Company",
        "legal_name": f"{code} Legal",
        "currency": "USD",
        "consolidation_group": "GROUP",
        "is_active": True,
    }
    data.update(overrides)
    return Company.objects.create(**data)


def _grant(tenant_id, company, subject, role="controller"):
    return CompanyAccessService.grant_access(
        tenant_id,
        "grantor",
        f"corr-grant-{company.company_code}-{subject}",
        {"company_id": company.id, "subject_id": subject, "role": role},
    )


def _company_pair_with_access(tenant_id, actor="controller"):
    source = _company(tenant_id, "SRC")
    target = _company(tenant_id, "TGT")
    _grant(tenant_id, source, actor, "controller")
    _grant(tenant_id, target, actor, "controller")
    return source, target


def _transaction(tenant_id, source, target, **overrides):
    data = {
        "tenant_id": tenant_id,
        "source_company": source,
        "target_company": target,
        "reference": overrides.pop("reference", "IC-001"),
        "transaction_type": "sale",
        "product_category": "standard",
        "original_amount": Decimal("100.0000"),
        "amount": Decimal("100.0000"),
        "currency": "USD",
        "transaction_date": date(2024, 1, 15),
        "created_by": "originator",
        "updated_by": "originator",
        "correlation_id": "corr-tx",
    }
    data.update(overrides)
    return IntercompanyTransaction.objects.create(**data)


def _run(tenant_id, **overrides):
    data = {
        "tenant_id": tenant_id,
        "name": overrides.pop("name", "January close"),
        "consolidation_group": "GROUP",
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 1, 31),
        "reporting_currency": "USD",
        "translation_method": "current_rate",
        "total_companies": 2,
        "created_by": "controller",
        "updated_by": "controller",
        "correlation_id": "corr-run",
    }
    data.update(overrides)
    return ConsolidationRun.objects.create(**data)


def _rule(tenant_id, source, target, **overrides):
    data = {
        "tenant_id": tenant_id,
        "name": "Cost plus services",
        "source_company": source,
        "target_company": target,
        "product_category": "standard",
        "transaction_type": "sale",
        "pricing_method": "cost_plus",
        "markup_percentage": Decimal("10.0000"),
        "effective_from": date(2024, 1, 1),
        "created_by": "tax",
        "updated_by": "tax",
        "correlation_id": "corr-rule",
    }
    data.update(overrides)
    return TransferPricingRule.objects.create(**data)


@pytest.mark.django_db
class TestCompanyService:
    """Test CompanyService."""

    def test_create_company(self):
        """Test creating a company via service."""
        tenant_id = uuid.uuid4()
        company = CompanyService.create_company(
            tenant_id=str(tenant_id),
            company_code="COMP-001",
            company_name="Test Company",
        )

        assert company.company_code == "COMP-001"
        assert company.company_name == "Test Company"
        assert str(company.tenant_id) == str(tenant_id)


@pytest.mark.django_db
def test_runtime_environment_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("SARAISE_ENVIRONMENT", "qa")

    with pytest.raises(ConfigurationUnavailable):
        runtime_environment()


@pytest.mark.django_db
def test_low_level_multi_company_helpers_fail_closed_for_invalid_input():
    tenant_id = uuid.uuid4()
    company = _company(tenant_id, "VAL")

    with pytest.raises(NotFoundError):
        multi_company_services._get(Company, tenant_id, uuid.uuid4())
    with pytest.raises(NotFoundError):
        multi_company_services._locked_get(Company, tenant_id, "not-a-uuid")
    with pytest.raises(ValidationError):
        multi_company_services._required_text(None, "name")
    with pytest.raises(ValidationError):
        multi_company_services._required_text("abcd", "name", maximum=3)
    with pytest.raises(ValidationError):
        multi_company_services._decimal("not-decimal", "amount")
    with pytest.raises(ValidationError):
        multi_company_services._decimal("0", "amount", positive=True)
    with pytest.raises(ValidationError):
        multi_company_services._currency("btc")
    with pytest.raises(ValidationError):
        multi_company_services._check_version(company, 0)
    with pytest.raises(multi_company_services.StaleVersionError):
        multi_company_services._check_version(company, company.version + 1)


@pytest.mark.django_db
def test_configuration_activation_supersedes_previous_active_and_audits():
    tenant_id = uuid.uuid4()
    first = MultiCompanyConfigurationService.create_draft(
        tenant_id,
        "controller",
        "corr-1",
        "development",
        DEFAULT_SETTINGS,
        "Initial governed defaults",
    )
    active = MultiCompanyConfigurationService.activate(tenant_id, first.id, "approver", "corr-2")

    updated_settings = {**DEFAULT_SETTINGS, "job_timeout_seconds": 600}
    second = MultiCompanyConfigurationService.create_draft(
        tenant_id,
        "controller",
        "corr-3",
        "development",
        updated_settings,
        "Increase job timeout",
    )
    replacement = MultiCompanyConfigurationService.activate(tenant_id, second.id, "approver", "corr-4")

    active.refresh_from_db()
    assert active.status == "superseded"
    assert replacement.status == "active"
    assert replacement.version == 2
    assert ConfigurationAuditRecord.objects.for_tenant(tenant_id).filter(action="activate").count() == 2


@pytest.mark.django_db
def test_configuration_validation_reports_missing_and_unsafe_values():
    invalid_settings = {**DEFAULT_SETTINGS, "rounding_mode": "ROUND_DOWN"}
    invalid_settings.pop("ledger_accounts")

    result = MultiCompanyConfigurationService.validate_settings(invalid_settings)

    assert not result.valid
    assert "ledger_accounts" in result.errors
    assert "rounding_mode" in result.errors


@pytest.mark.parametrize(
    ("patch", "expected_fields"),
    [
        ("not-object", {"settings"}),
        (
            {
                "draft_expiry_hours": 0,
                "minimum_consolidation_company_count": 1,
                "job_max_retries": 11,
                "job_timeout_seconds": 9,
                "money_precision": 5,
            },
            {
                "draft_expiry_hours",
                "minimum_consolidation_company_count",
                "job_max_retries",
                "job_timeout_seconds",
                "money_precision",
            },
        ),
        (
            {
                "permitted_translation_methods": [],
                "permitted_transaction_types": ["unsupported"],
                "permitted_pricing_methods": ["unsupported"],
                "approval_sides": ["owner"],
            },
            {
                "permitted_translation_methods",
                "permitted_transaction_types",
                "permitted_pricing_methods",
                "approval_sides",
            },
        ),
        (
            {
                "maximum_transaction_amount_by_currency": {
                    "USD": "1000000000000000.0000",
                    "XXX": "1.0000",
                    "EUR": "-1.0000",
                },
                "default_currency": "XXX",
            },
            {"maximum_transaction_amount_by_currency", "default_currency"},
        ),
        (
            {
                "ledger_accounts": {
                    "intercompany_receivable": "",
                    "intercompany_payable": "2200",
                    "intercompany_revenue": "4100",
                    "intercompany_expense": "5100",
                },
                "elimination_accounts": {"debit": "SAME", "credit": "SAME"},
            },
            {"ledger_accounts", "elimination_accounts"},
        ),
    ],
)
def test_configuration_validation_reports_all_governed_setting_boundaries(patch, expected_fields):
    settings = patch if isinstance(patch, str) else {**DEFAULT_SETTINGS, **patch}

    result = MultiCompanyConfigurationService.validate_settings(settings)

    assert not result.valid
    assert set(expected_fields).issubset(result.errors)


@pytest.mark.django_db
def test_company_registry_requires_configuration_for_governed_create():
    with pytest.raises(ConfigurationUnavailable):
        CompanyRegistryService.create_company(
            uuid.uuid4(),
            "controller",
            "corr",
            {"company_code": "COMP-001", "company_name": "No Config"},
            "create-company",
        )


@pytest.mark.django_db
def test_company_access_requires_sufficient_active_role():
    tenant_id = uuid.uuid4()
    company = Company.objects.create(
        tenant_id=tenant_id,
        company_code="HQ",
        company_name="Holding",
        legal_name="Holding",
        currency="USD",
    )
    CompanyAccessService.grant_access(
        tenant_id,
        "controller",
        "corr",
        {"company_id": company.id, "subject_id": "operator", "role": "viewer"},
    )

    with pytest.raises(PermissionDenied):
        CompanyAccessService.require_company_access(tenant_id, "operator", [company.id], "operator")

    grant = CompanyAccessGrant.objects.for_tenant(tenant_id).get(company=company, subject_id="operator")
    CompanyAccessService.revoke_access(tenant_id, grant.id, "controller", "corr", "Policy rollback")

    with pytest.raises(PermissionDenied):
        CompanyAccessService.require_company_access(tenant_id, "operator", [company.id], "viewer")


@pytest.mark.django_db
def test_company_access_rejects_unsupported_role_before_grant_creation():
    tenant_id = uuid.uuid4()
    company = Company.objects.create(
        tenant_id=tenant_id,
        company_code="HQ",
        company_name="Holding",
        legal_name="Holding",
        currency="USD",
    )

    with pytest.raises(ValidationError) as exc:
        CompanyAccessService.grant_access(
            tenant_id,
            "controller",
            "corr",
            {"company_id": company.id, "subject_id": "operator", "role": "superuser"},
        )

    assert exc.value.message_dict == {"role": ["Unsupported company role."]}
    assert not CompanyAccessGrant.objects.for_tenant(tenant_id).filter(subject_id="operator").exists()


@pytest.mark.django_db
def test_company_registry_lifecycle_filters_and_hierarchy_guardrails():
    tenant_id = uuid.uuid4()
    _activate_configuration(tenant_id)
    parent = CompanyRegistryService.create_company(
        tenant_id,
        "controller",
        "corr-parent",
        {
            "company_code": "hq",
            "company_name": "Holding",
            "legal_name": "Holding LLC",
            "currency": "usd",
            "consolidation_group": "GROUP",
        },
        "create-hq",
    )
    child = CompanyRegistryService.create_company(
        tenant_id,
        "controller",
        "corr-child",
        {
            "company_code": "sub",
            "company_name": "Subsidiary",
            "parent_company_id": parent.id,
            "currency": "usd",
            "consolidation_group": "GROUP",
        },
        "create-sub",
    )

    assert parent.company_code == "HQ"
    assert child.parent_company_id == parent.id
    assert CompanyRegistryService.list_companies(tenant_id, {"search": "hold"}).get() == parent
    assert CompanyRegistryService.get_hierarchy(tenant_id)[0]["children"][0]["company_code"] == "SUB"
    assert CompanyRegistryService.get_subsidiaries(tenant_id, parent.id, recursive=True) == [child]
    assert CompanyRegistryService.get_consolidation_group(tenant_id, "GROUP") == [parent, child]

    with pytest.raises(ValidationError) as exc:
        CompanyRegistryService.update_company(
            tenant_id,
            parent.id,
            "controller",
            "corr-cycle",
            parent.version,
            {"parent_company_id": child.id},
        )
    assert exc.value.message_dict == {"parent_company_id": ["Company hierarchy cycle detected."]}


@pytest.mark.django_db
def test_company_lifecycle_blocks_financial_history_and_enforces_versions():
    tenant_id = uuid.uuid4()
    source, target = _company_pair_with_access(tenant_id)
    tx = _transaction(tenant_id, source, target, status="pending_approval")

    with pytest.raises(ConflictError):
        CompanyRegistryService.deactivate_company(tenant_id, source.id, "controller", "corr-deactivate", source.version)

    tx.status = "draft"
    tx.save()
    deactivated = CompanyRegistryService.deactivate_company(
        tenant_id, source.id, "controller", "corr-deactivate", source.version
    )
    assert not deactivated.is_active
    reactivated = CompanyRegistryService.reactivate_company(
        tenant_id, source.id, "controller", "corr-reactivate", deactivated.version
    )
    assert reactivated.is_active

    with pytest.raises(ValidationError):
        CompanyRegistryService.delete_company(tenant_id, target.id, "controller", "corr-delete", 0)
    with pytest.raises(ConflictError):
        CompanyRegistryService.delete_company(tenant_id, target.id, "controller", "corr-delete", target.version)


@pytest.mark.django_db
def test_company_registry_validates_create_update_and_allows_delete_without_dependents():
    tenant_id = uuid.uuid4()
    _activate_configuration(tenant_id)

    with pytest.raises(ValidationError) as invalid_currency:
        CompanyRegistryService.create_company(
            tenant_id,
            "controller",
            "corr-bad-currency",
            {"company_code": "BAD", "company_name": "Bad Currency", "currency": "XYZ"},
            "create-bad-currency",
        )
    assert invalid_currency.value.message_dict == {"currency": ["Unsupported ISO 4217 currency."]}

    with pytest.raises(ValidationError) as invalid_fiscal_year:
        CompanyRegistryService.create_company(
            tenant_id,
            "controller",
            "corr-bad-fiscal",
            {"company_code": "FY", "company_name": "Bad Fiscal", "fiscal_year_start_month": 13},
            "create-bad-fiscal",
        )
    assert invalid_fiscal_year.value.message_dict == {"fiscal_year_start_month": ["Must be between 1 and 12."]}

    company = CompanyRegistryService.create_company(
        tenant_id,
        "controller",
        "corr-delete-candidate",
        {"company_code": "DEL", "company_name": "Delete Candidate"},
        "create-delete-candidate",
    )

    with pytest.raises(ValidationError) as bad_update:
        CompanyRegistryService.update_company(
            tenant_id,
            company.id,
            "controller",
            "corr-bad-update",
            company.version,
            {"unsupported": "value"},
        )
    assert bad_update.value.message_dict == {"unsupported": ["Field cannot be updated."]}

    with pytest.raises(ValidationError):
        CompanyRegistryService.update_company(
            tenant_id,
            company.id,
            "controller",
            "corr-stale-bool",
            True,
            {"company_name": "Rejected"},
        )

    CompanyRegistryService.delete_company(tenant_id, company.id, "controller", "corr-delete", company.version)
    company.refresh_from_db()
    assert company.is_deleted is True
    assert company.is_active is False
    assert company.deleted_at is not None


@pytest.mark.django_db
def test_transaction_workflow_validates_access_limits_and_replay_keys():
    tenant_id = uuid.uuid4()
    settings = {
        **DEFAULT_SETTINGS,
        "maximum_transaction_amount_by_currency": {"USD": "150.0000"},
        "approval_sides": ["source", "target"],
    }
    _activate_configuration(tenant_id, settings=settings)
    source, target = _company_pair_with_access(tenant_id, actor="operator")
    _grant(tenant_id, source, "source-approver", "approver")
    _grant(tenant_id, target, "target-approver", "approver")

    with pytest.raises(ValidationError) as exc:
        IntercompanyTransactionService.create_transaction(
            tenant_id,
            "operator",
            "corr-too-large",
            {
                "reference": "IC-LIMIT",
                "source_company_id": source.id,
                "target_company_id": target.id,
                "transaction_type": "sale",
                "amount": "151.0000",
                "currency": "USD",
                "transaction_date": date(2024, 1, 1),
            },
        )
    assert exc.value.message_dict == {"amount": ["Exceeds configured USD limit."]}

    record = IntercompanyTransactionService.create_transaction(
        tenant_id,
        "operator",
        "corr-create",
        {
            "reference": "IC-APPROVE",
            "source_company_id": source.id,
            "target_company_id": target.id,
            "transaction_type": "sale",
            "product_category": "standard",
            "amount": "100.0000",
            "currency": "USD",
            "exchange_rate": "1.25000000",
            "transaction_date": date(2024, 1, 1),
        },
    )
    assert record.target_amount == Decimal("125.0000")

    submitted = IntercompanyTransactionService.submit(tenant_id, record.id, "operator", "corr-submit", "submit-1")
    assert submitted.status == "pending_approval"
    repeated = IntercompanyTransactionService.submit(tenant_id, record.id, "operator", "corr-submit", "submit-1")
    assert repeated.status == "pending_approval"
    with pytest.raises(IdempotencyConflictError):
        IntercompanyTransactionService.cancel(
            tenant_id, record.id, "operator", "corr-cancel", "duplicate key", "submit-1"
        )

    IntercompanyTransactionService.record_approval(
        tenant_id, record.id, "source-approver", "corr-approve-1", "source", "approved", transition_key="approve-src"
    )
    assert IntercompanyApproval.objects.for_tenant(tenant_id).filter(transaction=record).count() == 1
    approved = IntercompanyTransactionService.record_approval(
        tenant_id, record.id, "target-approver", "corr-approve-2", "target", "approved", transition_key="approve-tgt"
    )
    assert approved.status == "approved"

    job = IntercompanyTransactionService.post(tenant_id, record.id, "operator", "corr-post", "post-job", "post-1")
    assert job.command == "multi_company.transaction.post"
    record.refresh_from_db()
    assert record.status == "posting"
    assert record.job_id == job.id

    with pytest.raises(IllegalTransitionError):
        IntercompanyTransactionService.post(tenant_id, record.id, "operator", "corr-post", "post-job", "post-2")


@pytest.mark.django_db
def test_transaction_dispute_reverse_pricing_and_reconciliation_paths():
    tenant_id = uuid.uuid4()
    _activate_configuration(tenant_id)
    source, target = _company_pair_with_access(tenant_id, actor="controller")
    _grant(tenant_id, source, "source-approver", "approver")
    rule = _rule(tenant_id, source, target)
    draft = _transaction(tenant_id, source, target, transfer_pricing_rule=rule, amount=Decimal("100.0000"))

    priced = IntercompanyTransactionService.apply_transfer_pricing(
        tenant_id, draft.id, "controller", "corr-price", rule.id
    )
    assert priced.amount == Decimal("110.0000")
    assert priced.transfer_pricing_snapshot["pricing_method"] == "cost_plus"

    submitted = IntercompanyTransactionService.submit(tenant_id, draft.id, "controller", "corr-submit", "submit-price")
    disputed = IntercompanyTransactionService.record_approval(
        tenant_id,
        submitted.id,
        "source-approver",
        "corr-reject",
        "source",
        "rejected",
        reason="Mismatch",
        transition_key="reject-source",
    )
    assert disputed.status == "disputed"
    assert disputed.dispute_reason == "Mismatch"
    resolved = IntercompanyTransactionService.resolve_dispute(
        tenant_id, disputed.id, "controller", "corr-resolve", "Corrected", "resolve-1"
    )
    assert resolved.status == "pending_approval"

    posted = _transaction(tenant_id, source, target, reference="IC-POSTED", status="posted")
    reversal = IntercompanyTransactionService.reverse(
        tenant_id, posted.id, "controller", "corr-reverse", "Close correction", "reverse-key"
    )
    same_reversal = IntercompanyTransactionService.reverse(
        tenant_id, posted.id, "controller", "corr-reverse", "Close correction", "reverse-key"
    )
    assert same_reversal.id == reversal.id
    assert reversal.source_company_id == target.id
    assert reversal.reversed_transaction_id == posted.id

    rows = IntercompanyTransactionService.get_reconciliation(tenant_id, {"search": "POSTED"})
    assert rows[0]["variance"] == Decimal("0.0000")


@pytest.mark.django_db
def test_transfer_pricing_versions_methods_and_fail_closed_extension_validation():
    tenant_id = uuid.uuid4()
    _activate_configuration(tenant_id)
    source, target = _company_pair_with_access(tenant_id)

    with pytest.raises(ValidationError) as exc:
        TransferPricingService.create_rule(
            tenant_id,
            "tax",
            "corr-rule",
            {
                "name": "Bad extension",
                "source_company_id": source.id,
                "target_company_id": target.id,
                "product_category": "standard",
                "transaction_type": "sale",
                "pricing_method": "extension",
                "effective_from": date(2024, 1, 1),
            },
        )
    assert exc.value.message_dict == {"extension_key": ["Required for extension method."]}

    base = TransferPricingService.create_rule(
        tenant_id,
        "tax",
        "corr-rule",
        {
            "name": "Cost plus",
            "source_company_id": source.id,
            "target_company_id": target.id,
            "product_category": "standard",
            "transaction_type": "sale",
            "pricing_method": "cost_plus",
            "markup_percentage": "15.0000",
            "effective_from": date(2024, 1, 1),
        },
    )
    result = TransferPricingService.calculate_price(tenant_id, {"rule_id": base.id, "amount": "200.0000"})
    assert result.amount == Decimal("230.0000")
    replacement = TransferPricingService.create_rule_version(
        tenant_id, base.id, "tax", "corr-version", base.version, {"markup_percentage": Decimal("20.0000")}
    )
    base.refresh_from_db()
    assert not base.is_active
    assert replacement.rule_key == base.rule_key
    assert replacement.rule_version == 2

    scenarios = TransferPricingService.preview_rule(
        tenant_id, {"rule_id": replacement.id}, [{"amount": "10.0000"}, {"amount": "20.0000"}]
    )
    assert [item.amount for item in scenarios] == [Decimal("12.0000"), Decimal("24.0000")]
    TransferPricingService.deactivate_rule(tenant_id, replacement.id, "tax", "corr-deactivate", replacement.version)
    replacement.refresh_from_db()
    assert not replacement.is_active
    TransferPricingService.delete_unused_draft_rule(tenant_id, replacement.id, "tax", "corr-delete")
    replacement.refresh_from_db()
    assert replacement.is_deleted


@pytest.mark.django_db
def test_consolidation_create_execute_eliminate_report_and_idempotency(monkeypatch):
    tenant_id = uuid.uuid4()
    _activate_configuration(tenant_id)
    source, target = _company_pair_with_access(tenant_id, actor="controller")

    with pytest.raises(ValidationError):
        ConsolidationService.create_run(
            tenant_id,
            "controller",
            "corr-small-group",
            {
                "name": "Small group",
                "consolidation_group": "MISSING",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 1, 31),
                "reporting_currency": "USD",
                "translation_method": "current_rate",
            },
        )

    run = ConsolidationService.create_run(
        tenant_id,
        "controller",
        "corr-run",
        {
            "name": "January close",
            "consolidation_group": "GROUP",
            "period_start": date(2024, 1, 1),
            "period_end": date(2024, 1, 31),
            "reporting_currency": "usd",
            "translation_method": "current_rate",
        },
    )
    assert run.total_companies == 2
    with pytest.raises(ConflictError):
        ConsolidationService.create_run(
            tenant_id,
            "controller",
            "corr-overlap",
            {
                "name": "Overlap",
                "consolidation_group": "GROUP",
                "period_start": date(2024, 1, 15),
                "period_end": date(2024, 2, 15),
                "reporting_currency": "USD",
                "translation_method": "current_rate",
            },
        )

    job = ConsolidationService.execute(tenant_id, run.id, "controller", "corr-exec", "exec-job", "queue-1")
    assert job.command == "multi_company.consolidation.execute"
    run.refresh_from_db()
    assert run.status == "queued"
    with pytest.raises(IllegalTransitionError):
        ConsolidationService.execute(tenant_id, run.id, "controller", "corr-exec", "exec-job", "queue-2")

    failed = _run(
        tenant_id,
        name="Failed close",
        period_start=date(2024, 2, 1),
        period_end=date(2024, 2, 29),
        status="failed",
    )
    retry = ConsolidationService.retry(tenant_id, failed.id, "controller", "corr-retry", "retry-job", "retry-1")
    assert retry.command == "multi_company.consolidation.execute"

    posted = _transaction(tenant_id, source, target, reference="IC-ELIM", status="posted")
    completed = _run(
        tenant_id,
        name="Completed close",
        period_start=date(2024, 3, 1),
        period_end=date(2024, 3, 31),
        status="completed",
        report_snapshot={"total": "100.0000"},
    )
    elimination = ConsolidationService.create_manual_elimination(
        tenant_id,
        completed.id,
        "controller",
        "corr-elim",
        {
            "elimination_type": "intercompany_balance",
            "source_company_id": source.id,
            "target_company_id": target.id,
            "source_transaction_id": posted.id,
            "debit_account": "4000",
            "credit_account": "2000",
            "amount": "100.0000",
            "currency": "usd",
            "description": "Manual elimination",
        },
    )
    assert elimination.sequence == 1
    assert not elimination.is_auto_generated

    generated = ConsolidationService.generate_eliminations(tenant_id, completed.id, "controller", "corr-auto")
    assert generated == []
    assert ConsolidationService.get_report(tenant_id, completed.id) == {"total": "100.0000"}
    with pytest.raises(PermissionDenied):
        ConsolidationService.approve(tenant_id, completed.id, completed.executed_by, "corr-approve", "approve-1")


@pytest.mark.django_db
def test_configuration_update_preview_export_import_and_rollback(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setenv("MULTI_COMPANY_EXPORT_SIGNING_KEY", "local-test-signing-key")
    active = _activate_configuration(tenant_id)
    _company(tenant_id, "CFG")
    draft = MultiCompanyConfigurationService.create_draft(
        tenant_id,
        "config-author",
        "corr-draft",
        {
            "environment": "development",
            "settings": {**DEFAULT_SETTINGS, "job_timeout_seconds": 900},
            "change_summary": "Increase timeout",
        },
    )
    updated = MultiCompanyConfigurationService.update_draft(
        tenant_id,
        draft.id,
        "config-author",
        "corr-update",
        draft.version,
        {
            "settings": {**DEFAULT_SETTINGS, "job_timeout_seconds": 1200},
            "change_summary": "Increase timeout again",
        },
    )
    assert updated.settings["job_timeout_seconds"] == 1200
    preview = MultiCompanyConfigurationService.preview_impact(tenant_id, updated.id)
    assert preview.valid
    assert "job_timeout_seconds" in preview.changed_keys
    MultiCompanyConfigurationService.activate(tenant_id, updated.id, "config-approver", "corr-activate")
    rolled_back = MultiCompanyConfigurationService.rollback(
        tenant_id,
        active.id,
        "config-approver",
        "corr-rollback",
        {"environment": "development", "change_summary": "Rollback to original defaults"},
    )
    assert rolled_back.status == "active"
    assert rolled_back.settings == active.settings
    assert ConfigurationAuditRecord.objects.for_tenant(tenant_id).filter(action="rollback").exists()

    document = MultiCompanyConfigurationService.export_document(
        tenant_id, "development", actor_id="config-exporter", correlation_id="corr-export"
    )
    imported = MultiCompanyConfigurationService.import_document(
        tenant_id,
        "config-importer",
        "corr-import",
        {"environment": "development", "document": document},
    )
    assert imported.status == "draft"
    tampered = {**document, "settings": {**document["settings"], "job_timeout_seconds": 30}}
    with pytest.raises(ValidationError):
        MultiCompanyConfigurationService.import_document(tenant_id, "config-importer", "corr-import", tampered)
    with pytest.raises(ConfigurationUnavailable):
        monkeypatch.delenv("MULTI_COMPANY_EXPORT_SIGNING_KEY")
        MultiCompanyConfigurationService.export_document(tenant_id, "development")


@pytest.mark.django_db
def test_tenant_isolation_for_service_reads_and_async_jobs():
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    company_a = _company(tenant_a, "A")
    company_b = _company(tenant_b, "B")
    assert list(CompanyRegistryService.list_companies(tenant_a)) == [company_a]

    assert CompanyRegistryService.get_company(tenant_a, company_a.id) == company_a
    with pytest.raises(NotFoundError):
        CompanyRegistryService.get_company(tenant_a, company_b.id)

    job_a = AsyncJob.objects.create(
        tenant_id=tenant_a,
        actor_id="controller",
        command="multi_company.transaction.post",
        idempotency_key="job-a",
        payload={},
        correlation_id="corr-job-a",
    )
    AsyncJob.objects.create(
        tenant_id=tenant_b,
        actor_id="controller",
        command="multi_company.transaction.post",
        idempotency_key="job-b",
        payload={},
        correlation_id="corr-job-b",
    )

    assert AsyncJob.objects.for_tenant(tenant_a).filter(command__startswith="multi_company.").get() == job_a


def test_multi_company_job_payload_validation_is_explicit() -> None:
    job = AsyncJob(payload={})

    with pytest.raises(ValueError, match="transaction_id"):
        multi_company_jobs._payload_id(job, "transaction_id")

    job.payload = {"transaction_id": ""}
    with pytest.raises(ValueError, match="transaction_id"):
        multi_company_jobs._payload_id(job, "transaction_id")

    job.payload = {"transaction_id": "abc"}
    assert multi_company_jobs._payload_id(job, "transaction_id") == "abc"


@pytest.mark.django_db
def test_post_transaction_worker_replays_posted_evidence_and_rejects_invalid_states():
    tenant_id = uuid.uuid4()
    source, target = _company_pair_with_access(tenant_id)
    source_journal_id = uuid.uuid4()
    target_journal_id = uuid.uuid4()
    posted = _transaction(
        tenant_id,
        source,
        target,
        reference="IC-POSTED",
        status="posted",
        source_journal_id=source_journal_id,
        target_journal_id=target_journal_id,
    )
    job = AsyncJob.objects.create(
        tenant_id=tenant_id,
        actor_id="controller",
        command=multi_company_jobs.POST_TRANSACTION,
        idempotency_key="posted-replay",
        payload={"transaction_id": str(posted.id), "correlation_id": "corr-posted"},
        correlation_id="corr-job",
    )

    result = multi_company_jobs._post_transaction(job, tenant_id=tenant_id)

    assert result == {
        "transaction_id": str(posted.id),
        "source_journal_id": str(source_journal_id),
        "target_journal_id": str(target_journal_id),
    }

    bad_posted = _transaction(
        tenant_id,
        source,
        target,
        reference="IC-BAD-POSTED",
        status="posted",
        source_journal_id=None,
        target_journal_id=uuid.uuid4(),
    )
    job.payload = {"transaction_id": str(bad_posted.id)}
    with pytest.raises(RuntimeError, match="lacks dual journal evidence"):
        multi_company_jobs._post_transaction(job, tenant_id=tenant_id)

    draft = _transaction(tenant_id, source, target, reference="IC-DRAFT")
    job.payload = {"transaction_id": str(draft.id)}
    with pytest.raises(RuntimeError, match="not posting"):
        multi_company_jobs._post_transaction(job, tenant_id=tenant_id)


@pytest.mark.django_db
def test_reverse_transaction_worker_requires_original_journal_evidence():
    tenant_id = uuid.uuid4()
    source, target = _company_pair_with_access(tenant_id)
    original = _transaction(
        tenant_id,
        source,
        target,
        reference="IC-ORIGINAL",
        status="posted",
        source_journal_id=None,
        target_journal_id=uuid.uuid4(),
    )
    reversal = _transaction(
        tenant_id,
        source,
        target,
        reference="IC-REVERSAL",
        reversed_transaction=original,
        status="posting",
    )
    job = AsyncJob.objects.create(
        tenant_id=tenant_id,
        actor_id="controller",
        command=multi_company_jobs.REVERSE_TRANSACTION,
        idempotency_key="reverse-missing-evidence",
        payload={"transaction_id": str(reversal.id)},
        correlation_id="corr-reverse",
    )

    with pytest.raises(RuntimeError, match="no reversible dual-journal evidence"):
        multi_company_jobs._reverse_transaction(job, tenant_id=tenant_id)


@pytest.mark.django_db
def test_expire_drafts_worker_expires_only_stale_drafts(monkeypatch):
    tenant_id = uuid.uuid4()
    settings = {**DEFAULT_SETTINGS, "draft_expiry_hours": 24}
    _activate_configuration(tenant_id, settings=settings)
    source, target = _company_pair_with_access(tenant_id)
    stale = _transaction(tenant_id, source, target, reference="IC-STALE")
    fresh = _transaction(tenant_id, source, target, reference="IC-FRESH")
    old_cutoff = timezone.now() - timedelta(hours=48)
    IntercompanyTransaction.objects.filter(pk=stale.pk).update(created_at=old_cutoff)
    job = AsyncJob.objects.create(
        tenant_id=tenant_id,
        actor_id="controller",
        command=multi_company_jobs.EXPIRE_DRAFTS,
        idempotency_key="expire-drafts",
        payload={"environment": "development"},
        correlation_id="corr-expire",
    )

    result = multi_company_jobs._expire_drafts(job, tenant_id=tenant_id)

    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert result == {"expired": 1}
    assert stale.status == "expired"
    assert fresh.status == "draft"

    result = multi_company_jobs._expire_drafts(job, tenant_id=tenant_id)
    assert result == {"expired": 0}


@pytest.mark.django_db
def test_transfer_pricing_calculates_supported_methods_and_resolves_effective_rule():
    tenant_id = uuid.uuid4()
    _activate_configuration(tenant_id)
    source, target = _company_pair_with_access(tenant_id)
    methods = [
        ("resale_minus", {"parameters": {"margin_percentage": "20.0000"}}, Decimal("80.0000")),
        ("comparable_uncontrolled", {"parameters": {"comparable_price": "88.8888"}}, Decimal("88.8888")),
        ("transactional_net_margin", {"parameters": {"net_margin_percentage": "12.5000"}}, Decimal("112.5000")),
        ("profit_split", {"parameters": {"target_share_percentage": "35.0000"}}, Decimal("35.0000")),
    ]

    for index, (method, overrides, expected) in enumerate(methods, start=1):
        rule = TransferPricingService.create_rule(
            tenant_id,
            "tax",
            f"corr-{method}",
            {
                "name": method.replace("_", " ").title(),
                "source_company_id": source.id,
                "target_company_id": target.id,
                "product_category": f"category-{index}",
                "transaction_type": "sale",
                "pricing_method": method,
                "effective_from": date(2024, 1, 1),
                **overrides,
            },
        )
        resolved = TransferPricingService.resolve_rule(
            tenant_id,
            source.id,
            target.id,
            f"category-{index}",
            "sale",
            date(2024, 1, 31),
        )
        assert resolved.id == rule.id
        calculated = TransferPricingService.calculate_price(tenant_id, {"rule_id": rule.id, "amount": "100.0000"})
        assert calculated.amount == expected
        assert calculated.pricing_method == method

    with pytest.raises(NotFoundError):
        TransferPricingService.resolve_rule(tenant_id, source.id, target.id, "missing", "sale", date(2024, 1, 31))
    with pytest.raises(ValidationError) as invalid_range:
        TransferPricingService.create_rule(
            tenant_id,
            "tax",
            "corr-invalid-range",
            {
                "name": "Invalid range",
                "source_company_id": source.id,
                "target_company_id": target.id,
                "product_category": "range",
                "transaction_type": "sale",
                "pricing_method": "resale_minus",
                "margin_range_min": "10.0000",
                "margin_range_max": "5.0000",
                "parameters": {"margin_percentage": "10.0000"},
                "effective_from": date(2024, 1, 1),
            },
        )
    assert invalid_range.value.message_dict == {"margin_range_max": ["Must not be below minimum."]}


@pytest.mark.django_db
def test_consolidation_generate_report_publish_cancel_and_conflict_paths():
    tenant_id = uuid.uuid4()
    _activate_configuration(tenant_id)
    source, target = _company_pair_with_access(tenant_id, actor="controller")
    completed = _run(
        tenant_id,
        name="Completed report",
        status="completed",
        period_start=date(2024, 7, 1),
        period_end=date(2024, 7, 31),
        report_snapshot={"currency": "USD", "total": "25.0000"},
        executed_by="executor",
    )
    posted = _transaction(
        tenant_id,
        source,
        target,
        reference="IC-AUTO-ELIM",
        status="posted",
        amount=Decimal("25.0000"),
        transaction_date=date(2024, 7, 15),
    )

    generated = ConsolidationService.generate_eliminations(tenant_id, completed.id, "controller", "corr-auto-elim")
    assert len(generated) == 1
    assert generated[0].source_transaction_id == posted.id
    assert ConsolidationService.generate_eliminations(tenant_id, completed.id, "controller", "corr-auto-elim") == []

    approved = ConsolidationService.approve(tenant_id, completed.id, "approver", "corr-approve", "approve-close")
    assert approved.status == "approved"
    published = ConsolidationService.publish(tenant_id, approved.id, "publisher", "corr-publish", "publish-close")
    assert published.status == "published"
    assert ConsolidationService.get_report(tenant_id, published.id) == {"currency": "USD", "total": "25.0000"}

    draft = _run(tenant_id, name="Draft cancel", period_start=date(2024, 8, 1), period_end=date(2024, 8, 31))
    cancelled = ConsolidationService.cancel(
        tenant_id, draft.id, "controller", "corr-cancel", "No longer needed", "cancel-run"
    )
    assert cancelled.status == "cancelled"
    with pytest.raises(ConflictError):
        ConsolidationService.get_report(tenant_id, cancelled.id)

    with pytest.raises(ConflictError):
        ConsolidationService.create_manual_elimination(
            tenant_id,
            cancelled.id,
            "controller",
            "corr-elim-cancelled",
            {
                "elimination_type": "intercompany_balance",
                "source_company_id": source.id,
                "target_company_id": target.id,
                "debit_account": "4000",
                "credit_account": "2000",
                "amount": "10.0000",
                "currency": "USD",
            },
        )


@pytest.mark.django_db
def test_configuration_production_self_activation_and_import_environment_guards(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setenv("MULTI_COMPANY_EXPORT_SIGNING_KEY", "config-guard-signing-key")
    production = MultiCompanyConfigurationService.create_draft(
        tenant_id,
        "author",
        "corr-prod",
        "production",
        DEFAULT_SETTINGS,
        "Production defaults",
    )
    with pytest.raises(PermissionDenied):
        MultiCompanyConfigurationService.activate(tenant_id, production.id, "author", "corr-self-activate")

    active = _activate_configuration(tenant_id)
    document = MultiCompanyConfigurationService.export_document(
        tenant_id,
        "development",
        actor_id="exporter",
        correlation_id="corr-export-guard",
    )
    with pytest.raises(ValidationError) as wrong_environment:
        MultiCompanyConfigurationService.rollback(
            tenant_id,
            active.id,
            "approver",
            "corr-rollback-wrong-env",
            {"environment": "production", "change_summary": "Wrong environment"},
        )
    assert wrong_environment.value.message_dict == {"environment": ["Must match the target version."]}

    with pytest.raises(ValidationError):
        MultiCompanyConfigurationService.import_document(
            tenant_id,
            "importer",
            "corr-import-bad-wrapper",
            {"environment": "development", "document": {**document, "signature": "sha256:bad"}},
        )


@pytest.mark.django_db
def test_terminal_and_illegal_transitions_fail_closed():
    tenant_id = uuid.uuid4()
    source, target = _company_pair_with_access(tenant_id)
    cancelled = _transaction(tenant_id, source, target, status="cancelled")
    draft = _transaction(tenant_id, source, target, reference="IC-DRAFT")

    with pytest.raises(TerminalStateError):
        IntercompanyTransactionService.submit(tenant_id, cancelled.id, "controller", "corr-submit", "terminal")
    with pytest.raises(IllegalTransitionError):
        IntercompanyTransactionService.post(tenant_id, draft.id, "controller", "corr-post", "draft-post", "draft-post")
