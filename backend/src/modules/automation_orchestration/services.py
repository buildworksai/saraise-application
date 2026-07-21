"""Tenant-first business engine for durable technical DAG orchestration."""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as datetime_timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.text import slugify

from src.core.async_jobs.models import JobStatus, OutboxEvent
from src.core.async_jobs.services import InvalidJobTransition, enqueue, transition
from src.core.middleware.correlation import get_correlation_id

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
from .metrics import (
    ACTIVE_RUNS,
    NODE_EXECUTIONS,
    RETRIES,
    RUNS,
    RUN_DURATION,
    SCHEDULE_LAG,
    TASKS,
    TASK_DURATION,
    TASK_QUEUE_WAIT,
)
from .node_registry import (
    CORE_CAPABILITY,
    CommitState,
    NodeContractError,
    NodeExecutionContext,
    NodeExecutionResult,
    NodeNotRegistered,
    NodeResultStatus,
    RetrySafety,
    execute_registered_node,
    get_node_descriptor,
    request_fingerprint,
    validate_json_schema,
    validate_json_value,
)

logger = logging.getLogger("saraise.automation_orchestration")

EXECUTE_RUN_COMMAND = "automation_orchestration.execute_run"
EXECUTE_TASK_COMMAND = "automation_orchestration.execute_task"
SCAN_SCHEDULES_COMMAND = "automation_orchestration.scan_schedules"

RUN_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
TASK_TERMINAL = frozenset({"succeeded", "failed", "skipped", "cancelled"})
ATTEMPT_TERMINAL = frozenset({"succeeded", "failed", "timed_out", "cancelled"})
SECRET_FRAGMENTS = ("password", "secret", "token", "api_key", "private_key", "credential")


class OrchestrationServiceError(RuntimeError):
    """Base domain failure with a stable public error code."""

    def __init__(self, message: str, *, code: str = "ORCHESTRATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


class ServiceValidationError(OrchestrationServiceError, ValueError):
    """Input or graph validation failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "VALIDATION_ERROR",
        issues: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        super().__init__(message, code=code)
        self.issues = tuple(dict(issue) for issue in issues)


class StateConflictError(OrchestrationServiceError):
    """Requested lifecycle operation conflicts with durable state."""


class IdempotencyConflictError(OrchestrationServiceError):
    """One idempotency key was reused for a different semantic request."""


@dataclass(frozen=True, slots=True)
class DueScheduleClaim:
    schedule_id: uuid.UUID
    scheduled_for: datetime
    should_enqueue: bool


@dataclass(frozen=True, slots=True)
class GraphValidationReport:
    valid: bool
    issues: tuple[dict[str, Any], ...]
    validated_at: datetime
    validated_revision: int
    node_contracts: Mapping[str, Mapping[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": list(self.issues),
            "validated_at": self.validated_at,
            "validated_revision": self.validated_revision,
            "node_contracts": {key: dict(value) for key, value in self.node_contracts.items()},
        }


def _uuid(value: uuid.UUID | str, name: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ServiceValidationError(f"{name} must be a valid UUID", code="INVALID_UUID") from exc


def _tenant_get(model: type[Any], tenant_id: uuid.UUID, object_id: uuid.UUID, *, lock: bool = False) -> Any:
    queryset = model.objects.for_tenant(tenant_id)
    if lock:
        queryset = queryset.select_for_update()
    return queryset.get(id=object_id)


def _clean_and_save(instance: Any, *, update_fields: Sequence[str] | None = None) -> Any:
    instance.full_clean()
    instance.save(update_fields=update_fields)
    return instance


def _event(
    tenant_id: uuid.UUID,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    *,
    actor_id: uuid.UUID | None,
    correlation_id: str = "",
    payload: Mapping[str, Any] | None = None,
) -> OrchestrationEvent:
    safe_payload = _redact_payload(payload or {})
    encoded = json.dumps(safe_payload, default=str, separators=(",", ":"))
    if len(encoded.encode()) > 16_384:
        raise ServiceValidationError("Event metadata exceeds 16 KiB", code="EVENT_TOO_LARGE")
    return OrchestrationEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        actor_id=actor_id,
        correlation_id=correlation_id or get_correlation_id() or str(uuid.uuid4()),
        payload=safe_payload,
    )


def _redact_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]" if any(part in str(key).lower() for part in SECRET_FRAGMENTS) else _redact_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_payload(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _log_transition(
    message: str,
    *,
    tenant_id: uuid.UUID,
    correlation_id: str = "",
    actor_id: uuid.UUID | None = None,
    definition_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    task_run_id: uuid.UUID | None = None,
    attempt_id: uuid.UUID | None = None,
    async_job_id: uuid.UUID | None = None,
    transition_name: str = "",
    outcome: str = "",
    duration_ms: int | None = None,
) -> None:
    """Emit identifiers and outcomes only; execution payloads are never logged."""

    logger.info(
        message,
        extra={
            "tenant_id": str(tenant_id),
            "correlation_id": correlation_id,
            "actor_id": str(actor_id or ""),
            "definition_id": str(definition_id or ""),
            "run_id": str(run_id or ""),
            "task_run_id": str(task_run_id or ""),
            "attempt_id": str(attempt_id or ""),
            "async_job_id": str(async_job_id or ""),
            "state_transition": transition_name,
            "outcome": outcome,
            "duration_ms": duration_ms,
        },
    )


def _history(instance: Any, transition_key: str, actor_id: uuid.UUID, source: str, target: str) -> None:
    if not transition_key or not isinstance(transition_key, str):
        raise ServiceValidationError("transition_key is required", code="TRANSITION_KEY_REQUIRED")
    entries = list(instance.transition_history or [])
    if any(item.get("transition_key") == transition_key for item in entries):
        raise StateConflictError("transition_key has already been used", code="DUPLICATE_TRANSITION")
    entries.append(
        {
            "transition_key": transition_key,
            "from": source,
            "to": target,
            "actor_id": str(actor_id),
            "occurred_at": timezone.now().isoformat(),
        }
    )
    instance.transition_history = entries


def _definition_input(definition: OrchestrationDefinition, value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ServiceValidationError("input must be an object", code="INVALID_INPUT")
    try:
        validate_json_value(dict(value), definition.input_schema, "input")
    except NodeContractError as exc:
        raise ServiceValidationError(str(exc), code="INPUT_SCHEMA_INVALID") from exc
    return dict(value)


class DefinitionService:
    """Owns draft editing, graph correctness and immutable version lifecycle."""

    EDITABLE_DEFINITION_FIELDS = frozenset(
        {
            "name",
            "description",
            "max_parallel_tasks",
            "default_timeout_seconds",
            "default_max_attempts",
            "input_schema",
            "output_schema",
            "output_mapping",
            "labels",
        }
    )
    EDITABLE_NODE_FIELDS = frozenset(
        {
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
        }
    )
    EDITABLE_EDGE_FIELDS = frozenset({"condition", "priority"})

    @classmethod
    def create_definition(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: Mapping[str, Any],
    ) -> OrchestrationDefinition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        if not isinstance(data, Mapping):
            raise ServiceValidationError("data must be an object")
        name = str(data.get("name", "")).strip()
        key = str(data.get("key", "")).strip() or slugify(name)
        if not name or not key:
            raise ServiceValidationError("name and key are required")
        unknown = set(data) - cls.EDITABLE_DEFINITION_FIELDS - {"key"}
        if unknown:
            raise ServiceValidationError(f"Unknown definition fields: {', '.join(sorted(unknown))}")
        values = {field: data[field] for field in cls.EDITABLE_DEFINITION_FIELDS if field in data}
        values.update(key=key, name=name)
        if "input_schema" not in values:
            values["input_schema"] = {"type": "object", "additionalProperties": True}
        if "output_schema" not in values:
            values["output_schema"] = {"type": "object", "additionalProperties": True}
        try:
            validate_json_schema(values["input_schema"], "input_schema")
            validate_json_schema(values["output_schema"], "output_schema")
            _validate_mapping(values.get("output_mapping", {}))
        except NodeContractError as exc:
            raise ServiceValidationError(str(exc), code="SCHEMA_INVALID") from exc
        labels = values.get("labels", {})
        if not isinstance(labels, Mapping) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in labels.items()
        ):
            raise ServiceValidationError("labels must contain only string keys and values")
        with transaction.atomic():
            definition = OrchestrationDefinition(
                tenant_id=tenant,
                version=1,
                created_by=actor,
                updated_by=actor,
                **values,
            )
            _clean_and_save(definition)
            _event(tenant, "definition", definition.id, "definition.created", actor_id=actor)
        return definition

    @classmethod
    def update_draft(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        actor_id: uuid.UUID,
        changes: Mapping[str, Any],
        transition_key: str,
    ) -> OrchestrationDefinition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _tenant_get(OrchestrationDefinition, tenant, _uuid(definition_id, "definition_id"), lock=True)
            cls._require_draft(definition)
            cls._apply_changes(definition, changes, cls.EDITABLE_DEFINITION_FIELDS)
            try:
                validate_json_schema(definition.input_schema, "input_schema")
                validate_json_schema(definition.output_schema, "output_schema")
                _validate_mapping(definition.output_mapping)
            except NodeContractError as exc:
                raise ServiceValidationError(str(exc), code="SCHEMA_INVALID") from exc
            definition.updated_by = actor
            _history(definition, transition_key, actor, "draft", "draft")
            definition.graph_revision += 1
            _clean_and_save(definition)
            _event(
                tenant,
                "definition",
                definition.id,
                "definition.updated",
                actor_id=actor,
                payload={"fields": sorted(changes)},
            )
        return definition

    @classmethod
    def add_node(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: Mapping[str, Any],
    ) -> OrchestrationNode:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _tenant_get(OrchestrationDefinition, tenant, _uuid(definition_id, "definition_id"), lock=True)
            cls._require_draft(definition)
            unknown = set(data) - cls.EDITABLE_NODE_FIELDS - {"key"}
            if unknown:
                raise ServiceValidationError(f"Unknown node fields: {', '.join(sorted(unknown))}")
            handler_key = str(data.get("handler_key", ""))
            key = str(data.get("key", ""))
            if not key or not handler_key or not data.get("name"):
                raise ServiceValidationError("key, name and handler_key are required")
            cls._validate_node_contract(handler_key, data.get("config", {}))
            _validate_mapping(data.get("input_mapping", {}))
            node = OrchestrationNode(
                tenant_id=tenant,
                definition=definition,
                created_by=actor,
                updated_by=actor,
                **dict(data),
            )
            _clean_and_save(node)
            cls._bump_graph_revision(tenant, definition.id, actor)
            _event(tenant, "node", node.id, "node.created", actor_id=actor, payload={"definition_id": definition.id})
        return node

    @classmethod
    def update_node(
        cls,
        tenant_id: uuid.UUID,
        node_id: uuid.UUID,
        actor_id: uuid.UUID,
        changes: Mapping[str, Any],
    ) -> OrchestrationNode:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            node = _tenant_get(OrchestrationNode, tenant, _uuid(node_id, "node_id"), lock=True)
            cls._require_draft(node.definition)
            cls._apply_changes(node, changes, cls.EDITABLE_NODE_FIELDS)
            cls._validate_node_contract(node.handler_key, node.config)
            _validate_mapping(node.input_mapping)
            node.updated_by = actor
            _clean_and_save(node)
            cls._bump_graph_revision(tenant, node.definition_id, actor)
            _event(tenant, "node", node.id, "node.updated", actor_id=actor, payload={"fields": sorted(changes)})
        return node

    @classmethod
    def remove_node(cls, tenant_id: uuid.UUID, node_id: uuid.UUID, actor_id: uuid.UUID) -> OrchestrationNode:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            node = _tenant_get(OrchestrationNode, tenant, _uuid(node_id, "node_id"), lock=True)
            cls._require_draft(node.definition)
            now = timezone.now()
            OrchestrationEdge.objects.for_tenant(tenant).filter(
                definition=node.definition,
                is_deleted=False,
            ).filter(
                upstream_node=node
            ).update(is_deleted=True, deleted_at=now, updated_by=actor)
            OrchestrationEdge.objects.for_tenant(tenant).filter(
                definition=node.definition,
                is_deleted=False,
            ).filter(
                downstream_node=node
            ).update(is_deleted=True, deleted_at=now, updated_by=actor)
            node.is_deleted, node.deleted_at, node.updated_by = True, now, actor
            _clean_and_save(node)
            cls._bump_graph_revision(tenant, node.definition_id, actor)
            _event(tenant, "node", node.id, "node.removed", actor_id=actor)
        return node

    @classmethod
    def add_edge(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        actor_id: uuid.UUID,
        data: Mapping[str, Any],
    ) -> OrchestrationEdge:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _tenant_get(OrchestrationDefinition, tenant, _uuid(definition_id, "definition_id"), lock=True)
            cls._require_draft(definition)
            unknown = set(data) - {
                "upstream_node",
                "upstream_node_id",
                "downstream_node",
                "downstream_node_id",
                "condition",
                "priority",
            }
            if unknown:
                raise ServiceValidationError(f"Unknown edge fields: {', '.join(sorted(unknown))}")
            upstream_id = data.get("upstream_node_id", data.get("upstream_node"))
            downstream_id = data.get("downstream_node_id", data.get("downstream_node"))
            upstream = _tenant_get(OrchestrationNode, tenant, _uuid(upstream_id, "upstream_node_id"))
            downstream = _tenant_get(OrchestrationNode, tenant, _uuid(downstream_id, "downstream_node_id"))
            if upstream.definition_id != definition.id or downstream.definition_id != definition.id:
                raise ServiceValidationError(
                    "Edge endpoints must belong to the selected definition", code="CROSS_DEFINITION_EDGE"
                )
            edge = OrchestrationEdge(
                tenant_id=tenant,
                definition=definition,
                upstream_node=upstream,
                downstream_node=downstream,
                condition=data.get("condition", "on_success"),
                priority=data.get("priority", 0),
                created_by=actor,
                updated_by=actor,
            )
            _clean_and_save(edge)
            cls._bump_graph_revision(tenant, definition.id, actor)
            report = cls._validate_graph(tenant, definition, publication=False)
            if any(issue["code"] in {"SELF_EDGE", "CYCLE"} for issue in report.issues):
                raise ServiceValidationError(
                    "The edge creates an invalid graph", code="INVALID_EDGE", issues=report.issues
                )
            _event(tenant, "edge", edge.id, "edge.created", actor_id=actor, payload={"definition_id": definition.id})
        return edge

    @classmethod
    def update_edge(
        cls,
        tenant_id: uuid.UUID,
        edge_id: uuid.UUID,
        actor_id: uuid.UUID,
        changes: Mapping[str, Any],
    ) -> OrchestrationEdge:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            edge = _tenant_get(OrchestrationEdge, tenant, _uuid(edge_id, "edge_id"), lock=True)
            cls._require_draft(edge.definition)
            cls._apply_changes(edge, changes, cls.EDITABLE_EDGE_FIELDS)
            edge.updated_by = actor
            _clean_and_save(edge)
            cls._bump_graph_revision(tenant, edge.definition_id, actor)
            _event(tenant, "edge", edge.id, "edge.updated", actor_id=actor, payload={"fields": sorted(changes)})
        return edge

    @classmethod
    def remove_edge(cls, tenant_id: uuid.UUID, edge_id: uuid.UUID, actor_id: uuid.UUID) -> OrchestrationEdge:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            edge = _tenant_get(OrchestrationEdge, tenant, _uuid(edge_id, "edge_id"), lock=True)
            cls._require_draft(edge.definition)
            edge.is_deleted, edge.deleted_at, edge.updated_by = True, timezone.now(), actor
            _clean_and_save(edge)
            cls._bump_graph_revision(tenant, edge.definition_id, actor)
            _event(tenant, "edge", edge.id, "edge.removed", actor_id=actor)
        return edge

    @classmethod
    def validate_graph(cls, tenant_id: uuid.UUID, definition_id: uuid.UUID) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        definition = _tenant_get(OrchestrationDefinition, tenant, _uuid(definition_id, "definition_id"))
        return cls._validate_graph(tenant, definition, publication=False).as_dict()

    @classmethod
    def publish(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        actor_id: uuid.UUID,
        transition_key: str,
    ) -> OrchestrationDefinition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _tenant_get(OrchestrationDefinition, tenant, _uuid(definition_id, "definition_id"), lock=True)
            cls._require_draft(definition)
            report = cls._validate_graph(tenant, definition, publication=True)
            if not report.valid:
                raise ServiceValidationError("Graph validation failed", code="GRAPH_INVALID", issues=report.issues)
            OrchestrationDefinition.objects.for_tenant(tenant).filter(
                key=definition.key,
                is_current=True,
                is_deleted=False,
            ).exclude(id=definition.id).update(is_current=False)
            _history(definition, transition_key, actor, "draft", "published")
            definition.transition_history[-1]["node_contracts"] = report.node_contracts
            definition.status, definition.is_current, definition.updated_by = "published", True, actor
            definition.contract_snapshot = {
                "validated_revision": report.validated_revision,
                "node_contracts": report.node_contracts,
            }
            _clean_and_save(definition)
            _event(
                tenant,
                "definition",
                definition.id,
                "definition.published",
                actor_id=actor,
                payload={"version": definition.version, "contracts": report.node_contracts},
            )
        return definition

    @classmethod
    def clone_version(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> OrchestrationDefinition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            source = _tenant_get(OrchestrationDefinition, tenant, _uuid(definition_id, "definition_id"), lock=True)
            if source.status not in {"published", "retired"} or source.is_deleted:
                raise StateConflictError(
                    "Only published or retired versions may be cloned", code="INVALID_DEFINITION_STATE"
                )
            highest = (
                OrchestrationDefinition.objects.for_tenant(tenant)
                .select_for_update()
                .filter(key=source.key)
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or source.version
            )
            clone = OrchestrationDefinition.objects.create(
                tenant_id=tenant,
                key=source.key,
                version=highest + 1,
                name=source.name,
                description=source.description,
                status="draft",
                is_current=False,
                max_parallel_tasks=source.max_parallel_tasks,
                default_timeout_seconds=source.default_timeout_seconds,
                default_max_attempts=source.default_max_attempts,
                input_schema=source.input_schema,
                output_schema=source.output_schema,
                output_mapping=source.output_mapping,
                labels=source.labels,
                created_by=actor,
                updated_by=actor,
            )
            node_map: dict[uuid.UUID, OrchestrationNode] = {}
            for node in OrchestrationNode.objects.for_tenant(tenant).filter(definition=source, is_deleted=False):
                copied = OrchestrationNode.objects.create(
                    tenant_id=tenant,
                    definition=clone,
                    key=node.key,
                    name=node.name,
                    description=node.description,
                    node_type=node.node_type,
                    handler_key=node.handler_key,
                    config=node.config,
                    input_mapping=node.input_mapping,
                    timeout_seconds=node.timeout_seconds,
                    max_attempts=node.max_attempts,
                    retry_initial_delay_seconds=node.retry_initial_delay_seconds,
                    retry_backoff_multiplier=node.retry_backoff_multiplier,
                    retry_max_delay_seconds=node.retry_max_delay_seconds,
                    priority=node.priority,
                    created_by=actor,
                    updated_by=actor,
                )
                node_map[node.id] = copied
            for edge in OrchestrationEdge.objects.for_tenant(tenant).filter(definition=source, is_deleted=False):
                OrchestrationEdge.objects.create(
                    tenant_id=tenant,
                    definition=clone,
                    upstream_node=node_map[edge.upstream_node_id],
                    downstream_node=node_map[edge.downstream_node_id],
                    condition=edge.condition,
                    priority=edge.priority,
                    created_by=actor,
                    updated_by=actor,
                )
            _event(
                tenant,
                "definition",
                clone.id,
                "definition.cloned",
                actor_id=actor,
                payload={"source_id": source.id, "version": clone.version},
            )
        return clone

    @classmethod
    def retire(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        actor_id: uuid.UUID,
        transition_key: str,
    ) -> OrchestrationDefinition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _tenant_get(OrchestrationDefinition, tenant, _uuid(definition_id, "definition_id"), lock=True)
            if definition.status != "published":
                raise StateConflictError("Only a published definition may be retired", code="INVALID_DEFINITION_STATE")
            if (
                OrchestrationSchedule.objects.for_tenant(tenant)
                .filter(definition=definition, status="active", is_deleted=False)
                .exists()
            ):
                raise StateConflictError("Pause or retire active schedules first", code="ACTIVE_SCHEDULE_EXISTS")
            _history(definition, transition_key, actor, "published", "retired")
            definition.status, definition.is_current, definition.updated_by = "retired", False, actor
            _clean_and_save(definition)
            _event(tenant, "definition", definition.id, "definition.retired", actor_id=actor)
        return definition

    @classmethod
    def delete_draft(
        cls, tenant_id: uuid.UUID, definition_id: uuid.UUID, actor_id: uuid.UUID
    ) -> OrchestrationDefinition:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _tenant_get(OrchestrationDefinition, tenant, _uuid(definition_id, "definition_id"), lock=True)
            if definition.status not in {"draft", "retired"}:
                raise StateConflictError(
                    "Only draft or retired definitions may be deleted", code="INVALID_DEFINITION_STATE"
                )
            if (
                OrchestrationSchedule.objects.for_tenant(tenant)
                .filter(definition=definition, status="active", is_deleted=False)
                .exists()
            ):
                raise StateConflictError("Definition has an active schedule", code="ACTIVE_SCHEDULE_EXISTS")
            definition.is_deleted, definition.deleted_at, definition.is_current = True, timezone.now(), False
            definition.updated_by = actor
            _clean_and_save(definition)
            _event(tenant, "definition", definition.id, "definition.deleted", actor_id=actor)
        return definition

    @classmethod
    def _validate_graph(
        cls,
        tenant_id: uuid.UUID,
        definition: OrchestrationDefinition,
        *,
        publication: bool,
    ) -> GraphValidationReport:
        nodes = list(OrchestrationNode.objects.for_tenant(tenant_id).filter(definition=definition, is_deleted=False))
        edges = list(
            OrchestrationEdge.objects.for_tenant(tenant_id)
            .filter(definition=definition, is_deleted=False)
            .select_related("upstream_node", "downstream_node")
        )
        issues: list[dict[str, Any]] = []
        contracts: dict[str, dict[str, str]] = {}
        node_ids = {node.id for node in nodes}
        incoming: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        outgoing: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for edge in edges:
            if edge.upstream_node_id == edge.downstream_node_id:
                issues.append(
                    _issue(
                        "SELF_EDGE",
                        "edge",
                        edge.id,
                        "upstream_node",
                        "A node cannot depend on itself",
                        "Remove the self-edge.",
                    )
                )
                continue
            if edge.upstream_node_id not in node_ids or edge.downstream_node_id not in node_ids:
                issues.append(
                    _issue(
                        "EDGE_ENDPOINT_INVALID",
                        "edge",
                        edge.id,
                        "definition",
                        "Both endpoints must belong to this graph",
                        "Select nodes from this definition.",
                    )
                )
                continue
            if (
                edge.tenant_id != tenant_id
                or edge.upstream_node.tenant_id != tenant_id
                or edge.downstream_node.tenant_id != tenant_id
            ):
                issues.append(
                    _issue(
                        "EDGE_TENANT_MISMATCH",
                        "edge",
                        edge.id,
                        "tenant_id",
                        "Edge ownership is inconsistent",
                        "Recreate the edge inside this tenant.",
                    )
                )
                continue
            incoming[edge.downstream_node_id].add(edge.upstream_node_id)
            outgoing[edge.upstream_node_id].add(edge.downstream_node_id)
        if not nodes:
            issues.append(
                _issue(
                    "GRAPH_EMPTY",
                    "definition",
                    definition.id,
                    "nodes",
                    "The graph must contain at least one node",
                    "Add a node.",
                )
            )
        roots = [node.id for node in nodes if not incoming[node.id]]
        if nodes and not roots:
            issues.append(
                _issue(
                    "NO_ROOT",
                    "definition",
                    definition.id,
                    "nodes",
                    "The graph has no root node",
                    "Remove a dependency to create a root.",
                )
            )
        indegree = {node.id: len(incoming[node.id]) for node in nodes}
        queue = deque(roots)
        visited: set[uuid.UUID] = set()
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for downstream in outgoing[current]:
                indegree[downstream] -= 1
                if indegree[downstream] == 0:
                    queue.append(downstream)
        if len(visited) != len(nodes):
            cyclic = node_ids - visited
            for node_id in cyclic:
                issues.append(
                    _issue(
                        "CYCLE",
                        "node",
                        node_id,
                        "dependencies",
                        "The node participates in a cycle or is unreachable",
                        "Remove a back-edge so every node is reachable from a root.",
                    )
                )
        for node in nodes:
            try:
                descriptor = get_node_descriptor(node.handler_key)
                validate_json_value(node.config, descriptor.configuration_schema, "config")
                _validate_mapping(node.input_mapping, known_nodes={item.key for item in nodes})
                contracts[node.key] = {
                    "handler_key": descriptor.key,
                    "contract_version": descriptor.contract_version,
                    "fingerprint": descriptor.contract_fingerprint,
                }
                if (
                    publication
                    and descriptor.source_module != "automation_orchestration"
                    and not _worker_authorized(tenant_id, definition.created_by, descriptor)
                ):
                    issues.append(
                        _issue(
                            "NODE_NOT_ENTITLED",
                            "node",
                            node.id,
                            "handler_key",
                            "The node capability is not available to this tenant",
                            "Install or enable the required module capability.",
                        )
                    )
                if node.node_type == "workflow" and descriptor.source_module != "workflow_automation":
                    issues.append(
                        _issue(
                            "WORKFLOW_CONTRACT_INVALID",
                            "node",
                            node.id,
                            "handler_key",
                            "Workflow nodes must use the workflow adapter contract",
                            "Choose a workflow_automation handler.",
                        )
                    )
            except NodeNotRegistered:
                issues.append(
                    _issue(
                        "HANDLER_MISSING",
                        "node",
                        node.id,
                        "handler_key",
                        f"Handler {node.handler_key!r} is not registered",
                        "Install the contributing module or select an available node type.",
                    )
                )
            except (NodeContractError, ServiceValidationError) as exc:
                issues.append(
                    _issue(
                        "NODE_CONFIG_INVALID",
                        "node",
                        node.id,
                        "config",
                        str(exc),
                        "Correct the highlighted configuration or mapping.",
                    )
                )
        try:
            validate_json_schema(definition.input_schema, "input_schema")
            validate_json_schema(definition.output_schema, "output_schema")
            _validate_mapping(definition.output_mapping, known_nodes={item.key for item in nodes})
        except (NodeContractError, ServiceValidationError) as exc:
            issues.append(
                _issue(
                    "DEFINITION_CONTRACT_INVALID",
                    "definition",
                    definition.id,
                    "output_mapping",
                    str(exc),
                    "Correct the definition input/output contract.",
                )
            )
        return GraphValidationReport(
            not issues,
            tuple(issues),
            timezone.now(),
            definition.graph_revision,
            contracts,
        )

    @staticmethod
    def _apply_changes(instance: Any, changes: Mapping[str, Any], allowed: frozenset[str]) -> None:
        if not isinstance(changes, Mapping) or not changes:
            raise ServiceValidationError("At least one change is required")
        unknown = set(changes) - allowed
        if unknown:
            raise ServiceValidationError(f"Protected or unknown fields: {', '.join(sorted(unknown))}")
        for field_name, value in changes.items():
            setattr(instance, field_name, value)

    @staticmethod
    def _require_draft(definition: OrchestrationDefinition) -> None:
        if definition.status != "draft" or definition.is_deleted:
            raise StateConflictError("Only a live draft may be edited", code="DEFINITION_IMMUTABLE")

    @staticmethod
    def _validate_node_contract(handler_key: str, config: Any) -> None:
        try:
            descriptor = get_node_descriptor(handler_key)
            validate_json_value(config, descriptor.configuration_schema, "config")
        except NodeNotRegistered as exc:
            raise ServiceValidationError(str(exc), code="HANDLER_MISSING") from exc
        except NodeContractError as exc:
            raise ServiceValidationError(str(exc), code="NODE_CONFIG_INVALID") from exc

    @staticmethod
    def _bump_graph_revision(tenant_id: uuid.UUID, definition_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        updated = (
            OrchestrationDefinition.objects.for_tenant(tenant_id)
            .filter(
                id=definition_id,
                status="draft",
                is_deleted=False,
            )
            .update(graph_revision=F("graph_revision") + 1, updated_by=actor_id)
        )
        if updated != 1:
            raise StateConflictError("The draft graph changed concurrently", code="GRAPH_REVISION_CONFLICT")


class ScheduleService:
    """Owns cron semantics, lifecycle and race-safe due schedule claiming."""

    EDITABLE_FIELDS = frozenset(
        {
            "definition",
            "definition_id",
            "name",
            "cron_expression",
            "timezone",
            "misfire_policy",
            "concurrency_policy",
            "input",
        }
    )

    @classmethod
    def create_schedule(
        cls, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: Mapping[str, Any]
    ) -> OrchestrationSchedule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        unknown = set(data) - cls.EDITABLE_FIELDS
        if unknown:
            raise ServiceValidationError(f"Unknown schedule fields: {', '.join(sorted(unknown))}")
        definition_id = data.get("definition_id", data.get("definition"))
        definition = _tenant_get(OrchestrationDefinition, tenant, _uuid(definition_id, "definition_id"))
        if definition.status != "published" or definition.is_deleted:
            raise StateConflictError(
                "Schedules require an exact published definition version", code="DEFINITION_NOT_PUBLISHED"
            )
        expression, zone_name = str(data.get("cron_expression", "")), str(data.get("timezone", "UTC"))
        cron = CronExpression(expression)
        zone = _zone(zone_name)
        input_value = _definition_input(definition, data.get("input", {}))
        with transaction.atomic():
            schedule = OrchestrationSchedule(
                tenant_id=tenant,
                definition=definition,
                name=data.get("name", ""),
                cron_expression=expression,
                timezone=zone_name,
                status="active",
                misfire_policy=data.get("misfire_policy", "skip"),
                concurrency_policy=data.get("concurrency_policy", "forbid"),
                input=input_value,
                next_run_at=cron.next_after(timezone.now(), zone),
                created_by=actor,
                updated_by=actor,
            )
            _clean_and_save(schedule)
            _event(
                tenant,
                "schedule",
                schedule.id,
                "schedule.created",
                actor_id=actor,
                payload={"definition_id": definition.id},
            )
        return schedule

    @classmethod
    def update_schedule(
        cls, tenant_id: uuid.UUID, schedule_id: uuid.UUID, actor_id: uuid.UUID, changes: Mapping[str, Any]
    ) -> OrchestrationSchedule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        if not changes:
            raise ServiceValidationError("At least one change is required")
        unknown = set(changes) - cls.EDITABLE_FIELDS
        if unknown:
            raise ServiceValidationError(f"Protected or unknown fields: {', '.join(sorted(unknown))}")
        with transaction.atomic():
            schedule = _tenant_get(OrchestrationSchedule, tenant, _uuid(schedule_id, "schedule_id"), lock=True)
            if schedule.status == "retired" or schedule.is_deleted:
                raise StateConflictError("Retired schedules are immutable", code="SCHEDULE_IMMUTABLE")
            if "definition_id" in changes or "definition" in changes:
                definition = _tenant_get(
                    OrchestrationDefinition,
                    tenant,
                    _uuid(changes.get("definition_id", changes.get("definition")), "definition_id"),
                )
                if definition.status != "published" or definition.is_deleted:
                    raise StateConflictError(
                        "Schedules require a published definition", code="DEFINITION_NOT_PUBLISHED"
                    )
                schedule.definition = definition
            for name, value in changes.items():
                if name not in {"definition", "definition_id", "input"}:
                    setattr(schedule, name, value)
            if "input" in changes or "definition" in changes or "definition_id" in changes:
                schedule.input = _definition_input(schedule.definition, changes.get("input", schedule.input))
            cron = CronExpression(schedule.cron_expression)
            zone = _zone(schedule.timezone)
            if "cron_expression" in changes or "timezone" in changes:
                schedule.next_run_at = cron.next_after(timezone.now(), zone)
            schedule.updated_by = actor
            _clean_and_save(schedule)
            _event(
                tenant, "schedule", schedule.id, "schedule.updated", actor_id=actor, payload={"fields": sorted(changes)}
            )
        return schedule

    @classmethod
    def pause_schedule(
        cls, tenant_id: uuid.UUID, schedule_id: uuid.UUID, actor_id: uuid.UUID, transition_key: str
    ) -> OrchestrationSchedule:
        return cls._transition_schedule(
            tenant_id, schedule_id, actor_id, transition_key, {"active"}, "paused", "schedule.paused"
        )

    @classmethod
    def resume_schedule(
        cls, tenant_id: uuid.UUID, schedule_id: uuid.UUID, actor_id: uuid.UUID, transition_key: str
    ) -> OrchestrationSchedule:
        schedule = cls._transition_schedule(
            tenant_id, schedule_id, actor_id, transition_key, {"paused"}, "active", "schedule.resumed"
        )
        with transaction.atomic():
            locked = _tenant_get(OrchestrationSchedule, _uuid(tenant_id, "tenant_id"), schedule.id, lock=True)
            locked.next_run_at = CronExpression(locked.cron_expression).next_after(
                timezone.now(), _zone(locked.timezone)
            )
            locked.save(update_fields=["next_run_at", "updated_at"])
            return locked

    @classmethod
    def retire_schedule(
        cls, tenant_id: uuid.UUID, schedule_id: uuid.UUID, actor_id: uuid.UUID, transition_key: str
    ) -> OrchestrationSchedule:
        return cls._transition_schedule(
            tenant_id, schedule_id, actor_id, transition_key, {"active", "paused"}, "retired", "schedule.retired"
        )

    @classmethod
    def delete_schedule(
        cls, tenant_id: uuid.UUID, schedule_id: uuid.UUID, actor_id: uuid.UUID
    ) -> OrchestrationSchedule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            schedule = _tenant_get(OrchestrationSchedule, tenant, _uuid(schedule_id, "schedule_id"), lock=True)
            if schedule.status != "retired":
                raise StateConflictError("Retire the schedule before deleting it", code="SCHEDULE_NOT_RETIRED")
            schedule.is_deleted, schedule.deleted_at, schedule.updated_by = True, timezone.now(), actor
            _clean_and_save(schedule)
            _event(tenant, "schedule", schedule.id, "schedule.deleted", actor_id=actor)
        return schedule

    @classmethod
    def claim_due_schedules(cls, tenant_id: uuid.UUID, now: datetime, batch_size: int) -> list[DueScheduleClaim]:
        tenant = _uuid(tenant_id, "tenant_id")
        if timezone.is_naive(now):
            raise ServiceValidationError("now must be timezone-aware")
        if not 1 <= batch_size <= 1000:
            raise ServiceValidationError("batch_size must be between 1 and 1000")
        claims: list[DueScheduleClaim] = []
        with transaction.atomic():
            queryset = (
                OrchestrationSchedule.objects.for_tenant(tenant)
                .filter(status="active", is_deleted=False, next_run_at__lte=now)
                .order_by("next_run_at", "id")
            )
            if connection.features.has_select_for_update_skip_locked:
                queryset = queryset.select_for_update(skip_locked=True)
            else:
                queryset = queryset.select_for_update()
            for schedule in queryset[:batch_size]:
                scheduled_for = schedule.next_run_at
                SCHEDULE_LAG.observe(max(0.0, (now - scheduled_for).total_seconds()))
                cron = CronExpression(schedule.cron_expression)
                zone = _zone(schedule.timezone)
                following = cron.next_after(scheduled_for, zone)
                missed_more_than_one = following <= now
                should_enqueue = schedule.misfire_policy == "run_once" or not missed_more_than_one
                schedule.next_run_at = cron.next_after(now if missed_more_than_one else scheduled_for, zone)
                schedule.save(update_fields=["next_run_at", "updated_at"])
                claims.append(DueScheduleClaim(schedule.id, scheduled_for, should_enqueue))
        return claims

    @classmethod
    def enqueue_due_schedule(
        cls, tenant_id: uuid.UUID, schedule_id: uuid.UUID, scheduled_for: datetime
    ) -> OrchestrationRun | None:
        tenant = _uuid(tenant_id, "tenant_id")
        if timezone.is_naive(scheduled_for):
            raise ServiceValidationError("scheduled_for must be timezone-aware")
        with transaction.atomic():
            schedule = _tenant_get(OrchestrationSchedule, tenant, _uuid(schedule_id, "schedule_id"), lock=True)
            if schedule.status != "active" or schedule.is_deleted:
                raise StateConflictError("Schedule is not active", code="SCHEDULE_NOT_ACTIVE")
            key = f"schedule:{schedule.id}:{scheduled_for.astimezone(datetime_timezone.utc).isoformat()}"
            existing = OrchestrationRun.objects.for_tenant(tenant).filter(idempotency_key=key).first()
            if existing:
                return existing
            if (
                schedule.concurrency_policy == "forbid"
                and OrchestrationRun.objects.for_tenant(tenant)
                .filter(schedule=schedule, status__in=["queued", "running", "paused", "cancelling"])
                .exists()
            ):
                _event(
                    tenant,
                    "schedule",
                    schedule.id,
                    "schedule.overlap_skipped",
                    actor_id=None,
                    payload={"scheduled_for": scheduled_for},
                )
                return None
            run = ExecutionService.start_run(
                tenant,
                schedule.definition_id,
                schedule.created_by,
                schedule.input,
                key,
                "schedule",
                schedule_id=schedule.id,
            )
            schedule.last_enqueued_at = scheduled_for
            schedule.save(update_fields=["last_enqueued_at", "updated_at"])
            return run

    @classmethod
    def _transition_schedule(
        cls,
        tenant_id: uuid.UUID,
        schedule_id: uuid.UUID,
        actor_id: uuid.UUID,
        transition_key: str,
        allowed: set[str],
        target: str,
        event_type: str,
    ) -> OrchestrationSchedule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            schedule = _tenant_get(OrchestrationSchedule, tenant, _uuid(schedule_id, "schedule_id"), lock=True)
            if schedule.status not in allowed:
                raise StateConflictError(
                    f"Cannot transition schedule from {schedule.status} to {target}", code="INVALID_SCHEDULE_STATE"
                )
            source = schedule.status
            _history(schedule, transition_key, actor, source, target)
            schedule.status, schedule.updated_by = target, actor
            _clean_and_save(schedule)
            _event(tenant, "schedule", schedule.id, event_type, actor_id=actor)
        return schedule


class ExecutionService:
    """Durable DAG run, task, dependency and retry engine."""

    @classmethod
    def start_run(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        actor_id: uuid.UUID,
        input: Mapping[str, Any],
        idempotency_key: str,
        trigger_type: str,
        schedule_id: uuid.UUID | None = None,
    ) -> OrchestrationRun:
        return cls._start_run(
            tenant_id, definition_id, actor_id, input, idempotency_key, trigger_type, schedule_id=schedule_id
        )

    @classmethod
    def _start_run(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        actor_id: uuid.UUID,
        input: Mapping[str, Any],
        idempotency_key: str,
        trigger_type: str,
        *,
        schedule_id: uuid.UUID | None = None,
        parent_run: OrchestrationRun | None = None,
    ) -> OrchestrationRun:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 255:
            raise ServiceValidationError("idempotency_key is required and limited to 255 characters")
        if not isinstance(input, Mapping):
            raise ServiceValidationError("input must be an object", code="INVALID_INPUT")
        definition_uuid = _uuid(definition_id, "definition_id")
        schedule_uuid = _uuid(schedule_id, "schedule_id") if schedule_id is not None else None
        with transaction.atomic():
            existing = OrchestrationRun.objects.for_tenant(tenant).filter(idempotency_key=idempotency_key).first()
            if existing:
                cls._verify_run_idempotency(
                    existing,
                    definition_uuid,
                    dict(input),
                    trigger_type,
                    schedule_uuid,
                    parent_run.id if parent_run else None,
                )
                return existing
            definition = _tenant_get(OrchestrationDefinition, tenant, definition_uuid, lock=True)
            if definition.status != "published" or definition.is_deleted:
                raise StateConflictError("Only a published definition may execute", code="DEFINITION_NOT_PUBLISHED")
            input_value = _definition_input(definition, input)
            schedule = None
            if schedule_id is not None:
                schedule = _tenant_get(OrchestrationSchedule, tenant, schedule_uuid)
                if schedule.definition_id != definition.id:
                    raise ServiceValidationError(
                        "schedule and definition version do not match", code="SCHEDULE_DEFINITION_MISMATCH"
                    )
            nodes = list(OrchestrationNode.objects.for_tenant(tenant).filter(definition=definition, is_deleted=False))
            edges = list(OrchestrationEdge.objects.for_tenant(tenant).filter(definition=definition, is_deleted=False))
            incoming: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
            for edge in edges:
                incoming[edge.downstream_node_id].add(edge.upstream_node_id)
            correlation_id = get_correlation_id() or str(uuid.uuid4())
            try:
                with transaction.atomic():
                    run = OrchestrationRun.objects.create(
                        tenant_id=tenant,
                        definition=definition,
                        schedule=schedule,
                        parent_run=parent_run,
                        trigger_type=trigger_type,
                        status="queued",
                        input=input_value,
                        idempotency_key=idempotency_key,
                        correlation_id=correlation_id,
                        requested_by=actor,
                        task_count=len(nodes),
                        transition_history=[
                            {
                                "from": "",
                                "to": "queued",
                                "actor_id": str(actor),
                                "occurred_at": timezone.now().isoformat(),
                            }
                        ],
                    )
            except IntegrityError:
                existing = OrchestrationRun.objects.for_tenant(tenant).get(idempotency_key=idempotency_key)
                cls._verify_run_idempotency(
                    existing,
                    definition_uuid,
                    input_value,
                    trigger_type,
                    schedule_uuid,
                    parent_run.id if parent_run else None,
                )
                return existing
            OrchestrationTaskRun.objects.bulk_create(
                [
                    OrchestrationTaskRun(
                        tenant_id=tenant,
                        run=run,
                        node=node,
                        status="ready" if not incoming[node.id] else "blocked",
                        remaining_dependencies=len(incoming[node.id]),
                        max_attempts=node.max_attempts or definition.default_max_attempts,
                        transition_history=[
                            {
                                "from": "",
                                "to": "ready" if not incoming[node.id] else "blocked",
                                "occurred_at": timezone.now().isoformat(),
                            }
                        ],
                    )
                    for node in nodes
                ]
            )
            job = enqueue(tenant, actor, EXECUTE_RUN_COMMAND, {"run_id": str(run.id)}, f"orchestration:run:{run.id}")
            if job.correlation_id != correlation_id:
                run.correlation_id = job.correlation_id
                run.save(update_fields=["correlation_id", "updated_at"])
            _event(
                tenant,
                "run",
                run.id,
                "run.queued",
                actor_id=actor,
                correlation_id=run.correlation_id,
                payload={"async_job_id": job.id, "definition_id": definition.id},
            )
            _log_transition(
                "orchestration run queued",
                tenant_id=tenant,
                correlation_id=run.correlation_id,
                actor_id=actor,
                definition_id=definition.id,
                run_id=run.id,
                async_job_id=job.id,
                transition_name="created->queued",
                outcome="queued",
            )
            transaction.on_commit(lambda: RUNS.labels(outcome="started").inc())
            transaction.on_commit(ACTIVE_RUNS.inc)
        return run

    @staticmethod
    def _verify_run_idempotency(
        existing: OrchestrationRun,
        definition_id: uuid.UUID,
        input_value: Mapping[str, Any],
        trigger_type: str,
        schedule_id: uuid.UUID | None,
        parent_run_id: uuid.UUID | None,
    ) -> None:
        fingerprint_matches = (
            existing.definition_id == definition_id
            and existing.input == dict(input_value)
            and existing.trigger_type == trigger_type
            and existing.schedule_id == schedule_id
            and existing.parent_run_id == parent_run_id
        )
        if not fingerprint_matches:
            raise IdempotencyConflictError(
                "The idempotency key was already used for a different run",
                code="IDEMPOTENCY_CONFLICT",
            )

    @classmethod
    def execute_run(cls, tenant_id: uuid.UUID, run_id: uuid.UUID) -> OrchestrationRun:
        tenant = _uuid(tenant_id, "tenant_id")
        with transaction.atomic():
            run = _tenant_get(OrchestrationRun, tenant, _uuid(run_id, "run_id"), lock=True)
            if run.status in RUN_TERMINAL:
                return run
            if run.status == "queued":
                run.status, run.started_at = "running", timezone.now()
                run.transition_history = [
                    *run.transition_history,
                    {"from": "queued", "to": "running", "occurred_at": timezone.now().isoformat()},
                ]
                run.save(update_fields=["status", "started_at", "transition_history", "updated_at"])
                _event(tenant, "run", run.id, "run.started", actor_id=None, correlation_id=run.correlation_id)
            elif run.status not in {"running", "paused"}:
                raise StateConflictError(f"Run cannot execute from {run.status}", code="INVALID_RUN_STATE")
        if run.status == "running":
            ready = cls.resolve_ready_tasks(tenant, run.id)
            for task_run in ready:
                cls.enqueue_task(tenant, task_run.id)
            return cls.finalize_run(tenant, run.id)
        return run

    @classmethod
    def resolve_ready_tasks(cls, tenant_id: uuid.UUID, run_id: uuid.UUID) -> list[OrchestrationTaskRun]:
        tenant = _uuid(tenant_id, "tenant_id")
        ready: list[OrchestrationTaskRun] = []
        with transaction.atomic():
            run = _tenant_get(OrchestrationRun, tenant, _uuid(run_id, "run_id"), lock=True)
            if run.status != "running":
                return ready
            tasks = list(
                OrchestrationTaskRun.objects.for_tenant(tenant)
                .select_for_update()
                .filter(run=run)
                .select_related("node")
            )
            by_node = {task.node_id: task for task in tasks}
            edges = list(
                OrchestrationEdge.objects.for_tenant(tenant).filter(definition=run.definition, is_deleted=False)
            )
            incoming: dict[uuid.UUID, list[OrchestrationEdge]] = defaultdict(list)
            for edge in edges:
                incoming[edge.downstream_node_id].append(edge)
            for task in tasks:
                if task.status == "ready":
                    ready.append(task)
                    continue
                if task.status != "blocked":
                    continue
                groups: dict[uuid.UUID, list[OrchestrationEdge]] = defaultdict(list)
                for edge in incoming[task.node_id]:
                    groups[edge.upstream_node_id].append(edge)
                upstream_tasks = [by_node[node_id] for node_id in groups]
                task.remaining_dependencies = sum(item.status not in TASK_TERMINAL for item in upstream_tasks)
                if task.remaining_dependencies:
                    task.save(update_fields=["remaining_dependencies", "updated_at"])
                    continue
                conditions_met = all(
                    any(_edge_matches(edge.condition, by_node[node_id].status) for edge in group)
                    for node_id, group in groups.items()
                )
                target = "ready" if conditions_met else "skipped"
                task.status = target
                task.completed_at = timezone.now() if target == "skipped" else None
                task.transition_history = [
                    *task.transition_history,
                    {"from": "blocked", "to": target, "occurred_at": timezone.now().isoformat()},
                ]
                task.save(
                    update_fields=[
                        "status",
                        "completed_at",
                        "remaining_dependencies",
                        "transition_history",
                        "updated_at",
                    ]
                )
                _event(tenant, "task_run", task.id, f"task.{target}", actor_id=None, correlation_id=run.correlation_id)
                if target == "ready":
                    ready.append(task)
            active = sum(task.status in {"queued", "running"} for task in tasks)
            available_slots = max(0, run.definition.max_parallel_tasks - active)
            ready.sort(key=lambda item: (-item.node.priority, str(item.id)))
            return ready[:available_slots]

    @classmethod
    def enqueue_task(cls, tenant_id: uuid.UUID, task_run_id: uuid.UUID) -> RetryAttempt:
        tenant = _uuid(tenant_id, "tenant_id")
        with transaction.atomic():
            task = _tenant_get(OrchestrationTaskRun, tenant, _uuid(task_run_id, "task_run_id"), lock=True)
            if task.run.status != "running":
                raise StateConflictError("Tasks dispatch only while a run is running", code="RUN_NOT_RUNNING")
            if task.status == "queued":
                existing = task.attempts.filter(status="queued").order_by("-attempt_number").first()
                if existing:
                    return existing
            if task.status not in {"ready", "retry_wait"}:
                raise StateConflictError(f"Task cannot be enqueued from {task.status}", code="INVALID_TASK_STATE")
            attempt_number = task.current_attempt + 1
            if attempt_number > task.max_attempts:
                raise StateConflictError("Task retry limit is exhausted", code="RETRY_EXHAUSTED")
            available_at = timezone.now()
            if task.status == "retry_wait":
                node = task.node
                delay = min(
                    node.retry_initial_delay_seconds
                    * math.pow(float(node.retry_backoff_multiplier), max(0, attempt_number - 2)),
                    node.retry_max_delay_seconds,
                )
                available_at += timedelta(seconds=delay)
            attempt_id = uuid.uuid4()
            idem = f"orchestration:task:{task.id}:attempt:{attempt_number}"
            job = enqueue(
                tenant,
                task.run.requested_by,
                EXECUTE_TASK_COMMAND,
                {"attempt_id": str(attempt_id)},
                idem,
            )
            attempt = RetryAttempt.objects.create(
                id=attempt_id,
                tenant_id=tenant,
                task_run=task,
                attempt_number=attempt_number,
                async_job_id=job.id,
                idempotency_key=idem,
                status="queued",
                available_at=available_at,
                correlation_id=task.run.correlation_id,
                transition_history=[{"from": "", "to": "queued", "occurred_at": timezone.now().isoformat()}],
            )
            if available_at > timezone.now():
                OutboxEvent.objects.for_tenant(tenant).filter(aggregate_id=job.id, status="pending").update(
                    available_at=available_at
                )
            source = task.status
            task.status, task.current_attempt = "queued", attempt_number
            task.transition_history = [
                *task.transition_history,
                {"from": source, "to": "queued", "attempt": attempt_number, "occurred_at": timezone.now().isoformat()},
            ]
            task.save(update_fields=["status", "current_attempt", "transition_history", "updated_at"])
            _event(
                tenant,
                "attempt",
                attempt.id,
                "attempt.queued",
                actor_id=None,
                correlation_id=task.run.correlation_id,
                payload={"async_job_id": job.id, "available_at": available_at},
            )
            TASKS.labels(transition="queued").inc()
            if attempt_number > 1:
                RETRIES.labels(outcome="queued").inc()
            return attempt

    @classmethod
    def execute_task(cls, tenant_id: uuid.UUID, attempt_id: uuid.UUID) -> RetryAttempt:
        tenant = _uuid(tenant_id, "tenant_id")
        result: NodeExecutionResult | None = None
        context: NodeExecutionContext | None = None
        timeout_seconds = 0
        retry_safety = RetrySafety.UNSAFE
        with transaction.atomic():
            attempt = _tenant_get(RetryAttempt, tenant, _uuid(attempt_id, "attempt_id"), lock=True)
            if attempt.status in ATTEMPT_TERMINAL:
                return attempt
            if attempt.available_at > timezone.now():
                raise StateConflictError("Attempt is not available yet", code="ATTEMPT_NOT_DUE")
            task = _tenant_get(OrchestrationTaskRun, tenant, attempt.task_run_id, lock=True)
            run = _tenant_get(OrchestrationRun, tenant, task.run_id, lock=True)
            if run.status in {"cancelling", "cancelled"}:
                return cls._cancel_attempt_locked(tenant, run, task, attempt)
            if run.status == "paused":
                raise StateConflictError("Run is paused", code="RUN_PAUSED")
            if run.status != "running" or task.status not in {"queued", "running"}:
                raise StateConflictError("Attempt is stale for the current task state", code="STALE_DELIVERY")
            if attempt.status == "queued":
                queue_wait_seconds = max(0.0, (timezone.now() - attempt.available_at).total_seconds())
                if task.status != "queued":
                    raise StateConflictError("Attempt and task state disagree", code="STALE_DELIVERY")
                attempt.status, attempt.started_at = "running", timezone.now()
                attempt.transition_history = [
                    *attempt.transition_history,
                    {"from": "queued", "to": "running", "occurred_at": timezone.now().isoformat()},
                ]
                attempt.save(update_fields=["status", "started_at", "transition_history", "updated_at"])
                task.status = "running"
                task.started_at = task.started_at or timezone.now()
                task.transition_history = [
                    *task.transition_history,
                    {"from": "queued", "to": "running", "occurred_at": timezone.now().isoformat()},
                ]
                task.save(update_fields=["status", "started_at", "transition_history", "updated_at"])
                transaction.on_commit(lambda wait=queue_wait_seconds: TASK_QUEUE_WAIT.observe(wait))
            elif attempt.status != "running" or task.status != "running":
                raise StateConflictError("Attempt is stale for the current task state", code="STALE_DELIVERY")
            try:
                descriptor = get_node_descriptor(task.node.handler_key)
            except NodeNotRegistered:
                result = NodeExecutionResult.unavailable("NODE_HANDLER_MISSING", "The node handler is not installed")
            if result is None and not _worker_authorized(tenant, run.requested_by, descriptor):
                result = NodeExecutionResult.unavailable(
                    "NODE_ACCESS_DENIED", "Node access is unavailable for this execution"
                )
            if result is None:
                mapped_input = _resolve_mapping(tenant, run, task)
                contract_version = _published_contract_version(
                    run.definition, task.node.key, descriptor.contract_version
                )
                fingerprint = request_fingerprint(
                    handler_key=task.node.handler_key, config=task.node.config, input=mapped_input
                )
                if attempt.request_fingerprint and attempt.request_fingerprint != fingerprint:
                    result = NodeExecutionResult.failure(
                        "IDEMPOTENCY_CONFLICT",
                        "The durable operation token was reused for different node input",
                        commit_state=CommitState.UNKNOWN,
                        manual_retry_safe=False,
                    )
                attempt.request_fingerprint = fingerprint
                attempt.save(update_fields=["request_fingerprint", "updated_at"])
                context = NodeExecutionContext(
                    tenant_id=tenant,
                    run_id=run.id,
                    task_run_id=task.id,
                    attempt_id=attempt.id,
                    actor_id=run.requested_by,
                    correlation_id=run.correlation_id,
                    input=mapped_input,
                    validated_config=task.node.config,
                    cancellation_probe=lambda: OrchestrationRun.objects.for_tenant(tenant)
                    .filter(id=run.id, status__in=["cancelling", "cancelled"])
                    .exists(),
                    operation_token=str(task.operation_token),
                    delivery_token=str(attempt.delivery_token),
                    handler_key=task.node.handler_key,
                    descriptor_version=contract_version,
                    request_fingerprint=fingerprint,
                )
                timeout_seconds = task.node.timeout_seconds or run.definition.default_timeout_seconds
                retry_safety = descriptor.retry_safety
        if result is None and context is not None:
            started = time.monotonic()
            result = execute_registered_node(context)
            duration = time.monotonic() - started
            if duration > timeout_seconds:
                result = NodeExecutionResult.failure(
                    "NODE_TIMEOUT",
                    "The node exceeded its configured execution deadline",
                    transient=True,
                    commit_state=CommitState.UNKNOWN,
                    manual_retry_safe=retry_safety != RetrySafety.UNSAFE,
                    evidence={"deadline_seconds": timeout_seconds},
                )
        if result is None:
            result = NodeExecutionResult.failure(
                "EXECUTION_STATE_INVALID", "The node execution could not be initialized"
            )
        return cls._persist_attempt_result(tenant, attempt.id, result)

    @classmethod
    def pause_run(
        cls, tenant_id: uuid.UUID, run_id: uuid.UUID, actor_id: uuid.UUID, transition_key: str
    ) -> OrchestrationRun:
        return cls._transition_run(tenant_id, run_id, actor_id, transition_key, {"running"}, "paused", "run.paused")

    @classmethod
    def resume_run(
        cls, tenant_id: uuid.UUID, run_id: uuid.UUID, actor_id: uuid.UUID, transition_key: str
    ) -> OrchestrationRun:
        run = cls._transition_run(tenant_id, run_id, actor_id, transition_key, {"paused"}, "running", "run.resumed")
        for task in cls.resolve_ready_tasks(_uuid(tenant_id, "tenant_id"), run.id):
            cls.enqueue_task(_uuid(tenant_id, "tenant_id"), task.id)
        return run

    @classmethod
    def cancel_run(
        cls, tenant_id: uuid.UUID, run_id: uuid.UUID, actor_id: uuid.UUID, transition_key: str
    ) -> OrchestrationRun:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            run = _tenant_get(OrchestrationRun, tenant, _uuid(run_id, "run_id"), lock=True)
            if run.status in RUN_TERMINAL:
                return run
            if run.status == "queued":
                target = "cancelled"
            elif run.status in {"running", "paused"}:
                target = "cancelling"
            elif run.status == "cancelling":
                return run
            else:
                raise StateConflictError("Run cannot be cancelled", code="INVALID_RUN_STATE")
            _history(run, transition_key, actor, run.status, target)
            run.status = target
            if target == "cancelled":
                run.completed_at = timezone.now()
            run.save(update_fields=["status", "completed_at", "transition_history", "updated_at"])
            tasks = (
                OrchestrationTaskRun.objects.for_tenant(tenant)
                .select_for_update()
                .filter(run=run)
                .exclude(status__in=TASK_TERMINAL)
            )
            for task in tasks:
                source_status = task.status
                task.status, task.completed_at = "cancelled", timezone.now()
                task.transition_history = [
                    *task.transition_history,
                    {"from": source_status, "to": "cancelled", "occurred_at": timezone.now().isoformat()},
                ]
                task.save(update_fields=["status", "completed_at", "transition_history", "updated_at"])
                for attempt in task.attempts.exclude(status__in=ATTEMPT_TERMINAL):
                    attempt.status, attempt.completed_at = "cancelled", timezone.now()
                    attempt.save(update_fields=["status", "completed_at", "updated_at"])
                    try:
                        transition(
                            attempt.async_job_id,
                            tenant,
                            JobStatus.CANCELLED,
                            reason="Orchestration run cancelled",
                            actor_id=actor,
                        )
                    except (InvalidJobTransition, ObjectDoesNotExist):
                        pass
            if target == "cancelling":
                run.status, run.completed_at = "cancelled", timezone.now()
                run.save(update_fields=["status", "completed_at", "updated_at"])
            _event(tenant, "run", run.id, "run.cancelled", actor_id=actor, correlation_id=run.correlation_id)
            transaction.on_commit(lambda: RUNS.labels(outcome="cancelled").inc())
            transaction.on_commit(ACTIVE_RUNS.dec)
        return run

    @classmethod
    def retry_run(
        cls, tenant_id: uuid.UUID, run_id: uuid.UUID, actor_id: uuid.UUID, idempotency_key: str
    ) -> OrchestrationRun:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        source = _tenant_get(OrchestrationRun, tenant, _uuid(run_id, "run_id"))
        if source.status not in RUN_TERMINAL:
            raise StateConflictError("Only a terminal run may be retried", code="RUN_NOT_TERMINAL")
        return cls._start_run(
            tenant,
            source.definition_id,
            actor,
            source.input,
            idempotency_key,
            source.trigger_type,
            schedule_id=source.schedule_id,
            parent_run=source,
        )

    @classmethod
    def retry_task(
        cls, tenant_id: uuid.UUID, task_run_id: uuid.UUID, actor_id: uuid.UUID, idempotency_key: str
    ) -> OrchestrationTaskRun:
        tenant = _uuid(tenant_id, "tenant_id")
        source_task = _tenant_get(OrchestrationTaskRun, tenant, _uuid(task_run_id, "task_run_id"))
        if source_task.status not in {"failed", "cancelled"}:
            raise StateConflictError(
                "Only failed or cancelled tasks may be manually retried", code="TASK_NOT_RETRYABLE"
            )
        latest = source_task.attempts.order_by("-attempt_number").first()
        if latest and latest.error_code in {"AMBIGUOUS_COMMIT", "MANUAL_RETRY_UNSAFE"}:
            raise StateConflictError("The task requires reconciliation before retry", code="RECONCILIATION_REQUIRED")
        new_run = cls.retry_run(tenant, source_task.run_id, actor_id, idempotency_key)
        return OrchestrationTaskRun.objects.for_tenant(tenant).get(run=new_run, node__key=source_task.node.key)

    @classmethod
    def finalize_run(cls, tenant_id: uuid.UUID, run_id: uuid.UUID) -> OrchestrationRun:
        tenant = _uuid(tenant_id, "tenant_id")
        with transaction.atomic():
            run = _tenant_get(OrchestrationRun, tenant, _uuid(run_id, "run_id"), lock=True)
            if run.status in RUN_TERMINAL:
                return run
            tasks = list(OrchestrationTaskRun.objects.for_tenant(tenant).filter(run=run).select_related("node"))
            run.completed_task_count = sum(task.status in TASK_TERMINAL for task in tasks)
            run.failed_task_count = sum(task.status == "failed" for task in tasks)
            if any(task.status not in TASK_TERMINAL for task in tasks):
                run.save(update_fields=["completed_task_count", "failed_task_count", "updated_at"])
                return run
            if run.status == "cancelling" or any(task.status == "cancelled" for task in tasks):
                target = "cancelled"
            elif run.failed_task_count:
                target = "failed"
            else:
                target = "succeeded"
            downstream_ids = set(
                OrchestrationEdge.objects.for_tenant(tenant)
                .filter(definition=run.definition, is_deleted=False)
                .values_list("upstream_node_id", flat=True)
            )
            sinks = {
                task.node.key: task.output
                for task in tasks
                if task.node_id not in downstream_ids and task.status == "succeeded"
            }
            try:
                run.output = (
                    _resolve_data_mapping(run, tasks, run.definition.output_mapping)
                    if run.definition.output_mapping
                    else sinks
                )
                validate_json_value(run.output, run.definition.output_schema, "output")
            except (NodeContractError, ServiceValidationError):
                target = "failed"
                run.output = None
                run.error_code = "OUTPUT_CONTRACT_INVALID"
                run.error_message = "The completed task evidence does not satisfy the definition output contract"
            run.status, run.completed_at = target, timezone.now()
            run.transition_history = [
                *run.transition_history,
                {"from": "running", "to": target, "occurred_at": timezone.now().isoformat()},
            ]
            if target == "failed" and not run.error_code:
                run.error_code, run.error_message = "TASK_FAILURE", "One or more orchestration tasks failed"
            run.save(
                update_fields=[
                    "status",
                    "output",
                    "completed_task_count",
                    "failed_task_count",
                    "error_code",
                    "error_message",
                    "completed_at",
                    "transition_history",
                    "updated_at",
                ]
            )
            _event(
                tenant,
                "run",
                run.id,
                f"run.{target}",
                actor_id=None,
                correlation_id=run.correlation_id,
                payload={"completed_tasks": run.completed_task_count, "failed_tasks": run.failed_task_count},
            )
            RUNS.labels(outcome=target).inc()
            if run.started_at:
                RUN_DURATION.observe(max(0.0, (run.completed_at - run.started_at).total_seconds()))
            transaction.on_commit(ACTIVE_RUNS.dec)
            _log_transition(
                "orchestration run terminal",
                tenant_id=tenant,
                correlation_id=run.correlation_id,
                definition_id=run.definition_id,
                run_id=run.id,
                transition_name=f"active->{target}",
                outcome=target,
                duration_ms=(
                    int((run.completed_at - run.started_at).total_seconds() * 1000) if run.started_at else None
                ),
            )
            return run

    @classmethod
    def get_run_history(cls, tenant_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        run = _tenant_get(OrchestrationRun, tenant, _uuid(run_id, "run_id"))
        tasks = list(
            OrchestrationTaskRun.objects.for_tenant(tenant)
            .filter(run=run)
            .select_related("node")
            .prefetch_related("attempts")
        )
        events = list(
            OrchestrationEvent.objects.for_tenant(tenant)
            .filter(correlation_id=run.correlation_id)
            .order_by("occurred_at", "id")
        )
        return {"run": run, "task_runs": tasks, "events": events}

    @classmethod
    def _persist_attempt_result(
        cls, tenant: uuid.UUID, attempt_id: uuid.UUID, result: NodeExecutionResult
    ) -> RetryAttempt:
        with transaction.atomic():
            attempt = _tenant_get(RetryAttempt, tenant, attempt_id, lock=True)
            if attempt.status in ATTEMPT_TERMINAL:
                return attempt
            task = _tenant_get(OrchestrationTaskRun, tenant, attempt.task_run_id, lock=True)
            run = _tenant_get(OrchestrationRun, tenant, task.run_id, lock=True)
            now = timezone.now()
            attempt.duration_ms = max(0, int((now - (attempt.started_at or now)).total_seconds() * 1000))
            if run.status in {"cancelling", "cancelled"}:
                return cls._cancel_attempt_locked(tenant, run, task, attempt)
            if result.status == NodeResultStatus.SUCCEEDED:
                attempt.status, attempt.output, attempt.completed_at = "succeeded", dict(result.output), now
                task.status, task.output, task.completed_at = "succeeded", dict(result.output), now
                task.error_code = task.error_message = ""
            else:
                attempt.status = "timed_out" if result.error_code == "NODE_TIMEOUT" else "failed"
                attempt.completed_at = now
                attempt.error_code, attempt.error_message = result.error_code, result.error_message
                can_retry = (
                    result.status == NodeResultStatus.FAILED
                    and result.transient
                    and result.commit_state != CommitState.COMMITTED
                    and result.manual_retry_safe
                    and task.current_attempt < task.max_attempts
                )
                if result.commit_state == CommitState.UNKNOWN and not result.manual_retry_safe:
                    attempt.error_code = "AMBIGUOUS_COMMIT"
                if can_retry:
                    task.status = "retry_wait"
                    task.error_code, task.error_message = attempt.error_code, attempt.error_message
                else:
                    task.status, task.completed_at = "failed", now
                    task.error_code, task.error_message = attempt.error_code, attempt.error_message
            attempt.output = dict(result.output) if result.output else None
            attempt.commit_outcome = {
                "state": result.commit_state.value,
                "manual_retry_safe": result.manual_retry_safe,
                "transient": result.transient,
            }
            attempt.transition_history = [
                *attempt.transition_history,
                {"from": "running", "to": attempt.status, "occurred_at": now.isoformat()},
            ]
            attempt.save(
                update_fields=[
                    "status",
                    "output",
                    "error_code",
                    "error_message",
                    "duration_ms",
                    "commit_outcome",
                    "completed_at",
                    "transition_history",
                    "updated_at",
                ]
            )
            task.transition_history = [
                *task.transition_history,
                {
                    "from": "running",
                    "to": task.status,
                    "attempt": attempt.attempt_number,
                    "occurred_at": now.isoformat(),
                },
            ]
            task.save(
                update_fields=[
                    "status",
                    "output",
                    "error_code",
                    "error_message",
                    "completed_at",
                    "transition_history",
                    "updated_at",
                ]
            )
            _event(
                tenant,
                "attempt",
                attempt.id,
                f"attempt.{attempt.status}",
                actor_id=None,
                correlation_id=run.correlation_id,
                payload={"error_code": attempt.error_code, "duration_ms": attempt.duration_ms},
            )
            NODE_EXECUTIONS.labels(handler=task.node.handler_key, outcome=attempt.status).inc()
            TASK_DURATION.observe((attempt.duration_ms or 0) / 1000.0)
            TASKS.labels(transition=task.status).inc()
            if task.status == "retry_wait":
                RETRIES.labels(outcome="scheduled").inc()
            elif task.status == "failed" and task.current_attempt >= task.max_attempts:
                RETRIES.labels(outcome="exhausted").inc()
            _log_transition(
                "orchestration node attempt completed",
                tenant_id=tenant,
                correlation_id=run.correlation_id,
                actor_id=run.requested_by,
                definition_id=run.definition_id,
                run_id=run.id,
                task_run_id=task.id,
                attempt_id=attempt.id,
                async_job_id=attempt.async_job_id,
                transition_name=f"running->{attempt.status}",
                outcome=attempt.status,
                duration_ms=attempt.duration_ms,
            )
        if task.status == "retry_wait":
            cls.enqueue_task(tenant, task.id)
        else:
            for ready in cls.resolve_ready_tasks(tenant, run.id):
                cls.enqueue_task(tenant, ready.id)
            cls.finalize_run(tenant, run.id)
        return RetryAttempt.objects.for_tenant(tenant).get(id=attempt_id)

    @classmethod
    def _cancel_attempt_locked(
        cls,
        tenant: uuid.UUID,
        run: OrchestrationRun,
        task: OrchestrationTaskRun,
        attempt: RetryAttempt,
    ) -> RetryAttempt:
        now = timezone.now()
        attempt.status, attempt.completed_at = "cancelled", now
        task.status, task.completed_at = "cancelled", now
        attempt.save(update_fields=["status", "completed_at", "updated_at"])
        task.save(update_fields=["status", "completed_at", "updated_at"])
        _event(tenant, "attempt", attempt.id, "attempt.cancelled", actor_id=None, correlation_id=run.correlation_id)
        return attempt

    @classmethod
    def _transition_run(
        cls,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        actor_id: uuid.UUID,
        transition_key: str,
        allowed: set[str],
        target: str,
        event_type: str,
    ) -> OrchestrationRun:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            run = _tenant_get(OrchestrationRun, tenant, _uuid(run_id, "run_id"), lock=True)
            if run.status not in allowed:
                raise StateConflictError(
                    f"Cannot transition run from {run.status} to {target}", code="INVALID_RUN_STATE"
                )
            source = run.status
            _history(run, transition_key, actor, source, target)
            run.status = target
            run.save(update_fields=["status", "transition_history", "updated_at"])
            _event(tenant, "run", run.id, event_type, actor_id=actor, correlation_id=run.correlation_id)
            return run


def _published_contract_version(definition: OrchestrationDefinition, node_key: str, fallback: str) -> str:
    for entry in reversed(definition.transition_history or []):
        contracts = entry.get("node_contracts", {})
        if node_key in contracts:
            return str(contracts[node_key].get("contract_version", fallback))
    return fallback


def _worker_authorized(tenant_id: uuid.UUID, actor_id: uuid.UUID, descriptor: Any) -> bool:
    if descriptor.capability == CORE_CAPABILITY and descriptor.source_module == "automation_orchestration":
        return True
    dotted = getattr(settings, "AUTOMATION_ORCHESTRATION_WORKER_AUTHORIZER", "")
    if not dotted:
        return False
    authorizer = import_string(dotted) if isinstance(dotted, str) else dotted
    return bool(
        authorizer(tenant_id, actor_id, descriptor.capability, descriptor.quota_resource, descriptor.quota_cost)
    )


def _issue(
    code: str, entity_type: str, entity_id: uuid.UUID, pointer: str, message: str, remediation: str
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "error",
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "pointer": f"/{pointer}",
        "message": message,
        "remediation": remediation,
    }


def _validate_mapping(value: Any, *, known_nodes: set[str] | None = None) -> None:
    if not isinstance(value, Mapping):
        raise ServiceValidationError("input_mapping must be an object", code="MAPPING_INVALID")

    def visit(item: Any, pointer: str) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise ServiceValidationError(f"Mapping key at {pointer} must be a string", code="MAPPING_INVALID")
                visit(nested, f"{pointer}/{key}")
        elif isinstance(item, list):
            for index, nested in enumerate(item):
                visit(nested, f"{pointer}/{index}")
        elif isinstance(item, str) and item.startswith("$"):
            parts = item.split(".")
            if parts[0] not in {"$input", "$tasks", "$nodes", "$run"}:
                raise ServiceValidationError(
                    f"Unsupported mapping expression {item!r} at {pointer}", code="MAPPING_INVALID"
                )
            if parts[0] in {"$tasks", "$nodes"} and (
                len(parts) < 3 or parts[2] != "output" or (known_nodes is not None and parts[1] not in known_nodes)
            ):
                raise ServiceValidationError(f"Mapping references unknown node in {item!r}", code="MAPPING_INVALID")
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ServiceValidationError(f"Mapping value at {pointer} is not JSON-compatible", code="MAPPING_INVALID")

    visit(value, "")


def _resolve_mapping(tenant: uuid.UUID, run: OrchestrationRun, task: OrchestrationTaskRun) -> dict[str, Any]:
    mapping = task.node.input_mapping or {}
    if not mapping:
        return dict(run.input)
    tasks = list(
        OrchestrationTaskRun.objects.for_tenant(tenant).filter(run=run, status="succeeded").select_related("node")
    )
    return _resolve_data_mapping(run, tasks, mapping)


def _resolve_data_mapping(
    run: OrchestrationRun,
    tasks: Sequence[OrchestrationTaskRun],
    mapping: Mapping[str, Any],
) -> dict[str, Any]:
    outputs = {item.node.key: item.output for item in tasks}

    def resolve(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): resolve(value) for key, value in item.items()}
        if isinstance(item, list):
            return [resolve(value) for value in item]
        if not isinstance(item, str) or not item.startswith("$"):
            return item
        parts = item.split(".")
        if parts[0] == "$input":
            current: Any = run.input
            parts = parts[1:]
        elif parts[0] in {"$tasks", "$nodes"} and len(parts) >= 3 and parts[2] == "output":
            current = outputs.get(parts[1])
            parts = parts[3:]
        elif parts[0] == "$run":
            current = {"id": str(run.id), "correlation_id": run.correlation_id}
            parts = parts[1:]
        else:
            raise ServiceValidationError(f"Unsupported mapping expression {item!r}", code="MAPPING_INVALID")
        for part in parts:
            if not isinstance(current, Mapping) or part not in current:
                raise ServiceValidationError(f"Mapping source {item!r} is unavailable", code="MAPPING_SOURCE_MISSING")
            current = current[part]
        return current

    return resolve(mapping)


def _edge_matches(condition: str, upstream_status: str) -> bool:
    return (
        condition == "always"
        or (condition == "on_success" and upstream_status == "succeeded")
        or (condition == "on_failure" and upstream_status == "failed")
    )


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ServiceValidationError("timezone must be a valid IANA timezone", code="INVALID_TIMEZONE") from exc


class CronExpression:
    """Deterministic five-field cron parser with explicit timezone evaluation."""

    _RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))

    def __init__(self, expression: str) -> None:
        if not isinstance(expression, str) or len(expression) > 100:
            raise ServiceValidationError("cron_expression must be a string up to 100 characters", code="INVALID_CRON")
        fields = expression.split()
        if len(fields) != 5:
            raise ServiceValidationError("cron_expression must contain five fields", code="INVALID_CRON")
        self.expression = expression
        self.allowed = tuple(
            self._parse_field(raw, minimum, maximum, index)
            for index, (raw, (minimum, maximum)) in enumerate(zip(fields, self._RANGES))
        )
        self.day_any = fields[2] == "*"
        self.weekday_any = fields[4] == "*"

    @staticmethod
    def _parse_field(raw: str, minimum: int, maximum: int, index: int) -> frozenset[int]:
        values: set[int] = set()
        for term in raw.split(","):
            if not term:
                raise ServiceValidationError("cron_expression contains an empty term", code="INVALID_CRON")
            base, separator, step_raw = term.partition("/")
            step = int(step_raw) if separator and step_raw.isdigit() else 1
            if separator and (not step_raw.isdigit() or step < 1):
                raise ServiceValidationError("cron step must be a positive integer", code="INVALID_CRON")
            if base == "*":
                start, end = minimum, maximum
            elif "-" in base:
                start_raw, end_raw = base.split("-", 1)
                if not start_raw.isdigit() or not end_raw.isdigit():
                    raise ServiceValidationError("cron ranges must be numeric", code="INVALID_CRON")
                start, end = int(start_raw), int(end_raw)
            elif base.isdigit():
                start = end = int(base)
            else:
                raise ServiceValidationError("cron fields must be numeric", code="INVALID_CRON")
            if not minimum <= start <= end <= maximum:
                raise ServiceValidationError("cron field is outside its valid range", code="INVALID_CRON")
            values.update(range(start, end + 1, step))
        if index == 4 and 7 in values:
            values.add(0)
            values.discard(7)
        return frozenset(values)

    def matches(self, value: datetime) -> bool:
        cron_weekday = (value.weekday() + 1) % 7
        day_match = value.day in self.allowed[2]
        weekday_match = cron_weekday in self.allowed[4]
        calendar_match = day_match and weekday_match if self.day_any or self.weekday_any else day_match or weekday_match
        return (
            value.minute in self.allowed[0]
            and value.hour in self.allowed[1]
            and value.month in self.allowed[3]
            and calendar_match
        )

    def next_after(self, value: datetime, zone: ZoneInfo) -> datetime:
        if timezone.is_naive(value):
            raise ServiceValidationError("cron base time must be timezone-aware", code="INVALID_TIME")
        # Advance on the UTC timeline so DST gaps never fabricate a local time
        # and DST folds retain their two real instants.
        candidate = value.astimezone(datetime_timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = candidate + timedelta(days=366 * 5)
        while candidate < limit:
            if self.matches(candidate.astimezone(zone)):
                return candidate
            candidate += timedelta(minutes=1)
        raise ServiceValidationError("cron expression has no occurrence within five years", code="INVALID_CRON")


__all__ = [
    "CronExpression",
    "DefinitionService",
    "DueScheduleClaim",
    "EXECUTE_RUN_COMMAND",
    "EXECUTE_TASK_COMMAND",
    "ExecutionService",
    "GraphValidationReport",
    "IdempotencyConflictError",
    "OrchestrationServiceError",
    "SCAN_SCHEDULES_COMMAND",
    "ScheduleService",
    "ServiceValidationError",
    "StateConflictError",
]
