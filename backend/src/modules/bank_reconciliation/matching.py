"""Deterministic candidate matching and paid-provider extension registry."""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable
from uuid import UUID

MAX_CANDIDATES_PER_TRANSACTION = 50
_ONE = Decimal("1.0000")
_ZERO = Decimal("0.0000")


class CandidateProviderError(RuntimeError):
    """Base error for an unavailable or untrusted candidate provider."""


class CandidateProviderNotRegistered(CandidateProviderError, LookupError):
    pass


class InvalidCandidateOutput(CandidateProviderError, ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LedgerCandidate:
    """Immutable ledger-side evidence supplied by a tenant-validated gateway."""

    entry_id: UUID
    entry_type: str
    transaction_date: date
    amount: Decimal
    currency: str
    reference: str = ""
    description: str = ""
    counterparty_name: str = ""
    document_number: str = ""
    remaining_amount: Decimal | None = None
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        amount = _decimal(self.amount, "amount")
        if amount == 0:
            raise InvalidCandidateOutput("ledger candidate amount must not be zero")
        object.__setattr__(self, "amount", amount)
        if self.remaining_amount is not None:
            object.__setattr__(self, "remaining_amount", _decimal(self.remaining_amount, "remaining_amount"))
        if self.entry_type not in {"payment", "journal_line", "deposit", "other"}:
            raise InvalidCandidateOutput("ledger candidate type is invalid")
        currency = str(self.currency).upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise InvalidCandidateOutput("ledger candidate currency is invalid")
        object.__setattr__(self, "currency", currency)
        if not isinstance(self.evidence, Mapping):
            raise InvalidCandidateOutput("ledger candidate evidence must be an object")


@dataclass(frozen=True, slots=True)
class ScoreFactors:
    amount: Decimal
    reference: Decimal
    date: Decimal
    counterparty: Decimal

    def __post_init__(self) -> None:
        for name in ("amount", "reference", "date", "counterparty"):
            object.__setattr__(self, name, _score(getattr(self, name), name))

    def as_dict(self) -> dict[str, str]:
        return {name: f"{getattr(self, name):.4f}" for name in ("amount", "reference", "date", "counterparty")}


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    bank_transaction_id: UUID
    ledger_entry_id: UUID
    ledger_entry_type: str
    score: Decimal
    factors: ScoreFactors
    rule_id: UUID | None = None
    rule_name: str = "Core deterministic"
    provider_key: str = "core"
    provider_version: str = "1.0"
    bank_transaction: object | None = field(default=None, repr=False, compare=False)
    amount: Decimal = Decimal("0.0000")
    rule: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "score", _score(self.score, "score"))
        amount = _decimal(self.amount, "amount")
        if amount == 0:
            amount = Decimal("0.0000")
        object.__setattr__(self, "amount", amount)

    @property
    def candidate_key(self) -> str:
        return f"{self.provider_key}:{self.bank_transaction_id}:{self.ledger_entry_type}:{self.ledger_entry_id}"

    @property
    def explanation(self) -> dict[str, object]:
        return {
            "candidate_key": self.candidate_key,
            "provider": self.provider_key,
            "provider_version": self.provider_version,
            "rule": self.rule_name,
            "factors": self.factors.as_dict(),
            "score": f"{self.score:.4f}",
        }


@runtime_checkable
class CandidateProvider(Protocol):
    key: str
    version: str

    def generate(
        self,
        tenant_id: UUID,
        reconciliation: object,
        bank_transactions: Sequence[object],
        ledger_candidates: Sequence[LedgerCandidate | Mapping[str, object]],
    ) -> tuple[MatchCandidate, ...]: ...


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidCandidateOutput(f"{name} must be a finite decimal") from exc
    if not result.is_finite():
        raise InvalidCandidateOutput(f"{name} must be a finite decimal")
    return result.quantize(Decimal("0.0001"))


def _score(value: object, name: str) -> Decimal:
    result = _decimal(value, name)
    if result < 0 or result > 1:
        raise InvalidCandidateOutput(f"{name} must be between zero and one")
    return result


def normalize_reference(value: object) -> str:
    """Normalize a reference without locale-sensitive or fuzzy behavior."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def normalize_counterparty(value: object) -> str:
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper()).split())


def _value(item: object, key: str, default: object = None) -> object:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _as_ledger(value: LedgerCandidate | Mapping[str, object]) -> LedgerCandidate:
    if isinstance(value, LedgerCandidate):
        return value
    try:
        entry_id = UUID(str(value["entry_id"]))
        entry_type = str(value.get("entry_type", "other"))
        tx_date = value["transaction_date"]
        if not isinstance(tx_date, date):
            tx_date = date.fromisoformat(str(tx_date))
        return LedgerCandidate(
            entry_id=entry_id,
            entry_type=entry_type,
            transaction_date=tx_date,
            amount=_decimal(value["amount"], "amount"),
            remaining_amount=(
                _decimal(value["remaining_amount"], "remaining_amount")
                if value.get("remaining_amount") is not None
                else None
            ),
            currency=str(value["currency"]),
            reference=str(value.get("reference", "")),
            description=str(value.get("description", "")),
            counterparty_name=str(value.get("counterparty_name", "")),
            document_number=str(value.get("document_number", "")),
            evidence=value.get("evidence", {}) if isinstance(value.get("evidence", {}), Mapping) else {},
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidCandidateOutput("ledger candidate contract is invalid") from exc


def _rules(reconciliation: object, tenant_id: UUID) -> tuple[object, ...]:
    supplied = _value(reconciliation, "matching_rules", ())
    if hasattr(supplied, "all"):
        supplied = supplied.all()
    try:
        rules = tuple(rule for rule in supplied if bool(_value(rule, "is_active", True)))
    except TypeError:
        rules = ()
    if not rules and not isinstance(reconciliation, Mapping) and getattr(reconciliation, "pk", None):
        # Service callers pass a locked persisted session. Rules remain a core
        # module query and are explicitly restricted to the trusted tenant.
        from .models import MatchingRule

        rules = tuple(MatchingRule.objects.for_tenant(tenant_id).filter(is_active=True))
    return tuple(sorted(rules, key=lambda rule: (int(_value(rule, "priority", 65535)), str(_value(rule, "id", "")))))


class CoreDeterministicCandidateProvider:
    """Transparent scorer: amount 40%, reference 25%, date 20%, party 15%."""

    key = "core"
    version = "1.0"

    def generate(
        self,
        tenant_id: UUID,
        reconciliation: object,
        bank_transactions: Sequence[object],
        ledger_candidates: Sequence[LedgerCandidate | Mapping[str, object]],
    ) -> tuple[MatchCandidate, ...]:
        try:
            tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("tenant_id must be a UUID") from exc
        reconciliation_tenant = _value(reconciliation, "tenant_id")
        if reconciliation_tenant is not None and UUID(str(reconciliation_tenant)) != tenant_uuid:
            raise CandidateProviderError("reconciliation does not belong to the requested tenant")
        ledger = tuple(_as_ledger(item) for item in ledger_candidates)
        if len(ledger) > 100_000 or len(bank_transactions) > 100_000:
            raise CandidateProviderError("candidate input exceeds the configured bound")
        account = _value(reconciliation, "bank_account")
        account_currency = str(_value(account, "currency", _value(reconciliation, "currency", ""))).upper()
        rules = _rules(reconciliation, tenant_uuid)
        output: list[MatchCandidate] = []
        for transaction in bank_transactions:
            transaction_tenant = _value(transaction, "tenant_id")
            if transaction_tenant is not None and UUID(str(transaction_tenant)) != tenant_uuid:
                raise CandidateProviderError("bank transaction does not belong to the requested tenant")
            transaction_id = UUID(str(_value(transaction, "id")))
            transaction_amount = abs(_decimal(_value(transaction, "amount"), "amount"))
            transaction_date = _value(transaction, "transaction_date")
            if not isinstance(transaction_date, date):
                transaction_date = date.fromisoformat(str(transaction_date))
            transaction_reference = normalize_reference(_value(transaction, "reference_number", ""))
            transaction_party = normalize_counterparty(_value(transaction, "counterparty_name", ""))
            scored: list[MatchCandidate] = []
            for entry in ledger:
                if account_currency and entry.currency != account_currency:
                    continue
                remaining = abs(entry.remaining_amount if entry.remaining_amount is not None else entry.amount)
                tolerance = Decimal("0")
                date_window = 30
                minimum = Decimal("0")
                selected_rule: object | None = None
                for rule in rules:
                    configuration = _value(rule, "configuration", {})
                    if not isinstance(configuration, Mapping):
                        continue
                    tolerance = max(
                        tolerance,
                        abs(_decimal(configuration.get("amount_tolerance", 0), "amount_tolerance")),
                    )
                    date_window = min(365, max(0, int(configuration.get("date_window_days", date_window))))
                    minimum = max(minimum, _score(_value(rule, "minimum_score", 0), "minimum_score"))
                    selected_rule = selected_rule or rule
                difference = abs(transaction_amount - remaining)
                if difference == 0:
                    amount_factor = _ONE
                elif tolerance > 0 and difference <= tolerance:
                    amount_factor = max(_ZERO, _ONE - difference / tolerance).quantize(Decimal("0.0001"))
                else:
                    amount_factor = _ZERO
                entry_reference = normalize_reference(entry.reference or entry.document_number)
                reference_factor = _ONE if transaction_reference and transaction_reference == entry_reference else _ZERO
                distance = abs((transaction_date - entry.transaction_date).days)
                date_factor = (
                    max(_ZERO, _ONE - Decimal(distance) / Decimal(max(date_window, 1))).quantize(Decimal("0.0001"))
                    if distance <= date_window
                    else _ZERO
                )
                entry_party = normalize_counterparty(entry.counterparty_name)
                party_factor = _ONE if transaction_party and transaction_party == entry_party else _ZERO
                factors = ScoreFactors(amount_factor, reference_factor, date_factor, party_factor)
                score = (
                    factors.amount * Decimal("0.4000")
                    + factors.reference * Decimal("0.2500")
                    + factors.date * Decimal("0.2000")
                    + factors.counterparty * Decimal("0.1500")
                ).quantize(Decimal("0.0001"))
                if score <= 0 or score < minimum:
                    continue
                scored.append(
                    MatchCandidate(
                        bank_transaction_id=transaction_id,
                        ledger_entry_id=entry.entry_id,
                        ledger_entry_type=entry.entry_type,
                        score=score,
                        factors=factors,
                        rule_id=(UUID(str(_value(selected_rule, "id"))) if selected_rule is not None else None),
                        rule_name=str(_value(selected_rule, "name", "Core deterministic")),
                        bank_transaction=transaction,
                        amount=_decimal(_value(transaction, "amount"), "amount"),
                        rule=selected_rule,
                    )
                )
            scored.sort(key=lambda candidate: (-candidate.score, str(candidate.ledger_entry_id)))
            output.extend(scored[:MAX_CANDIDATES_PER_TRANSACTION])
        output.sort(
            key=lambda candidate: (
                str(candidate.bank_transaction_id),
                -candidate.score,
                str(candidate.ledger_entry_id),
            )
        )
        return tuple(output)


_provider_lock = threading.RLock()
_providers: dict[str, CandidateProvider] = {}


def register_candidate_provider(key: str, provider: CandidateProvider, *, replace: bool = False) -> CandidateProvider:
    normalized = str(key).strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", normalized):
        raise ValueError("candidate provider key is invalid")
    if not isinstance(provider, CandidateProvider):
        raise TypeError("provider must implement CandidateProvider")
    if provider.key != normalized:
        raise ValueError("candidate provider key does not match registration")
    with _provider_lock:
        if normalized in _providers and not replace:
            raise ValueError(f"Candidate provider {normalized!r} is already registered")
        _providers[normalized] = provider
    return provider


def unregister_candidate_provider(key: str) -> CandidateProvider | None:
    with _provider_lock:
        return _providers.pop(str(key).strip().lower(), None)


def get_candidate_provider(key: str = "core") -> CandidateProvider:
    normalized = str(key).strip().lower()
    with _provider_lock:
        try:
            return _providers[normalized]
        except KeyError as exc:
            raise CandidateProviderNotRegistered(f"No candidate provider is registered for {normalized!r}") from exc


def candidate_provider_registry_status() -> dict[str, object]:
    with _provider_lock:
        registered = tuple(sorted(_providers))
        versions = {key: str(_providers[key].version)[:20] for key in registered}
    return {"ready": "core" in registered, "registered": registered, "versions": versions}


register_candidate_provider("core", CoreDeterministicCandidateProvider())


__all__ = [
    "CandidateProvider",
    "CandidateProviderError",
    "CandidateProviderNotRegistered",
    "CoreDeterministicCandidateProvider",
    "InvalidCandidateOutput",
    "LedgerCandidate",
    "MAX_CANDIDATES_PER_TRANSACTION",
    "MatchCandidate",
    "ScoreFactors",
    "candidate_provider_registry_status",
    "get_candidate_provider",
    "normalize_counterparty",
    "normalize_reference",
    "register_candidate_provider",
    "unregister_candidate_provider",
]
