"""Operation-specific serializers for the governed orchestration API.

Request serializers intentionally expose no ownership, state, counters or
audit fields.  They also bound every JSON document before it reaches the
service layer, where graph- and registry-aware validation is performed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .models import (
    OrchestrationDefinition,
    OrchestrationEdge,
    OrchestrationEvent,
    OrchestrationNode,
    OrchestrationRun,
    OrchestrationSchedule,
    OrchestrationTaskRun,
    RetryAttempt,
)

MAX_JSON_BYTES = 256 * 1024
MAX_JSON_DEPTH = 20
SECRET_KEY_PATTERN = re.compile(
    r"(^|[_-])(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential)([_-]|$)",
    re.IGNORECASE,
)
MAPPING_SOURCE_PATTERN = re.compile(r"^\$(input|tasks\.[a-z0-9_-]+\.output)(\.[a-zA-Z0-9_-]+)*$")


def _walk_json(value: object, *, depth: int = 0, reject_secrets: bool = False) -> None:
    if depth > MAX_JSON_DEPTH:
        raise serializers.ValidationError(f"JSON nesting must not exceed {MAX_JSON_DEPTH} levels")
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise serializers.ValidationError("JSON object keys must be strings")
            if reject_secrets and SECRET_KEY_PATTERN.search(key):
                raise serializers.ValidationError(
                    f"Configuration key '{key}' may contain a secret; use an opaque secret reference"
                )
            _walk_json(child, depth=depth + 1, reject_secrets=reject_secrets)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            _walk_json(child, depth=depth + 1, reject_secrets=reject_secrets)
        return
    raise serializers.ValidationError("JSON contains an unsupported value")


def validate_bounded_json(value: object, *, reject_secrets: bool = False) -> object:
    _walk_json(value, reject_secrets=reject_secrets)
    try:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError("Value must be valid JSON") from exc
    if len(encoded) > MAX_JSON_BYTES:
        raise serializers.ValidationError(f"JSON document must not exceed {MAX_JSON_BYTES} bytes")
    return value


def validate_json_object(value: object, *, reject_secrets: bool = False) -> dict[str, object]:
    validate_bounded_json(value, reject_secrets=reject_secrets)
    if not isinstance(value, dict):
        raise serializers.ValidationError("Expected a JSON object")
    return value


def validate_schema(value: object) -> dict[str, object]:
    schema = validate_json_object(value)
    allowed = {
        "$schema",
        "$id",
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "default",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "format",
    }
    unsupported = sorted(set(schema) - allowed)
    if unsupported:
        raise serializers.ValidationError({"schema": f"Unsupported JSON Schema keywords: {', '.join(unsupported)}"})
    schema_type = schema.get("type", "object")
    if schema_type not in {"object", "array", "string", "number", "integer", "boolean", "null"}:
        raise serializers.ValidationError({"type": "Unsupported JSON Schema type"})
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise serializers.ValidationError({"properties": "Must be an object"})
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise serializers.ValidationError({"required": "Must be an array of property names"})
    missing = sorted(set(required) - set(properties))
    if missing:
        raise serializers.ValidationError({"required": f"Unknown required properties: {', '.join(missing)}"})
    return schema


def validate_labels(value: object) -> dict[str, str]:
    labels = validate_json_object(value)
    if any(not isinstance(item, str) for item in labels.values()):
        raise serializers.ValidationError("Labels must map string keys to string values")
    return labels  # type: ignore[return-value]


def validate_mapping(value: object) -> dict[str, object]:
    mapping = validate_json_object(value)
    for target, source in mapping.items():
        if not target or not isinstance(target, str):
            raise serializers.ValidationError("Mapping targets must be non-empty strings")
        if isinstance(source, str) and source.startswith("$") and not MAPPING_SOURCE_PATTERN.fullmatch(source):
            raise serializers.ValidationError(
                f"Mapping '{target}' uses an unsupported source; use $input or $tasks.<node>.output paths"
            )
    return mapping


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise serializers.ValidationError("Use a valid IANA timezone, for example Europe/Berlin") from exc
    return value


def validate_cron_expression(value: str) -> str:
    normalized = " ".join(value.split())
    fields = normalized.split(" ")
    if len(fields) != 5:
        raise serializers.ValidationError("Cron expressions must contain exactly five fields")
    token = re.compile(r"^(\*|\*/[1-9]\d*|\d+(-\d+)?(,\d+)*)(/[1-9]\d*)?$")
    if any(not token.fullmatch(field) for field in fields):
        raise serializers.ValidationError("Cron expression contains an unsupported token")
    return normalized


class StrictModelSerializer(serializers.ModelSerializer):
    """Model serializer with a shared bounded-JSON validation hook."""

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        for key in ("input", "output", "payload"):
            if key in attrs:
                validate_bounded_json(attrs[key])
        return attrs


class NodeListSerializer(StrictModelSerializer):
    class Meta:
        model = OrchestrationNode
        fields = (
            "id",
            "tenant_id",
            "definition_id",
            "key",
            "name",
            "node_type",
            "handler_key",
            "priority",
            "timeout_seconds",
            "max_attempts",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class NodeDetailSerializer(StrictModelSerializer):
    class Meta:
        model = OrchestrationNode
        fields = (
            "id",
            "tenant_id",
            "definition_id",
            "key",
            "name",
            "description",
            "node_type",
            "handler_key",
            "config",
            "input_mapping",
            "timeout_seconds",
            "max_attempts",
            "retry_initial_delay_seconds",
            "retry_backoff_multiplier",
            "retry_max_delay_seconds",
            "priority",
            "is_deleted",
            "deleted_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class NodeCreateSerializer(serializers.Serializer):
    key = serializers.SlugField(max_length=100)
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    node_type = serializers.ChoiceField(choices=("internal", "workflow", "extension"))
    handler_key = serializers.CharField(max_length=150, trim_whitespace=True)
    config = serializers.JSONField(required=False, default=dict)
    input_mapping = serializers.JSONField(required=False, default=dict)
    timeout_seconds = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=86400)
    max_attempts = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=20)
    retry_initial_delay_seconds = serializers.IntegerField(required=False, default=5, min_value=1, max_value=86400)
    retry_backoff_multiplier = serializers.DecimalField(
        required=False, default="2.00", max_digits=4, decimal_places=2, min_value=1, max_value=10
    )
    retry_max_delay_seconds = serializers.IntegerField(required=False, default=300, min_value=1, max_value=86400)
    priority = serializers.IntegerField(required=False, default=0, min_value=-32768, max_value=32767)

    def validate_config(self, value: object) -> dict[str, object]:
        return validate_json_object(value, reject_secrets=True)

    def validate_input_mapping(self, value: object) -> dict[str, object]:
        return validate_mapping(value)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if int(attrs.get("retry_max_delay_seconds", 300)) < int(attrs.get("retry_initial_delay_seconds", 5)):
            raise serializers.ValidationError(
                {"retry_max_delay_seconds": "Must be greater than or equal to the initial delay"}
            )
        return attrs


class NodeUpdateSerializer(NodeCreateSerializer):
    key = serializers.SlugField(max_length=100, required=False)
    name = serializers.CharField(max_length=255, trim_whitespace=True, required=False)
    node_type = serializers.ChoiceField(choices=("internal", "workflow", "extension"), required=False)
    handler_key = serializers.CharField(max_length=150, trim_whitespace=True, required=False)
    retry_initial_delay_seconds = serializers.IntegerField(required=False, min_value=1, max_value=86400)
    retry_backoff_multiplier = serializers.DecimalField(
        required=False, max_digits=4, decimal_places=2, min_value=1, max_value=10
    )
    retry_max_delay_seconds = serializers.IntegerField(required=False, min_value=1, max_value=86400)
    priority = serializers.IntegerField(required=False, min_value=-32768, max_value=32767)


class EdgeSerializer(StrictModelSerializer):
    class Meta:
        model = OrchestrationEdge
        fields = (
            "id",
            "tenant_id",
            "definition_id",
            "upstream_node_id",
            "downstream_node_id",
            "condition",
            "priority",
            "is_deleted",
            "deleted_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class EdgeCreateSerializer(serializers.Serializer):
    upstream_node_id = serializers.UUIDField()
    downstream_node_id = serializers.UUIDField()
    condition = serializers.ChoiceField(choices=("on_success", "on_failure", "always"), default="on_success")
    priority = serializers.IntegerField(default=0, min_value=-32768, max_value=32767)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs["upstream_node_id"] == attrs["downstream_node_id"]:
            raise serializers.ValidationError({"downstream_node_id": "A node cannot depend on itself"})
        return attrs


class EdgeUpdateSerializer(serializers.Serializer):
    condition = serializers.ChoiceField(choices=("on_success", "on_failure", "always"), required=False)
    priority = serializers.IntegerField(required=False, min_value=-32768, max_value=32767)


class DefinitionListSerializer(StrictModelSerializer):
    node_count = serializers.IntegerField(read_only=True, default=0)
    schedule_count = serializers.IntegerField(read_only=True, default=0)
    last_run_at = serializers.DateTimeField(read_only=True, allow_null=True, default=None)
    success_rate = serializers.FloatField(read_only=True, allow_null=True, default=None)

    class Meta:
        model = OrchestrationDefinition
        fields = (
            "id",
            "tenant_id",
            "key",
            "version",
            "name",
            "description",
            "status",
            "is_current",
            "is_deleted",
            "graph_revision",
            "node_count",
            "schedule_count",
            "last_run_at",
            "success_rate",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DefinitionDetailSerializer(StrictModelSerializer):
    nodes = serializers.SerializerMethodField()
    edges = serializers.SerializerMethodField()

    class Meta:
        model = OrchestrationDefinition
        fields = (
            "id",
            "tenant_id",
            "key",
            "version",
            "name",
            "description",
            "status",
            "is_current",
            "max_parallel_tasks",
            "default_timeout_seconds",
            "default_max_attempts",
            "input_schema",
            "output_schema",
            "output_mapping",
            "labels",
            "graph_revision",
            "contract_snapshot",
            "transition_history",
            "is_deleted",
            "deleted_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "nodes",
            "edges",
        )
        read_only_fields = fields

    def get_nodes(self, instance: OrchestrationDefinition) -> list[dict[str, object]]:
        return NodeDetailSerializer(
            instance.nodes.filter(is_deleted=False).order_by("-priority", "key"), many=True
        ).data

    def get_edges(self, instance: OrchestrationDefinition) -> list[dict[str, object]]:
        return EdgeSerializer(
            instance.edges.filter(is_deleted=False).order_by("-priority", "created_at"), many=True
        ).data


class DefinitionCreateSerializer(serializers.Serializer):
    key = serializers.SlugField(max_length=100)
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    max_parallel_tasks = serializers.IntegerField(required=False, default=10, min_value=1, max_value=100)
    default_timeout_seconds = serializers.IntegerField(required=False, default=300, min_value=1, max_value=86400)
    default_max_attempts = serializers.IntegerField(required=False, default=3, min_value=1, max_value=20)
    input_schema = serializers.JSONField(required=False, default=dict)
    output_schema = serializers.JSONField(required=False, default=dict)
    output_mapping = serializers.JSONField(required=False, default=dict)
    labels = serializers.JSONField(required=False, default=dict)

    def validate_input_schema(self, value: object) -> dict[str, object]:
        return validate_schema(value)

    def validate_output_schema(self, value: object) -> dict[str, object]:
        return validate_schema(value)

    def validate_output_mapping(self, value: object) -> dict[str, object]:
        return validate_mapping(value)

    def validate_labels(self, value: object) -> dict[str, str]:
        return validate_labels(value)


class DefinitionUpdateSerializer(DefinitionCreateSerializer):
    key = serializers.SlugField(max_length=100, required=False)
    name = serializers.CharField(max_length=255, trim_whitespace=True, required=False)
    max_parallel_tasks = serializers.IntegerField(required=False, min_value=1, max_value=100)
    default_timeout_seconds = serializers.IntegerField(required=False, min_value=1, max_value=86400)
    default_max_attempts = serializers.IntegerField(required=False, min_value=1, max_value=20)
    transition_key = serializers.CharField(max_length=64, required=False, write_only=True)
    expected_revision = serializers.IntegerField(required=False, min_value=1, write_only=True)


class GraphValidationIssueSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=("error", "warning"))
    message = serializers.CharField()
    entity_type = serializers.ChoiceField(choices=("definition", "node", "edge"))
    entity_id = serializers.UUIDField(required=False, allow_null=True)
    pointer = serializers.CharField(required=False, allow_blank=True)
    remediation = serializers.CharField(required=False, allow_blank=True)


class GraphValidationSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    validated_revision = serializers.IntegerField(min_value=1)
    issues = GraphValidationIssueSerializer(many=True)


class ScheduleListSerializer(StrictModelSerializer):
    definition_name = serializers.CharField(source="definition.name", read_only=True)
    definition_key = serializers.CharField(source="definition.key", read_only=True)
    definition_version = serializers.IntegerField(source="definition.version", read_only=True)

    class Meta:
        model = OrchestrationSchedule
        fields = (
            "id",
            "tenant_id",
            "definition_id",
            "definition_name",
            "definition_key",
            "definition_version",
            "name",
            "cron_expression",
            "timezone",
            "status",
            "misfire_policy",
            "concurrency_policy",
            "next_run_at",
            "last_enqueued_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ScheduleDetailSerializer(StrictModelSerializer):
    definition_name = serializers.CharField(source="definition.name", read_only=True)
    definition_key = serializers.CharField(source="definition.key", read_only=True)
    definition_version = serializers.IntegerField(source="definition.version", read_only=True)

    class Meta:
        model = OrchestrationSchedule
        fields = (
            "id",
            "tenant_id",
            "definition_id",
            "definition_name",
            "definition_key",
            "definition_version",
            "name",
            "cron_expression",
            "timezone",
            "status",
            "misfire_policy",
            "concurrency_policy",
            "input",
            "next_run_at",
            "last_enqueued_at",
            "transition_history",
            "is_deleted",
            "deleted_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ScheduleCreateSerializer(serializers.Serializer):
    definition_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    cron_expression = serializers.CharField(max_length=100, validators=(validate_cron_expression,))
    timezone = serializers.CharField(max_length=64, validators=(validate_timezone,))
    misfire_policy = serializers.ChoiceField(choices=("skip", "run_once"), default="skip")
    concurrency_policy = serializers.ChoiceField(choices=("allow", "forbid"), default="forbid")
    input = serializers.JSONField(required=False, default=dict)

    def validate_input(self, value: object) -> dict[str, object]:
        return validate_json_object(value, reject_secrets=True)


class ScheduleUpdateSerializer(ScheduleCreateSerializer):
    definition_id = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=255, trim_whitespace=True, required=False)
    cron_expression = serializers.CharField(max_length=100, validators=(validate_cron_expression,), required=False)
    timezone = serializers.CharField(max_length=64, validators=(validate_timezone,), required=False)
    misfire_policy = serializers.ChoiceField(choices=("skip", "run_once"), required=False)
    concurrency_policy = serializers.ChoiceField(choices=("allow", "forbid"), required=False)
    transition_key = serializers.CharField(max_length=64, required=False, write_only=True)


class RunListSerializer(StrictModelSerializer):
    definition_name = serializers.CharField(source="definition.name", read_only=True)
    definition_key = serializers.CharField(source="definition.key", read_only=True)
    definition_version = serializers.IntegerField(source="definition.version", read_only=True)

    class Meta:
        model = OrchestrationRun
        fields = (
            "id",
            "tenant_id",
            "definition_id",
            "definition_name",
            "definition_key",
            "definition_version",
            "schedule_id",
            "parent_run_id",
            "trigger_type",
            "status",
            "idempotency_key",
            "correlation_id",
            "requested_by",
            "task_count",
            "completed_task_count",
            "failed_task_count",
            "error_code",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RunDetailSerializer(StrictModelSerializer):
    task_runs = serializers.SerializerMethodField()
    graph = serializers.SerializerMethodField()
    definition_name = serializers.CharField(source="definition.name", read_only=True)
    definition_key = serializers.CharField(source="definition.key", read_only=True)
    definition_version = serializers.IntegerField(source="definition.version", read_only=True)

    class Meta:
        model = OrchestrationRun
        fields = (
            "id",
            "tenant_id",
            "definition_id",
            "definition_name",
            "definition_key",
            "definition_version",
            "schedule_id",
            "parent_run_id",
            "trigger_type",
            "status",
            "input",
            "output",
            "idempotency_key",
            "correlation_id",
            "requested_by",
            "task_count",
            "completed_task_count",
            "failed_task_count",
            "error_code",
            "error_message",
            "transition_history",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
            "task_runs",
            "graph",
        )
        read_only_fields = fields

    def get_task_runs(self, instance: OrchestrationRun) -> list[dict[str, object]]:
        return TaskRunListSerializer(instance.task_runs.select_related("node").order_by("created_at"), many=True).data

    def get_graph(self, instance: OrchestrationRun) -> dict[str, object]:
        definition = instance.definition
        return {
            "nodes": NodeDetailSerializer(
                definition.nodes.filter(is_deleted=False).order_by("-priority", "key"), many=True
            ).data,
            "edges": EdgeSerializer(
                definition.edges.filter(is_deleted=False).order_by("-priority", "created_at"), many=True
            ).data,
        }


class RunStartSerializer(serializers.Serializer):
    definition_id = serializers.UUIDField()
    input = serializers.JSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)
    trigger_type = serializers.ChoiceField(choices=("manual", "workflow", "event"), default="manual")
    schedule_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_input(self, value: object) -> dict[str, object]:
        return validate_json_object(value, reject_secrets=True)


class RunControlSerializer(serializers.Serializer):
    transition_key = serializers.CharField(max_length=64, trim_whitespace=True)


class RunRetrySerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)


class TaskRunListSerializer(StrictModelSerializer):
    node_key = serializers.CharField(source="node.key", read_only=True)
    node_name = serializers.CharField(source="node.name", read_only=True)

    class Meta:
        model = OrchestrationTaskRun
        fields = (
            "id",
            "tenant_id",
            "run_id",
            "node_id",
            "node_key",
            "node_name",
            "status",
            "remaining_dependencies",
            "current_attempt",
            "max_attempts",
            "error_code",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RetryAttemptSerializer(StrictModelSerializer):
    class Meta:
        model = RetryAttempt
        fields = (
            "id",
            "tenant_id",
            "task_run_id",
            "attempt_number",
            "async_job_id",
            "idempotency_key",
            "delivery_token",
            "request_fingerprint",
            "commit_outcome",
            "status",
            "available_at",
            "correlation_id",
            "output",
            "error_code",
            "error_message",
            "duration_ms",
            "transition_history",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TaskRunDetailSerializer(StrictModelSerializer):
    attempts = RetryAttemptSerializer(many=True, read_only=True)
    node = NodeListSerializer(read_only=True)
    node_key = serializers.CharField(source="node.key", read_only=True)
    node_name = serializers.CharField(source="node.name", read_only=True)

    class Meta:
        model = OrchestrationTaskRun
        fields = (
            "id",
            "tenant_id",
            "run_id",
            "node_id",
            "node_key",
            "node_name",
            "node",
            "status",
            "input",
            "output",
            "remaining_dependencies",
            "current_attempt",
            "max_attempts",
            "operation_token",
            "error_code",
            "error_message",
            "transition_history",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
            "attempts",
        )
        read_only_fields = fields


class TaskRetrySerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=255, trim_whitespace=True)


class OrchestrationEventSerializer(StrictModelSerializer):
    class Meta:
        model = OrchestrationEvent
        fields = (
            "id",
            "tenant_id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "actor_id",
            "correlation_id",
            "payload",
            "occurred_at",
        )
        read_only_fields = fields


class NodeDescriptorSerializer(serializers.Serializer):
    key = serializers.CharField()
    display_name = serializers.CharField()
    category = serializers.CharField()
    description = serializers.CharField()
    configuration_schema = serializers.JSONField()
    input_schema = serializers.JSONField()
    output_schema = serializers.JSONField()
    icon_key = serializers.CharField()
    capability = serializers.CharField()
    source_module = serializers.CharField()
    spi_version = serializers.CharField(required=False, default="1.0")
    module_version = serializers.CharField(required=False, default="1.0.0")
    executor_version = serializers.CharField(required=False, default="1.0.0")
    availability = serializers.CharField(required=False, default="available")
    availability_reason = serializers.CharField(required=False, allow_blank=True, default="")
    retry_safety = serializers.CharField(required=False, default="idempotent")


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("ready", "not_ready"))
    checks = serializers.DictField(child=serializers.CharField())


__all__ = [name for name in globals() if name.endswith("Serializer")]
