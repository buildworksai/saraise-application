"""Stable, versioned extension ABI for free and paid MDM modules.

Extensions are registered by trusted installed modules during application
bootstrap.  Tenant-supplied executable code is never accepted.  Resolution is
exact-version and collision-safe so historical validations and merge decisions
remain reproducible after an extension upgrade.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import MappingProxyType
from typing import Protocol, runtime_checkable
from uuid import UUID


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{1,99}$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){1,2}(?:[-+][A-Za-z0-9.-]+)?$")


class ExtensionRegistryError(RuntimeError):
    """Base class for deterministic extension registration failures."""


class ExtensionConflict(ExtensionRegistryError):
    """Raised when a stable extension identity is claimed incompatibly."""


class CapabilityUnavailable(ExtensionRegistryError):
    """Raised when an exact installed and available capability cannot resolve."""

    code = "CAPABILITY_UNAVAILABLE"


class ExtensionExecutionError(ExtensionRegistryError):
    """Typed boundary for extension failure without fabricated fallback data."""


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]


def _freeze(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        frozen = {str(key): _freeze(item) for key, item in value.items()}
        return MappingProxyType(frozen)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze(item) for item in value)
    raise TypeError("Extension DTOs accept JSON-compatible values only")


def _identifier(value: str, label: str) -> str:
    candidate = str(value).strip()
    if not _IDENTIFIER.fullmatch(candidate):
        raise ValueError(f"{label} must be a lowercase snake-case identifier")
    return candidate


def _version(value: str) -> str:
    candidate = str(value).strip()
    if not _VERSION.fullmatch(candidate):
        raise ValueError("version must be a semantic numeric version")
    return candidate


@dataclass(frozen=True, slots=True)
class EntityTypeDefinition:
    key: str
    display_name: str
    description: str
    json_schema: Mapping[str, JsonValue]
    required_fields: tuple[str, ...] = ()
    sensitive_fields: tuple[str, ...] = ()
    searchable_fields: tuple[str, ...] = ()
    metadata: Mapping[str, JsonValue] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _identifier(self.key, "entity type key"))
        object.__setattr__(self, "json_schema", _freeze(self.json_schema))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True, slots=True)
class EntityRecord:
    """Immutable, policy-filtered record passed across the ORM boundary."""

    tenant_id: UUID
    entity_id: UUID
    entity_type_key: str
    entity_code: str
    entity_name: str
    data: Mapping[str, JsonValue]
    version: int
    schema_version: int
    purpose: str
    allowed_fields: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _freeze(self.data))


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    field_path: str
    dimension: str
    severity: str
    code: str
    message: str
    evidence: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze(self.evidence))


@dataclass(frozen=True, slots=True)
class MatchEvidence:
    confidence: str
    field_scores: Mapping[str, JsonValue]
    evidence: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_scores", _freeze(self.field_scores))
        object.__setattr__(self, "evidence", _freeze(self.evidence))


@dataclass(frozen=True, slots=True)
class SurvivorshipDecision:
    values: Mapping[str, JsonValue]
    source_entity_ids: Mapping[str, JsonValue]
    evidence: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze(self.values))
        object.__setattr__(self, "source_entity_ids", _freeze(self.source_entity_ids))
        object.__setattr__(self, "evidence", _freeze(self.evidence))


@dataclass(frozen=True, slots=True)
class ProjectionEvent:
    event_id: UUID
    schema_name: str
    schema_version: int
    tenant_id: UUID
    aggregate_id: UUID
    aggregate_version: int
    occurred_at: datetime
    correlation_id: str
    payload: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))


@dataclass(frozen=True, slots=True)
class ProjectionReceipt:
    event_id: UUID
    consumer_key: str
    consumer_version: str
    checkpoint: str


@runtime_checkable
class EntityTypeContributor(Protocol):
    owner_module: str
    key: str
    version: str

    def definitions(self, tenant_id: UUID) -> tuple[EntityTypeDefinition, ...]:
        """Return declarative types; persistence remains in EntityTypeService."""


@runtime_checkable
class EntityValidator(Protocol):
    owner_module: str
    key: str
    version: str

    def validate(self, tenant_id: UUID, entity: EntityRecord) -> tuple[ValidationFinding, ...]:
        """Return deterministic findings without mutating the record."""


@runtime_checkable
class MatchingStrategy(Protocol):
    owner_module: str
    key: str
    version: str

    def compare(
        self,
        tenant_id: UUID,
        left: EntityRecord,
        right: EntityRecord,
        configuration: Mapping[str, JsonValue],
    ) -> MatchEvidence:
        """Return deterministic evidence for an already-blocked pair."""


@runtime_checkable
class SurvivorshipStrategy(Protocol):
    owner_module: str
    key: str
    version: str

    def select(
        self,
        tenant_id: UUID,
        records: tuple[EntityRecord, ...],
        overrides: Mapping[str, JsonValue],
        configuration: Mapping[str, JsonValue],
    ) -> SurvivorshipDecision:
        """Select values and provenance without writing ORM state."""


@runtime_checkable
class EntityProjectionConsumer(Protocol):
    owner_module: str
    key: str
    version: str

    def consume(self, event: ProjectionEvent, *, idempotency_key: str) -> ProjectionReceipt:
        """Consume one ordered outbox event idempotently or raise truthfully."""


Extension = EntityTypeContributor | EntityValidator | MatchingStrategy | SurvivorshipStrategy | EntityProjectionConsumer


@dataclass(frozen=True, slots=True)
class ExtensionRegistration:
    category: str
    owner_module: str
    key: str
    version: str
    implementation: Extension
    available: bool = True

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return self.category, self.owner_module, self.key, self.version


class MDMExtensionRegistry:
    """Thread-safe exact-version registry with explicit replacement semantics."""

    CATEGORIES = frozenset({"entity_type", "validator", "matching", "survivorship", "projection"})

    def __init__(self) -> None:
        self._registrations: dict[tuple[str, str, str, str], ExtensionRegistration] = {}
        self._lock = threading.RLock()

    def register(
        self,
        category: str,
        extension: Extension,
        *,
        replaces_version: str | None = None,
    ) -> ExtensionRegistration:
        if category not in self.CATEGORIES:
            raise ValueError(f"Unknown MDM extension category {category!r}")
        owner = _identifier(extension.owner_module, "owner module")
        key = _identifier(extension.key, "extension key")
        version = _version(extension.version)
        registration = ExtensionRegistration(category, owner, key, version, extension)
        with self._lock:
            existing = self._registrations.get(registration.identity)
            if existing is not None:
                if existing.implementation is extension and existing.available:
                    return existing
                raise ExtensionConflict(f"Extension identity {registration.identity!r} is already registered")
            active_versions = [
                item
                for item in self._registrations.values()
                if item.category == category and item.owner_module == owner and item.key == key and item.available
            ]
            if active_versions:
                expected = _version(replaces_version) if replaces_version is not None else None
                if expected is None or not any(item.version == expected for item in active_versions):
                    raise ExtensionConflict("A version upgrade must explicitly name the active version it replaces")
                for item in active_versions:
                    if item.version == expected:
                        self._registrations[item.identity] = replace(item, available=False)
            self._registrations[registration.identity] = registration
        return registration

    def unregister(self, category: str, owner_module: str, key: str, version: str) -> ExtensionRegistration:
        identity = (
            category,
            _identifier(owner_module, "owner module"),
            _identifier(key, "extension key"),
            _version(version),
        )
        with self._lock:
            existing = self._registrations.get(identity)
            if existing is None:
                raise CapabilityUnavailable(f"Extension {identity!r} is not installed")
            unavailable = replace(existing, available=False)
            self._registrations[identity] = unavailable
            return unavailable

    def resolve(self, category: str, owner_module: str, key: str, version: str) -> Extension:
        identity = (
            category,
            _identifier(owner_module, "owner module"),
            _identifier(key, "extension key"),
            _version(version),
        )
        with self._lock:
            registration = self._registrations.get(identity)
        if registration is None or not registration.available:
            raise CapabilityUnavailable(f"Extension {identity!r} is unavailable")
        return registration.implementation

    def list(
        self,
        *,
        category: str | None = None,
        include_unavailable: bool = False,
    ) -> tuple[ExtensionRegistration, ...]:
        if category is not None and category not in self.CATEGORIES:
            raise ValueError(f"Unknown MDM extension category {category!r}")
        with self._lock:
            values = tuple(self._registrations[key] for key in sorted(self._registrations))
        return tuple(
            item
            for item in values
            if (category is None or item.category == category) and (include_unavailable or item.available)
        )

    def clear(self) -> None:
        """Test/bootstrap reset; production callers should use unregister."""
        with self._lock:
            self._registrations.clear()


extension_registry = MDMExtensionRegistry()


def register_entity_type_contributor(
    extension: EntityTypeContributor,
    *,
    replaces_version: str | None = None,
) -> ExtensionRegistration:
    return extension_registry.register("entity_type", extension, replaces_version=replaces_version)


def register_validator(extension: EntityValidator, *, replaces_version: str | None = None) -> ExtensionRegistration:
    return extension_registry.register("validator", extension, replaces_version=replaces_version)


def register_matching_strategy(
    extension: MatchingStrategy,
    *,
    replaces_version: str | None = None,
) -> ExtensionRegistration:
    return extension_registry.register("matching", extension, replaces_version=replaces_version)


def register_survivorship_strategy(
    extension: SurvivorshipStrategy,
    *,
    replaces_version: str | None = None,
) -> ExtensionRegistration:
    return extension_registry.register("survivorship", extension, replaces_version=replaces_version)


def register_projection_consumer(
    extension: EntityProjectionConsumer,
    *,
    replaces_version: str | None = None,
) -> ExtensionRegistration:
    return extension_registry.register("projection", extension, replaces_version=replaces_version)


__all__ = [
    "CapabilityUnavailable",
    "EntityProjectionConsumer",
    "EntityRecord",
    "EntityTypeContributor",
    "EntityTypeDefinition",
    "EntityValidator",
    "ExtensionConflict",
    "ExtensionExecutionError",
    "ExtensionRegistration",
    "MDMExtensionRegistry",
    "MatchEvidence",
    "MatchingStrategy",
    "ProjectionEvent",
    "ProjectionReceipt",
    "SurvivorshipDecision",
    "SurvivorshipStrategy",
    "ValidationFinding",
    "extension_registry",
    "register_entity_type_contributor",
    "register_matching_strategy",
    "register_projection_consumer",
    "register_survivorship_strategy",
    "register_validator",
]
