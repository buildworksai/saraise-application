"""Operation-specific serializers for the governed multi-company API.

Write serializers deliberately are not model serializers: ownership, audit,
state, concurrency and job fields are server-controlled and are never copied
from an HTTP request into an aggregate.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import (
    Company,
    CompanyAccessGrant,
    ConsolidationRun,
    EliminationEntry,
    IntercompanyApproval,
    IntercompanyTransaction,
    MultiCompanyConfigurationVersion,
    TransferPricingRule,
)

SERVER_OWNED_FIELDS = frozenset(
    {
        "id", "tenant_id", "created_by", "updated_by", "created_at", "updated_at",
        "correlation_id", "version", "is_deleted", "deleted_at", "status",
        "transition_history", "job_id", "source_journal_id", "target_journal_id",
        "posted_date", "failure_code", "failure_detail", "report_snapshot",
        "started_at", "completed_at", "approved_at", "published_at", "approved_by",
        "published_by", "activated_by", "activated_at", "transfer_pricing_snapshot",
    }
)

TRANSACTION_TYPES = (
    "sale", "purchase", "service", "loan", "transfer", "dividend", "cost_allocation",
)
PRICING_METHODS = (
    "cost_plus", "resale_minus", "comparable_uncontrolled",
    "transactional_net_margin", "profit_split", "extension",
)
TRANSLATION_METHODS = ("current_rate", "temporal", "monetary_non_monetary")
ACCESS_ROLES = ("viewer", "operator", "approver", "controller", "tax_admin")
ELIMINATION_TYPES = (
    "intercompany_balance", "intercompany_revenue", "intercompany_expense",
    "intercompany_receivable", "intercompany_payable", "unrealized_profit",
    "intercompany_dividend", "equity_investment", "minority_interest",
)
ENVIRONMENTS = ("development", "staging", "production")


class RejectServerOwnedFieldsMixin:
    """Fail explicitly when callers attempt to set authoritative fields."""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        supplied = set(getattr(self, "initial_data", {})) & SERVER_OWNED_FIELDS
        if supplied:
            raise serializers.ValidationError(
                {field: "This field is server-owned." for field in sorted(supplied)}
            )
        return super().validate(attrs)  # type: ignore[misc]


class _ReadSerializer(serializers.ModelSerializer):
    allowed_commands = serializers.SerializerMethodField()
    denial_reasons = serializers.SerializerMethodField()

    command_permissions: dict[str, str] = {}

    def candidate_commands(self, instance: Any) -> set[str]:
        return set()

    def _command_projection(self, instance: Any) -> tuple[list[str], dict[str, str]]:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        candidates = self.candidate_commands(instance)
        allowed: list[str] = []
        denied: dict[str, str] = {}
        for command, permission in self.command_permissions.items():
            if command not in candidates:
                denied[command] = "state_not_allowed"
            elif user is None or not user.has_perm(permission):
                denied[command] = "permission_denied"
            else:
                allowed.append(command)
        return sorted(allowed), denied

    def get_allowed_commands(self, instance: Any) -> list[str]:
        resolver = self.context.get("command_resolver")
        if callable(resolver):
            result = resolver(instance)
            return list(result.get("allowed_commands", ()))
        explicit = getattr(instance, "allowed_commands", None)
        return list(explicit) if explicit is not None else self._command_projection(instance)[0]

    def get_denial_reasons(self, instance: Any) -> dict[str, str]:
        resolver = self.context.get("command_resolver")
        if callable(resolver):
            result = resolver(instance)
            return dict(result.get("denial_reasons", {}))
        explicit = getattr(instance, "denial_reasons", None)
        return dict(explicit) if explicit is not None else self._command_projection(instance)[1]


COMPANY_LIST_FIELDS = (
    "id", "company_code", "company_name", "legal_name", "currency",
    "parent_company", "consolidation_group", "ownership_percentage", "is_active",
    "is_holding", "version", "created_at", "updated_at", "allowed_commands",
    "denial_reasons",
)


class CompanyListSerializer(_ReadSerializer):
    command_permissions = {
        "update": "multi_company.company:update",
        "deactivate": "multi_company.company:deactivate",
        "reactivate": "multi_company.company:update",
        "delete": "multi_company.company:delete",
    }

    def candidate_commands(self, instance: Company) -> set[str]:
        return {"update", "delete", "deactivate" if instance.is_active else "reactivate"}

    class Meta:
        model = Company
        fields = COMPANY_LIST_FIELDS
        read_only_fields = fields


class CompanyDetailSerializer(_ReadSerializer):
    tax_id = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = (
            *COMPANY_LIST_FIELDS, "tax_id", "address", "fiscal_year_start_month",
            "created_by", "updated_by", "correlation_id", "is_deleted", "deleted_at",
        )
        read_only_fields = fields

    def get_tax_id(self, instance: Company) -> str:
        value = str(instance.tax_id or "")
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.has_perm("multi_company.company:read_sensitive"):
            return value
        if not value:
            return ""
        return f"{'*' * max(0, len(value) - 4)}{value[-4:]}"


class CompanyCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    company_code = serializers.CharField(max_length=50)
    company_name = serializers.CharField(max_length=255)
    legal_name = serializers.CharField(max_length=255)
    tax_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    currency = serializers.CharField(min_length=3, max_length=3)
    fiscal_year_start_month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    parent_company_id = serializers.UUIDField(required=False, allow_null=True)
    consolidation_group = serializers.CharField(max_length=50, required=False, allow_blank=True)
    ownership_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, allow_null=True
    )
    address = serializers.CharField(required=False, allow_blank=True)
    is_holding = serializers.BooleanField(required=False)
    idempotency_key = serializers.CharField(max_length=255)


class CompanyUpdateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    company_code = serializers.CharField(max_length=50, required=False)
    company_name = serializers.CharField(max_length=255, required=False)
    legal_name = serializers.CharField(max_length=255, required=False)
    tax_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    currency = serializers.CharField(min_length=3, max_length=3, required=False)
    fiscal_year_start_month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    parent_company_id = serializers.UUIDField(required=False, allow_null=True)
    consolidation_group = serializers.CharField(max_length=50, required=False, allow_blank=True)
    ownership_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, allow_null=True
    )
    address = serializers.CharField(required=False, allow_blank=True)
    is_holding = serializers.BooleanField(required=False)


class ExpectedVersionSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    transition_key = serializers.CharField(max_length=255)


class CompanyHierarchySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    company_code = serializers.CharField()
    company_name = serializers.CharField()
    is_active = serializers.BooleanField()
    depth = serializers.IntegerField(min_value=0, default=0)
    children = serializers.ListField(child=serializers.DictField(), required=False)


class CompanyAccessGrantSerializer(_ReadSerializer):
    command_permissions = {"revoke": "multi_company.company_access:revoke"}

    def candidate_commands(self, instance: CompanyAccessGrant) -> set[str]:
        return set() if instance.is_deleted or instance.revoked_at else {"revoke"}

    class Meta:
        model = CompanyAccessGrant
        fields = (
            "id", "company", "subject_id", "role", "valid_from", "valid_until",
            "granted_by", "revoked_by", "revoked_at", "is_deleted", "created_at",
            "version", "allowed_commands", "denial_reasons",
        )
        read_only_fields = fields


class CompanyAccessGrantCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    company_id = serializers.UUIDField()
    subject_id = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=ACCESS_ROLES)
    valid_from = serializers.DateTimeField(required=False)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs.get("valid_until") and attrs.get("valid_from") and attrs["valid_until"] <= attrs["valid_from"]:
            raise serializers.ValidationError({"valid_until": "Must be later than valid_from."})
        return attrs


class CompanyAccessRevokeSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=2000)


TRANSACTION_LIST_FIELDS = (
    "id", "reference", "source_company", "target_company", "transaction_type",
    "product_category", "amount", "currency", "target_amount", "transaction_date",
    "status", "job_id", "version", "created_at", "updated_at", "allowed_commands",
    "denial_reasons",
)


class TransactionListSerializer(_ReadSerializer):
    command_permissions = {
        "update": "multi_company.transaction:update",
        "submit": "multi_company.transaction:submit",
        "approve": "multi_company.transaction:approve",
        "dispute": "multi_company.transaction:dispute",
        "resolve_dispute": "multi_company.transaction:dispute",
        "apply_transfer_pricing": "multi_company.transfer_pricing:calculate",
        "post": "multi_company.transaction:post",
        "retry_posting": "multi_company.transaction:post",
        "cancel": "multi_company.transaction:cancel",
        "reverse": "multi_company.transaction:reverse",
    }

    def candidate_commands(self, instance: IntercompanyTransaction) -> set[str]:
        status = instance.status
        result: set[str] = set()
        if status == "draft": result.update({"update", "submit", "apply_transfer_pricing", "cancel"})
        if status == "pending_approval": result.update({"approve", "dispute", "cancel"})
        if status == "approved": result.update({"dispute", "post", "cancel"})
        if status == "disputed": result.update({"resolve_dispute", "cancel"})
        if status == "posting_failed": result.update({"retry_posting", "cancel"})
        if status == "posted": result.add("reverse")
        return result
    class Meta:
        model = IntercompanyTransaction
        fields = TRANSACTION_LIST_FIELDS
        read_only_fields = fields


class IntercompanyApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntercompanyApproval
        fields = (
            "id", "transaction", "side", "attempt", "approver_id", "decision",
            "reason", "workflow_reference", "decided_at", "correlation_id", "created_at",
        )
        read_only_fields = fields


class TransactionDetailSerializer(_ReadSerializer):
    approvals = IntercompanyApprovalSerializer(many=True, read_only=True)

    class Meta:
        model = IntercompanyTransaction
        fields = (
            *TRANSACTION_LIST_FIELDS, "original_amount", "exchange_rate", "description",
            "transfer_pricing_rule", "transfer_pricing_snapshot", "source_journal_id",
            "target_journal_id", "posted_date", "cancellation_reason", "dispute_reason",
            "failure_code", "failure_detail", "transition_history", "created_by",
            "updated_by", "correlation_id", "approvals",
        )
        read_only_fields = fields


class TransactionCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    reference = serializers.CharField(max_length=100)
    source_company_id = serializers.UUIDField()
    target_company_id = serializers.UUIDField()
    transaction_type = serializers.ChoiceField(choices=TRANSACTION_TYPES)
    product_category = serializers.CharField(max_length=100, required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=Decimal("0.0001"))
    currency = serializers.CharField(min_length=3, max_length=3)
    exchange_rate = serializers.DecimalField(max_digits=18, decimal_places=8, min_value=Decimal("0.00000001"), required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)
    transaction_date = serializers.DateField()
    transfer_pricing_rule_id = serializers.UUIDField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=255)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs["source_company_id"] == attrs["target_company_id"]:
            raise serializers.ValidationError({"target_company_id": "Must differ from source company."})
        return attrs


class TransactionUpdateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    reference = serializers.CharField(max_length=100, required=False)
    transaction_type = serializers.ChoiceField(choices=TRANSACTION_TYPES, required=False)
    product_category = serializers.CharField(max_length=100, required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=Decimal("0.0001"), required=False)
    currency = serializers.CharField(min_length=3, max_length=3, required=False)
    exchange_rate = serializers.DecimalField(max_digits=18, decimal_places=8, min_value=Decimal("0.00000001"), required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)
    transaction_date = serializers.DateField(required=False)
    transfer_pricing_rule_id = serializers.UUIDField(required=False, allow_null=True)


class TransactionSubmitSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    transition_key = serializers.CharField(max_length=255)


class ApprovalDecisionSerializer(TransactionSubmitSerializer):
    side = serializers.ChoiceField(choices=("source", "target"))
    decision = serializers.ChoiceField(choices=("approved", "rejected"))
    reason = serializers.CharField(required=False, allow_blank=True)
    workflow_reference = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs["decision"] == "rejected" and not attrs.get("reason", "").strip():
            raise serializers.ValidationError({"reason": "A rejection reason is required."})
        return attrs


class DisputeSerializer(TransactionSubmitSerializer):
    reason = serializers.CharField(max_length=4000, allow_blank=False)


class ResolveDisputeSerializer(TransactionSubmitSerializer):
    resolution = serializers.CharField(max_length=4000, allow_blank=False)


class CancelSerializer(TransactionSubmitSerializer):
    reason = serializers.CharField(max_length=4000, allow_blank=False)


class ReverseSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=4000, allow_blank=False)


class ApplyTransferPricingSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    rule_id = serializers.UUIDField(required=False, allow_null=True)


CONSOLIDATION_LIST_FIELDS = (
    "id", "name", "consolidation_group", "period_start", "period_end",
    "reporting_currency", "translation_method", "status", "total_companies",
    "total_eliminations", "elimination_total", "minority_interest_total", "job_id",
    "version", "created_at", "updated_at", "allowed_commands", "denial_reasons",
)


class ConsolidationRunListSerializer(_ReadSerializer):
    command_permissions = {
        "update": "multi_company.consolidation:update",
        "execute": "multi_company.consolidation:execute",
        "retry": "multi_company.consolidation:execute",
        "approve": "multi_company.consolidation:approve",
        "publish": "multi_company.consolidation:publish",
        "cancel": "multi_company.consolidation:update",
        "create_elimination": "multi_company.elimination:create",
    }

    def candidate_commands(self, instance: ConsolidationRun) -> set[str]:
        mapping = {
            "draft": {"update", "execute", "cancel"},
            "failed": {"retry", "cancel"},
            "completed": {"approve", "create_elimination"},
            "approved": {"publish"},
        }
        return mapping.get(instance.status, set())
    class Meta:
        model = ConsolidationRun
        fields = CONSOLIDATION_LIST_FIELDS
        read_only_fields = fields


class ConsolidationRunDetailSerializer(_ReadSerializer):
    class Meta:
        model = ConsolidationRun
        fields = (
            *CONSOLIDATION_LIST_FIELDS, "started_at", "completed_at", "approved_at",
            "published_at", "approved_by", "published_by", "failure_code", "failure_step",
            "failure_detail", "report_snapshot", "transition_history", "created_by",
            "updated_by", "correlation_id",
        )
        read_only_fields = fields


class ConsolidationRunCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=255)
    consolidation_group = serializers.CharField(max_length=50)
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    reporting_currency = serializers.CharField(min_length=3, max_length=3)
    translation_method = serializers.ChoiceField(choices=TRANSLATION_METHODS)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs["period_start"] > attrs["period_end"]:
            raise serializers.ValidationError({"period_end": "Must not precede period_start."})
        return attrs


class ConsolidationRunUpdateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    consolidation_group = serializers.CharField(max_length=50, required=False)
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)
    reporting_currency = serializers.CharField(min_length=3, max_length=3, required=False)
    translation_method = serializers.ChoiceField(choices=TRANSLATION_METHODS, required=False)


class ManualEliminationCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    elimination_type = serializers.ChoiceField(choices=ELIMINATION_TYPES)
    source_company_id = serializers.UUIDField()
    target_company_id = serializers.UUIDField()
    debit_account = serializers.CharField(max_length=20)
    credit_account = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=Decimal("0.0001"))
    currency = serializers.CharField(min_length=3, max_length=3)
    description = serializers.CharField(required=False, allow_blank=True)
    source_transaction_id = serializers.UUIDField(required=False, allow_null=True)
    rule_key = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        errors = {}
        if attrs["source_company_id"] == attrs["target_company_id"]:
            errors["target_company_id"] = "Must differ from source company."
        if attrs["debit_account"] == attrs["credit_account"]:
            errors["credit_account"] = "Must differ from debit account."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class EliminationEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = EliminationEntry
        fields = (
            "id", "consolidation_run", "elimination_type", "source_company",
            "target_company", "debit_account", "credit_account", "amount", "currency",
            "description", "source_transaction", "is_auto_generated", "rule_key",
            "sequence", "created_by", "correlation_id", "created_at",
        )
        read_only_fields = fields


class ConsolidatedReportSerializer(serializers.Serializer):
    def to_representation(self, instance: Any) -> dict[str, Any]:
        if not isinstance(instance, dict):
            raise serializers.ValidationError("Persisted report snapshot must be an object.")
        return instance


RULE_LIST_FIELDS = (
    "id", "rule_key", "rule_version", "name", "source_company", "target_company",
    "product_category", "transaction_type", "pricing_method", "effective_from",
    "effective_to", "is_active", "version", "created_at", "updated_at",
    "allowed_commands", "denial_reasons",
)


class TransferPricingRuleListSerializer(_ReadSerializer):
    command_permissions = {
        "create_version": "multi_company.transfer_pricing:update",
        "delete": "multi_company.transfer_pricing:delete",
        "calculate": "multi_company.transfer_pricing:calculate",
    }

    def candidate_commands(self, instance: TransferPricingRule) -> set[str]:
        result = {"calculate", "create_version"}
        if not instance.is_active:
            result.add("delete")
        return result
    class Meta:
        model = TransferPricingRule
        fields = RULE_LIST_FIELDS
        read_only_fields = fields


class TransferPricingRuleDetailSerializer(_ReadSerializer):
    class Meta:
        model = TransferPricingRule
        fields = (
            *RULE_LIST_FIELDS, "extension_key", "markup_percentage", "margin_range_min",
            "margin_range_max", "parameters", "documentation", "supersedes", "created_by",
            "updated_by", "correlation_id",
        )
        read_only_fields = fields


class _TransferRuleFields(RejectServerOwnedFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=255)
    source_company_id = serializers.UUIDField()
    target_company_id = serializers.UUIDField()
    product_category = serializers.CharField(max_length=100)
    transaction_type = serializers.ChoiceField(choices=TRANSACTION_TYPES)
    pricing_method = serializers.ChoiceField(choices=PRICING_METHODS)
    extension_key = serializers.CharField(max_length=150, required=False, allow_blank=True)
    markup_percentage = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    margin_range_min = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    margin_range_max = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    parameters = serializers.JSONField(required=False)
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)
    documentation = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        errors = {}
        if attrs.get("source_company_id") == attrs.get("target_company_id"):
            errors["target_company_id"] = "Must differ from source company."
        if attrs.get("effective_to") and attrs["effective_to"] < attrs["effective_from"]:
            errors["effective_to"] = "Must not precede effective_from."
        if attrs.get("margin_range_min") is not None and attrs.get("margin_range_max") is not None and attrs["margin_range_min"] > attrs["margin_range_max"]:
            errors["margin_range_max"] = "Must not be less than margin_range_min."
        if attrs["pricing_method"] == "extension" and not attrs.get("extension_key", "").strip():
            errors["extension_key"] = "Required for extension pricing."
        if attrs["pricing_method"] != "extension" and attrs.get("extension_key"):
            errors["extension_key"] = "Allowed only for extension pricing."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class TransferPricingRuleCreateSerializer(_TransferRuleFields):
    pass


class TransferPricingRuleVersionSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255, required=False)
    product_category = serializers.CharField(max_length=100, required=False)
    pricing_method = serializers.ChoiceField(choices=PRICING_METHODS, required=False)
    extension_key = serializers.CharField(max_length=150, required=False, allow_blank=True)
    markup_percentage = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    margin_range_min = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    margin_range_max = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, allow_null=True)
    parameters = serializers.JSONField(required=False)
    effective_from = serializers.DateField(required=False)
    effective_to = serializers.DateField(required=False, allow_null=True)
    documentation = serializers.CharField(required=False, allow_blank=True)


class TransferPriceCalculateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    source_company_id = serializers.UUIDField()
    target_company_id = serializers.UUIDField()
    product_category = serializers.CharField(max_length=100)
    transaction_type = serializers.ChoiceField(choices=TRANSACTION_TYPES)
    effective_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=Decimal("0.0001"))
    currency = serializers.CharField(min_length=3, max_length=3)
    rule_id = serializers.UUIDField(required=False, allow_null=True)
    parameters = serializers.JSONField(required=False)


class TransferPriceResultSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=19, decimal_places=4)
    rule_id = serializers.UUIDField(allow_null=True)
    rule_version = serializers.IntegerField(allow_null=True)
    pricing_method = serializers.CharField()
    formula = serializers.CharField()
    rounding_mode = serializers.CharField()
    precision = serializers.IntegerField(min_value=0, max_value=8)
    evidence = serializers.DictField()


class RulePreviewSerializer(TransferPriceCalculateSerializer):
    scenarios = serializers.ListField(child=serializers.DictField(), allow_empty=False, max_length=100)


class ConfigurationVersionSerializer(serializers.ModelSerializer):
    allowed_commands = serializers.SerializerMethodField()
    denial_reasons = serializers.SerializerMethodField()

    class Meta:
        model = MultiCompanyConfigurationVersion
        fields = (
            "id", "environment", "version", "status", "schema_version", "settings",
            "change_summary", "supersedes", "activated_by", "activated_at", "created_by",
            "correlation_id", "created_at", "allowed_commands", "denial_reasons",
        )
        read_only_fields = fields

    def get_allowed_commands(self, instance: Any) -> list[str]:
        explicit = getattr(instance, "allowed_commands", None)
        if explicit is not None:
            return list(explicit)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        candidates = {
            "draft": {
                "update": "multi_company.configuration:write",
                "validate": "multi_company.configuration:write",
                "preview": "multi_company.configuration:write",
                "activate": "multi_company.configuration:activate",
            },
            "active": {"export": "multi_company.configuration:export"},
            "superseded": {"rollback": "multi_company.configuration:rollback", "export": "multi_company.configuration:export"},
            "rolled_back": {"rollback": "multi_company.configuration:rollback", "export": "multi_company.configuration:export"},
        }.get(instance.status, {})
        return sorted(command for command, permission in candidates.items() if user is not None and user.has_perm(permission))

    def get_denial_reasons(self, instance: Any) -> dict[str, str]:
        explicit = getattr(instance, "denial_reasons", None)
        if explicit is not None:
            return dict(explicit)
        all_commands = {"update", "validate", "preview", "activate", "rollback", "export"}
        allowed = set(self.get_allowed_commands(instance))
        state_candidates = {
            "draft": {"update", "validate", "preview", "activate"},
            "active": {"export"},
            "superseded": {"rollback", "export"},
            "rolled_back": {"rollback", "export"},
        }.get(instance.status, set())
        return {command: "permission_denied" if command in state_candidates else "state_not_allowed" for command in sorted(all_commands - allowed)}


class ConfigurationDraftSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    environment = serializers.ChoiceField(choices=ENVIRONMENTS)
    schema_version = serializers.CharField(max_length=20)
    settings = serializers.JSONField()
    change_summary = serializers.CharField(max_length=4000)
    expected_version = serializers.IntegerField(min_value=1, required=False)


class ConfigurationPreviewSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    changed_keys = serializers.ListField(child=serializers.CharField())
    affected_companies = serializers.IntegerField(min_value=0)
    affected_draft_transactions = serializers.IntegerField(min_value=0)
    warnings = serializers.ListField(child=serializers.CharField())


class ConfigurationImportSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    document = serializers.JSONField()
    environment = serializers.ChoiceField(choices=ENVIRONMENTS, required=False)
    change_summary = serializers.CharField(max_length=4000, required=False)


class ConfigurationRollbackSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    environment = serializers.ChoiceField(choices=ENVIRONMENTS)
    change_summary = serializers.CharField(max_length=4000)


class AsyncJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = AsyncJob
        fields = (
            "id", "command", "status", "attempts", "result", "error_message",
            "correlation_id", "started_at", "completed_at", "created_at", "updated_at",
        )
        read_only_fields = fields


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unhealthy"))
    checked_at = serializers.DateTimeField()
    checks = serializers.DictField(child=serializers.CharField())


class ExtensionCatalogEntrySerializer(serializers.Serializer):
    key = serializers.CharField()
    version = serializers.CharField()
    spi_version = serializers.CharField()
    installed = serializers.BooleanField()
    entitled = serializers.BooleanField()
    feature_enabled = serializers.BooleanField()
    access_allowed = serializers.BooleanField()
    compatible = serializers.BooleanField()
    healthy = serializers.BooleanField()
    available = serializers.BooleanField()
    locked = serializers.BooleanField()
    unavailable_reason = serializers.CharField(allow_blank=True)


class CompanyV1CompatibilitySerializer(serializers.ModelSerializer):
    """Deprecated v1 shape; ownership and activation remain server-controlled."""

    class Meta:
        model = Company
        fields = (
            "id", "tenant_id", "company_code", "company_name", "legal_name",
            "tax_id", "address", "is_active", "created_at", "updated_at",
        )
        read_only_fields = ("id", "tenant_id", "is_active", "created_at", "updated_at")
        extra_kwargs = {
            # These fields were optional in the published v1 contract. The
            # compatibility service derives legal_name from company_name.
            "legal_name": {"required": False, "allow_blank": True},
            "tax_id": {"required": False, "allow_blank": True},
            "address": {"required": False, "allow_blank": True},
        }


# Import compatibility for integrations that used the scaffold serializer name.
# The alias points to the deliberately restricted v1 contract, not to an
# unrestricted all-fields ModelSerializer.
CompanySerializer = CompanyV1CompatibilitySerializer


__all__ = [name for name in globals() if name.endswith("Serializer")]
