"""Stable, ORM-free security extension contract for paid modules.

Industry modules register declarative permission and resource metadata through
this module.  They never import or mutate the security module's ORM models.
The registry is deliberately process-local discovery: durable catalog changes
remain the responsibility of :class:`PermissionCatalogPort` during governed
module installation and upgrade transactions.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Mapping, Protocol, Sequence, TypeVar, runtime_checkable
from uuid import UUID

from django.db.models import Model, Q, QuerySet

EXTENSION_SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_MAJOR = 1
ALLOWED_PREDICATE_NODES = frozenset({"and", "or", "not", "eq", "in", "is_null", "owner", "tenant"})
FIELD_PREDICATE_NODES = frozenset({"eq", "in", "is_null"})

_MANIFEST_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
_FIELD = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$")
_SCHEMA_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ExtensionContractError(ValueError):
    """Base error for invalid or incompatible extension metadata."""


class ExtensionCollisionError(ExtensionContractError):
    """Raised when a namespace, permission, or resource has another owner."""


class PermissionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResourceFieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"
    ENUM = "enum"
    RELATION = "relation"


def _required(value: object, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or value != value.strip() or not pattern.fullmatch(value):
        raise ExtensionContractError(f"{name} has an invalid format")
    return value


def _version_tuple(value: str) -> tuple[int, int, int, str]:
    match = _VERSION.fullmatch(value)
    if match is None:
        raise ExtensionContractError("owner_version must use semantic versioning")
    major, minor, patch, prerelease = match.groups()
    # A final release sorts after its prereleases.
    release_rank = "\uffff" if prerelease is None else prerelease
    return int(major), int(minor), int(patch), release_rank


@dataclass(frozen=True, slots=True)
class PermissionDescriptor:
    """One immutable permission-catalog contribution."""

    module: str
    resource: str
    action: str
    name: str
    description: str = ""
    risk_level: PermissionRisk = PermissionRisk.MEDIUM

    def __post_init__(self) -> None:
        object.__setattr__(self, "module", _required(self.module, "permission module", _SLUG))
        object.__setattr__(self, "resource", _required(self.resource, "permission resource", _SLUG))
        object.__setattr__(self, "action", _required(self.action, "permission action", _SLUG))
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name.strip()) > 255:
            raise ExtensionContractError("permission name must contain 1 to 255 characters")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.description, str) or len(self.description) > 2_000:
            raise ExtensionContractError("permission description must be at most 2000 characters")
        try:
            object.__setattr__(self, "risk_level", PermissionRisk(self.risk_level))
        except ValueError as exc:
            raise ExtensionContractError("permission risk_level is unsupported") from exc

    @property
    def code(self) -> str:
        return f"{self.module}.{self.resource}:{self.action}"


@dataclass(frozen=True, slots=True)
class ResourceFieldDescriptor:
    """A policy-safe field exposed by an owning resource module."""

    name: str
    data_type: ResourceFieldType
    nullable: bool = False
    allowed_predicates: tuple[str, ...] = ("eq", "in", "is_null")

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required(self.name, "field name", _FIELD))
        try:
            object.__setattr__(self, "data_type", ResourceFieldType(self.data_type))
        except ValueError as exc:
            raise ExtensionContractError("field data_type is unsupported") from exc
        if not isinstance(self.nullable, bool):
            raise ExtensionContractError("field nullable must be boolean")
        predicates = tuple(self.allowed_predicates)
        if not predicates or len(set(predicates)) != len(predicates):
            raise ExtensionContractError("field predicates must be non-empty and unique")
        if not set(predicates).issubset(FIELD_PREDICATE_NODES):
            raise ExtensionContractError("field predicates contain an unsafe operator")
        if not self.nullable and "is_null" in predicates:
            predicates = tuple(item for item in predicates if item != "is_null")
        if not predicates:
            raise ExtensionContractError("a non-nullable field must expose at least one usable predicate")
        object.__setattr__(self, "allowed_predicates", predicates)


@dataclass(frozen=True, slots=True)
class PredicateSchemaDescriptor:
    """Versioned complexity limits for the foundation safe-predicate DSL."""

    schema_version: str = EXTENSION_SCHEMA_VERSION
    allowed_nodes: tuple[str, ...] = tuple(sorted(ALLOWED_PREDICATE_NODES))
    max_depth: int | None = None
    max_nodes: int | None = None
    max_in_values: int | None = None

    def __post_init__(self) -> None:
        match = _SCHEMA_VERSION.fullmatch(self.schema_version) if isinstance(self.schema_version, str) else None
        if match is None or int(match.group(1)) != SUPPORTED_SCHEMA_MAJOR:
            raise ExtensionContractError("predicate schema_version is incompatible")
        nodes = tuple(self.allowed_nodes)
        if not nodes or len(nodes) != len(set(nodes)) or not set(nodes).issubset(ALLOWED_PREDICATE_NODES):
            raise ExtensionContractError("predicate schema contains unsupported nodes")
        from .services import default_security_configuration

        limits = default_security_configuration()["limits"]
        if not isinstance(limits, Mapping):
            raise ExtensionContractError("predicate configuration limits are unavailable")
        configured = {
            "max_depth": int(limits["predicate_max_depth"]),
            "max_nodes": int(limits["predicate_max_nodes"]),
            "max_in_values": int(limits["predicate_max_in_values"]),
        }
        hard_limits = {
            "max_depth": int(limits["predicate_hard_max_depth"]),
            "max_nodes": int(limits["predicate_hard_max_nodes"]),
            "max_in_values": int(limits["predicate_hard_max_in_values"]),
        }
        for name, supplied in (
            ("max_depth", self.max_depth),
            ("max_nodes", self.max_nodes),
            ("max_in_values", self.max_in_values),
        ):
            value = configured[name] if supplied is None else supplied
            maximum = hard_limits[name]
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ExtensionContractError(f"{name} must be between 1 and {maximum}")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "allowed_nodes", nodes)


@dataclass(frozen=True, slots=True)
class ResourceSecurityDescriptor:
    """Field and subject metadata available to field/row policy builders."""

    module: str
    resource: str
    fields: tuple[ResourceFieldDescriptor, ...]
    trusted_subject_attributes: tuple[str, ...] = ()
    descriptor_version: str = EXTENSION_SCHEMA_VERSION
    predicate_schema_version: str = EXTENSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "module", _required(self.module, "resource module", _SLUG))
        object.__setattr__(self, "resource", _required(self.resource, "resource name", _SLUG))
        if not _SCHEMA_VERSION.fullmatch(self.descriptor_version):
            raise ExtensionContractError("descriptor_version must use major.minor versioning")
        predicate_match = _SCHEMA_VERSION.fullmatch(self.predicate_schema_version)
        if predicate_match is None or int(predicate_match.group(1)) != SUPPORTED_SCHEMA_MAJOR:
            raise ExtensionContractError("resource predicate_schema_version is incompatible")
        fields = tuple(self.fields)
        if not fields or any(not isinstance(item, ResourceFieldDescriptor) for item in fields):
            raise ExtensionContractError("a resource must declare typed fields")
        if len({item.name for item in fields}) != len(fields):
            raise ExtensionContractError("resource field names must be unique")
        attributes = tuple(self.trusted_subject_attributes)
        if len(attributes) != len(set(attributes)):
            raise ExtensionContractError("trusted subject attributes must be unique")
        for attribute in attributes:
            _required(attribute, "trusted subject attribute", _FIELD)
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "trusted_subject_attributes", attributes)

    @property
    def key(self) -> str:
        return f"{self.module}.{self.resource}"


@dataclass(frozen=True, slots=True)
class SecurityExtensionDescriptor:
    """Atomic contribution owned by one signed module manifest."""

    owner_manifest: str
    owner_version: str
    permission_namespace: str
    permissions: tuple[PermissionDescriptor, ...]
    resources: tuple[ResourceSecurityDescriptor, ...]
    predicate_schema: PredicateSchemaDescriptor = field(default_factory=PredicateSchemaDescriptor)
    schema_version: str = EXTENSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_manifest", _required(self.owner_manifest, "owner_manifest", _MANIFEST_NAME))
        _version_tuple(self.owner_version)
        namespace = _required(self.permission_namespace, "permission_namespace", _SLUG)
        object.__setattr__(self, "permission_namespace", namespace)
        schema_match = _SCHEMA_VERSION.fullmatch(self.schema_version) if isinstance(self.schema_version, str) else None
        if schema_match is None or int(schema_match.group(1)) != SUPPORTED_SCHEMA_MAJOR:
            raise ExtensionContractError("extension schema_version is incompatible")
        permissions = tuple(self.permissions)
        resources = tuple(self.resources)
        if any(not isinstance(item, PermissionDescriptor) for item in permissions):
            raise ExtensionContractError("permissions must contain PermissionDescriptor values")
        if any(item.module != namespace for item in permissions):
            raise ExtensionContractError("every permission must belong to the owned namespace")
        if len({item.code for item in permissions}) != len(permissions):
            raise ExtensionContractError("permission codes must be unique")
        if any(not isinstance(item, ResourceSecurityDescriptor) for item in resources):
            raise ExtensionContractError("resources must contain ResourceSecurityDescriptor values")
        if any(item.module != namespace for item in resources):
            raise ExtensionContractError("every resource must belong to the owned namespace")
        if len({item.key for item in resources}) != len(resources):
            raise ExtensionContractError("resource keys must be unique")
        if any(item.predicate_schema_version != self.predicate_schema.schema_version for item in resources):
            raise ExtensionContractError("resource and predicate schema versions must match")
        object.__setattr__(self, "permissions", permissions)
        object.__setattr__(self, "resources", resources)

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SecurityExtensionRegistry:
    """Thread-safe discovery registry with strict ownership and upgrades."""

    def __init__(self) -> None:
        self._by_owner: dict[str, SecurityExtensionDescriptor] = {}
        self._namespace_owners: dict[str, str] = {}
        self._permissions: dict[str, tuple[str, PermissionDescriptor]] = {}
        self._resources: dict[str, tuple[str, ResourceSecurityDescriptor]] = {}
        self._lock = threading.RLock()

    def register(self, descriptor: SecurityExtensionDescriptor) -> SecurityExtensionDescriptor:
        if not isinstance(descriptor, SecurityExtensionDescriptor):
            raise ExtensionContractError("descriptor must be a SecurityExtensionDescriptor")
        with self._lock:
            current = self._by_owner.get(descriptor.owner_manifest)
            if current is not None:
                if current.fingerprint == descriptor.fingerprint:
                    return current
                if _version_tuple(descriptor.owner_version) <= _version_tuple(current.owner_version):
                    raise ExtensionCollisionError("extension upgrades require a newer owner_version")
            namespace_owner = self._namespace_owners.get(descriptor.permission_namespace)
            if namespace_owner not in (None, descriptor.owner_manifest):
                raise ExtensionCollisionError("permission namespace is owned by another module")
            for permission in descriptor.permissions:
                owner = self._permissions.get(permission.code, (descriptor.owner_manifest, permission))[0]
                if owner != descriptor.owner_manifest:
                    raise ExtensionCollisionError(f"permission {permission.code} is owned by another module")
            for resource in descriptor.resources:
                owner = self._resources.get(resource.key, (descriptor.owner_manifest, resource))[0]
                if owner != descriptor.owner_manifest:
                    raise ExtensionCollisionError(f"resource {resource.key} is owned by another module")

            if current is not None:
                self._remove(current)
            self._by_owner[descriptor.owner_manifest] = descriptor
            self._namespace_owners[descriptor.permission_namespace] = descriptor.owner_manifest
            self._permissions.update({item.code: (descriptor.owner_manifest, item) for item in descriptor.permissions})
            self._resources.update({item.key: (descriptor.owner_manifest, item) for item in descriptor.resources})
            return descriptor

    def unregister(
        self,
        owner_manifest: str,
        *,
        expected_version: str | None = None,
    ) -> SecurityExtensionDescriptor | None:
        owner = _required(owner_manifest, "owner_manifest", _MANIFEST_NAME)
        with self._lock:
            current = self._by_owner.get(owner)
            if current is None:
                return None
            if expected_version is not None and current.owner_version != expected_version:
                raise ExtensionCollisionError("installed extension version changed before unregister")
            self._remove(current)
            return current

    def _remove(self, descriptor: SecurityExtensionDescriptor) -> None:
        self._by_owner.pop(descriptor.owner_manifest, None)
        if self._namespace_owners.get(descriptor.permission_namespace) == descriptor.owner_manifest:
            self._namespace_owners.pop(descriptor.permission_namespace, None)
        for permission in descriptor.permissions:
            if self._permissions.get(permission.code, (None, None))[0] == descriptor.owner_manifest:
                self._permissions.pop(permission.code, None)
        for resource in descriptor.resources:
            if self._resources.get(resource.key, (None, None))[0] == descriptor.owner_manifest:
                self._resources.pop(resource.key, None)

    def get_permission(self, code: str) -> PermissionDescriptor:
        with self._lock:
            try:
                return self._permissions[code][1]
            except KeyError as exc:
                raise LookupError(f"permission descriptor {code!r} is not registered") from exc

    def get_resource(self, module: str, resource: str) -> ResourceSecurityDescriptor:
        key = f"{_required(module, 'resource module', _SLUG)}.{_required(resource, 'resource name', _SLUG)}"
        with self._lock:
            try:
                return self._resources[key][1]
            except KeyError as exc:
                raise LookupError(f"resource descriptor {key!r} is not registered") from exc

    def get_predicate_schema(self, module: str, resource: str) -> PredicateSchemaDescriptor:
        """Resolve the exact safe-predicate schema owned by a resource."""
        key = f"{_required(module, 'resource module', _SLUG)}.{_required(resource, 'resource name', _SLUG)}"
        with self._lock:
            try:
                owner = self._resources[key][0]
                return self._by_owner[owner].predicate_schema
            except KeyError as exc:
                raise LookupError(f"predicate schema for {key!r} is not registered") from exc

    def list_extensions(self) -> tuple[SecurityExtensionDescriptor, ...]:
        with self._lock:
            return tuple(self._by_owner[key] for key in sorted(self._by_owner))

    def clear(self) -> None:
        """Clear process discovery state, primarily during controlled tests."""
        with self._lock:
            self._by_owner.clear()
            self._namespace_owners.clear()
            self._permissions.clear()
            self._resources.clear()


@dataclass(frozen=True, slots=True)
class FieldAccess:
    visibility: str
    edit_control: str
    mask_pattern: str = ""
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RowAccessExplanation:
    allowed: bool
    applied_rule_ids: tuple[UUID, ...]
    reason_codes: tuple[str, ...]


ModelT = TypeVar("ModelT", bound=Model)


@runtime_checkable
class PermissionCatalogPort(Protocol):
    def register_extension(
        self,
        tenant_id: UUID,
        descriptor: SecurityExtensionDescriptor,
        *,
        actor_id: UUID,
        correlation_id: str,
    ) -> tuple[str, ...]: ...


@runtime_checkable
class FieldPolicyPort(Protocol):
    def resolve_field_access(
        self,
        tenant_id: UUID,
        user_id: UUID,
        module: str,
        resource: str,
        *,
        fields: Sequence[str],
        context: Mapping[str, object],
    ) -> Mapping[str, FieldAccess]: ...


@runtime_checkable
class RowPolicyPort(Protocol):
    def compile_queryset_filter(
        self,
        tenant_id: UUID,
        user_id: UUID,
        module: str,
        resource: str,
        *,
        context: Mapping[str, object],
    ) -> Q: ...

    def explain_row_access(
        self,
        tenant_id: UUID,
        user_id: UUID,
        module: str,
        resource: str,
        *,
        record_attributes: Mapping[str, object],
        context: Mapping[str, object],
    ) -> RowAccessExplanation: ...


@runtime_checkable
class SecurityEnforcementPort(Protocol):
    """Mandatory facade for paid modules serving secured resource data."""

    def secure_queryset(
        self,
        tenant_id: UUID,
        user_id: UUID,
        module: str,
        resource: str,
        queryset: QuerySet[ModelT],
        *,
        context: Mapping[str, object],
    ) -> QuerySet[ModelT]: ...

    def project_fields(
        self,
        tenant_id: UUID,
        user_id: UUID,
        module: str,
        resource: str,
        record: Mapping[str, object],
        *,
        context: Mapping[str, object],
    ) -> Mapping[str, object]: ...


extension_registry = SecurityExtensionRegistry()


def register_security_extension(descriptor: SecurityExtensionDescriptor) -> SecurityExtensionDescriptor:
    return extension_registry.register(descriptor)


def unregister_security_extension(
    owner_manifest: str,
    *,
    expected_version: str | None = None,
) -> SecurityExtensionDescriptor | None:
    return extension_registry.unregister(owner_manifest, expected_version=expected_version)


def get_resource_descriptor(module: str, resource: str) -> ResourceSecurityDescriptor:
    return extension_registry.get_resource(module, resource)


def get_predicate_schema(module: str, resource: str) -> PredicateSchemaDescriptor:
    return extension_registry.get_predicate_schema(module, resource)


__all__ = [
    "ALLOWED_PREDICATE_NODES",
    "EXTENSION_SCHEMA_VERSION",
    "ExtensionCollisionError",
    "ExtensionContractError",
    "FieldAccess",
    "FieldPolicyPort",
    "PermissionCatalogPort",
    "PermissionDescriptor",
    "PermissionRisk",
    "PredicateSchemaDescriptor",
    "ResourceFieldDescriptor",
    "ResourceFieldType",
    "ResourceSecurityDescriptor",
    "RowAccessExplanation",
    "RowPolicyPort",
    "SecurityEnforcementPort",
    "SecurityExtensionDescriptor",
    "SecurityExtensionRegistry",
    "extension_registry",
    "get_predicate_schema",
    "get_resource_descriptor",
    "register_security_extension",
    "unregister_security_extension",
]
