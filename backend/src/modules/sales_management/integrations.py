"""Stable, DTO-only extension contracts for optional sales capabilities.

The open-source funnel does not import models from CRM, inventory, accounting,
tax, shipping, or document modules.  Providers register implementations of the
protocols in this module and receive immutable value objects.  Absence and
provider failure are first-class outcomes: no caller can mistake an empty or
invented value for a successful stock, tax, invoice, shipment, or document
operation.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Generic, Protocol, TypeVar, cast, runtime_checkable
from uuid import UUID

INTEGRATION_CONTRACT_VERSION = "1.0.0"
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
ResultT = TypeVar("ResultT")


def _freeze_json(value: object) -> JsonValue:
    """Copy JSON-compatible input into immutable containers."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError("integration metadata must be JSON-compatible")


def _required_text(value: str, field_name: str, maximum: int = 255) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} must contain between 1 and {maximum} characters")
    return normalized


def _positive_amount(value: Decimal, field_name: str, *, allow_zero: bool = False) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if value < 0 or (not allow_zero and value == 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{field_name} must be {qualifier}")


class Capability(str, Enum):
    CRM_OPPORTUNITY = "crm_opportunity"
    INVENTORY_AVAILABILITY = "inventory_availability"
    ACCOUNTING_INVOICE = "accounting_invoice"
    TAX_CALCULATION = "tax_calculation"
    SHIPPING = "shipping"
    DOCUMENT_RENDERING = "document_rendering"
    DOCUMENT_DISPATCH = "document_dispatch"


class CapabilityStatus(str, Enum):
    AVAILABLE = "available"
    NOT_INSTALLED = "not_installed"
    NOT_ENTITLED = "not_entitled"
    NOT_CONFIGURED = "not_configured"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


class FailureCode(str, Enum):
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_ENTITLED = "NOT_ENTITLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    DEPENDENCY_TIMEOUT = "DEPENDENCY_TIMEOUT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    DEPENDENCY_REJECTED = "DEPENDENCY_REJECTED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    ENTITLEMENT_AUTHORITY_UNAVAILABLE = "ENTITLEMENT_AUTHORITY_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class IntegrationFailure:
    """Sanitized failure evidence safe to expose through governed APIs."""

    code: FailureCode
    dependency: str
    message: str
    retryable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependency", _required_text(self.dependency, "dependency", 100))
        object.__setattr__(self, "message", _required_text(self.message, "message", 500))


@dataclass(frozen=True, slots=True)
class GatewayResult(Generic[ResultT]):
    """Explicit result union used by every optional provider operation."""

    value: ResultT | None = None
    failure: IntegrationFailure | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.failure is None):
            raise ValueError("gateway result must contain exactly one of value or failure")

    @property
    def succeeded(self) -> bool:
        return self.failure is None

    @classmethod
    def success(cls, value: ResultT) -> "GatewayResult[ResultT]":
        if value is None:
            raise ValueError("successful gateway results require evidence")
        return cls(value=value)

    @classmethod
    def unavailable(
        cls,
        *,
        dependency: str,
        code: FailureCode,
        message: str,
        retryable: bool = False,
    ) -> "GatewayResult[ResultT]":
        return cls(failure=IntegrationFailure(code, dependency, message, retryable))


@dataclass(frozen=True, slots=True)
class CapabilityState:
    capability: Capability
    status: CapabilityStatus
    reason_code: str
    provider_id: str | None = None
    provider_version: str | None = None

    @property
    def available(self) -> bool:
        return self.status is CapabilityStatus.AVAILABLE

    def as_dict(self) -> dict[str, object]:
        return {
            "capability": self.capability.value,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
        }


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    """Versioned registration metadata for deterministic provider selection."""

    provider_id: str
    provider_version: str
    capabilities: tuple[Capability, ...]
    priority: int = 100
    required_entitlement: str | None = None
    configured: bool = True
    contract_version: str = INTEGRATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _required_text(self.provider_id, "provider_id", 120))
        object.__setattr__(self, "provider_version", _required_text(self.provider_version, "provider_version", 40))
        object.__setattr__(self, "contract_version", _required_text(self.contract_version, "contract_version", 40))
        if not self.capabilities or len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("provider capabilities must be non-empty and unique")
        if self.contract_version.split(".", 1)[0] != INTEGRATION_CONTRACT_VERSION.split(".", 1)[0]:
            raise ValueError("provider contract major version is incompatible")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer")
        if self.required_entitlement is not None:
            object.__setattr__(
                self,
                "required_entitlement",
                _required_text(self.required_entitlement, "required_entitlement", 160),
            )


@dataclass(frozen=True, slots=True)
class OpportunitySnapshot:
    opportunity_id: UUID
    customer_reference: UUID | None
    currency: str
    valid_until: date | None
    line_items: tuple[Mapping[str, JsonValue], ...]
    source_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _required_text(self.currency, "currency", 3).upper())
        object.__setattr__(self, "source_version", _required_text(self.source_version, "source_version", 64))
        object.__setattr__(
            self, "line_items", tuple(cast(Mapping[str, JsonValue], _freeze_json(item)) for item in self.line_items)
        )


@dataclass(frozen=True, slots=True)
class InventoryAvailabilityRequest:
    tenant_id: UUID
    order_id: UUID
    warehouse_id: UUID | None
    lines: tuple[tuple[UUID, Decimal], ...]
    correlation_id: UUID

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError("inventory request must contain at least one line")
        for _item_id, quantity in self.lines:
            _positive_amount(quantity, "quantity")


@dataclass(frozen=True, slots=True)
class InventoryLineAvailability:
    item_id: UUID
    requested_quantity: Decimal
    available_quantity: Decimal
    available: bool

    def __post_init__(self) -> None:
        _positive_amount(self.requested_quantity, "requested_quantity")
        _positive_amount(self.available_quantity, "available_quantity", allow_zero=True)


@dataclass(frozen=True, slots=True)
class InventoryAvailability:
    accepted: bool
    lines: tuple[InventoryLineAvailability, ...]
    evidence_reference: str

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError("inventory result must contain line evidence")
        object.__setattr__(self, "evidence_reference", _required_text(self.evidence_reference, "evidence_reference"))
        if self.accepted != all(line.available for line in self.lines):
            raise ValueError("inventory acceptance must match its line evidence")


@dataclass(frozen=True, slots=True)
class InvoiceRequest:
    tenant_id: UUID
    order_id: UUID
    currency: str
    total_amount: Decimal
    idempotency_key: str
    correlation_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _required_text(self.currency, "currency", 3).upper())
        object.__setattr__(self, "idempotency_key", _required_text(self.idempotency_key, "idempotency_key"))
        _positive_amount(self.total_amount, "total_amount", allow_zero=True)


@dataclass(frozen=True, slots=True)
class InvoiceResult:
    invoice_id: UUID
    provider_reference: str
    accepted_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_reference", _required_text(self.provider_reference, "provider_reference"))


@dataclass(frozen=True, slots=True)
class TaxLineInput:
    line_id: UUID
    item_id: UUID | None
    quantity: Decimal
    taxable_amount: Decimal

    def __post_init__(self) -> None:
        _positive_amount(self.quantity, "quantity")
        _positive_amount(self.taxable_amount, "taxable_amount", allow_zero=True)


@dataclass(frozen=True, slots=True)
class TaxCalculationRequest:
    tenant_id: UUID
    currency: str
    transaction_date: date
    destination_reference: str
    lines: tuple[TaxLineInput, ...]
    correlation_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _required_text(self.currency, "currency", 3).upper())
        object.__setattr__(
            self, "destination_reference", _required_text(self.destination_reference, "destination_reference")
        )
        if not self.lines:
            raise ValueError("tax request must contain at least one line")


@dataclass(frozen=True, slots=True)
class TaxLineResult:
    line_id: UUID
    tax_amount: Decimal
    rate: Decimal
    jurisdiction_code: str

    def __post_init__(self) -> None:
        _positive_amount(self.tax_amount, "tax_amount", allow_zero=True)
        _positive_amount(self.rate, "rate", allow_zero=True)
        object.__setattr__(self, "jurisdiction_code", _required_text(self.jurisdiction_code, "jurisdiction_code", 80))


@dataclass(frozen=True, slots=True)
class TaxCalculation:
    total_tax: Decimal
    lines: tuple[TaxLineResult, ...]
    provider_reference: str
    calculation_version: str

    def __post_init__(self) -> None:
        _positive_amount(self.total_tax, "total_tax", allow_zero=True)
        if not self.lines or sum((line.tax_amount for line in self.lines), Decimal("0")) != self.total_tax:
            raise ValueError("tax total must equal the supplied line evidence")
        object.__setattr__(self, "provider_reference", _required_text(self.provider_reference, "provider_reference"))
        object.__setattr__(
            self, "calculation_version", _required_text(self.calculation_version, "calculation_version", 64)
        )


@dataclass(frozen=True, slots=True)
class ShipmentRequest:
    tenant_id: UUID
    delivery_note_id: UUID
    carrier_code: str
    destination_reference: str
    idempotency_key: str
    correlation_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "carrier_code", _required_text(self.carrier_code, "carrier_code", 80))
        object.__setattr__(
            self, "destination_reference", _required_text(self.destination_reference, "destination_reference")
        )
        object.__setattr__(self, "idempotency_key", _required_text(self.idempotency_key, "idempotency_key"))


@dataclass(frozen=True, slots=True)
class ShipmentResult:
    shipment_id: str
    tracking_number: str
    carrier_name: str
    accepted_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "shipment_id", _required_text(self.shipment_id, "shipment_id"))
        object.__setattr__(self, "tracking_number", _required_text(self.tracking_number, "tracking_number"))
        object.__setattr__(self, "carrier_name", _required_text(self.carrier_name, "carrier_name", 120))


@dataclass(frozen=True, slots=True)
class DocumentRenderRequest:
    tenant_id: UUID
    document_kind: str
    aggregate_id: UUID
    aggregate_version: int
    locale: str
    snapshot: Mapping[str, JsonValue]
    correlation_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_kind", _required_text(self.document_kind, "document_kind", 40))
        object.__setattr__(self, "locale", _required_text(self.locale, "locale", 20))
        object.__setattr__(self, "snapshot", cast(Mapping[str, JsonValue], _freeze_json(self.snapshot)))
        if self.aggregate_version < 1:
            raise ValueError("aggregate_version must be positive")


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    document_id: UUID
    media_type: str
    content: bytes
    checksum_sha256: str
    rendered_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_type", _required_text(self.media_type, "media_type", 100))
        if not self.content:
            raise ValueError("rendered document content cannot be empty")
        checksum = self.checksum_sha256.lower()
        if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
            raise ValueError("checksum_sha256 must be lowercase hexadecimal")
        object.__setattr__(self, "checksum_sha256", checksum)


@dataclass(frozen=True, slots=True)
class DocumentDispatchRequest:
    tenant_id: UUID
    document_id: UUID
    channel: str
    recipient_reference: str
    idempotency_key: str
    correlation_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel", _required_text(self.channel, "channel", 40))
        object.__setattr__(self, "recipient_reference", _required_text(self.recipient_reference, "recipient_reference"))
        object.__setattr__(self, "idempotency_key", _required_text(self.idempotency_key, "idempotency_key"))


@dataclass(frozen=True, slots=True)
class DocumentDispatchResult:
    dispatch_id: str
    accepted_at: datetime
    provider_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "dispatch_id", _required_text(self.dispatch_id, "dispatch_id"))
        object.__setattr__(self, "provider_reference", _required_text(self.provider_reference, "provider_reference"))


@runtime_checkable
class CRMOpportunityGateway(Protocol):
    descriptor: ProviderDescriptor

    def get_opportunity(
        self, tenant_id: UUID, opportunity_id: UUID, correlation_id: UUID
    ) -> GatewayResult[OpportunitySnapshot]: ...


@runtime_checkable
class InventoryAvailabilityGateway(Protocol):
    descriptor: ProviderDescriptor

    def check_availability(self, request: InventoryAvailabilityRequest) -> GatewayResult[InventoryAvailability]: ...


@runtime_checkable
class AccountingInvoiceGateway(Protocol):
    descriptor: ProviderDescriptor

    def create_invoice(self, request: InvoiceRequest) -> GatewayResult[InvoiceResult]: ...


@runtime_checkable
class TaxCalculationGateway(Protocol):
    descriptor: ProviderDescriptor

    def calculate_tax(self, request: TaxCalculationRequest) -> GatewayResult[TaxCalculation]: ...


@runtime_checkable
class ShippingGateway(Protocol):
    descriptor: ProviderDescriptor

    def create_shipment(self, request: ShipmentRequest) -> GatewayResult[ShipmentResult]: ...


@runtime_checkable
class DocumentGateway(Protocol):
    descriptor: ProviderDescriptor

    def render(self, request: DocumentRenderRequest) -> GatewayResult[RenderedDocument]: ...

    def dispatch(self, request: DocumentDispatchRequest) -> GatewayResult[DocumentDispatchResult]: ...


Gateway = (
    CRMOpportunityGateway
    | InventoryAvailabilityGateway
    | AccountingInvoiceGateway
    | TaxCalculationGateway
    | ShippingGateway
    | DocumentGateway
)


class IntegrationRegistryError(RuntimeError):
    code = "INTEGRATION_REGISTRY_ERROR"


class RegistrationCollision(IntegrationRegistryError):
    code = "INTEGRATION_REGISTRATION_COLLISION"


class IntegrationUnavailable(IntegrationRegistryError):
    """503-mappable resolution error with a stable, non-sensitive reason."""

    code = "INTEGRATION_UNAVAILABLE"

    def __init__(self, state: CapabilityState) -> None:
        self.state = state
        super().__init__(f"{state.capability.value} is unavailable ({state.reason_code})")


AvailabilityResolver = Callable[[UUID, ProviderDescriptor, Capability], CapabilityState | None]
EntitlementChecker = Callable[[UUID, str], bool]


class SalesIntegrationRegistry:
    """Thread-safe registry with deterministic selection and clean uninstall."""

    _PROTOCOLS: Mapping[Capability, type[object]] = MappingProxyType(
        {
            Capability.CRM_OPPORTUNITY: CRMOpportunityGateway,
            Capability.INVENTORY_AVAILABILITY: InventoryAvailabilityGateway,
            Capability.ACCOUNTING_INVOICE: AccountingInvoiceGateway,
            Capability.TAX_CALCULATION: TaxCalculationGateway,
            Capability.SHIPPING: ShippingGateway,
            Capability.DOCUMENT_RENDERING: DocumentGateway,
            Capability.DOCUMENT_DISPATCH: DocumentGateway,
        }
    )

    def __init__(
        self,
        *,
        entitlement_checker: EntitlementChecker | None = None,
        availability_resolver: AvailabilityResolver | None = None,
    ) -> None:
        self._providers: dict[tuple[Capability, str], Gateway] = {}
        self._lock = threading.RLock()
        self._entitlement_checker = entitlement_checker
        self._availability_resolver = availability_resolver

    def register(self, provider: Gateway) -> ProviderDescriptor:
        descriptor = getattr(provider, "descriptor", None)
        if not isinstance(descriptor, ProviderDescriptor):
            raise TypeError("provider must expose a ProviderDescriptor")
        for capability in descriptor.capabilities:
            protocol = self._PROTOCOLS[capability]
            if not isinstance(provider, protocol):
                raise TypeError(f"provider does not implement {capability.value}")
        keys = tuple((capability, descriptor.provider_id) for capability in descriptor.capabilities)
        with self._lock:
            collisions = [key for key in keys if key in self._providers]
            if collisions:
                raise RegistrationCollision(f"provider {descriptor.provider_id!r} is already registered")
            for key in keys:
                self._providers[key] = provider
        return descriptor

    def unregister(self, provider_id: str) -> tuple[Gateway, ...]:
        canonical = _required_text(provider_id, "provider_id", 120)
        removed: list[Gateway] = []
        with self._lock:
            for key in tuple(self._providers):
                if key[1] == canonical:
                    provider = self._providers.pop(key)
                    if all(provider is not item for item in removed):
                        removed.append(provider)
        return tuple(removed)

    def _candidates(self, capability: Capability) -> tuple[Gateway, ...]:
        with self._lock:
            values = [provider for (registered, _), provider in self._providers.items() if registered is capability]
        return tuple(
            sorted(
                values,
                key=lambda provider: (-provider.descriptor.priority, provider.descriptor.provider_id),
            )
        )

    def _state_for(self, tenant_id: UUID, capability: Capability, provider: Gateway) -> CapabilityState:
        descriptor = provider.descriptor
        if not descriptor.configured:
            return CapabilityState(
                capability,
                CapabilityStatus.NOT_CONFIGURED,
                FailureCode.NOT_CONFIGURED.value,
                descriptor.provider_id,
                descriptor.provider_version,
            )
        if descriptor.required_entitlement:
            if self._entitlement_checker is None:
                return CapabilityState(
                    capability,
                    CapabilityStatus.TEMPORARILY_UNAVAILABLE,
                    FailureCode.ENTITLEMENT_AUTHORITY_UNAVAILABLE.value,
                    descriptor.provider_id,
                    descriptor.provider_version,
                )
            try:
                entitled = self._entitlement_checker(tenant_id, descriptor.required_entitlement)
            except Exception:
                return CapabilityState(
                    capability,
                    CapabilityStatus.TEMPORARILY_UNAVAILABLE,
                    FailureCode.ENTITLEMENT_AUTHORITY_UNAVAILABLE.value,
                    descriptor.provider_id,
                    descriptor.provider_version,
                )
            if not entitled:
                return CapabilityState(
                    capability,
                    CapabilityStatus.NOT_ENTITLED,
                    FailureCode.NOT_ENTITLED.value,
                    descriptor.provider_id,
                    descriptor.provider_version,
                )
        if self._availability_resolver is not None:
            try:
                resolved = self._availability_resolver(tenant_id, descriptor, capability)
            except Exception:
                resolved = CapabilityState(
                    capability,
                    CapabilityStatus.TEMPORARILY_UNAVAILABLE,
                    FailureCode.DEPENDENCY_UNAVAILABLE.value,
                    descriptor.provider_id,
                    descriptor.provider_version,
                )
            if resolved is not None:
                if resolved.capability is not capability:
                    raise ValueError("availability resolver returned the wrong capability")
                return resolved
        return CapabilityState(
            capability,
            CapabilityStatus.AVAILABLE,
            "AVAILABLE",
            descriptor.provider_id,
            descriptor.provider_version,
        )

    def capability_state(self, tenant_id: UUID, capability: Capability) -> CapabilityState:
        if not isinstance(tenant_id, UUID):
            raise TypeError("tenant_id must be UUID")
        candidates = self._candidates(capability)
        if not candidates:
            return CapabilityState(capability, CapabilityStatus.NOT_INSTALLED, FailureCode.NOT_INSTALLED.value)
        states = tuple(self._state_for(tenant_id, capability, provider) for provider in candidates)
        for state in states:
            if state.available:
                return state
        return states[0]

    def capabilities(self, tenant_id: UUID) -> tuple[CapabilityState, ...]:
        return tuple(self.capability_state(tenant_id, capability) for capability in Capability)

    def resolve(self, tenant_id: UUID, capability: Capability) -> Gateway:
        state = self.capability_state(tenant_id, capability)
        if not state.available or state.provider_id is None:
            raise IntegrationUnavailable(state)
        with self._lock:
            provider = self._providers.get((capability, state.provider_id))
        if provider is None:
            raise IntegrationUnavailable(
                CapabilityState(
                    capability,
                    CapabilityStatus.TEMPORARILY_UNAVAILABLE,
                    FailureCode.DEPENDENCY_UNAVAILABLE.value,
                    state.provider_id,
                    state.provider_version,
                )
            )
        return provider


_registry = SalesIntegrationRegistry()
_registry_lock = threading.RLock()


def get_integration_registry() -> SalesIntegrationRegistry:
    with _registry_lock:
        return _registry


def set_integration_registry(registry: SalesIntegrationRegistry) -> None:
    if not isinstance(registry, SalesIntegrationRegistry):
        raise TypeError("registry must be a SalesIntegrationRegistry")
    global _registry, integrations
    with _registry_lock:
        _registry = registry
        integrations = registry


# Backwards-friendly public aliases for extensions that use the generic name.
IntegrationRegistry = SalesIntegrationRegistry
integrations = _registry


__all__ = [
    "AccountingInvoiceGateway",
    "Capability",
    "CapabilityState",
    "CapabilityStatus",
    "CRMOpportunityGateway",
    "DocumentDispatchRequest",
    "DocumentDispatchResult",
    "DocumentGateway",
    "DocumentRenderRequest",
    "FailureCode",
    "GatewayResult",
    "INTEGRATION_CONTRACT_VERSION",
    "IntegrationFailure",
    "IntegrationRegistry",
    "IntegrationUnavailable",
    "InventoryAvailability",
    "InventoryAvailabilityGateway",
    "InventoryAvailabilityRequest",
    "InventoryLineAvailability",
    "InvoiceRequest",
    "InvoiceResult",
    "OpportunitySnapshot",
    "ProviderDescriptor",
    "RegistrationCollision",
    "RenderedDocument",
    "SalesIntegrationRegistry",
    "ShipmentRequest",
    "ShipmentResult",
    "ShippingGateway",
    "TaxCalculation",
    "TaxCalculationGateway",
    "TaxCalculationRequest",
    "TaxLineInput",
    "TaxLineResult",
    "get_integration_registry",
    "integrations",
    "set_integration_registry",
]
