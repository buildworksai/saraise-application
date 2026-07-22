"""Strict transport contracts for the governed budget-management API.

Command serializers deliberately do not implement persistence: all mutations
are executed by :mod:`services` under transaction locks.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import Budget, BudgetApproval, BudgetLine, BudgetTransition, VarianceAlert

BUDGET_STATUSES = ("draft", "pending_approval", "approved", "rejected", "revision", "closed")
BUDGET_TYPES = ("operating", "capital", "project", "departmental")
PERIOD_TYPES = ("annual", "monthly", "quarterly")
ALERT_TYPES = ("over_budget", "approaching_limit", "underspend")

SERVER_OWNED_FIELDS = frozenset(
    {
        "id", "tenant_id", "status", "total_budget", "variance", "committed_amount",
        "actual_amount", "actuals_as_of", "source", "account_name", "created_at",
        "updated_at", "created_by", "updated_by", "deleted_at", "deleted_by",
        "is_deleted", "submitted_at", "submitted_by", "approved_at", "approved_by",
        "rejected_at", "rejected_by", "rejection_reason", "transition_state",
    }
)


class ServiceRequestSerializer(serializers.Serializer):
    """Forbid authority/audit spoofing and serializer-driven persistence."""

    allowed_server_fields: frozenset[str] = frozenset()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        submitted = set(self.initial_data) if isinstance(self.initial_data, Mapping) else set()
        forbidden = sorted(submitted & (SERVER_OWNED_FIELDS - self.allowed_server_fields))
        if forbidden:
            raise serializers.ValidationError({field: "This field is controlled by the server." for field in forbidden})
        return attrs

    def create(self, validated_data: dict[str, Any]) -> object:
        del validated_data
        raise NotImplementedError("Budget mutations must use services.py")

    def update(self, instance: object, validated_data: dict[str, Any]) -> object:
        del instance, validated_data
        raise NotImplementedError("Budget mutations must use services.py")


class TrimmedCharField(serializers.CharField):
    def to_internal_value(self, data: object) -> str:
        return super().to_internal_value(data).strip()


class UppercaseCharField(TrimmedCharField):
    def to_internal_value(self, data: object) -> str:
        return super().to_internal_value(data).upper()


class StrictDecimalField(serializers.DecimalField):
    """Accept decimal strings/integers only and never silently round."""

    def to_internal_value(self, data: object) -> Decimal:
        if isinstance(data, (float, bool)):
            self.fail("invalid")
        value = super().to_internal_value(data)
        if value.as_tuple().exponent < -self.decimal_places:
            self.fail("max_decimal_places", max_decimal_places=self.decimal_places)
        return value.quantize(Decimal("0.01"))


def MoneyField(**kwargs: Any) -> StrictDecimalField:  # noqa: N802
    return StrictDecimalField(max_digits=15, decimal_places=2, coerce_to_string=True, **kwargs)


class BudgetLineReadSerializer(serializers.ModelSerializer):
    budget_id = serializers.UUIDField(read_only=True)
    budget_amount = MoneyField(read_only=True)
    committed_amount = MoneyField(read_only=True)
    actual_amount = MoneyField(read_only=True)
    variance = MoneyField(read_only=True)

    class Meta:
        model = BudgetLine
        fields = (
            "id", "budget_id", "account_id", "account_code", "account_name", "period_type",
            "period_number", "budget_amount", "committed_amount", "actual_amount", "variance",
            "actuals_as_of", "source", "created_at", "updated_at",
        )


class BudgetApprovalSerializer(serializers.ModelSerializer):
    budget_id = serializers.UUIDField(read_only=True)
    status = serializers.SerializerMethodField()
    decision_at = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()
    rejection_reason = serializers.SerializerMethodField()

    class Meta:
        model = BudgetApproval
        fields = (
            "id", "budget_id", "workflow_request_id", "approver_id", "approval_level", "status",
            "decision_at", "notes", "rejection_reason", "created_by", "created_at",
        )
        read_only_fields = fields

    @staticmethod
    def _decision(obj: BudgetApproval) -> object | None:
        decisions = list(obj.decisions.all())
        return decisions[0] if decisions else None

    def get_status(self, obj: BudgetApproval) -> str:
        decision = self._decision(obj)
        return str(getattr(decision, "status", "pending"))

    def get_decision_at(self, obj: BudgetApproval) -> object | None:
        return getattr(self._decision(obj), "decided_at", None)

    def get_notes(self, obj: BudgetApproval) -> str:
        return str(getattr(self._decision(obj), "notes", obj.notes))

    def get_rejection_reason(self, obj: BudgetApproval) -> str:
        return str(getattr(self._decision(obj), "rejection_reason", ""))


class BudgetTransitionSerializer(serializers.ModelSerializer):
    budget_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = BudgetTransition
        fields = (
            "id", "budget_id", "transition_key", "command", "from_state", "to_state",
            "actor_id", "notes", "metadata", "occurred_at",
        )
        read_only_fields = fields


class VarianceAlertListSerializer(serializers.ModelSerializer):
    budget_id = serializers.UUIDField(read_only=True)
    budget_line_id = serializers.UUIDField(read_only=True)
    threshold_percentage = StrictDecimalField(max_digits=7, decimal_places=2, read_only=True)
    variance_percentage = StrictDecimalField(max_digits=9, decimal_places=2, read_only=True, allow_null=True)
    budget_amount = MoneyField(read_only=True)
    actual_amount = MoneyField(read_only=True)
    committed_amount = MoneyField(read_only=True)

    class Meta:
        model = VarianceAlert
        fields = (
            "id", "budget_id", "budget_line_id", "alert_type", "threshold_percentage",
            "variance_percentage", "budget_amount", "actual_amount", "committed_amount",
            "alert_date", "notification_status", "notification_job_id", "acknowledged_at",
            "acknowledged_by", "created_at",
        )


class VarianceAlertDetailSerializer(VarianceAlertListSerializer):
    pass


class BudgetListSerializer(serializers.ModelSerializer):
    total_budget = MoneyField(read_only=True)
    variance_indicator = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = (
            "id", "budget_code", "budget_name", "fiscal_year", "start_date", "end_date",
            "budget_type", "department_id", "project_id", "status", "currency", "budget_ceiling",
            "total_budget", "variance_indicator", "created_at", "updated_at",
        )

    def get_variance_indicator(self, obj: Budget) -> str:
        actual = sum((line.actual_amount for line in obj.lines.all() if not line.is_deleted), Decimal("0.00"))
        if actual > obj.total_budget:
            return "unfavorable"
        if actual < obj.total_budget:
            return "favorable"
        return "on_budget"


class BudgetDetailSerializer(BudgetListSerializer):
    lines = BudgetLineReadSerializer(many=True, read_only=True)
    approvals = BudgetApprovalSerializer(many=True, read_only=True)
    transitions = BudgetTransitionSerializer(many=True, read_only=True)
    variance_alerts = VarianceAlertListSerializer(many=True, read_only=True)
    allowed_commands = serializers.SerializerMethodField()
    variance_summary = serializers.SerializerMethodField()

    class Meta(BudgetListSerializer.Meta):
        fields = BudgetListSerializer.Meta.fields + (
            "submitted_at", "submitted_by", "approved_at", "approved_by", "rejected_at",
            "rejected_by", "rejection_reason", "lines", "approvals", "transitions",
            "variance_alerts", "allowed_commands", "variance_summary",
        )

    def get_allowed_commands(self, obj: Budget) -> list[str]:
        return {
            "draft": ["update", "delete", "allocations", "submit"],
            "revision": ["update", "allocations", "submit"],
            "pending_approval": ["approve", "reject"],
            "approved": ["close", "sync_actuals"],
            "rejected": ["revise"],
            "closed": ["sync_actuals"],
        }.get(obj.status, [])

    def get_variance_summary(self, obj: Budget) -> dict[str, str | None]:
        active = [line for line in obj.lines.all() if not line.is_deleted]
        actual = sum((line.actual_amount for line in active), Decimal("0.00"))
        committed = sum((line.committed_amount for line in active), Decimal("0.00"))
        variance = obj.total_budget - actual
        percentage = None if obj.total_budget == 0 else (variance / obj.total_budget * Decimal("100")).quantize(Decimal("0.01"))
        return {
            "budgeted": f"{obj.total_budget:.2f}", "committed": f"{committed:.2f}",
            "actual": f"{actual:.2f}", "variance": f"{variance:.2f}",
            "variance_percentage": None if percentage is None else f"{percentage:.2f}",
        }


class BudgetCreateSerializer(ServiceRequestSerializer):
    budget_code = UppercaseCharField(max_length=50)
    budget_name = TrimmedCharField(max_length=255)
    fiscal_year = serializers.IntegerField(min_value=1, max_value=9999)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    budget_type = serializers.ChoiceField(choices=BUDGET_TYPES)
    department_id = serializers.UUIDField(required=False, allow_null=True)
    project_id = serializers.UUIDField(required=False, allow_null=True)
    currency = UppercaseCharField(min_length=3, max_length=3)
    budget_ceiling = MoneyField(required=False, allow_null=True, min_value=Decimal("0.00"))


class BudgetUpdateSerializer(ServiceRequestSerializer):
    expected_updated_at = serializers.DateTimeField()
    budget_code = UppercaseCharField(max_length=50, required=False)
    budget_name = TrimmedCharField(max_length=255, required=False)
    fiscal_year = serializers.IntegerField(min_value=1, max_value=9999, required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    budget_type = serializers.ChoiceField(choices=BUDGET_TYPES, required=False)
    department_id = serializers.UUIDField(required=False, allow_null=True)
    project_id = serializers.UUIDField(required=False, allow_null=True)
    currency = UppercaseCharField(min_length=3, max_length=3, required=False)
    budget_ceiling = MoneyField(required=False, allow_null=True, min_value=Decimal("0.00"))


class BudgetDeleteSerializer(ServiceRequestSerializer):
    expected_updated_at = serializers.DateTimeField()


class BudgetLineCreateSerializer(ServiceRequestSerializer):
    budget_id = serializers.UUIDField()
    account_id = serializers.UUIDField(required=False, allow_null=True)
    account_code = UppercaseCharField(max_length=50)
    period_type = serializers.ChoiceField(choices=PERIOD_TYPES, default="annual")
    period_number = serializers.IntegerField(min_value=1, max_value=12, default=1)
    budget_amount = MoneyField(min_value=Decimal("0.00"))


class BudgetLineUpdateSerializer(ServiceRequestSerializer):
    expected_updated_at = serializers.DateTimeField()
    account_id = serializers.UUIDField(required=False, allow_null=True)
    account_code = UppercaseCharField(max_length=50, required=False)
    period_type = serializers.ChoiceField(choices=PERIOD_TYPES, required=False)
    period_number = serializers.IntegerField(min_value=1, max_value=12, required=False)
    budget_amount = MoneyField(required=False, min_value=Decimal("0.00"))


class AllocationInputSerializer(ServiceRequestSerializer):
    account_id = serializers.UUIDField(required=False, allow_null=True)
    account_code = UppercaseCharField(max_length=50)
    period_type = serializers.ChoiceField(choices=PERIOD_TYPES)
    period_number = serializers.IntegerField(min_value=1, max_value=12)
    budget_amount = MoneyField(min_value=Decimal("0.00"))


class AllocationReplaceSerializer(ServiceRequestSerializer):
    expected_updated_at = serializers.DateTimeField()
    allocations = AllocationInputSerializer(many=True, allow_empty=False)


class TransitionSerializer(ServiceRequestSerializer):
    notes = TrimmedCharField(required=False, allow_blank=True, max_length=2000)


class BudgetSubmitSerializer(TransitionSerializer):
    pass


class BudgetApproveSerializer(TransitionSerializer):
    pass


class BudgetRejectSerializer(ServiceRequestSerializer):
    reason = TrimmedCharField(allow_blank=False, max_length=2000)


class BudgetReviseSerializer(TransitionSerializer):
    pass


class BudgetCloseSerializer(ServiceRequestSerializer):
    pass


class BudgetAvailabilityRequestSerializer(ServiceRequestSerializer):
    account_code = UppercaseCharField(max_length=50)
    amount = MoneyField(min_value=Decimal("0.01"))
    period = serializers.DateField()
    budget_id = serializers.UUIDField(required=False, allow_null=True)


class BudgetAvailabilityResultSerializer(serializers.Serializer):
    allocated = MoneyField(read_only=True)
    committed = MoneyField(read_only=True)
    actual = MoneyField(read_only=True)
    available = MoneyField(read_only=True)
    deficit = MoneyField(read_only=True)
    sufficient = serializers.BooleanField(read_only=True)
    unbudgeted = serializers.BooleanField(read_only=True)
    currency = serializers.CharField(read_only=True, allow_null=True, required=False)


class VarianceLineSerializer(serializers.Serializer):
    budget_line_id = serializers.UUIDField(read_only=True)
    account_code = serializers.CharField(read_only=True)
    account_name = serializers.CharField(read_only=True)
    period_type = serializers.CharField(read_only=True)
    period_number = serializers.IntegerField(read_only=True)
    budgeted = MoneyField(read_only=True)
    committed = MoneyField(read_only=True)
    actual = MoneyField(read_only=True)
    variance = MoneyField(read_only=True)
    variance_percentage = StrictDecimalField(max_digits=9, decimal_places=2, read_only=True, allow_null=True)
    favorable = serializers.BooleanField(read_only=True)
    over_budget = serializers.BooleanField(read_only=True)
    threshold_exceeded = serializers.BooleanField(read_only=True)


class VarianceReportSerializer(serializers.Serializer):
    budget_id = serializers.UUIDField(read_only=True)
    currency = serializers.CharField(read_only=True)
    budgeted = MoneyField(read_only=True)
    committed = MoneyField(read_only=True)
    actual = MoneyField(read_only=True)
    variance = MoneyField(read_only=True)
    variance_percentage = StrictDecimalField(max_digits=9, decimal_places=2, read_only=True, allow_null=True)
    favorable = serializers.BooleanField(read_only=True)
    threshold_percentage = StrictDecimalField(max_digits=7, decimal_places=2, read_only=True)
    lines = VarianceLineSerializer(many=True, read_only=True)


class VarianceAlertGenerateSerializer(ServiceRequestSerializer):
    threshold_percentage = StrictDecimalField(max_digits=7, decimal_places=2, min_value=Decimal("0.00"))
    alert_type = serializers.ChoiceField(choices=ALERT_TYPES)


class VarianceAlertAcknowledgeSerializer(ServiceRequestSerializer):
    pass


class ActualsSyncRequestSerializer(ServiceRequestSerializer):
    pass


class AsyncJobSummarySerializer(serializers.ModelSerializer):
    job_type = serializers.CharField(source="command", read_only=True)

    class Meta:
        model = AsyncJob
        fields = (
            "id", "job_type", "command", "status", "idempotency_key", "correlation_id",
            "created_at", "updated_at",
        )
        read_only_fields = fields


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unhealthy"), read_only=True)
    dependencies = serializers.DictField(child=serializers.CharField(), read_only=True)
    checked_at = serializers.DateTimeField(read_only=True, required=False)


# Compatibility aliases for code that imported the partial v1 serializers.
BudgetSerializer = BudgetDetailSerializer
BudgetLineSerializer = BudgetLineReadSerializer
