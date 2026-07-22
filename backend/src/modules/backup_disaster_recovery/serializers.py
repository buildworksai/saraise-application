"""Strict request and response serializers for the governed v2 API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

from .models import (
    BackupType,
    BDRConfiguration,
    BDRConfigurationVersion,
    DRExercise,
    DRRunbook,
    DRStepExecution,
    ExerciseEnvironment,
    ExerciseType,
    RecoveryPoint,
    RestoreMode,
    RestoreRun,
    RunbookActionType,
    RunbookStep,
    ScopeType,
    StepFailureBehavior,
    TargetEnvironment,
)


class TrimmedCharField(serializers.CharField):
    """A non-blank string normalized before it reaches domain services."""

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data).strip()
        if not value:
            self.fail("blank")
        return value


class BackupExecutionCreateSerializer(serializers.Serializer[dict[str, Any]]):
    backup_type = serializers.ChoiceField(choices=BackupType.choices)
    scope_type = serializers.ChoiceField(choices=ScopeType.choices)
    scope_ref = TrimmedCharField(max_length=255)
    idempotency_key = TrimmedCharField(max_length=255)


class BackupExecutionReceiptSerializer(serializers.Serializer[dict[str, Any]]):
    backup_job_id = serializers.UUIDField(read_only=True)
    async_job_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    requested_at = serializers.DateTimeField(read_only=True)


class BackupExecutionStatusSerializer(serializers.Serializer[dict[str, Any]]):
    backup_job_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    error_code = serializers.CharField(read_only=True, allow_blank=True)
    safe_error = serializers.CharField(read_only=True, allow_blank=True)
    recovery_point_id = serializers.UUIDField(read_only=True, allow_null=True)


class RecoveryPointListSerializer(serializers.ModelSerializer[RecoveryPoint]):
    class Meta:
        model = RecoveryPoint
        fields = (
            "id",
            "backup_job_id",
            "backup_archive_id",
            "scope_type",
            "scope_ref",
            "backup_type",
            "status",
            "data_cutoff_at",
            "captured_at",
            "verified_at",
            "expires_at",
            "size_bytes",
            "created_at",
        )
        read_only_fields = fields


class RecoveryPointDetailSerializer(RecoveryPointListSerializer):
    verification_evidence = serializers.SerializerMethodField()

    class Meta(RecoveryPointListSerializer.Meta):
        fields = RecoveryPointListSerializer.Meta.fields + (
            "checksum_algorithm",
            "checksum_digest",
            "verification_evidence",
            "updated_at",
        )
        read_only_fields = fields

    def get_verification_evidence(self, obj: RecoveryPoint) -> dict[str, object] | None:
        event = obj.latest_verification_evidence
        raw = event.evidence if event is not None else obj.verification_evidence
        if not raw:
            return None
        return {
            "kind": "artifact_validation",
            "checksum_valid": bool(raw.get("checksum_matches", False)),
            "artifact_available": bool(raw.get("artifact_available", False)),
            "encryption_metadata_valid": bool(raw.get("encryption_metadata_valid", False)),
            "provider_acknowledged": bool(raw.get("provider_acknowledged", False)),
            "checked_at": event.created_at if event is not None else obj.updated_at,
        }


class RecoveryPointVerifySerializer(serializers.Serializer[dict[str, Any]]):
    idempotency_key = TrimmedCharField(max_length=255)


class RestoreRunListSerializer(serializers.ModelSerializer[RestoreRun]):
    recovery_point_id = serializers.UUIDField(read_only=True)
    runbook_id = serializers.UUIDField(read_only=True, allow_null=True)
    exercise_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = RestoreRun
        fields = (
            "id",
            "recovery_point_id",
            "runbook_id",
            "exercise_id",
            "target_environment",
            "target_ref",
            "restore_mode",
            "status",
            "requested_at",
            "started_at",
            "completed_at",
            "achieved_rpo_seconds",
            "achieved_rto_seconds",
        )
        read_only_fields = fields


class RestoreRunDetailSerializer(RestoreRunListSerializer):
    class Meta(RestoreRunListSerializer.Meta):
        fields = RestoreRunListSerializer.Meta.fields + (
            "selected_components",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RestoreRunCreateSerializer(serializers.Serializer[dict[str, Any]]):
    recovery_point_id = serializers.UUIDField()
    runbook_id = serializers.UUIDField(required=False, allow_null=True)
    exercise_id = serializers.UUIDField(required=False, allow_null=True)
    target_environment = serializers.ChoiceField(choices=TargetEnvironment.choices)
    target_ref = TrimmedCharField(max_length=255)
    restore_mode = serializers.ChoiceField(choices=RestoreMode.choices)
    selected_components = serializers.ListField(
        child=serializers.RegexField(r"^[a-z][a-z0-9_.-]{0,119}$"),
        required=False,
        allow_empty=True,
    )
    idempotency_key = TrimmedCharField(max_length=255)
    step_up_token = TrimmedCharField(max_length=512, required=False, write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        mode = attrs["restore_mode"]
        components = attrs.get("selected_components", [])
        if mode == RestoreMode.SELECTIVE and not components:
            raise serializers.ValidationError(
                {"selected_components": "Selective restores require at least one component."}
            )
        if mode == RestoreMode.FULL and components:
            raise serializers.ValidationError(
                {"selected_components": "Full restores cannot select individual components."}
            )
        if len(set(components)) != len(components):
            raise serializers.ValidationError({"selected_components": "Component names must be unique."})
        return attrs


class RestoreRunExecuteSerializer(serializers.Serializer[dict[str, Any]]):
    idempotency_key = TrimmedCharField(max_length=255)


class RestoreRunCancelSerializer(serializers.Serializer[dict[str, Any]]):
    transition_key = TrimmedCharField(max_length=255)


class RunbookStepListSerializer(serializers.ModelSerializer[RunbookStep]):
    runbook_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RunbookStep
        fields = (
            "id",
            "runbook_id",
            "step_key",
            "position",
            "name",
            "action_type",
            "timeout_seconds",
            "retry_limit",
            "on_failure",
        )
        read_only_fields = fields


class RunbookStepDetailSerializer(RunbookStepListSerializer):
    class Meta(RunbookStepListSerializer.Meta):
        fields = RunbookStepListSerializer.Meta.fields + (
            "description",
            "extension_action_key",
            "parameters",
            "approval_permission",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DRRunbookListSerializer(serializers.ModelSerializer[DRRunbook]):
    class Meta:
        model = DRRunbook
        fields = (
            "id",
            "name",
            "slug",
            "version",
            "status",
            "scope_type",
            "scope_ref",
            "rpo_target_seconds",
            "rto_target_seconds",
            "published_at",
            "updated_at",
        )
        read_only_fields = fields


class DRRunbookDetailSerializer(DRRunbookListSerializer):
    steps = serializers.SerializerMethodField()
    supersedes_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta(DRRunbookListSerializer.Meta):
        fields = DRRunbookListSerializer.Meta.fields + (
            "description",
            "backup_schedule_id",
            "supersedes_id",
            "retired_at",
            "created_at",
            "steps",
        )
        read_only_fields = fields

    def get_steps(self, obj: DRRunbook) -> list[dict[str, Any]]:
        queryset = obj.steps.filter(deleted_at__isnull=True).order_by("position")
        return list(RunbookStepDetailSerializer(queryset, many=True).data)


class DRRunbookCreateSerializer(serializers.Serializer[dict[str, Any]]):
    name = TrimmedCharField(max_length=255)
    slug = serializers.SlugField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    scope_type = serializers.ChoiceField(choices=ScopeType.choices)
    scope_ref = TrimmedCharField(max_length=255)
    backup_schedule_id = serializers.UUIDField(required=False, allow_null=True)
    rpo_target_seconds = serializers.IntegerField(min_value=1)
    rto_target_seconds = serializers.IntegerField(min_value=1)

    def validate_slug(self, value: str) -> str:
        return value.lower()


class DRRunbookUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    name = TrimmedCharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    scope_type = serializers.ChoiceField(choices=ScopeType.choices, required=False)
    scope_ref = TrimmedCharField(max_length=255, required=False)
    backup_schedule_id = serializers.UUIDField(required=False, allow_null=True)
    rpo_target_seconds = serializers.IntegerField(min_value=1, required=False)
    rto_target_seconds = serializers.IntegerField(min_value=1, required=False)


class DRRunbookCloneSerializer(serializers.Serializer[dict[str, Any]]):
    name = TrimmedCharField(max_length=255, required=False)


class _ValidateParametersSerializer(serializers.Serializer[dict[str, Any]]):
    require_checksum = serializers.BooleanField(default=True)
    require_encryption = serializers.BooleanField(default=True)


class _RestoreParametersSerializer(serializers.Serializer[dict[str, Any]]):
    restore_mode = serializers.ChoiceField(choices=RestoreMode.choices)
    selected_components = serializers.ListField(
        child=serializers.RegexField(r"^[a-z][a-z0-9_.-]{0,119}$"),
        required=False,
    )


class _VerifyParametersSerializer(serializers.Serializer[dict[str, Any]]):
    checks = serializers.ListField(
        child=TrimmedCharField(max_length=64),
        min_length=1,
    )


class _FailoverParametersSerializer(serializers.Serializer[dict[str, Any]]):
    target_ref = TrimmedCharField(max_length=255)


class _ApprovalParametersSerializer(serializers.Serializer[dict[str, Any]]):
    instructions = TrimmedCharField(max_length=2000)


class _NotifyParametersSerializer(serializers.Serializer[dict[str, Any]]):
    channel_ref = TrimmedCharField(max_length=255)
    message_template = TrimmedCharField(max_length=2000)


class _ExtensionParametersSerializer(serializers.Serializer[dict[str, Any]]):
    configuration_ref = TrimmedCharField(max_length=255)


_PARAMETER_SERIALIZERS: dict[str, type[serializers.Serializer[dict[str, Any]]]] = {
    RunbookActionType.VALIDATE_RECOVERY_POINT: _ValidateParametersSerializer,
    RunbookActionType.RESTORE: _RestoreParametersSerializer,
    RunbookActionType.VERIFY: _VerifyParametersSerializer,
    RunbookActionType.FAILOVER: _FailoverParametersSerializer,
    RunbookActionType.FAILBACK: _FailoverParametersSerializer,
    RunbookActionType.MANUAL_APPROVAL: _ApprovalParametersSerializer,
    RunbookActionType.NOTIFY: _NotifyParametersSerializer,
    RunbookActionType.EXTENSION: _ExtensionParametersSerializer,
}


class RunbookStepParametersField(serializers.Field[dict[str, Any], Mapping[str, Any], dict[str, Any], object]):
    """Reject opaque parameter bags; validation is selected by action type."""

    def to_representation(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return dict(value)

    def to_internal_value(self, data: object) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise serializers.ValidationError("Step parameters must be an object.")
        return dict(data)


class _RunbookStepWriteSerializer(serializers.Serializer[dict[str, Any]]):
    step_key = serializers.SlugField(max_length=80, required=False)
    position = serializers.IntegerField(min_value=1, required=False)
    name = TrimmedCharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    action_type = serializers.ChoiceField(choices=RunbookActionType.choices, required=False)
    extension_action_key = serializers.SlugField(max_length=120, required=False, allow_null=True, allow_blank=True)
    parameters = RunbookStepParametersField(required=False)
    timeout_seconds = serializers.IntegerField(min_value=1, required=False)
    retry_limit = serializers.IntegerField(min_value=0, required=False)
    on_failure = serializers.ChoiceField(choices=StepFailureBehavior.choices, required=False)
    approval_permission = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = getattr(self, "instance", None)
        action_type = attrs.get("action_type", getattr(instance, "action_type", None))
        parameters = attrs.get("parameters", getattr(instance, "parameters", None))
        extension_key = attrs.get("extension_action_key", getattr(instance, "extension_action_key", None))
        approval_permission = attrs.get("approval_permission", getattr(instance, "approval_permission", None))
        if not action_type:
            raise serializers.ValidationError({"action_type": "This field is required."})
        if parameters is None:
            raise serializers.ValidationError({"parameters": "This field is required."})
        validator = _PARAMETER_SERIALIZERS[str(action_type)](data=parameters)
        validator.is_valid(raise_exception=True)
        attrs["parameters"] = validator.validated_data
        if action_type == RunbookActionType.EXTENSION and not extension_key:
            raise serializers.ValidationError(
                {"extension_action_key": "Extension actions require a registered action key."}
            )
        if action_type != RunbookActionType.EXTENSION and extension_key:
            raise serializers.ValidationError(
                {"extension_action_key": "Only extension actions accept an extension action key."}
            )
        if action_type == RunbookActionType.MANUAL_APPROVAL and not approval_permission:
            raise serializers.ValidationError({"approval_permission": "Manual approvals require a permission."})
        return attrs


class RunbookStepCreateSerializer(_RunbookStepWriteSerializer):
    runbook_id = serializers.UUIDField()
    step_key = serializers.SlugField(max_length=80)
    position = serializers.IntegerField(min_value=1)
    name = TrimmedCharField(max_length=255)
    action_type = serializers.ChoiceField(choices=RunbookActionType.choices)
    parameters = RunbookStepParametersField()
    timeout_seconds = serializers.IntegerField(min_value=1, required=False)
    retry_limit = serializers.IntegerField(min_value=0, required=False)
    on_failure = serializers.ChoiceField(choices=StepFailureBehavior.choices, required=False)


class RunbookStepUpdateSerializer(_RunbookStepWriteSerializer):
    pass


class RunbookStepReorderSerializer(serializers.Serializer[dict[str, Any]]):
    step_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)

    def validate_step_ids(self, value: list[Any]) -> list[Any]:
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Step identifiers must be unique.")
        return value


class DRExerciseListSerializer(serializers.ModelSerializer[DRExercise]):
    runbook_id = serializers.UUIDField(read_only=True)
    recovery_point_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = DRExercise
        fields = (
            "id",
            "name",
            "runbook_id",
            "recovery_point_id",
            "exercise_type",
            "environment",
            "status",
            "scheduled_for",
            "started_at",
            "completed_at",
            "rpo_met",
            "rto_met",
            "created_at",
        )
        read_only_fields = fields


class DRExerciseDetailSerializer(DRExerciseListSerializer):
    class Meta(DRExerciseListSerializer.Meta):
        fields = DRExerciseListSerializer.Meta.fields + (
            "summary",
            "observed_rpo_seconds",
            "observed_rto_seconds",
            "failed_step_id",
            "updated_at",
        )
        read_only_fields = fields


class DRExerciseCreateSerializer(serializers.Serializer[dict[str, Any]]):
    name = TrimmedCharField(max_length=255)
    runbook_id = serializers.UUIDField()
    recovery_point_id = serializers.UUIDField(required=False, allow_null=True)
    exercise_type = serializers.ChoiceField(choices=ExerciseType.choices)
    environment = serializers.ChoiceField(choices=ExerciseEnvironment.choices)
    scheduled_for = serializers.DateTimeField()
    idempotency_key = TrimmedCharField(max_length=255)


class DRExerciseUpdateSerializer(serializers.Serializer[dict[str, Any]]):
    name = TrimmedCharField(max_length=255, required=False)
    recovery_point_id = serializers.UUIDField(required=False, allow_null=True)
    exercise_type = serializers.ChoiceField(choices=ExerciseType.choices, required=False)
    environment = serializers.ChoiceField(choices=ExerciseEnvironment.choices, required=False)
    scheduled_for = serializers.DateTimeField(required=False)


class DRExerciseStartSerializer(serializers.Serializer[dict[str, Any]]):
    idempotency_key = TrimmedCharField(max_length=255)


class DRExerciseCancelSerializer(serializers.Serializer[dict[str, Any]]):
    transition_key = TrimmedCharField(max_length=255)


class DRStepExecutionListSerializer(serializers.ModelSerializer[DRStepExecution]):
    exercise_id = serializers.UUIDField(read_only=True)
    runbook_step_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = DRStepExecution
        fields = (
            "id",
            "exercise_id",
            "runbook_step_id",
            "status",
            "attempt",
            "started_at",
            "completed_at",
            "created_at",
        )
        read_only_fields = fields


class DRStepExecutionDetailSerializer(DRStepExecutionListSerializer):
    class Meta(DRStepExecutionListSerializer.Meta):
        fields = DRStepExecutionListSerializer.Meta.fields + ("updated_at",)
        read_only_fields = fields


class ObjectiveReportQuerySerializer(serializers.Serializer[dict[str, Any]]):
    runbook_id = serializers.UUIDField(required=False)
    from_at = serializers.DateTimeField(required=False, source="from")
    to = serializers.DateTimeField(required=False)
    bucket = serializers.CharField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start = attrs.get("from")
        end = attrs.get("to")
        if start and end and start >= end:
            raise serializers.ValidationError({"to": "Must be later than from."})
        return attrs


class ObjectiveMeasurementSerializer(serializers.Serializer[dict[str, Any]]):
    restore_run_id = serializers.UUIDField()
    runbook_id = serializers.UUIDField(allow_null=True)
    rpo_seconds = serializers.IntegerField(min_value=0, allow_null=True)
    rto_seconds = serializers.IntegerField(min_value=0, allow_null=True)
    rpo_target_seconds = serializers.IntegerField(min_value=1, allow_null=True)
    rto_target_seconds = serializers.IntegerField(min_value=1, allow_null=True)
    rpo_met = serializers.BooleanField(allow_null=True)
    rto_met = serializers.BooleanField(allow_null=True)
    measured_at = serializers.DateTimeField()
    outcome = serializers.ChoiceField(choices=("succeeded", "failed"))


class ObjectiveBucketSerializer(serializers.Serializer[dict[str, Any]]):
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    runbook_id = serializers.UUIDField()
    runbook_name = serializers.CharField()
    runbook_version = serializers.IntegerField(min_value=1)
    restore_count = serializers.IntegerField(min_value=0)
    failed_restore_count = serializers.IntegerField(min_value=0)
    rpo_compliance_percent = serializers.FloatField(min_value=0, max_value=100)
    rto_compliance_percent = serializers.FloatField(min_value=0, max_value=100)
    measurements = ObjectiveMeasurementSerializer(many=True)


class ObjectiveReportSerializer(serializers.Serializer[dict[str, Any]]):
    from_at = serializers.DateTimeField()
    to = serializers.DateTimeField()
    bucket = serializers.CharField()
    total_restores = serializers.IntegerField(min_value=0)
    failed_restores = serializers.IntegerField(min_value=0)
    rpo_compliance_percent = serializers.FloatField(min_value=0, max_value=100)
    rto_compliance_percent = serializers.FloatField(min_value=0, max_value=100)
    buckets = ObjectiveBucketSerializer(many=True)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)
        data["from"] = data.pop("from_at")
        return data


class ReadinessSummarySerializer(serializers.Serializer[dict[str, Any]]):
    calculated_at = serializers.DateTimeField()
    rpo_compliance_percent = serializers.FloatField(min_value=0, max_value=100)
    rto_compliance_percent = serializers.FloatField(min_value=0, max_value=100)
    last_verified_recovery_point = RecoveryPointListSerializer(allow_null=True)
    latest_passed_exercise = DRExerciseListSerializer(allow_null=True)
    latest_successful_restore = RestoreRunListSerializer(allow_null=True)
    latest_failed_restore = RestoreRunListSerializer(allow_null=True)
    next_scheduled_exercise = DRExerciseListSerializer(allow_null=True)
    stale_runbook_count = serializers.IntegerField(min_value=0)
    unpublished_runbook_count = serializers.IntegerField(min_value=0)
    current_rpo_breaches = serializers.IntegerField(min_value=0)
    current_rto_breaches = serializers.IntegerField(min_value=0)
    provider_state = serializers.ChoiceField(choices=("operational", "degraded", "unavailable"))
    queue_state = serializers.ChoiceField(choices=("operational", "degraded", "unavailable"))
    provider_message = serializers.CharField(allow_blank=True)


class BDRConfigurationSerializer(serializers.ModelSerializer[BDRConfiguration]):
    class Meta:
        model = BDRConfiguration
        fields = ("id", "tenant_id", "environment", "version", "document", "rollout", "updated_at")
        read_only_fields = fields


class BDRConfigurationWriteSerializer(serializers.Serializer[dict[str, Any]]):
    environment = TrimmedCharField(max_length=64, required=False, default="default")
    document = serializers.JSONField()
    rollout = serializers.JSONField(required=False)


class BDRConfigurationRollbackSerializer(serializers.Serializer[dict[str, Any]]):
    environment = TrimmedCharField(max_length=64, required=False, default="default")
    version = serializers.IntegerField(min_value=1)


class BDRConfigurationVersionSerializer(serializers.ModelSerializer[BDRConfigurationVersion]):
    rollback_of = serializers.UUIDField(source="rollback_of_id", read_only=True, allow_null=True)

    class Meta:
        model = BDRConfigurationVersion
        fields = (
            "id",
            "version",
            "actor_id",
            "correlation_id",
            "prior_value",
            "new_value",
            "rollback_of",
            "created_at",
        )
        read_only_fields = fields


__all__ = [name for name in globals() if name.endswith("Serializer")]
