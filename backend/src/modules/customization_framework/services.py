"""Tenant-safe customization domain services and paid-module extension contract.

The module deliberately evaluates a small declarative language.  Tenant input
never reaches Python evaluation, imports, SQL, the filesystem, or the network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from src.core.api import CapabilityUnavailable
from src.core.async_jobs.models import OutboxEvent
from src.core.observability import get_correlation_id
from src.core.state_machine import (
    IdempotencyConflictError,
    StateMachine,
    Transition,
    registry as state_machine_registry,
)

from .models import (
    BusinessRule,
    BusinessRuleVersion,
    CustomFieldDefinition,
    CustomFieldValue,
    FormDefinition,
    FormLayoutVersion,
    RuleExecution,
)

logger = logging.getLogger("saraise.customization_framework")

MAX_JSON_BYTES: Final[int] = 64 * 1024
MAX_AST_NODES: Final[int] = 256
MAX_AST_DEPTH: Final[int] = 16
MAX_EVALUATION_MS: Final[int] = 50
SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
FIELD_TYPES: Final[frozenset[str]] = frozenset(
    {"text", "long_text", "integer", "decimal", "boolean", "date", "datetime", "uuid", "choice", "multi_choice", "json"}
)
RULE_TRIGGERS: Final[frozenset[str]] = frozenset({"validate", "before_create", "before_update", "form_change"})
CONDITION_OPERATORS: Final[frozenset[str]] = frozenset(
    {
        "and",
        "or",
        "not",
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "not_in",
        "contains",
        "starts_with",
        "ends_with",
        "is_null",
        "not_null",
        "changed",
    }
)
ACTION_TYPES: Final[frozenset[str]] = frozenset(
    {"reject-with-message", "set-derived-value", "set-required", "set-visible", "set-enabled", "emit-field-diagnostic"}
)


class CustomizationError(RuntimeError):
    """Base error that contains no sensitive payload."""


class CustomizationValidationError(CustomizationError):
    """A declarative document or domain command is invalid."""

    def __init__(self, message: str, *, detail: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.detail = dict(detail or {})


class CustomizationNotFound(CustomizationError):
    """A tenant-scoped object is not visible to the caller."""


class OptimisticLockConflict(CustomizationError):
    """The aggregate changed after the caller read it."""


class EvaluationIdempotencyConflict(CustomizationError):
    """An evaluation key was reused for different input."""


@dataclass(frozen=True, slots=True)
class ResourceContract:
    """Versioned, immutable contract registered by a free or paid module."""

    module: str
    resource: str
    version: str
    fields: Mapping[str, Mapping[str, object]]
    custom_field_types: frozenset[str]
    form_surfaces: frozenset[str]
    rule_triggers: frozenset[str]
    entitlement_keys: frozenset[str]
    capabilities: Mapping[str, object]
    available: bool = True
    discovery: Mapping[str, object] | None = None


class CustomizationRegistry:
    """Stable process registry consumed by free and paid modules.

    Registration is explicit and collision-safe.  Unregistering marks a
    contract unavailable rather than deleting its identity, so stored
    customization records remain interpretable.
    """

    _contracts: dict[tuple[str, str, str], ResourceContract] = {}
    _lock = threading.RLock()

    @classmethod
    def register_resource_contract(
        cls,
        module: str,
        resource: str,
        version: str,
        fields: Mapping[str, Mapping[str, object]],
        capabilities: Mapping[str, object],
    ) -> ResourceContract:
        module_key = _slug(module, "module")
        resource_key = _slug(resource, "resource")
        version_key = _required_text(version, "version", maximum=32)
        if not isinstance(fields, Mapping) or not isinstance(capabilities, Mapping):
            raise CustomizationValidationError("fields and capabilities must be objects")
        supported_types = frozenset(capabilities.get("custom_field_types", FIELD_TYPES))
        triggers = frozenset(capabilities.get("rule_triggers", RULE_TRIGGERS))
        if not supported_types or not supported_types.issubset(FIELD_TYPES):
            raise CustomizationValidationError("resource contract declares unsupported custom field types")
        if not triggers.issubset(RULE_TRIGGERS):
            raise CustomizationValidationError("resource contract declares unsupported rule triggers")
        normalized_fields = {_slug(key, "field key"): MappingProxyType(dict(value)) for key, value in fields.items()}
        contract = ResourceContract(
            module_key,
            resource_key,
            version_key,
            MappingProxyType(normalized_fields),
            supported_types,
            frozenset(str(item) for item in capabilities.get("form_surfaces", ("default",))),
            triggers,
            frozenset(str(item) for item in capabilities.get("entitlement_keys", ())),
            MappingProxyType(dict(capabilities)),
            bool(capabilities.get("available", True)),
            MappingProxyType(dict(capabilities.get("discovery", {}))),
        )
        identity = (module_key, resource_key, version_key)
        with cls._lock:
            existing = cls._contracts.get(identity)
            if existing is not None and existing != contract:
                raise CustomizationValidationError("an incompatible resource contract is already registered")
            cls._contracts[identity] = contract
        return contract

    @classmethod
    def unregister_resource_contract(cls, module: str, resource: str, version: str) -> ResourceContract | None:
        identity = (
            _slug(module, "module"),
            _slug(resource, "resource"),
            _required_text(version, "version", maximum=32),
        )
        with cls._lock:
            existing = cls._contracts.get(identity)
            if existing is None:
                return None
            unavailable = replace(existing, available=False)
            cls._contracts[identity] = unavailable
            return unavailable

    @classmethod
    def list_resource_contracts(cls, *, include_unavailable: bool = True) -> tuple[ResourceContract, ...]:
        with cls._lock:
            contracts = tuple(cls._contracts[key] for key in sorted(cls._contracts))
        return contracts if include_unavailable else tuple(item for item in contracts if item.available)

    @classmethod
    def resolve_resource_contract(cls, tenant_id: UUID, module: str, resource: str, version: str) -> ResourceContract:
        _uuid(tenant_id, "tenant_id")
        identity = (
            _slug(module, "module"),
            _slug(resource, "resource"),
            _required_text(version, "version", maximum=32),
        )
        with cls._lock:
            contract = cls._contracts.get(identity)
        if contract is None or not contract.available:
            raise CapabilityUnavailable(
                capability=f"{identity[0]}.{identity[1]}@{identity[2]}",
                detail={"code": "capability_unavailable", "module": identity[0], "resource": identity[1]},
            )
        return contract

    @classmethod
    def get_active_field_schema(cls, tenant_id: UUID, module: str, resource: str) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        definitions = CustomFieldDefinition.objects.filter(
            tenant_id=tenant,
            owner_module=_slug(module, "module"),
            target_resource=_slug(resource, "resource"),
            status="active",
            deleted_at__isnull=True,
        ).order_by("key")
        return {item.key: _definition_schema(item) for item in definitions}

    @classmethod
    def get_published_form(cls, tenant_id: UUID, module: str, resource: str, form_key: str) -> dict[str, object]:
        return FormService().get_render_schema(tenant_id, module=module, resource=resource, form_key=form_key)

    @classmethod
    def validate_record_extensions(
        cls, tenant_id: UUID, module: str, resource: str, record_id: UUID, values: Mapping[str, object]
    ) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        _uuid(record_id, "record_id")
        if not isinstance(values, Mapping):
            raise CustomizationValidationError("values must be an object")
        definitions = {
            item.key: item
            for item in CustomFieldDefinition.objects.filter(
                tenant_id=tenant,
                owner_module=_slug(module, "module"),
                target_resource=_slug(resource, "resource"),
                status="active",
                deleted_at__isnull=True,
            )
        }
        unknown = sorted(set(values) - set(definitions))
        diagnostics: list[dict[str, object]] = []
        if unknown:
            diagnostics.extend({"code": "unknown_field", "field": item} for item in unknown)
        service = CustomFieldService()
        for key, definition in definitions.items():
            if key not in values:
                if definition.required:
                    diagnostics.append({"code": "required", "field": key})
                continue
            try:
                service.validate_value(
                    tenant, definition_id=definition.id, value=values[key], target_record_id=record_id
                )
            except CustomizationValidationError as exc:
                diagnostics.append({"code": "invalid_value", "field": key, "message": str(exc)})
        return {"valid": not diagnostics, "diagnostics": diagnostics}

    @classmethod
    def evaluate_rules(
        cls,
        tenant_id: UUID,
        module: str,
        resource: str,
        trigger: str,
        record: Mapping[str, object],
        changed_fields: Sequence[str],
        actor_id: UUID,
        idempotency_key: str,
    ) -> list[RuleExecution]:
        return BusinessRuleService().evaluate_for_resource(
            tenant_id,
            module=module,
            resource=resource,
            trigger=trigger,
            record=record,
            changed_fields=changed_fields,
            target_record_id=None,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def get_dependency_impact(cls, tenant_id: UUID, module: str, resource: str, field_key: str) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        definition = CustomFieldDefinition.objects.filter(
            tenant_id=tenant,
            owner_module=_slug(module, "module"),
            target_resource=_slug(resource, "resource"),
            key=_slug(field_key, "field_key"),
            deleted_at__isnull=True,
        ).first()
        if definition is None:
            raise CustomizationNotFound("field definition not found")
        return CustomFieldService().get_definition_impact(tenant, definition_id=definition.id)


def _uuid(value: object, name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise CustomizationValidationError(f"{name} must be a valid UUID") from exc


def _required_text(value: object, name: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CustomizationValidationError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise CustomizationValidationError(f"{name} must not exceed {maximum} characters")
    return normalized


def _slug(value: object, name: str) -> str:
    normalized = _required_text(value, name, maximum=120).lower()
    if not SLUG_RE.fullmatch(normalized):
        raise CustomizationValidationError(f"{name} must use lowercase slug syntax")
    return normalized


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _json_size(value: object, name: str) -> None:
    if len(_canonical(value).encode("utf-8")) > MAX_JSON_BYTES:
        raise CustomizationValidationError(f"{name} exceeds the {MAX_JSON_BYTES}-byte limit")


def _hash(*documents: object) -> str:
    return hashlib.sha256(_canonical(documents).encode("utf-8")).hexdigest()


def _correlation_uuid() -> UUID:
    try:
        return UUID(get_correlation_id())
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid4()


def _event(
    tenant_id: UUID, aggregate_type: str, aggregate_id: UUID, event_type: str, actor_id: UUID, **payload: object
) -> OutboxEvent:
    safe_payload = {"entity_id": str(aggregate_id), "actor_id": str(actor_id), **payload}
    return OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=f"customization_framework.{event_type}",
        payload={"schema_version": 1, "correlation_id": str(_correlation_uuid()), "payload": safe_payload},
    )


def _log(operation: str, entity: object, actor_id: UUID, started: float, outcome: str = "succeeded") -> None:
    logger.info(
        "Customization domain operation completed",
        extra={
            "correlation_id": str(_correlation_uuid()),
            "tenant_id": str(getattr(entity, "tenant_id")),
            "actor_id": str(actor_id),
            "operation": operation,
            "entity_type": entity.__class__.__name__,
            "entity_id": str(getattr(entity, "id")),
            "resulting_state": getattr(entity, "status", None),
            "lock_version": getattr(entity, "lock_version", None),
            "version": getattr(entity, "version", None),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "outcome": outcome,
        },
    )


def _lock(queryset: QuerySet[Any], object_id: UUID, label: str) -> Any:
    value = queryset.select_for_update().filter(id=object_id).first()
    if value is None:
        raise CustomizationNotFound(f"{label} not found")
    return value


def _check_lock(value: object, expected: int) -> None:
    if not isinstance(expected, int) or expected < 1:
        raise CustomizationValidationError("expected_lock_version must be a positive integer")
    if getattr(value, "lock_version") != expected:
        raise OptimisticLockConflict("the record has changed; reload before retrying")


def _apply_transition(
    machine: StateMachine[Any], aggregate: Any, command: str, transition_key: str, actor_id: UUID
) -> bool:
    """Use the registered core machine while persisting coupled fields once.

    Lifecycle database checks couple status to timestamps/publication fields,
    so the generic machine's status-only save cannot be used for these models.
    This adapter treats the core machine definition as the transition authority;
    callers then save status, history, and companion fields atomically.
    """

    key = _required_text(transition_key, "transition_key", maximum=128)
    history = list(aggregate.transition_history or [])
    existing = next((item for item in history if item.get("transition_key") == key), None)
    if existing is not None:
        if existing.get("command") != command:
            raise IdempotencyConflictError("transition key belongs to another command")
        return False
    current = str(aggregate.status)
    if current in machine.terminal_states:
        raise CustomizationValidationError("terminal lifecycle state is immutable")
    edge = next(
        (item for item in machine.transitions if item.command == command and item.source == current),
        None,
    )
    if edge is None:
        raise CustomizationValidationError("lifecycle transition is not allowed")
    aggregate.status = edge.target
    history.append(
        {
            "transition_key": key,
            "command": command,
            "from_state": current,
            "to_state": edge.target,
            "occurred_at": timezone.now().isoformat(),
            "metadata": {"actor_id": str(actor_id), "correlation_id": str(_correlation_uuid())},
        }
    )
    aggregate.transition_history = history
    return True


def _normalize_definition_data(data: Mapping[str, object], *, partial: bool = False) -> dict[str, object]:
    allowed = {
        "key",
        "label",
        "description",
        "owner_module",
        "target_resource",
        "target_contract_version",
        "data_type",
        "required",
        "searchable",
        "default_value",
        "validation_schema",
        "presentation_schema",
    }
    unknown = set(data) - allowed
    if unknown:
        raise CustomizationValidationError(f"unknown field definition keys: {', '.join(sorted(unknown))}")
    normalized = dict(data)
    for key in ("key", "owner_module", "target_resource"):
        if key in normalized:
            normalized[key] = _slug(normalized[key], key)
    if "label" in normalized:
        normalized["label"] = _required_text(normalized["label"], "label", maximum=160)
    if "description" in normalized:
        normalized["description"] = str(normalized["description"]).strip()
    if "target_contract_version" in normalized:
        normalized["target_contract_version"] = _required_text(
            normalized["target_contract_version"], "target_contract_version", maximum=32
        )
    if "data_type" in normalized and normalized["data_type"] not in FIELD_TYPES:
        raise CustomizationValidationError("unsupported field data type")
    for key in ("validation_schema", "presentation_schema"):
        if key in normalized:
            if not isinstance(normalized[key], Mapping):
                raise CustomizationValidationError(f"{key} must be an object")
            _json_size(normalized[key], key)
            normalized[key] = dict(normalized[key])
    if not partial:
        missing = {"key", "label", "owner_module", "target_resource", "target_contract_version", "data_type"} - set(
            normalized
        )
        if missing:
            raise CustomizationValidationError(f"missing field definition keys: {', '.join(sorted(missing))}")
    return normalized


def _definition_schema(definition: CustomFieldDefinition) -> dict[str, object]:
    type_map: dict[str, object] = {
        "text": "string",
        "long_text": "string",
        "integer": "integer",
        "decimal": "number",
        "boolean": "boolean",
        "date": "string",
        "datetime": "string",
        "uuid": "string",
        "choice": "string",
        "multi_choice": "array",
        "json": ["object", "array", "string", "number", "boolean", "null"],
    }
    schema = dict(definition.validation_schema or {})
    declared = schema.get("type")
    expected = type_map[definition.data_type]
    if declared is not None and declared != expected:
        raise CustomizationValidationError("validation schema type conflicts with the field data type")
    schema["type"] = expected
    if definition.data_type == "date":
        schema.setdefault("format", "date")
    elif definition.data_type == "datetime":
        schema.setdefault("format", "date-time")
    elif definition.data_type == "uuid":
        schema.setdefault("format", "uuid")
    elif definition.data_type == "multi_choice":
        schema.setdefault("items", {"type": "string"})
        schema.setdefault("uniqueItems", True)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise CustomizationValidationError("validation schema is not a valid JSON Schema") from exc
    return schema


class CustomFieldService:
    """Field-definition and field-value aggregate service."""

    registry = CustomizationRegistry

    def create_definition(
        self, tenant_id: UUID, *, actor_id: UUID, data: Mapping[str, object]
    ) -> CustomFieldDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        values = _normalize_definition_data(data)
        contract = self.registry.resolve_resource_contract(
            tenant, str(values["owner_module"]), str(values["target_resource"]), str(values["target_contract_version"])
        )
        if values["data_type"] not in contract.custom_field_types:
            raise CustomizationValidationError("target contract does not support this field type")
        with transaction.atomic():
            definition = CustomFieldDefinition.objects.create(
                tenant_id=tenant, created_by=actor, updated_by=actor, status="draft", **values
            )
            _definition_schema(definition)
            if "default_value" in values and values["default_value"] is not None:
                self._validate_definition_value(definition, values["default_value"])
            _event(
                tenant, "field_definition", definition.id, "field_definition.created", actor, status=definition.status
            )
        _log("create_definition", definition, actor, started)
        return definition

    def get_definition(self, tenant_id: UUID, *, definition_id: UUID) -> CustomFieldDefinition:
        value = CustomFieldDefinition.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(definition_id, "definition_id"), deleted_at__isnull=True
        ).first()
        if value is None:
            raise CustomizationNotFound("field definition not found")
        return value

    def list_definitions(
        self, tenant_id: UUID, *, filters: Mapping[str, object] | None = None, ordering: str = "key"
    ) -> QuerySet[CustomFieldDefinition]:
        queryset = CustomFieldDefinition.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), deleted_at__isnull=True
        )
        allowed_filters = {"owner_module", "target_resource", "data_type", "status"}
        for key, value in (filters or {}).items():
            if key not in allowed_filters:
                raise CustomizationValidationError(f"unsupported definition filter: {key}")
            queryset = queryset.filter(**{key: value})
        return queryset.order_by(_ordering(ordering, {"key", "label", "status", "created_at", "updated_at"}, "key"))

    def update_definition(
        self,
        tenant_id: UUID,
        *,
        definition_id: UUID,
        expected_lock_version: int,
        actor_id: UUID,
        data: Mapping[str, object],
    ) -> CustomFieldDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        updates = _normalize_definition_data(data, partial=True)
        with transaction.atomic():
            definition = _lock(
                CustomFieldDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(definition_id, "definition_id"),
                "field definition",
            )
            _check_lock(definition, expected_lock_version)
            if definition.status != "draft" and {"key", "owner_module", "target_resource", "data_type"} & set(updates):
                raise CustomizationValidationError("identity and data type are immutable after activation")
            for key, value in updates.items():
                setattr(definition, key, value)
            self.registry.resolve_resource_contract(
                tenant, definition.owner_module, definition.target_resource, definition.target_contract_version
            )
            _definition_schema(definition)
            if definition.default_value is not None:
                self._validate_definition_value(definition, definition.default_value)
            definition.updated_by = actor
            definition.lock_version += 1
            definition.save(update_fields=[*updates, "updated_by", "lock_version", "updated_at"])
            _event(
                tenant,
                "field_definition",
                definition.id,
                "field_definition.updated",
                actor,
                status=definition.status,
                lock_version=definition.lock_version,
            )
        _log("update_definition", definition, actor, started)
        return definition

    def transition_definition(
        self, tenant_id: UUID, *, definition_id: UUID, command: str, transition_key: str, actor_id: UUID
    ) -> CustomFieldDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _lock(
                CustomFieldDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(definition_id, "definition_id"),
                "field definition",
            )
            if command == "activate":
                self.registry.resolve_resource_contract(
                    tenant, definition.owner_module, definition.target_resource, definition.target_contract_version
                )
                _definition_schema(definition)
                if definition.default_value is not None:
                    self._validate_definition_value(definition, definition.default_value)
            if not _apply_transition(FIELD_STATE_MACHINE, definition, command, transition_key, actor):
                return definition
            now = timezone.now()
            timestamp_field = {"activate": "activated_at", "deprecate": "deprecated_at", "retire": "retired_at"}[
                command
            ]
            setattr(definition, timestamp_field, now)
            definition.updated_by = actor
            definition.lock_version += 1
            definition.save(
                update_fields=[
                    "status",
                    "transition_history",
                    timestamp_field,
                    "updated_by",
                    "lock_version",
                    "updated_at",
                ]
            )
            event_name = {"activate": "activated", "deprecate": "deprecated", "retire": "retired"}[command]
            _event(
                tenant,
                "field_definition",
                definition.id,
                f"field_definition.{event_name}",
                actor,
                status=definition.status,
            )
        _log(f"transition_definition.{command}", definition, actor, started)
        return definition

    def delete_definition(
        self, tenant_id: UUID, *, definition_id: UUID, expected_lock_version: int, actor_id: UUID
    ) -> CustomFieldDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _lock(
                CustomFieldDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(definition_id, "definition_id"),
                "field definition",
            )
            _check_lock(definition, expected_lock_version)
            impact = self.get_definition_impact(tenant, definition_id=definition.id)
            if impact["blocking"]:
                raise CustomizationValidationError("field definition has unresolved dependencies", detail=impact)
            if definition.status not in {"draft", "retired"}:
                raise CustomizationValidationError("only draft or retired definitions can be deleted")
            definition.deleted_at = timezone.now()
            definition.deleted_by = actor
            definition.updated_by = actor
            definition.lock_version += 1
            definition.save(update_fields=["deleted_at", "deleted_by", "updated_by", "lock_version", "updated_at"])
            _event(
                tenant, "field_definition", definition.id, "field_definition.deleted", actor, status=definition.status
            )
        _log("delete_definition", definition, actor, started)
        return definition

    def _validate_definition_value(self, definition: CustomFieldDefinition, value: object) -> None:
        _json_size(value, "value")
        errors = sorted(
            Draft202012Validator(_definition_schema(definition), format_checker=FormatChecker()).iter_errors(value),
            key=lambda item: list(item.path),
        )
        if errors:
            raise CustomizationValidationError(
                "value does not conform to the field definition",
                detail={"errors": [{"path": list(item.path), "message": item.message} for item in errors]},
            )

    def validate_value(
        self, tenant_id: UUID, *, definition_id: UUID, value: object, target_record_id: UUID | None = None
    ) -> dict[str, object]:
        definition = self.get_definition(tenant_id, definition_id=definition_id)
        if target_record_id is not None:
            _uuid(target_record_id, "target_record_id")
        self._validate_definition_value(definition, value)
        return {
            "valid": True,
            "definition_id": str(definition.id),
            "definition_revision": definition.lock_version,
            "diagnostics": [],
        }

    def upsert_value(
        self,
        tenant_id: UUID,
        *,
        definition_id: UUID,
        target_record_id: UUID,
        value: object,
        source: str,
        expected_lock_version: int | None,
        actor_id: UUID,
    ) -> CustomFieldValue:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        target = _uuid(target_record_id, "target_record_id")
        if source not in {"ui", "api", "import"}:
            raise CustomizationValidationError("source must be ui, api, or import")
        definition = self.get_definition(tenant, definition_id=definition_id)
        if definition.status not in {"active", "deprecated"}:
            raise CustomizationValidationError("stored values require an active or deprecated definition")
        self.validate_value(tenant, definition_id=definition.id, value=value, target_record_id=target)
        with transaction.atomic():
            existing = (
                CustomFieldValue.objects.select_for_update()
                .filter(tenant_id=tenant, definition_id=definition.id, target_record_id=target, deleted_at__isnull=True)
                .first()
            )
            if existing is None:
                if expected_lock_version is not None:
                    raise OptimisticLockConflict("field value does not exist")
                result = CustomFieldValue.objects.create(
                    tenant_id=tenant,
                    definition=definition,
                    target_record_id=target,
                    value=value,
                    definition_revision=definition.lock_version,
                    source=source,
                    created_by=actor,
                    updated_by=actor,
                )
            else:
                if expected_lock_version is None:
                    raise OptimisticLockConflict("field value already exists; provide expected_lock_version")
                _check_lock(existing, expected_lock_version)
                existing.value = value
                existing.source = source
                existing.definition_revision = definition.lock_version
                existing.updated_by = actor
                existing.lock_version += 1
                existing.save(
                    update_fields=["value", "source", "definition_revision", "updated_by", "lock_version", "updated_at"]
                )
                result = existing
            _event(
                tenant,
                "field_value",
                result.id,
                "field_value.upserted",
                actor,
                definition_id=str(definition.id),
                lock_version=result.lock_version,
            )
        _log("upsert_value", result, actor, started)
        return result

    def get_value(self, tenant_id: UUID, *, definition_id: UUID, target_record_id: UUID) -> CustomFieldValue:
        value = (
            CustomFieldValue.objects.filter(
                tenant_id=_uuid(tenant_id, "tenant_id"),
                definition_id=_uuid(definition_id, "definition_id"),
                target_record_id=_uuid(target_record_id, "target_record_id"),
                deleted_at__isnull=True,
            )
            .select_related("definition")
            .first()
        )
        if value is None:
            raise CustomizationNotFound("field value not found")
        return value

    def list_values(
        self, tenant_id: UUID, *, target_record_id: UUID | None = None, definition_id: UUID | None = None
    ) -> QuerySet[CustomFieldValue]:
        if target_record_id is None and definition_id is None:
            raise CustomizationValidationError("target_record_id or definition_id is required")
        queryset = CustomFieldValue.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), deleted_at__isnull=True
        ).select_related("definition")
        if target_record_id is not None:
            queryset = queryset.filter(target_record_id=_uuid(target_record_id, "target_record_id"))
        if definition_id is not None:
            queryset = queryset.filter(definition_id=_uuid(definition_id, "definition_id"))
        return queryset.order_by("-updated_at", "id")

    def delete_value(
        self, tenant_id: UUID, *, value_id: UUID, expected_lock_version: int, actor_id: UUID
    ) -> CustomFieldValue:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = _lock(
                CustomFieldValue.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(value_id, "value_id"),
                "field value",
            )
            _check_lock(value, expected_lock_version)
            value.deleted_at = timezone.now()
            value.deleted_by = actor
            value.updated_by = actor
            value.lock_version += 1
            value.save(update_fields=["deleted_at", "deleted_by", "updated_by", "lock_version", "updated_at"])
            _event(
                tenant, "field_value", value.id, "field_value.deleted", actor, definition_id=str(value.definition_id)
            )
        _log("delete_value", value, actor, started)
        return value

    def get_definition_impact(self, tenant_id: UUID, *, definition_id: UUID) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        definition = self.get_definition(tenant, definition_id=definition_id)
        value_count = CustomFieldValue.objects.filter(
            tenant_id=tenant, definition_id=definition.id, deleted_at__isnull=True
        ).count()
        forms = []
        for version in FormLayoutVersion.objects.filter(tenant_id=tenant, form__deleted_at__isnull=True).select_related(
            "form"
        ):
            if definition.key in _collect_field_refs(version.layout):
                forms.append({"form_id": str(version.form_id), "version_id": str(version.id), "status": version.status})
        rules = []
        for version in BusinessRuleVersion.objects.filter(
            tenant_id=tenant, rule__deleted_at__isnull=True
        ).select_related("rule"):
            dependencies = version.dependencies or []
            if definition.key in dependencies or any(
                isinstance(item, Mapping) and item.get("field_key") == definition.key for item in dependencies
            ):
                rules.append({"rule_id": str(version.rule_id), "version_id": str(version.id), "status": version.status})
        return {
            "entity_type": "field_definition",
            "entity_id": str(definition.id),
            "value_count": value_count,
            "forms": forms,
            "rules": rules,
            "dependency_count": value_count + len(forms) + len(rules),
            "blocking": bool(value_count or forms or rules),
            "capability_unavailable": False,
        }


def _ordering(value: str, allowed: set[str], default: str) -> str:
    if not isinstance(value, str):
        return default
    descending = value.startswith("-")
    field = value[1:] if descending else value
    if field not in allowed:
        raise CustomizationValidationError("unsupported ordering field")
    return f"-{field}" if descending else field


def _collect_field_refs(document: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(document, Mapping):
        for key in ("field", "field_key"):
            value = document.get(key)
            if isinstance(value, str) and SLUG_RE.fullmatch(value):
                refs.add(value)
        for value in document.values():
            refs.update(_collect_field_refs(value))
    elif isinstance(document, list):
        for value in document:
            refs.update(_collect_field_refs(value))
    return refs


class FormService:
    """Form aggregate and immutable layout publication service."""

    registry = CustomizationRegistry

    def create_form(self, tenant_id: UUID, *, actor_id: UUID, data: Mapping[str, object]) -> FormDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        values = _form_data(data)
        self.registry.resolve_resource_contract(
            tenant, values["owner_module"], values["target_resource"], values["target_contract_version"]
        )
        with transaction.atomic():
            form = FormDefinition.objects.create(
                tenant_id=tenant, created_by=actor, updated_by=actor, status="draft", **values
            )
            _event(tenant, "form", form.id, "form.created", actor, status=form.status)
        _log("create_form", form, actor, started)
        return form

    def get_form(self, tenant_id: UUID, *, form_id: UUID) -> FormDefinition:
        value = FormDefinition.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(form_id, "form_id"), deleted_at__isnull=True
        ).first()
        if value is None:
            raise CustomizationNotFound("form not found")
        return value

    def list_forms(
        self, tenant_id: UUID, *, filters: Mapping[str, object] | None = None, ordering: str = "key"
    ) -> QuerySet[FormDefinition]:
        queryset = FormDefinition.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), deleted_at__isnull=True)
        for key, value in (filters or {}).items():
            if key not in {"owner_module", "target_resource", "status"}:
                raise CustomizationValidationError(f"unsupported form filter: {key}")
            queryset = queryset.filter(**{key: value})
        return queryset.order_by(_ordering(ordering, {"key", "name", "status", "created_at", "updated_at"}, "key"))

    def update_form(
        self, tenant_id: UUID, *, form_id: UUID, expected_lock_version: int, actor_id: UUID, data: Mapping[str, object]
    ) -> FormDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        updates = _form_data(data, partial=True)
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            _check_lock(form, expected_lock_version)
            if form.status != "draft" and {"key", "owner_module", "target_resource", "target_contract_version"} & set(
                updates
            ):
                raise CustomizationValidationError("published form identity is immutable")
            for key, value in updates.items():
                setattr(form, key, value)
            form.updated_by = actor
            form.lock_version += 1
            form.save(update_fields=[*updates, "updated_by", "lock_version", "updated_at"])
            _event(tenant, "form", form.id, "form.updated", actor, status=form.status, lock_version=form.lock_version)
        _log("update_form", form, actor, started)
        return form

    def validate_layout(self, tenant_id: UUID, *, form_id: UUID, layout: object) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        form = self.get_form(tenant, form_id=form_id)
        _json_size(layout, "layout")
        diagnostics: list[dict[str, object]] = []
        if (
            not isinstance(layout, Mapping)
            or layout.get("schema_version", 1) != 1
            or not isinstance(layout.get("sections"), list)
        ):
            diagnostics.append({"code": "invalid_layout_schema", "path": []})
        refs = _collect_field_refs(layout)
        if len(refs) != len(_ordered_field_ref_occurrences(layout)):
            diagnostics.append({"code": "duplicate_field_reference", "path": []})
        active = set(
            CustomFieldDefinition.objects.filter(
                tenant_id=tenant,
                owner_module=form.owner_module,
                target_resource=form.target_resource,
                deleted_at__isnull=True,
            )
            .exclude(status="retired")
            .values_list("key", flat=True)
        )
        for ref in sorted(refs - active):
            diagnostics.append({"code": "unresolved_or_retired_field", "field": ref})
        try:
            self.registry.resolve_resource_contract(
                tenant, form.owner_module, form.target_resource, form.target_contract_version
            )
        except CapabilityUnavailable:
            diagnostics.append({"code": "capability_unavailable"})
        return {"valid": not diagnostics, "diagnostics": diagnostics, "field_references": sorted(refs)}

    def create_layout_version(
        self, tenant_id: UUID, *, form_id: UUID, actor_id: UUID, layout: object, change_summary: str
    ) -> FormLayoutVersion:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        summary = _required_text(change_summary, "change_summary", maximum=500)
        report = self.validate_layout(tenant, form_id=form_id, layout=layout)
        if not report["valid"]:
            raise CustomizationValidationError("layout validation failed", detail=report)
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            version_number = (
                FormLayoutVersion.objects.filter(tenant_id=tenant, form_id=form.id)
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            ) + 1
            try:
                version = FormLayoutVersion.objects.create(
                    tenant_id=tenant,
                    form=form,
                    version=version_number,
                    schema_version=1,
                    layout=layout,
                    content_hash=_hash(layout),
                    change_summary=summary,
                    status="candidate",
                    validation_errors=[],
                    created_by=actor,
                )
            except IntegrityError as exc:
                raise CustomizationValidationError("an identical layout version already exists") from exc
            _event(
                tenant,
                "form_layout",
                version.id,
                "form.layout_version_created",
                actor,
                form_id=str(form.id),
                version=version.version,
            )
        _log("create_layout_version", version, actor, started)
        return version

    def publish_layout(
        self, tenant_id: UUID, *, form_id: UUID, layout_version_id: UUID, transition_key: str, actor_id: UUID
    ) -> FormLayoutVersion:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            source = _lock(
                FormLayoutVersion.objects.filter(tenant_id=tenant, form_id=form.id),
                _uuid(layout_version_id, "layout_version_id"),
                "layout version",
            )
            report = self.validate_layout(tenant, form_id=form.id, layout=source.layout)
            if not report["valid"]:
                raise CustomizationValidationError("layout publication validation failed", detail=report)
            # Republishing a superseded snapshot is the explicit rollback
            # contract. Content and hash remain immutable; only publication
            # lifecycle metadata changes through tenant-filtered updates.
            if source.status not in {"candidate", "published", "superseded"}:
                raise CustomizationValidationError("only a candidate or historical valid layout can be published")
            if (
                any(item.get("transition_key") == transition_key for item in (form.transition_history or []))
                and form.published_version != source.version
            ):
                raise IdempotencyConflictError("publication key was already used for another layout version")
            if source.status in {"published", "superseded"}:
                source_version = source.version
                next_version = (
                    FormLayoutVersion.objects.filter(tenant_id=tenant, form_id=form.id)
                    .order_by("-version")
                    .values_list("version", flat=True)
                    .first()
                    or 0
                ) + 1
                source = FormLayoutVersion.objects.create(
                    tenant_id=tenant,
                    form=form,
                    version=next_version,
                    schema_version=source.schema_version,
                    layout=source.layout,
                    content_hash=_hash(
                        source.layout,
                        {"republished_from": source_version, "version": next_version},
                    ),
                    change_summary=f"Republished from version {source_version}",
                    status="candidate",
                    validation_errors=[],
                    created_by=actor,
                )
            previous = (
                FormLayoutVersion.objects.select_for_update()
                .filter(tenant_id=tenant, form_id=form.id, status="published")
                .exclude(id=source.id)
                .first()
            )
            if previous is not None:
                FormLayoutVersion.objects.filter(tenant_id=tenant, id=previous.id).update(status="superseded")
            command = "publish_revision" if form.status == "published" else "publish"
            changed = _apply_transition(FORM_STATE_MACHINE, form, command, transition_key, actor)
            if not changed and form.published_version == source.version:
                return source
            now = timezone.now()
            FormLayoutVersion.objects.filter(tenant_id=tenant, id=source.id).update(
                status="published", published_at=now, published_by=actor
            )
            source.status = "published"
            source.published_at = now
            source.published_by = actor
            form.published_version = source.version
            form.published_at = now
            form.published_by = actor
            form.updated_by = actor
            form.lock_version += 1
            form.save(
                update_fields=[
                    "status",
                    "transition_history",
                    "published_version",
                    "published_at",
                    "published_by",
                    "updated_by",
                    "lock_version",
                    "updated_at",
                ]
            )
            _event(
                tenant,
                "form",
                form.id,
                "form.published",
                actor,
                layout_version_id=str(source.id),
                version=source.version,
            )
        _log("publish_layout", form, actor, started)
        return source

    def archive_form(self, tenant_id: UUID, *, form_id: UUID, transition_key: str, actor_id: UUID) -> FormDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            if not _apply_transition(FORM_STATE_MACHINE, form, "archive", transition_key, actor):
                return form
            form.archived_at = timezone.now()
            form.updated_by = actor
            form.lock_version += 1
            form.save(
                update_fields=[
                    "status",
                    "transition_history",
                    "archived_at",
                    "updated_by",
                    "lock_version",
                    "updated_at",
                ]
            )
            _event(tenant, "form", form.id, "form.archived", actor, status=form.status)
        _log("archive_form", form, actor, started)
        return form

    def delete_form(
        self, tenant_id: UUID, *, form_id: UUID, expected_lock_version: int, actor_id: UUID
    ) -> FormDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            _check_lock(form, expected_lock_version)
            if form.status == "published":
                raise CustomizationValidationError("published forms must be archived before deletion")
            form.deleted_at = timezone.now()
            form.deleted_by = actor
            form.updated_by = actor
            form.lock_version += 1
            form.save(update_fields=["deleted_at", "deleted_by", "updated_by", "lock_version", "updated_at"])
            _event(tenant, "form", form.id, "form.deleted", actor, status=form.status)
        _log("delete_form", form, actor, started)
        return form

    def get_render_schema(
        self,
        tenant_id: UUID,
        *,
        form_id: UUID | None = None,
        module: str | None = None,
        resource: str | None = None,
        form_key: str | None = None,
    ) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        if form_id is not None:
            form = self.get_form(tenant, form_id=form_id)
        elif module and resource and form_key:
            form = FormDefinition.objects.filter(
                tenant_id=tenant,
                owner_module=_slug(module, "module"),
                target_resource=_slug(resource, "resource"),
                key=_slug(form_key, "form_key"),
                status="published",
                deleted_at__isnull=True,
            ).first()
            if form is None:
                raise CustomizationNotFound("published form not found")
        else:
            raise CustomizationValidationError("form_id or module/resource/form_key is required")
        if form.status != "published" or form.published_version is None:
            raise CustomizationValidationError("form is not published")
        self.registry.resolve_resource_contract(
            tenant, form.owner_module, form.target_resource, form.target_contract_version
        )
        version = FormLayoutVersion.objects.filter(
            tenant_id=tenant, form_id=form.id, version=form.published_version, status="published"
        ).first()
        if version is None:
            raise CustomizationNotFound("published layout not found")
        return {
            "form_id": str(form.id),
            "form_key": form.key,
            "owner_module": form.owner_module,
            "target_resource": form.target_resource,
            "contract_version": form.target_contract_version,
            "version": version.version,
            "content_hash": version.content_hash,
            "layout": version.layout,
            "fields": CustomizationRegistry.get_active_field_schema(tenant, form.owner_module, form.target_resource),
        }

    def get_form_impact(self, tenant_id: UUID, *, form_id: UUID) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        form = self.get_form(tenant, form_id=form_id)
        versions = FormLayoutVersion.objects.filter(tenant_id=tenant, form_id=form.id)
        refs: set[str] = set()
        for layout in versions.values_list("layout", flat=True):
            refs.update(_collect_field_refs(layout))
        return {
            "entity_type": "form",
            "entity_id": str(form.id),
            "layout_version_count": versions.count(),
            "field_references": sorted(refs),
            "dependency_count": len(refs),
            "blocking": form.status == "published",
            "capability_unavailable": False,
        }


def _form_data(data: Mapping[str, object], partial: bool = False) -> dict[str, Any]:
    allowed = {"key", "name", "description", "owner_module", "target_resource", "target_contract_version"}
    unknown = set(data) - allowed
    if unknown:
        raise CustomizationValidationError(f"unknown form keys: {', '.join(sorted(unknown))}")
    result = dict(data)
    for key in ("key", "owner_module", "target_resource"):
        if key in result:
            result[key] = _slug(result[key], key)
    if "name" in result:
        result["name"] = _required_text(result["name"], "name", maximum=160)
    if "target_contract_version" in result:
        result["target_contract_version"] = _required_text(
            result["target_contract_version"], "target_contract_version", maximum=32
        )
    if "description" in result:
        result["description"] = str(result["description"]).strip()
    if not partial:
        missing = {"key", "name", "owner_module", "target_resource", "target_contract_version"} - set(result)
        if missing:
            raise CustomizationValidationError(f"missing form keys: {', '.join(sorted(missing))}")
    return result


def _ordered_field_ref_occurrences(document: object) -> list[str]:
    result: list[str] = []
    if isinstance(document, Mapping):
        for key in ("field", "field_key"):
            value = document.get(key)
            if isinstance(value, str) and SLUG_RE.fullmatch(value):
                result.append(value)
        for value in document.values():
            result.extend(_ordered_field_ref_occurrences(value))
    elif isinstance(document, list):
        for value in document:
            result.extend(_ordered_field_ref_occurrences(value))
    return result


class _EvaluationBudget:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.nodes = 0

    def visit(self, depth: int) -> None:
        self.nodes += 1
        if self.nodes > MAX_AST_NODES:
            raise CustomizationValidationError("rule AST exceeds node limit")
        if depth > MAX_AST_DEPTH:
            raise CustomizationValidationError("rule AST exceeds depth limit")
        if (time.monotonic() - self.started) * 1000 > MAX_EVALUATION_MS:
            raise TimeoutError("rule evaluation time limit exceeded")


def _validate_condition(node: object, budget: _EvaluationBudget, depth: int = 1) -> set[str]:
    budget.visit(depth)
    if not isinstance(node, Mapping):
        raise CustomizationValidationError("condition nodes must be objects")
    allowed_keys = {"operator", "operands", "operand", "field", "value", "values"}
    if set(node) - allowed_keys:
        raise CustomizationValidationError("condition contains unknown or dangerous keys")
    operator = node.get("operator")
    if operator not in CONDITION_OPERATORS:
        raise CustomizationValidationError("unknown rule condition operator")
    dependencies: set[str] = set()
    if operator in {"and", "or"}:
        operands = node.get("operands")
        if not isinstance(operands, list) or not operands:
            raise CustomizationValidationError(f"{operator} requires operands")
        for child in operands:
            dependencies.update(_validate_condition(child, budget, depth + 1))
    elif operator == "not":
        dependencies.update(_validate_condition(node.get("operand"), budget, depth + 1))
    else:
        field = node.get("field")
        if not isinstance(field, str) or not SLUG_RE.fullmatch(field):
            raise CustomizationValidationError("condition field must be a simple slug")
        dependencies.add(field)
    return dependencies


def _validate_actions(actions: object, budget: _EvaluationBudget, depth: int = 1) -> set[str]:
    if not isinstance(actions, list) or not actions:
        raise CustomizationValidationError("action_ast must be a non-empty array")
    dependencies: set[str] = set()
    for action in actions:
        budget.visit(depth)
        if not isinstance(action, Mapping):
            raise CustomizationValidationError("actions must be objects")
        if set(action) - {"type", "field", "value", "message", "code", "severity"}:
            raise CustomizationValidationError("action contains unknown or dangerous keys")
        if action.get("type") not in ACTION_TYPES:
            raise CustomizationValidationError("unknown rule action type")
        if action.get("type") in {
            "set-derived-value",
            "set-required",
            "set-visible",
            "set-enabled",
            "emit-field-diagnostic",
        }:
            field = action.get("field")
            if not isinstance(field, str) or not SLUG_RE.fullmatch(field):
                raise CustomizationValidationError("action field must be a simple slug")
            dependencies.add(field)
        if action.get("type") in {"reject-with-message", "emit-field-diagnostic"}:
            _required_text(action.get("message"), "action message", maximum=500)
    return dependencies


def _evaluate_condition(
    node: Mapping[str, object],
    record: Mapping[str, object],
    changed: frozenset[str],
    budget: _EvaluationBudget,
    diagnostics: list[dict[str, object]],
    depth: int = 1,
) -> bool:
    budget.visit(depth)
    operator = str(node["operator"])
    if operator == "and":
        result = all(_evaluate_condition(item, record, changed, budget, diagnostics, depth + 1) for item in node["operands"])  # type: ignore[arg-type]
    elif operator == "or":
        result = any(_evaluate_condition(item, record, changed, budget, diagnostics, depth + 1) for item in node["operands"])  # type: ignore[arg-type]
    elif operator == "not":
        result = not _evaluate_condition(node["operand"], record, changed, budget, diagnostics, depth + 1)  # type: ignore[arg-type]
    else:
        field = str(node["field"])
        actual = record.get(field)
        expected = node.get("value", node.get("values"))
        operations = {
            "eq": lambda: actual == expected,
            "ne": lambda: actual != expected,
            "gt": lambda: actual is not None and actual > expected,
            "gte": lambda: actual is not None and actual >= expected,
            "lt": lambda: actual is not None and actual < expected,
            "lte": lambda: actual is not None and actual <= expected,
            "in": lambda: actual in expected,
            "not_in": lambda: actual not in expected,
            "contains": lambda: expected in actual,
            "starts_with": lambda: isinstance(actual, str)
            and isinstance(expected, str)
            and actual.startswith(expected),
            "ends_with": lambda: isinstance(actual, str) and isinstance(expected, str) and actual.endswith(expected),
            "is_null": lambda: actual is None,
            "not_null": lambda: actual is not None,
            "changed": lambda: field in changed,
        }
        try:
            result = bool(operations[operator]())
        except (TypeError, ValueError):
            result = False
    diagnostics.append({"operator": operator, "matched": result})
    return result


class BusinessRuleService:
    """Immutable rule versions, lifecycle, and deterministic evaluation."""

    registry = CustomizationRegistry

    def create_rule(self, tenant_id: UUID, *, actor_id: UUID, data: Mapping[str, object]) -> BusinessRule:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        values = _rule_data(data)
        contract = self.registry.resolve_resource_contract(
            tenant, values["owner_module"], values["target_resource"], values["target_contract_version"]
        )
        if values["trigger"] not in contract.rule_triggers:
            raise CustomizationValidationError("target contract does not support this trigger")
        with transaction.atomic():
            rule = BusinessRule.objects.create(
                tenant_id=tenant, created_by=actor, updated_by=actor, status="draft", **values
            )
            _event(tenant, "business_rule", rule.id, "rule.created", actor, status=rule.status)
        _log("create_rule", rule, actor, started)
        return rule

    def get_rule(self, tenant_id: UUID, *, rule_id: UUID) -> BusinessRule:
        value = BusinessRule.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(rule_id, "rule_id"), deleted_at__isnull=True
        ).first()
        if value is None:
            raise CustomizationNotFound("business rule not found")
        return value

    def list_rules(
        self, tenant_id: UUID, *, filters: Mapping[str, object] | None = None, ordering: str = "priority"
    ) -> QuerySet[BusinessRule]:
        queryset = BusinessRule.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), deleted_at__isnull=True)
        for key, value in (filters or {}).items():
            if key not in {"owner_module", "target_resource", "trigger", "status"}:
                raise CustomizationValidationError(f"unsupported rule filter: {key}")
            queryset = queryset.filter(**{key: value})
        return queryset.order_by(
            _ordering(ordering, {"priority", "key", "status", "created_at", "updated_at"}, "priority"), "id"
        )

    def update_rule(
        self, tenant_id: UUID, *, rule_id: UUID, expected_lock_version: int, actor_id: UUID, data: Mapping[str, object]
    ) -> BusinessRule:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        updates = _rule_data(data, partial=True)
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            _check_lock(rule, expected_lock_version)
            if rule.status != "draft" and {
                "key",
                "owner_module",
                "target_resource",
                "trigger",
                "target_contract_version",
            } & set(updates):
                raise CustomizationValidationError("published rule identity and trigger are immutable")
            for key, value in updates.items():
                setattr(rule, key, value)
            rule.updated_by = actor
            rule.lock_version += 1
            rule.save(update_fields=[*updates, "updated_by", "lock_version", "updated_at"])
            _event(
                tenant,
                "business_rule",
                rule.id,
                "rule.updated",
                actor,
                status=rule.status,
                lock_version=rule.lock_version,
            )
        _log("update_rule", rule, actor, started)
        return rule

    def validate_rule_version(
        self, tenant_id: UUID, *, rule_id: UUID, condition_ast: object, action_ast: object
    ) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        rule = self.get_rule(tenant, rule_id=rule_id)
        _json_size(condition_ast, "condition_ast")
        _json_size(action_ast, "action_ast")
        budget = _EvaluationBudget()
        dependencies = _validate_condition(condition_ast, budget)
        dependencies.update(_validate_actions(action_ast, budget))
        fields = set(
            CustomFieldDefinition.objects.filter(
                tenant_id=tenant,
                owner_module=rule.owner_module,
                target_resource=rule.target_resource,
                deleted_at__isnull=True,
            )
            .exclude(status="retired")
            .values_list("key", flat=True)
        )
        contract = self.registry.resolve_resource_contract(
            tenant, rule.owner_module, rule.target_resource, rule.target_contract_version
        )
        fields.update(contract.fields)
        unresolved = sorted(dependencies - fields)
        if unresolved:
            raise CustomizationValidationError("rule references unresolved fields", detail={"fields": unresolved})
        return {"valid": True, "diagnostics": [], "dependencies": sorted(dependencies), "node_count": budget.nodes}

    def create_rule_version(
        self,
        tenant_id: UUID,
        *,
        rule_id: UUID,
        actor_id: UUID,
        condition_ast: object,
        action_ast: object,
        change_summary: str,
    ) -> BusinessRuleVersion:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        summary = _required_text(change_summary, "change_summary", maximum=500)
        report = self.validate_rule_version(tenant, rule_id=rule_id, condition_ast=condition_ast, action_ast=action_ast)
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            number = (
                BusinessRuleVersion.objects.filter(tenant_id=tenant, rule_id=rule.id)
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            ) + 1
            try:
                version = BusinessRuleVersion.objects.create(
                    tenant_id=tenant,
                    rule=rule,
                    version=number,
                    language_version=1,
                    condition_ast=condition_ast,
                    action_ast=action_ast,
                    dependencies=report["dependencies"],
                    content_hash=_hash(condition_ast, action_ast),
                    status="candidate",
                    validation_errors=[],
                    change_summary=summary,
                    created_by=actor,
                )
            except IntegrityError as exc:
                raise CustomizationValidationError("an identical rule version already exists") from exc
            _event(
                tenant,
                "business_rule_version",
                version.id,
                "rule.version_created",
                actor,
                rule_id=str(rule.id),
                version=number,
            )
        _log("create_rule_version", version, actor, started)
        return version

    def publish_rule_version(
        self, tenant_id: UUID, *, rule_id: UUID, version_id: UUID, transition_key: str, actor_id: UUID
    ) -> BusinessRuleVersion:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            source = _lock(
                BusinessRuleVersion.objects.filter(tenant_id=tenant, rule_id=rule.id),
                _uuid(version_id, "version_id"),
                "rule version",
            )
            self.validate_rule_version(
                tenant, rule_id=rule.id, condition_ast=source.condition_ast, action_ast=source.action_ast
            )
            if source.status not in {"candidate", "published", "superseded"}:
                raise CustomizationValidationError("only a candidate or historical valid rule can be published")
            if (
                any(item.get("transition_key") == transition_key for item in (rule.transition_history or []))
                and rule.published_version != source.version
            ):
                raise IdempotencyConflictError("publication key was already used for another rule version")
            if source.status in {"published", "superseded"}:
                source_version = source.version
                next_version = (
                    BusinessRuleVersion.objects.filter(tenant_id=tenant, rule_id=rule.id)
                    .order_by("-version")
                    .values_list("version", flat=True)
                    .first()
                    or 0
                ) + 1
                source = BusinessRuleVersion.objects.create(
                    tenant_id=tenant,
                    rule=rule,
                    version=next_version,
                    language_version=source.language_version,
                    condition_ast=source.condition_ast,
                    action_ast=source.action_ast,
                    dependencies=source.dependencies,
                    content_hash=_hash(
                        source.condition_ast,
                        source.action_ast,
                        {"republished_from": source_version, "version": next_version},
                    ),
                    status="candidate",
                    validation_errors=[],
                    change_summary=f"Republished from version {source_version}",
                    created_by=actor,
                )
            previous = (
                BusinessRuleVersion.objects.select_for_update()
                .filter(tenant_id=tenant, rule_id=rule.id, status="published")
                .exclude(id=source.id)
                .first()
            )
            if previous is not None:
                BusinessRuleVersion.objects.filter(tenant_id=tenant, id=previous.id).update(status="superseded")
            command = "publish_revision" if rule.status in {"published", "paused"} else "publish"
            changed = _apply_transition(RULE_STATE_MACHINE, rule, command, transition_key, actor)
            if not changed and rule.published_version == source.version:
                return source
            now = timezone.now()
            BusinessRuleVersion.objects.filter(tenant_id=tenant, id=source.id).update(
                status="published", published_at=now, published_by=actor
            )
            source.status = "published"
            source.published_at = now
            source.published_by = actor
            rule.published_version = source.version
            rule.published_at = now
            rule.published_by = actor
            rule.updated_by = actor
            rule.lock_version += 1
            rule.save(
                update_fields=[
                    "status",
                    "transition_history",
                    "published_version",
                    "published_at",
                    "published_by",
                    "updated_by",
                    "lock_version",
                    "updated_at",
                ]
            )
            _event(
                tenant,
                "business_rule",
                rule.id,
                "rule.published",
                actor,
                version_id=str(source.id),
                version=source.version,
            )
        _log("publish_rule_version", rule, actor, started)
        return source

    def transition_rule(
        self, tenant_id: UUID, *, rule_id: UUID, command: str, transition_key: str, actor_id: UUID
    ) -> BusinessRule:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            if not _apply_transition(RULE_STATE_MACHINE, rule, command, transition_key, actor):
                return rule
            rule.updated_by = actor
            rule.lock_version += 1
            rule.save(update_fields=["status", "transition_history", "updated_by", "lock_version", "updated_at"])
            _event(tenant, "business_rule", rule.id, f"rule.{command}d", actor, status=rule.status)
        _log(f"transition_rule.{command}", rule, actor, started)
        return rule

    def delete_rule(
        self, tenant_id: UUID, *, rule_id: UUID, expected_lock_version: int, actor_id: UUID
    ) -> BusinessRule:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            _check_lock(rule, expected_lock_version)
            if rule.status not in {"draft", "retired"}:
                raise CustomizationValidationError("only draft or retired rules can be deleted")
            rule.deleted_at = timezone.now()
            rule.deleted_by = actor
            rule.updated_by = actor
            rule.lock_version += 1
            rule.save(update_fields=["deleted_at", "deleted_by", "updated_by", "lock_version", "updated_at"])
            _event(tenant, "business_rule", rule.id, "rule.deleted", actor, status=rule.status)
        _log("delete_rule", rule, actor, started)
        return rule

    def evaluate(
        self,
        tenant_id: UUID,
        *,
        rule_id: UUID,
        record: Mapping[str, object],
        changed_fields: Sequence[str],
        target_record_id: UUID | None,
        actor_id: UUID,
        idempotency_key: str,
    ) -> RuleExecution:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        rule = self.get_rule(tenant, rule_id=rule_id)
        key = _required_text(idempotency_key, "idempotency_key", maximum=128)
        fingerprint = _hash(record, sorted(changed_fields))
        existing = RuleExecution.objects.filter(tenant_id=tenant, rule_id=rule.id, idempotency_key=key).first()
        if existing is not None:
            if existing.input_fingerprint != fingerprint:
                raise EvaluationIdempotencyConflict("idempotency key was already used for different input")
            return existing
        if rule.status != "published" or rule.published_version is None:
            raise CustomizationValidationError("only published rules can be evaluated")
        version = BusinessRuleVersion.objects.filter(
            tenant_id=tenant, rule_id=rule.id, version=rule.published_version, status="published"
        ).first()
        if version is None:
            raise CustomizationNotFound("published rule version not found")
        started = time.monotonic()
        diagnostics: list[dict[str, object]] = []
        status = "failed"
        result: dict[str, object] = {}
        try:
            self.validate_rule_version(
                tenant, rule_id=rule.id, condition_ast=version.condition_ast, action_ast=version.action_ast
            )
            budget = _EvaluationBudget()
            matched = _evaluate_condition(version.condition_ast, record, frozenset(changed_fields), budget, diagnostics)
            actions = []
            if matched:
                for action in version.action_ast:
                    safe = {
                        key: action[key]
                        for key in ("type", "field", "value", "message", "code", "severity")
                        if key in action
                    }
                    actions.append(safe)
                status = "rejected" if any(item["type"] == "reject-with-message" for item in actions) else "matched"
                result = {"matched": True, "actions": actions}
            else:
                status = "not_matched"
                result = {"matched": False, "actions": []}
        except Exception as exc:
            diagnostics = [{"code": "evaluation_failed", "error_type": exc.__class__.__name__}]
            result = {"matched": False, "actions": []}
        duration = max(0, int((time.monotonic() - started) * 1000))
        correlation = _correlation_uuid()
        try:
            execution = RuleExecution.objects.create(
                tenant_id=tenant,
                rule=rule,
                rule_version=version,
                target_record_id=_uuid(target_record_id, "target_record_id") if target_record_id else None,
                trigger=rule.trigger,
                idempotency_key=key,
                status=status,
                input_fingerprint=fingerprint,
                result=result,
                diagnostics=diagnostics,
                duration_ms=duration,
                correlation_id=correlation,
                executed_by=actor,
            )
        except IntegrityError:
            existing = RuleExecution.objects.filter(tenant_id=tenant, rule_id=rule.id, idempotency_key=key).first()
            if existing is None:
                raise
            if existing.input_fingerprint != fingerprint:
                raise EvaluationIdempotencyConflict("idempotency key was already used for different input")
            return existing
        _log("evaluate_rule", execution, actor, started, outcome=status)
        return execution

    def evaluate_for_resource(
        self,
        tenant_id: UUID,
        *,
        module: str,
        resource: str,
        trigger: str,
        record: Mapping[str, object],
        changed_fields: Sequence[str],
        target_record_id: UUID | None,
        actor_id: UUID,
        idempotency_key: str,
    ) -> list[RuleExecution]:
        tenant = _uuid(tenant_id, "tenant_id")
        trigger_value = _required_text(trigger, "trigger", maximum=32)
        if trigger_value not in RULE_TRIGGERS:
            raise CustomizationValidationError("unsupported rule trigger")
        rules = BusinessRule.objects.filter(
            tenant_id=tenant,
            owner_module=_slug(module, "module"),
            target_resource=_slug(resource, "resource"),
            trigger=trigger_value,
            status="published",
            deleted_at__isnull=True,
        ).order_by("priority", "id")
        results = []
        for rule in rules:
            execution = self.evaluate(
                tenant,
                rule_id=rule.id,
                record=record,
                changed_fields=changed_fields,
                target_record_id=target_record_id,
                actor_id=actor_id,
                idempotency_key=f"{idempotency_key}:{rule.id}",
            )
            results.append(execution)
            if rule.stop_on_match and execution.status in {"matched", "rejected"}:
                break
        return results

    def list_executions(
        self, tenant_id: UUID, *, filters: Mapping[str, object] | None = None, ordering: str = "-executed_at"
    ) -> QuerySet[RuleExecution]:
        queryset = RuleExecution.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related(
            "rule", "rule_version"
        )
        mappings = {
            "rule_id": "rule_id",
            "rule_version_id": "rule_version_id",
            "target_record_id": "target_record_id",
            "status": "status",
            "correlation_id": "correlation_id",
            "executed_after": "executed_at__gte",
            "executed_before": "executed_at__lte",
        }
        for key, value in (filters or {}).items():
            if key not in mappings:
                raise CustomizationValidationError(f"unsupported execution filter: {key}")
            queryset = queryset.filter(**{mappings[key]: value})
        return queryset.order_by(_ordering(ordering, {"executed_at", "duration_ms", "status"}, "executed_at"))

    def get_execution(self, tenant_id: UUID, *, execution_id: UUID) -> RuleExecution:
        value = (
            RuleExecution.objects.filter(
                tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(execution_id, "execution_id")
            )
            .select_related("rule", "rule_version")
            .first()
        )
        if value is None:
            raise CustomizationNotFound("rule execution not found")
        return value

    def get_rule_impact(self, tenant_id: UUID, *, rule_id: UUID) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        rule = self.get_rule(tenant, rule_id=rule_id)
        versions = BusinessRuleVersion.objects.filter(tenant_id=tenant, rule_id=rule.id)
        executions = RuleExecution.objects.filter(tenant_id=tenant, rule_id=rule.id).count()
        dependencies = sorted(
            {str(item) for values in versions.values_list("dependencies", flat=True) for item in (values or [])}
        )
        return {
            "entity_type": "business_rule",
            "entity_id": str(rule.id),
            "version_count": versions.count(),
            "execution_count": executions,
            "field_references": dependencies,
            "dependency_count": len(dependencies) + executions,
            "blocking": rule.status == "published" or executions > 0,
            "capability_unavailable": False,
        }


def _rule_data(data: Mapping[str, object], partial: bool = False) -> dict[str, Any]:
    allowed = {
        "key",
        "name",
        "description",
        "owner_module",
        "target_resource",
        "target_contract_version",
        "trigger",
        "priority",
        "stop_on_match",
    }
    unknown = set(data) - allowed
    if unknown:
        raise CustomizationValidationError(f"unknown rule keys: {', '.join(sorted(unknown))}")
    result = dict(data)
    for key in ("key", "owner_module", "target_resource"):
        if key in result:
            result[key] = _slug(result[key], key)
    if "name" in result:
        result["name"] = _required_text(result["name"], "name", maximum=160)
    if "target_contract_version" in result:
        result["target_contract_version"] = _required_text(
            result["target_contract_version"], "target_contract_version", maximum=32
        )
    if "trigger" in result and result["trigger"] not in RULE_TRIGGERS:
        raise CustomizationValidationError("unsupported rule trigger")
    if "priority" in result and (not isinstance(result["priority"], int) or not 1 <= result["priority"] <= 1000):
        raise CustomizationValidationError("priority must be between 1 and 1000")
    if "description" in result:
        result["description"] = str(result["description"]).strip()
    if not partial:
        missing = {"key", "name", "owner_module", "target_resource", "target_contract_version", "trigger"} - set(result)
        if missing:
            raise CustomizationValidationError(f"missing rule keys: {', '.join(sorted(missing))}")
    return result


FIELD_STATE_MACHINE = StateMachine(
    name="customization_framework.field_definition",
    model=CustomFieldDefinition,
    states=("draft", "active", "deprecated", "retired"),
    terminal_states=("retired",),
    transitions=(
        Transition("activate", "draft", "active"),
        Transition("deprecate", "active", "deprecated"),
        Transition("retire", "deprecated", "retired"),
    ),
)
FORM_STATE_MACHINE = StateMachine(
    name="customization_framework.form",
    model=FormDefinition,
    states=("draft", "published", "archived"),
    terminal_states=("archived",),
    transitions=(
        Transition("publish", "draft", "published"),
        Transition("publish_revision", "published", "published"),
        Transition("archive", "draft", "archived"),
        Transition("archive", "published", "archived"),
    ),
)
RULE_STATE_MACHINE = StateMachine(
    name="customization_framework.rule",
    model=BusinessRule,
    states=("draft", "published", "paused", "retired"),
    terminal_states=("retired",),
    transitions=(
        Transition("publish", "draft", "published"),
        Transition("pause", "published", "paused"),
        Transition("resume", "paused", "published"),
        Transition("publish_revision", "published", "published"),
        Transition("publish_revision", "paused", "published"),
        Transition("retire", "draft", "retired"),
        Transition("retire", "published", "retired"),
        Transition("retire", "paused", "retired"),
    ),
)
for _machine in (FIELD_STATE_MACHINE, FORM_STATE_MACHINE, RULE_STATE_MACHINE):
    if _machine.name not in state_machine_registry.names():
        state_machine_registry.register(_machine.name or "", _machine)


__all__ = [
    "ACTION_TYPES",
    "BusinessRuleService",
    "CONDITION_OPERATORS",
    "CustomizationError",
    "CustomizationNotFound",
    "CustomizationRegistry",
    "CustomizationValidationError",
    "EvaluationIdempotencyConflict",
    "FIELD_TYPES",
    "FormService",
    "MAX_AST_DEPTH",
    "MAX_AST_NODES",
    "MAX_EVALUATION_MS",
    "OptimisticLockConflict",
    "ResourceContract",
    "RULE_TRIGGERS",
    "CustomFieldService",
]
