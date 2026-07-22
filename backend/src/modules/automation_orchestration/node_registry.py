"""Versioned, ORM-free extension contract for orchestration node executors.

The registry deliberately contains no model imports.  Industry modules can
register an executor from ``AppConfig.ready`` without gaining a write path to
orchestration state; the engine remains the sole owner of validation,
transitions, retries and audit evidence.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, TypeAlias, runtime_checkable

from jsonschema import Draft202012Validator, SchemaError, ValidationError

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONMapping: TypeAlias = Mapping[str, JSONValue]

NODE_SPI_VERSION = "1.0"
CORE_CAPABILITY = "automation_orchestration.core"


class _FrozenJSONDict(dict[str, Any]):
    """JSON-serializable mapping that rejects post-construction mutation."""

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise TypeError("node contract mappings are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable


class RegistryError(RuntimeError):
    """Base error for the node extension registry."""


class DuplicateNodeRegistration(RegistryError):
    """Raised when import order would otherwise silently replace a node."""


class NodeNotRegistered(RegistryError):
    """Raised when a definition references a handler which is not installed."""


class NodeReplacementForbidden(RegistryError):
    """Raised because in-place replacement is forbidden in every environment."""


class NodeContractError(ValueError):
    """Raised when a descriptor, schema or execution context is malformed."""


class RetrySafety(str, Enum):
    """Executor promise governing automatic retry after an ambiguous failure."""

    IDEMPOTENT = "idempotent"
    RECONCILABLE = "reconcilable"
    UNSAFE = "unsafe"

    def __str__(self) -> str:
        return self.value


class CommitState(str, Enum):
    """Whether a failed executor may already have committed its side effect."""

    NOT_STARTED = "not_started"
    COMMITTED = "committed"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


class NodeResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"

    def __str__(self) -> str:
        return self.value


CancellationProbe = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class NodeDescriptor:
    """Immutable catalog and ABI descriptor published by a module."""

    key: str
    display_name: str
    category: str
    description: str
    configuration_schema: JSONMapping
    input_schema: JSONMapping
    output_schema: JSONMapping
    icon_key: str
    capability: str
    source_module: str
    spi_version: str = NODE_SPI_VERSION
    module_version: str = "1.0.0"
    executor_version: str = "1"
    retry_safety: RetrySafety = RetrySafety.IDEMPOTENT
    quota_resource: str | None = None
    quota_cost: Decimal = Decimal("0")
    availability: str = "available"
    availability_reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.retry_safety, RetrySafety):
            try:
                object.__setattr__(self, "retry_safety", RetrySafety(self.retry_safety))
            except (TypeError, ValueError) as exc:
                raise NodeContractError("retry_safety is invalid") from exc
        for name in (
            "key",
            "display_name",
            "category",
            "description",
            "icon_key",
            "capability",
            "source_module",
            "spi_version",
            "module_version",
            "executor_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise NodeContractError(f"{name} must be a non-empty string")
        if self.key != self.key.strip() or len(self.key) > 150:
            raise NodeContractError("key must be canonical and at most 150 characters")
        if self.spi_version != NODE_SPI_VERSION:
            raise NodeContractError(f"Unsupported node SPI {self.spi_version!r}; expected {NODE_SPI_VERSION!r}")
        if self.quota_cost < 0:
            raise NodeContractError("quota_cost cannot be negative")
        if self.availability not in {"available", "locked", "setup_required", "unavailable"}:
            raise NodeContractError("availability is invalid")
        for name in ("configuration_schema", "input_schema", "output_schema"):
            schema = _plain_mapping(getattr(self, name), name)
            _validate_schema_contract(schema, name)
            object.__setattr__(self, name, _FrozenJSONDict(schema))

    @property
    def contract_version(self) -> str:
        """Stable publication pin persisted into graph validation evidence."""

        return f"{self.spi_version}:{self.module_version}:{self.executor_version}"

    @property
    def contract_fingerprint(self) -> str:
        payload = {
            "key": self.key,
            "version": self.contract_version,
            "configuration_schema": dict(self.configuration_schema),
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "retry_safety": self.retry_safety.value,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class NodeExecutionContext:
    """Durable input passed to an executor for exactly one delivery.

    ``operation_token`` is stable for a task run across retries.  The separate
    ``delivery_token`` identifies the physical AsyncJob/attempt and may change.
    External side effects must use the operation token.
    """

    tenant_id: uuid.UUID
    run_id: uuid.UUID
    task_run_id: uuid.UUID
    attempt_id: uuid.UUID
    actor_id: uuid.UUID
    correlation_id: str
    input: JSONMapping
    validated_config: JSONMapping
    cancellation_probe: CancellationProbe
    operation_token: str
    delivery_token: str
    handler_key: str
    descriptor_version: str
    request_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("tenant_id", "run_id", "task_run_id", "attempt_id", "actor_id"):
            value = getattr(self, name)
            if not isinstance(value, uuid.UUID):
                raise NodeContractError(f"{name} must be a UUID")
        for name in (
            "correlation_id",
            "operation_token",
            "delivery_token",
            "handler_key",
            "descriptor_version",
            "request_fingerprint",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise NodeContractError(f"{name} must be a non-empty string")
        if not callable(self.cancellation_probe):
            raise NodeContractError("cancellation_probe must be callable")
        object.__setattr__(self, "input", _FrozenJSONDict(_plain_mapping(self.input, "input")))
        object.__setattr__(
            self,
            "validated_config",
            _FrozenJSONDict(_plain_mapping(self.validated_config, "validated_config")),
        )

    @property
    def idempotency_token(self) -> str:
        """Compatibility alias with the original SPI name."""

        return self.operation_token


@dataclass(frozen=True, slots=True)
class NodeExecutionResult:
    """Typed executor outcome; booleans and arbitrary dictionaries are invalid."""

    status: NodeResultStatus
    output: JSONMapping = field(default_factory=dict)
    evidence: JSONMapping = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    transient: bool = False
    retry_after_seconds: int | None = None
    commit_state: CommitState = CommitState.NOT_STARTED
    manual_retry_safe: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.status, NodeResultStatus):
            try:
                object.__setattr__(self, "status", NodeResultStatus(self.status))
            except (TypeError, ValueError) as exc:
                raise NodeContractError("status must be succeeded, failed or unavailable") from exc
        if not isinstance(self.commit_state, CommitState):
            try:
                object.__setattr__(self, "commit_state", CommitState(self.commit_state))
            except (TypeError, ValueError) as exc:
                raise NodeContractError("commit_state is invalid") from exc
        if self.status == NodeResultStatus.SUCCEEDED and (self.error_code or self.error_message):
            raise NodeContractError("successful results cannot contain error fields")
        if self.status != NodeResultStatus.SUCCEEDED and not self.error_code:
            raise NodeContractError("failed and unavailable results require a stable error_code")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise NodeContractError("retry_after_seconds cannot be negative")
        object.__setattr__(self, "output", _FrozenJSONDict(_plain_mapping(self.output, "output")))
        object.__setattr__(self, "evidence", _FrozenJSONDict(_plain_mapping(self.evidence, "evidence")))

    @classmethod
    def success(
        cls,
        output: JSONMapping | None = None,
        *,
        evidence: JSONMapping | None = None,
    ) -> "NodeExecutionResult":
        return cls(NodeResultStatus.SUCCEEDED, output or {}, evidence or {})

    @classmethod
    def failure(
        cls,
        error_code: str,
        error_message: str,
        *,
        transient: bool = False,
        retry_after_seconds: int | None = None,
        commit_state: CommitState = CommitState.NOT_STARTED,
        manual_retry_safe: bool = True,
        evidence: JSONMapping | None = None,
    ) -> "NodeExecutionResult":
        return cls(
            NodeResultStatus.FAILED,
            {},
            evidence or {},
            error_code,
            error_message,
            transient,
            retry_after_seconds,
            commit_state,
            manual_retry_safe,
        )

    @classmethod
    def unavailable(
        cls,
        error_code: str,
        error_message: str,
        *,
        evidence: JSONMapping | None = None,
    ) -> "NodeExecutionResult":
        return cls(
            NodeResultStatus.UNAVAILABLE,
            {},
            evidence or {},
            error_code,
            error_message,
            False,
            None,
            CommitState.NOT_STARTED,
            False,
        )


@runtime_checkable
class NodeExecutor(Protocol):
    def __call__(self, context: NodeExecutionContext) -> NodeExecutionResult: ...


@runtime_checkable
class NodeAccessContext(Protocol):
    """Minimal access projection understood by the ORM-free catalog."""

    def allows_node(self, descriptor: NodeDescriptor) -> bool: ...


_registry: dict[str, tuple[NodeDescriptor, NodeExecutor]] = {}
_registry_lock = threading.RLock()


def register_node(
    descriptor: NodeDescriptor,
    executor: NodeExecutor,
    replace: bool = False,
) -> None:
    """Register one descriptor/executor pair without import-order overrides."""

    if not isinstance(descriptor, NodeDescriptor):
        raise TypeError("descriptor must be a NodeDescriptor")
    if not callable(executor):
        raise TypeError("executor must be callable")
    with _registry_lock:
        if descriptor.key in _registry:
            if not replace:
                raise DuplicateNodeRegistration(f"Node {descriptor.key!r} is already registered")
            raise NodeReplacementForbidden("Node replacement is forbidden; use an isolated registry instance")
        _registry[descriptor.key] = (descriptor, executor)


def unregister_node(handler_key: str) -> tuple[NodeDescriptor, NodeExecutor] | None:
    """Remove a node registration for isolated tests and development reloads."""

    with _registry_lock:
        return _registry.pop(handler_key, None)


def get_node_descriptor(handler_key: str) -> NodeDescriptor:
    """Resolve a handler contract or fail explicitly."""

    with _registry_lock:
        try:
            return _registry[handler_key][0]
        except KeyError as exc:
            raise NodeNotRegistered(f"No node handler is registered for {handler_key!r}") from exc


def list_node_descriptors(access_context: NodeAccessContext | Mapping[str, Any] | None) -> tuple[NodeDescriptor, ...]:
    """Return the deterministic catalog visible to the supplied access projection.

    Core OSS nodes are always discoverable.  Extension discovery fails closed
    unless the caller supplies an affirmative capability/access decision.
    """

    with _registry_lock:
        descriptors = tuple(pair[0] for pair in _registry.values())
    return tuple(sorted((item for item in descriptors if _is_visible(item, access_context)), key=lambda d: d.key))


def list_node_catalog(
    access_context: NodeAccessContext | Mapping[str, Any] | None,
) -> tuple[NodeDescriptor, ...]:
    """Return installed capabilities including safe locked/setup discovery.

    Catalog visibility is not execution authorization.  The worker always
    re-evaluates access, so a discoverable paid node cannot be invoked merely
    because it appears in this response.
    """

    with _registry_lock:
        descriptors = tuple(pair[0] for pair in _registry.values())
    entries: list[NodeDescriptor] = []
    for descriptor in descriptors:
        availability, reason = _catalog_availability(descriptor, access_context)
        entries.append(replace(descriptor, availability=availability, availability_reason=reason))
    return tuple(sorted(entries, key=lambda item: item.key))


def execute_registered_node(context: NodeExecutionContext) -> NodeExecutionResult:
    """Validate and invoke an executor, mapping contract failures explicitly."""

    if not isinstance(context, NodeExecutionContext):
        raise TypeError("context must be a NodeExecutionContext")
    with _registry_lock:
        pair = _registry.get(context.handler_key)
    if pair is None:
        return NodeExecutionResult.unavailable("NODE_HANDLER_MISSING", "The node handler is not installed")
    descriptor, executor = pair
    if context.descriptor_version != descriptor.contract_version:
        return NodeExecutionResult.unavailable(
            "NODE_VERSION_MISMATCH",
            "The installed node executor does not match the published graph version",
            evidence={"expected": context.descriptor_version, "installed": descriptor.contract_version},
        )
    if context.cancellation_probe():
        return NodeExecutionResult.failure(
            "EXECUTION_CANCELLED",
            "Execution was cancelled before the node started",
            manual_retry_safe=True,
        )
    try:
        validate_json_value(dict(context.validated_config), descriptor.configuration_schema, "config")
        validate_json_value(dict(context.input), descriptor.input_schema, "input")
    except NodeContractError as exc:
        return NodeExecutionResult.failure("NODE_INPUT_INVALID", str(exc), manual_retry_safe=True)
    try:
        result = executor(context)
    except Exception:
        return NodeExecutionResult.failure(
            "NODE_EXECUTOR_EXCEPTION",
            "The node executor failed unexpectedly",
            transient=True,
            commit_state=CommitState.UNKNOWN,
            manual_retry_safe=descriptor.retry_safety != RetrySafety.UNSAFE,
        )
    if not isinstance(result, NodeExecutionResult):
        return NodeExecutionResult.failure(
            "INVALID_EXECUTOR_RESULT",
            "The node executor returned an invalid result contract",
            manual_retry_safe=True,
        )
    if result.status == NodeResultStatus.SUCCEEDED:
        try:
            validate_json_value(dict(result.output), descriptor.output_schema, "output")
        except NodeContractError as exc:
            return NodeExecutionResult.failure("NODE_OUTPUT_INVALID", str(exc), manual_retry_safe=True)
    return result


def validate_json_value(value: Any, schema: Mapping[str, Any], label: str) -> None:
    """Validate JSON-compatible data against the supported schema subset."""

    _validate_schema_contract(dict(schema), f"{label}_schema")
    try:
        Draft202012Validator(dict(schema)).validate(value)
    except ValidationError as exc:
        pointer = "/" + "/".join(str(part) for part in exc.absolute_path) if exc.absolute_path else "/"
        raise NodeContractError(f"{label}{pointer}: {exc.message}") from exc


def validate_json_schema(schema: Mapping[str, Any], label: str) -> None:
    """Validate a schema contract without requiring a sample instance."""

    _validate_schema_contract(_plain_mapping(schema, label), label)


def request_fingerprint(*, handler_key: str, config: Mapping[str, Any], input: Mapping[str, Any]) -> str:
    """Hash the semantic request to detect idempotency-key reuse conflicts."""

    payload = {"handler_key": handler_key, "config": dict(config), "input": dict(input)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _plain_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NodeContractError(f"{field_name} must be a mapping")
    result = dict(value)
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise NodeContractError(f"{field_name} must contain JSON-compatible values") from exc
    return result


def _validate_schema_contract(schema: dict[str, Any], field_name: str) -> None:
    if not schema:
        raise NodeContractError(f"{field_name} must declare an explicit JSON schema")
    if any(key in json.dumps(schema) for key in ('"$ref"', '"$dynamicRef"', '"$recursiveRef"')):
        raise NodeContractError(f"{field_name} cannot contain remote or recursive references")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise NodeContractError(f"{field_name} is not a valid JSON schema: {exc.message}") from exc


def _is_visible(
    descriptor: NodeDescriptor,
    access_context: NodeAccessContext | Mapping[str, Any] | None,
) -> bool:
    if descriptor.source_module == "automation_orchestration" and descriptor.capability == CORE_CAPABILITY:
        return True
    if access_context is None:
        return False
    if hasattr(access_context, "allowed"):
        return bool(getattr(access_context, "allowed"))
    if isinstance(access_context, NodeAccessContext):
        return bool(access_context.allows_node(descriptor))
    if isinstance(access_context, Mapping):
        decision = access_context.get("allows_node")
        if callable(decision):
            return bool(decision(descriptor))
        capabilities = access_context.get("capabilities", ())
        modules = access_context.get("modules", ())
        return descriptor.capability in capabilities and descriptor.source_module in modules
    return False


def _catalog_availability(
    descriptor: NodeDescriptor,
    access_context: NodeAccessContext | Mapping[str, Any] | None,
) -> tuple[str, str]:
    if descriptor.source_module == "automation_orchestration" and descriptor.capability == CORE_CAPABILITY:
        return "available", ""
    if _is_visible(descriptor, access_context):
        return "available", ""
    if isinstance(access_context, Mapping):
        unavailable = access_context.get("unavailable_modules", ())
        installed = access_context.get("modules", ())
        if descriptor.source_module in unavailable:
            return "unavailable", "The installed provider is temporarily unavailable."
        if descriptor.source_module not in installed:
            return "setup_required", "Install and configure the contributing module to use this node."
    return "locked", "This node requires additional access or entitlement."


def _passthrough_executor(context: NodeExecutionContext) -> NodeExecutionResult:
    """Real OSS utility node: copy its validated input to its output."""

    return NodeExecutionResult.success(dict(context.input), evidence={"operation": "passthrough"})


_OBJECT_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": True}


def register_core_nodes() -> None:
    """Install the free baseline catalog idempotently for Django autoreload."""

    descriptor = NodeDescriptor(
        key="core.passthrough",
        display_name="Pass through",
        category="Core",
        description="Copies validated node input to output without external side effects.",
        configuration_schema={"type": "object", "properties": {}, "additionalProperties": False},
        input_schema=_OBJECT_SCHEMA,
        output_schema=_OBJECT_SCHEMA,
        icon_key="arrow-right",
        capability=CORE_CAPABILITY,
        source_module="automation_orchestration",
        retry_safety=RetrySafety.IDEMPOTENT,
    )
    with _registry_lock:
        if descriptor.key not in _registry:
            _registry[descriptor.key] = (descriptor, _passthrough_executor)


register_core_nodes()


__all__ = [
    "CommitState",
    "DuplicateNodeRegistration",
    "NODE_SPI_VERSION",
    "NodeAccessContext",
    "NodeContractError",
    "NodeDescriptor",
    "NodeExecutionContext",
    "NodeExecutionResult",
    "NodeExecutor",
    "NodeNotRegistered",
    "NodeReplacementForbidden",
    "NodeResultStatus",
    "RetrySafety",
    "execute_registered_node",
    "get_node_descriptor",
    "list_node_descriptors",
    "list_node_catalog",
    "register_core_nodes",
    "register_node",
    "request_fingerprint",
    "unregister_node",
    "validate_json_value",
    "validate_json_schema",
]
