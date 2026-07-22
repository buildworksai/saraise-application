"""Strict HTTP DTOs for the governed workflow automation API.

Serializers deliberately validate request shape only.  Persistence, tenant
ownership, lifecycle rules, and extension resolution belong to ``services``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from rest_framework import serializers

from .models import Workflow, WorkflowInstance, WorkflowStep, WorkflowTask

MAX_JSON_DEPTH = 12
MAX_JSON_ITEMS = 2_000
MAX_JSON_STRING = 32_768
REJECT_REASON_MAX_LENGTH = 2_000

_SAFE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_FORBIDDEN_KEY = re.compile(
    r"(?:password|passwd|secret|credential|authorization|api[_-]?key|private[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|python|script|model[_-]?label|raw[_-]?email|"
    r"request[_-]?body|response[_-]?body|headers?|url)$",
    re.IGNORECASE,
)
_URL_VALUE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


class StrictSerializer(serializers.Serializer):
    """Reject unknown fields instead of silently accepting contract drift."""

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            self.fail("invalid")
        unknown = sorted(set(data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError(
                {field: ["Unknown field."] for field in unknown},
                code="unknown_field",
            )
        return super().to_internal_value(data)


def validate_json_value(
    value: Any,
    *,
    path: str = "value",
    depth: int = 0,
    counter: list[int] | None = None,
) -> Any:
    """Validate a bounded recursive JSON value and reject secret-like input."""

    if depth > MAX_JSON_DEPTH:
        raise serializers.ValidationError(f"{path} exceeds the maximum nesting depth.")
    count = counter if counter is not None else [0]
    count[0] += 1
    if count[0] > MAX_JSON_ITEMS:
        raise serializers.ValidationError(f"{path} contains too many values.")

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > MAX_JSON_STRING:
            raise serializers.ValidationError(f"{path} contains an oversized string.")
        if _URL_VALUE.match(value.strip()):
            raise serializers.ValidationError(f"{path} must not contain an arbitrary URL.")
        return value
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise serializers.ValidationError(f"{path} object keys must be nonblank strings.")
            if _FORBIDDEN_KEY.search(key):
                raise serializers.ValidationError(f"{path}.{key} is not permitted.")
            output[key] = validate_json_value(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
                counter=count,
            )
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            validate_json_value(item, path=f"{path}[{index}]", depth=depth + 1, counter=count)
            for index, item in enumerate(value)
        ]
    raise serializers.ValidationError(f"{path} contains a non-JSON value.")


class JsonObjectField(serializers.JSONField):
    """An explicit, bounded JSON object field."""

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        value = super().to_internal_value(data)
        if not isinstance(value, dict):
            self.fail("invalid")
        return validate_json_value(value, path=self.field_name or "value")


def _require_exact_keys(config: Mapping[str, Any], *, required: set[str], optional: set[str]) -> None:
    missing = sorted(required - set(config))
    unknown = sorted(set(config) - required - optional)
    errors: dict[str, list[str]] = {}
    if missing:
        errors.update({key: ["This field is required."] for key in missing})
    if unknown:
        errors.update({key: ["Unknown configuration field."] for key in unknown})
    if errors:
        raise serializers.ValidationError(errors)


def _positive_int(value: Any, field: str, *, maximum: int = 31_536_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > maximum:
        raise serializers.ValidationError({field: [f"Must be between 1 and {maximum}."]})
    return value


def validate_step_config(step_type: str, config: Any) -> dict[str, Any]:
    """Apply the discriminated configuration contract for a workflow step."""

    if not isinstance(config, Mapping):
        raise serializers.ValidationError("Step config must be an object.")
    clean = validate_json_value(dict(config), path="config")

    if step_type == "action":
        _require_exact_keys(
            clean,
            required={"handler", "schema_version", "input_mapping"},
            optional={"configuration"},
        )
        if not isinstance(clean["handler"], str) or not _SAFE_KEY.fullmatch(clean["handler"]):
            raise serializers.ValidationError({"handler": ["Use a registered handler key."]})
        if not isinstance(clean["schema_version"], str) or not clean["schema_version"].strip():
            raise serializers.ValidationError({"schema_version": ["A schema version is required."]})
        if not isinstance(clean["input_mapping"], dict):
            raise serializers.ValidationError({"input_mapping": ["Must be an object."]})
        if "configuration" in clean and not isinstance(clean["configuration"], dict):
            raise serializers.ValidationError({"configuration": ["Must be an object."]})
    elif step_type == "approval":
        _require_exact_keys(
            clean,
            required={"assignment_kind", "assignee_id", "rejection_behavior"},
            optional={"due_in_seconds", "reject_step_key", "completion_rule"},
        )
        if clean["assignment_kind"] not in {"user", "role"}:
            raise serializers.ValidationError({"assignment_kind": ["Must be user or role."]})
        if not isinstance(clean["assignee_id"], (str, int)) or not str(clean["assignee_id"]).strip():
            raise serializers.ValidationError({"assignee_id": ["Must identify a selected assignee."]})
        if "due_in_seconds" in clean:
            _positive_int(clean["due_in_seconds"], "due_in_seconds")
        if clean["rejection_behavior"] not in {"fail", "goto", "cancel"}:
            raise serializers.ValidationError({"rejection_behavior": ["Must be fail, goto, or cancel."]})
        if clean["rejection_behavior"] == "goto" and not clean.get("reject_step_key"):
            raise serializers.ValidationError({"reject_step_key": ["Required when rejection_behavior is goto."]})
        if clean.get("completion_rule", "any") not in {"any", "all"}:
            raise serializers.ValidationError({"completion_rule": ["Must be any or all."]})
    elif step_type == "notification":
        _require_exact_keys(clean, required={"channel", "recipient_mapping", "template_key"}, optional=set())
        if clean["channel"] not in {"in_app", "email"}:
            raise serializers.ValidationError({"channel": ["Must be in_app or email."]})
        if not isinstance(clean["recipient_mapping"], dict) or not clean["recipient_mapping"]:
            raise serializers.ValidationError({"recipient_mapping": ["Must be a non-empty object."]})
        if not isinstance(clean["template_key"], str) or not _SAFE_KEY.fullmatch(clean["template_key"]):
            raise serializers.ValidationError({"template_key": ["Use a registered notification template key."]})
    elif step_type == "decision":
        _require_exact_keys(
            clean,
            required={"condition", "true_step_key", "false_step_key"},
            optional={"schema_version"},
        )
        if not isinstance(clean["condition"], dict) or not isinstance(clean["condition"].get("handler"), str):
            raise serializers.ValidationError({"condition": ["Must be a registered condition object."]})
        for key in ("true_step_key", "false_step_key"):
            if not isinstance(clean[key], str) or not _SAFE_KEY.fullmatch(clean[key]):
                raise serializers.ValidationError({key: ["Must reference a valid step key."]})
    else:
        raise serializers.ValidationError("Unsupported step type.")
    return clean


class WorkflowStepWriteSerializer(StrictSerializer):
    key = serializers.RegexField(_SAFE_KEY, max_length=64)
    name = serializers.CharField(max_length=255, trim_whitespace=True, allow_blank=False)
    step_type = serializers.ChoiceField(choices=("action", "approval", "notification", "decision"))
    order = serializers.IntegerField(min_value=1)
    config = JsonObjectField()
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=31_536_000, allow_null=True, required=False)
    timeout_action = serializers.ChoiceField(
        choices=("fail", "notify", "escalate", "cancel"), allow_null=True, required=False
    )
    is_terminal = serializers.BooleanField(default=False, required=False)
    next_step_keys = serializers.ListField(
        child=serializers.RegexField(_SAFE_KEY, max_length=64),
        allow_empty=True,
        required=False,
        default=list,
    )
    join_key = serializers.RegexField(_SAFE_KEY, max_length=64, allow_blank=True, required=False, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        timeout_seconds = attrs.get("timeout_seconds")
        timeout_action = attrs.get("timeout_action")
        if timeout_seconds is None and timeout_action is not None:
            raise serializers.ValidationError({"timeout_action": ["Requires timeout_seconds."]})
        if timeout_seconds is not None and timeout_action is None:
            raise serializers.ValidationError({"timeout_action": ["Required when timeout_seconds is set."]})
        attrs["config"] = validate_step_config(attrs["step_type"], attrs["config"])
        return attrs


class WorkflowStepReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowStep
        fields = (
            "id",
            "key",
            "name",
            "step_type",
            "order",
            "config",
            "timeout_seconds",
            "timeout_action",
            "is_terminal",
            "next_step_keys",
            "join_key",
            "handler_contract_version",
            "handler_contract_fingerprint",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WorkflowListSerializer(serializers.ModelSerializer):
    step_count = serializers.IntegerField(read_only=True, required=False)
    created_by_name = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    @staticmethod
    def get_created_by_name(obj: Workflow) -> str | None:
        user = obj.created_by
        if user is None:
            return None
        full_name = user.get_full_name().strip() if hasattr(user, "get_full_name") else ""
        return full_name or str(user.get_username() if hasattr(user, "get_username") else user)

    @staticmethod
    def get_allowed_actions(obj: Workflow) -> list[str]:
        actions = ["view"]
        if obj.status == "draft":
            actions.extend(("edit", "publish", "delete"))
        elif obj.status == "published":
            actions.extend(("clone", "archive", "start"))
        elif obj.status == "archived":
            actions.append("clone")
        return actions

    class Meta:
        model = Workflow
        fields = (
            "id",
            "key",
            "version",
            "name",
            "description",
            "workflow_type",
            "trigger_type",
            "trigger_config",
            "status",
            "step_count",
            "created_by_name",
            "allowed_actions",
            "created_at",
            "updated_at",
            "published_at",
            "archived_at",
        )
        read_only_fields = fields


class WorkflowDetailSerializer(WorkflowListSerializer):
    steps = WorkflowStepReadSerializer(many=True, read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    published_by = serializers.PrimaryKeyRelatedField(read_only=True)
    transition_history = serializers.SerializerMethodField()
    versions = serializers.SerializerMethodField()
    execution_statistics = serializers.SerializerMethodField()
    handler_health = serializers.SerializerMethodField()

    @staticmethod
    def _transition_values(obj: Workflow) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        correlation_id = ""
        for item in obj.transition_history:
            record = dict(item)
            metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
            record["actor_id"] = metadata.get("actor_id")
            record["correlation_id"] = metadata.get("correlation_id", correlation_id)
            values.append(record)
        return values

    def get_transition_history(self, obj: Workflow) -> list[dict[str, Any]]:
        return self._transition_values(obj)

    @staticmethod
    def get_versions(obj: Workflow) -> list[dict[str, Any]]:
        return list(
            Workflow.objects.for_tenant(obj.tenant_id)
            .filter(key=obj.key, deleted_at__isnull=True)
            .order_by("-version")
            .values("id", "version", "status", "updated_at")
        )

    @staticmethod
    def get_execution_statistics(obj: Workflow) -> dict[str, Any]:
        from django.db.models import Count, Q

        from .models import WorkflowInstance

        totals = WorkflowInstance.objects.for_tenant(obj.tenant_id).filter(workflow=obj).aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(state__in=("pending", "running", "waiting"))),
            completed=Count("id", filter=Q(state="completed")),
            failed=Count("id", filter=Q(state="failed")),
        )
        total = int(totals["total"] or 0)
        completed = int(totals["completed"] or 0)
        return {
            **totals,
            "completion_rate": (completed / total) if total else None,
        }

    @staticmethod
    def get_handler_health(obj: Workflow) -> list[dict[str, Any]]:
        from .extensions import action_registry, condition_registry

        results: list[dict[str, Any]] = []
        for step in WorkflowStep.objects.for_tenant(obj.tenant_id).filter(workflow=obj):
            key = ""
            registry = action_registry
            if step.step_type == "action":
                key = str(step.config.get("handler", ""))
            elif step.step_type == "notification":
                key = {
                    "in_app": "core.in_app_notification.v1",
                    "email": "core.email_notification.v1",
                }.get(str(step.config.get("channel", "")), "")
            elif step.step_type == "decision":
                condition = step.config.get("condition", {})
                key = str(condition.get("handler", "")) if isinstance(condition, Mapping) else ""
                registry = condition_registry
            if not key:
                continue
            availability = "available"
            reason: str | None = None
            try:
                handler = registry.get(key)
                if hasattr(handler, "health") and not handler.health().healthy:
                    availability = "degraded"
                    reason = "Provider health check is unavailable."
            except Exception:
                availability = "degraded"
                reason = "Required provider is not registered."
            results.append({"key": key, "availability": availability, "reason": reason})
        return results

    class Meta(WorkflowListSerializer.Meta):
        fields = WorkflowListSerializer.Meta.fields + (
            "required_context_schema",
            "transition_history",
            "created_by",
            "published_by",
            "steps",
            "versions",
            "execution_statistics",
            "handler_health",
        )
        read_only_fields = fields


class WorkflowDefinitionShapeSerializer(StrictSerializer):
    key = serializers.RegexField(_SAFE_KEY, max_length=64)
    name = serializers.CharField(max_length=255, trim_whitespace=True, allow_blank=False)
    description = serializers.CharField(allow_blank=True, required=False, default="")
    workflow_type = serializers.ChoiceField(
        choices=("approval", "state_machine", "sequential", "parallel", "conditional")
    )
    trigger_type = serializers.ChoiceField(choices=("manual", "event", "scheduled"), default="manual")
    trigger_config = JsonObjectField(required=False, default=dict)
    required_context_schema = JsonObjectField(required=False, default=dict)
    steps = WorkflowStepWriteSerializer(many=True, allow_empty=False)


class WorkflowCreateSerializer(WorkflowDefinitionShapeSerializer):
    pass


class WorkflowUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255, trim_whitespace=True, allow_blank=False, required=False)
    description = serializers.CharField(allow_blank=True, required=False)
    workflow_type = serializers.ChoiceField(
        choices=("approval", "state_machine", "sequential", "parallel", "conditional"), required=False
    )
    trigger_type = serializers.ChoiceField(choices=("manual", "event", "scheduled"), required=False)
    trigger_config = JsonObjectField(required=False)
    required_context_schema = JsonObjectField(required=False)
    steps = WorkflowStepWriteSerializer(many=True, allow_empty=False, required=False)
    expected_updated_at = serializers.DateTimeField(required=True)


class WorkflowDefinitionValidationSerializer(WorkflowDefinitionShapeSerializer):
    pass


class WorkflowPublishSerializer(StrictSerializer):
    transition_key = serializers.CharField(max_length=255, trim_whitespace=True, allow_blank=False)


class WorkflowCloneSerializer(StrictSerializer):
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True, allow_blank=False, required=False)


class WorkflowTaskSummarySerializer(serializers.ModelSerializer):
    instance_id = serializers.UUIDField(read_only=True)
    workflow_id = serializers.UUIDField(source="instance.workflow_id", read_only=True)
    workflow_name = serializers.CharField(source="instance.workflow.name", read_only=True)
    workflow_version = serializers.IntegerField(source="instance.workflow_version", read_only=True)
    step_id = serializers.UUIDField(read_only=True)
    step_name = serializers.CharField(source="step.name", read_only=True)
    assignment_label = serializers.CharField(source="assignment_key", read_only=True)
    subject = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    @staticmethod
    def get_subject(obj: WorkflowTask) -> str | None:
        instance = obj.instance
        return f"{instance.entity_type}:{instance.entity_id}" if instance.entity_type and instance.entity_id else None

    @staticmethod
    def get_allowed_actions(obj: WorkflowTask) -> list[str]:
        return ["view", "complete", "reject"] if obj.status == "pending" else ["view"]

    class Meta:
        model = WorkflowTask
        fields = (
            "id",
            "instance_id",
            "workflow_id",
            "workflow_name",
            "workflow_version",
            "step_id",
            "step_name",
            "assignment_kind",
            "assignment_label",
            "subject",
            "status",
            "due_date",
            "created_at",
            "completed_at",
            "correlation_id",
            "allowed_actions",
        )
        read_only_fields = fields


class WorkflowInstanceListSerializer(serializers.ModelSerializer):
    workflow_id = serializers.UUIDField(read_only=True)
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    current_step_name = serializers.CharField(source="current_step.name", read_only=True)
    started_by_name = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    @staticmethod
    def get_started_by_name(obj: WorkflowInstance) -> str | None:
        user = obj.started_by
        if user is None:
            return None
        full_name = user.get_full_name().strip() if hasattr(user, "get_full_name") else ""
        return full_name or str(user.get_username() if hasattr(user, "get_username") else user)

    @staticmethod
    def get_subject(obj: WorkflowInstance) -> str | None:
        return f"{obj.entity_type}:{obj.entity_id}" if obj.entity_type and obj.entity_id else None

    @staticmethod
    def get_allowed_actions(obj: WorkflowInstance) -> list[str]:
        return ["view"] if obj.state in {"completed", "failed", "cancelled"} else ["view", "cancel"]

    class Meta:
        model = WorkflowInstance
        fields = (
            "id",
            "workflow_id",
            "workflow_name",
            "workflow_version",
            "current_step",
            "current_step_name",
            "state",
            "entity_type",
            "entity_id",
            "priority",
            "correlation_id",
            "started_by",
            "started_by_name",
            "subject",
            "started_at",
            "completed_at",
            "failure_code",
            "failure_message",
            "allowed_actions",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WorkflowInstanceDetailSerializer(WorkflowInstanceListSerializer):
    tasks = WorkflowTaskSummarySerializer(many=True, read_only=True)
    current_step = WorkflowStepReadSerializer(read_only=True)
    transition_history = serializers.SerializerMethodField()

    @staticmethod
    def get_transition_history(obj: WorkflowInstance) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for item in obj.transition_history:
            record = dict(item)
            metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
            record["actor_id"] = metadata.get("actor_id")
            record["correlation_id"] = metadata.get("correlation_id", obj.correlation_id)
            values.append(record)
        return values

    class Meta(WorkflowInstanceListSerializer.Meta):
        fields = WorkflowInstanceListSerializer.Meta.fields + (
            "context_data",
            "result_data",
            "transition_history",
            "async_job_id",
            "active_step_keys",
            "tasks",
        )
        read_only_fields = fields


class WorkflowInstanceStartSerializer(StrictSerializer):
    workflow_id = serializers.UUIDField()
    context_data = JsonObjectField(required=False, default=dict)
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True, allow_blank=False)
    entity_type = serializers.RegexField(r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$", required=False, allow_blank=True)
    entity_id = serializers.UUIDField(required=False, allow_null=True)
    priority = serializers.IntegerField(min_value=1, max_value=9, default=5)


class WorkflowInstanceCancelSerializer(StrictSerializer):
    transition_key = serializers.CharField(max_length=255, trim_whitespace=True, allow_blank=False)
    reason = serializers.CharField(max_length=500, trim_whitespace=True, allow_blank=False, required=False)


class WorkflowTaskListSerializer(serializers.ModelSerializer):
    instance_id = serializers.UUIDField(read_only=True)
    workflow_id = serializers.UUIDField(source="instance.workflow_id", read_only=True)
    workflow_name = serializers.CharField(source="instance.workflow.name", read_only=True)
    workflow_version = serializers.IntegerField(source="instance.workflow_version", read_only=True)
    step_id = serializers.UUIDField(read_only=True)
    step_name = serializers.CharField(source="step.name", read_only=True)
    entity_type = serializers.CharField(source="instance.entity_type", read_only=True)
    entity_id = serializers.UUIDField(source="instance.entity_id", read_only=True)
    assignment_label = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    @staticmethod
    def get_assignment_label(obj: WorkflowTask) -> str:
        if obj.assignee is not None:
            full_name = obj.assignee.get_full_name().strip() if hasattr(obj.assignee, "get_full_name") else ""
            return full_name or str(obj.assignee.get_username() if hasattr(obj.assignee, "get_username") else obj.assignee)
        return obj.assignment_key

    @staticmethod
    def get_subject(obj: WorkflowTask) -> str | None:
        instance = obj.instance
        return f"{instance.entity_type}:{instance.entity_id}" if instance.entity_type and instance.entity_id else None

    @staticmethod
    def get_allowed_actions(obj: WorkflowTask) -> list[str]:
        return ["view", "complete", "reject"] if obj.status == "pending" else ["view"]

    class Meta:
        model = WorkflowTask
        fields = (
            "id",
            "instance_id",
            "workflow_id",
            "workflow_name",
            "workflow_version",
            "step_id",
            "step_name",
            "assignment_kind",
            "assignment_key",
            "assignment_label",
            "subject",
            "status",
            "due_date",
            "entity_type",
            "entity_id",
            "correlation_id",
            "created_at",
            "updated_at",
            "completed_at",
            "allowed_actions",
        )
        read_only_fields = fields


class WorkflowTaskDetailSerializer(WorkflowTaskListSerializer):
    completed_by = serializers.PrimaryKeyRelatedField(read_only=True)
    completed_by_name = serializers.SerializerMethodField()
    safe_context = serializers.SerializerMethodField()
    transition_history = serializers.SerializerMethodField()

    @staticmethod
    def get_completed_by_name(obj: WorkflowTask) -> str | None:
        user = obj.completed_by
        if user is None:
            return None
        full_name = user.get_full_name().strip() if hasattr(user, "get_full_name") else ""
        return full_name or str(user.get_username() if hasattr(user, "get_username") else user)

    @staticmethod
    def get_safe_context(obj: WorkflowTask) -> dict[str, Any]:
        allowed = obj.step.config.get("display_context_keys", [])
        if not isinstance(allowed, list):
            return {}
        return {key: obj.instance.context_data[key] for key in allowed if isinstance(key, str) and key in obj.instance.context_data}

    @staticmethod
    def get_transition_history(obj: WorkflowTask) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for item in obj.transition_history:
            record = dict(item)
            metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
            record["actor_id"] = metadata.get("actor_id")
            record["correlation_id"] = metadata.get("correlation_id", obj.correlation_id)
            values.append(record)
        return values

    class Meta(WorkflowTaskListSerializer.Meta):
        fields = WorkflowTaskListSerializer.Meta.fields + (
            "assignee",
            "assignee_role_id",
            "completed_by",
            "completed_by_name",
            "completed_at",
            "safe_context",
            "meta_data",
            "transition_history",
        )
        read_only_fields = fields


class WorkflowTaskCompleteSerializer(StrictSerializer):
    meta_data = JsonObjectField(required=False, default=dict)
    transition_key = serializers.CharField(max_length=255, trim_whitespace=True, allow_blank=False)


class WorkflowTaskRejectSerializer(WorkflowTaskCompleteSerializer):
    reason = serializers.CharField(
        max_length=REJECT_REASON_MAX_LENGTH,
        trim_whitespace=True,
        allow_blank=False,
    )


class CatalogDescriptorSerializer(StrictSerializer):
    key = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    schema_version = serializers.CharField(read_only=True)
    owning_module = serializers.CharField(read_only=True)
    availability = serializers.ChoiceField(
        choices=("available", "locked", "setup_required", "degraded"), read_only=True
    )
    ui_schema = serializers.JSONField(read_only=True)
    input_schema = serializers.JSONField(read_only=True)
    output_schema = serializers.JSONField(read_only=True)
    descriptor_fingerprint = serializers.CharField(read_only=True)
    required_permission = serializers.CharField(read_only=True, allow_blank=True)
    required_entitlement = serializers.CharField(read_only=True, allow_blank=True)
    idempotent = serializers.BooleanField(read_only=True)
    network_access = serializers.BooleanField(read_only=True)
    reason = serializers.CharField(read_only=True, allow_null=True)


class AssigneeCatalogSerializer(StrictSerializer):
    id = serializers.CharField(read_only=True)
    kind = serializers.ChoiceField(choices=("user", "role"), read_only=True)
    display_name = serializers.CharField(read_only=True)
    availability = serializers.ChoiceField(choices=("available", "locked"), read_only=True)


# Compatibility aliases retained for integrations during the v1 sunset window.
WorkflowSerializer = WorkflowDetailSerializer
WorkflowStepSerializer = WorkflowStepReadSerializer
WorkflowInstanceSerializer = WorkflowInstanceDetailSerializer
WorkflowTaskSerializer = WorkflowTaskDetailSerializer
