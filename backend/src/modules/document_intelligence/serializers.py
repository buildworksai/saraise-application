"""Operation-specific DRF serializers for the governed v2 API."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import (
    ClassifierModelVersion,
    ClassifierTrainingJob,
    ConfigurationAudit,
    ConfigurationVersion,
    DocumentClassification,
    DocumentClassificationScore,
    DocumentExtraction,
    DocumentExtractionPage,
    DocumentIntelligenceConfiguration,
    ExpectedDataType,
    ExtractionTemplate,
    ExtractionTemplateZone,
    ExtractionType,
    ZoneType,
)

SERVER_OWNED_FIELDS = frozenset(
    {
        "id",
        "tenant_id",
        "created_by",
        "status",
        "async_job_id",
        "raw_text",
        "structured_data",
        "table_data",
        "category",
        "confidence",
        "secondary_category",
        "secondary_confidence",
        "needs_review",
        "review_status",
        "reviewed_category",
        "reviewed_by",
        "reviewed_at",
        "processing_time_ms",
        "failure_code",
        "failure_message",
        "accuracy",
        "artifact_ref",
        "artifact_checksum",
        "activated_by",
        "activated_at",
        "retired_at",
        "completed_at",
        "started_at",
        "created_at",
        "updated_at",
        "deleted_at",
        "is_deleted",
        "transition_history",
    }
)


class RejectServerOwnedFieldsMixin:
    """Reject privilege-confusing fields instead of silently discarding them."""

    server_owned_fields = SERVER_OWNED_FIELDS

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        supplied = set(getattr(self, "initial_data", {})) & self.server_owned_fields
        if supplied:
            raise serializers.ValidationError({field: "This field is server-owned." for field in sorted(supplied)})
        return super().validate(attrs)  # type: ignore[misc]


class JobTransitionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    from_status = serializers.CharField()
    to_status = serializers.CharField()
    actor_id = serializers.CharField(allow_null=True)
    reason = serializers.CharField()
    metadata = serializers.JSONField()
    created_at = serializers.DateTimeField()


class JobSummarySerializer(serializers.ModelSerializer):
    transitions = JobTransitionSerializer(many=True, read_only=True)

    class Meta:
        model = AsyncJob
        fields = (
            "id",
            "command",
            "status",
            "attempts",
            "correlation_id",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "transitions",
        )
        read_only_fields = fields


class DocumentExtractionListSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentExtraction
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "document_id",
            "document_version_id",
            "engine",
            "extraction_type",
            "template",
            "status",
            "confidence",
            "page_count",
            "processing_time_ms",
            "created_at",
            "updated_at",
            "completed_at",
            "is_deleted",
            "deleted_at",
        )
        read_only_fields = fields


class DocumentExtractionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentExtraction
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "document_id",
            "document_version_id",
            "engine",
            "extraction_type",
            "template",
            "status",
            "raw_text",
            "structured_data",
            "table_data",
            "confidence",
            "page_count",
            "processing_time_ms",
            "failure_code",
            "failure_message",
            "started_at",
            "completed_at",
            "transition_history",
            "is_deleted",
            "deleted_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DocumentExtractionCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    document_id = serializers.UUIDField()
    document_version_id = serializers.UUIDField()
    engine = serializers.CharField(max_length=50, required=False, allow_blank=False)
    extraction_type = serializers.ChoiceField(choices=ExtractionType.choices)
    template_id = serializers.UUIDField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=255, write_only=True, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs["extraction_type"] in {ExtractionType.STRUCTURED, ExtractionType.ZONE} and not attrs.get(
            "template_id"
        ):
            raise serializers.ValidationError({"template_id": "This extraction type requires a template."})
        if attrs["extraction_type"] in {ExtractionType.TEXT, ExtractionType.TABLE} and not attrs.get("engine"):
            raise serializers.ValidationError({"engine": "An engine is required for this extraction type."})
        return attrs


class DocumentExtractionPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentExtractionPage
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "extraction",
            "page_number",
            "width",
            "height",
            "raw_text",
            "structured_data",
            "table_data",
            "confidence",
            "provider_metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DocumentClassificationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentClassification
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "document_id",
            "document_version_id",
            "status",
            "category",
            "confidence",
            "needs_review",
            "review_status",
            "model_version",
            "processing_time_ms",
            "created_at",
            "completed_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
        )
        read_only_fields = fields


class DocumentClassificationDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentClassification
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "document_id",
            "document_version_id",
            "model_version",
            "status",
            "category",
            "confidence",
            "secondary_category",
            "secondary_confidence",
            "needs_review",
            "review_status",
            "reviewed_category",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "processing_time_ms",
            "failure_code",
            "failure_message",
            "completed_at",
            "transition_history",
            "is_deleted",
            "deleted_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DocumentClassificationCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    document_id = serializers.UUIDField()
    document_version_id = serializers.UUIDField()
    idempotency_key = serializers.CharField(max_length=255, write_only=True)


class ClassificationReviewSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    server_owned_fields = SERVER_OWNED_FIELDS - {"category"}

    category = serializers.RegexField(r"^[a-z0-9][a-z0-9._-]{0,79}$", max_length=80)
    note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)


class DocumentClassificationScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentClassificationScore
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "classification",
            "category",
            "confidence",
            "rank",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ClassifierTrainingJobListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassifierTrainingJob
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "name",
            "requested_version",
            "status",
            "training_data_count",
            "category_counts",
            "accuracy",
            "created_at",
            "started_at",
            "completed_at",
            "updated_at",
        )
        read_only_fields = fields


class ClassifierTrainingJobDetailSerializer(serializers.ModelSerializer):
    job = serializers.SerializerMethodField()

    class Meta:
        model = ClassifierTrainingJob
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "name",
            "training_items",
            "training_data_count",
            "category_counts",
            "requested_version",
            "status",
            "accuracy",
            "failure_code",
            "failure_message",
            "started_at",
            "completed_at",
            "transition_history",
            "created_at",
            "updated_at",
            "job",
        )
        read_only_fields = fields

    def get_job(self, obj: ClassifierTrainingJob) -> dict[str, Any] | None:
        job = AsyncJob.objects.for_tenant(obj.tenant_id).filter(pk=obj.async_job_id).first()
        if job is None:
            raise RuntimeError("Training job has no durable AsyncJob record")
        return JobSummarySerializer(job).data


class TrainingItemSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    document_version_id = serializers.UUIDField()
    category = serializers.RegexField(r"^[a-z0-9][a-z0-9._-]{0,79}$", max_length=80)


class ClassifierTrainingJobCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    items = TrainingItemSerializer(many=True, min_length=1, max_length=100_000)
    requested_version = serializers.CharField(max_length=50, trim_whitespace=True)
    idempotency_key = serializers.CharField(max_length=255, write_only=True)

    def validate_items(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from .services import ConfigurationService, default_configuration_document

        tenant_id = self.context.get("tenant_id")
        classifier_policy = (
            ConfigurationService().get_effective(tenant_id)["classifier"]
            if tenant_id is not None
            else default_configuration_document()["classifier"]
        )
        minimum_documents = int(classifier_policy["minimum_training_documents"])
        minimum_per_category = int(classifier_policy["minimum_documents_per_category"])
        if len(value) < minimum_documents:
            raise serializers.ValidationError(f"At least {minimum_documents} training documents are required.")
        counts: dict[str, int] = {}
        for item in value:
            category = str(item["category"])
            counts[category] = counts.get(category, 0) + 1
        if any(count < minimum_per_category for count in counts.values()):
            raise serializers.ValidationError(f"Every category requires at least {minimum_per_category} documents.")
        pairs = [(item["document_id"], item["document_version_id"]) for item in value]
        if len(pairs) != len(set(pairs)):
            raise serializers.ValidationError("A document version may only appear once.")
        return value


class ExtractionTemplateZoneCreateSerializer(RejectServerOwnedFieldsMixin, serializers.ModelSerializer):
    template_id = serializers.UUIDField(required=False, write_only=True)

    class Meta:
        model = ExtractionTemplateZone
        fields = (
            "template_id",
            "zone_name",
            "extraction_key",
            "zone_type",
            "x",
            "y",
            "width",
            "height",
            "page_number",
            "expected_data_type",
            "is_required",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        x, y, width, height = attrs["x"], attrs["y"], attrs["width"], attrs["height"]
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
            raise serializers.ValidationError("Zone coordinates must be normalized within the page.")
        return attrs


class ExtractionTemplateZoneUpdateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    zone_name = serializers.CharField(max_length=100, required=False)
    extraction_key = serializers.CharField(max_length=100, required=False)
    zone_type = serializers.ChoiceField(choices=ZoneType.choices, required=False)
    x = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, min_value=0, max_value=1)
    y = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, min_value=0, max_value=1)
    width = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, min_value=0, max_value=1)
    height = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, min_value=0, max_value=1)
    page_number = serializers.IntegerField(min_value=1, required=False)
    expected_data_type = serializers.ChoiceField(choices=ExpectedDataType.choices, required=False)
    is_required = serializers.BooleanField(required=False)


class ExtractionTemplateListSerializer(serializers.ModelSerializer):
    zone_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = ExtractionTemplate
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "name",
            "description",
            "document_category",
            "engine",
            "match_threshold",
            "status",
            "version",
            "activated_at",
            "zone_count",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
        )
        read_only_fields = fields


class ExtractionTemplateDetailSerializer(serializers.ModelSerializer):
    zones = serializers.SerializerMethodField()

    class Meta:
        model = ExtractionTemplate
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "name",
            "description",
            "document_category",
            "engine",
            "match_threshold",
            "status",
            "version",
            "activated_at",
            "transition_history",
            "zones",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
        )
        read_only_fields = fields

    def get_zones(self, obj: ExtractionTemplate) -> list[dict[str, Any]]:
        zones = obj.zones.filter(tenant_id=obj.tenant_id, is_deleted=False).order_by("page_number", "zone_name")
        return ExtractionTemplateZoneReadSerializer(zones, many=True).data


class ExtractionTemplateZoneReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractionTemplateZone
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "template",
            "zone_name",
            "extraction_key",
            "zone_type",
            "x",
            "y",
            "width",
            "height",
            "page_number",
            "expected_data_type",
            "is_required",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
        )
        read_only_fields = fields


class ExtractionTemplateCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=255, write_only=True, required=False)
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=10_000)
    document_category = serializers.RegexField(
        r"^[a-z0-9][a-z0-9._-]{0,79}$", required=False, allow_blank=True, max_length=80
    )
    engine = serializers.CharField(max_length=50, trim_whitespace=True)
    match_threshold = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1, required=False)
    zones = ExtractionTemplateZoneCreateSerializer(many=True, required=False)


class ExtractionTemplateUpdateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=255, trim_whitespace=True, required=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=10_000)
    document_category = serializers.RegexField(
        r"^[a-z0-9][a-z0-9._-]{0,79}$", required=False, allow_blank=True, max_length=80
    )
    engine = serializers.CharField(max_length=50, trim_whitespace=True, required=False)
    match_threshold = serializers.DecimalField(max_digits=5, decimal_places=4, min_value=0, max_value=1, required=False)


class ClassifierModelVersionListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassifierModelVersion
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "version",
            "provider_key",
            "accuracy",
            "status",
            "training_job",
            "activated_by",
            "activated_at",
            "retired_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ClassifierModelVersionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassifierModelVersion
        fields = (
            "id",
            "tenant_id",
            "created_by",
            "version",
            "provider_key",
            "training_job",
            "accuracy",
            "status",
            "activated_by",
            "activated_at",
            "retired_at",
            "transition_history",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RetryActionSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=255)


class CancelActionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class ActivateActionSerializer(serializers.Serializer):
    transition_key = serializers.CharField(max_length=255)


class RollbackActionSerializer(ActivateActionSerializer):
    pass


class DeactivateActionSerializer(ActivateActionSerializer):
    pass


class CloneTemplateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, trim_whitespace=True)


class TemplateMatchSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    document_version_id = serializers.UUIDField()


class ExtractionRetrySerializer(RetryActionSerializer):
    pass


class ExtractionCancelSerializer(CancelActionSerializer):
    pass


class ClassificationRetrySerializer(RetryActionSerializer):
    pass


class ClassificationCancelSerializer(CancelActionSerializer):
    pass


class TrainingRetrySerializer(RetryActionSerializer):
    pass


class TrainingCancelSerializer(CancelActionSerializer):
    pass


class ModelActivateSerializer(ActivateActionSerializer):
    pass


class ModelRollbackSerializer(RollbackActionSerializer):
    pass


class TemplateActivateSerializer(ActivateActionSerializer):
    pass


class TemplateDeactivateSerializer(DeactivateActionSerializer):
    pass


class DocumentIntelligenceConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentIntelligenceConfiguration
        fields = (
            "id",
            "tenant_id",
            "environment",
            "version",
            "document",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ConfigurationVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationVersion
        fields = (
            "id",
            "tenant_id",
            "environment",
            "version",
            "document",
            "created_by",
            "correlation_id",
            "change_reason",
            "created_at",
        )
        read_only_fields = fields


class ConfigurationAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationAudit
        fields = (
            "id",
            "tenant_id",
            "environment",
            "version",
            "operation",
            "previous_document",
            "new_document",
            "created_by",
            "correlation_id",
            "change_reason",
            "created_at",
        )
        read_only_fields = fields


class ConfigurationWriteSerializer(serializers.Serializer):
    document = serializers.JSONField()
    environment = serializers.ChoiceField(choices=("development", "self-hosted", "saas"), required=False)
    change_reason = serializers.CharField(max_length=500, trim_whitespace=True)


class ConfigurationRollbackSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    environment = serializers.ChoiceField(choices=("development", "self-hosted", "saas"), required=False)
    change_reason = serializers.CharField(max_length=500, trim_whitespace=True)


class ConfigurationImportSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField(min_value=1, max_value=1)
    module = serializers.ChoiceField(choices=("document_intelligence",))
    environment = serializers.ChoiceField(choices=("development", "self-hosted", "saas"))
    version = serializers.IntegerField(min_value=1, required=False)
    exported_at = serializers.DateTimeField(required=False)
    document = serializers.JSONField()
    change_reason = serializers.CharField(max_length=500, trim_whitespace=True, required=False)


class ConfigurationSimulationSerializer(serializers.Serializer):
    document = serializers.JSONField()
    environment = serializers.ChoiceField(choices=("development", "self-hosted", "saas"), required=False)


__all__ = [name for name in globals() if name.endswith("Serializer")]
