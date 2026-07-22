"""Tenant-isolated persistence for the multi-company financial domain.

Models deliberately contain structural invariants and immutable-evidence guards;
all business mutations and cross-record validation live in :mod:`services`.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from src.core.tenancy import TENANT_SCOPED, TenantScopedModel, TimestampedModel, register_model_scope


def _correlation_id() -> str:
    return uuid.uuid4().hex


class MutableTenantAggregate(TenantScopedModel, TimestampedModel):
    """Common auditable and versioned aggregate contract."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.CharField(max_length=255, default="system")
    updated_by = models.CharField(max_length=255, default="system")
    correlation_id = models.CharField(max_length=64, default=_correlation_id, db_index=True)
    version = models.PositiveBigIntegerField(default=1)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            persisted = type(self).objects.filter(pk=self.pk).values_list("version", flat=True).first()
            if persisted is not None and self.version <= persisted:
                self.version = persisted + 1
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"version", "updated_at"}
        super().save(*args, **kwargs)


class AppendOnlyTenantRecord(TenantScopedModel):
    """Evidence row that can be inserted once and never rewritten or removed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    correlation_id = models.CharField(max_length=64, default=_correlation_id, db_index=True)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Immutable evidence records cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Immutable evidence records cannot be deleted.")


class ImmutableTenantQuerySet(models.QuerySet):
    """Tenant-aware manager that closes bulk mutation escape hatches."""

    def for_tenant(self, tenant_id: uuid.UUID) -> "ImmutableTenantQuerySet":
        return self.filter(tenant_id=tenant_id)

    def update(self, **kwargs: Any) -> int:
        raise ValidationError("Immutable evidence records cannot be modified.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Immutable evidence records cannot be deleted.")


class Company(MutableTenantAggregate):
    """Legal or operating entity registered within one tenant."""

    company_code = models.CharField(max_length=50, db_index=True)
    company_name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=3)
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=1)
    parent_company = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="subsidiaries"
    )
    consolidation_group = models.CharField(max_length=50, blank=True)
    ownership_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_holding = models.BooleanField(default=False)

    class Meta:
        db_table = "multi_company_companies"
        indexes = [
            models.Index(fields=["tenant_id", "company_code"], name="mc_company_code_idx"),
            models.Index(fields=["tenant_id", "is_active", "company_code"], name="mc_company_active_idx"),
            models.Index(fields=["tenant_id", "consolidation_group", "is_active"], name="mc_company_group_idx"),
            models.Index(fields=["tenant_id", "parent_company", "is_active"], name="mc_company_parent_idx"),
            models.Index(fields=["tenant_id", "created_at"], name="mc_company_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "company_code"], name="unique_company_code_per_tenant"),
            models.CheckConstraint(
                condition=Q(fiscal_year_start_month__gte=1, fiscal_year_start_month__lte=12),
                name="mc_company_fiscal_month_ck",
            ),
            models.CheckConstraint(
                condition=Q(ownership_percentage__isnull=True)
                | Q(ownership_percentage__gte=0, ownership_percentage__lte=100),
                name="mc_company_ownership_ck",
            ),
            models.CheckConstraint(condition=~Q(parent_company=models.F("id")), name="mc_company_not_self_parent_ck"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.company_code = self.company_code.strip().upper()
        self.currency = self.currency.strip().upper()
        if not self.legal_name:
            self.legal_name = self.company_name
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.company_code} - {self.company_name}"


class CompanyAccessGrant(MutableTenantAggregate):
    class Role(models.TextChoices):
        VIEWER = "viewer", "Viewer"
        OPERATOR = "operator", "Operator"
        APPROVER = "approver", "Approver"
        CONTROLLER = "controller", "Controller"
        TAX_ADMIN = "tax_admin", "Tax administrator"

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="access_grants")
    subject_id = models.CharField(max_length=255, db_index=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    granted_by = models.CharField(max_length=255)
    revoked_by = models.CharField(max_length=255, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "multi_company_access_grants"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "company", "subject_id", "role"], name="mc_access_unique_grant"
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gt=models.F("valid_from")),
                name="mc_access_valid_window_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "subject_id", "valid_until"], name="mc_access_subject_idx"),
            models.Index(fields=["tenant_id", "company", "role", "valid_until"], name="mc_access_company_idx"),
        ]


TRANSACTION_TYPES = (
    ("sale", "Sale"),
    ("purchase", "Purchase"),
    ("service", "Service"),
    ("loan", "Loan"),
    ("transfer", "Transfer"),
    ("dividend", "Dividend"),
    ("cost_allocation", "Cost allocation"),
)


class TransferPricingRule(MutableTenantAggregate):
    class PricingMethod(models.TextChoices):
        COST_PLUS = "cost_plus", "Cost plus"
        RESALE_MINUS = "resale_minus", "Resale minus"
        COMPARABLE_UNCONTROLLED = "comparable_uncontrolled", "Comparable uncontrolled"
        TRANSACTIONAL_NET_MARGIN = "transactional_net_margin", "Transactional net margin"
        PROFIT_SPLIT = "profit_split", "Profit split"
        EXTENSION = "extension", "Extension"

    rule_key = models.UUIDField(default=uuid.uuid4)
    rule_version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=255)
    source_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="source_pricing_rules")
    target_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="target_pricing_rules")
    product_category = models.CharField(max_length=100)
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES)
    pricing_method = models.CharField(max_length=40, choices=PricingMethod.choices)
    extension_key = models.CharField(max_length=150, blank=True)
    markup_percentage = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    margin_range_min = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    margin_range_max = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    parameters = models.JSONField(default=dict)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    documentation = models.TextField(blank=True)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        db_table = "multi_company_transfer_pricing_rules"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "rule_key", "rule_version"], name="mc_pricing_version_uk"),
            models.UniqueConstraint(
                fields=[
                    "tenant_id", "source_company", "target_company", "product_category", "transaction_type", "effective_from"
                ],
                condition=Q(is_active=True, is_deleted=False),
                name="mc_pricing_active_app_uk",
            ),
            models.CheckConstraint(condition=~Q(source_company=models.F("target_company")), name="mc_pricing_companies_ck"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="mc_pricing_dates_ck",
            ),
            models.CheckConstraint(
                condition=Q(margin_range_min__isnull=True)
                | Q(margin_range_max__isnull=True)
                | Q(margin_range_min__lte=models.F("margin_range_max")),
                name="mc_pricing_margin_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "source_company", "target_company", "product_category"], name="mc_pricing_match_idx"),
            models.Index(fields=["tenant_id", "is_active", "effective_from", "effective_to"], name="mc_pricing_active_idx"),
            models.Index(fields=["tenant_id", "pricing_method"], name="mc_pricing_method_idx"),
        ]


class IntercompanyTransaction(MutableTenantAggregate):
    class TransactionType(models.TextChoices):
        SALE = "sale", "Sale"
        PURCHASE = "purchase", "Purchase"
        SERVICE = "service", "Service"
        LOAN = "loan", "Loan"
        TRANSFER = "transfer", "Transfer"
        DIVIDEND = "dividend", "Dividend"
        COST_ALLOCATION = "cost_allocation", "Cost allocation"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        POSTING = "posting", "Posting"
        POSTED = "posted", "Posted"
        POSTING_FAILED = "posting_failed", "Posting failed"
        DISPUTED = "disputed", "Disputed"
        ELIMINATED = "eliminated", "Eliminated"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    reference = models.CharField(max_length=100)
    source_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="outbound_intercompany_transactions")
    target_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="inbound_intercompany_transactions")
    transaction_type = models.CharField(max_length=30, choices=TransactionType.choices)
    product_category = models.CharField(max_length=100, blank=True)
    original_amount = models.DecimalField(max_digits=19, decimal_places=4)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    target_amount = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    description = models.TextField(blank=True)
    transaction_date = models.DateField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT, db_index=True)
    transfer_pricing_rule = models.ForeignKey(TransferPricingRule, null=True, blank=True, on_delete=models.PROTECT)
    transfer_pricing_snapshot = models.JSONField(default=dict)
    source_journal_id = models.UUIDField(null=True, blank=True)
    target_journal_id = models.UUIDField(null=True, blank=True)
    compensation_journal_ids = models.JSONField(default=list)
    posted_date = models.DateField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    dispute_reason = models.TextField(blank=True)
    failure_code = models.CharField(max_length=100, blank=True)
    failure_detail = models.TextField(blank=True)
    job_id = models.UUIDField(null=True, blank=True)
    transition_history = models.JSONField(default=list)
    reversed_transaction = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals")

    class Meta:
        db_table = "multi_company_transactions"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "reference"], name="mc_transaction_reference_uk"),
            models.CheckConstraint(condition=~Q(source_company=models.F("target_company")), name="mc_transaction_companies_ck"),
            models.CheckConstraint(condition=Q(original_amount__gt=0), name="mc_transaction_original_gt_zero_ck"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="mc_transaction_amount_gt_zero_ck"),
            models.CheckConstraint(condition=Q(exchange_rate__isnull=True) | Q(exchange_rate__gt=0), name="mc_transaction_rate_ck"),
            models.CheckConstraint(condition=Q(target_amount__isnull=True) | Q(target_amount__gte=0), name="mc_transaction_target_amount_ck"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "transaction_date"], name="mc_tx_status_date_idx"),
            models.Index(fields=["tenant_id", "source_company", "status", "transaction_date"], name="mc_tx_source_idx"),
            models.Index(fields=["tenant_id", "target_company", "status", "transaction_date"], name="mc_tx_target_idx"),
            models.Index(fields=["tenant_id", "transaction_type", "status"], name="mc_tx_type_idx"),
            models.Index(fields=["tenant_id", "reference"], name="mc_tx_reference_idx"),
            models.Index(fields=["tenant_id", "job_id"], name="mc_tx_job_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.currency = self.currency.upper()
        if not self._state.adding:
            prior = type(self).objects.filter(pk=self.pk).values("status").first()
            if prior and prior["status"] in {self.Status.POSTED, self.Status.ELIMINATED} and self.status == prior["status"]:
                raise ValidationError("Posted financial transactions are immutable; use reversal or elimination.")
        super().save(*args, **kwargs)


class IntercompanyApproval(AppendOnlyTenantRecord):
    class Side(models.TextChoices):
        SOURCE = "source", "Source"
        TARGET = "target", "Target"

    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    transaction = models.ForeignKey(IntercompanyTransaction, on_delete=models.PROTECT, related_name="approvals")
    side = models.CharField(max_length=10, choices=Side.choices)
    attempt = models.PositiveIntegerField()
    approver_id = models.CharField(max_length=255)
    decision = models.CharField(max_length=10, choices=Decision.choices)
    reason = models.TextField(blank=True)
    workflow_reference = models.CharField(max_length=255, blank=True)
    decided_at = models.DateTimeField()
    objects = ImmutableTenantQuerySet.as_manager()

    class Meta:
        db_table = "multi_company_approvals"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "transaction", "side", "attempt"], name="mc_approval_attempt_uk"),
            models.CheckConstraint(condition=Q(decision="approved") | ~Q(reason=""), name="mc_approval_rejection_reason_ck"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "transaction", "side", "decided_at"], name="mc_approval_tx_idx"),
            models.Index(fields=["tenant_id", "approver_id", "decided_at"], name="mc_approval_actor_idx"),
        ]


class ConsolidationRun(MutableTenantAggregate):
    class TranslationMethod(models.TextChoices):
        CURRENT_RATE = "current_rate", "Current rate"
        TEMPORAL = "temporal", "Temporal"
        MONETARY_NON_MONETARY = "monetary_non_monetary", "Monetary/non-monetary"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        APPROVED = "approved", "Approved"
        PUBLISHED = "published", "Published"
        CANCELLED = "cancelled", "Cancelled"

    name = models.CharField(max_length=255)
    consolidation_group = models.CharField(max_length=50)
    period_start = models.DateField()
    period_end = models.DateField()
    reporting_currency = models.CharField(max_length=3)
    translation_method = models.CharField(max_length=40, choices=TranslationMethod.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    total_companies = models.PositiveIntegerField(default=0)
    total_eliminations = models.PositiveIntegerField(default=0)
    elimination_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    minority_interest_total = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    job_id = models.UUIDField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    executed_by = models.CharField(max_length=255, blank=True)
    approved_by = models.CharField(max_length=255, blank=True)
    published_by = models.CharField(max_length=255, blank=True)
    failure_code = models.CharField(max_length=100, blank=True)
    failure_step = models.CharField(max_length=100, blank=True)
    failure_detail = models.TextField(blank=True)
    report_snapshot = models.JSONField(null=True, blank=True)
    transition_history = models.JSONField(default=list)

    class Meta:
        db_table = "multi_company_consolidation_runs"
        constraints = [
            models.CheckConstraint(condition=Q(period_start__lte=models.F("period_end")), name="mc_consolidation_period_ck"),
            models.UniqueConstraint(
                fields=["tenant_id", "consolidation_group", "period_start", "period_end"], name="mc_consolidation_period_uk"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "status", "created_at"], name="mc_consolidation_status_idx"),
            models.Index(fields=["tenant_id", "consolidation_group", "period_end"], name="mc_consolidation_group_idx"),
            models.Index(fields=["tenant_id", "job_id"], name="mc_consolidation_job_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.reporting_currency = self.reporting_currency.upper()
        if not self._state.adding:
            prior = type(self).objects.filter(pk=self.pk).values("status").first()
            if prior and prior["status"] in {self.Status.APPROVED, self.Status.PUBLISHED} and self.status == prior["status"]:
                raise ValidationError("Approved financial snapshots are immutable.")
        super().save(*args, **kwargs)


class EliminationEntry(AppendOnlyTenantRecord):
    class EliminationType(models.TextChoices):
        INTERCOMPANY_BALANCE = "intercompany_balance", "Intercompany balance"
        INTERCOMPANY_REVENUE = "intercompany_revenue", "Intercompany revenue"
        INTERCOMPANY_EXPENSE = "intercompany_expense", "Intercompany expense"
        INTERCOMPANY_RECEIVABLE = "intercompany_receivable", "Intercompany receivable"
        INTERCOMPANY_PAYABLE = "intercompany_payable", "Intercompany payable"
        UNREALIZED_PROFIT = "unrealized_profit", "Unrealized profit"
        INTERCOMPANY_DIVIDEND = "intercompany_dividend", "Intercompany dividend"
        EQUITY_INVESTMENT = "equity_investment", "Equity investment"
        MINORITY_INTEREST = "minority_interest", "Minority interest"

    created_by = models.CharField(max_length=255)
    consolidation_run = models.ForeignKey(ConsolidationRun, on_delete=models.PROTECT, related_name="eliminations")
    elimination_type = models.CharField(max_length=40, choices=EliminationType.choices)
    source_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="source_eliminations")
    target_company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="target_eliminations")
    debit_account = models.CharField(max_length=20)
    credit_account = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    currency = models.CharField(max_length=3)
    description = models.TextField(blank=True)
    source_transaction = models.ForeignKey(IntercompanyTransaction, null=True, blank=True, on_delete=models.PROTECT)
    is_auto_generated = models.BooleanField(default=True)
    rule_key = models.CharField(max_length=150, blank=True)
    sequence = models.PositiveIntegerField()
    objects = ImmutableTenantQuerySet.as_manager()

    class Meta:
        db_table = "multi_company_eliminations"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "consolidation_run", "sequence"], name="mc_elimination_sequence_uk"),
            models.CheckConstraint(condition=~Q(source_company=models.F("target_company")), name="mc_elimination_companies_ck"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="mc_elimination_amount_ck"),
            models.CheckConstraint(condition=~Q(debit_account=models.F("credit_account")), name="mc_elimination_accounts_ck"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "consolidation_run", "elimination_type"], name="mc_elimination_run_idx"),
            models.Index(fields=["tenant_id", "source_company", "target_company"], name="mc_elimination_pair_idx"),
            models.Index(fields=["tenant_id", "source_transaction"], name="mc_elimination_tx_idx"),
        ]


class MultiCompanyConfigurationVersion(AppendOnlyTenantRecord):
    class Environment(models.TextChoices):
        DEVELOPMENT = "development", "Development"
        STAGING = "staging", "Staging"
        PRODUCTION = "production", "Production"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        SUPERSEDED = "superseded", "Superseded"
        ROLLED_BACK = "rolled_back", "Rolled back"

    created_by = models.CharField(max_length=255)
    environment = models.CharField(max_length=20, choices=Environment.choices)
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    schema_version = models.CharField(max_length=20, default="1.0")
    settings = models.JSONField()
    change_summary = models.TextField()
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    activated_by = models.CharField(max_length=255, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "multi_company_configuration_versions"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "environment", "version"], name="mc_config_version_uk"),
            models.UniqueConstraint(
                fields=["tenant_id", "environment"], condition=Q(status="active"), name="mc_config_one_active_uk"
            ),
        ]
        indexes = [models.Index(fields=["tenant_id", "environment", "status"], name="mc_config_lookup_idx")]

    # Draft rows are intentionally editable through a controlled service; all
    # other versions are immutable audit evidence.
    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            current = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if current != self.Status.DRAFT:
                raise ValidationError("Activated configuration versions are immutable.")
            models.Model.save(self, *args, **kwargs)
            return
        models.Model.save(self, *args, **kwargs)


class ConfigurationAuditRecord(AppendOnlyTenantRecord):
    """Tamper-evident evidence for activation, rollback, import and export."""

    actor_id = models.CharField(max_length=255)
    environment = models.CharField(max_length=20, choices=MultiCompanyConfigurationVersion.Environment.choices)
    action = models.CharField(max_length=30)
    from_version = models.PositiveIntegerField(null=True, blank=True)
    to_version = models.PositiveIntegerField(null=True, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    objects = ImmutableTenantQuerySet.as_manager()

    class Meta:
        db_table = "multi_company_configuration_audit"
        indexes = [models.Index(fields=["tenant_id", "environment", "created_at"], name="mc_config_audit_idx")]


for _model in (
    Company,
    CompanyAccessGrant,
    TransferPricingRule,
    IntercompanyTransaction,
    IntercompanyApproval,
    ConsolidationRun,
    EliminationEntry,
    MultiCompanyConfigurationVersion,
    ConfigurationAuditRecord,
):
    register_model_scope(_model, TENANT_SCOPED)
