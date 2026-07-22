"""Versioned, circuit-isolated SPI for paid multi-company modules."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, TypeVar, runtime_checkable
from uuid import UUID

from src.core.resilience import CircuitBreakerRegistry

from .integrations import CapabilityUnavailable

SPI_VERSION = "multi-company-spi-v1"
_KEY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}$")


class ExtensionError(RuntimeError):
    pass


class DuplicateExtensionError(ExtensionError):
    pass


class InvalidExtensionError(ExtensionError):
    pass


class ExtensionAccessDenied(ExtensionError):
    pass


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def immutable_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Recursively freeze provider input so extensions cannot mutate core context."""
    return _freeze(value or {})


@dataclass(frozen=True, slots=True)
class ExtensionContext:
    tenant_id: UUID
    actor_id: str
    correlation_id: str
    environment: str
    configuration_version: int
    settings: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    entitlements: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class CompanyDTO:
    id: UUID
    code: str
    name: str
    currency: str
    consolidation_group: str
    ownership_percentage: Decimal | None


@dataclass(frozen=True, slots=True)
class TransactionDTO:
    id: UUID
    reference: str
    source_company_id: UUID
    target_company_id: UUID
    transaction_type: str
    product_category: str
    amount: Decimal
    currency: str
    transaction_date: date


@dataclass(frozen=True, slots=True)
class ProviderResultV1:
    provider_key: str
    provider_version: str
    schema_version: str
    data: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TransferPricingInputV1:
    amount: Decimal
    parameters: Mapping[str, Any]
    source_company: CompanyDTO
    target_company: CompanyDTO
    transaction_type: str
    product_category: str
    effective_date: date


@dataclass(frozen=True, slots=True)
class TransferPricingOutputV1:
    provider_key: str
    provider_version: str
    calculated_amount: Decimal
    formula: str
    evidence: Mapping[str, Any]


class ExtensionProviderV1(Protocol):
    key: str
    version: str
    spi_version: str
    entitlement: str
    feature_flag: str
    required_permission: str


@runtime_checkable
class ConsolidationContributorV1(ExtensionProviderV1, Protocol):
    def contribute(self, companies: Sequence[CompanyDTO], period_start: date, period_end: date, context: ExtensionContext) -> ProviderResultV1: ...


@runtime_checkable
class EliminationRuleProviderV1(ExtensionProviderV1, Protocol):
    def generate(self, transactions: Sequence[TransactionDTO], context: ExtensionContext) -> Sequence[ProviderResultV1]: ...


@runtime_checkable
class TransferPricingMethodProviderV1(ExtensionProviderV1, Protocol):
    def calculate(self, request: TransferPricingInputV1, context: ExtensionContext) -> TransferPricingOutputV1: ...


@runtime_checkable
class CompanyValidationProviderV1(ExtensionProviderV1, Protocol):
    def validate(self, company: CompanyDTO, context: ExtensionContext) -> ProviderResultV1: ...


@runtime_checkable
class TransactionEnrichmentProviderV1(ExtensionProviderV1, Protocol):
    def enrich(self, transaction: TransactionDTO, context: ExtensionContext) -> ProviderResultV1: ...


@runtime_checkable
class CompanyDetailPanelProviderV1(ExtensionProviderV1, Protocol):
    def panel(self, company: CompanyDTO, context: ExtensionContext) -> ProviderResultV1: ...


@dataclass(frozen=True, slots=True)
class ExtensionCatalogEntry:
    key: str
    version: str
    spi_version: str
    installed: bool
    entitled: bool
    feature_enabled: bool
    access_allowed: bool
    compatible: bool
    healthy: bool
    available: bool
    locked: bool
    unavailable_reason: str = ""


ProviderT = TypeVar("ProviderT", bound=ExtensionProviderV1)


class ExtensionRegistry:
    """Thread-safe registry with explicit activation and failure isolation."""

    def __init__(self) -> None:
        self._providers: dict[str, ExtensionProviderV1] = {}
        self._lock = threading.RLock()
        self._breakers = CircuitBreakerRegistry(failure_threshold=3, reset_timeout=60)

    def register(self, provider: ProviderT) -> ProviderT:
        self._validate(provider)
        with self._lock:
            if provider.key in self._providers:
                raise DuplicateExtensionError(f"Extension {provider.key!r} is already registered")
            self._providers[provider.key] = provider
        return provider

    def unregister(self, key: str) -> ExtensionProviderV1 | None:
        with self._lock:
            return self._providers.pop(key, None)

    def get(self, key: str) -> ExtensionProviderV1:
        with self._lock:
            provider = self._providers.get(key)
        if provider is None:
            raise CapabilityUnavailable("multi_company_extension", key)
        return provider

    def invoke(self, key: str, method: str, context: ExtensionContext, *args: Any) -> Any:
        provider = self.get(key)
        entry = self._catalog_entry(provider, context)
        if not entry.available:
            if entry.locked:
                raise ExtensionAccessDenied(entry.unavailable_reason)
            raise CapabilityUnavailable("multi_company_extension", key)
        function = getattr(provider, method, None)
        if function is None or not callable(function):
            raise InvalidExtensionError(f"Extension {key!r} does not implement {method!r}")
        result = self._breakers.get(key).call(function, *args, context)
        self._validate_result(key, result)
        return result

    def catalog(self, context: ExtensionContext) -> tuple[ExtensionCatalogEntry, ...]:
        with self._lock:
            providers = tuple(self._providers.values())
        return tuple(self._catalog_entry(provider, context) for provider in sorted(providers, key=lambda item: item.key))

    def _catalog_entry(self, provider: ExtensionProviderV1, context: ExtensionContext) -> ExtensionCatalogEntry:
        entitled = not provider.entitlement or provider.entitlement in context.entitlements
        enabled = not provider.feature_flag or bool(context.settings.get("feature_flags", {}).get(provider.feature_flag, False))
        allowed = not provider.required_permission or provider.required_permission in context.permissions
        compatible = provider.spi_version == SPI_VERSION
        healthy = self._breakers.get(provider.key).state.value != "open"
        available = entitled and enabled and allowed and compatible and healthy
        reason = ""
        if not compatible: reason = "INCOMPATIBLE_SPI"
        elif not entitled: reason = "ENTITLEMENT_REQUIRED"
        elif not enabled: reason = "FEATURE_DISABLED"
        elif not allowed: reason = "ACCESS_DENIED"
        elif not healthy: reason = "PROVIDER_UNHEALTHY"
        return ExtensionCatalogEntry(
            key=provider.key, version=provider.version, spi_version=provider.spi_version,
            installed=True, entitled=entitled, feature_enabled=enabled,
            access_allowed=allowed, compatible=compatible, healthy=healthy,
            available=available, locked=not entitled or not allowed,
            unavailable_reason=reason,
        )

    @staticmethod
    def _validate(provider: ExtensionProviderV1) -> None:
        if not _KEY.fullmatch(getattr(provider, "key", "")):
            raise InvalidExtensionError("Extension key must be a namespaced lowercase identifier")
        if not getattr(provider, "version", ""):
            raise InvalidExtensionError("Extension version is required")
        if getattr(provider, "spi_version", None) != SPI_VERSION:
            raise InvalidExtensionError(f"Extension must implement {SPI_VERSION}")
        for attribute in ("entitlement", "feature_flag", "required_permission"):
            if not isinstance(getattr(provider, attribute, None), str):
                raise InvalidExtensionError(f"Extension {attribute} must be a string")

    @staticmethod
    def _validate_result(key: str, result: Any) -> None:
        if isinstance(result, (ProviderResultV1, TransferPricingOutputV1)):
            if result.provider_key != key:
                raise InvalidExtensionError("Extension result provider_key does not match registration")
            return
        if isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
            if all(isinstance(item, ProviderResultV1) and item.provider_key == key for item in result):
                return
        raise InvalidExtensionError("Extension returned an unsupported or unvalidated result")


extension_registry = ExtensionRegistry()


__all__ = [name for name in globals() if not name.startswith("_")]
