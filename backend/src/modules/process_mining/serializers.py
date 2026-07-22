"""Strict operation-specific serializers for process-mining API v2."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import (
    BottleneckAnalysis, BottleneckFinding, ConformanceCaseMetric, ConformanceCheck,
    ConformanceDeviation, EventExportJob, ExportFormat, MiningAlgorithmName, ProcessDiscoveryJob,
    ProcessEvent, ProcessModel, ProcessModelVersion, ProcessVariant, validate_graph,
    ProcessMiningConfiguration, ProcessMiningConfigurationAudit, ProcessMiningConfigurationVersion,
)
from .services import FLOAT_LIMITS, INTEGER_LIMITS

SERVER_OWNED = frozenset({"id", "tenant_id", "created_by", "created_at", "updated_at", "is_deleted", "deleted_at", "status", "transition_history", "async_job_id", "artifact_key", "content_type", "row_count", "byte_size", "sha256", "expires_at", "completed_at", "started_at", "error_code", "error_message", "event_count", "case_count", "activity_count", "fitness", "precision", "generalization", "total_cases", "conformant_cases", "deviating_cases", "total_variants", "avg_case_duration_seconds"})


class RejectServerOwnedFieldsMixin:
    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        supplied = set(getattr(self, "initial_data", {})) & SERVER_OWNED
        if supplied:
            raise serializers.ValidationError({field: "This field is server-owned." for field in sorted(supplied)})
        return super().validate(attrs)  # type: ignore[misc]


class ReadOnlyModelSerializer(serializers.ModelSerializer):
    class Meta:
        fields: tuple[str, ...] = ()
        read_only_fields: tuple[str, ...] = ()


EVENT_LIST_FIELDS = ("id", "process_name", "source_module", "source_event_id", "case_id", "activity", "occurred_at", "resource", "ingested_at", "created_at")


class ProcessEventListSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ProcessEvent
        fields = EVENT_LIST_FIELDS
        read_only_fields = fields


class ProcessEventDetailSerializer(ReadOnlyModelSerializer):
    attributes = serializers.SerializerMethodField()

    class Meta:
        model = ProcessEvent
        fields = (*EVENT_LIST_FIELDS, "attributes")
        read_only_fields = fields

    def get_attributes(self, instance: ProcessEvent) -> dict[str, object]:
        sensitive = {"email", "phone", "address", "name", "ssn", "tax_id", "account_number"}
        return {key: "[REDACTED]" if key.lower() in sensitive or key.lower().startswith("sensitive_") else value for key, value in instance.attributes.items()}


class CanonicalEventInputSerializer(serializers.Serializer):
    case_id = serializers.CharField(max_length=255)
    activity = serializers.CharField(max_length=255)
    occurred_at = serializers.DateTimeField()
    resource = serializers.CharField(max_length=255, required=False, allow_blank=True)
    source_event_id = serializers.CharField(max_length=255, required=False, allow_blank=True)
    attributes = serializers.JSONField(required=False)


class EventBatchIngestSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    process_name = serializers.CharField(max_length=255)
    source_module = serializers.CharField(max_length=100)
    events = CanonicalEventInputSerializer(many=True, allow_empty=False, max_length=10_000)


EXPORT_LIST_FIELDS = ("id", "process_name", "format", "status", "row_count", "byte_size", "sha256", "expires_at", "completed_at", "error_code", "created_at", "updated_at")


class EventExportListSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = EventExportJob
        fields = EXPORT_LIST_FIELDS
        read_only_fields = fields


class EventExportDetailSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = EventExportJob
        fields = (*EXPORT_LIST_FIELDS, "event_filter")
        read_only_fields = fields


class EventExportCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    process_name = serializers.CharField(max_length=255)
    format = serializers.ChoiceField(choices=ExportFormat.choices)
    event_filter = serializers.JSONField(required=False)
    idempotency_key = serializers.CharField(max_length=255)


DISCOVERY_LIST_FIELDS = ("id", "process_name", "algorithm", "status", "event_count", "case_count", "activity_count", "started_at", "completed_at", "error_code", "created_at", "updated_at")


class DiscoveryListSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ProcessDiscoveryJob
        fields = DISCOVERY_LIST_FIELDS
        read_only_fields = fields


class DiscoveryDetailSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ProcessDiscoveryJob
        fields = (*DISCOVERY_LIST_FIELDS, "parameters")
        read_only_fields = fields


class DiscoveryCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    process_name = serializers.CharField(max_length=255)
    algorithm = serializers.ChoiceField(choices=MiningAlgorithmName.choices)
    parameters = serializers.JSONField(required=False)
    idempotency_key = serializers.CharField(max_length=255)


MODEL_LIST_FIELDS = ("id", "name", "process_name", "description", "source_kind", "current_version_number", "reference_version_number", "created_at", "updated_at")


class ProcessModelListSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ProcessModel
        fields = MODEL_LIST_FIELDS
        read_only_fields = fields


class ProcessModelDetailSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ProcessModel
        fields = MODEL_LIST_FIELDS
        read_only_fields = fields


class ProcessModelCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=255)
    process_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    model_data = serializers.JSONField()

    def validate_model_data(self, value: object) -> object:
        validate_graph(value)
        return value


class ProcessModelUpdateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)


VERSION_LIST_FIELDS = ("id", "process_model", "version", "algorithm", "event_count", "case_count", "activity_count", "avg_case_duration_seconds", "is_reference", "published_at", "created_at")


class ProcessModelVersionListSerializer(ReadOnlyModelSerializer):
    is_reference = serializers.SerializerMethodField()

    class Meta:
        model = ProcessModelVersion
        fields = VERSION_LIST_FIELDS
        read_only_fields = fields

    def get_is_reference(self, instance: ProcessModelVersion) -> bool:
        latest = instance.process_model.reference_assignments.filter(tenant_id=instance.tenant_id).order_by("-created_at", "-id").first()
        return bool(latest and latest.process_model_version_id == instance.id)


class ProcessModelVersionDetailSerializer(ProcessModelVersionListSerializer):
    class Meta:
        model = ProcessModelVersion
        fields = (*VERSION_LIST_FIELDS, "parameters", "model_data")
        read_only_fields = fields


class SetReferenceSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    version_id = serializers.UUIDField()
    transition_key = serializers.CharField(max_length=255)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)


CONFORMANCE_LIST_FIELDS = ("id", "process_model_version", "status", "fitness", "precision", "generalization", "total_cases", "conformant_cases", "deviating_cases", "started_at", "completed_at", "error_code", "created_at", "updated_at")


class ConformanceListSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ConformanceCheck
        fields = CONFORMANCE_LIST_FIELDS
        read_only_fields = fields


class ConformanceDetailSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ConformanceCheck
        fields = (*CONFORMANCE_LIST_FIELDS, "event_filter")
        read_only_fields = fields


class ConformanceCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    process_model_version_id = serializers.UUIDField()
    event_filter = serializers.JSONField(required=False)
    idempotency_key = serializers.CharField(max_length=255)


class DeviationListSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ConformanceDeviation
        fields = ("id", "conformance_check", "case_id", "deviation_type", "expected", "actual", "position", "description", "created_at")
        read_only_fields = fields


class CaseFitnessSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ConformanceCaseMetric
        fields = ("id", "conformance_check", "case_id", "fitness", "is_conformant", "deviation_count", "trace_length", "created_at")
        read_only_fields = fields


BOTTLENECK_LIST_FIELDS = ("id", "process_name", "time_range_start", "time_range_end", "status", "total_cases", "total_variants", "avg_case_duration_seconds", "started_at", "completed_at", "error_code", "created_at", "updated_at")


class BottleneckAnalysisListSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = BottleneckAnalysis
        fields = BOTTLENECK_LIST_FIELDS
        read_only_fields = fields


class BottleneckAnalysisDetailSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = BottleneckAnalysis
        fields = BOTTLENECK_LIST_FIELDS
        read_only_fields = fields


class BottleneckCreateSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    process_name = serializers.CharField(max_length=255)
    time_range_start = serializers.DateTimeField()
    time_range_end = serializers.DateTimeField()
    idempotency_key = serializers.CharField(max_length=255)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs["time_range_end"] <= attrs["time_range_start"]:
            raise serializers.ValidationError({"time_range_end": "End must follow start."})
        return attrs


class BottleneckFindingSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = BottleneckFinding
        fields = ("id", "analysis", "from_activity", "to_activity", "avg_duration_seconds", "median_duration_seconds", "p95_duration_seconds", "case_count", "severity", "resource_bottleneck", "rank", "created_at")
        read_only_fields = fields


class ProcessVariantSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ProcessVariant
        fields = ("id", "analysis", "variant_key", "activities", "case_count", "percentage", "avg_duration_seconds", "is_happy_path", "is_grouped_other", "created_at")
        read_only_fields = fields


class TransitionActionSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    transition_key = serializers.CharField(max_length=255)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    idempotency_key = serializers.CharField(required=False, max_length=255)


class ModuleHealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unavailable"))
    live = serializers.BooleanField()
    ready = serializers.BooleanField()
    checked_at = serializers.DateTimeField()
    dependencies = serializers.ListField(child=serializers.DictField())


class IngestEvidenceSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    status = serializers.CharField()
    event_id = serializers.UUIDField(allow_null=True)
    code = serializers.CharField(allow_blank=True)
    message = serializers.CharField(allow_blank=True)


class IngestResultSerializer(serializers.Serializer):
    accepted = serializers.IntegerField()
    rejected = serializers.IntegerField()
    duplicates = serializers.IntegerField()
    rows = IngestEvidenceSerializer(many=True)


class ProcessMiningConfigurationSerializer(ReadOnlyModelSerializer):
    limits = serializers.SerializerMethodField()

    class Meta:
        model = ProcessMiningConfiguration
        fields = ("id", "version", "document", "limits", "updated_at")
        read_only_fields = fields

    def get_limits(self, instance: ProcessMiningConfiguration) -> dict[str, tuple[float, float]]:
        del instance
        return {**INTEGER_LIMITS, **FLOAT_LIMITS}


class ProcessMiningConfigurationVersionSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ProcessMiningConfigurationVersion
        fields = ("id", "version", "document", "source", "correlation_id", "created_at")
        read_only_fields = fields


class ProcessMiningConfigurationAuditSerializer(ReadOnlyModelSerializer):
    class Meta:
        model = ProcessMiningConfigurationAudit
        fields = ("id", "version", "action", "previous_document", "current_document", "correlation_id", "created_at")
        read_only_fields = fields


class ConfigurationDocumentSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    document = serializers.JSONField()


class ConfigurationImportSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    configuration = serializers.JSONField()


class ConfigurationRollbackSerializer(RejectServerOwnedFieldsMixin, serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


__all__ = [name for name in globals() if name.endswith("Serializer")]
