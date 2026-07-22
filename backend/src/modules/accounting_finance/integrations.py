"""Versioned, model-independent accounting extension contracts.

The objects in this module are the public boundary used by free and paid
modules.  They deliberately contain no Django models: callers can depend on
the contracts without acquiring permission to write accounting tables.
Registrations are explicit, exact-version, collision safe, and fail closed.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID


SPI_VERSION = "1.0"
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_NAMESPACE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_PROVIDER_KEY = re.compile(r"^[a-z][a-z0-9_]{1,99}$")
_SOURCE_MODULE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_CORRELATION = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_DIRECTION = frozenset({"debit", "credit"})


class AccountingIntegrationError(RuntimeError):
    """Base error with a stable code suitable for API translation."""

    code = "INTEGRATION_ERROR"


class CapabilityUnavailable(AccountingIntegrationError):
    """A required installed capability has not been registered."""

    code = "CAPABILITY_UNAVAILABLE"


class RegistrationConflict(AccountingIntegrationError):
    """A provider identity is already owned by another implementation."""

    code = "REGISTRATION_CONFLICT"


class SchemaVersionRejected(AccountingIntegrationError):
    """An integration used an unsupported contract version."""

    code = "SCHEMA_VERSION_UNSUPPORTED"


class InvalidProviderResult(AccountingIntegrationError):
    """A provider returned a value that violates its published contract."""

    code = "PROVIDER_RESULT_INVALID"


class ExtensionValidationError(AccountingIntegrationError, ValueError):
    """An extension DTO or namespaced value failed deterministic validation."""

    code = "EXTENSION_VALIDATION_ERROR"


def _uuid(value: object, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ExtensionValidationError(f"{field_name} must be a valid UUID.") from exc


def _bounded(value: object, field_name: str, maximum: int, *, blank: bool = False) -> str:
    candidate = str(value or "").strip()
    if (not candidate and not blank) or len(candidate) > maximum:
        qualifier = "a bounded string" if blank else "a bounded non-empty string"
        raise ExtensionValidationError(f"{field_name} must be {qualifier}.")
    return candidate


def _currency(value: object) -> str:
    candidate = str(value or "").strip().upper()
    if not _CURRENCY.fullmatch(candidate):
        raise ExtensionValidationError("currency must be a three-letter ISO-4217 code.")
    return candidate


def _decimal(value: object, field_name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, float):
        raise ExtensionValidationError(f"{field_name} must not be supplied as a float.")
    try:
        candidate = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ExtensionValidationError(f"{field_name} must be a decimal value.") from exc
    if not candidate.is_finite() or (positive and candidate <= 0):
        raise ExtensionValidationError(f"{field_name} must be a finite positive decimal.")
    return candidate


def _schema(value: object) -> str:
    candidate = str(value or "").strip()
    if candidate != SPI_VERSION:
        raise SchemaVersionRejected(f"Accounting integration schema {candidate!r} is unsupported.")
    return candidate


def _provider_key(value: object) -> str:
    candidate = str(value or "").strip()
    if not _PROVIDER_KEY.fullmatch(candidate):
        raise ExtensionValidationError("provider key must be a lowercase snake-case identifier.")
    return candidate


def _metadata(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ExtensionValidationError("metadata must be an object.")
    normalized: dict[str, object] = {}
    for raw_key, item in value.items():
        key = str(raw_key)
        if not _NAMESPACE.fullmatch(key):
            raise ExtensionValidationError("metadata keys must be namespaced lowercase identifiers.")
        if item is not None and not isinstance(item, (str, int, bool, Decimal, UUID, date)):
            raise ExtensionValidationError("metadata values must be scalar integration values.")
        normalized[key] = item
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class JournalLegV1:
    """One debit or credit leg in a source module's posting command."""

    account_id: UUID
    direction: Literal["debit", "credit"]
    amount: Decimal
    currency: str
    exchange_rate: Decimal = Decimal("1")
    description: str = ""
    cost_center: str = ""
    dimension_values: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "account_id", _uuid(self.account_id, "account_id"))
        direction = str(self.direction).strip().lower()
        if direction not in _DIRECTION:
            raise ExtensionValidationError("direction must be debit or credit.")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "amount", _decimal(self.amount, "amount", positive=True))
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "exchange_rate", _decimal(self.exchange_rate, "exchange_rate", positive=True))
        object.__setattr__(self, "description", _bounded(self.description, "description", 500, blank=True))
        object.__setattr__(self, "cost_center", _bounded(self.cost_center, "cost_center", 100, blank=True))
        if not isinstance(self.dimension_values, Mapping):
            raise ExtensionValidationError("dimension_values must be an object.")
        dimensions: dict[str, str] = {}
        for raw_key, raw_value in self.dimension_values.items():
            key = str(raw_key).strip()
            value = str(raw_value).strip()
            if not _NAMESPACE.fullmatch(key) or not value or len(value) > 255:
                raise ExtensionValidationError("dimension values require namespaced keys and bounded values.")
            dimensions[key] = value
        object.__setattr__(self, "dimension_values", MappingProxyType(dimensions))


@dataclass(frozen=True, slots=True)
class JournalPostingRequestV1:
    """Complete, idempotent request accepted by the accounting posting port."""

    schema_version: str
    tenant_id: UUID
    posting_date: date
    currency: str
    source_module: str
    entry_number: str
    source_reference: str
    idempotency_key: str
    correlation_id: str
    actor_id: str
    legs: tuple[JournalLegV1, ...]
    description: str = ""
    metadata: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "tenant_id", _uuid(self.tenant_id, "tenant_id"))
        if not isinstance(self.posting_date, date):
            raise ExtensionValidationError("posting_date must be a date.")
        object.__setattr__(self, "currency", _currency(self.currency))
        source_module = _bounded(self.source_module, "source_module", 100)
        if not _SOURCE_MODULE.fullmatch(source_module):
            raise ExtensionValidationError("source_module must be a lowercase namespaced identifier.")
        object.__setattr__(self, "source_module", source_module)
        object.__setattr__(self, "entry_number", _bounded(self.entry_number, "entry_number", 50))
        object.__setattr__(self, "source_reference", _bounded(self.source_reference, "source_reference", 255))
        object.__setattr__(self, "idempotency_key", _bounded(self.idempotency_key, "idempotency_key", 255))
        correlation_id = str(self.correlation_id or "").strip()
        if not _CORRELATION.fullmatch(correlation_id):
            raise ExtensionValidationError("correlation_id contains unsupported characters.")
        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "actor_id", _bounded(self.actor_id, "actor_id", 255))
        legs = tuple(self.legs)
        if len(legs) < 2 or not all(isinstance(leg, JournalLegV1) for leg in legs):
            raise ExtensionValidationError("legs must contain at least two JournalLegV1 values.")
        if any(leg.currency != self.currency for leg in legs):
            raise ExtensionValidationError("all journal legs must use the request currency.")
        debit = sum((leg.amount * leg.exchange_rate for leg in legs if leg.direction == "debit"), Decimal("0"))
        credit = sum((leg.amount * leg.exchange_rate for leg in legs if leg.direction == "credit"), Decimal("0"))
        if debit.quantize(Decimal("0.01")) != credit.quantize(Decimal("0.01")):
            raise ExtensionValidationError("journal legs must balance exactly in base currency.")
        object.__setattr__(self, "legs", legs)
        object.__setattr__(self, "description", _bounded(self.description, "description", 10_000, blank=True))
        object.__setattr__(self, "metadata", _metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class JournalPostingResultV1:
    schema_version: str
    journal_entry_id: UUID
    entry_number: str
    posted_at: str
    status: Literal["posted"] = "posted"

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "journal_entry_id", _uuid(self.journal_entry_id, "journal_entry_id"))
        object.__setattr__(self, "entry_number", _bounded(self.entry_number, "entry_number", 50))
        object.__setattr__(self, "posted_at", _bounded(self.posted_at, "posted_at", 64))
        if self.status != "posted":
            raise InvalidProviderResult("An accounting posting result must be posted.")


@dataclass(frozen=True, slots=True)
class PartyRecordV1:
    schema_version: str
    tenant_id: UUID
    party_id: UUID
    party_type: Literal["supplier", "customer"]
    is_active: bool
    credit_approved: bool = True
    available_credit: Decimal | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "tenant_id", _uuid(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "party_id", _uuid(self.party_id, "party_id"))
        if self.party_type not in {"supplier", "customer"}:
            raise ExtensionValidationError("party_type must be supplier or customer.")
        if not isinstance(self.is_active, bool) or not isinstance(self.credit_approved, bool):
            raise ExtensionValidationError("party activity and credit decisions must be booleans.")
        if self.available_credit is not None:
            credit = _decimal(self.available_credit, "available_credit")
            if credit < 0:
                raise ExtensionValidationError("available_credit cannot be negative.")
            object.__setattr__(self, "available_credit", credit)
        if self.currency is not None:
            object.__setattr__(self, "currency", _currency(self.currency))


@dataclass(frozen=True, slots=True)
class TaxCalculationResultV1:
    schema_version: str
    tax_amount: Decimal
    currency: str
    provenance: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        amount = _decimal(self.tax_amount, "tax_amount")
        if amount < 0:
            raise ExtensionValidationError("tax_amount cannot be negative.")
        object.__setattr__(self, "tax_amount", amount)
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "provenance", _bounded(self.provenance, "provenance", 255))


@dataclass(frozen=True, slots=True)
class PeriodCloseEvidenceV1:
    schema_version: str
    provider: str
    satisfied: bool
    evidence_reference: str
    reason_code: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "provider", _provider_key(self.provider))
        if not isinstance(self.satisfied, bool):
            raise ExtensionValidationError("satisfied must be a boolean.")
        object.__setattr__(
            self,
            "evidence_reference",
            _bounded(self.evidence_reference, "evidence_reference", 255, blank=not self.satisfied),
        )
        object.__setattr__(self, "reason_code", _bounded(self.reason_code, "reason_code", 100, blank=True))


@runtime_checkable
class AccountingPostingPortV1(Protocol):
    schema_version: str

    def post_journal(self, request: JournalPostingRequestV1) -> JournalPostingResultV1: ...


@runtime_checkable
class PartyDirectoryPortV1(Protocol):
    schema_version: str

    def resolve_party(
        self,
        tenant_id: UUID,
        party_id: UUID,
        *,
        party_type: Literal["supplier", "customer"],
        requested_amount: Decimal | None = None,
        currency: str | None = None,
    ) -> PartyRecordV1: ...


@runtime_checkable
class DimensionProviderV1(Protocol):
    schema_version: str
    namespace: str

    def validate(self, tenant_id: UUID, values: Mapping[str, str]) -> Mapping[str, str]: ...


@runtime_checkable
class TaxCalculationPortV1(Protocol):
    schema_version: str
    provider: str

    def calculate(self, tenant_id: UUID, request: Mapping[str, object]) -> TaxCalculationResultV1: ...


@runtime_checkable
class PeriodCloseEvidencePortV1(Protocol):
    schema_version: str
    provider: str

    def check(
        self,
        tenant_id: UUID,
        *,
        period_id: UUID,
        start_date: date,
        end_date: date,
    ) -> PeriodCloseEvidenceV1: ...


class AccountingExtensionRegistry:
    """Thread-safe registry that never substitutes an absent capability."""

    def __init__(self) -> None:
        self._posting: AccountingPostingPortV1 | None = None
        self._party: PartyDirectoryPortV1 | None = None
        self._dimensions: dict[str, DimensionProviderV1] = {}
        self._tax: dict[str, TaxCalculationPortV1] = {}
        self._period_evidence: dict[str, PeriodCloseEvidencePortV1] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _compatible(port: object) -> None:
        _schema(getattr(port, "schema_version", ""))

    @staticmethod
    def _single(existing: object | None, candidate: object, capability: str) -> object:
        if existing is None:
            return candidate
        if existing is candidate:
            return existing
        raise RegistrationConflict(f"{capability} is already registered.")

    def register_posting_port(self, port: AccountingPostingPortV1) -> None:
        self._compatible(port)
        if not callable(getattr(port, "post_journal", None)):
            raise TypeError("posting port must implement post_journal().")
        with self._lock:
            self._posting = self._single(self._posting, port, "accounting posting")  # type: ignore[assignment]

    def posting_port(self) -> AccountingPostingPortV1:
        with self._lock:
            if self._posting is None:
                raise CapabilityUnavailable("Accounting posting capability is unavailable.")
            return self._posting

    def register_party_directory(self, port: PartyDirectoryPortV1) -> None:
        self._compatible(port)
        if not callable(getattr(port, "resolve_party", None)):
            raise TypeError("party directory must implement resolve_party().")
        with self._lock:
            self._party = self._single(self._party, port, "party directory")  # type: ignore[assignment]

    def party_directory(self) -> PartyDirectoryPortV1:
        with self._lock:
            if self._party is None:
                raise CapabilityUnavailable("Required party directory capability is unavailable.")
            return self._party

    def has_party_directory(self) -> bool:
        with self._lock:
            return self._party is not None

    def resolve_party(
        self,
        tenant_id: UUID,
        party_id: UUID,
        *,
        party_type: Literal["supplier", "customer"],
        requested_amount: Decimal | None = None,
        currency: str | None = None,
    ) -> PartyRecordV1:
        tenant, identifier = _uuid(tenant_id, "tenant_id"), _uuid(party_id, "party_id")
        result = self.party_directory().resolve_party(
            tenant,
            identifier,
            party_type=party_type,
            requested_amount=requested_amount,
            currency=currency,
        )
        if not isinstance(result, PartyRecordV1):
            raise InvalidProviderResult("Party directory returned an invalid result type.")
        if result.tenant_id != tenant or result.party_id != identifier or result.party_type != party_type:
            raise InvalidProviderResult("Party directory result identity does not match the request.")
        if not result.is_active:
            raise ExtensionValidationError("The referenced party is inactive.")
        if party_type == "customer" and requested_amount is not None:
            requested = _decimal(requested_amount, "requested_amount")
            if not result.credit_approved:
                raise ExtensionValidationError("Customer credit is not approved.")
            if result.available_credit is not None and result.available_credit < requested:
                raise ExtensionValidationError("Customer credit is insufficient.")
            if currency and result.currency and result.currency != _currency(currency):
                raise InvalidProviderResult("Party credit currency does not match the request.")
        return result

    def register_dimension_provider(self, namespace: str, provider: DimensionProviderV1) -> None:
        key = _provider_key(namespace)
        self._compatible(provider)
        if getattr(provider, "namespace", None) != key or not callable(getattr(provider, "validate", None)):
            raise TypeError("dimension provider namespace and validate() contract are required.")
        with self._lock:
            existing = self._dimensions.get(key)
            self._dimensions[key] = self._single(existing, provider, f"dimension namespace {key!r}")  # type: ignore[assignment]

    def validate_dimensions(self, tenant_id: UUID, dimension_values: Mapping[str, str]) -> dict[str, str]:
        tenant = _uuid(tenant_id, "tenant_id")
        if not isinstance(dimension_values, Mapping):
            raise ExtensionValidationError("dimension_values must be an object.")
        grouped: dict[str, dict[str, str]] = {}
        for raw_key, raw_value in dimension_values.items():
            key, value = str(raw_key).strip(), str(raw_value).strip()
            if not _NAMESPACE.fullmatch(key) or not value or len(value) > 255:
                raise ExtensionValidationError("Dimension keys must be namespaced and values bounded.")
            grouped.setdefault(key.split(".", 1)[0], {})[key] = value

        normalized: dict[str, str] = {}
        with self._lock:
            providers = dict(self._dimensions)
        for namespace, values in grouped.items():
            provider = providers.get(namespace)
            if provider is None:
                raise CapabilityUnavailable(f"Dimension provider {namespace!r} is unavailable.")
            result = provider.validate(tenant, MappingProxyType(values))
            if not isinstance(result, Mapping) or set(result) != set(values):
                raise InvalidProviderResult("Dimension provider changed the declared dimension keys.")
            for key, value in result.items():
                canonical = str(value).strip()
                if not canonical or len(canonical) > 255:
                    raise InvalidProviderResult("Dimension provider returned an invalid value.")
                normalized[str(key)] = canonical
        return normalized

    def register_tax_calculator(self, provider: str, port: TaxCalculationPortV1) -> None:
        key = _provider_key(provider)
        self._compatible(port)
        if getattr(port, "provider", None) != key or not callable(getattr(port, "calculate", None)):
            raise TypeError("tax port provider and calculate() contract are required.")
        with self._lock:
            existing = self._tax.get(key)
            self._tax[key] = self._single(existing, port, f"tax provider {key!r}")  # type: ignore[assignment]

    def tax_calculator(self, provider: str) -> TaxCalculationPortV1:
        key = _provider_key(provider)
        with self._lock:
            try:
                return self._tax[key]
            except KeyError as exc:
                raise CapabilityUnavailable(f"Tax provider {key!r} is unavailable.") from exc

    def register_period_close_evidence(self, provider: str, port: PeriodCloseEvidencePortV1) -> None:
        key = _provider_key(provider)
        self._compatible(port)
        if getattr(port, "provider", None) != key or not callable(getattr(port, "check", None)):
            raise TypeError("period evidence provider and check() contract are required.")
        with self._lock:
            existing = self._period_evidence.get(key)
            self._period_evidence[key] = self._single(existing, port, f"period evidence provider {key!r}")  # type: ignore[assignment]

    def period_close_evidence(self) -> tuple[PeriodCloseEvidencePortV1, ...]:
        with self._lock:
            return tuple(self._period_evidence[key] for key in sorted(self._period_evidence))

    def circuit_states(self) -> dict[str, str]:
        """Return states only for explicitly configured external adapters."""

        with self._lock:
            configured: list[tuple[str, object]] = []
            if self._party is not None:
                configured.append(("party_directory", self._party))
            configured.extend((f"tax.{key}", value) for key, value in self._tax.items())
            configured.extend((f"period_close.{key}", value) for key, value in self._period_evidence.items())
        states: dict[str, str] = {}
        for name, provider in configured:
            state_reader = getattr(provider, "circuit_state", None)
            if callable(state_reader):
                state = str(state_reader()).strip().lower()
                if state not in {"closed", "open", "half_open"}:
                    raise InvalidProviderResult(f"Adapter {name!r} returned an invalid circuit state.")
                states[name] = state
        return states


extension_registry = AccountingExtensionRegistry()


class _ServicePostingPort:
    """Default local port; it delegates to the authoritative service lazily."""

    schema_version = SPI_VERSION

    @staticmethod
    def post_journal(request: JournalPostingRequestV1) -> JournalPostingResultV1:
        from .services import JournalEntryService

        result = JournalEntryService.post_from_source(
            request.tenant_id,
            actor_id=request.actor_id,
            request=request,
        )
        if not isinstance(result, JournalPostingResultV1):
            raise InvalidProviderResult("Accounting service returned an invalid posting result.")
        return result


extension_registry.register_posting_port(_ServicePostingPort())


class FixedAssetAccountingFacade:
    """Identity-preserving bridge for the published fixed-assets ABI."""

    @staticmethod
    def validate_fixed_asset_accounts(*, tenant_id: UUID, account_ids: Sequence[UUID], schema_version: str) -> bool:
        _schema(schema_version)
        if not account_ids:
            raise ExtensionValidationError("account_ids must not be empty.")
        from .services import AccountService

        AccountService.validate_posting_accounts(_uuid(tenant_id, "tenant_id"), tuple(_uuid(v, "account_id") for v in account_ids))
        return True

    @staticmethod
    def post_fixed_asset_journal(request: object) -> object:
        # Import at invocation time so accounting can be installed without the
        # optional fixed-assets module and to preserve its exact result class.
        from src.modules.fixed_assets.integrations import AccountingPostingRequest, AccountingPostingResult

        if not isinstance(request, AccountingPostingRequest):
            raise ExtensionValidationError("Expected fixed-assets AccountingPostingRequest.")
        _schema(request.schema_version)
        legs = tuple(
            JournalLegV1(
                account_id=leg.account_id,
                direction=leg.direction,
                amount=leg.amount,
                currency=leg.currency,
                cost_center=leg.cost_center,
            )
            for leg in request.legs
        )
        fixed_metadata = {
            key if str(key).startswith("fixed_assets.") else f"fixed_assets.{key}": value
            for key, value in request.metadata.items()
        }
        fixed_metadata.update(
            {
                "fixed_assets.asset_id": request.asset_id,
                "fixed_assets.depreciation_line_id": request.depreciation_line_id,
            }
        )
        posting_request = JournalPostingRequestV1(
            schema_version=SPI_VERSION,
            tenant_id=request.tenant_id,
            posting_date=request.posting_date,
            currency=request.currency,
            source_module="fixed_assets",
            entry_number=f"FA-{str(request.asset_id)[:8]}-{str(request.depreciation_line_id)[:8]}",
            source_reference=f"{request.asset_id}:{request.depreciation_line_id}",
            idempotency_key=request.idempotency_key,
            correlation_id=request.correlation_id,
            actor_id=request.actor_id,
            legs=legs,
            metadata=fixed_metadata,
        )
        result = extension_registry.posting_port().post_journal(posting_request)
        if not isinstance(result, JournalPostingResultV1):
            raise InvalidProviderResult("Accounting posting port returned an invalid result.")
        return AccountingPostingResult(
            schema_version=SPI_VERSION,
            journal_entry_id=result.journal_entry_id,
            posted_at=result.posted_at,
        )


__all__ = [
    "AccountingExtensionRegistry",
    "AccountingIntegrationError",
    "AccountingPostingPortV1",
    "CapabilityUnavailable",
    "DimensionProviderV1",
    "ExtensionValidationError",
    "FixedAssetAccountingFacade",
    "InvalidProviderResult",
    "JournalLegV1",
    "JournalPostingRequestV1",
    "JournalPostingResultV1",
    "PartyDirectoryPortV1",
    "PartyRecordV1",
    "PeriodCloseEvidencePortV1",
    "PeriodCloseEvidenceV1",
    "RegistrationConflict",
    "SPI_VERSION",
    "SchemaVersionRejected",
    "TaxCalculationPortV1",
    "TaxCalculationResultV1",
    "extension_registry",
]
