"""Closed, tenant-safe API v2 serializers for AI Agent Management.

Request serializers deliberately expose identifiers instead of writable model
relations.  Tenant ownership, actor identity, lifecycle state, and evidence
fields are assigned by tenant-first services only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

from src.core.access.entitlements import Quota
from src.core.async_jobs.models import AsyncJob

from .approval_models import ApprovalRequest, SoDPolicy, SoDViolation
from .audit_models import AuditEvent, AuditTrail
from .egress_models import EgressRequest, EgressRule, Secret, SecretAccess
from .models import (
    Agent,
    AgentExecution,
    AgentManagementConfiguration,
    AgentManagementConfigurationVersion,
    AgentSchedulerTask,
)
from .quota_models import KillSwitch, QuotaUsage, ShardSaturation
from .token_models import CostRecord, CostSummary, TokenUsage
from .tool_models import Tool, ToolInvocation


class ClosedSerializer(serializers.Serializer[dict[str, Any]]):
    """Reject unknown request keys instead of silently dropping them."""

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise serializers.ValidationError("Expected a JSON object.")
        unknown = sorted(set(data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError({key: "Unknown field." for key in unknown})
        return super().to_internal_value(data)


class StrictJSONField(serializers.JSONField):
    def __init__(self, *, expected_type: type[dict] | type[list] = dict, **kwargs: Any) -> None:
        self.expected_type = expected_type
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> Any:
        value = super().to_internal_value(data)
        if not isinstance(value, self.expected_type):
            label = "object" if self.expected_type is dict else "array"
            raise serializers.ValidationError(f"Must be a JSON {label}.")
        return value


def _public_transitions(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize internal state-machine keys into the stable public evidence DTO."""

    return [
        {
            "transition": item.get("command", item.get("transition", "unknown")),
            "from": item.get("from_state", item.get("from", "unknown")),
            "to": item.get("to_state", item.get("to", "unknown")),
            "occurred_at": item.get("occurred_at"),
            "reason": (item.get("metadata") or {}).get("reason_code"),
        }
        for item in history
    ]


class AgentListSerializer(serializers.ModelSerializer[Agent]):
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = Agent
        fields = (
            "id", "name", "description", "identity_type", "runner_key",
            "provider_config_id", "status", "created_at", "updated_at",
            "allowed_actions",
        )

    def get_allowed_actions(self, obj: Agent) -> tuple[str, ...]:
        return {
            "draft": ("update", "activate", "retire"),
            "active": ("update", "disable", "retire", "execute"),
            "disabled": ("update", "activate", "retire"),
            "retired": (),
        }[obj.status]


class AgentDetailSerializer(serializers.ModelSerializer[Agent]):
    config = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()
    runner_status = serializers.SerializerMethodField()
    transition_history = serializers.SerializerMethodField()

    class Meta:
        model = Agent
        fields = (
            "id", "name", "description", "identity_type", "subject_id",
            "runner_key", "provider_config_id", "config", "status",
            "transition_history", "created_at", "updated_at", "deleted_at",
            "allowed_actions", "runner_status",
        )
        read_only_fields = fields

    def get_config(self, obj: Agent) -> dict[str, Any]:
        allowed = {
            "schema_version", "budget", "cost_ceiling", "approval", "require_approval", "tools",
            "model", "temperature", "max_tokens", "version",
        }
        return {key: value for key, value in obj.config.items() if key in allowed}

    def get_allowed_actions(self, obj: Agent) -> tuple[str, ...]:
        return AgentListSerializer().get_allowed_actions(obj)

    def get_runner_status(self, obj: Agent) -> str:
        from .registries import runner_registry

        return "available" if runner_registry.get(obj.runner_key) is not None else "unavailable"

    def get_transition_history(self, obj: Agent) -> list[dict[str, Any]]:
        return _public_transitions(obj.transition_history)


class AgentCreateSerializer(ClosedSerializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    identity_type = serializers.ChoiceField(choices=("user_bound", "system_bound"))
    subject_id = serializers.UUIDField()
    session_id = serializers.UUIDField(required=False, allow_null=True)
    runner_key = serializers.CharField(max_length=100)
    provider_config_id = serializers.UUIDField(required=False, allow_null=True)
    config = StrictJSONField(required=False, default=dict)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["identity_type"] == "user_bound" and not attrs.get("session_id"):
            raise serializers.ValidationError({"session_id": "User-bound agents require a session."})
        if attrs["identity_type"] == "system_bound" and attrs.get("session_id"):
            raise serializers.ValidationError({"session_id": "System-bound agents cannot carry a session."})
        return attrs


class AgentUpdateSerializer(ClosedSerializer):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    identity_type = serializers.ChoiceField(choices=("user_bound", "system_bound"), required=False)
    subject_id = serializers.UUIDField(required=False)
    session_id = serializers.UUIDField(required=False, allow_null=True)
    runner_key = serializers.CharField(max_length=100, required=False)
    provider_config_id = serializers.UUIDField(required=False, allow_null=True)
    config = StrictJSONField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.context.get("agent")
        identity = attrs.get("identity_type", getattr(instance, "identity_type", None))
        session = attrs.get("session_id", getattr(instance, "session_id", None))
        if identity == "user_bound" and not session:
            raise serializers.ValidationError({"session_id": "User-bound agents require a session."})
        if identity == "system_bound" and session:
            raise serializers.ValidationError({"session_id": "System-bound agents cannot carry a session."})
        return attrs


class TransitionKeySerializer(ClosedSerializer):
    transition_key = serializers.CharField(max_length=255)
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class ExecuteAgentSerializer(ClosedSerializer):
    task = StrictJSONField()
    input_metadata = StrictJSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(max_length=255)
    schedule_at = serializers.DateTimeField(required=False, allow_null=True)


class EvaluationStartSerializer(ClosedSerializer):
    suite_key = serializers.CharField(max_length=255)
    idempotency_key = serializers.CharField(max_length=255)
    red_team = serializers.BooleanField(required=False, default=False)


class AgentExecutionListSerializer(serializers.ModelSerializer[AgentExecution]):
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = AgentExecution
        fields = (
            "id", "agent_id", "async_job_id", "state", "started_at",
            "completed_at", "error_code", "created_at", "updated_at",
            "allowed_actions",
        )

    def get_allowed_actions(self, obj: AgentExecution) -> tuple[str, ...]:
        return {
            "running": ("pause", "terminate"),
            "paused": ("resume", "terminate"),
            "created": ("terminate",),
            "validated": ("terminate",),
            "queued": ("terminate",),
        }.get(obj.state, ())


class AgentExecutionDetailSerializer(serializers.ModelSerializer[AgentExecution]):
    allowed_actions = serializers.SerializerMethodField()
    transition_history = serializers.SerializerMethodField()

    class Meta:
        model = AgentExecution
        fields = (
            "id", "agent_id", "async_job_id", "state", "transition_history",
            "initiating_actor_id", "started_at", "completed_at", "error_code",
            "error_message", "provider_config_id", "created_at", "updated_at",
            "allowed_actions",
        )
        read_only_fields = fields

    def get_allowed_actions(self, obj: AgentExecution) -> tuple[str, ...]:
        return AgentExecutionListSerializer().get_allowed_actions(obj)

    def get_transition_history(self, obj: AgentExecution) -> list[dict[str, Any]]:
        return _public_transitions(obj.transition_history)


class TransitionExecutionSerializer(TransitionKeySerializer):
    agent_id = serializers.UUIDField(required=False)


class ScheduleCreateSerializer(ClosedSerializer):
    agent_id = serializers.UUIDField()
    scheduled_at = serializers.DateTimeField()
    priority = serializers.IntegerField(required=False)
    max_retries = serializers.IntegerField(required=False)
    task_data = StrictJSONField()
    idempotency_key = serializers.CharField(max_length=255)


class ScheduleSerializer(serializers.ModelSerializer[AgentSchedulerTask]):
    transition_history = serializers.SerializerMethodField()

    class Meta:
        model = AgentSchedulerTask
        exclude = ("tenant_id", "created_by")
        read_only_fields = tuple(field.name for field in AgentSchedulerTask._meta.fields)

    def get_transition_history(self, obj: AgentSchedulerTask) -> list[dict[str, Any]]:
        return _public_transitions(obj.transition_history)


class ApprovalCreateSerializer(ClosedSerializer):
    execution_id = serializers.UUIDField()
    invocation_id = serializers.UUIDField(required=False, allow_null=True)
    tool_id = serializers.UUIDField()
    requested_for = serializers.UUIDField()
    tool_input = StrictJSONField()
    justification = serializers.CharField(required=False, allow_blank=True, default="")
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    metadata = StrictJSONField(required=False, default=dict)


class ApprovalDecisionSerializer(ClosedSerializer):
    transition_key = serializers.CharField(max_length=255)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class ApprovalRequestSerializer(serializers.ModelSerializer[ApprovalRequest]):
    allowed_actions = serializers.SerializerMethodField()
    transition_history = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = (
            "id", "tool_id", "agent_execution_id", "tool_invocation_id",
            "requested_by", "requested_for", "approver_id", "status",
            "transition_history", "justification", "rejection_reason",
            "requested_at", "expires_at", "decided_at", "created_at", "updated_at",
            "allowed_actions",
        )
        read_only_fields = fields

    def get_allowed_actions(self, obj: ApprovalRequest) -> tuple[str, ...]:
        return ("approve", "reject", "cancel") if obj.status == "pending" else ()

    def get_transition_history(self, obj: ApprovalRequest) -> list[dict[str, Any]]:
        return _public_transitions(obj.transition_history)


class SoDPolicyWriteSerializer(ClosedSerializer):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    action_1 = serializers.CharField(max_length=255, required=False)
    action_2 = serializers.CharField(max_length=255, required=False)
    is_active = serializers.BooleanField(required=False)


class ToolWriteSerializer(ClosedSerializer):
    name = serializers.CharField(max_length=255, required=False)
    owning_module = serializers.CharField(max_length=100, required=False)
    version = serializers.CharField(max_length=50, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    required_permissions = StrictJSONField(expected_type=list, required=False)
    input_schema = StrictJSONField(required=False)
    output_schema = StrictJSONField(required=False)
    side_effect_class = serializers.ChoiceField(choices=("read_only", "workflow_transition", "data_mutation", "external_integration"), required=False)
    is_active = serializers.BooleanField(required=False)
    metadata = StrictJSONField(required=False)


class ToolValidationSerializer(ClosedSerializer):
    direction = serializers.ChoiceField(choices=("input", "output"))
    value = StrictJSONField()


class EgressRuleWriteSerializer(ClosedSerializer):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    destination_type = serializers.ChoiceField(choices=("domain", "ip", "cidr", "url_pattern"), required=False)
    destination = serializers.CharField(max_length=500, required=False)
    port = serializers.IntegerField(min_value=1, max_value=65535, required=False, allow_null=True)
    protocol = serializers.ChoiceField(choices=("http", "https", "tcp", "udp"), required=False)
    is_active = serializers.BooleanField(required=False)


class SecretCreateSerializer(ClosedSerializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    secret_type = serializers.ChoiceField(choices=("api_key", "password", "token", "certificate", "other"))
    plaintext = serializers.CharField(trim_whitespace=False, write_only=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    rotation_interval_days = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class SecretRotateSerializer(ClosedSerializer):
    plaintext = serializers.CharField(trim_whitespace=False, write_only=True)
    idempotency_key = serializers.CharField(max_length=255)


class SecretMetadataSerializer(serializers.ModelSerializer[Secret]):
    class Meta:
        model = Secret
        fields = ("id", "name", "description", "secret_type", "is_active", "expires_at", "last_rotated_at", "rotation_interval_days", "created_at", "updated_at")
        read_only_fields = fields


class KillSwitchActivateSerializer(ClosedSerializer):
    name = serializers.CharField(max_length=255, required=False, default="Emergency control")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    scope = serializers.ChoiceField(choices=("tenant", "shard", "agent"))
    scope_id = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=2000)
    transition_key = serializers.CharField(max_length=255)


class KillSwitchDeactivateSerializer(ClosedSerializer):
    reason = serializers.CharField(max_length=2000)
    transition_key = serializers.CharField(max_length=255)


class CostRecalculationSerializer(ClosedSerializer):
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    period_type = serializers.ChoiceField(choices=("hourly", "daily", "weekly", "monthly"))
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    idempotency_key = serializers.CharField(max_length=255)


def evidence_serializer(name: str, model: type, *, exclude: tuple[str, ...] = ("tenant_id",)) -> type[serializers.ModelSerializer]:
    meta = type("Meta", (), {"model": model, "exclude": exclude, "read_only_fields": tuple(field.name for field in model._meta.fields)})
    return type(name, (serializers.ModelSerializer,), {"Meta": meta, "__module__": __name__})


SoDPolicySerializer = evidence_serializer("SoDPolicySerializer", SoDPolicy)
SoDViolationSerializer = evidence_serializer("SoDViolationSerializer", SoDViolation)
ToolSerializer = evidence_serializer("ToolSerializer", Tool)
class ToolInvocationSerializer(serializers.ModelSerializer[ToolInvocation]):
    class Meta:
        model = ToolInvocation
        fields = (
            "id", "tool_id", "agent_execution_id", "approval_request_id", "status",
            "transition_history", "error_code", "error_message", "invoked_at",
            "completed_at", "duration_ms", "created_at", "updated_at",
        )
        read_only_fields = fields
EgressRuleSerializer = evidence_serializer("EgressRuleSerializer", EgressRule)
EgressRequestSerializer = evidence_serializer("EgressRequestSerializer", EgressRequest)
SecretAccessSerializer = evidence_serializer("SecretAccessSerializer", SecretAccess)
QuotaSerializer = evidence_serializer("QuotaSerializer", Quota)
QuotaUsageSerializer = evidence_serializer("QuotaUsageSerializer", QuotaUsage)
ShardSaturationSerializer = evidence_serializer("ShardSaturationSerializer", ShardSaturation)
KillSwitchSerializer = evidence_serializer("KillSwitchSerializer", KillSwitch)
TokenUsageSerializer = evidence_serializer("TokenUsageSerializer", TokenUsage)
class CostRecordSerializer(serializers.ModelSerializer[CostRecord]):
    pricing_available = serializers.SerializerMethodField()

    class Meta:
        model = CostRecord
        exclude = ("tenant_id", "metadata")
        read_only_fields = tuple(field.name for field in CostRecord._meta.fields)

    def get_pricing_available(self, obj: CostRecord) -> bool:
        # A record is only persisted after versioned pricing resolves; unknown
        # pricing returns 503/unavailable and creates no cost record.
        return bool(obj.pricing_version)
CostSummarySerializer = evidence_serializer("CostSummarySerializer", CostSummary)
AuditEventSerializer = evidence_serializer("AuditEventSerializer", AuditEvent)
class AuditTrailSerializer(serializers.ModelSerializer[AuditTrail]):
    events = serializers.SerializerMethodField()
    completed_timestamp = serializers.SerializerMethodField()
    final_outcome = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = AuditTrail
        fields = (
            "id", "request_id", "correlation_id", "agent_execution_id",
            "initiating_principal", "request_timestamp", "completed_timestamp",
            "final_outcome", "summary", "events", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_events(self, obj: AuditTrail) -> list[dict[str, Any]]:
        events = [
            link.audit_event
            for link in obj.ordered_events.select_related("audit_event").order_by("position", "id")
        ]
        return AuditEventSerializer(events, many=True).data

    def _completion(self, obj: AuditTrail) -> AuditEvent | None:
        return obj.events.filter(event_type="audit_trail_completed").order_by("-event_timestamp", "id").first()

    def get_completed_timestamp(self, obj: AuditTrail) -> Any:
        event = self._completion(obj)
        return event.event_timestamp if event else None

    def get_final_outcome(self, obj: AuditTrail) -> str | None:
        event = self._completion(obj)
        return str(event.outcome_details.get("final_outcome")) if event else None

    def get_summary(self, obj: AuditTrail) -> dict[str, Any]:
        event = self._completion(obj)
        return dict(event.metadata) if event else {}


class AsyncJobSerializer(serializers.ModelSerializer[AsyncJob]):
    """Sanitized durable-job projection; command payload and actor stay private."""

    class Meta:
        model = AsyncJob
        fields = (
            "id", "status", "attempts",
            "correlation_id", "started_at", "completed_at", "created_at", "updated_at",
        )
        read_only_fields = fields


class ConfigurationSerializer(serializers.ModelSerializer[AgentManagementConfiguration]):
    class Meta:
        model = AgentManagementConfiguration
        fields = ("id", "environment", "version", "document", "created_at", "updated_at")
        read_only_fields = fields


class ConfigurationVersionSerializer(serializers.ModelSerializer[AgentManagementConfigurationVersion]):
    class Meta:
        model = AgentManagementConfigurationVersion
        fields = (
            "id",
            "environment",
            "version",
            "previous_document",
            "document",
            "changed_by",
            "correlation_id",
            "change_type",
            "created_at",
        )
        read_only_fields = fields


class ConfigurationWriteSerializer(ClosedSerializer):
    environment = serializers.ChoiceField(
        choices=("development", "staging", "production"),
        required=False,
        default="production",
    )
    expected_version = serializers.IntegerField(min_value=1)
    document = StrictJSONField()


class ConfigurationImportSerializer(ClosedSerializer):
    document = StrictJSONField()


class ConfigurationRollbackSerializer(ClosedSerializer):
    environment = serializers.ChoiceField(
        choices=("development", "staging", "production"),
        required=False,
        default="production",
    )
    target_version = serializers.IntegerField(min_value=1)

# Compatibility aliases for legacy imports while v1 is phased out.
AgentSerializer = AgentDetailSerializer
AgentExecutionSerializer = AgentExecutionDetailSerializer
AgentSchedulerTaskSerializer = ScheduleSerializer
TenantQuotaSerializer = QuotaSerializer
