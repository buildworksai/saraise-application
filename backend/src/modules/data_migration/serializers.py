"""Read/write separated serializers for the data-migration API v2."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from rest_framework import serializers

from .models import (
    DataMigrationConfiguration,
    DataMigrationConfigurationAudit,
    ExternalConnection,
    MigrationJob,
    MigrationJobVersion,
    MigrationMapping,
    MigrationRollback,
    MigrationRun,
    MigrationRunIssue,
    ValidationRule,
)

SAFE_SOURCE_KEYS = frozenset(
    {
        "connection_id",
        "table",
        "columns",
        "filters",
        "batch_size",
        "delimiter",
        "encoding",
        "sheet",
        "header_row",
        "json_path",
        "relative_path",
        "method",
        "query_parameters",
        "results_path",
        "page_parameter",
        "page_size_parameter",
        "page_size",
        "max_pages",
    }
)


def safe_source_config(value: object) -> dict[str, Any]:
    """Defensively redact unknown keys before a source configuration leaves API."""

    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if key in SAFE_SOURCE_KEYS}


class StrictSerializer(serializers.Serializer):
    """Reject unrecognized fields instead of silently accepting future hazards."""

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if hasattr(data, "keys"):
            unknown = set(data.keys()) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: "Unknown field." for key in sorted(unknown)})
        return super().to_internal_value(data)


class LatestRunSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = MigrationRun
        fields = (
            "id",
            "mode",
            "status",
            "total_records",
            "processed_records",
            "succeeded_records",
            "failed_records",
            "warning_records",
            "created_at",
            "completed_at",
        )


class MigrationMappingReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = MigrationMapping
        fields = (
            "id",
            "job",
            "source_field",
            "target_field",
            "position",
            "transform_type",
            "transform_config",
            "is_required",
            "origin",
            "confidence",
            "created_at",
            "updated_at",
        )


class MigrationMappingWriteSerializer(StrictSerializer, serializers.ModelSerializer):
    class Meta:
        model = MigrationMapping
        fields = (
            "source_field",
            "target_field",
            "position",
            "transform_type",
            "transform_config",
            "is_required",
        )

    def validate_transform_config(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        return value


class ValidationRuleReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValidationRule
        fields = (
            "id",
            "job",
            "field_name",
            "rule_type",
            "rule_config",
            "error_message",
            "severity",
            "position",
            "is_active",
            "created_at",
            "updated_at",
        )


class ValidationRuleWriteSerializer(StrictSerializer, serializers.ModelSerializer):
    class Meta:
        model = ValidationRule
        fields = (
            "field_name",
            "rule_type",
            "rule_config",
            "error_message",
            "severity",
            "position",
            "is_active",
        )

    def validate_rule_config(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        return value


class MigrationJobListSerializer(serializers.ModelSerializer):
    latest_run = serializers.SerializerMethodField()
    readiness = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = MigrationJob
        fields = (
            "id",
            "name",
            "description",
            "source_type",
            "target_adapter",
            "target_entity",
            "write_mode",
            "status",
            "configuration_version",
            "readiness",
            "latest_run",
            "allowed_actions",
            "created_at",
            "updated_at",
        )

    def get_latest_run(self, obj: MigrationJob) -> dict[str, Any] | None:
        run = obj.runs.order_by("-created_at").first()
        return LatestRunSummarySerializer(run).data if run else None

    def get_readiness(self, obj: MigrationJob) -> dict[str, Any]:
        blockers: list[dict[str, str]] = []
        if not obj.mappings.exists():
            blockers.append({"code": "MAPPINGS_REQUIRED", "message": "Map at least one source field.", "section": "mappings"})
        if not obj.validation_rules.filter(is_active=True).exists():
            blockers.append({"code": "RULE_REQUIRED", "message": "Add an active validation rule.", "section": "rules"})
        if obj.source_type in {"csv", "excel", "json", "xml"} and not obj.source_artifact_id:
            blockers.append({"code": "SOURCE_REQUIRED", "message": "Attach an immutable source artifact.", "section": "source"})
        return {"ready": obj.status == "ready" and not blockers, "blockers": blockers}

    def get_allowed_actions(self, obj: MigrationJob) -> list[str]:
        request = self.context.get("request")
        permissions = set(getattr(getattr(request, "user", None), "permissions", ()) or ())
        candidates = {
            "open": "data_migration.job:read", "edit": "data_migration.job:update", "archive": "data_migration.job:update",
            "delete": "data_migration.job:delete", "export": "data_migration.job:export", "clone": "data_migration.job:import",
            "dry_run": "data_migration.run:execute", "run": "data_migration.run:execute",
        }
        state_allowed = {"open", "export", "clone"}
        if obj.status != "archived": state_allowed |= {"edit", "archive", "delete"}
        if obj.status == "ready": state_allowed |= {"dry_run", "run"}
        return sorted(action for action, permission in candidates.items() if action in state_allowed and permission in permissions)


class MigrationJobDetailSerializer(MigrationJobListSerializer):
    source_config = serializers.SerializerMethodField()
    mappings = MigrationMappingReadSerializer(many=True, read_only=True)
    validation_rules = ValidationRuleReadSerializer(many=True, read_only=True)

    class Meta(MigrationJobListSerializer.Meta):
        fields = MigrationJobListSerializer.Meta.fields + (
            "source_artifact_id",
            "source_config",
            "lookup_fields",
            "transition_history",
            "mappings",
            "validation_rules",
        )

    def get_source_config(self, obj: MigrationJob) -> dict[str, Any]:
        return safe_source_config(obj.source_config)


class _MigrationJobWriteSerializer(StrictSerializer, serializers.ModelSerializer):
    class Meta:
        model = MigrationJob
        fields = (
            "name",
            "description",
            "source_type",
            "source_artifact_id",
            "source_config",
            "target_adapter",
            "target_entity",
            "write_mode",
            "lookup_fields",
        )

    def validate_source_config(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        forbidden = set(value) - SAFE_SOURCE_KEYS
        if forbidden:
            raise serializers.ValidationError(f"Unsupported or sensitive keys: {', '.join(sorted(forbidden))}.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        source_type = attrs.get("source_type", getattr(self.instance, "source_type", None))
        config = attrs.get("source_config", getattr(self.instance, "source_config", {}))
        artifact = attrs.get("source_artifact_id", getattr(self.instance, "source_artifact_id", None))
        if source_type in {"csv", "excel", "json", "xml"} and not artifact:
            raise serializers.ValidationError({"source_artifact_id": "Required for file sources."})
        if source_type in {"database", "api"} and not config.get("connection_id"):
            raise serializers.ValidationError({"source_config": "A named connection_id is required."})
        if attrs.get("write_mode", getattr(self.instance, "write_mode", None)) == "upsert" and not attrs.get(
            "lookup_fields", getattr(self.instance, "lookup_fields", [])
        ):
            raise serializers.ValidationError({"lookup_fields": "At least one lookup field is required for upsert."})
        return attrs


class MigrationJobCreateSerializer(_MigrationJobWriteSerializer):
    pass


class MigrationJobUpdateSerializer(_MigrationJobWriteSerializer):
    expected_version = serializers.IntegerField(min_value=1, write_only=True)


class MigrationJobVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MigrationJobVersion
        fields = ("id", "job", "version", "snapshot", "change_summary", "created_by", "correlation_id", "created_at")


class ExpectedVersionSerializer(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)


class TransitionSerializer(StrictSerializer):
    transition_key = serializers.CharField(max_length=255)


class SourceAttachmentSerializer(ExpectedVersionSerializer):
    source_artifact_id = serializers.UUIDField()


class InspectionRequestSerializer(StrictSerializer):
    pass


class PreviewRequestSerializer(StrictSerializer):
    limit = serializers.IntegerField(min_value=1, max_value=100, default=25)


class RestoreVersionSerializer(ExpectedVersionSerializer):
    pass


class MappingSuggestionRequestSerializer(StrictSerializer):
    provider = serializers.ChoiceField(choices=("deterministic", "extension"), default="deterministic")


class MappingSuggestionApplySerializer(StrictSerializer):
    suggestion_ids = serializers.ListField(child=serializers.CharField(max_length=255), allow_empty=False, max_length=500)


class MigrationRunRequestSerializer(StrictSerializer):
    source_checksum = serializers.CharField(max_length=128, required=False)


class CancelRunSerializer(TransitionSerializer):
    pass


class MigrationRunSerializer(serializers.ModelSerializer):
    rollback_eligible = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    class Meta:
        model = MigrationRun
        fields = (
            "id",
            "job",
            "job_version",
            "mode",
            "status",
            "idempotency_key",
            "source_checksum",
            "total_records",
            "processed_records",
            "succeeded_records",
            "failed_records",
            "warning_records",
            "started_at",
            "completed_at",
            "cancel_requested_at",
            "transition_history",
            "created_by",
            "correlation_id",
            "created_at",
            "updated_at",
            "rollback_eligible",
            "allowed_actions",
        )

    def get_rollback_eligible(self, obj: MigrationRun) -> bool:
        return obj.mode == "commit" and obj.status in {"succeeded", "partial"} and obj.changes.filter(reversed_at__isnull=True).exists()

    def get_allowed_actions(self, obj: MigrationRun) -> list[str]:
        request = self.context.get("request")
        permissions = set(getattr(getattr(request, "user", None), "permissions", ()) or ())
        actions = []
        if "data_migration.job:read" in permissions: actions.append("export_issues")
        if obj.status in {"queued", "running"} and "data_migration.run:cancel" in permissions: actions.append("cancel")
        if self.get_rollback_eligible(obj) and "data_migration.rollback:execute" in permissions: actions.append("rollback")
        return actions


class MigrationRunIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MigrationRunIssue
        fields = ("id", "run", "row_number", "field_name", "stage", "severity", "code", "message", "redacted_sample", "created_at")


class RollbackRequestSerializer(StrictSerializer):
    pass


class MigrationRollbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = MigrationRollback
        fields = (
            "id",
            "run",
            "status",
            "idempotency_key",
            "records_total",
            "records_reversed",
            "records_failed",
            "failure_summary",
            "started_at",
            "completed_at",
            "transition_history",
            "requested_by",
            "correlation_id",
            "created_at",
            "updated_at",
        )


class ExternalConnectionReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalConnection
        fields = ("id", "name", "kind", "is_active", "created_at", "updated_at")


class ExternalConnectionManagementSerializer(StrictSerializer, serializers.ModelSerializer):
    credential_ref = serializers.CharField(max_length=255, write_only=True, required=False)

    class Meta:
        model = ExternalConnection
        fields = (
            "id",
            "name",
            "kind",
            "host",
            "port",
            "database",
            "username",
            "base_url",
            "credential_ref",
            "tls_mode",
            "public_options",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ConnectionTestResultSerializer(StrictSerializer):
    verified = serializers.BooleanField()
    code = serializers.CharField(max_length=100)
    checked_at = serializers.DateTimeField()
    latency_ms = serializers.IntegerField(min_value=0, required=False)


class CredentialRotationSerializer(StrictSerializer):
    credential_ref = serializers.CharField(max_length=255, trim_whitespace=True)


class DefinitionImportSerializer(StrictSerializer):
    document = serializers.DictField()
    preview_only = serializers.BooleanField(default=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        document = attrs["document"]
        required = {"schema_version", "checksum", "job", "mappings", "rules"}
        if not required <= set(document) or document.get("schema_version") != "2.0":
            raise serializers.ValidationError({"document": "Unsupported or incomplete migration document."})
        canonical = json.dumps(
            {key: document[key] for key in ("schema_version", "job", "mappings", "rules")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if hashlib.sha256(canonical).hexdigest() != document["checksum"]:
            raise serializers.ValidationError({"checksum": "Document checksum does not match its contents."})
        forbidden = {"tenant_id", "created_by", "updated_by", "credential_ref", "execution_history"}
        if forbidden.intersection(document["job"]):
            raise serializers.ValidationError({"document": "Document contains non-portable identity or secret fields."})
        return attrs


# Compatibility names kept for existing imports while v1 is deprecated.
MigrationJobSerializer = MigrationJobDetailSerializer
MigrationMappingSerializer = MigrationMappingReadSerializer


class DataMigrationConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataMigrationConfiguration
        fields = (
            "id",
            "source_row_limit",
            "batch_size",
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "retry_count",
            "issue_sample_limit",
            "preview_row_limit",
            "retention_days",
            "allowed_target_adapters",
            "enabled_roles",
            "rollout_percentage",
            "enabled",
            "version",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DataMigrationConfigurationUpdateSerializer(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    source_row_limit = serializers.IntegerField(min_value=1, max_value=10_000_000, required=False)
    batch_size = serializers.IntegerField(min_value=1, max_value=10_000, required=False)
    connect_timeout_seconds = serializers.IntegerField(min_value=1, max_value=120, required=False)
    read_timeout_seconds = serializers.IntegerField(min_value=1, max_value=600, required=False)
    retry_count = serializers.IntegerField(min_value=0, max_value=10, required=False)
    issue_sample_limit = serializers.IntegerField(min_value=0, max_value=1000, required=False)
    preview_row_limit = serializers.IntegerField(min_value=1, max_value=100, required=False)
    retention_days = serializers.IntegerField(min_value=1, max_value=3650, required=False)
    enabled_roles = serializers.ListField(child=serializers.CharField(max_length=100), max_length=100, required=False)
    allowed_target_adapters = serializers.ListField(child=serializers.CharField(max_length=100), max_length=100, required=False)
    rollout_percentage = serializers.IntegerField(min_value=0, max_value=100, required=False)
    enabled = serializers.BooleanField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if len(attrs) == 1 and "expected_version" in attrs:
            raise serializers.ValidationError({"non_field_errors": "At least one configuration value is required."})
        return attrs


class DataMigrationConfigurationPreviewSerializer(DataMigrationConfigurationUpdateSerializer):
    expected_version = None


class DataMigrationConfigurationAuditSerializer(serializers.ModelSerializer):
    snapshot = serializers.JSONField(source="after", read_only=True)
    change_summary = serializers.SerializerMethodField()

    class Meta:
        model = DataMigrationConfigurationAudit
        fields = ("id", "configuration", "version", "before", "after", "snapshot", "change_summary", "changed_by", "correlation_id", "created_at")
        read_only_fields = fields

    def get_change_summary(self, obj: DataMigrationConfigurationAudit) -> str:
        changed = sorted(key for key in set(obj.before) | set(obj.after) if obj.before.get(key) != obj.after.get(key))
        return "Changed " + ", ".join(changed) if changed else "Configuration restored"


class DataMigrationConfigurationRestoreSerializer(ExpectedVersionSerializer):
    pass


class DataMigrationConfigurationImportSerializer(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    document = serializers.DictField()


__all__ = [name for name in globals() if name.endswith("Serializer")]
