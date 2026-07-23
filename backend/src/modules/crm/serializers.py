"""Strict API v2 serializers for CRM resources and commands."""

from __future__ import annotations

from datetime import date
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .configuration import DEFAULT_CRM_CONFIGURATION
from .models import (
    ISO_3166_ALPHA_2,
    ISO_4217_CODES,
    Account,
    AccountType,
    Activity,
    Contact,
    Lead,
    Opportunity,
    OpportunityStage,
    validate_metadata,
    validate_non_empty_string_array,
    validate_uuid_string_array,
)


class StrictInputMixin:
    """Reject rather than silently discard fields outside the declared DTO."""

    def to_internal_value(self, data: Any) -> Any:
        if not isinstance(data, dict):
            raise serializers.ValidationError({"non_field_errors": ["Expected a JSON object."]})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({field: ["Unknown field."] for field in sorted(unknown)})
        return super().to_internal_value(data)


class StrictModelSerializer(StrictInputMixin, serializers.ModelSerializer):
    pass


class StrictSerializer(StrictInputMixin, serializers.Serializer):
    pass


class CRMConfigurationWriteSerializer(StrictSerializer):
    environment = serializers.CharField(required=False)
    document = serializers.JSONField(required=False)
    feature_flags = serializers.JSONField(required=False)
    rollout = serializers.JSONField(required=False)


class CRMConfigurationRollbackSerializer(StrictSerializer):
    environment = serializers.CharField(required=False)
    version = serializers.IntegerField(min_value=1)


class CRMConfigurationImportSerializer(StrictSerializer):
    schema_version = serializers.IntegerField()
    module = serializers.CharField()
    configuration = serializers.JSONField()


PUBLIC_READ_FIELDS = ["id", "created_at", "updated_at", "version"]


class ExpectedVersionMixin:
    version = serializers.IntegerField(min_value=1, required=False, write_only=True)


def _metadata(value: object) -> object:
    try:
        validate_metadata(value)
    except Exception as exc:
        raise serializers.ValidationError("Metadata must be a JSON object of supported primitive values.") from exc
    return value


class LeadReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = [
            *PUBLIC_READ_FIELDS,
            "first_name",
            "last_name",
            "email",
            "phone",
            "company",
            "title",
            "score",
            "grade",
            "score_source",
            "score_explanation",
            "source",
            "campaign_id",
            "owner_id",
            "status",
            "converted_at",
            "converted_to_opportunity_id",
            "transition_history",
        ]


class LeadCreateSerializer(StrictModelSerializer):
    class Meta:
        model = Lead
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "company",
            "title",
            "source",
            "campaign_id",
            "owner_id",
            "metadata",
        ]
        extra_kwargs = {"metadata": {"validators": [_metadata]}}


class LeadUpdateSerializer(ExpectedVersionMixin, LeadCreateSerializer):
    class Meta(LeadCreateSerializer.Meta):
        fields = [*LeadCreateSerializer.Meta.fields, "version"]
        extra_kwargs = {field: {"required": False} for field in LeadCreateSerializer.Meta.fields}


class LeadTransitionSerializer(StrictSerializer):
    command = serializers.ChoiceField(choices=("contact", "qualify", "disqualify"))
    transition_key = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    expected_version = serializers.IntegerField(min_value=1)
    context = serializers.DictField(required=False, default=dict)


class LeadScoreRequestSerializer(StrictSerializer):
    async_execution = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(min_length=1, required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs.get("async_execution") and not attrs.get("idempotency_key"):
            raise serializers.ValidationError({"idempotency_key": "Required for durable asynchronous scoring."})
        return attrs


class LeadConvertSerializer(StrictSerializer):
    amount = serializers.DecimalField(
        max_digits=DEFAULT_CRM_CONFIGURATION["field_limits"]["opportunity_amount_digits"],
        decimal_places=DEFAULT_CRM_CONFIGURATION["field_limits"]["opportunity_amount_decimals"],
    )
    currency = serializers.ChoiceField(choices=sorted(ISO_4217_CODES), required=False)
    close_date = serializers.DateField()
    name = serializers.CharField(
        max_length=DEFAULT_CRM_CONFIGURATION["field_limits"]["opportunity_name"],
        required=False,
        allow_blank=False,
    )
    account_id = serializers.UUIDField(required=False)
    create_new_account = serializers.BooleanField(required=False, default=False)
    expected_version = serializers.IntegerField(min_value=1)
    transition_key = serializers.CharField(min_length=1, max_length=255)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs["close_date"] < timezone.localdate():
            raise serializers.ValidationError({"close_date": "Close date cannot be in the past."})
        if bool(attrs.get("account_id")) == bool(attrs.get("create_new_account")):
            raise serializers.ValidationError("Choose exactly one existing or new account decision.")
        attrs["currency"] = str(attrs["currency"]).upper()
        return attrs


class AccountReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            *PUBLIC_READ_FIELDS,
            "name",
            "website",
            "industry",
            "employees",
            "annual_revenue",
            "parent_account_id",
            "billing_street",
            "billing_city",
            "billing_state",
            "billing_postal_code",
            "billing_country",
            "owner_id",
            "account_type",
        ]


class AccountCreateSerializer(StrictModelSerializer):
    class Meta:
        model = Account
        fields = [
            "name",
            "website",
            "industry",
            "employees",
            "annual_revenue",
            "parent_account_id",
            "billing_street",
            "billing_city",
            "billing_state",
            "billing_postal_code",
            "billing_country",
            "owner_id",
            "account_type",
            "metadata",
        ]

    def validate_billing_country(self, value: str) -> str:
        normalized = value.upper()
        if normalized and normalized not in ISO_3166_ALPHA_2:
            raise serializers.ValidationError("Use an ISO 3166-1 alpha-2 country code.")
        return normalized


class AccountUpdateSerializer(ExpectedVersionMixin, AccountCreateSerializer):
    class Meta(AccountCreateSerializer.Meta):
        fields = [*AccountCreateSerializer.Meta.fields, "version"]
        extra_kwargs = {field: {"required": False} for field in AccountCreateSerializer.Meta.fields}


class AccountHierarchySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    account_type = serializers.ChoiceField(choices=AccountType.choices)
    children = serializers.ListField(child=serializers.DictField(), default=list)


class DuplicateAccountQuerySerializer(StrictSerializer):
    name = serializers.CharField(min_length=1, max_length=DEFAULT_CRM_CONFIGURATION["field_limits"]["account_name"])
    website = serializers.URLField(
        max_length=DEFAULT_CRM_CONFIGURATION["field_limits"]["account_name"],
        required=False,
        allow_blank=True,
    )


class ContactReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = [
            *PUBLIC_READ_FIELDS,
            "account_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "mobile",
            "title",
            "department",
            "linkedin",
            "twitter",
            "last_contacted_at",
            "engagement_score",
            "owner_id",
        ]


class ContactCreateSerializer(StrictModelSerializer):
    domain_override_reason = serializers.CharField(required=False, allow_blank=False, write_only=True)

    class Meta:
        model = Contact
        fields = [
            "account_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "mobile",
            "title",
            "department",
            "linkedin",
            "twitter",
            "owner_id",
            "metadata",
            "domain_override_reason",
        ]


class ContactUpdateSerializer(ExpectedVersionMixin, StrictModelSerializer):
    domain_override_reason = serializers.CharField(required=False, allow_blank=False, write_only=True)

    class Meta:
        model = Contact
        fields = [
            "account_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "mobile",
            "title",
            "department",
            "linkedin",
            "twitter",
            "owner_id",
            "metadata",
            "domain_override_reason",
            "version",
        ]
        extra_kwargs = {
            field: {"required": False} for field in fields if field not in {"version", "domain_override_reason"}
        }


class OpportunityReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Opportunity
        fields = [
            *PUBLIC_READ_FIELDS,
            "account_id",
            "primary_contact_id",
            "name",
            "description",
            "amount",
            "currency",
            "probability",
            "stage",
            "close_date",
            "product_ids",
            "competitors",
            "owner_id",
            "status",
            "closed_at",
            "loss_reason",
            "converted_to_order_id",
            "last_activity_at",
            "transition_history",
        ]


class OpportunityCreateSerializer(StrictModelSerializer):
    stage = serializers.ChoiceField(
        choices=tuple(
            (value, label)
            for value, label in OpportunityStage.choices
            if value not in {OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST}
        ),
        required=False,
    )

    class Meta:
        model = Opportunity
        fields = [
            "account_id",
            "primary_contact_id",
            "name",
            "description",
            "amount",
            "currency",
            "probability",
            "stage",
            "close_date",
            "product_ids",
            "competitors",
            "owner_id",
            "metadata",
        ]

    def validate_currency(self, value: str) -> str:
        normalized = value.upper()
        if normalized not in ISO_4217_CODES:
            raise serializers.ValidationError("Use an ISO 4217 currency code.")
        return normalized

    def validate_close_date(self, value: date) -> date:
        if value < timezone.localdate():
            raise serializers.ValidationError("Close date cannot be in the past.")
        return value

    def validate_product_ids(self, value: object) -> object:
        try:
            validate_uuid_string_array(value)
        except Exception as exc:
            raise serializers.ValidationError("Every product ID must be a UUID string.") from exc
        return value

    def validate_competitors(self, value: object) -> object:
        try:
            validate_non_empty_string_array(value)
        except Exception as exc:
            raise serializers.ValidationError("Competitors must be non-empty strings.") from exc
        return value


class OpportunityUpdateSerializer(ExpectedVersionMixin, StrictModelSerializer):
    class Meta:
        model = Opportunity
        fields = [
            "account_id",
            "primary_contact_id",
            "name",
            "description",
            "amount",
            "currency",
            "close_date",
            "product_ids",
            "competitors",
            "owner_id",
            "metadata",
            "version",
        ]
        extra_kwargs = {field: {"required": False} for field in fields if field != "version"}


class OpportunityStageTransitionSerializer(StrictSerializer):
    command = serializers.ChoiceField(
        choices=(
            "advance_to_qualification",
            "advance_to_needs_analysis",
            "advance_to_proposal",
            "advance_to_negotiation",
            "reopen_to_prospecting",
            "reopen_to_qualification",
            "reopen_to_needs_analysis",
            "reopen_to_proposal",
        )
    )
    transition_key = serializers.CharField(min_length=1, max_length=255)
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=False)


class CloseWonSerializer(StrictSerializer):
    transition_key = serializers.CharField(min_length=1, max_length=255)
    expected_version = serializers.IntegerField(min_value=1)
    confirmed = serializers.BooleanField()

    def validate_confirmed(self, value: bool) -> bool:
        if value is not True:
            raise serializers.ValidationError("Explicit confirmation is required.")
        return value


class CloseLostSerializer(StrictSerializer):
    loss_reason = serializers.CharField(min_length=1, trim_whitespace=True)
    transition_key = serializers.CharField(min_length=1, max_length=255)
    expected_version = serializers.IntegerField(min_value=1)


class ActivityReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = [
            *PUBLIC_READ_FIELDS,
            "activity_type",
            "related_to_type",
            "related_to_id",
            "subject",
            "description",
            "outcome",
            "due_date",
            "completed",
            "completed_at",
            "owner_id",
        ]


class ActivityCreateSerializer(StrictModelSerializer):
    class Meta:
        model = Activity
        fields = [
            "activity_type",
            "related_to_type",
            "related_to_id",
            "subject",
            "description",
            "outcome",
            "due_date",
            "owner_id",
            "metadata",
        ]


class ActivityUpdateSerializer(ExpectedVersionMixin, StrictModelSerializer):
    class Meta:
        model = Activity
        fields = ["activity_type", "subject", "description", "outcome", "due_date", "owner_id", "metadata", "version"]
        extra_kwargs = {field: {"required": False} for field in fields if field != "version"}


class ActivityCompleteSerializer(StrictSerializer):
    transition_key = serializers.CharField(min_length=1, max_length=255)
    expected_version = serializers.IntegerField(min_value=1)


class CurrencyForecastSerializer(serializers.Serializer):
    currency = serializers.CharField(min_length=3, max_length=3)
    total_pipeline_value = serializers.DecimalField(max_digits=19, decimal_places=4)
    weighted_pipeline_value = serializers.DecimalField(max_digits=19, decimal_places=4)
    opportunity_count = serializers.IntegerField(min_value=0)


class ForecastSerializer(serializers.Serializer):
    currencies = CurrencyForecastSerializer(many=True)
    period_days = serializers.IntegerField()


class WinRateSerializer(serializers.Serializer):
    win_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    won_count = serializers.IntegerField(min_value=0)
    lost_count = serializers.IntegerField(min_value=0)
    total_closed = serializers.IntegerField(min_value=0)
    period_days = serializers.IntegerField()


class StageForecastSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(choices=OpportunityStage.choices)
    currency = serializers.CharField(min_length=3, max_length=3)
    total_value = serializers.DecimalField(max_digits=19, decimal_places=4)
    weighted_value = serializers.DecimalField(max_digits=19, decimal_places=4)
    opportunity_count = serializers.IntegerField(min_value=0)


class RevenuePredictionSerializer(serializers.Serializer):
    provider = serializers.CharField()
    model = serializers.CharField()
    amount = serializers.DecimalField(max_digits=19, decimal_places=4)
    currency = serializers.CharField(min_length=3, max_length=3)
    confidence = serializers.DecimalField(max_digits=6, decimal_places=5, allow_null=True)
    factors = serializers.DictField()
    as_of = serializers.CharField()
    period_days = serializers.IntegerField()


class ForecastQuerySerializer(StrictSerializer):
    owner_id = serializers.UUIDField(required=False)
    period = serializers.IntegerField(required=False)


class RevenuePredictionRequestSerializer(StrictSerializer):
    period = serializers.IntegerField(required=False)


class AsyncOperationSerializer(serializers.ModelSerializer):
    job_id = serializers.UUIDField(source="id")

    class Meta:
        model = AsyncJob
        fields = ["job_id", "status", "command", "created_at", "correlation_id"]


class AsyncJobReadSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()
    error = serializers.SerializerMethodField()

    class Meta:
        model = AsyncJob
        fields = [
            "id",
            "command",
            "status",
            "progress",
            "result",
            "error",
            "created_at",
            "updated_at",
            "correlation_id",
        ]

    def get_progress(self, instance: AsyncJob) -> None:
        """Progress is unknown unless a worker persists a real progress field."""

        del instance
        return None

    def get_error(self, instance: AsyncJob) -> dict[str, object] | None:
        if not instance.error_message:
            return None
        return {
            "code": "JOB_FAILED",
            "message": instance.error_message,
            "detail": None,
            "correlation_id": instance.correlation_id,
        }


# Compatibility aliases for existing open-source imports.
LeadSerializer = LeadReadSerializer
AccountSerializer = AccountReadSerializer
ContactSerializer = ContactReadSerializer
OpportunitySerializer = OpportunityReadSerializer
ActivitySerializer = ActivityReadSerializer
LeadScoringResponseSerializer = LeadReadSerializer
OpportunityCreateFromLeadSerializer = LeadConvertSerializer
CloseWonRequestSerializer = CloseWonSerializer
CloseLostRequestSerializer = CloseLostSerializer
AIPredictionSerializer = RevenuePredictionSerializer


__all__ = [name for name in globals() if name.endswith("Serializer")]
