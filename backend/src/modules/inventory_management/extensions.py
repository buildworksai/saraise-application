"""Typed extension SPI for paid and industry inventory modules.

Implementations receive immutable values and narrow service ports. They never
receive inventory QuerySets or model instances, preserving tenant boundaries
and the core ledger invariants.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable
from uuid import UUID

INVENTORY_EXTENSION_CONTRACT_VERSION = "1.0"
_NAME = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")


class ExtensionKind(str, Enum):
    ENTRY_VALIDATOR = "entry_validator"
    VALUATION_STRATEGY = "valuation_strategy"
    TRACE_ENRICHER = "trace_enricher"
    REPLENISHMENT_PROVIDER = "replenishment_provider"
    HEALTH_CONTRIBUTOR = "health_contributor"


class ExtensionRegistrationError(ValueError):
    pass


class DuplicateExtensionError(ExtensionRegistrationError):
    pass


class IncompatibleContractError(ExtensionRegistrationError):
    pass


class CapabilityUnavailableError(LookupError):
    """Truthful failure returned when an optional provider is not installed."""


@dataclass(frozen=True, slots=True)
class EntryLineDTO:
    line_id: UUID
    item_id: UUID
    source_location_id: UUID | None
    destination_location_id: UUID | None
    batch_id: UUID | None
    serial_number_id: UUID | None
    quantity: Decimal
    uom: str
    unit_cost: Decimal | None


@dataclass(frozen=True, slots=True)
class StockEntryDTO:
    tenant_id: UUID
    entry_id: UUID
    entry_number: str
    entry_type: str
    source_warehouse_id: UUID | None
    destination_warehouse_id: UUID | None
    lines: tuple[EntryLineDTO, ...]
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ValuationRequestDTO:
    tenant_id: UUID
    item_id: UUID
    warehouse_id: UUID
    location_id: UUID
    quantity: Decimal
    posting_sequence: int
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ValuationResultDTO:
    unit_cost: Decimal
    total_value: Decimal
    evidence_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class TracePointDTO:
    ledger_entry_id: UUID
    occurred_at: str
    warehouse_id: UUID
    location_id: UUID
    quantity_delta: Decimal
    entry_type: str


@dataclass(frozen=True, slots=True)
class TraceEnrichmentDTO:
    provider: str
    facts: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))


@dataclass(frozen=True, slots=True)
class ReplenishmentRequestDTO:
    tenant_id: UUID
    item_id: UUID
    warehouse_id: UUID
    quantity_on_hand: Decimal
    quantity_available: Decimal
    reorder_point: Decimal | None
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ReplenishmentProposalDTO:
    provider: str
    proposed_quantity: Decimal
    reason_code: str


@dataclass(frozen=True, slots=True)
class ExtensionHealthDTO:
    name: str
    healthy: bool
    breaker_state: str
    reason_code: str


@runtime_checkable
class InventoryReadService(Protocol):
    """Narrow tenant-aware read port exposed to extensions."""

    def available_quantity(
        self, tenant_id: UUID, item_id: UUID, warehouse_id: UUID, location_id: UUID | None = None
    ) -> Decimal: ...


@runtime_checkable
class EntryValidationExtension(Protocol):
    def validate(self, entry: StockEntryDTO, inventory: InventoryReadService) -> tuple[str, ...]: ...


@runtime_checkable
class ValuationStrategyExtension(Protocol):
    def value(self, request: ValuationRequestDTO, inventory: InventoryReadService) -> ValuationResultDTO: ...


@runtime_checkable
class TraceEnricherExtension(Protocol):
    def enrich(
        self, tenant_id: UUID, aggregate_id: UUID, points: tuple[TracePointDTO, ...]
    ) -> TraceEnrichmentDTO: ...


@runtime_checkable
class ReplenishmentProviderExtension(Protocol):
    def propose(
        self, request: ReplenishmentRequestDTO, inventory: InventoryReadService
    ) -> ReplenishmentProposalDTO: ...


@runtime_checkable
class HealthContributorExtension(Protocol):
    def check(self) -> ExtensionHealthDTO: ...


_PROTOCOLS: Mapping[ExtensionKind, type] = {
    ExtensionKind.ENTRY_VALIDATOR: EntryValidationExtension,
    ExtensionKind.VALUATION_STRATEGY: ValuationStrategyExtension,
    ExtensionKind.TRACE_ENRICHER: TraceEnricherExtension,
    ExtensionKind.REPLENISHMENT_PROVIDER: ReplenishmentProviderExtension,
    ExtensionKind.HEALTH_CONTRIBUTOR: HealthContributorExtension,
}


@dataclass(frozen=True, slots=True)
class ExtensionDescriptor:
    name: str
    kind: ExtensionKind
    contract_version: str
    capability: str
    priority: int = 100
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if _NAME.fullmatch(self.name) is None:
            raise ExtensionRegistrationError("extension name must be a lowercase namespaced identifier")
        if _NAME.fullmatch(self.capability) is None:
            raise ExtensionRegistrationError("capability must be a lowercase namespaced identifier")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class RegisteredExtension:
    descriptor: ExtensionDescriptor
    implementation: object = field(repr=False)


@dataclass(frozen=True, slots=True)
class CapabilityResolution:
    available: bool
    capability: str
    reason: str
    extension: RegisteredExtension | None = field(default=None, repr=False)


class InventoryExtensionRegistry:
    """Thread-safe, deterministic registry with strict ABI validation."""

    def __init__(self, contract_version: str = INVENTORY_EXTENSION_CONTRACT_VERSION) -> None:
        self.contract_version = contract_version
        self._entries: dict[tuple[ExtensionKind, str], RegisteredExtension] = {}
        self._lock = threading.RLock()

    def register(self, descriptor: ExtensionDescriptor, implementation: object) -> RegisteredExtension:
        if descriptor.contract_version != self.contract_version:
            raise IncompatibleContractError(
                f"extension {descriptor.name!r} requires inventory contract {descriptor.contract_version}; "
                f"core provides {self.contract_version}"
            )
        protocol = _PROTOCOLS[descriptor.kind]
        if not isinstance(implementation, protocol):
            raise ExtensionRegistrationError(f"implementation does not satisfy {protocol.__name__}")
        key = (descriptor.kind, descriptor.name)
        with self._lock:
            if key in self._entries:
                raise DuplicateExtensionError(f"inventory extension {descriptor.name!r} is already registered")
            registered = RegisteredExtension(descriptor, implementation)
            self._entries[key] = registered
            return registered

    def unregister(self, kind: ExtensionKind, name: str) -> RegisteredExtension:
        with self._lock:
            try:
                return self._entries.pop((kind, name))
            except KeyError as exc:
                raise CapabilityUnavailableError(f"inventory extension {name!r} is not registered") from exc

    def list(self, kind: ExtensionKind | None = None) -> tuple[RegisteredExtension, ...]:
        with self._lock:
            entries = tuple(self._entries.values())
        if kind is not None:
            entries = tuple(entry for entry in entries if entry.descriptor.kind is kind)
        return tuple(sorted(entries, key=lambda entry: (entry.descriptor.priority, entry.descriptor.name)))

    def resolve(self, kind: ExtensionKind, name: str) -> RegisteredExtension:
        with self._lock:
            try:
                return self._entries[(kind, name)]
            except KeyError as exc:
                raise CapabilityUnavailableError(
                    f"inventory capability {kind.value}/{name} is unavailable"
                ) from exc

    def capability(self, capability: str) -> CapabilityResolution:
        matches = tuple(entry for entry in self.list() if entry.descriptor.capability == capability)
        if not matches:
            return CapabilityResolution(False, capability, "capability_not_installed")
        return CapabilityResolution(True, capability, "available", matches[0])


registry = InventoryExtensionRegistry()


def register_extension(descriptor: ExtensionDescriptor, implementation: object) -> RegisteredExtension:
    return registry.register(descriptor, implementation)


def health_contributors() -> tuple[HealthContributorExtension, ...]:
    return tuple(
        entry.implementation  # type: ignore[misc]
        for entry in registry.list(ExtensionKind.HEALTH_CONTRIBUTOR)
    )


__all__ = [
    "CapabilityResolution",
    "CapabilityUnavailableError",
    "DuplicateExtensionError",
    "EntryLineDTO",
    "EntryValidationExtension",
    "ExtensionDescriptor",
    "ExtensionHealthDTO",
    "ExtensionKind",
    "HealthContributorExtension",
    "INVENTORY_EXTENSION_CONTRACT_VERSION",
    "IncompatibleContractError",
    "InventoryExtensionRegistry",
    "InventoryReadService",
    "ReplenishmentProviderExtension",
    "ReplenishmentProposalDTO",
    "ReplenishmentRequestDTO",
    "StockEntryDTO",
    "TraceEnricherExtension",
    "TraceEnrichmentDTO",
    "TracePointDTO",
    "ValuationRequestDTO",
    "ValuationResultDTO",
    "ValuationStrategyExtension",
    "health_contributors",
    "register_extension",
    "registry",
]
