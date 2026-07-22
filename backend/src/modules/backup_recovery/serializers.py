"""Strict API v2 serializers; system-owned evidence is never writable."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePath

from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import (
    BackupArchive,
    BackupFrequency,
    BackupJob,
    BackupRetentionPolicy,
    BackupSchedule,
    BackupScopeType,
    BackupStorageTarget,
    BackupType,
    BackupVerification,
)

_UNSAFE_REFERENCE_FRAGMENTS = ("?", "#", "password=", "secret=", "token=", "signature=", "x-amz-")


def _reference_is_safe(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    lowered = value.lower()
    if any(fragment in lowered for fragment in _UNSAFE_REFERENCE_FRAGMENTS):
        return False
    return not ("://" in lowered and "@" in lowered.split("://", 1)[1].split("/", 1)[0])


class StrictInputSerializer(serializers.Serializer):
    """Reject unknown keys so system-owned fields cannot be silently ignored."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError(
                    {field: ["This field is unknown or server-managed."] for field in unknown}
                )
        return super().to_internal_value(data)


class BackupJobListSerializer(serializers.ModelSerializer):
    schedule_name = serializers.CharField(source="schedule.name", read_only=True, allow_null=True)
    storage_target_name = serializers.CharField(source="storage_target.name", read_only=True)

    class Meta:
        model = BackupJob
        fields = (
            "id",
            "backup_type",
            "scope_type",
            "scope_ref",
            "status",
            "description",
            "requested_at",
            "started_at",
            "completed_at",
            "size_bytes",
            "schedule",
            "schedule_name",
            "storage_target",
            "storage_target_name",
            "error_code",
            "updated_at",
        )


class BackupJobDetailSerializer(serializers.ModelSerializer):
    allowed_commands = serializers.SerializerMethodField()
    archive = serializers.SerializerMethodField()
    transition_history = serializers.SerializerMethodField()
    correlation_id = serializers.SerializerMethodField()
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = BackupJob
        exclude = ("tenant_id", "storage_location", "is_deleted", "deleted_at")

    def get_allowed_commands(self, obj: BackupJob) -> dict[str, dict[str, object]]:
        if obj.status == "pending":
            commands = ("update", "cancel")
        elif obj.status == "running":
            commands = ("cancel",)
        elif obj.status in ("failed", "cancelled"):
            commands = ("retry", "delete")
        else:
            commands = ("delete",)
        return {command: {"allowed": True} for command in commands}

    def get_archive(self, obj: BackupJob) -> dict[str, object] | None:
        try:
            archive = obj.archive
        except BackupArchive.DoesNotExist:
            return None
        return {
            "id": archive.id,
            "lifecycle": archive.lifecycle,
            "checksum_algorithm": archive.checksum_algorithm,
            "checksum_digest": archive.checksum_digest,
            "integrity_status": archive.integrity_status,
        }

    def get_transition_history(self, obj: BackupJob) -> list[dict[str, object]]:
        return [
            {
                "command": item.get("command", ""),
                "from": item.get("from_state", ""),
                "to": item.get("to_state", ""),
                "at": item.get("occurred_at", ""),
                "actor_id": (
                    item.get("metadata", {}).get("actor_id") if isinstance(item.get("metadata"), dict) else None
                ),
                "correlation_id": (
                    item.get("metadata", {}).get("correlation_id") if isinstance(item.get("metadata"), dict) else None
                ),
            }
            for item in obj.transition_history
            if isinstance(item, dict)
        ]

    def get_correlation_id(self, obj: BackupJob) -> str | None:
        if obj.async_job_id is None:
            return None
        return (
            AsyncJob.objects.filter(tenant_id=obj.tenant_id, pk=obj.async_job_id)
            .values_list("correlation_id", flat=True)
            .first()
        )

    def get_duration_seconds(self, obj: BackupJob) -> float | None:
        end = obj.completed_at
        if obj.started_at is None or end is None:
            return None
        return max(0.0, (end - obj.started_at).total_seconds())


class BackupJobCreateSerializer(StrictInputSerializer):
    backup_type = serializers.ChoiceField(choices=BackupType.choices)
    scope_type = serializers.ChoiceField(choices=BackupScopeType.choices)
    scope_ref = serializers.CharField(max_length=255)
    idempotency_key = serializers.CharField(max_length=128)
    storage_target_id = serializers.UUIDField(required=False, allow_null=True)
    retention_policy_id = serializers.UUIDField(required=False, allow_null=True)
    schedule_id = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)


class BackupJobUpdateSerializer(StrictInputSerializer):
    description = serializers.CharField(required=True, allow_blank=True)


class BackupJobCancelSerializer(StrictInputSerializer):
    transition_key = serializers.CharField(max_length=128)


class BackupJobRetrySerializer(StrictInputSerializer):
    idempotency_key = serializers.CharField(max_length=128)


class BackupRequestReceiptSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    async_job_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=("pending", "running", "completed", "failed", "cancelled"))
    idempotency_key = serializers.CharField(max_length=128)


class BackupScheduleListSerializer(serializers.ModelSerializer):
    storage_target_name = serializers.CharField(source="storage_target.name", read_only=True)
    retention_policy_name = serializers.CharField(source="retention_policy.name", read_only=True)

    class Meta:
        model = BackupSchedule
        fields = (
            "id",
            "name",
            "scope_type",
            "scope_ref",
            "backup_type",
            "frequency",
            "timezone",
            "is_active",
            "next_run_at",
            "last_run_at",
            "storage_target",
            "storage_target_name",
            "retention_policy",
            "retention_policy_name",
            "description",
            "created_at",
            "updated_at",
        )


class BackupScheduleDetailSerializer(serializers.ModelSerializer):
    allowed_commands = serializers.SerializerMethodField()

    class Meta:
        model = BackupSchedule
        exclude = ("tenant_id", "is_deleted", "deleted_at")

    def get_allowed_commands(self, obj: BackupSchedule) -> dict[str, dict[str, object]]:
        commands = ("update", "delete", "activate") + (("execute",) if obj.is_active else ())
        return {command: {"allowed": True} for command in commands}


class BackupScheduleCreateSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=120)
    scope_type = serializers.ChoiceField(choices=BackupScopeType.choices)
    scope_ref = serializers.CharField(max_length=255)
    backup_type = serializers.ChoiceField(choices=BackupType.choices)
    frequency = serializers.ChoiceField(choices=BackupFrequency.choices)
    schedule_time = serializers.TimeField(required=False, allow_null=True)
    day_of_week = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=6)
    day_of_month = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=28)
    timezone = serializers.CharField(max_length=64)
    storage_target_id = serializers.UUIDField()
    retention_policy_id = serializers.UUIDField()
    description = serializers.CharField(required=False, allow_blank=True)


class BackupScheduleUpdateSerializer(BackupScheduleCreateSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


class ScheduleRunNowSerializer(StrictInputSerializer):
    idempotency_key = serializers.CharField(max_length=128)


class BackupRetentionPolicyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupRetentionPolicy
        fields = (
            "id",
            "name",
            "description",
            "archive_after_days",
            "retention_days",
            "keep_last_successful",
            "is_active",
            "created_at",
            "updated_at",
        )


class BackupRetentionPolicyDetailSerializer(serializers.ModelSerializer):
    allowed_commands = serializers.SerializerMethodField()

    class Meta:
        model = BackupRetentionPolicy
        exclude = ("tenant_id", "is_deleted", "deleted_at")

    def get_allowed_commands(self, obj: BackupRetentionPolicy) -> dict[str, dict[str, object]]:
        del obj
        return {command: {"allowed": True} for command in ("update", "delete", "activate")}


class BackupRetentionPolicyCreateSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True)
    archive_after_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    retention_days = serializers.IntegerField(min_value=1, max_value=3650)
    keep_last_successful = serializers.IntegerField(required=False, default=3, min_value=1)

    def validate(self, attrs):
        archive_after = attrs.get("archive_after_days")
        if archive_after is not None and "retention_days" in attrs and archive_after >= attrs["retention_days"]:
            raise serializers.ValidationError({"archive_after_days": "Must be less than retention days."})
        return attrs


class BackupRetentionPolicyUpdateSerializer(BackupRetentionPolicyCreateSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


class RetentionPreviewSerializer(serializers.Serializer):
    captured_at = serializers.DateTimeField()
    archive_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField()
    keep_last_successful = serializers.IntegerField()
    retention_days = serializers.IntegerField()
    archive_after_days = serializers.IntegerField(allow_null=True)


class BackupStorageTargetListSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupStorageTarget
        fields = ("id", "name", "adapter_key", "is_default", "is_active", "created_at", "updated_at")


class BackupStorageTargetDetailSerializer(serializers.ModelSerializer):
    allowed_commands = serializers.SerializerMethodField()

    class Meta:
        model = BackupStorageTarget
        exclude = ("tenant_id", "is_deleted", "deleted_at")

    def get_allowed_commands(self, obj: BackupStorageTarget) -> dict[str, dict[str, object]]:
        commands = ("update", "delete", "probe") + (("set_default",) if obj.is_active and not obj.is_default else ())
        return {command: {"allowed": True} for command in commands}


class BackupStorageTargetCreateSerializer(StrictInputSerializer):
    name = serializers.CharField(max_length=120)
    adapter_key = serializers.RegexField(r"^[a-z0-9]+(?:[-_.][a-z0-9]+)*$", max_length=120)
    locator_prefix_ref = serializers.CharField(max_length=1024)
    configuration_ref = serializers.CharField(max_length=255)
    encryption_key_ref = serializers.CharField(required=False, allow_blank=True, max_length=255)
    is_default = serializers.BooleanField(required=False, default=False)
    is_active = serializers.BooleanField(required=False, default=True)


class BackupStorageTargetUpdateSerializer(BackupStorageTargetCreateSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False


class StorageTargetProbeSerializer(serializers.Serializer):
    healthy = serializers.BooleanField()
    message = serializers.CharField()
    checked_at = serializers.DateTimeField()
    details = serializers.DictField()


class BackupArchiveListSerializer(serializers.ModelSerializer):
    artifact_locator_ref = serializers.SerializerMethodField()
    backup_type = serializers.CharField(source="backup_job.backup_type", read_only=True)

    class Meta:
        model = BackupArchive
        fields = (
            "id",
            "backup_job",
            "backup_type",
            "lifecycle",
            "adapter_key",
            "artifact_locator_ref",
            "size_bytes",
            "checksum_algorithm",
            "captured_at",
            "expires_at",
            "integrity_status",
            "last_verified_at",
        )

    def get_artifact_locator_ref(self, obj: BackupArchive) -> str:
        if not _reference_is_safe(obj.artifact_locator_ref):
            return "*** / redacted-reference"
        return f"*** / {PurePath(obj.artifact_locator_ref).name}"


class BackupArchiveDetailSerializer(serializers.ModelSerializer):
    backup_type = serializers.CharField(source="backup_job.backup_type", read_only=True)
    scope_type = serializers.CharField(source="backup_job.scope_type", read_only=True)
    scope_ref = serializers.CharField(source="backup_job.scope_ref", read_only=True)
    artifact_locator_ref = serializers.SerializerMethodField()
    provider_acknowledgement = serializers.SerializerMethodField()
    allowed_commands = serializers.SerializerMethodField()

    class Meta:
        model = BackupArchive
        exclude = (
            "tenant_id",
            "encryption_key_ref",
            "purge_async_job_id",
            "purge_idempotency_key",
        )

    def get_allowed_commands(self, obj: BackupArchive) -> dict[str, dict[str, object]]:
        return {"verify": {"allowed": obj.lifecycle == "available"}}

    def get_artifact_locator_ref(self, obj: BackupArchive) -> str:
        return obj.artifact_locator_ref if _reference_is_safe(obj.artifact_locator_ref) else "redacted-reference"

    def get_provider_acknowledgement(self, obj: BackupArchive) -> str:
        value = obj.provider_acknowledgement
        return value if _reference_is_safe(value) else "redacted-reference"


class BackupVerificationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupVerification
        fields = (
            "id",
            "archive",
            "status",
            "requested_at",
            "started_at",
            "completed_at",
            "checksum_matches",
            "artifact_available",
            "error_code",
        )


class BackupVerificationDetailSerializer(serializers.ModelSerializer):
    allowed_commands = serializers.SerializerMethodField()
    correlation_id = serializers.SerializerMethodField()

    class Meta:
        model = BackupVerification
        exclude = ("tenant_id",)

    def get_allowed_commands(self, obj: BackupVerification) -> dict[str, dict[str, object]]:
        return {"cancel": {"allowed": obj.status in ("pending", "running")}}

    def get_correlation_id(self, obj: BackupVerification) -> str | None:
        if obj.async_job_id is None:
            return None
        return (
            AsyncJob.objects.filter(tenant_id=obj.tenant_id, pk=obj.async_job_id)
            .values_list("correlation_id", flat=True)
            .first()
        )


class BackupVerificationCreateSerializer(StrictInputSerializer):
    idempotency_key = serializers.CharField(max_length=128)


class BackupVerificationCancelSerializer(StrictInputSerializer):
    transition_key = serializers.CharField(max_length=128)


class ModuleHealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unavailable"))
    ready = serializers.BooleanField()
    checked_at = serializers.DateTimeField()
    database = serializers.DictField()
    async_jobs = serializers.DictField()
    outbox = serializers.DictField()
    scheduler = serializers.DictField()
    adapters = serializers.ListField(child=serializers.DictField())
    oldest_pending_outbox_seconds = serializers.IntegerField(allow_null=True, required=False)
