"""Fail-closed accounting and depreciation extension contracts.

The open-source fixed-assets register remains usable without accounting, but
posting never fabricates a journal identity.  Integrations must opt in through
this module's versioned contracts.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Protocol, Sequence
from uuid import UUID


class FixedAssetIntegrationError(RuntimeError):
    """Stable base error raised by fixed-assets integration boundaries."""

    code = "INTEGRATION_ERROR"


class CapabilityUnavailable(FixedAssetIntegrationError):
    """Raised when no governed accounting implementation is installed."""

    code = "CAPABILITY_UNAVAILABLE"


class AccountMappingError(FixedAssetIntegrationError):
    code = "ACCOUNT_MAPPING_INVALID"


class AccountingPeriodClosed(FixedAssetIntegrationError):
    code = "ACCOUNTING_PERIOD_CLOSED"


class AccountingPostingRejected(FixedAssetIntegrationError):
    code = "ACCOUNTING_POSTING_REJECTED"


@dataclass(frozen=True, slots=True)
class JournalLeg:
    account_id: UUID
    direction: str
    amount: Decimal
    currency: str
    cost_center: str = ""


@dataclass(frozen=True, slots=True)
class AccountingPostingRequest:
    schema_version: str
    tenant_id: UUID
    asset_id: UUID
    depreciation_line_id: UUID
    posting_date: date
    currency: str
    idempotency_key: str
    correlation_id: str
    actor_id: str
    legs: tuple[JournalLeg, ...]
    metadata: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class AccountingPostingResult:
    schema_version: str
    journal_entry_id: UUID
    posted_at: str


class AccountingPostingPort(Protocol):
    """Published boundary required by lifecycle and posting services."""

    schema_version: str

    def validate_accounts(self, tenant_id: UUID, account_ids: Sequence[UUID]) -> None: ...

    def post_journal(self, request: AccountingPostingRequest) -> AccountingPostingResult: ...


class DepreciationStrategy(Protocol):
    """Versioned extension boundary for deterministic schedule generation."""

    schema_version: str
    strategy_id: str

    def generate(self, assumptions: Mapping[str, object]) -> Sequence[Mapping[str, object]]: ...


class DefaultAccountingAdapter:
    """Resolve only a future published accounting facade; otherwise fail shut."""

    schema_version = "1.0"

    @staticmethod
    def _facade() -> object:
        try:
            from src.modules.accounting_finance import services as accounting_services
        except (ImportError, RuntimeError) as exc:
            raise CapabilityUnavailable("Accounting capability is unavailable.") from exc
        facade = getattr(accounting_services, "FixedAssetAccountingFacade", None)
        if facade is None:
            raise CapabilityUnavailable("Accounting capability is unavailable.")
        return facade

    def validate_accounts(self, tenant_id: UUID, account_ids: Sequence[UUID]) -> None:
        facade = self._facade()
        validator = getattr(facade, "validate_fixed_asset_accounts", None)
        if not callable(validator):
            raise CapabilityUnavailable("Accounting account validation is unavailable.")
        result = validator(tenant_id=tenant_id, account_ids=tuple(account_ids), schema_version=self.schema_version)
        if result is not True:
            raise AccountMappingError("Accounting account mapping was rejected.")

    def post_journal(self, request: AccountingPostingRequest) -> AccountingPostingResult:
        facade = self._facade()
        poster = getattr(facade, "post_fixed_asset_journal", None)
        if not callable(poster):
            raise CapabilityUnavailable("Accounting journal posting is unavailable.")
        result = poster(request)
        if not isinstance(result, AccountingPostingResult):
            raise AccountingPostingRejected("Accounting returned an invalid posting result.")
        return result


class FixedAssetExtensionRegistry:
    """Deterministic, explicit registry for strategies and event consumers."""

    def __init__(self) -> None:
        self._strategies: dict[str, DepreciationStrategy] = {}
        self._consumers: dict[str, object] = {}
        self._accounting: AccountingPostingPort = DefaultAccountingAdapter()
        self._lock = threading.RLock()

    def register_strategy(self, strategy: DepreciationStrategy) -> None:
        key = str(getattr(strategy, "strategy_id", "")).strip()
        if not key or getattr(strategy, "schema_version", None) != "1.0":
            raise ValueError("Depreciation strategies require an id and schema_version 1.0.")
        with self._lock:
            if key in self._strategies:
                raise ValueError(f"Depreciation strategy {key!r} is already registered.")
            self._strategies[key] = strategy

    def strategy(self, strategy_id: str) -> DepreciationStrategy:
        try:
            return self._strategies[strategy_id]
        except KeyError as exc:
            raise CapabilityUnavailable(f"Depreciation strategy {strategy_id!r} is unavailable.") from exc

    def register_event_consumer(self, provider: str, consumer: object) -> None:
        key = provider.strip()
        if not key or not callable(consumer):
            raise ValueError("Event consumers require a provider and callable.")
        with self._lock:
            if key in self._consumers:
                raise ValueError(f"Event consumer {key!r} is already registered.")
            self._consumers[key] = consumer

    def set_accounting_port(self, port: AccountingPostingPort) -> None:
        if getattr(port, "schema_version", None) != "1.0":
            raise ValueError("AccountingPostingPort schema_version must be 1.0.")
        with self._lock:
            self._accounting = port

    def accounting_port(self) -> AccountingPostingPort:
        with self._lock:
            return self._accounting


extension_registry = FixedAssetExtensionRegistry()


__all__ = [
    "AccountMappingError",
    "AccountingPeriodClosed",
    "AccountingPostingPort",
    "AccountingPostingRejected",
    "AccountingPostingRequest",
    "AccountingPostingResult",
    "CapabilityUnavailable",
    "DefaultAccountingAdapter",
    "DepreciationStrategy",
    "FixedAssetExtensionRegistry",
    "FixedAssetIntegrationError",
    "JournalLeg",
    "extension_registry",
]
