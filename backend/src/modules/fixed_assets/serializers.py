"""Explicit request and response serializers for fixed-assets API v2.

Request serializers validate transport shape only. They intentionally do not
implement ``create`` or ``update``: every mutation is owned by ``services.py``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from django.utils import timezone
from rest_framework import serializers

DEPRECIATION_METHODS = (
    "straight_line",
    "declining_balance",
    "units_of_production",
)
ASSET_STATUSES = ("draft", "active", "fully_depreciated", "disposed")
SCHEDULE_STATUSES = ("draft", "calculated", "active", "completed", "superseded")
LINE_STATUSES = ("planned", "posting", "posted", "failed", "void")
TRANSACTION_TYPES = ("capitalization", "depreciation", "transfer", "impairment", "disposal")
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled", "timed_out", "retrying")

SERVER_OWNED_FIELDS = frozenset(
    {
        "tenant_id",
        "status",
        "transition_history",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "actor_id",
        "correlation_id",
        "accumulated_depreciation",
        "accumulated_impairment",
        "net_book_value",
        "disposal_date",
        "disposal_proceeds",
        "disposal_gain_loss",
        "journal_entry_id",
        "posting_job_id",
        "posted_at",
        "posting_error_code",
        "calculated_at",
        "activated_at",
        "completed_at",
        "superseded_by",
    }
)


class ServiceRequestSerializer(serializers.Serializer):
    """Reject ownership/audit spoofing and forbid serializer persistence."""

    allowed_server_fields: frozenset[str] = frozenset()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        submitted = set(self.initial_data) if isinstance(self.initial_data, Mapping) else set()
        forbidden = sorted(submitted & (SERVER_OWNED_FIELDS - self.allowed_server_fields))
        if forbidden:
            raise serializers.ValidationError({name: "This field is server controlled." for name in forbidden})
        return attrs

    def create(self, validated_data: dict[str, Any]) -> object:
        del validated_data
        raise NotImplementedError("Fixed-asset mutations must use the service layer.")

    def update(self, instance: object, validated_data: dict[str, Any]) -> object:
        del instance, validated_data
        raise NotImplementedError("Fixed-asset mutations must use the service layer.")


class UppercaseCharField(serializers.CharField):
    """Normalize identifier-like text before it reaches a service."""

    def to_internal_value(self, data: object) -> str:
        return super().to_internal_value(data).strip().upper()


def MoneyField(**kwargs: Any) -> serializers.DecimalField:  # noqa: N802
    return serializers.DecimalField(max_digits=15, decimal_places=2, coerce_to_string=True, **kwargs)


def RateField(**kwargs: Any) -> serializers.DecimalField:  # noqa: N802
    return serializers.DecimalField(max_digits=7, decimal_places=4, coerce_to_string=True, **kwargs)


def UnitsField(**kwargs: Any) -> serializers.DecimalField:  # noqa: N802
    return serializers.DecimalField(max_digits=18, decimal_places=4, coerce_to_string=True, **kwargs)


class CategorySummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    default_depreciation_method = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


class CategoryListSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    default_depreciation_method = serializers.CharField(read_only=True)
    default_useful_life_months = serializers.IntegerField(read_only=True)
    default_residual_value_percent = MoneyField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    version = serializers.IntegerField(read_only=True, required=False)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class CategoryDetailSerializer(CategoryListSerializer):
    default_declining_balance_rate = RateField(read_only=True, allow_null=True)
    asset_account_id = serializers.UUIDField(read_only=True, allow_null=True)
    accumulated_depreciation_account_id = serializers.UUIDField(read_only=True, allow_null=True)
    depreciation_expense_account_id = serializers.UUIDField(read_only=True, allow_null=True)
    impairment_loss_account_id = serializers.UUIDField(read_only=True, allow_null=True)
    disposal_gain_account_id = serializers.UUIDField(read_only=True, allow_null=True)
    disposal_loss_account_id = serializers.UUIDField(read_only=True, allow_null=True)
    allowed_commands = serializers.SerializerMethodField()
    denial_reasons = serializers.SerializerMethodField()

    def get_allowed_commands(self, obj: object) -> list[str]:
        commands = ["update"]
        if bool(getattr(obj, "is_active", False)):
            commands.append("deactivate")
        return commands

    def get_denial_reasons(self, obj: object) -> dict[str, str]:
        if bool(getattr(obj, "is_active", False)):
            return {}
        return {"deactivate": "CATEGORY_ALREADY_INACTIVE"}


class CategoryCreateSerializer(ServiceRequestSerializer):
    code = UppercaseCharField(max_length=30)
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True)
    default_depreciation_method = serializers.ChoiceField(choices=DEPRECIATION_METHODS)
    default_useful_life_months = serializers.IntegerField(min_value=1)
    default_residual_value_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0.00"), max_value=Decimal("100.00")
    )
    default_declining_balance_rate = RateField(required=False, allow_null=True, min_value=Decimal("0.0001"))
    asset_account_id = serializers.UUIDField(required=False, allow_null=True)
    accumulated_depreciation_account_id = serializers.UUIDField(required=False, allow_null=True)
    depreciation_expense_account_id = serializers.UUIDField(required=False, allow_null=True)
    impairment_loss_account_id = serializers.UUIDField(required=False, allow_null=True)
    disposal_gain_account_id = serializers.UUIDField(required=False, allow_null=True)
    disposal_loss_account_id = serializers.UUIDField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        method = attrs.get("default_depreciation_method")
        rate = attrs.get("default_declining_balance_rate")
        if method == "declining_balance" and rate is None:
            raise serializers.ValidationError(
                {"default_declining_balance_rate": "A declining-balance rate is required for this method."}
            )
        if method != "declining_balance" and rate is not None:
            raise serializers.ValidationError(
                {"default_declining_balance_rate": "A declining-balance rate is only valid for that method."}
            )
        return attrs


class CategoryUpdateSerializer(CategoryCreateSerializer):
    code = UppercaseCharField(max_length=30, required=False)
    name = serializers.CharField(max_length=120, required=False)
    default_depreciation_method = serializers.ChoiceField(choices=DEPRECIATION_METHODS, required=False)
    default_useful_life_months = serializers.IntegerField(min_value=1, required=False)
    default_residual_value_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.00"),
        max_value=Decimal("100.00"),
        required=False,
    )
    is_active = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1)


class AssetListSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    asset_code = serializers.CharField(read_only=True)
    asset_name = serializers.CharField(read_only=True)
    category = CategorySummarySerializer(read_only=True)
    purchase_date = serializers.DateField(read_only=True)
    purchase_cost = MoneyField(read_only=True)
    currency = serializers.CharField(read_only=True)
    net_book_value = MoneyField(read_only=True)
    depreciation_method = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    location = serializers.CharField(read_only=True)
    cost_center = serializers.CharField(read_only=True)
    capitalization_date = serializers.DateField(read_only=True, allow_null=True)
    next_depreciation_date = serializers.DateField(read_only=True, allow_null=True, required=False)
    as_of = serializers.SerializerMethodField()
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_as_of(self, obj: object) -> str:
        del obj
        return timezone.localdate().isoformat()


class AssetSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    asset_code = serializers.CharField(read_only=True)
    asset_name = serializers.CharField(read_only=True)
    currency = serializers.CharField(read_only=True)


class BalanceReconciliationSerializer(serializers.Serializer):
    purchase_cost = MoneyField(read_only=True)
    accumulated_depreciation = MoneyField(read_only=True)
    accumulated_impairment = MoneyField(read_only=True)
    calculated_net_book_value = MoneyField(read_only=True)
    reported_net_book_value = MoneyField(read_only=True)
    reconciled = serializers.BooleanField(read_only=True)


class ScheduleSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    schedule_number = serializers.CharField(read_only=True)
    revision = serializers.IntegerField(read_only=True)
    method = serializers.CharField(read_only=True)
    start_date = serializers.DateField(read_only=True)
    end_date = serializers.DateField(read_only=True)
    status = serializers.CharField(read_only=True)


class AssetDetailSerializer(AssetListSerializer):
    description = serializers.CharField(read_only=True)
    residual_value = MoneyField(read_only=True)
    depreciation_start_date = serializers.DateField(read_only=True, allow_null=True)
    useful_life_months = serializers.IntegerField(read_only=True)
    declining_balance_rate = RateField(read_only=True, allow_null=True)
    expected_total_units = UnitsField(read_only=True, allow_null=True)
    accumulated_depreciation = MoneyField(read_only=True)
    accumulated_impairment = MoneyField(read_only=True)
    disposal_date = serializers.DateField(read_only=True, allow_null=True)
    disposal_proceeds = MoneyField(read_only=True, allow_null=True)
    disposal_gain_loss = MoneyField(read_only=True, allow_null=True)
    transition_history = serializers.JSONField(read_only=True)
    created_by = serializers.CharField(read_only=True)
    updated_by = serializers.CharField(read_only=True)
    active_schedule = serializers.SerializerMethodField()
    allowed_commands = serializers.SerializerMethodField()
    denial_reasons = serializers.SerializerMethodField()
    balance_reconciliation = serializers.SerializerMethodField()

    def get_active_schedule(self, obj: object) -> object | None:
        prefetched = getattr(obj, "prefetched_active_schedules", None)
        if prefetched is not None:
            schedule = prefetched[0] if prefetched else None
        else:
            manager = getattr(obj, "depreciation_schedules", None)
            schedule = manager.filter(status="active").first() if manager is not None else None
        return ScheduleSummarySerializer(schedule).data if schedule is not None else None

    def get_allowed_commands(self, obj: object) -> list[str]:
        state = str(getattr(obj, "status", ""))
        if state == "draft":
            return ["update", "delete", "capitalize"]
        if state == "active":
            return ["transfer", "impair", "dispose"]
        if state == "fully_depreciated":
            return ["transfer", "dispose"]
        return []

    def get_denial_reasons(self, obj: object) -> dict[str, str]:
        allowed = set(self.get_allowed_commands(obj))
        candidates = ("update", "delete", "capitalize", "transfer", "impair", "dispose")
        state = str(getattr(obj, "status", "unknown")).upper()
        return {command: f"ASSET_STATE_{state}" for command in candidates if command not in allowed}

    def get_balance_reconciliation(self, obj: object) -> dict[str, object]:
        cost = Decimal(getattr(obj, "purchase_cost", 0))
        depreciation = Decimal(getattr(obj, "accumulated_depreciation", 0))
        impairment = Decimal(getattr(obj, "accumulated_impairment", 0))
        reported = Decimal(getattr(obj, "net_book_value", 0))
        calculated = cost - depreciation - impairment
        return {
            "purchase_cost": cost,
            "accumulated_depreciation": depreciation,
            "accumulated_impairment": impairment,
            "calculated_net_book_value": calculated,
            "reported_net_book_value": reported,
            "reconciled": calculated == reported,
        }


class AssetCreateSerializer(ServiceRequestSerializer):
    asset_code = UppercaseCharField(max_length=50)
    asset_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.UUIDField()
    purchase_date = serializers.DateField()
    purchase_cost = MoneyField(min_value=Decimal("0.01"))
    currency = UppercaseCharField(min_length=3, max_length=3)
    residual_value = MoneyField(required=False, min_value=Decimal("0.00"))
    depreciation_method = serializers.ChoiceField(choices=DEPRECIATION_METHODS, required=False)
    useful_life_months = serializers.IntegerField(min_value=1, required=False)
    declining_balance_rate = RateField(required=False, allow_null=True, min_value=Decimal("0.0001"))
    expected_total_units = UnitsField(required=False, allow_null=True, min_value=Decimal("0.0001"))
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    cost_center = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs.get("residual_value", Decimal("0")) > attrs["purchase_cost"]:
            raise serializers.ValidationError({"residual_value": "Residual value cannot exceed purchase cost."})
        method = attrs.get("depreciation_method")
        if method == "declining_balance" and attrs.get("declining_balance_rate") is None:
            raise serializers.ValidationError({"declining_balance_rate": "This method requires a rate."})
        if method == "units_of_production" and attrs.get("expected_total_units") is None:
            raise serializers.ValidationError({"expected_total_units": "This method requires expected units."})
        return attrs


class AssetDraftUpdateSerializer(ServiceRequestSerializer):
    asset_code = UppercaseCharField(max_length=50, required=False)
    asset_name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    category_id = serializers.UUIDField(required=False)
    purchase_date = serializers.DateField(required=False)
    purchase_cost = MoneyField(required=False, min_value=Decimal("0.01"))
    currency = UppercaseCharField(min_length=3, max_length=3, required=False)
    residual_value = MoneyField(required=False, min_value=Decimal("0.00"))
    depreciation_method = serializers.ChoiceField(choices=DEPRECIATION_METHODS, required=False)
    useful_life_months = serializers.IntegerField(min_value=1, required=False)
    declining_balance_rate = RateField(required=False, allow_null=True, min_value=Decimal("0.0001"))
    expected_total_units = UnitsField(required=False, allow_null=True, min_value=Decimal("0.0001"))
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    cost_center = serializers.CharField(max_length=100, required=False, allow_blank=True)
    expected_version = serializers.IntegerField(min_value=1)


class CapitalizeCommandSerializer(ServiceRequestSerializer):
    effective_date = serializers.DateField()
    depreciation_start_date = serializers.DateField(required=False)
    expected_version = serializers.IntegerField(min_value=1)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        start = attrs.get("depreciation_start_date")
        if start is not None and start < attrs["effective_date"]:
            raise serializers.ValidationError(
                {"depreciation_start_date": "Depreciation cannot start before capitalization."}
            )
        return attrs


class TransferCommandSerializer(ServiceRequestSerializer):
    effective_date = serializers.DateField()
    to_location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    to_cost_center = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if "to_location" not in attrs and "to_cost_center" not in attrs:
            raise serializers.ValidationError("Provide a destination location or cost center.")
        return attrs


class ImpairmentCommandSerializer(ServiceRequestSerializer):
    effective_date = serializers.DateField()
    recoverable_amount = MoneyField(min_value=Decimal("0.00"))
    reason = serializers.CharField(max_length=2000)


class DisposalCommandSerializer(ServiceRequestSerializer):
    effective_date = serializers.DateField()
    proceeds = MoneyField(min_value=Decimal("0.00"))
    reason = serializers.CharField(max_length=2000)


class ScheduleListSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    asset_id = serializers.UUIDField(read_only=True)
    asset = AssetSummarySerializer(read_only=True)
    schedule_number = serializers.CharField(read_only=True)
    revision = serializers.IntegerField(read_only=True)
    method = serializers.CharField(read_only=True)
    frequency = serializers.CharField(read_only=True)
    start_date = serializers.DateField(read_only=True)
    end_date = serializers.DateField(read_only=True)
    cost_basis = MoneyField(read_only=True)
    residual_value = MoneyField(read_only=True)
    depreciable_amount = MoneyField(read_only=True)
    total_planned_depreciation = MoneyField(read_only=True)
    status = serializers.CharField(read_only=True)
    version = serializers.IntegerField(read_only=True, required=False)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class ScheduleDetailSerializer(ScheduleListSerializer):
    declining_balance_rate = RateField(read_only=True, allow_null=True)
    expected_total_units = UnitsField(read_only=True, allow_null=True)
    calculated_at = serializers.DateTimeField(read_only=True, allow_null=True)
    activated_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    superseded_by = serializers.UUIDField(source="superseded_by_id", read_only=True, allow_null=True)
    transition_history = serializers.JSONField(read_only=True)
    created_by = serializers.CharField(read_only=True)
    updated_by = serializers.CharField(read_only=True)
    lines_url = serializers.SerializerMethodField()
    reconciliation = serializers.SerializerMethodField()
    allowed_commands = serializers.SerializerMethodField()
    denial_reasons = serializers.SerializerMethodField()

    def get_lines_url(self, obj: object) -> str:
        from rest_framework.reverse import reverse

        request = self.context.get("request")
        base_url = reverse("depreciation-line-list", request=request)
        return f"{base_url}?schedule_id={getattr(obj, 'id')}"

    def get_reconciliation(self, obj: object) -> dict[str, object]:
        prefetched = getattr(obj, "prefetched_lines", None)
        lines = list(prefetched) if prefetched is not None else list(getattr(obj, "lines").all())
        line_total = sum((Decimal(line.depreciation_amount) for line in lines), Decimal("0.00"))
        planned = Decimal(getattr(obj, "total_planned_depreciation", 0))
        return {
            "line_count": len(lines),
            "line_total": line_total,
            "schedule_total": planned,
            "difference": planned - line_total,
            "reconciled": line_total == planned,
        }

    def get_allowed_commands(self, obj: object) -> list[str]:
        state = str(getattr(obj, "status", ""))
        return {
            "draft": ["update", "delete", "calculate", "supersede"],
            "calculated": ["activate", "supersede"],
            "active": ["supersede"],
        }.get(state, [])

    def get_denial_reasons(self, obj: object) -> dict[str, str]:
        allowed = set(self.get_allowed_commands(obj))
        state = str(getattr(obj, "status", "unknown")).upper()
        return {
            command: f"SCHEDULE_STATE_{state}"
            for command in ("update", "delete", "calculate", "activate", "supersede")
            if command not in allowed
        }


class ScheduleCreateSerializer(ServiceRequestSerializer):
    asset_id = serializers.UUIDField()
    method = serializers.ChoiceField(choices=DEPRECIATION_METHODS, required=False)
    frequency = serializers.ChoiceField(choices=("monthly",), required=False, default="monthly")
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    cost_basis = MoneyField(required=False, min_value=Decimal("0.01"))
    residual_value = MoneyField(required=False, min_value=Decimal("0.00"))
    declining_balance_rate = RateField(required=False, allow_null=True, min_value=Decimal("0.0001"))
    expected_total_units = UnitsField(required=False, allow_null=True, min_value=Decimal("0.0001"))


class ScheduleUpdateSerializer(ServiceRequestSerializer):
    method = serializers.ChoiceField(choices=DEPRECIATION_METHODS, required=False)
    frequency = serializers.ChoiceField(choices=("monthly",), required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    cost_basis = MoneyField(required=False, min_value=Decimal("0.01"))
    residual_value = MoneyField(required=False, min_value=Decimal("0.00"))
    declining_balance_rate = RateField(required=False, allow_null=True, min_value=Decimal("0.0001"))
    expected_total_units = UnitsField(required=False, allow_null=True, min_value=Decimal("0.0001"))
    expected_version = serializers.IntegerField(min_value=1)


class UnitConsumptionSerializer(serializers.Serializer):
    period_start = serializers.DateField()
    units_consumed = UnitsField(min_value=Decimal("0.0000"))


class ScheduleCalculateSerializer(ServiceRequestSerializer):
    units_by_period = UnitConsumptionSerializer(many=True, required=False, default=list)


class ScheduleTransitionSerializer(ServiceRequestSerializer):
    transition_key = serializers.CharField(max_length=255)
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class DepreciationLineListSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    schedule_id = serializers.UUIDField(read_only=True)
    asset_id = serializers.UUIDField(read_only=True)
    currency = serializers.CharField(source="asset.currency", read_only=True)
    sequence = serializers.IntegerField(read_only=True)
    period_start = serializers.DateField(read_only=True)
    period_end = serializers.DateField(read_only=True)
    opening_net_book_value = MoneyField(read_only=True)
    depreciation_amount = MoneyField(read_only=True)
    accumulated_depreciation = MoneyField(read_only=True)
    closing_net_book_value = MoneyField(read_only=True)
    status = serializers.CharField(read_only=True)
    posted_at = serializers.DateTimeField(read_only=True, allow_null=True)
    allowed_commands = serializers.SerializerMethodField()
    denial_reasons = serializers.SerializerMethodField()

    def get_allowed_commands(self, obj: object) -> list[str]:
        state = str(getattr(obj, "status", ""))
        if state == "planned":
            return ["post"]
        if state == "failed":
            return ["retry"]
        return []

    def get_denial_reasons(self, obj: object) -> dict[str, str]:
        allowed = set(self.get_allowed_commands(obj))
        state = str(getattr(obj, "status", "unknown")).upper()
        return {command: f"LINE_STATE_{state}" for command in ("post", "retry") if command not in allowed}


class DepreciationLineDetailSerializer(DepreciationLineListSerializer):
    units_consumed = UnitsField(read_only=True, allow_null=True)
    journal_entry_id = serializers.UUIDField(read_only=True, allow_null=True)
    posting_job_id = serializers.UUIDField(read_only=True, allow_null=True)
    posting_error_code = serializers.CharField(read_only=True)
    transition_history = serializers.JSONField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class LinePostingSerializer(ServiceRequestSerializer):
    expected_asset_version = serializers.IntegerField(min_value=1, required=False)


class DuePostingSerializer(ServiceRequestSerializer):
    through_date = serializers.DateField()


class TransactionListSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    asset_id = serializers.UUIDField(read_only=True)
    asset = AssetSummarySerializer(read_only=True)
    transaction_type = serializers.CharField(read_only=True)
    effective_date = serializers.DateField(read_only=True)
    amount = MoneyField(read_only=True)
    currency = serializers.CharField(read_only=True)
    opening_net_book_value = MoneyField(read_only=True)
    closing_net_book_value = MoneyField(read_only=True)
    actor_id = serializers.CharField(read_only=True)
    correlation_id = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class TransactionDetailSerializer(TransactionListSerializer):
    from_location = serializers.CharField(read_only=True)
    to_location = serializers.CharField(read_only=True)
    from_cost_center = serializers.CharField(read_only=True)
    to_cost_center = serializers.CharField(read_only=True)
    journal_entry_id = serializers.UUIDField(read_only=True, allow_null=True)
    source_type = serializers.CharField(read_only=True)
    source_id = serializers.UUIDField(read_only=True, allow_null=True)
    idempotency_key = serializers.CharField(read_only=True)
    metadata = serializers.JSONField(read_only=True)


class JobStatusSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    status = serializers.ChoiceField(choices=JOB_STATUSES, read_only=True)
    operation = serializers.SerializerMethodField()
    attempts = serializers.IntegerField(read_only=True)
    progress_percent = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()
    error_code = serializers.SerializerMethodField()
    correlation_id = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)

    def get_operation(self, obj: object) -> str:
        command = str(getattr(obj, "command", ""))
        return command.rsplit(".", maxsplit=1)[-1]

    def get_result(self, obj: object) -> dict[str, object] | None:
        result = getattr(obj, "result", None)
        if not isinstance(result, Mapping):
            return None
        safe_fields = (
            "line_id",
            "posted_line_ids",
            "failed_line_ids",
            "posted_count",
            "failed_count",
            "progress_percent",
            "status",
        )
        return {name: result[name] for name in safe_fields if name in result}

    def get_error_code(self, obj: object) -> str | None:
        result = getattr(obj, "result", None)
        if isinstance(result, Mapping) and isinstance(result.get("error_code"), str):
            return result["error_code"]
        return "POSTING_FAILED" if str(getattr(obj, "status", "")) == "failed" else None

    def get_progress_percent(self, obj: object) -> int | None:
        result = getattr(obj, "result", None)
        if isinstance(result, Mapping):
            candidate = result.get("progress_percent")
            if isinstance(candidate, int) and 0 <= candidate <= 100:
                return candidate
        if str(getattr(obj, "status", "")) == "succeeded":
            return 100
        return None


class AssetCountsSerializer(serializers.Serializer):
    draft = serializers.IntegerField(min_value=0)
    active = serializers.IntegerField(min_value=0)
    fully_depreciated = serializers.IntegerField(min_value=0)
    disposed = serializers.IntegerField(min_value=0)
    total = serializers.IntegerField(min_value=0)


class CurrencyAmountSerializer(serializers.Serializer):
    currency = serializers.CharField(min_length=3, max_length=3)
    amount = MoneyField()


class DashboardSerializer(serializers.Serializer):
    asset_counts = AssetCountsSerializer()
    book_value_by_currency = CurrencyAmountSerializer(many=True)
    current_period_depreciation_by_currency = CurrencyAmountSerializer(many=True)
    pending_postings = serializers.IntegerField(min_value=0)
    failed_postings = serializers.IntegerField(min_value=0)
    impairments = serializers.IntegerField(min_value=0)
    disposals = serializers.IntegerField(min_value=0)


class HealthCheckSerializer(serializers.Serializer):
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unhealthy"))
    code = serializers.CharField(required=False)


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unhealthy"))
    checks = HealthCheckSerializer(many=True)


class PreviewMessageSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()


class PreviewJournalEntrySerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=("debit", "credit"))
    account_id = serializers.UUIDField(allow_null=True)
    amount = MoneyField()
    currency = serializers.CharField(min_length=3, max_length=3)
    description = serializers.CharField(required=False, allow_blank=True)


class PreviewJournalEffectSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("ready", "unavailable", "not_required"))
    entries = PreviewJournalEntrySerializer(many=True)


class PreviewScheduleEffectSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("unchanged", "created", "superseded", "completed", "voided"))
    description = serializers.CharField()


class LifecyclePreviewSerializer(serializers.Serializer):
    command = serializers.ChoiceField(choices=("capitalize", "transfer", "impair", "dispose"))
    asset_version = serializers.IntegerField(min_value=1)
    as_of = serializers.DateField()
    opening_net_book_value = MoneyField()
    closing_net_book_value = MoneyField()
    currency = serializers.CharField(min_length=3, max_length=3)
    warnings = PreviewMessageSerializer(many=True)
    blockers = PreviewMessageSerializer(many=True)
    journal_effect = PreviewJournalEffectSerializer()
    schedule_effect = PreviewScheduleEffectSerializer()


class LegacyFixedAssetSerializer(serializers.Serializer):
    """Read adapter preserving the original API v1 response shape."""

    id = serializers.UUIDField(read_only=True)
    tenant_id = serializers.UUIDField(read_only=True)
    asset_code = serializers.CharField(read_only=True)
    asset_name = serializers.CharField(read_only=True)
    asset_category = serializers.CharField(source="category.code", read_only=True)
    purchase_date = serializers.DateField(read_only=True)
    purchase_cost = MoneyField(read_only=True)
    current_value = MoneyField(source="net_book_value", read_only=True)
    depreciation_method = serializers.CharField(read_only=True)
    useful_life_years = serializers.SerializerMethodField()
    location = serializers.CharField(read_only=True)
    is_active = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_useful_life_years(self, obj: object) -> int | None:
        months = getattr(obj, "useful_life_months", None)
        return int(months) // 12 if months is not None else None

    def get_is_active(self, obj: object) -> bool:
        return str(getattr(obj, "status", "")) != "disposed"


class LegacyFixedAssetWriteSerializer(ServiceRequestSerializer):
    asset_code = UppercaseCharField(max_length=50, required=False)
    asset_name = serializers.CharField(max_length=255, required=False)
    asset_category = UppercaseCharField(max_length=100, required=False)
    purchase_date = serializers.DateField(required=False)
    purchase_cost = MoneyField(required=False, min_value=Decimal("0.01"))
    depreciation_method = serializers.ChoiceField(choices=DEPRECIATION_METHODS, required=False)
    useful_life_years = serializers.IntegerField(min_value=1, required=False)
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)


# Historical import retained for callers that imported the v1 serializer name.
FixedAssetSerializer = LegacyFixedAssetSerializer


__all__ = [name for name in globals() if name.endswith("Serializer")]
