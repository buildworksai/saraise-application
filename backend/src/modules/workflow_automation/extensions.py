"""Versioned, process-safe workflow extension surface.

Industry modules contribute descriptors and ORM-free handlers from their own
``AppConfig.ready`` methods.  Published steps pin the descriptor version and
fingerprint, preventing an upgrade from silently changing immutable workflow
semantics.  Catalog discovery is intentionally separate from execution access.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from copy import deepcopy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeAlias, TypeVar, runtime_checkable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from jsonschema import Draft202012Validator, SchemaError, ValidationError as JsonSchemaValidationError

from src.core.api.results import OperationResult
from src.core.health import HealthCheckResult

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
JsonMapping: TypeAlias = Mapping[str, JsonValue]

WORKFLOW_SPI_VERSION = "1.0"
CORE_MODULE = "workflow_automation"
CORE_ENTITLEMENT = "module.workflow_automation"


class WorkflowExtensionError(RuntimeError):
    """Base registry and extension contract error."""


class DuplicateWorkflowExtension(WorkflowExtensionError):
    """Raised when import order would silently replace a registered key."""


class WorkflowExtensionNotFound(WorkflowExtensionError, LookupError):
    """Raised when an immutable definition references an unavailable handler."""


class WorkflowExtensionReplacementForbidden(WorkflowExtensionError):
    """Raised when replacement is attempted outside controlled dev/test mode."""


class WorkflowExtensionContractError(WorkflowExtensionError, ValueError):
    """Raised for malformed descriptors, schemas, invocations, or results."""


class _FrozenJsonObject(dict[str, JsonValue]):
    """JSON-serializable immutable mapping with catalog-safe deepcopy."""

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise TypeError("workflow extension schemas are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, JsonValue]:
        return deepcopy(dict(self), memo)


def _json_object(value: Mapping[str, Any], label: str) -> JsonObject:
    if not isinstance(value, Mapping):
        raise WorkflowExtensionContractError(f"{label} must be a JSON object")
    result = dict(value)
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkflowExtensionContractError(f"{label} must contain JSON-compatible values") from exc
    return result  # type: ignore[return-value]


def _schema(value: Mapping[str, Any], label: str) -> JsonMapping:
    result = _json_object(value, label)
    if not result:
        raise WorkflowExtensionContractError(f"{label} must declare an explicit JSON schema")
    encoded = json.dumps(result, sort_keys=True)
    if any(token in encoded for token in ('"$ref"', '"$dynamicRef"', '"$recursiveRef"')):
        raise WorkflowExtensionContractError(f"{label} cannot use remote or recursive schema references")
    try:
        Draft202012Validator.check_schema(result)
    except SchemaError as exc:
        raise WorkflowExtensionContractError(f"{label} is invalid: {exc.message}") from exc
    return _FrozenJsonObject(result)


def _required_text(value: Any, label: str, *, max_length: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowExtensionContractError(f"{label} must be a non-empty string")
    clean = value.strip()
    if clean != value or len(clean) > max_length:
        raise WorkflowExtensionContractError(f"{label} must be canonical and at most {max_length} characters")
    return clean


def _validate(value: Mapping[str, Any], schema: Mapping[str, Any], label: str) -> None:
    try:
        Draft202012Validator(dict(schema)).validate(dict(value))
    except JsonSchemaValidationError as exc:
        path = "/" + "/".join(str(part) for part in exc.absolute_path) if exc.absolute_path else "/"
        raise WorkflowExtensionContractError(f"{label}{path}: {exc.message}") from exc


@dataclass(frozen=True, slots=True)
class LookupDescriptor:
    """A schema field whose selectable values come from a governed provider."""

    field: str
    provider_key: str
    label: str
    multiple: bool = False

    def __post_init__(self) -> None:
        _required_text(self.field, "lookup field", max_length=100)
        _required_text(self.provider_key, "lookup provider key", max_length=150)
        _required_text(self.label, "lookup label")


@dataclass(frozen=True, slots=True)
class ActionDescriptor:
    key: str
    display_name: str
    description: str
    category: str
    owning_module: str
    required_permission: str
    required_entitlement: str
    quota_resource: str
    quota_cost: Decimal
    configuration_schema: JsonMapping
    input_schema: JsonMapping
    output_schema: JsonMapping
    idempotency_supported: bool
    outbound_network_required: bool
    icon_key: str
    schema_version: str = "1"
    spi_version: str = WORKFLOW_SPI_VERSION
    module_version: str = "2.0.0"
    lookup_descriptors: tuple[LookupDescriptor, ...] = ()
    availability: str = "available"
    availability_reason: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "key",
            "display_name",
            "description",
            "category",
            "owning_module",
            "required_permission",
            "required_entitlement",
            "quota_resource",
            "icon_key",
            "schema_version",
            "spi_version",
            "module_version",
        ):
            _required_text(getattr(self, field_name), field_name, max_length=255)
        if self.spi_version != WORKFLOW_SPI_VERSION:
            raise WorkflowExtensionContractError(f"Unsupported workflow action SPI {self.spi_version!r}")
        if self.quota_cost < 0:
            raise WorkflowExtensionContractError("quota_cost cannot be negative")
        if self.availability not in {"available", "locked", "setup_required", "unavailable"}:
            raise WorkflowExtensionContractError("availability is invalid")
        object.__setattr__(self, "configuration_schema", _schema(self.configuration_schema, "configuration_schema"))
        object.__setattr__(self, "input_schema", _schema(self.input_schema, "input_schema"))
        object.__setattr__(self, "output_schema", _schema(self.output_schema, "output_schema"))

    @property
    def contract_version(self) -> str:
        return f"{self.spi_version}:{self.module_version}:{self.schema_version}"

    @property
    def contract_fingerprint(self) -> str:
        payload = {
            "key": self.key,
            "contract_version": self.contract_version,
            "configuration_schema": dict(self.configuration_schema),
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "idempotency_supported": self.idempotency_supported,
            "outbound_network_required": self.outbound_network_required,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ConditionDescriptor:
    key: str
    display_name: str
    description: str
    owning_module: str
    required_entitlement: str
    condition_schema: JsonMapping
    context_schema: JsonMapping
    schema_version: str = "1"
    spi_version: str = WORKFLOW_SPI_VERSION
    module_version: str = "2.0.0"
    availability: str = "available"
    availability_reason: str = ""

    def __post_init__(self) -> None:
        for name in ("key", "display_name", "description", "owning_module", "required_entitlement"):
            _required_text(getattr(self, name), name)
        if self.spi_version != WORKFLOW_SPI_VERSION:
            raise WorkflowExtensionContractError(f"Unsupported workflow condition SPI {self.spi_version!r}")
        object.__setattr__(self, "condition_schema", _schema(self.condition_schema, "condition_schema"))
        object.__setattr__(self, "context_schema", _schema(self.context_schema, "context_schema"))

    @property
    def contract_version(self) -> str:
        return f"{self.spi_version}:{self.module_version}:{self.schema_version}"

    @property
    def contract_fingerprint(self) -> str:
        payload = {
            "key": self.key,
            "contract_version": self.contract_version,
            "condition_schema": dict(self.condition_schema),
            "context_schema": dict(self.context_schema),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SubjectResolverDescriptor:
    key: str
    display_name: str
    owning_module: str
    entity_types: tuple[str, ...]
    required_entitlement: str
    schema_version: str = "1"
    availability: str = "available"
    availability_reason: str = ""

    def __post_init__(self) -> None:
        for name in ("key", "display_name", "owning_module", "required_entitlement"):
            _required_text(getattr(self, name), name)
        if not self.entity_types or not all(isinstance(item, str) and item.strip() for item in self.entity_types):
            raise WorkflowExtensionContractError("entity_types must contain canonical names")


@dataclass(frozen=True, slots=True)
class AssigneeProviderDescriptor:
    key: str
    display_name: str
    owning_module: str
    assignment_kind: str
    required_permission: str
    required_entitlement: str
    result_schema: JsonMapping
    schema_version: str = "1"
    availability: str = "available"
    availability_reason: str = ""

    def __post_init__(self) -> None:
        for name in (
            "key",
            "display_name",
            "owning_module",
            "required_permission",
            "required_entitlement",
        ):
            _required_text(getattr(self, name), name)
        if self.assignment_kind not in {"user", "role", "custom"}:
            raise WorkflowExtensionContractError("assignment_kind is invalid")
        object.__setattr__(self, "result_schema", _schema(self.result_schema, "result_schema"))


@dataclass(frozen=True, slots=True)
class WorkflowActionInvocation:
    tenant_id: uuid.UUID
    workflow_id: uuid.UUID
    instance_id: uuid.UUID
    step_id: uuid.UUID
    actor_id: str | None
    correlation_id: str
    idempotency_key: str
    handler_key: str
    descriptor_version: str
    descriptor_fingerprint: str
    config: JsonMapping
    input: JsonMapping
    cancellation_probe: Any = field(repr=False)

    def __post_init__(self) -> None:
        for name in ("tenant_id", "workflow_id", "instance_id", "step_id"):
            if not isinstance(getattr(self, name), uuid.UUID):
                raise WorkflowExtensionContractError(f"{name} must be a UUID")
        for name in (
            "correlation_id",
            "idempotency_key",
            "handler_key",
            "descriptor_version",
            "descriptor_fingerprint",
        ):
            _required_text(getattr(self, name), name)
        if not callable(self.cancellation_probe):
            raise WorkflowExtensionContractError("cancellation_probe must be callable")
        object.__setattr__(self, "config", MappingProxyType(_json_object(self.config, "config")))
        object.__setattr__(self, "input", MappingProxyType(_json_object(self.input, "input")))


@dataclass(frozen=True, slots=True)
class WorkflowConditionEvaluation:
    tenant_id: uuid.UUID
    instance_id: uuid.UUID
    condition: JsonMapping
    context: JsonMapping


@dataclass(frozen=True, slots=True)
class SubjectResolutionInvocation:
    tenant_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class AssigneeSearchInvocation:
    tenant_id: uuid.UUID
    limit: int
    query: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, uuid.UUID):
            raise WorkflowExtensionContractError("tenant_id must be a UUID")
        if self.limit < 1:
            raise WorkflowExtensionContractError("limit must be positive")


@runtime_checkable
class WorkflowActionHandler(Protocol):
    descriptor: ActionDescriptor

    @property
    def key(self) -> str: ...

    @property
    def schema_version(self) -> str: ...

    def validate_config(self, config: Mapping[str, Any]) -> None: ...

    def execute(self, invocation: WorkflowActionInvocation) -> OperationResult[JsonObject]: ...

    def health(self) -> HealthCheckResult: ...


@runtime_checkable
class WorkflowConditionHandler(Protocol):
    descriptor: ConditionDescriptor

    @property
    def key(self) -> str: ...

    @property
    def schema_version(self) -> str: ...

    def validate(self, condition: Mapping[str, Any]) -> None: ...

    def evaluate(self, context: Mapping[str, Any]) -> bool: ...


@runtime_checkable
class WorkflowSubjectResolver(Protocol):
    descriptor: SubjectResolverDescriptor

    @property
    def key(self) -> str: ...

    def resolve(self, invocation: SubjectResolutionInvocation) -> OperationResult[JsonObject]: ...


@runtime_checkable
class WorkflowAssigneeProvider(Protocol):
    descriptor: AssigneeProviderDescriptor

    @property
    def key(self) -> str: ...

    def search(self, invocation: AssigneeSearchInvocation) -> OperationResult[list[JsonObject]]: ...


HandlerT = TypeVar("HandlerT")
DescriptorT = TypeVar("DescriptorT")


class VersionedRegistry(Generic[HandlerT, DescriptorT]):
    """Thread-safe registry with explicit, dev/test-only replacement."""

    def __init__(self, label: str) -> None:
        self.label = label
        self._entries: dict[str, HandlerT] = {}
        self._lock = threading.RLock()

    def register(self, handler: HandlerT, *, replace: bool = False) -> HandlerT:
        key = _required_text(getattr(handler, "key", None), f"{self.label} key", max_length=150)
        descriptor = getattr(handler, "descriptor", None)
        if descriptor is None or getattr(descriptor, "key", None) != key:
            raise WorkflowExtensionContractError(f"{self.label} descriptor key must match handler key")
        with self._lock:
            if key in self._entries:
                if not replace:
                    raise DuplicateWorkflowExtension(f"{self.label} {key!r} is already registered")
                if not _replacement_allowed():
                    raise WorkflowExtensionReplacementForbidden(
                        f"{self.label} replacement is disabled outside development/test mode"
                    )
            self._entries[key] = handler
        return handler

    def get(self, key: str) -> HandlerT:
        canonical = _required_text(key, f"{self.label} key", max_length=150)
        with self._lock:
            try:
                return self._entries[canonical]
            except KeyError as exc:
                raise WorkflowExtensionNotFound(f"No {self.label} is registered for {canonical!r}") from exc

    def unregister(self, key: str) -> HandlerT | None:
        canonical = _required_text(key, f"{self.label} key", max_length=150)
        with self._lock:
            return self._entries.pop(canonical, None)

    def descriptors(self) -> tuple[DescriptorT, ...]:
        with self._lock:
            descriptors = tuple(getattr(handler, "descriptor") for handler in self._entries.values())
        return tuple(sorted(descriptors, key=lambda descriptor: getattr(descriptor, "key")))

    list_descriptors = descriptors

    def catalog(self, access_context: Mapping[str, Any] | None = None) -> tuple[DescriptorT, ...]:
        catalog: list[DescriptorT] = []
        for descriptor in self.descriptors():
            availability, reason = _availability(descriptor, access_context)
            catalog.append(replace(descriptor, availability=availability, availability_reason=reason))
        return tuple(catalog)

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._entries))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


action_registry: VersionedRegistry[WorkflowActionHandler, ActionDescriptor] = VersionedRegistry("action handler")
condition_registry: VersionedRegistry[WorkflowConditionHandler, ConditionDescriptor] = VersionedRegistry(
    "condition handler"
)
subject_registry: VersionedRegistry[WorkflowSubjectResolver, SubjectResolverDescriptor] = VersionedRegistry(
    "subject resolver"
)
assignee_registry: VersionedRegistry[WorkflowAssigneeProvider, AssigneeProviderDescriptor] = VersionedRegistry(
    "assignee provider"
)


def _replacement_allowed() -> bool:
    mode = os.environ.get("SARAISE_MODE", "development").lower()
    return bool(getattr(settings, "DEBUG", False)) and mode in {"development", "test"}


def _availability(descriptor: Any, access_context: Mapping[str, Any] | None) -> tuple[str, str]:
    if descriptor.owning_module == CORE_MODULE:
        return "available", ""
    if access_context is None:
        return "locked", "This capability requires an industry module entitlement."
    modules = access_context.get("modules", ())
    entitlements = access_context.get("entitlements", ())
    unavailable = access_context.get("unavailable_modules", ())
    if descriptor.owning_module in unavailable:
        return "unavailable", "The installed provider is temporarily unavailable."
    if descriptor.owning_module not in modules:
        return "setup_required", "Install and configure the contributing module to use this capability."
    if descriptor.required_entitlement not in entitlements:
        return "locked", "This capability requires an additional entitlement."
    return "available", ""


class _ActionBase:
    descriptor: ActionDescriptor

    @property
    def key(self) -> str:
        return self.descriptor.key

    @property
    def schema_version(self) -> str:
        return self.descriptor.schema_version

    def validate_config(self, config: Mapping[str, Any]) -> None:
        _validate(config, self.descriptor.configuration_schema, "config")

    def health(self) -> HealthCheckResult:
        return HealthCheckResult(
            False,
            "handler_readiness_probe_not_implemented",
            timezone.now(),
            {"code": "provider_unavailable"},
        )


_OBJECT_SCHEMA: JsonMapping = {"type": "object", "additionalProperties": True}


class InAppNotificationAction(_ActionBase):
    descriptor = ActionDescriptor(
        key="core.in_app_notification.v1",
        display_name="In-app notification",
        description="Persist a notification in the recipient's SARAISE inbox.",
        category="Notifications",
        owning_module=CORE_MODULE,
        required_permission="workflow_automation.instance:start",
        required_entitlement=CORE_ENTITLEMENT,
        quota_resource="workflow_automation.external_actions",
        # Tenant policy supplies the effective quota cost at runtime.
        quota_cost=Decimal(),
        configuration_schema={
            "type": "object",
            "properties": {"notification_type": {"enum": ["workflow", "approval", "info", "warning"]}},
            "additionalProperties": False,
        },
        input_schema={
            "type": "object",
            "required": ["recipient_id", "title", "message"],
            "properties": {
                "recipient_id": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1, "maxLength": 255},
                "message": {"type": "string", "minLength": 1, "maxLength": 4000},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "required": ["notification_id"],
            "properties": {"notification_id": {"type": "string", "format": "uuid"}},
            "additionalProperties": False,
        },
        idempotency_supported=True,
        outbound_network_required=False,
        icon_key="bell",
        lookup_descriptors=(LookupDescriptor("recipient_id", "core.users.v1", "Recipient"),),
    )

    def health(self) -> HealthCheckResult:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                ready = cursor.fetchone() == (1,)
        except Exception:
            ready = False
        return HealthCheckResult(
            ready,
            "ready" if ready else "notification_store_unavailable",
            timezone.now(),
            {"code": "ready" if ready else "provider_unavailable"},
        )

    def execute(self, invocation: WorkflowActionInvocation) -> OperationResult[JsonObject]:
        if invocation.cancellation_probe():
            return OperationResult.failed(code="EXECUTION_CANCELLED", message="Execution was cancelled")
        self.validate_config(invocation.config)
        _validate(invocation.input, self.descriptor.input_schema, "input")
        from src.core.notifications.models import Notification

        recipient = str(invocation.input["recipient_id"])
        try:
            recipient_uuid = uuid.UUID(recipient)
        except ValueError:
            recipient_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"saraise-user:{recipient}")
        existing = Notification.objects.filter(
            tenant_id=invocation.tenant_id,
            metadata__idempotency_key=invocation.idempotency_key,
        ).first()
        if existing is not None:
            return OperationResult.succeeded(
                {"notification_id": str(existing.id)},
                evidence={"notification_id": str(existing.id), "persisted": True, "replayed": True},
                provider="notifications",
            )
        notification = Notification.objects.create(
            tenant_id=invocation.tenant_id,
            user_id=recipient_uuid,
            type=str(invocation.config.get("notification_type", "workflow")),
            title=str(invocation.input["title"]),
            message=str(invocation.input["message"]),
            metadata={
                "workflow_instance_id": str(invocation.instance_id),
                "workflow_step_id": str(invocation.step_id),
                "correlation_id": invocation.correlation_id,
                "idempotency_key": invocation.idempotency_key,
            },
        )
        value: JsonObject = {"notification_id": str(notification.id)}
        return OperationResult.succeeded(
            value,
            evidence={"notification_id": str(notification.id), "persisted": True},
            provider="notifications",
        )


_EMAIL_ACTION_DESCRIPTION = (
    "Render an administrator-owned template and request delivery through " "Django's configured email backend."
)


class EmailNotificationAction(_ActionBase):
    descriptor = ActionDescriptor(
        key="core.email_notification.v1",
        display_name="Email notification",
        description=_EMAIL_ACTION_DESCRIPTION,
        category="Notifications",
        owning_module=CORE_MODULE,
        required_permission="workflow_automation.instance:start",
        required_entitlement=CORE_ENTITLEMENT,
        quota_resource="workflow_automation.external_actions",
        # Tenant policy supplies the effective quota cost at runtime.
        quota_cost=Decimal(),
        configuration_schema={
            "type": "object",
            "required": ["template_key"],
            "properties": {"template_key": {"type": "string", "pattern": "^[a-z0-9_.-]+$"}},
            "additionalProperties": False,
        },
        input_schema={
            "type": "object",
            "required": ["recipient_email", "template_context"],
            "properties": {
                "recipient_email": {"type": "string", "format": "email"},
                "template_context": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "number", "boolean", "null"]},
                },
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "required": ["accepted"],
            "properties": {"accepted": {"type": "boolean"}},
            "additionalProperties": False,
        },
        idempotency_supported=False,
        outbound_network_required=True,
        icon_key="mail",
        lookup_descriptors=(LookupDescriptor("recipient_email", "core.users.v1", "Recipient"),),
    )

    def health(self) -> HealthCheckResult:
        return HealthCheckResult(
            False,
            "durable_email_provider_adapter_required",
            timezone.now(),
            {"code": "provider_unavailable"},
        )

    def execute(self, invocation: WorkflowActionInvocation) -> OperationResult[JsonObject]:
        del invocation
        return OperationResult.unavailable(
            capability=self.key,
            message=(
                "Email delivery is disabled until a durable provider adapter supplies "
                "timeouts, bounded jittered retries, circuit breaking, idempotency, and reconciliation."
            ),
        )


def _read_path(source: Mapping[str, Any], path: str) -> JsonValue:
    value: Any = source
    for component in path.split("."):
        if not isinstance(value, Mapping) or component not in value:
            raise KeyError(path)
        value = value[component]
    return value


class ContextProjectionAction(_ActionBase):
    descriptor = ActionDescriptor(
        key="core.context_projection.v1",
        display_name="Project context",
        description="Copy explicitly selected context paths into step output.",
        category="Data",
        owning_module=CORE_MODULE,
        required_permission="workflow_automation.instance:start",
        required_entitlement=CORE_ENTITLEMENT,
        quota_resource="workflow_automation.executions",
        quota_cost=Decimal(),
        configuration_schema={
            "type": "object",
            "required": ["input_mapping"],
            "properties": {
                "input_mapping": {
                    "type": "object",
                    "additionalProperties": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+$"},
                }
            },
            "additionalProperties": False,
        },
        input_schema=_OBJECT_SCHEMA,
        output_schema=_OBJECT_SCHEMA,
        idempotency_supported=True,
        outbound_network_required=False,
        icon_key="brackets",
    )

    def health(self) -> HealthCheckResult:
        try:
            Draft202012Validator.check_schema(dict(self.descriptor.configuration_schema))
            ready = True
        except SchemaError:
            ready = False
        return HealthCheckResult(
            ready,
            "ready" if ready else "handler_schema_invalid",
            timezone.now(),
            {"code": "ready" if ready else "provider_unavailable"},
        )

    def execute(self, invocation: WorkflowActionInvocation) -> OperationResult[JsonObject]:
        self.validate_config(invocation.config)
        mapping = invocation.config["input_mapping"]
        assert isinstance(mapping, Mapping)
        try:
            output: JsonObject = {
                str(target): _read_path(invocation.input, str(path)) for target, path in mapping.items()
            }
        except KeyError as exc:
            return OperationResult.failed(
                code="CONTEXT_PATH_MISSING",
                message="A configured context path is unavailable.",
                detail={"path": exc.args[0]},
            )
        return OperationResult.succeeded(
            output,
            evidence={"projected_fields": len(output), "input_fingerprint": _fingerprint(invocation.input)},
        )


class TerminalCompletionAction(_ActionBase):
    descriptor = ActionDescriptor(
        key="core.terminal_completion.v1",
        display_name="Complete workflow",
        description="Emit an explicit, durable terminal-completion marker.",
        category="Control flow",
        owning_module=CORE_MODULE,
        required_permission="workflow_automation.instance:start",
        required_entitlement=CORE_ENTITLEMENT,
        quota_resource="workflow_automation.executions",
        quota_cost=Decimal(),
        configuration_schema={"type": "object", "properties": {}, "additionalProperties": False},
        input_schema=_OBJECT_SCHEMA,
        output_schema={
            "type": "object",
            "required": ["completed"],
            "properties": {"completed": {"const": True}},
            "additionalProperties": False,
        },
        idempotency_supported=True,
        outbound_network_required=False,
        icon_key="check-circle",
    )

    def health(self) -> HealthCheckResult:
        try:
            Draft202012Validator.check_schema(dict(self.descriptor.output_schema))
            ready = True
        except SchemaError:
            ready = False
        return HealthCheckResult(
            ready,
            "ready" if ready else "handler_schema_invalid",
            timezone.now(),
            {"code": "ready" if ready else "provider_unavailable"},
        )

    def execute(self, invocation: WorkflowActionInvocation) -> OperationResult[JsonObject]:
        self.validate_config(invocation.config)
        return OperationResult.succeeded(
            {"completed": True},
            evidence={
                "terminal_marker": invocation.idempotency_key,
                "instance_id": str(invocation.instance_id),
                "step_id": str(invocation.step_id),
            },
        )


class _ConditionBase:
    descriptor: ConditionDescriptor

    @property
    def key(self) -> str:
        return self.descriptor.key

    @property
    def schema_version(self) -> str:
        return self.descriptor.schema_version

    def validate(self, condition: Mapping[str, Any]) -> None:
        _validate(condition, self.descriptor.condition_schema, "condition")


class EqualsCondition(_ConditionBase):
    descriptor = ConditionDescriptor(
        key="core.equals.v1",
        display_name="Equals",
        description="Compare two already-resolved JSON values for equality.",
        owning_module=CORE_MODULE,
        required_entitlement=CORE_ENTITLEMENT,
        condition_schema={
            "type": "object",
            "required": ["handler", "left_path", "right_value"],
            "properties": {
                "handler": {"const": "core.equals.v1"},
                "left_path": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+$"},
                "right_value": {},
            },
            "additionalProperties": False,
        },
        context_schema={
            "type": "object",
            "required": ["left", "right"],
            "properties": {"left": {}, "right": {}},
            "additionalProperties": False,
        },
    )

    def evaluate(self, context: Mapping[str, Any]) -> bool:
        _validate(context, self.descriptor.context_schema, "context")
        return context["left"] == context["right"]


class TruthyCondition(_ConditionBase):
    descriptor = ConditionDescriptor(
        key="core.truthy.v1",
        display_name="Is true",
        description="Require an already-resolved context value to be the JSON boolean true.",
        owning_module=CORE_MODULE,
        required_entitlement=CORE_ENTITLEMENT,
        condition_schema={
            "type": "object",
            "required": ["handler", "value_path"],
            "properties": {
                "handler": {"const": "core.truthy.v1"},
                "value_path": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+$"},
            },
            "additionalProperties": False,
        },
        context_schema={
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "boolean"}},
            "additionalProperties": False,
        },
    )

    def evaluate(self, context: Mapping[str, Any]) -> bool:
        _validate(context, self.descriptor.context_schema, "context")
        return context["value"] is True


_ASSIGNEE_RESULT_SCHEMA: JsonMapping = {
    "type": "object",
    "required": ["assignment_key", "display_name", "assignment_kind"],
    "properties": {
        "assignment_key": {"type": "string"},
        "display_name": {"type": "string"},
        "assignment_kind": {"enum": ["user", "role", "custom"]},
        "secondary_text": {"type": "string"},
    },
    "additionalProperties": False,
}


class CoreUserAssigneeProvider:
    descriptor = AssigneeProviderDescriptor(
        key="core.users.v1",
        display_name="Users",
        owning_module=CORE_MODULE,
        assignment_kind="user",
        required_permission="workflow_automation.task:read",
        required_entitlement=CORE_ENTITLEMENT,
        result_schema=_ASSIGNEE_RESULT_SCHEMA,
    )

    @property
    def key(self) -> str:
        return self.descriptor.key

    def search(self, invocation: AssigneeSearchInvocation) -> OperationResult[list[JsonObject]]:
        User = get_user_model()
        queryset = User.objects.filter(profile__tenant_id=str(invocation.tenant_id), is_active=True).order_by(
            "first_name", "last_name", "username"
        )
        if invocation.query.strip():
            from django.db.models import Q

            query = invocation.query.strip()
            queryset = queryset.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(username__icontains=query)
                | Q(email__icontains=query)
            )
        rows: list[JsonObject] = []
        for user in queryset[: invocation.limit]:
            display_name = user.get_full_name().strip() or user.get_username()
            rows.append(
                {
                    "assignment_key": f"user:{user.pk}",
                    "display_name": display_name,
                    "assignment_kind": "user",
                    "secondary_text": user.email or user.get_username(),
                }
            )
        return OperationResult.succeeded(rows, evidence={"matched": len(rows), "tenant_filtered": True})


class CoreRoleAssigneeProvider:
    descriptor = AssigneeProviderDescriptor(
        key="core.roles.v1",
        display_name="Roles",
        owning_module=CORE_MODULE,
        assignment_kind="role",
        required_permission="workflow_automation.task:read",
        required_entitlement=CORE_ENTITLEMENT,
        result_schema=_ASSIGNEE_RESULT_SCHEMA,
    )

    @property
    def key(self) -> str:
        return self.descriptor.key

    def search(self, invocation: AssigneeSearchInvocation) -> OperationResult[list[JsonObject]]:
        from src.modules.security_access_control.models import Role

        queryset = Role.objects.filter(tenant_id=invocation.tenant_id, is_active=True).order_by("name", "code")
        if invocation.query.strip():
            from django.db.models import Q

            query = invocation.query.strip()
            queryset = queryset.filter(Q(name__icontains=query) | Q(code__icontains=query))
        rows: list[JsonObject] = [
            {
                "assignment_key": f"role:{role.id}",
                "display_name": role.name,
                "assignment_kind": "role",
                "secondary_text": role.code,
            }
            for role in queryset[: invocation.limit]
        ]
        return OperationResult.succeeded(rows, evidence={"matched": len(rows), "tenant_filtered": True})


class EntityReferenceSubjectResolver:
    """Safe fallback that preserves identity without fabricating a title."""

    descriptor = SubjectResolverDescriptor(
        key="core.entity_reference.v1",
        display_name="Entity reference",
        owning_module=CORE_MODULE,
        entity_types=("*",),
        required_entitlement=CORE_ENTITLEMENT,
    )

    @property
    def key(self) -> str:
        return self.descriptor.key

    def resolve(self, invocation: SubjectResolutionInvocation) -> OperationResult[JsonObject]:
        value: JsonObject = {
            "entity_type": invocation.entity_type,
            "entity_id": str(invocation.entity_id),
            "display_name": f"{invocation.entity_type} {invocation.entity_id}",
            "resolved": False,
        }
        return OperationResult.succeeded(
            value,
            evidence={"identity_preserved": True, "resolver": self.key},
        )


def _fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(value), sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def register_builtin_handlers() -> None:
    """Install the complete OSS baseline idempotently for autoreload."""
    registrations: Sequence[tuple[VersionedRegistry[Any, Any], Any]] = (
        (action_registry, InAppNotificationAction()),
        (action_registry, EmailNotificationAction()),
        (action_registry, ContextProjectionAction()),
        (action_registry, TerminalCompletionAction()),
        (condition_registry, EqualsCondition()),
        (condition_registry, TruthyCondition()),
        (subject_registry, EntityReferenceSubjectResolver()),
        (assignee_registry, CoreUserAssigneeProvider()),
        (assignee_registry, CoreRoleAssigneeProvider()),
    )
    for registry, handler in registrations:
        if handler.key not in registry.keys():
            registry.register(handler)


def execute_registered_action(invocation: WorkflowActionInvocation) -> OperationResult[JsonObject]:
    try:
        handler = action_registry.get(invocation.handler_key)
    except WorkflowExtensionNotFound:
        return OperationResult.unavailable(
            capability=invocation.handler_key,
            message="The workflow action handler is not installed.",
        )
    descriptor = handler.descriptor
    if invocation.descriptor_version != descriptor.contract_version:
        return OperationResult.unavailable(
            capability=invocation.handler_key,
            message="The installed handler version does not match the published workflow.",
        )
    if invocation.descriptor_fingerprint != descriptor.contract_fingerprint:
        return OperationResult.unavailable(
            capability=invocation.handler_key,
            message="The installed handler contract does not match the published workflow.",
        )
    try:
        handler.validate_config(invocation.config)
        _validate(invocation.input, descriptor.input_schema, "input")
        result = handler.execute(invocation)
    except WorkflowExtensionContractError as exc:
        return OperationResult.failed(code="ACTION_CONTRACT_INVALID", message=str(exc))
    except Exception:
        return OperationResult.failed(code="ACTION_HANDLER_EXCEPTION", message="The action handler failed unexpectedly")
    if not isinstance(result, OperationResult):
        return OperationResult.failed(
            code="ACTION_RESULT_INVALID", message="The action handler returned an invalid result"
        )
    if result.status == "succeeded" and result.value is not None:
        try:
            _validate(result.value, descriptor.output_schema, "output")
        except WorkflowExtensionContractError as exc:
            return OperationResult.failed(code="ACTION_OUTPUT_INVALID", message=str(exc))
    return result


register_builtin_handlers()


__all__ = [
    "ActionDescriptor",
    "AssigneeProviderDescriptor",
    "AssigneeSearchInvocation",
    "ConditionDescriptor",
    "DuplicateWorkflowExtension",
    "JsonMapping",
    "JsonObject",
    "JsonValue",
    "LookupDescriptor",
    "SubjectResolutionInvocation",
    "SubjectResolverDescriptor",
    "VersionedRegistry",
    "WORKFLOW_SPI_VERSION",
    "WorkflowActionHandler",
    "WorkflowActionInvocation",
    "WorkflowAssigneeProvider",
    "WorkflowConditionEvaluation",
    "WorkflowConditionHandler",
    "WorkflowExtensionContractError",
    "WorkflowExtensionError",
    "WorkflowExtensionNotFound",
    "WorkflowExtensionReplacementForbidden",
    "WorkflowSubjectResolver",
    "action_registry",
    "assignee_registry",
    "condition_registry",
    "execute_registered_action",
    "register_builtin_handlers",
    "subject_registry",
]
