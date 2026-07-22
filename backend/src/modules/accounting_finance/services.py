"""Transactional accounting command and projection services.

The service layer is the only write authority for accounting aggregates.  It
contains no HTTP/DRF objects, accepts tenant identity first, and records every
financial transition with durable outbox evidence.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q, QuerySet, Sum
from django.utils import timezone

from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.middleware.correlation import get_correlation_id
from src.core.state_machine import StateMachineError

from .integrations import (
    FixedAssetAccountingFacade,
    JournalLegV1,
    JournalPostingRequestV1,
    JournalPostingResultV1,
    extension_registry,
)
from .models import (
    APInvoice,
    APInvoiceLine,
    ARInvoice,
    ARInvoiceLine,
    Account,
    JournalEntry,
    JournalLine,
    LEGACY_UNATTRIBUTED_ACTOR,
    Payment,
    PostingPeriod,
)
from .state_machines import (
    AP_INVOICE_MACHINE,
    AR_INVOICE_MACHINE,
    JOURNAL_ENTRY_MACHINE,
    PAYMENT_MACHINE,
    POSTING_PERIOD_MACHINE,
)

logger = logging.getLogger(__name__)
MONEY_QUANTUM = Decimal("0.01")
RATE_QUANTUM = Decimal("0.00000001")


class AccountingServiceError(ValidationError):
    """Public domain failure carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str, *, detail: object | None = None, http_status: int = 422) -> None:
        self.domain_code = code
        self.detail_payload = detail
        self.http_status = http_status
        super().__init__(message, code=code)


class StaleVersionError(AccountingServiceError):
    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__("STALE_VERSION", "The aggregate changed; reload before retrying.", http_status=409)


def _tenant(value: UUID | str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AccountingServiceError("INVALID_TENANT", "tenant_id must be a UUID.") from exc


def _identifier(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AccountingServiceError("VALIDATION_ERROR", f"{field} must be a UUID.") from exc


def _text(value: object, field: str, *, maximum: int = 255, blank: bool = False) -> str:
    result = str(value or "").strip()
    if (not result and not blank) or len(result) > maximum:
        raise AccountingServiceError("VALIDATION_ERROR", f"{field} must be a bounded non-empty string.")
    return result


def _currency(value: object) -> str:
    result = str(value or "").strip().upper()
    if len(result) != 3 or not result.isalpha():
        raise AccountingServiceError("VALIDATION_ERROR", "currency must be a three-letter ISO-4217 code.")
    return result


def _money(value: object) -> Decimal:
    try:
        return Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise AccountingServiceError("VALIDATION_ERROR", "A valid monetary amount is required.") from exc


def _rate(value: object) -> Decimal:
    try:
        result = Decimal(str(value)).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise AccountingServiceError("VALIDATION_ERROR", "A valid exchange rate is required.") from exc
    if result <= 0:
        raise AccountingServiceError("VALIDATION_ERROR", "exchange_rate must be positive.")
    return result


def _canonical(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (UUID, date, Decimal)):
        return str(value)
    return value


def _fingerprint(value: Mapping[str, object]) -> str:
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _correlation(identity: str) -> str:
    current = get_correlation_id().strip()
    return current[:64] if current else f"cmd-{hashlib.sha256(identity.encode()).hexdigest()[:40]}"


def _clean(instance: object) -> None:
    cleaner = getattr(instance, "full_clean", None)
    if callable(cleaner):
        cleaner()


def _version(instance: object, expected: int) -> None:
    actual = int(getattr(instance, "version"))
    if isinstance(expected, bool) or int(expected) < 1 or actual != int(expected):
        raise StaleVersionError(int(expected), actual)


def _event(
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    actor_id: str,
    payload: Mapping[str, object] | None = None,
) -> OutboxEvent:
    correlation_id = _correlation(f"{event_type}:{aggregate_id}")
    event = OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload={
            "schema_version": "1.0",
            "event_type": event_type,
            "tenant_id": str(tenant_id),
            "aggregate_id": str(aggregate_id),
            "actor_id": actor_id,
            "correlation_id": correlation_id,
            "data": _canonical(payload or {}),
        },
    )
    event.payload["event_id"] = str(event.id)
    event.save(update_fields=["payload", "updated_at"])
    return event


def _log(command: str, tenant_id: UUID, actor_id: str, aggregate: object, outcome: str) -> None:
    logger.info(
        "accounting_command",
        extra={
            "correlation_id": _correlation(command),
            "tenant_id": str(tenant_id),
            "actor_id": actor_id,
            "aggregate_type": type(aggregate).__name__,
            "aggregate_id": str(getattr(aggregate, "pk", "")),
            "command": command,
            "outcome": outcome,
        },
    )


def _not_found(resource: str) -> AccountingServiceError:
    return AccountingServiceError("RESOURCE_NOT_FOUND", f"{resource} was not found.", http_status=404)


def _idempotent_create(
    model: type[Any], tenant_id: UUID, key: str, fingerprint: str
) -> object | None:
    existing = model.objects.for_tenant(tenant_id).filter(creation_idempotency_key=key).first()
    if existing is None:
        return None
    if existing.creation_request_fingerprint != fingerprint:
        raise AccountingServiceError(
            "IDEMPOTENCY_CONFLICT", "Idempotency-Key was reused with a different request.", http_status=409
        )
    return existing


def _dimensions(tenant_id: UUID, values: object) -> dict[str, object]:
    if not isinstance(values, Mapping):
        raise AccountingServiceError("VALIDATION_ERROR", "dimension_values must be an object.")
    result = {str(key): str(item) for key, item in values.items()}
    return dict(extension_registry.validate_dimensions(tenant_id, result))


def _apply(machine: object, aggregate: object, command: str, tenant: UUID, key: str, actor: str, **metadata: object) -> Any:
    try:
        return machine.apply(  # type: ignore[attr-defined]
            aggregate,
            command,
            tenant_id=tenant,
            transition_key=_text(key, "transition_key"),
            context={"actor_id": actor, **metadata},
            metadata={"actor_id": actor, "correlation_id": _correlation(key), **metadata},
        )
    except StateMachineError as exc:
        raise AccountingServiceError(
            "ILLEGAL_TRANSITION", "The lifecycle command conflicts with the current state.", http_status=409
        ) from exc


@dataclass(frozen=True, slots=True)
class AccountNode:
    id: UUID
    code: str
    name: str
    account_type: str
    is_group: bool
    children: tuple["AccountNode", ...]


class AccountService:
    @staticmethod
    def create_account(
        tenant_id: UUID | str,
        *,
        actor_id: str | None = None,
        data: Mapping[str, object] | None = None,
        idempotency_key: str | None = None,
        **legacy_fields: object,
    ) -> Account:
        """Create an account through the canonical path or the legacy facade.

        The v2 contract supplies ``data``, ``actor_id`` and an idempotency key.
        The former keyword-field signature remains a thin compatibility facade;
        its deliberately named actor sentinel exposes unavailable legacy identity.
        """

        if data is None:
            if not legacy_fields:
                raise AccountingServiceError("VALIDATION_ERROR", "Account data is required.")
            data = legacy_fields
            actor_id = actor_id or LEGACY_UNATTRIBUTED_ACTOR
            idempotency_key = idempotency_key or f"legacy-service:{uuid4()}"
        elif legacy_fields:
            raise AccountingServiceError("VALIDATION_ERROR", "Use either data or legacy account fields, not both.")

        tenant, actor, key = _tenant(tenant_id), _text(actor_id, "actor_id"), _text(idempotency_key, "idempotency_key")
        values = dict(data)
        values.pop("tenant_id", None)
        values["currency"] = _currency(values.get("currency", "USD"))
        if not values.get("normal_balance"):
            values["normal_balance"] = "credit" if values.get("account_type") in {"liability", "equity", "revenue"} else "debit"
        parent_id = values.pop("parent_id", values.pop("parent_account_id", None))
        fingerprint = _fingerprint({**values, "parent_id": parent_id})
        with transaction.atomic():
            replay = _idempotent_create(Account, tenant, key, fingerprint)
            if replay is not None:
                return replay  # type: ignore[return-value]
            parent = None
            if parent_id:
                parent = Account.objects.for_tenant(tenant).filter(pk=_identifier(parent_id, "parent_id"), is_deleted=False).first()
                if parent is None:
                    raise AccountingServiceError("INVALID_PARENT", "Parent account was not found in this tenant.")
            account = Account(
                tenant_id=tenant,
                parent=parent,
                created_by=actor,
                updated_by=actor,
                creation_idempotency_key=key,
                creation_request_fingerprint=fingerprint,
                **values,
            )
            _clean(account)
            try:
                account.save()
            except IntegrityError as exc:
                raise AccountingServiceError("ACCOUNT_CODE_EXISTS", "An active account already uses this code.", http_status=409) from exc
            _log("account.create", tenant, actor, account, "succeeded")
            return account

    @staticmethod
    def get_account(tenant_id: UUID, account_id: UUID) -> Account:
        account = Account.objects.for_tenant(_tenant(tenant_id)).filter(pk=account_id, is_deleted=False).first()
        if account is None:
            raise _not_found("Account")
        return account

    @staticmethod
    def list_accounts(tenant_id: UUID, *, filters: Mapping[str, object] | None = None) -> QuerySet[Account]:
        queryset = Account.objects.for_tenant(_tenant(tenant_id)).filter(is_deleted=False).select_related("parent")
        for field in ("account_type", "parent_id", "is_group", "is_active"):
            if filters and filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        return queryset.order_by("code", "id")

    @staticmethod
    def update_account(
        tenant_id: UUID, account_id: UUID, *, actor_id: str, version: int, changes: Mapping[str, object]
    ) -> Account:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        allowed = {"code", "name", "parent_id", "is_group", "is_active", "currency", "allow_multi_currency", "cash_flow_category", "description", "account_type", "normal_balance"}
        unknown = set(changes) - allowed
        if unknown:
            raise AccountingServiceError("VALIDATION_ERROR", "Unsupported account fields.", detail=sorted(unknown))
        with transaction.atomic():
            account = Account.objects.for_tenant(tenant).select_for_update().filter(pk=account_id, is_deleted=False).first()
            if account is None:
                raise _not_found("Account")
            _version(account, version)
            for field, value in changes.items():
                if field == "parent_id":
                    parent = None
                    if value:
                        parent = Account.objects.for_tenant(tenant).filter(pk=value, is_deleted=False).first()
                        if parent is None:
                            raise AccountingServiceError("INVALID_PARENT", "Parent account was not found in this tenant.")
                    account.parent = parent
                else:
                    setattr(account, field, _currency(value) if field == "currency" else value)
            account.updated_by = actor
            account.version += 1
            _clean(account)
            account.save()
            return account

    @staticmethod
    def soft_delete_account(tenant_id: UUID, account_id: UUID, *, actor_id: str, reason: str) -> None:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        _text(reason, "reason", maximum=1000)
        with transaction.atomic():
            account = Account.objects.for_tenant(tenant).select_for_update().filter(pk=account_id, is_deleted=False).first()
            if account is None:
                raise _not_found("Account")
            if JournalLine.objects.for_tenant(tenant).filter(account=account).exists():
                raise AccountingServiceError("ACCOUNT_HAS_HISTORY", "Accounts with journal history must be deactivated.", http_status=409)
            account.is_deleted = True
            account.is_active = False
            account.deleted_at = timezone.now()
            account.deleted_by = actor
            account.updated_by = actor
            account.version += 1
            account.save(update_fields=["is_deleted", "is_active", "deleted_at", "deleted_by", "updated_by", "version", "updated_at"])

    @staticmethod
    def get_hierarchy(tenant_id: UUID, *, active_only: bool = True) -> list[AccountNode]:
        rows = list(AccountService.list_accounts(tenant_id, filters={"is_active": True} if active_only else {}))
        children: dict[UUID | None, list[Account]] = {}
        for row in rows:
            children.setdefault(row.parent_id, []).append(row)

        def build(row: Account, seen: frozenset[UUID]) -> AccountNode:
            if row.id in seen:
                raise AccountingServiceError("ACCOUNT_HIERARCHY_CYCLE", "Account hierarchy contains a cycle.")
            return AccountNode(
                row.id,
                row.code,
                row.name,
                row.account_type,
                row.is_group,
                tuple(build(child, seen | {row.id}) for child in children.get(row.id, [])),
            )

        return [build(root, frozenset()) for root in children.get(None, [])]

    @staticmethod
    def validate_posting_accounts(tenant_id: UUID, account_ids: Iterable[UUID]) -> None:
        tenant = _tenant(tenant_id)
        identifiers = {_identifier(value, "account_id") for value in account_ids}
        valid = set(
            Account.objects.for_tenant(tenant)
            .filter(id__in=identifiers, is_deleted=False, is_active=True, is_group=False)
            .values_list("id", flat=True)
        )
        if valid != identifiers:
            raise AccountingServiceError("INVALID_POSTING_ACCOUNT", "A posting account is missing, inactive, grouped, or foreign.")


class PostingPeriodService:
    @staticmethod
    def create_period(tenant_id: UUID, *, actor_id: str, data: Mapping[str, object], idempotency_key: str) -> PostingPeriod:
        tenant, actor, key = _tenant(tenant_id), _text(actor_id, "actor_id"), _text(idempotency_key, "idempotency_key")
        values = dict(data)
        values.pop("tenant_id", None)
        fingerprint = _fingerprint(values)
        with transaction.atomic():
            replay = _idempotent_create(PostingPeriod, tenant, key, fingerprint)
            if replay is not None:
                return replay  # type: ignore[return-value]
            start, end = values.get("start_date"), values.get("end_date")
            if not isinstance(start, date) or not isinstance(end, date) or start > end:
                raise AccountingServiceError("INVALID_PERIOD_RANGE", "start_date must not be after end_date.")
            if PostingPeriod.objects.for_tenant(tenant).select_for_update().filter(start_date__lte=end, end_date__gte=start).exists():
                raise AccountingServiceError("PERIOD_OVERLAP", "Posting periods may not overlap.", http_status=409)
            period = PostingPeriod(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                creation_idempotency_key=key,
                creation_request_fingerprint=fingerprint,
                **values,
            )
            _clean(period)
            period.save()
            return period

    @staticmethod
    def get_period(tenant_id: UUID, period_id: UUID) -> PostingPeriod:
        period = PostingPeriod.objects.for_tenant(_tenant(tenant_id)).filter(pk=period_id).first()
        if period is None:
            raise _not_found("Posting period")
        return period

    @staticmethod
    def list_periods(tenant_id: UUID, *, filters: Mapping[str, object] | None = None) -> QuerySet[PostingPeriod]:
        queryset = PostingPeriod.objects.for_tenant(_tenant(tenant_id))
        for field in ("status", "fiscal_year"):
            if filters and filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        return queryset.order_by("-start_date", "id")

    @staticmethod
    def update_period(tenant_id: UUID, period_id: UUID, *, actor_id: str, version: int, changes: Mapping[str, object]) -> PostingPeriod:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        if set(changes) - {"period_name", "start_date", "end_date", "fiscal_year"}:
            raise AccountingServiceError("VALIDATION_ERROR", "Unsupported posting-period fields.")
        with transaction.atomic():
            period = PostingPeriod.objects.for_tenant(tenant).select_for_update().filter(pk=period_id).first()
            if period is None:
                raise _not_found("Posting period")
            _version(period, version)
            if period.status != "open":
                raise AccountingServiceError("PERIOD_NOT_OPEN", "Only open periods may be edited.", http_status=409)
            for field, value in changes.items():
                setattr(period, field, value)
            if PostingPeriod.objects.for_tenant(tenant).exclude(pk=period.id).filter(start_date__lte=period.end_date, end_date__gte=period.start_date).exists():
                raise AccountingServiceError("PERIOD_OVERLAP", "Posting periods may not overlap.", http_status=409)
            period.updated_by = actor
            period.version += 1
            _clean(period)
            period.save()
            return period

    @staticmethod
    def close_period(tenant_id: UUID, period_id: UUID, *, actor_id: str, transition_key: str, reason: str) -> PostingPeriod:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        _text(reason, "reason", maximum=1000)
        with transaction.atomic():
            period = PostingPeriod.objects.for_tenant(tenant).select_for_update().filter(pk=period_id).first()
            if period is None:
                raise _not_found("Posting period")
            if JournalEntry.objects.for_tenant(tenant).filter(posting_period=period, status="draft", is_deleted=False).exists():
                raise AccountingServiceError("PERIOD_HAS_DRAFTS", "Draft journal entries block period close.", http_status=409)
            for evidence_port in extension_registry.period_close_evidence():
                evidence = evidence_port.check(
                    tenant,
                    period_id=period.id,
                    start_date=period.start_date,
                    end_date=period.end_date,
                )
                if not evidence.satisfied:
                    raise AccountingServiceError(
                        "PERIOD_CLOSE_EVIDENCE_BLOCKED",
                        "A configured period-close prerequisite is not satisfied.",
                        http_status=409,
                    )
            period = _apply(POSTING_PERIOD_MACHINE, period, "close", tenant, transition_key, actor, reason=reason)
            period.closed_at, period.closed_by, period.updated_by = timezone.now(), actor, actor
            period.version += 1
            period.save(update_fields=["closed_at", "closed_by", "updated_by", "version", "updated_at"])
            _event(tenant, "accounting.period.closed.v1", "posting_period", period.id, actor, {"status": period.status})
            return period

    @staticmethod
    def reopen_period(tenant_id: UUID, period_id: UUID, *, actor_id: str, transition_key: str, reason: str) -> PostingPeriod:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        _text(reason, "reason", maximum=1000)
        with transaction.atomic():
            period = PostingPeriod.objects.for_tenant(tenant).select_for_update().filter(pk=period_id).first()
            if period is None:
                raise _not_found("Posting period")
            if PostingPeriod.objects.for_tenant(tenant).filter(start_date__gt=period.start_date, status="locked").exists():
                raise AccountingServiceError("LATER_PERIOD_LOCKED", "A later locked period prevents reopening.", http_status=409)
            period = _apply(POSTING_PERIOD_MACHINE, period, "reopen", tenant, transition_key, actor, reason=reason)
            period.closed_at = None
            period.closed_by = None
            period.updated_by = actor
            period.version += 1
            period.save(update_fields=["closed_at", "closed_by", "updated_by", "version", "updated_at"])
            return period

    @staticmethod
    def lock_period(tenant_id: UUID, period_id: UUID, *, actor_id: str, transition_key: str, reason: str) -> PostingPeriod:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        _text(reason, "reason", maximum=1000)
        with transaction.atomic():
            period = PostingPeriod.objects.for_tenant(tenant).select_for_update().filter(pk=period_id).first()
            if period is None:
                raise _not_found("Posting period")
            period = _apply(POSTING_PERIOD_MACHINE, period, "lock", tenant, transition_key, actor, reason=reason)
            period.locked_at, period.locked_by, period.updated_by = timezone.now(), actor, actor
            period.version += 1
            period.save(update_fields=["locked_at", "locked_by", "updated_by", "version", "updated_at"])
            return period

    @staticmethod
    def resolve_open_period(tenant_id: UUID, posting_date: date) -> PostingPeriod:
        matches = PostingPeriod.objects.for_tenant(_tenant(tenant_id)).filter(
            start_date__lte=posting_date, end_date__gte=posting_date, status="open"
        )
        period = matches.first()
        if period is None:
            raise AccountingServiceError("POSTING_PERIOD_CLOSED", "No open posting period covers this date.", http_status=409)
        return period


def _line_values(tenant: UUID, payload: Mapping[str, object], entry_currency: str) -> dict[str, object]:
    account_id = _identifier(payload.get("account_id", payload.get("account")), "account_id")
    account = Account.objects.for_tenant(tenant).filter(pk=account_id, is_deleted=False).first()
    if account is None:
        raise AccountingServiceError("INVALID_POSTING_ACCOUNT", "Journal line account is not in this tenant.")
    debit, credit = _money(payload.get("debit_amount", 0)), _money(payload.get("credit_amount", 0))
    if (debit > 0) == (credit > 0):
        raise AccountingServiceError("LINE_AMOUNT_XOR", "Exactly one of debit or credit must be positive.")
    rate = _rate(payload.get("exchange_rate", 1))
    currency = _currency(payload.get("currency", entry_currency))
    return {
        "account": account,
        "debit_amount": debit,
        "credit_amount": credit,
        "currency": currency,
        "exchange_rate": rate,
        "base_debit_amount": _money(debit * rate),
        "base_credit_amount": _money(credit * rate),
        "description": str(payload.get("description", ""))[:500],
        "cost_center": str(payload.get("cost_center", ""))[:100],
        "dimension_values": _dimensions(tenant, payload.get("dimension_values", {})),
    }


class JournalEntryService:
    @staticmethod
    def create_draft(tenant_id: UUID, *, actor_id: str, payload: Mapping[str, object], idempotency_key: str) -> JournalEntry:
        tenant, actor, key = _tenant(tenant_id), _text(actor_id, "actor_id"), _text(idempotency_key, "idempotency_key")
        values = dict(payload)
        values.pop("tenant_id", None)
        lines = values.pop("lines", None)
        if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)) or len(lines) < 2:
            raise AccountingServiceError("JOURNAL_LINES_REQUIRED", "A journal draft requires at least two lines.")
        currency = _currency(values.get("currency", "USD"))
        values["currency"] = currency
        period_id = values.pop("posting_period_id", values.pop("posting_period", None))
        period = PostingPeriod.objects.for_tenant(tenant).filter(pk=period_id).first()
        if period is None:
            raise AccountingServiceError("INVALID_POSTING_PERIOD", "Posting period is not in this tenant.")
        fingerprint = _fingerprint({**values, "posting_period_id": period_id, "lines": list(lines)})
        with transaction.atomic():
            replay = _idempotent_create(JournalEntry, tenant, key, fingerprint)
            if replay is not None:
                return replay  # type: ignore[return-value]
            entry = JournalEntry(
                tenant_id=tenant,
                posting_period=period,
                created_by=actor,
                updated_by=actor,
                creation_idempotency_key=key,
                creation_request_fingerprint=fingerprint,
                **values,
            )
            _clean(entry)
            entry.save()
            for number, raw in enumerate(lines, 1):
                if not isinstance(raw, Mapping):
                    raise AccountingServiceError("VALIDATION_ERROR", "Each journal line must be an object.")
                line = JournalLine(tenant_id=tenant, journal_entry=entry, line_number=number, **_line_values(tenant, raw, currency))
                _clean(line)
                line.save()
            return entry

    @staticmethod
    def get_entry(tenant_id: UUID, entry_id: UUID) -> JournalEntry:
        entry = JournalEntry.objects.for_tenant(_tenant(tenant_id)).prefetch_related("lines__account").filter(pk=entry_id, is_deleted=False).first()
        if entry is None:
            raise _not_found("Journal entry")
        return entry

    @staticmethod
    def list_entries(tenant_id: UUID, *, filters: Mapping[str, object] | None = None) -> QuerySet[JournalEntry]:
        queryset = JournalEntry.objects.for_tenant(_tenant(tenant_id)).filter(is_deleted=False).select_related("posting_period")
        for field in ("status", "posting_period_id", "source_module"):
            if filters and filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        if filters and filters.get("date_from"):
            queryset = queryset.filter(posting_date__gte=filters["date_from"])
        if filters and filters.get("date_to"):
            queryset = queryset.filter(posting_date__lte=filters["date_to"])
        return queryset.order_by("-posting_date", "-entry_number", "id")

    @staticmethod
    def update_draft(tenant_id: UUID, entry_id: UUID, *, actor_id: str, version: int, payload: Mapping[str, object]) -> JournalEntry:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        values = dict(payload)
        values.pop("tenant_id", None)
        lines = values.pop("lines", None)
        allowed = {"posting_date", "posting_period_id", "reference", "description", "currency", "source_module", "source_reference"}
        if set(values) - allowed:
            raise AccountingServiceError("VALIDATION_ERROR", "Unsupported journal fields.")
        with transaction.atomic():
            entry = JournalEntry.objects.for_tenant(tenant).select_for_update().filter(pk=entry_id, is_deleted=False).first()
            if entry is None:
                raise _not_found("Journal entry")
            _version(entry, version)
            if entry.status != "draft":
                raise AccountingServiceError("POSTED_ENTRY_IMMUTABLE", "Only draft entries may be edited.", http_status=409)
            for field, value in values.items():
                if field == "posting_period_id":
                    period = PostingPeriod.objects.for_tenant(tenant).filter(pk=value).first()
                    if period is None:
                        raise AccountingServiceError("INVALID_POSTING_PERIOD", "Posting period is not in this tenant.")
                    entry.posting_period = period
                else:
                    setattr(entry, field, _currency(value) if field == "currency" else value)
            entry.updated_by, entry.version = actor, entry.version + 1
            _clean(entry)
            entry.save()
            if lines is not None:
                if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)) or len(lines) < 2:
                    raise AccountingServiceError("JOURNAL_LINES_REQUIRED", "A journal draft requires at least two lines.")
                entry.lines.all().delete()
                for number, raw in enumerate(lines, 1):
                    if not isinstance(raw, Mapping):
                        raise AccountingServiceError("VALIDATION_ERROR", "Each journal line must be an object.")
                    line = JournalLine(tenant_id=tenant, journal_entry=entry, line_number=number, **_line_values(tenant, raw, entry.currency))
                    _clean(line)
                    line.save()
            return entry

    @staticmethod
    def soft_delete_draft(tenant_id: UUID, entry_id: UUID, *, actor_id: str, reason: str) -> None:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        _text(reason, "reason", maximum=1000)
        with transaction.atomic():
            entry = JournalEntry.objects.for_tenant(tenant).select_for_update().filter(pk=entry_id, is_deleted=False).first()
            if entry is None:
                raise _not_found("Journal entry")
            if entry.status != "draft":
                raise AccountingServiceError("POSTED_ENTRY_IMMUTABLE", "Posted entries cannot be deleted.", http_status=409)
            entry.is_deleted, entry.deleted_at, entry.deleted_by = True, timezone.now(), actor
            entry.updated_by, entry.version = actor, entry.version + 1
            entry.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_by", "version", "updated_at"])

    @staticmethod
    def post_entry(tenant_id: UUID, entry_id: UUID, *, actor_id: str, transition_key: str) -> JournalEntry:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        with transaction.atomic():
            entry = JournalEntry.objects.for_tenant(tenant).select_for_update().filter(pk=entry_id, is_deleted=False).first()
            if entry is None:
                raise _not_found("Journal entry")
            if entry.status == "posted" and any(row.get("transition_key") == transition_key for row in entry.transition_history):
                return entry
            if entry.created_by == actor and not entry.source_module:
                raise AccountingServiceError("SOD_CREATOR_CANNOT_POST", "The journal creator cannot post the same entry.", http_status=403)
            period = PostingPeriod.objects.for_tenant(tenant).select_for_update().filter(pk=entry.posting_period_id).first()
            if period is None or period.status != "open" or not period.start_date <= entry.posting_date <= period.end_date:
                raise AccountingServiceError("POSTING_PERIOD_CLOSED", "The selected period is not open for this date.", http_status=409)
            lines = list(JournalLine.objects.for_tenant(tenant).select_related("account").filter(journal_entry=entry).order_by("line_number"))
            if len(lines) < 2:
                raise AccountingServiceError("JOURNAL_LINES_REQUIRED", "At least two lines are required to post.")
            AccountService.validate_posting_accounts(tenant, [line.account_id for line in lines])
            debit = sum((line.base_debit_amount for line in lines), Decimal("0.00"))
            credit = sum((line.base_credit_amount for line in lines), Decimal("0.00"))
            if debit <= 0 or debit != credit:
                raise AccountingServiceError("JOURNAL_UNBALANCED", "Base-currency debits and credits must balance exactly.")
            entry = _apply(JOURNAL_ENTRY_MACHINE, entry, "post", tenant, transition_key, actor)
            entry.debit_total, entry.credit_total = _money(debit), _money(credit)
            entry.posted_at, entry.posted_by, entry.updated_by = timezone.now(), actor, actor
            entry.version += 1
            entry.save(update_fields=["debit_total", "credit_total", "posted_at", "posted_by", "updated_by", "version", "updated_at"])
            _event(tenant, "accounting.journal_entry.posted.v1", "journal_entry", entry.id, actor, {"posting_date": entry.posting_date, "debit_total": entry.debit_total, "credit_total": entry.credit_total})
            _log("journal.post", tenant, actor, entry, "succeeded")
            return entry

    # Backward-compatible name delegates to the canonical tenant-first command.
    @staticmethod
    def post_journal_entry(journal_entry: JournalEntry, posted_by: str) -> JournalEntry:
        return JournalEntryService.post_entry(
            journal_entry.tenant_id,
            journal_entry.id,
            actor_id=posted_by,
            transition_key=f"legacy-post:{journal_entry.id}",
        )

    @staticmethod
    def reverse_entry(tenant_id: UUID, entry_id: UUID, *, actor_id: str, transition_key: str, posting_date: date, reason: str) -> JournalEntry:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        _text(reason, "reason", maximum=1000)
        with transaction.atomic():
            original = JournalEntry.objects.for_tenant(tenant).select_for_update().filter(pk=entry_id, is_deleted=False).first()
            if original is None:
                raise _not_found("Journal entry")
            existing = JournalEntry.objects.for_tenant(tenant).filter(reversed_entry=original, source_idempotency_key=transition_key).first()
            if existing is not None:
                return existing
            if original.status != "posted":
                raise AccountingServiceError("JOURNAL_NOT_POSTED", "Only posted entries can be reversed.", http_status=409)
            period = PostingPeriodService.resolve_open_period(tenant, posting_date)
            lines = list(JournalLine.objects.for_tenant(tenant).filter(journal_entry=original).order_by("line_number"))
            payload_lines = [
                {
                    "account_id": line.account_id,
                    "debit_amount": line.credit_amount,
                    "credit_amount": line.debit_amount,
                    "currency": line.currency,
                    "exchange_rate": line.exchange_rate,
                    "description": f"Reversal of {original.entry_number}",
                    "cost_center": line.cost_center,
                    "dimension_values": line.dimension_values,
                }
                for line in lines
            ]
            reversal = JournalEntryService.create_draft(
                tenant,
                actor_id=actor,
                idempotency_key=f"reversal-create:{transition_key}",
                payload={
                    "entry_number": f"REV-{original.entry_number}-{str(original.id)[:8]}",
                    "posting_date": posting_date,
                    "posting_period_id": period.id,
                    "reference": original.reference,
                    "description": reason,
                    "currency": original.currency,
                    "source_module": "accounting_finance",
                    "source_reference": str(original.id),
                    "source_idempotency_key": transition_key,
                    "reversed_entry": original,
                    "lines": payload_lines,
                },
            )
            reversal = JournalEntryService.post_entry(tenant, reversal.id, actor_id=actor, transition_key=f"reversal-post:{transition_key}")
            original = _apply(JOURNAL_ENTRY_MACHINE, original, "reverse", tenant, transition_key, actor, reason=reason)
            original.reversed_at, original.reversed_by, original.updated_by = timezone.now(), actor, actor
            original.version += 1
            original.save(update_fields=["reversed_at", "reversed_by", "updated_by", "version", "updated_at"])
            _event(tenant, "accounting.journal_entry.reversed.v1", "journal_entry", original.id, actor, {"reversal_entry_id": reversal.id})
            return reversal

    @staticmethod
    def enqueue_batch_import(tenant_id: UUID, *, actor_id: str, file_reference: str, idempotency_key: str) -> AsyncJob:
        reference = _text(file_reference, "file_reference", maximum=512)
        if reference.startswith(("http://", "https://")) or ".." in reference:
            raise AccountingServiceError("INVALID_FILE_REFERENCE", "Use an opaque managed file reference.")
        return enqueue(_tenant(tenant_id), actor_id, "accounting.journal_entries.import", {"file_reference": reference}, idempotency_key)

    @staticmethod
    def post_from_source(tenant_id: UUID, *, actor_id: str, request: JournalPostingRequestV1) -> JournalPostingResultV1:
        tenant = _tenant(tenant_id)
        if request.tenant_id != tenant:
            raise AccountingServiceError("TENANT_MISMATCH", "Posting request tenant does not match authority.", http_status=404)
        period = PostingPeriodService.resolve_open_period(tenant, request.posting_date)
        lines = [
            {
                "account_id": leg.account_id,
                "debit_amount": leg.amount if leg.direction == "debit" else Decimal("0"),
                "credit_amount": leg.amount if leg.direction == "credit" else Decimal("0"),
                "currency": leg.currency,
                "exchange_rate": leg.exchange_rate,
                "description": leg.description,
                "cost_center": leg.cost_center,
                "dimension_values": dict(leg.dimension_values),
            }
            for leg in request.legs
        ]
        entry = JournalEntryService.create_draft(
            tenant,
            actor_id=actor_id,
            idempotency_key=f"source-create:{request.source_module}:{request.idempotency_key}",
            payload={
                "entry_number": request.entry_number,
                "posting_date": request.posting_date,
                "posting_period_id": period.id,
                "reference": request.source_reference,
                "description": request.description,
                "currency": request.currency,
                "source_module": request.source_module,
                "source_reference": request.source_reference,
                "source_idempotency_key": request.idempotency_key,
                "lines": lines,
            },
        )
        entry = JournalEntryService.post_entry(tenant, entry.id, actor_id=actor_id, transition_key=f"source-post:{request.idempotency_key}")
        return JournalPostingResultV1("1.0", entry.id, entry.entry_number, entry.posted_at.isoformat() if entry.posted_at else "")


def _invoice_lines(
    tenant: UUID,
    invoice: APInvoice | ARInvoice,
    model: type[APInvoiceLine] | type[ARInvoiceLine],
    lines: Sequence[object],
) -> None:
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    for number, raw in enumerate(lines, 1):
        if not isinstance(raw, Mapping):
            raise AccountingServiceError("VALIDATION_ERROR", "Each invoice line must be an object.")
        account = Account.objects.for_tenant(tenant).filter(pk=raw.get("account_id", raw.get("account")), is_deleted=False).first()
        if account is None:
            raise AccountingServiceError("INVALID_POSTING_ACCOUNT", "Invoice line account is not in this tenant.")
        quantity = Decimal(str(raw.get("quantity", 1))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        unit_price, tax_amount = _money(raw.get("unit_price", 0)), _money(raw.get("tax_amount", 0))
        line_total = _money(quantity * unit_price)
        line = model(
            tenant_id=tenant,
            invoice=invoice,
            line_number=number,
            description=_text(raw.get("description"), "description", maximum=500),
            account=account,
            quantity=quantity,
            unit_price=unit_price,
            tax_amount=tax_amount,
            line_total=line_total,
            cost_center=str(raw.get("cost_center", ""))[:100],
            dimension_values=_dimensions(tenant, raw.get("dimension_values", {})),
        )
        _clean(line)
        line.save()
        subtotal += line_total
        tax_total += tax_amount
    invoice.amount, invoice.tax_amount, invoice.total_amount = _money(subtotal), _money(tax_total), _money(subtotal + tax_total)
    invoice.save(update_fields=["amount", "tax_amount", "total_amount", "updated_at"])


def _party(kind: str, tenant: UUID, party_id: UUID, amount: Decimal, currency: str) -> None:
    extension_registry.resolve_party(
        tenant,
        party_id,
        party_type=kind,
        requested_amount=amount if kind == "customer" else None,
        currency=currency,
    )


def _control_account(tenant: UUID, account_type: str, *, cash: bool = False) -> Account:
    queryset = Account.objects.for_tenant(tenant).filter(
        account_type=account_type, is_active=True, is_group=False, is_deleted=False
    )
    if cash:
        queryset = queryset.filter(cash_flow_category__isnull=False)
    account = queryset.order_by("code").first()
    if account is None:
        code = "CASH_ACCOUNT_UNAVAILABLE" if cash else "CONTROL_ACCOUNT_UNAVAILABLE"
        raise AccountingServiceError(code, "A configured posting account is required before this command can run.", http_status=503)
    return account


class _InvoiceBase:
    model: type[APInvoice] | type[ARInvoice]
    line_model: type[APInvoiceLine] | type[ARInvoiceLine]
    party_field: str
    kind: str

    @classmethod
    def _create(cls, tenant_id: UUID, actor_id: str, payload: Mapping[str, object], idempotency_key: str) -> APInvoice | ARInvoice:
        tenant, actor, key = _tenant(tenant_id), _text(actor_id, "actor_id"), _text(idempotency_key, "idempotency_key")
        values = dict(payload)
        values.pop("tenant_id", None)
        lines = values.pop("lines", None)
        if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)) or not lines:
            raise AccountingServiceError("INVOICE_LINES_REQUIRED", "New invoices require at least one real line.")
        party_id = _identifier(values.get(cls.party_field), cls.party_field)
        currency = _currency(values.get("currency", "USD"))
        provisional = sum((_money(Decimal(str(row.get("quantity", 1))) * Decimal(str(row.get("unit_price", 0)))) + _money(row.get("tax_amount", 0)) for row in lines if isinstance(row, Mapping)), Decimal("0"))
        _party(cls.kind, tenant, party_id, provisional, currency)
        values[cls.party_field] = party_id
        values["currency"] = currency
        values["exchange_rate"] = _rate(values.get("exchange_rate", 1))
        values.pop("amount", None)
        values.pop("tax_amount", None)
        values.pop("total_amount", None)
        values.pop("paid_amount", None)
        fingerprint = _fingerprint({**values, "lines": list(lines)})
        with transaction.atomic():
            replay = _idempotent_create(cls.model, tenant, key, fingerprint)
            if replay is not None:
                return replay  # type: ignore[return-value]
            invoice = cls.model(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                creation_idempotency_key=key,
                creation_request_fingerprint=fingerprint,
                amount=Decimal("0.00"),
                tax_amount=Decimal("0.00"),
                total_amount=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                **values,
            )
            _clean(invoice)
            invoice.save()
            _invoice_lines(tenant, invoice, cls.line_model, lines)
            event = "accounting.ap_invoice.created.v1" if cls.kind == "supplier" else "accounting.ar_invoice.created.v1"
            _event(tenant, event, cls.model.__name__.lower(), invoice.id, actor, {"total_amount": invoice.total_amount})
            return invoice

    @classmethod
    def _get(cls, tenant_id: UUID, invoice_id: UUID) -> APInvoice | ARInvoice:
        invoice = cls.model.objects.for_tenant(_tenant(tenant_id)).prefetch_related("lines__account", "payments").filter(pk=invoice_id, is_deleted=False).first()
        if invoice is None:
            raise _not_found("Invoice")
        return invoice

    @classmethod
    def _list(cls, tenant_id: UUID, filters: Mapping[str, object] | None) -> QuerySet[Any]:
        queryset = cls.model.objects.for_tenant(_tenant(tenant_id)).filter(is_deleted=False).select_related("journal_entry")
        for field in ("status", cls.party_field, "currency"):
            if filters and filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        return queryset.order_by("-invoice_date", "-invoice_number", "id")

    @classmethod
    def _update(cls, tenant_id: UUID, invoice_id: UUID, actor_id: str, version: int, payload: Mapping[str, object]) -> Any:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        values = dict(payload)
        values.pop("tenant_id", None)
        lines = values.pop("lines", None)
        allowed = {"invoice_number", cls.party_field, "invoice_date", "due_date", "currency", "exchange_rate", "description"}
        if set(values) - allowed:
            raise AccountingServiceError("VALIDATION_ERROR", "Unsupported invoice fields.")
        with transaction.atomic():
            invoice = cls.model.objects.for_tenant(tenant).select_for_update().filter(pk=invoice_id, is_deleted=False).first()
            if invoice is None:
                raise _not_found("Invoice")
            _version(invoice, version)
            if invoice.status != "draft" or invoice.legacy_without_lines:
                raise AccountingServiceError("INVOICE_IMMUTABLE", "Only reconciled draft invoices may be edited.", http_status=409)
            for field, value in values.items():
                setattr(invoice, field, _currency(value) if field == "currency" else (_rate(value) if field == "exchange_rate" else value))
            invoice.updated_by, invoice.version = actor, invoice.version + 1
            _clean(invoice)
            invoice.save()
            if lines is not None:
                if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)) or not lines:
                    raise AccountingServiceError("INVOICE_LINES_REQUIRED", "Invoice lines may not be empty.")
                invoice.lines.all().delete()
                _invoice_lines(tenant, invoice, cls.line_model, lines)
            _party(cls.kind, tenant, getattr(invoice, cls.party_field), invoice.total_amount, invoice.currency)
            return invoice

    @classmethod
    def _delete(cls, tenant_id: UUID, invoice_id: UUID, actor_id: str, reason: str) -> None:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        _text(reason, "reason", maximum=1000)
        with transaction.atomic():
            invoice = cls.model.objects.for_tenant(tenant).select_for_update().filter(pk=invoice_id, is_deleted=False).first()
            if invoice is None:
                raise _not_found("Invoice")
            if invoice.status != "draft":
                raise AccountingServiceError("INVOICE_IMMUTABLE", "Only draft invoices may be deleted.", http_status=409)
            invoice.is_deleted, invoice.deleted_at, invoice.deleted_by = True, timezone.now(), actor
            invoice.updated_by, invoice.version = actor, invoice.version + 1
            invoice.save(update_fields=["is_deleted", "deleted_at", "deleted_by", "updated_by", "version", "updated_at"])

    @classmethod
    def _aging(cls, tenant_id: UUID, as_of_date: date) -> dict[str, object]:
        tenant = _tenant(tenant_id)
        buckets = {"current": Decimal("0.00"), "1_30": Decimal("0.00"), "31_60": Decimal("0.00"), "61_90": Decimal("0.00"), "over_90": Decimal("0.00")}
        items: list[dict[str, object]] = []
        for invoice in cls.model.objects.for_tenant(tenant).filter(is_deleted=False, invoice_date__lte=as_of_date).exclude(status__in=("draft", "cancelled", "paid")):
            outstanding = _money(invoice.total_amount - invoice.paid_amount)
            days = (as_of_date - invoice.due_date).days
            bucket = "current" if days <= 0 else "1_30" if days <= 30 else "31_60" if days <= 60 else "61_90" if days <= 90 else "over_90"
            buckets[bucket] += outstanding
            items.append({"invoice_id": invoice.id, "invoice_number": invoice.invoice_number, "due_date": invoice.due_date, "days_overdue": max(0, days), "outstanding": outstanding, "bucket": bucket})
        return {"as_of_date": as_of_date, "currency": _single_currency(cls.model.objects.for_tenant(tenant).filter(is_deleted=False)), "generated_at": timezone.now(), "correlation_id": _correlation(f"aging:{tenant}:{as_of_date}"), "buckets": buckets, "items": items}


class APInvoiceService(_InvoiceBase):
    model, line_model, party_field, kind = APInvoice, APInvoiceLine, "supplier_id", "supplier"

    create_invoice = staticmethod(lambda tenant_id, *, actor_id, payload, idempotency_key: APInvoiceService._create(tenant_id, actor_id, payload, idempotency_key))
    get_invoice = staticmethod(lambda tenant_id, invoice_id: APInvoiceService._get(tenant_id, invoice_id))
    list_invoices = staticmethod(lambda tenant_id, *, filters=None: APInvoiceService._list(tenant_id, filters))
    update_draft = staticmethod(lambda tenant_id, invoice_id, *, actor_id, version, payload: APInvoiceService._update(tenant_id, invoice_id, actor_id, version, payload))
    soft_delete_draft = staticmethod(lambda tenant_id, invoice_id, *, actor_id, reason: APInvoiceService._delete(tenant_id, invoice_id, actor_id, reason))

    @staticmethod
    def _transition(tenant_id: UUID, invoice_id: UUID, actor_id: str, key: str, command: str, **metadata: object) -> APInvoice:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        with transaction.atomic():
            invoice = APInvoice.objects.for_tenant(tenant).select_for_update().filter(pk=invoice_id, is_deleted=False).first()
            if invoice is None:
                raise _not_found("AP invoice")
            if command in {"approve", "post"} and invoice.created_by == actor:
                raise AccountingServiceError("SOD_CREATOR_CONFLICT", "The invoice creator cannot approve or post it.", http_status=403)
            if command == "post" and invoice.approved_by == actor:
                raise AccountingServiceError("SOD_APPROVER_POSTER_CONFLICT", "The same actor cannot approve and post this invoice.", http_status=403)
            invoice = _apply(AP_INVOICE_MACHINE, invoice, command, tenant, key, actor, **metadata)
            now = timezone.now()
            if command == "approve":
                invoice.approved_at, invoice.approved_by = now, actor
                _event(tenant, "accounting.ap_invoice.approved.v1", "ap_invoice", invoice.id, actor, {"status": invoice.status})
            elif command == "post":
                invoice.posted_at, invoice.posted_by = now, actor
            elif command == "cancel":
                invoice.cancelled_at, invoice.cancelled_by = now, actor
            invoice.updated_by, invoice.version = actor, invoice.version + 1
            invoice.save()
            return invoice

    @staticmethod
    def submit(tenant_id: UUID, invoice_id: UUID, *, actor_id: str, transition_key: str) -> APInvoice:
        return APInvoiceService._transition(tenant_id, invoice_id, actor_id, transition_key, "submit")

    @staticmethod
    def approve(tenant_id: UUID, invoice_id: UUID, *, actor_id: str, transition_key: str, comments: str = "") -> APInvoice:
        return APInvoiceService._transition(tenant_id, invoice_id, actor_id, transition_key, "approve", comments=comments[:1000])

    @staticmethod
    def reject(tenant_id: UUID, invoice_id: UUID, *, actor_id: str, transition_key: str, reason: str) -> APInvoice:
        return APInvoiceService._transition(tenant_id, invoice_id, actor_id, transition_key, "reject", reason=_text(reason, "reason", maximum=1000))

    @staticmethod
    def post_to_gl(tenant_id: UUID, invoice_id: UUID, *, actor_id: str, transition_key: str) -> APInvoice:
        tenant = _tenant(tenant_id)
        with transaction.atomic():
            invoice = APInvoice.objects.for_tenant(tenant).select_for_update().prefetch_related("lines").filter(pk=invoice_id, is_deleted=False).first()
            if invoice is None:
                raise _not_found("AP invoice")
            control = _control_account(tenant, "liability")
            period = PostingPeriodService.resolve_open_period(tenant, invoice.invoice_date)
            lines = [{"account_id": line.account_id, "debit_amount": line.line_total + line.tax_amount, "credit_amount": 0, "currency": invoice.currency, "exchange_rate": invoice.exchange_rate, "description": line.description, "cost_center": line.cost_center, "dimension_values": line.dimension_values} for line in invoice.lines.all()]
            lines.append({"account_id": control.id, "debit_amount": 0, "credit_amount": invoice.total_amount, "currency": invoice.currency, "exchange_rate": invoice.exchange_rate, "description": "Accounts payable control"})
            entry = JournalEntryService.create_draft(tenant, actor_id=actor_id, idempotency_key=f"ap-gl-create:{transition_key}", payload={"entry_number": f"AP-{invoice.invoice_number}-{str(invoice.id)[:8]}", "posting_date": invoice.invoice_date, "posting_period_id": period.id, "reference": invoice.invoice_number, "description": "AP invoice posting", "currency": invoice.currency, "source_module": "accounting_finance.ap", "source_reference": str(invoice.id), "source_idempotency_key": transition_key, "lines": lines})
            entry = JournalEntryService.post_entry(tenant, entry.id, actor_id=actor_id, transition_key=f"ap-gl-post:{transition_key}")
            invoice = APInvoiceService._transition(tenant, invoice.id, actor_id, transition_key, "post")
            invoice.journal_entry = entry
            invoice.save(update_fields=["journal_entry", "updated_at"])
            _event(tenant, "accounting.ap_invoice.posted.v1", "ap_invoice", invoice.id, actor_id, {"journal_entry_id": entry.id})
            return invoice

    @staticmethod
    def cancel(tenant_id: UUID, invoice_id: UUID, *, actor_id: str, transition_key: str, reason: str) -> APInvoice:
        return APInvoiceService._transition(tenant_id, invoice_id, actor_id, transition_key, "cancel", reason=_text(reason, "reason", maximum=1000))

    @staticmethod
    def aging(tenant_id: UUID, *, as_of_date: date) -> dict[str, object]:
        return APInvoiceService._aging(tenant_id, as_of_date)


class ARInvoiceService(_InvoiceBase):
    model, line_model, party_field, kind = ARInvoice, ARInvoiceLine, "customer_id", "customer"

    create_invoice = staticmethod(lambda tenant_id, *, actor_id, payload, idempotency_key: ARInvoiceService._create(tenant_id, actor_id, payload, idempotency_key))
    get_invoice = staticmethod(lambda tenant_id, invoice_id: ARInvoiceService._get(tenant_id, invoice_id))
    list_invoices = staticmethod(lambda tenant_id, *, filters=None: ARInvoiceService._list(tenant_id, filters))
    update_draft = staticmethod(lambda tenant_id, invoice_id, *, actor_id, version, payload: ARInvoiceService._update(tenant_id, invoice_id, actor_id, version, payload))
    soft_delete_draft = staticmethod(lambda tenant_id, invoice_id, *, actor_id, reason: ARInvoiceService._delete(tenant_id, invoice_id, actor_id, reason))

    @staticmethod
    def post_to_gl(tenant_id: UUID, invoice_id: UUID, *, actor_id: str, transition_key: str) -> ARInvoice:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        with transaction.atomic():
            invoice = ARInvoice.objects.for_tenant(tenant).select_for_update().prefetch_related("lines").filter(pk=invoice_id, is_deleted=False).first()
            if invoice is None:
                raise _not_found("AR invoice")
            control = _control_account(tenant, "asset")
            period = PostingPeriodService.resolve_open_period(tenant, invoice.invoice_date)
            lines = [{"account_id": control.id, "debit_amount": invoice.total_amount, "credit_amount": 0, "currency": invoice.currency, "exchange_rate": invoice.exchange_rate, "description": "Accounts receivable control"}]
            lines.extend({"account_id": line.account_id, "debit_amount": 0, "credit_amount": line.line_total + line.tax_amount, "currency": invoice.currency, "exchange_rate": invoice.exchange_rate, "description": line.description, "cost_center": line.cost_center, "dimension_values": line.dimension_values} for line in invoice.lines.all())
            entry = JournalEntryService.create_draft(tenant, actor_id=actor, idempotency_key=f"ar-gl-create:{transition_key}", payload={"entry_number": f"AR-{invoice.invoice_number}-{str(invoice.id)[:8]}", "posting_date": invoice.invoice_date, "posting_period_id": period.id, "reference": invoice.invoice_number, "description": "AR invoice posting", "currency": invoice.currency, "source_module": "accounting_finance.ar", "source_reference": str(invoice.id), "source_idempotency_key": transition_key, "lines": lines})
            entry = JournalEntryService.post_entry(tenant, entry.id, actor_id=actor, transition_key=f"ar-gl-post:{transition_key}")
            invoice = _apply(AR_INVOICE_MACHINE, invoice, "post", tenant, transition_key, actor)
            invoice.posted_at, invoice.posted_by, invoice.journal_entry = timezone.now(), actor, entry
            invoice.updated_by, invoice.version = actor, invoice.version + 1
            invoice.save()
            _event(tenant, "accounting.ar_invoice.posted.v1", "ar_invoice", invoice.id, actor, {"journal_entry_id": entry.id})
            return invoice

    @staticmethod
    def cancel(tenant_id: UUID, invoice_id: UUID, *, actor_id: str, transition_key: str, reason: str) -> ARInvoice:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        with transaction.atomic():
            invoice = ARInvoice.objects.for_tenant(tenant).select_for_update().filter(pk=invoice_id, is_deleted=False).first()
            if invoice is None:
                raise _not_found("AR invoice")
            invoice = _apply(AR_INVOICE_MACHINE, invoice, "cancel", tenant, transition_key, actor, reason=_text(reason, "reason", maximum=1000))
            invoice.cancelled_at, invoice.cancelled_by = timezone.now(), actor
            invoice.updated_by, invoice.version = actor, invoice.version + 1
            invoice.save()
            return invoice

    @staticmethod
    def mark_overdue(tenant_id: UUID, *, as_of_date: date, actor_id: str) -> int:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        count = 0
        for invoice in ARInvoice.objects.for_tenant(tenant).filter(status__in=("posted", "partially_paid"), due_date__lt=as_of_date, is_deleted=False):
            _apply(AR_INVOICE_MACHINE, invoice, "mark_overdue", tenant, f"overdue:{as_of_date}:{invoice.id}", actor)
            count += 1
        return count

    @staticmethod
    def aging(tenant_id: UUID, *, as_of_date: date) -> dict[str, object]:
        return ARInvoiceService._aging(tenant_id, as_of_date)


def _recompute_invoice(invoice: APInvoice | ARInvoice, tenant: UUID, actor: str, transition_key: str) -> None:
    total = Payment.objects.for_tenant(tenant).filter(
        Q(ap_invoice_id=invoice.id) | Q(ar_invoice_id=invoice.id), status="recorded"
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    invoice.paid_amount = _money(total)
    command = "record_full_payment" if invoice.paid_amount == invoice.total_amount else "record_partial_payment"
    machine = AP_INVOICE_MACHINE if isinstance(invoice, APInvoice) else AR_INVOICE_MACHINE
    if invoice.paid_amount > 0 and invoice.status not in ("paid", "cancelled"):
        invoice = _apply(machine, invoice, command, tenant, transition_key, actor)
    invoice.updated_by, invoice.version = actor, invoice.version + 1
    invoice.save(update_fields=["paid_amount", "updated_by", "version", "updated_at"])


class PaymentService:
    @staticmethod
    def record_payment(tenant_id: UUID, *, actor_id: str, payload: Mapping[str, object], idempotency_key: str) -> Payment:
        tenant, actor, key = _tenant(tenant_id), _text(actor_id, "actor_id"), _text(idempotency_key, "idempotency_key")
        values = dict(payload)
        values.pop("tenant_id", None)
        amount = _money(values.get("amount"))
        if amount <= 0:
            raise AccountingServiceError("INVALID_PAYMENT_AMOUNT", "Payment amount must be positive.")
        ap_id, ar_id = values.pop("ap_invoice_id", values.pop("ap_invoice", None)), values.pop("ar_invoice_id", values.pop("ar_invoice", None))
        if bool(ap_id) == bool(ar_id):
            raise AccountingServiceError("PAYMENT_INVOICE_XOR", "Exactly one AP or AR invoice is required.")
        fingerprint = _fingerprint({**values, "amount": amount, "ap_invoice_id": ap_id, "ar_invoice_id": ar_id})
        with transaction.atomic():
            existing = Payment.objects.for_tenant(tenant).filter(idempotency_key=key).first()
            if existing:
                if existing.request_fingerprint != fingerprint:
                    raise AccountingServiceError("IDEMPOTENCY_CONFLICT", "Idempotency-Key was reused with a different payment.", http_status=409)
                return existing
            model = APInvoice if ap_id else ARInvoice
            invoice = model.objects.for_tenant(tenant).select_for_update().filter(pk=ap_id or ar_id, is_deleted=False).first()
            if invoice is None:
                raise _not_found("Invoice")
            if invoice.status not in ("posted", "partially_paid", "overdue"):
                raise AccountingServiceError("INVOICE_NOT_PAYABLE", "The invoice is not in a payable state.", http_status=409)
            if isinstance(invoice, APInvoice) and invoice.created_by == actor:
                raise AccountingServiceError("SOD_CREATOR_PAYMENT_CONFLICT", "The AP creator cannot record its payment.", http_status=403)
            currency = _currency(values.get("currency", invoice.currency))
            payment_date = values.get("payment_date")
            if currency != invoice.currency or not isinstance(payment_date, date) or payment_date < invoice.invoice_date:
                raise AccountingServiceError("PAYMENT_INVOICE_MISMATCH", "Payment currency/date does not match the invoice.")
            paid = Payment.objects.for_tenant(tenant).filter(Q(ap_invoice=invoice) | Q(ar_invoice=invoice), status="recorded").aggregate(total=Sum("amount"))["total"] or Decimal("0")
            if _money(paid + amount) > invoice.total_amount:
                raise AccountingServiceError("OVERPAYMENT", "Payment exceeds the remaining invoice balance.", http_status=409)
            payment = Payment(
                tenant_id=tenant,
                created_by=actor,
                amount=amount,
                ap_invoice=invoice if isinstance(invoice, APInvoice) else None,
                ar_invoice=invoice if isinstance(invoice, ARInvoice) else None,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                currency=currency,
                **{field: value for field, value in values.items() if field not in {"amount", "currency"}},
            )
            _clean(payment)
            payment.save()
            cash = _control_account(tenant, "asset", cash=True)
            control = _control_account(tenant, "liability" if isinstance(invoice, APInvoice) else "asset")
            period = PostingPeriodService.resolve_open_period(tenant, payment.payment_date)
            debit, credit = (control, cash) if isinstance(invoice, APInvoice) else (cash, control)
            JournalEntryService.post_from_source(
                tenant,
                actor_id=actor,
                request=JournalPostingRequestV1(
                    schema_version="1.0",
                    tenant_id=tenant,
                    source_module="accounting_finance.payment",
                    source_reference=str(payment.id),
                    idempotency_key=key,
                    entry_number=f"PAY-{str(payment.id)[:12]}",
                    posting_date=payment.payment_date,
                    currency=payment.currency,
                    description="Payment posting",
                    legs=(JournalLegV1(debit.id, "debit", amount, payment.currency), JournalLegV1(credit.id, "credit", amount, payment.currency)),
                    metadata={"accounting_finance.payment_id": str(payment.id), "accounting_finance.period_id": str(period.id)},
                    correlation_id=_correlation(key),
                    actor_id=actor,
                ),
            )
            _recompute_invoice(invoice, tenant, actor, f"payment:{payment.id}")
            _event(tenant, "accounting.payment.recorded.v1", "payment", payment.id, actor, {"invoice_id": invoice.id, "amount": amount})
            return payment

    @staticmethod
    def get_payment(tenant_id: UUID, payment_id: UUID) -> Payment:
        payment = Payment.objects.for_tenant(_tenant(tenant_id)).select_related("ap_invoice", "ar_invoice").filter(pk=payment_id).first()
        if payment is None:
            raise _not_found("Payment")
        return payment

    @staticmethod
    def list_payments(tenant_id: UUID, *, filters: Mapping[str, object] | None = None) -> QuerySet[Payment]:
        queryset = Payment.objects.for_tenant(_tenant(tenant_id)).select_related("ap_invoice", "ar_invoice")
        for field in ("ap_invoice_id", "ar_invoice_id", "payment_method", "status"):
            if filters and filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        return queryset.order_by("-payment_date", "-created_at", "id")

    @staticmethod
    def update_reference(tenant_id: UUID, payment_id: UUID, *, actor_id: str, description: str, reference_number: str) -> Payment:
        tenant = _tenant(tenant_id)
        with transaction.atomic():
            payment = Payment.objects.for_tenant(tenant).select_for_update().filter(pk=payment_id).first()
            if payment is None:
                raise _not_found("Payment")
            if payment.status != "recorded":
                raise AccountingServiceError("VOIDED_PAYMENT_IMMUTABLE", "Voided payments cannot be edited.", http_status=409)
            payment.description, payment.reference_number = str(description)[:10000], str(reference_number)[:100]
            payment.save(update_fields=["description", "reference_number", "updated_at"])
            return payment

    @staticmethod
    def void_payment(tenant_id: UUID, payment_id: UUID, *, actor_id: str, transition_key: str, reason: str) -> Payment:
        tenant, actor = _tenant(tenant_id), _text(actor_id, "actor_id")
        with transaction.atomic():
            payment = Payment.objects.for_tenant(tenant).select_for_update().filter(pk=payment_id).first()
            if payment is None:
                raise _not_found("Payment")
            invoice = payment.ap_invoice or payment.ar_invoice
            invoice = type(invoice).objects.for_tenant(tenant).select_for_update().get(pk=invoice.pk)
            payment = _apply(PAYMENT_MACHINE, payment, "void", tenant, transition_key, actor, reason=_text(reason, "reason", maximum=1000))
            payment.voided_at, payment.voided_by, payment.void_reason = timezone.now(), actor, reason
            payment.save(update_fields=["voided_at", "voided_by", "void_reason", "updated_at"])
            original = JournalEntry.objects.for_tenant(tenant).filter(source_module="accounting_finance.payment", source_reference=str(payment.id), status="posted").first()
            if original is None:
                raise AccountingServiceError("PAYMENT_LEDGER_MISSING", "The payment journal could not be located.", http_status=503)
            JournalEntryService.reverse_entry(tenant, original.id, actor_id=actor, transition_key=f"payment-void:{transition_key}", posting_date=payment.payment_date, reason=reason)
            total = Payment.objects.for_tenant(tenant).filter(Q(ap_invoice=invoice) | Q(ar_invoice=invoice), status="recorded").aggregate(total=Sum("amount"))["total"] or Decimal("0")
            invoice.paid_amount = _money(total)
            desired = "paid" if total == invoice.total_amount else "partially_paid" if total > 0 else "posted"
            # Payment reversal is a system-derived correction; append evidence
            # while restoring the derived invoice state without faking a user command.
            history = list(invoice.transition_history)
            history.append({"transition_key": f"payment-void:{transition_key}", "command": "payment_void_recompute", "from_state": invoice.status, "to_state": desired, "occurred_at": timezone.now().isoformat(), "metadata": {"actor_id": actor, "correlation_id": _correlation(transition_key)}})
            type(invoice)._base_manager.filter(pk=invoice.pk, tenant_id=tenant).update(status=desired, transition_history=history, paid_amount=invoice.paid_amount, updated_by=actor, version=F("version") + 1)
            _event(tenant, "accounting.payment.voided.v1", "payment", payment.id, actor, {"invoice_id": invoice.id})
            return payment


def _single_currency(queryset: QuerySet[Any]) -> str:
    currencies = list(queryset.values_list("currency", flat=True).distinct()[:2])
    return currencies[0] if len(currencies) == 1 else "MULTI" if currencies else "USD"


def _report_lines(tenant: UUID, *, start: date | None = None, end: date) -> QuerySet[JournalLine]:
    queryset = JournalLine.objects.for_tenant(tenant).filter(
        journal_entry__is_deleted=False,
        journal_entry__status__in=("posted", "reversed"),
        journal_entry__posting_date__lte=end,
    ).select_related("account", "journal_entry")
    if start is not None:
        queryset = queryset.filter(journal_entry__posting_date__gte=start)
    return queryset


def _report_meta(tenant: UUID, parameters: Mapping[str, object], currency: str) -> dict[str, object]:
    return {"parameters": dict(parameters), "currency": currency, "generated_at": timezone.now(), "correlation_id": _correlation(f"report:{tenant}:{parameters}")}


class FinancialReportingService:
    @staticmethod
    def trial_balance(tenant_id: UUID, *, as_of_date: date) -> dict[str, object]:
        tenant = _tenant(tenant_id)
        rows: list[dict[str, object]] = []
        total_debit = total_credit = Decimal("0.00")
        for account in Account.objects.for_tenant(tenant).filter(is_deleted=False, is_group=False).order_by("code"):
            aggregate = _report_lines(tenant, end=as_of_date).filter(account=account).aggregate(debit=Sum("base_debit_amount"), credit=Sum("base_credit_amount"))
            net = _money((aggregate["debit"] or 0) - (aggregate["credit"] or 0))
            debit, credit = (net, Decimal("0.00")) if net >= 0 else (Decimal("0.00"), -net)
            total_debit += debit
            total_credit += credit
            rows.append({"account_id": account.id, "code": account.code, "name": account.name, "debit": debit, "credit": credit, "journal_line_ids": list(_report_lines(tenant, end=as_of_date).filter(account=account).values_list("id", flat=True))})
        return {**_report_meta(tenant, {"as_of_date": as_of_date}, _single_currency(Account.objects.for_tenant(tenant))), "as_of_date": as_of_date, "rows": rows, "total_debit": _money(total_debit), "total_credit": _money(total_credit), "balanced": _money(total_debit) == _money(total_credit)}

    @staticmethod
    def general_ledger(tenant_id: UUID, *, account_id: UUID, start_date: date, end_date: date) -> list[dict[str, object]]:
        tenant = _tenant(tenant_id)
        account = AccountService.get_account(tenant, account_id)
        opening = _report_lines(tenant, end=start_date).filter(account=account, journal_entry__posting_date__lt=start_date).aggregate(debit=Sum("base_debit_amount"), credit=Sum("base_credit_amount"))
        running = _money((opening["debit"] or 0) - (opening["credit"] or 0))
        rows: list[dict[str, object]] = []
        for line in _report_lines(tenant, start=start_date, end=end_date).filter(account=account).order_by("journal_entry__posting_date", "journal_entry__entry_number", "line_number"):
            running = _money(running + line.base_debit_amount - line.base_credit_amount)
            rows.append({"line_id": line.id, "journal_entry_id": line.journal_entry_id, "entry_number": line.journal_entry.entry_number, "posting_date": line.journal_entry.posting_date, "debit": line.base_debit_amount, "credit": line.base_credit_amount, "running_balance": running, "source_module": line.journal_entry.source_module, "source_reference": line.journal_entry.source_reference})
        return rows

    @staticmethod
    def balance_sheet(tenant_id: UUID, *, as_of_date: date) -> dict[str, object]:
        tenant = _tenant(tenant_id)
        grouped = FinancialReportingService._statement(tenant, None, as_of_date, {"asset", "liability", "equity"})
        assets = grouped.get("asset", Decimal("0"))
        liabilities = grouped.get("liability", Decimal("0"))
        equity = grouped.get("equity", Decimal("0"))
        earnings = sum(FinancialReportingService._statement(tenant, None, as_of_date, {"revenue", "expense"}).values(), Decimal("0"))
        return {**_report_meta(tenant, {"as_of_date": as_of_date}, _single_currency(Account.objects.for_tenant(tenant))), "as_of_date": as_of_date, "sections": grouped, "assets": _money(assets), "liabilities": _money(liabilities), "equity": _money(equity + earnings), "retained_earnings": _money(earnings), "balanced": _money(assets) == _money(liabilities + equity + earnings)}

    @staticmethod
    def income_statement(tenant_id: UUID, *, start_date: date, end_date: date) -> dict[str, object]:
        tenant = _tenant(tenant_id)
        grouped = FinancialReportingService._statement(tenant, start_date, end_date, {"revenue", "expense"})
        revenue, expense = grouped.get("revenue", Decimal("0")), grouped.get("expense", Decimal("0"))
        return {**_report_meta(tenant, {"start_date": start_date, "end_date": end_date}, _single_currency(Account.objects.for_tenant(tenant))), "start_date": start_date, "end_date": end_date, "revenue": _money(revenue), "expenses": _money(expense), "net_income": _money(revenue - expense), "sections": grouped}

    @staticmethod
    def _statement(tenant: UUID, start: date | None, end: date, types: set[str]) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for account in Account.objects.for_tenant(tenant).filter(account_type__in=types, is_deleted=False, is_group=False):
            sums = _report_lines(tenant, start=start, end=end).filter(account=account).aggregate(debit=Sum("base_debit_amount"), credit=Sum("base_credit_amount"))
            debit, credit = sums["debit"] or Decimal("0"), sums["credit"] or Decimal("0")
            natural = credit - debit if account.normal_balance == "credit" else debit - credit
            result[account.account_type] = result.get(account.account_type, Decimal("0")) + _money(natural)
        return result

    @staticmethod
    def cash_flow(tenant_id: UUID, *, start_date: date, end_date: date) -> dict[str, object]:
        tenant = _tenant(tenant_id)
        cash_accounts = Account.objects.for_tenant(tenant).filter(account_type="asset", is_deleted=False, is_group=False)
        if cash_accounts.filter(cash_flow_category__isnull=True).exists():
            raise AccountingServiceError("UNCLASSIFIED_CASH_FLOW", "All cash-flow accounts must be classified before generating this statement.")
        sections = {"operating": Decimal("0.00"), "investing": Decimal("0.00"), "financing": Decimal("0.00")}
        drilldown: dict[str, list[UUID]] = {key: [] for key in sections}
        for account in cash_accounts.exclude(cash_flow_category__isnull=True):
            lines = _report_lines(tenant, start=start_date, end=end_date).filter(account=account)
            sums = lines.aggregate(debit=Sum("base_debit_amount"), credit=Sum("base_credit_amount"))
            category = account.cash_flow_category
            sections[category] += _money((sums["debit"] or 0) - (sums["credit"] or 0))
            drilldown[category].extend(lines.values_list("id", flat=True))
        return {**_report_meta(tenant, {"start_date": start_date, "end_date": end_date}, _single_currency(cash_accounts)), "start_date": start_date, "end_date": end_date, "sections": sections, "net_change": _money(sum(sections.values(), Decimal("0"))), "drilldown": drilldown}

    @staticmethod
    def enqueue_report(tenant_id: UUID, *, actor_id: str, report_type: str, parameters: Mapping[str, object], idempotency_key: str) -> AsyncJob:
        supported = {"trial_balance", "general_ledger", "balance_sheet", "income_statement", "cash_flow"}
        if report_type not in supported:
            raise AccountingServiceError("INVALID_REPORT_TYPE", "Unsupported financial report type.")
        return enqueue(_tenant(tenant_id), actor_id, "accounting.reports.generate", {"report_type": report_type, "parameters": _canonical(parameters)}, idempotency_key)


__all__ = [
    "APInvoiceService",
    "ARInvoiceService",
    "AccountNode",
    "AccountService",
    "AccountingServiceError",
    "FinancialReportingService",
    "FixedAssetAccountingFacade",
    "JournalEntryService",
    "PaymentService",
    "PostingPeriodService",
    "StaleVersionError",
]
