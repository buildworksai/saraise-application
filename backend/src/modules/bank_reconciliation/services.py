"""Tenant-first application services for bank reconciliation.

Controllers in this module deliberately contain no business mutations.  Every
public command reloads its aggregate by tenant, takes the appropriate row lock,
validates the complete invariant, and records an outbox event in the same
transaction.  This makes the services safe for HTTP, worker, and extension
callers alike.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from typing import Any, Iterable, Mapping, Protocol, Sequence
from uuid import UUID

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet, Sum
from django.utils import timezone
from rest_framework import status as http_status

from src.core.api.results import OperationFailed
from src.core.async_jobs.models import AsyncJob, JobStatus, OutboxEvent
from src.core.async_jobs.services import enqueue, transition
from src.core.middleware.correlation import get_correlation_id

from .models import (
    BankAccount,
    BankStatement,
    BankStatementImport,
    BankTransaction,
    MatchingRule,
    ReconciliationMatch,
    ReconciliationMatchLine,
    ReconciliationSession,
)

logger = logging.getLogger("saraise.bank_reconciliation")
MONEY_ZERO = Decimal("0.0000")
MAX_IMPORT_BYTES = 20 * 1024 * 1024
MAX_IMPORT_ROWS = 100_000
SUPPORTED_FORMATS = frozenset({"csv", "ofx", "qif", "bai2", "mt940", "camt053"})


class BankReconciliationError(OperationFailed):
    """Stable public domain error consumed by the governed exception handler."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = http_status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail: object | None = None,
    ) -> None:
        super().__init__(error_code=code, message=message, detail=detail, http_status=status_code)


class LedgerGateway(Protocol):
    """Stable optional accounting contract; implementations never expose ORM objects."""

    key: str
    version: str

    def validate_account(self, tenant_id: UUID, ledger_account_id: UUID) -> None: ...

    def get_balance(self, tenant_id: UUID, ledger_account_id: UUID, as_of_date: date) -> Decimal: ...

    def list_unreconciled(
        self, tenant_id: UUID, ledger_account_id: UUID, date_range: tuple[date, date]
    ) -> Sequence[Mapping[str, object]]: ...

    def health(self) -> object: ...


_ledger_gateway: LedgerGateway | None = None


def register_ledger_gateway(gateway: LedgerGateway | None) -> None:
    """Register or clear the optional ledger service contract."""

    global _ledger_gateway
    _ledger_gateway = gateway
    from .adapters import configure_ledger_gateway

    configure_ledger_gateway(gateway)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class AcceptedImport:
    statement_import: BankStatementImport
    job: AsyncJob


@dataclass(frozen=True, slots=True)
class CandidateResult:
    reconciliation_id: UUID
    proposals: tuple[ReconciliationMatch, ...]
    evaluated_transactions: int


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    reconciliation_id: UUID
    statement_balance: Decimal
    ledger_balance: Decimal
    matched_amount: Decimal
    unmatched_amount: Decimal
    difference: Decimal
    tolerance: Decimal
    can_submit_review: bool
    can_finalize: bool
    blockers: tuple[str, ...]


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BankReconciliationError("INVALID_UUID", f"{field} must be a valid UUID.") from exc


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BankReconciliationError("VALIDATION_ERROR", f"{field} is required.", detail={field: "Required."})
    result = value.strip()
    if len(result) > maximum:
        raise BankReconciliationError(
            "VALIDATION_ERROR", f"{field} is too long.", detail={field: f"Maximum {maximum} characters."}
        )
    return result


def _decimal(value: object, field: str, *, nonnegative: bool = False) -> Decimal:
    try:
        result = Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BankReconciliationError("VALIDATION_ERROR", f"{field} must be a decimal value.") from exc
    if nonnegative and result < MONEY_ZERO:
        raise BankReconciliationError("VALIDATION_ERROR", f"{field} cannot be negative.")
    return result


def _pdf_document(lines: Iterable[str]) -> bytes:
    """Build a small standards-compliant PDF without an optional renderer dependency."""

    escaped = [str(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")[:180] for line in lines]
    commands = ["BT", "/F1 10 Tf", "50 760 Td"]
    for index, line in enumerate(escaped):
        if index:
            commands.append("0 -15 Td")
        commands.append(f"({line}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    )
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode("ascii"))
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(document)


def _not_found(resource: str) -> BankReconciliationError:
    return BankReconciliationError(
        "NOT_FOUND", f"{resource} was not found.", status_code=http_status.HTTP_404_NOT_FOUND
    )


def _event(
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    actor_id: UUID | None,
    payload: Mapping[str, object] | None = None,
    causation_id: str | None = None,
) -> None:
    from .events import publish_domain_event

    publish_domain_event(
        tenant_id,
        event_type,
        aggregate_type,
        aggregate_id,
        actor_id=actor_id,
        payload=payload or {},
        causation_id=causation_id,
        correlation_id=get_correlation_id() or str(uuid.uuid4()),
    )


def _clean_and_save(instance: Any, *, update_fields: Iterable[str] | None = None) -> Any:
    instance.full_clean()
    if update_fields is None:
        instance.save()
    else:
        fields = set(update_fields)
        fields.add("updated_at")
        instance.save(update_fields=sorted(fields))
    return instance


def _history_entry(
    command: str, source: str, target: str, key: str, actor_id: UUID, reason: str = ""
) -> dict[str, object]:
    return {
        "transition_key": key,
        "command": command,
        "from_state": source,
        "to_state": target,
        "occurred_at": timezone.now().isoformat(),
        "metadata": {
            "actor_id": str(actor_id),
            "reason": reason,
            "correlation_id": get_correlation_id() or str(uuid.uuid4()),
        },
    }


def _transition_session(
    session: ReconciliationSession,
    command: str,
    target: str,
    actor_id: UUID,
    idempotency_key: str,
    *,
    reason: str = "",
) -> ReconciliationSession:
    key = _text(idempotency_key, "idempotency_key", 128)
    for item in session.transition_history:
        if item.get("transition_key") == key:
            if item.get("command") != command:
                raise BankReconciliationError("IDEMPOTENCY_CONFLICT", "Idempotency key was used for another command.")
            return session
    allowed: dict[str, dict[str, str]] = {
        "start": {"draft": "in_progress"},
        "submit_review": {"in_progress": "review"},
        "return_to_work": {"review": "in_progress"},
        "finalize": {"review": "finalized"},
        "void": {"draft": "void", "in_progress": "void", "review": "void"},
    }
    expected = allowed.get(command, {}).get(session.status)
    if expected != target:
        raise BankReconciliationError(
            "ILLEGAL_TRANSITION", f"Cannot {command.replace('_', ' ')} a reconciliation in {session.status} state."
        )
    history = list(session.transition_history)
    history.append(_history_entry(command, session.status, target, key, actor_id, reason))
    session.status = target
    session.transition_history = history
    return session


class BankAccountService:
    @staticmethod
    def get(tenant_id: UUID | str, account_id: UUID | str) -> BankAccount:
        tenant = _uuid(tenant_id, "tenant_id")
        account = BankAccount.objects.for_tenant(tenant).filter(pk=_uuid(account_id, "account_id")).first()
        if account is None:
            raise _not_found("Bank account")
        return account

    @staticmethod
    def validate_ledger_account(tenant_id: UUID | str, ledger_account_id: UUID | str) -> None:
        tenant = _uuid(tenant_id, "tenant_id")
        ledger_id = _uuid(ledger_account_id, "ledger_account_id")
        if _ledger_gateway is None:
            raise BankReconciliationError(
                "LEDGER_UNAVAILABLE",
                "Accounting integration is not configured; leave the ledger account blank to use file reconciliation.",
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            _ledger_gateway.validate_account(tenant, ledger_id)
        except BankReconciliationError:
            raise
        except (KeyError, LookupError) as exc:
            raise _not_found("Ledger account") from exc
        except Exception as exc:
            raise BankReconciliationError(
                "LEDGER_UNAVAILABLE",
                "Accounting integration is currently unavailable.",
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc

    @classmethod
    def create(cls, tenant_id: UUID | str, actor_id: UUID | str, data: Mapping[str, object]) -> BankAccount:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        values = dict(data)
        values.pop("tenant_id", None)
        ledger_id = values.get("ledger_account_id")
        if ledger_id:
            cls.validate_ledger_account(tenant, str(ledger_id))
            values["ledger_account_id"] = _uuid(str(ledger_id), "ledger_account_id")
        account_number = _text(values.pop("account_number", None), "account_number", 100)
        with transaction.atomic():
            account = BankAccount(tenant_id=tenant, account_number=account_number, created_by_id=actor, **values)
            try:
                _clean_and_save(account)
            except IntegrityError as exc:
                raise BankReconciliationError("DUPLICATE_ACCOUNT", "This bank account already exists.") from exc
            _event(
                tenant,
                "bank_reconciliation.account.created",
                "bank_account",
                account.id,
                actor,
                {"currency": account.currency},
            )
            return account

    # Compatibility for callers of the former scaffold API.
    @classmethod
    def create_bank_account(
        cls, tenant_id: UUID | str, account_number: str, bank_name: str, account_name: str, **kwargs: object
    ) -> BankAccount:
        actor = kwargs.pop("actor_id", uuid.UUID(int=0))
        return cls.create(
            tenant_id,
            actor,
            {"account_number": account_number, "bank_name": bank_name, "account_name": account_name, **kwargs},
        )

    @classmethod
    def update(
        cls, tenant_id: UUID | str, account_id: UUID | str, actor_id: UUID | str, data: Mapping[str, object]
    ) -> BankAccount:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            account = (
                BankAccount.objects.select_for_update()
                .for_tenant(tenant)
                .filter(pk=_uuid(account_id, "account_id"))
                .first()
            )
            if account is None:
                raise _not_found("Bank account")
            values = dict(data)
            values.pop("tenant_id", None)
            if (
                "currency" in values
                and str(values["currency"]).upper() != account.currency
                and account.statements.exists()
            ):
                raise BankReconciliationError("ACCOUNT_LOCKED", "Currency cannot change after statements exist.")
            if "account_number" in values and account.statements.exists():
                raise BankReconciliationError(
                    "ACCOUNT_LOCKED", "Account identity cannot change after statements exist."
                )
            if values.get("ledger_account_id"):
                cls.validate_ledger_account(tenant, str(values["ledger_account_id"]))
            mutable = {
                "account_number",
                "bank_name",
                "account_name",
                "account_type",
                "currency",
                "bank_identifier",
                "ledger_account_id",
                "opening_balance",
                "opening_balance_date",
            }
            for field, value in values.items():
                if field in mutable:
                    setattr(account, field, value)
            _clean_and_save(account)
            _event(
                tenant,
                "bank_reconciliation.account.updated",
                "bank_account",
                account.id,
                actor,
                {"currency": account.currency},
            )
            return account

    @staticmethod
    def archive(tenant_id: UUID | str, account_id: UUID | str, actor_id: UUID | str) -> BankAccount:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            account = (
                BankAccount.objects.select_for_update()
                .for_tenant(tenant)
                .filter(pk=_uuid(account_id, "account_id"))
                .first()
            )
            if account is None:
                raise _not_found("Bank account")
            if (
                ReconciliationSession.objects.for_tenant(tenant)
                .filter(bank_account=account, status__in=("draft", "in_progress", "review"))
                .exists()
            ):
                raise BankReconciliationError(
                    "ACTIVE_RECONCILIATION", "Archive is blocked while a reconciliation is active."
                )
            if account.is_active:
                account.is_active = False
                account.archived_at = timezone.now()
                _clean_and_save(account, update_fields=("is_active", "archived_at"))
                _event(tenant, "bank_reconciliation.account.archived", "bank_account", account.id, actor)
            return account


class StatementService:
    @staticmethod
    def get(tenant_id: UUID | str, statement_id: UUID | str) -> BankStatement:
        tenant = _uuid(tenant_id, "tenant_id")
        statement = BankStatement.objects.for_tenant(tenant).filter(pk=_uuid(statement_id, "statement_id")).first()
        if statement is None:
            raise _not_found("Bank statement")
        return statement

    @staticmethod
    def _recalculate(statement: BankStatement) -> None:
        total = statement.transactions.aggregate(value=Sum("amount"))["value"] or MONEY_ZERO
        statement.transaction_total = Decimal(total).quantize(Decimal("0.0001"))
        statement.calculated_closing_balance = statement.opening_balance + statement.transaction_total
        statement.balance_variance = statement.closing_balance - statement.calculated_closing_balance
        _clean_and_save(
            statement, update_fields=("transaction_total", "calculated_closing_balance", "balance_variance")
        )

    @classmethod
    def create_manual_statement(
        cls, tenant_id: UUID | str, actor_id: UUID | str, data: Mapping[str, object]
    ) -> BankStatement:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        values = dict(data)
        transactions = list(values.pop("transactions", []))
        account_id = values.pop("bank_account_id", values.pop("bank_account", None))
        with transaction.atomic():
            account = (
                BankAccount.objects.select_for_update()
                .for_tenant(tenant)
                .filter(pk=_uuid(str(account_id), "bank_account_id"), is_active=True)
                .first()
            )
            if account is None:
                raise _not_found("Active bank account")
            period_end = values.get("period_end") or values.get("statement_date")
            period_start = values.get("period_start") or period_end
            statement = BankStatement(
                tenant_id=tenant,
                bank_account=account,
                statement_import=None,
                statement_reference=values.get("statement_reference") or f"MANUAL-{uuid.uuid4().hex[:12].upper()}",
                period_start=period_start,
                period_end=period_end,
                statement_date=period_end,
                opening_balance=_decimal(values.get("opening_balance", MONEY_ZERO), "opening_balance"),
                closing_balance=_decimal(values.get("closing_balance", MONEY_ZERO), "closing_balance"),
                status="imported",
                created_by_id=actor,
            )
            _clean_and_save(statement)
            for sequence, row in enumerate(transactions, 1):
                cls._create_transaction(tenant, statement, actor, row, sequence)
            cls._recalculate(statement)
            _event(
                tenant,
                "bank_reconciliation.statement.created",
                "bank_statement",
                statement.id,
                actor,
                {"status": statement.status},
            )
            return statement

    @staticmethod
    def list_transactions(
        tenant_id: UUID | str, statement_id: UUID | str, filters: Mapping[str, object]
    ) -> QuerySet[BankTransaction]:
        tenant = _uuid(tenant_id, "tenant_id")
        statement = StatementService.get(tenant, statement_id)
        queryset = BankTransaction.objects.for_tenant(tenant).filter(bank_statement=statement)
        for field in ("match_status", "transaction_type"):
            if filters.get(field):
                queryset = queryset.filter(**{field: filters[field]})
        if filters.get("date_from"):
            queryset = queryset.filter(transaction_date__gte=filters["date_from"])
        if filters.get("date_to"):
            queryset = queryset.filter(transaction_date__lte=filters["date_to"])
        if filters.get("search"):
            term = str(filters["search"])
            queryset = queryset.filter(
                Q(description__icontains=term)
                | Q(reference_number__icontains=term)
                | Q(counterparty_name__icontains=term)
            )
        return queryset.order_by("sequence_number", "id")

    @staticmethod
    def _create_transaction(
        tenant: UUID, statement: BankStatement, actor: UUID, data: Mapping[str, object], sequence: int | None = None
    ) -> BankTransaction:
        amount = _decimal(data.get("amount"), "amount")
        if amount == MONEY_ZERO:
            raise BankReconciliationError("VALIDATION_ERROR", "Transaction amount cannot be zero.")
        number = sequence or ((statement.transactions.aggregate(value=Sum("sequence_number"))["value"] or 0) + 1)
        value_date = data.get("value_date") or None
        value = BankTransaction(
            tenant_id=tenant,
            bank_statement=statement,
            sequence_number=number,
            external_id=str(data.get("external_id") or ""),
            transaction_date=data.get("transaction_date"),
            value_date=value_date,
            description=_text(data.get("description"), "description", 500),
            amount=amount,
            transaction_type="credit" if amount > 0 else "debit",
            running_balance=data.get("running_balance") or None,
            reference_number=str(data.get("reference_number") or "").strip(),
            counterparty_name=str(data.get("counterparty_name") or "").strip(),
            counterparty_account_masked=str(data.get("counterparty_account_masked") or "").strip(),
            match_status="unmatched",
            is_reconciled=False,
            source_data=dict(data.get("source_data") or {}),
            created_by_id=actor,
        )
        _clean_and_save(value)
        return value

    @classmethod
    def add_manual_transaction(
        cls, tenant_id: UUID | str, statement_id: UUID | str, actor_id: UUID | str, data: Mapping[str, object]
    ) -> BankTransaction:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            statement = (
                BankStatement.objects.select_for_update()
                .for_tenant(tenant)
                .filter(pk=_uuid(statement_id, "statement_id"))
                .first()
            )
            if statement is None:
                raise _not_found("Bank statement")
            if statement.status in ("reconciled", "void"):
                raise BankReconciliationError("STATEMENT_LOCKED", "This statement is immutable.")
            value = cls._create_transaction(tenant, statement, actor, data)
            cls._recalculate(statement)
            _event(
                tenant,
                "bank_reconciliation.transaction.created",
                "bank_transaction",
                value.id,
                actor,
                {"statement_id": str(statement.id)},
            )
            return value

    @classmethod
    def update_manual_transaction(
        cls, tenant_id: UUID | str, transaction_id: UUID | str, actor_id: UUID | str, data: Mapping[str, object]
    ) -> BankTransaction:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = (
                BankTransaction.objects.select_for_update()
                .for_tenant(tenant)
                .select_related("bank_statement")
                .filter(pk=_uuid(transaction_id, "transaction_id"))
                .first()
            )
            if value is None:
                raise _not_found("Bank transaction")
            statement = BankStatement.objects.select_for_update().get(pk=value.bank_statement_id, tenant_id=tenant)
            if (
                statement.statement_import_id
                or statement.status in ("reconciled", "void")
                or value.match_status in ("matched", "proposed")
            ):
                raise BankReconciliationError("TRANSACTION_LOCKED", "Only unmatched manual transactions can be edited.")
            for field in (
                "transaction_date",
                "value_date",
                "description",
                "amount",
                "reference_number",
                "counterparty_name",
            ):
                if field in data:
                    setattr(value, field, data[field])
            if "amount" in data:
                value.amount = _decimal(data["amount"], "amount")
                value.transaction_type = "credit" if value.amount > 0 else "debit"
            _clean_and_save(value)
            cls._recalculate(statement)
            _event(tenant, "bank_reconciliation.transaction.updated", "bank_transaction", value.id, actor)
            return value

    @staticmethod
    def exclude_transaction(
        tenant_id: UUID | str, transaction_id: UUID | str, actor_id: UUID | str, reason: str
    ) -> BankTransaction:
        return StatementService._set_excluded(tenant_id, transaction_id, actor_id, True, reason)

    @staticmethod
    def restore_transaction(tenant_id: UUID | str, transaction_id: UUID | str, actor_id: UUID | str) -> BankTransaction:
        return StatementService._set_excluded(tenant_id, transaction_id, actor_id, False, "Restored")

    @staticmethod
    def _set_excluded(
        tenant_id: UUID | str, transaction_id: UUID | str, actor_id: UUID | str, excluded: bool, reason: str
    ) -> BankTransaction:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        reason_text = _text(reason, "reason", 500)
        with transaction.atomic():
            value = (
                BankTransaction.objects.select_for_update()
                .for_tenant(tenant)
                .select_related("bank_statement")
                .filter(pk=_uuid(transaction_id, "transaction_id"))
                .first()
            )
            if value is None:
                raise _not_found("Bank transaction")
            if value.bank_statement.status in ("reconciled", "void") or value.match_status in ("matched", "proposed"):
                raise BankReconciliationError(
                    "TRANSACTION_LOCKED", "Matched or certified transactions cannot be changed."
                )
            value.match_status = "excluded" if excluded else "unmatched"
            if hasattr(value, "audit_history"):
                history = list(value.audit_history)
                history.append(
                    {
                        "action": "exclude" if excluded else "restore",
                        "reason": reason_text,
                        "actor_id": str(actor),
                        "at": timezone.now().isoformat(),
                    }
                )
                value.audit_history = history
            _clean_and_save(value)
            _event(
                tenant,
                f"bank_reconciliation.transaction.{'excluded' if excluded else 'restored'}",
                "bank_transaction",
                value.id,
                actor,
                {"reason_provided": True},
            )
            return value

    @staticmethod
    def void_statement(
        tenant_id: UUID | str,
        statement_id: UUID | str,
        actor_id: UUID | str,
        reason: str,
        idempotency_key: str | None = None,
    ) -> BankStatement:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        _text(reason, "reason", 500)
        key = _text(idempotency_key, "idempotency_key", 128) if idempotency_key is not None else None
        with transaction.atomic():
            value = (
                BankStatement.objects.select_for_update()
                .for_tenant(tenant)
                .filter(pk=_uuid(statement_id, "statement_id"))
                .first()
            )
            if value is None:
                raise _not_found("Bank statement")
            if (
                key
                and OutboxEvent.objects.for_tenant(tenant)
                .filter(
                    aggregate_type="bank_statement",
                    aggregate_id=value.id,
                    event_type="bank_reconciliation.statement.voided",
                    payload__causation_id=key,
                )
                .exists()
            ):
                return value
            if value.status in ("reconciled", "void"):
                raise BankReconciliationError("STATEMENT_LOCKED", "A reconciled or void statement cannot be voided.")
            if (
                ReconciliationSession.objects.for_tenant(tenant)
                .filter(bank_statement=value, status__in=("in_progress", "review", "finalized"))
                .exists()
            ):
                raise BankReconciliationError("ACTIVE_RECONCILIATION", "Void is blocked by an active reconciliation.")
            value.status = "void"
            value.is_reconciled = False
            _clean_and_save(value, update_fields=("status", "is_reconciled"))
            _event(
                tenant,
                "bank_reconciliation.statement.voided",
                "bank_statement",
                value.id,
                actor,
                {"reason_provided": True},
                causation_id=key,
            )
            return value


class StatementImportService:
    @staticmethod
    def get_import(tenant_id: UUID | str, import_id: UUID | str) -> BankStatementImport:
        tenant = _uuid(tenant_id, "tenant_id")
        value = BankStatementImport.objects.for_tenant(tenant).filter(pk=_uuid(import_id, "import_id")).first()
        if value is None:
            raise _not_found("Statement import")
        return value

    @staticmethod
    def _storage_name(value: BankStatementImport) -> str:
        return f"bank_reconciliation/{value.tenant_id}/{value.id}/statement.{value.file_format}"

    @classmethod
    def request_import(
        cls,
        tenant_id: UUID | str,
        actor_id: UUID | str,
        data: Mapping[str, object],
        idempotency_key: str,
    ) -> AcceptedImport:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        key = _text(idempotency_key, "idempotency_key", 128)
        existing = BankStatementImport.objects.for_tenant(tenant).filter(idempotency_key=key).first()
        if existing is not None:
            job = AsyncJob.objects.for_tenant(tenant).filter(pk=existing.async_job_id).first()
            if job is None:
                raise BankReconciliationError("IMPORT_INCOMPLETE", "The import has no durable job.", status_code=503)
            return AcceptedImport(existing, job)
        account_id = data.get("bank_account_id", data.get("bank_account"))
        file_format = str(data.get("file_format") or "").lower().replace(".", "")
        if file_format not in SUPPORTED_FORMATS:
            raise BankReconciliationError("UNSUPPORTED_FORMAT", "The statement format is not supported.")
        upload = data.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise BankReconciliationError("VALIDATION_ERROR", "A statement file is required.")
        raw = upload.read(MAX_IMPORT_BYTES + 1)
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_IMPORT_BYTES:
            raise BankReconciliationError(
                "IMPORT_SIZE_LIMIT", "The statement file exceeds the configured limit.", status_code=413
            )
        checksum = hashlib.sha256(raw).hexdigest()
        filename = PurePath(str(getattr(upload, "name", "statement"))).name[:255]
        mapping = dict(data.get("mapping") or {})
        if file_format != "csv" and mapping:
            raise BankReconciliationError("INVALID_MAPPING", "Column mapping is supported only for CSV imports.")
        import_id = uuid.uuid4()
        storage_name = f"bank_reconciliation/{tenant}/{import_id}/statement.{file_format}"
        stored = False
        try:
            with transaction.atomic():
                account = (
                    BankAccount.objects.select_for_update()
                    .for_tenant(tenant)
                    .filter(pk=_uuid(str(account_id), "bank_account_id"), is_active=True)
                    .first()
                )
                if account is None:
                    raise _not_found("Active bank account")
                value = BankStatementImport(
                    id=import_id,
                    tenant_id=tenant,
                    bank_account=account,
                    source="file",
                    file_format=file_format,
                    source_document_id=_uuid(str(data.get("source_document_id") or uuid.uuid4()), "source_document_id"),
                    source_filename=filename,
                    content_sha256=checksum,
                    mapping=mapping,
                    status="pending",
                    idempotency_key=key,
                    requested_by_id=actor,
                )
                _clean_and_save(value)
                if default_storage.exists(storage_name):
                    default_storage.delete(storage_name)
                saved_name = default_storage.save(storage_name, ContentFile(raw))
                stored = True
                if saved_name != storage_name:
                    raise BankReconciliationError(
                        "STORAGE_CONFLICT", "Statement storage returned an unexpected identity.", status_code=503
                    )
                job = enqueue(
                    tenant,
                    actor,
                    "bank_reconciliation.import_statement",
                    {"import_id": str(value.id)},
                    f"bank-import:{key}",
                )
                value.async_job_id = job.id
                _clean_and_save(value, update_fields=("async_job_id",))
                _event(
                    tenant,
                    "bank_reconciliation.statement.import.requested",
                    "statement_import",
                    value.id,
                    actor,
                    {"file_format": file_format, "job_id": str(job.id)},
                )
                return AcceptedImport(value, job)
        except Exception:
            if stored and default_storage.exists(storage_name):
                default_storage.delete(storage_name)
            raise

    @classmethod
    def execute_import(cls, tenant_id: UUID | str, import_id: UUID | str) -> BankStatement:
        tenant = _uuid(tenant_id, "tenant_id")
        import_uuid = _uuid(import_id, "import_id")
        with transaction.atomic():
            value = (
                BankStatementImport.objects.select_for_update()
                .for_tenant(tenant)
                .select_related("bank_account")
                .filter(pk=import_uuid)
                .first()
            )
            if value is None:
                raise _not_found("Statement import")
            if value.status == "succeeded" and hasattr(value, "statement"):
                return value.statement
            if value.status not in ("pending", "running"):
                raise BankReconciliationError("ILLEGAL_TRANSITION", f"Import cannot run from {value.status}.")
            if not value.bank_account.is_active:
                raise BankReconciliationError("ACCOUNT_ARCHIVED", "Archived accounts reject imports.")
            value.status, value.started_at = "running", value.started_at or timezone.now()
            _clean_and_save(value, update_fields=("status", "started_at"))
        try:
            from .adapters import get_parser

            storage_name = cls._storage_name(value)
            if not default_storage.exists(storage_name):
                raise BankReconciliationError(
                    "SOURCE_UNAVAILABLE", "The durable statement source is unavailable.", status_code=503
                )
            with default_storage.open(storage_name, "rb") as stream:
                parsed = get_parser(value.file_format).parse(stream, value.mapping)
            rows = list(parsed.transactions)
            if len(rows) > MAX_IMPORT_ROWS:
                raise BankReconciliationError("IMPORT_ROW_LIMIT", "The statement exceeds the configured row limit.")
            with transaction.atomic():
                value = BankStatementImport.objects.select_for_update().for_tenant(tenant).get(pk=import_uuid)
                statement = BankStatement(
                    tenant_id=tenant,
                    bank_account=value.bank_account,
                    statement_import=value,
                    statement_reference=parsed.statement_reference,
                    period_start=parsed.period_start,
                    period_end=parsed.period_end,
                    statement_date=parsed.period_end,
                    opening_balance=parsed.opening_balance,
                    closing_balance=parsed.closing_balance,
                    status="imported",
                    created_by_id=value.requested_by_id,
                )
                _clean_and_save(statement)
                for sequence, row in enumerate(rows, 1):
                    StatementService._create_transaction(
                        tenant, statement, value.requested_by_id, row.as_mapping(), sequence
                    )
                StatementService._recalculate(statement)
                if statement.balance_variance != MONEY_ZERO:
                    raise BankReconciliationError(
                        "STATEMENT_BALANCE_MISMATCH",
                        "The imported statement balances do not reconcile with its transactions.",
                        detail={"variance": str(statement.balance_variance)},
                    )
                value.rows_received = len(rows)
                value.rows_imported = len(rows)
                value.rows_rejected = 0
                value.status = "succeeded"
                value.completed_at = timezone.now()
                value.error_code = ""
                value.error_detail = {}
                _clean_and_save(value)
                _event(
                    tenant,
                    "bank_reconciliation.statement.import.succeeded",
                    "statement_import",
                    value.id,
                    value.requested_by_id,
                    {"file_format": value.file_format, "rows_imported": len(rows)},
                )
                return statement
        except Exception as exc:
            with transaction.atomic():
                failed = (
                    BankStatementImport.objects.select_for_update().for_tenant(tenant).filter(pk=import_uuid).first()
                )
                if failed and failed.status not in ("succeeded", "cancelled"):
                    failed.status = "failed"
                    failed.error_code = exc.error_code if isinstance(exc, BankReconciliationError) else "PARSE_FAILED"
                    failed.error_detail = {"message": "The statement could not be imported."}
                    failed.completed_at = timezone.now()
                    _clean_and_save(failed)
                    _event(
                        tenant,
                        "bank_reconciliation.statement.import.failed",
                        "statement_import",
                        failed.id,
                        failed.requested_by_id,
                        {"file_format": failed.file_format, "failure_code": failed.error_code},
                    )
            raise

    @classmethod
    def retry_import(
        cls, tenant_id: UUID | str, import_id: UUID | str, actor_id: UUID | str, idempotency_key: str
    ) -> AcceptedImport:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        key = _text(idempotency_key, "idempotency_key", 128)
        with transaction.atomic():
            value = (
                BankStatementImport.objects.select_for_update()
                .for_tenant(tenant)
                .filter(pk=_uuid(import_id, "import_id"))
                .first()
            )
            if value is None:
                raise _not_found("Statement import")
            if value.status != "failed":
                raise BankReconciliationError("ILLEGAL_TRANSITION", "Only failed imports can be retried.")
            job = enqueue(
                tenant,
                actor,
                "bank_reconciliation.import_statement",
                {"import_id": str(value.id)},
                f"bank-import-retry:{value.id}:{key}",
            )
            value.status, value.async_job_id = "pending", job.id
            value.error_code, value.error_detail, value.completed_at = "", {}, None
            _clean_and_save(value)
            _event(
                tenant,
                "bank_reconciliation.statement.import.requested",
                "statement_import",
                value.id,
                actor,
                {"file_format": value.file_format, "job_id": str(job.id)},
            )
            return AcceptedImport(value, job)

    @staticmethod
    def cancel_import(tenant_id: UUID | str, import_id: UUID | str, actor_id: UUID | str) -> BankStatementImport:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = (
                BankStatementImport.objects.select_for_update()
                .for_tenant(tenant)
                .filter(pk=_uuid(import_id, "import_id"))
                .first()
            )
            if value is None:
                raise _not_found("Statement import")
            if value.status not in ("pending", "running"):
                raise BankReconciliationError("ILLEGAL_TRANSITION", "Only active imports can be cancelled.")
            value.status, value.completed_at = "cancelled", timezone.now()
            _clean_and_save(value, update_fields=("status", "completed_at"))
            if value.async_job_id:
                job = AsyncJob.objects.for_tenant(tenant).filter(pk=value.async_job_id).first()
                if job and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                    transition(job.id, tenant, JobStatus.CANCELLED, reason="Statement import cancelled", actor_id=actor)
            _event(tenant, "bank_reconciliation.statement.import.cancelled", "statement_import", value.id, actor)
            return value


class MatchingRuleService:
    ALLOWED_KEYS = frozenset(
        {"date_window_days", "amount_tolerance", "reference_normalization", "counterparty_pattern"}
    )

    @staticmethod
    def _configuration(rule_type: str, configuration: object, extension_key: object = "") -> dict[str, object]:
        if not isinstance(configuration, dict):
            raise BankReconciliationError("INVALID_RULE", "Rule configuration must be an object.")
        unknown = set(configuration) - MatchingRuleService.ALLOWED_KEYS
        if rule_type == "extension":
            prefix = f"{extension_key}."
            unknown = {key for key in unknown if not str(key).startswith(prefix)}
        if unknown:
            raise BankReconciliationError(
                "INVALID_RULE", "Rule configuration contains unsupported keys.", detail={"keys": sorted(unknown)}
            )
        if "date_window_days" in configuration and (
            not isinstance(configuration["date_window_days"], int) or not 0 <= configuration["date_window_days"] <= 365
        ):
            raise BankReconciliationError("INVALID_RULE", "date_window_days must be between 0 and 365.")
        if "amount_tolerance" in configuration and _decimal(
            configuration["amount_tolerance"], "amount_tolerance", nonnegative=True
        ) > Decimal("1000000"):
            raise BankReconciliationError("INVALID_RULE", "amount_tolerance exceeds the safe limit.")
        if "counterparty_pattern" in configuration:
            try:
                re.compile(str(configuration["counterparty_pattern"]))
            except re.error as exc:
                raise BankReconciliationError("INVALID_RULE", "counterparty_pattern is invalid.") from exc
        return configuration

    @staticmethod
    def get(tenant_id: UUID | str, rule_id: UUID | str) -> MatchingRule:
        tenant = _uuid(tenant_id, "tenant_id")
        value = MatchingRule.objects.for_tenant(tenant).filter(pk=_uuid(rule_id, "rule_id")).first()
        if value is None:
            raise _not_found("Matching rule")
        return value

    @classmethod
    def create(cls, tenant_id: UUID | str, actor_id: UUID | str, data: Mapping[str, object]) -> MatchingRule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        values = dict(data)
        values["configuration"] = cls._configuration(
            str(values.get("rule_type")), values.get("configuration", {}), values.get("extension_key", "")
        )
        if (
            values.get("auto_confirm")
            and str(values.get("rule_type")) != "extension"
            and _decimal(values.get("minimum_score", 0), "minimum_score") != Decimal("1.0000")
        ):
            raise BankReconciliationError("INVALID_RULE", "Core auto-confirm rules require a score of exactly 1.0000.")
        with transaction.atomic():
            value = MatchingRule(tenant_id=tenant, created_by_id=actor, updated_by_id=actor, **values)
            try:
                _clean_and_save(value)
            except IntegrityError as exc:
                raise BankReconciliationError("DUPLICATE_RULE", "Rule name or priority already exists.") from exc
            _event(
                tenant,
                "bank_reconciliation.rule.created",
                "matching_rule",
                value.id,
                actor,
                {"rule_type": value.rule_type},
            )
            return value

    @classmethod
    def update(
        cls, tenant_id: UUID | str, rule_id: UUID | str, actor_id: UUID | str, data: Mapping[str, object]
    ) -> MatchingRule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = (
                MatchingRule.objects.select_for_update().for_tenant(tenant).filter(pk=_uuid(rule_id, "rule_id")).first()
            )
            if value is None:
                raise _not_found("Matching rule")
            merged_type = str(data.get("rule_type", value.rule_type))
            merged_ext = data.get("extension_key", value.extension_key)
            if "configuration" in data:
                cls._configuration(merged_type, data["configuration"], merged_ext)
            for field in (
                "name",
                "description",
                "rule_type",
                "priority",
                "configuration",
                "auto_confirm",
                "minimum_score",
                "extension_key",
            ):
                if field in data:
                    setattr(value, field, data[field])
            value.updated_by_id = actor
            _clean_and_save(value)
            _event(
                tenant,
                "bank_reconciliation.rule.updated",
                "matching_rule",
                value.id,
                actor,
                {"rule_type": value.rule_type},
            )
            return value

    @staticmethod
    def _active(tenant_id: UUID | str, rule_id: UUID | str, actor_id: UUID | str, active: bool) -> MatchingRule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = (
                MatchingRule.objects.select_for_update().for_tenant(tenant).filter(pk=_uuid(rule_id, "rule_id")).first()
            )
            if value is None:
                raise _not_found("Matching rule")
            value.is_active, value.updated_by_id = active, actor
            _clean_and_save(value, update_fields=("is_active", "updated_by_id"))
            _event(
                tenant,
                f"bank_reconciliation.rule.{'activated' if active else 'deactivated'}",
                "matching_rule",
                value.id,
                actor,
            )
            return value

    activate = classmethod(lambda cls, tenant_id, rule_id, actor_id: cls._active(tenant_id, rule_id, actor_id, True))
    deactivate = classmethod(lambda cls, tenant_id, rule_id, actor_id: cls._active(tenant_id, rule_id, actor_id, False))

    @staticmethod
    def delete(tenant_id: UUID | str, rule_id: UUID | str, actor_id: UUID | str) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = (
                MatchingRule.objects.select_for_update().for_tenant(tenant).filter(pk=_uuid(rule_id, "rule_id")).first()
            )
            if value is None:
                raise _not_found("Matching rule")
            if ReconciliationMatch.objects.for_tenant(tenant).filter(rule=value).exists():
                raise BankReconciliationError("RULE_IN_USE", "Referenced rules must be deactivated instead of deleted.")
            value_id = value.id
            value.delete()
            _event(tenant, "bank_reconciliation.rule.deleted", "matching_rule", value_id, actor)


class ReconciliationService:
    @staticmethod
    def get(tenant_id: UUID | str, reconciliation_id: UUID | str) -> ReconciliationSession:
        tenant = _uuid(tenant_id, "tenant_id")
        value = (
            ReconciliationSession.objects.for_tenant(tenant)
            .filter(pk=_uuid(reconciliation_id, "reconciliation_id"))
            .first()
        )
        if value is None:
            raise _not_found("Reconciliation")
        return value

    @classmethod
    def create(
        cls, tenant_id: UUID | str, actor_id: UUID | str, data: Mapping[str, object], idempotency_key: str
    ) -> ReconciliationSession:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        key = _text(idempotency_key, "idempotency_key", 128)
        for candidate in ReconciliationSession.objects.for_tenant(tenant).only("id", "transition_history"):
            if any(
                item.get("transition_key") == key and item.get("command") == "create"
                for item in candidate.transition_history
            ):
                return ReconciliationSession.objects.get(pk=candidate.pk)
        statement_id = data.get("bank_statement_id", data.get("bank_statement"))
        with transaction.atomic():
            statement = (
                BankStatement.objects.select_for_update()
                .for_tenant(tenant)
                .select_related("bank_account")
                .filter(pk=_uuid(str(statement_id), "bank_statement_id"))
                .first()
            )
            if statement is None:
                raise _not_found("Bank statement")
            if not statement.bank_account.is_active or statement.status in ("reconciled", "void"):
                raise BankReconciliationError("STATEMENT_LOCKED", "The statement cannot be reconciled.")
            if ReconciliationSession.objects.for_tenant(tenant).filter(bank_statement=statement).exists():
                raise BankReconciliationError(
                    "DUPLICATE_RECONCILIATION", "A reconciliation already exists for this statement."
                )
            ledger_balance = _decimal(data.get("ledger_balance"), "ledger_balance")
            tolerance = _decimal(data.get("tolerance", MONEY_ZERO), "tolerance", nonnegative=True)
            value = ReconciliationSession(
                tenant_id=tenant,
                bank_account=statement.bank_account,
                bank_statement=statement,
                reconciliation_date=data.get("reconciliation_date"),
                status="draft",
                statement_balance=statement.closing_balance,
                ledger_balance=ledger_balance,
                matched_amount=MONEY_ZERO,
                unmatched_amount=sum(
                    (abs(tx.amount) for tx in statement.transactions.exclude(match_status="excluded")), MONEY_ZERO
                ),
                difference=statement.closing_balance - ledger_balance,
                tolerance=tolerance,
                notes=str(data.get("notes") or ""),
                transition_history=[_history_entry("create", "", "draft", key, actor)],
                started_by_id=actor,
            )
            _clean_and_save(value)
            statement.status = "reconciling"
            _clean_and_save(statement, update_fields=("status",))
            _event(
                tenant,
                "bank_reconciliation.reconciliation.created",
                "reconciliation",
                value.id,
                actor,
                {"statement_id": str(statement.id)},
            )
            return value

    @staticmethod
    def _locked(tenant: UUID, reconciliation_id: UUID | str) -> ReconciliationSession:
        value = (
            ReconciliationSession.objects.select_for_update()
            .for_tenant(tenant)
            .filter(pk=_uuid(reconciliation_id, "reconciliation_id"))
            .first()
        )
        if value is None:
            raise _not_found("Reconciliation")
        return value

    @classmethod
    def start(
        cls, tenant_id: UUID | str, reconciliation_id: UUID | str, actor_id: UUID | str, idempotency_key: str
    ) -> ReconciliationSession:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = cls._locked(tenant, reconciliation_id)
            _transition_session(value, "start", "in_progress", actor, idempotency_key)
            _clean_and_save(value)
            _event(tenant, "bank_reconciliation.reconciliation.started", "reconciliation", value.id, actor)
            return value

    @classmethod
    def create_manual_match(
        cls, tenant_id: UUID | str, reconciliation_id: UUID | str, actor_id: UUID | str, data: Mapping[str, object]
    ) -> ReconciliationMatch:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        lines = list(data.get("lines") or [])
        if len(lines) < 2:
            raise BankReconciliationError("INVALID_ALLOCATION", "A match requires bank and ledger lines.")
        with transaction.atomic():
            reconciliation = cls._locked(tenant, reconciliation_id)
            if reconciliation.status not in ("draft", "in_progress"):
                raise BankReconciliationError("RECONCILIATION_LOCKED", "Matches cannot be changed in this state.")
            bank_count = sum(1 for line in lines if line.get("side") == "bank")
            ledger_count = sum(1 for line in lines if line.get("side") == "ledger")
            if not bank_count or not ledger_count:
                raise BankReconciliationError("INVALID_ALLOCATION", "Both bank and ledger sides are required.")
            inferred = (
                "one_to_many"
                if bank_count == 1 and ledger_count > 1
                else "many_to_one" if bank_count > 1 and ledger_count == 1 else "manual"
            )
            value = ReconciliationMatch.objects.create(
                tenant_id=tenant,
                reconciliation=reconciliation,
                match_type=str(data.get("match_type") or inferred),
                status="proposed",
                explanation={"source": "manual"},
            )
            bank_total, ledger_total = MONEY_ZERO, MONEY_ZERO
            seen_bank: set[UUID] = set()
            seen_ledger: set[tuple[UUID, str]] = set()
            for raw in lines:
                side = raw.get("side")
                amount = _decimal(raw.get("allocated_amount"), "allocated_amount")
                if amount == MONEY_ZERO:
                    raise BankReconciliationError("INVALID_ALLOCATION", "Allocated amounts cannot be zero.")
                if side == "bank":
                    tx_id = _uuid(str(raw.get("bank_transaction_id")), "bank_transaction_id")
                    tx = (
                        BankTransaction.objects.select_for_update()
                        .for_tenant(tenant)
                        .filter(pk=tx_id, bank_statement=reconciliation.bank_statement)
                        .first()
                    )
                    if tx is None:
                        raise _not_found("Bank transaction")
                    if tx.match_status in ("matched", "excluded") or tx_id in seen_bank:
                        raise BankReconciliationError(
                            "ALLOCATION_CONFLICT", "A bank transaction is unavailable for allocation."
                        )
                    already = (
                        ReconciliationMatchLine.objects.for_tenant(tenant)
                        .filter(bank_transaction=tx, match__status__in=("proposed", "confirmed"))
                        .aggregate(total=Sum("allocated_amount"))["total"]
                        or MONEY_ZERO
                    )
                    if abs(Decimal(already) + amount) > abs(tx.amount):
                        raise BankReconciliationError(
                            "OVER_ALLOCATION", "Bank allocation exceeds the transaction amount."
                        )
                    seen_bank.add(tx_id)
                    ReconciliationMatchLine.objects.create(
                        tenant_id=tenant,
                        match=value,
                        side="bank",
                        bank_transaction=tx,
                        allocated_amount=amount,
                        currency=reconciliation.bank_account.currency,
                        ledger_entry_type="other",
                    )
                    bank_total += amount
                elif side == "ledger":
                    ledger_id = _uuid(str(raw.get("ledger_entry_id")), "ledger_entry_id")
                    entry_type = str(raw.get("ledger_entry_type") or "other")
                    key = (ledger_id, entry_type)
                    if key in seen_ledger:
                        raise BankReconciliationError("ALLOCATION_CONFLICT", "A ledger entry is repeated.")
                    seen_ledger.add(key)
                    ReconciliationMatchLine.objects.create(
                        tenant_id=tenant,
                        match=value,
                        side="ledger",
                        ledger_entry_id=ledger_id,
                        ledger_entry_type=entry_type,
                        allocated_amount=amount,
                        currency=reconciliation.bank_account.currency,
                    )
                    ledger_total += amount
                else:
                    raise BankReconciliationError("INVALID_ALLOCATION", "Match line side must be bank or ledger.")
            if bank_total != ledger_total:
                raise BankReconciliationError("UNBALANCED_MATCH", "Bank and ledger allocations must balance exactly.")
            _event(
                tenant,
                "bank_reconciliation.match.proposed",
                "reconciliation_match",
                value.id,
                actor,
                {"reconciliation_id": str(reconciliation.id), "match_type": value.match_type},
            )
            return value

    @classmethod
    def _recalculate(cls, value: ReconciliationSession) -> None:
        value.matched_amount = sum(
            (
                abs(line.allocated_amount)
                for line in ReconciliationMatchLine.objects.for_tenant(value.tenant_id).filter(
                    match__reconciliation=value, match__status="confirmed", side="bank"
                )
            ),
            MONEY_ZERO,
        )
        available = sum(
            (abs(tx.amount) for tx in value.bank_statement.transactions.exclude(match_status="excluded")), MONEY_ZERO
        )
        value.unmatched_amount = max(MONEY_ZERO, available - value.matched_amount)
        value.difference = value.statement_balance - value.ledger_balance
        _clean_and_save(value, update_fields=("matched_amount", "unmatched_amount", "difference"))

    @classmethod
    def confirm_match(
        cls, tenant_id: UUID | str, match_id: UUID | str, actor_id: UUID | str, idempotency_key: str
    ) -> ReconciliationMatch:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        _text(idempotency_key, "idempotency_key", 128)
        with transaction.atomic():
            value = (
                ReconciliationMatch.objects.select_for_update()
                .for_tenant(tenant)
                .select_related("reconciliation")
                .filter(pk=_uuid(match_id, "match_id"))
                .first()
            )
            if value is None:
                raise _not_found("Reconciliation match")
            if value.status == "confirmed":
                return value
            if value.status != "proposed" or value.reconciliation.status not in ("draft", "in_progress"):
                raise BankReconciliationError("MATCH_LOCKED", "Only active proposals can be confirmed.")
            lines = list(value.lines.select_for_update().all())
            bank_total = sum((line.allocated_amount for line in lines if line.side == "bank"), MONEY_ZERO)
            ledger_total = sum((line.allocated_amount for line in lines if line.side == "ledger"), MONEY_ZERO)
            if not lines or bank_total != ledger_total:
                raise BankReconciliationError("UNBALANCED_MATCH", "Bank and ledger allocations must balance exactly.")
            for line in lines:
                if line.bank_transaction_id:
                    tx = BankTransaction.objects.select_for_update().for_tenant(tenant).get(pk=line.bank_transaction_id)
                    tx.match_status, tx.is_reconciled = "matched", True
                    if line.ledger_entry_type == "payment":
                        tx.matched_payment_id = next(
                            (
                                candidate.ledger_entry_id
                                for candidate in lines
                                if candidate.side == "ledger" and candidate.ledger_entry_type == "payment"
                            ),
                            None,
                        )
                    _clean_and_save(tx)
            value.status, value.matched_at, value.matched_by_id = "confirmed", timezone.now(), actor
            _clean_and_save(value)
            reconciliation = ReconciliationSession.objects.select_for_update().get(
                pk=value.reconciliation_id, tenant_id=tenant
            )
            cls._recalculate(reconciliation)
            _event(
                tenant,
                "bank_reconciliation.match.confirmed",
                "reconciliation_match",
                value.id,
                actor,
                {"reconciliation_id": str(reconciliation.id)},
            )
            return value

    @staticmethod
    def reject_match(
        tenant_id: UUID | str, match_id: UUID | str, actor_id: UUID | str, reason: str
    ) -> ReconciliationMatch:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        reason_text = _text(reason, "reason", 500)
        with transaction.atomic():
            value = (
                ReconciliationMatch.objects.select_for_update()
                .for_tenant(tenant)
                .filter(pk=_uuid(match_id, "match_id"))
                .first()
            )
            if value is None:
                raise _not_found("Reconciliation match")
            if value.status != "proposed":
                raise BankReconciliationError("MATCH_LOCKED", "Only proposed matches can be rejected.")
            value.status, value.reversal_reason = "rejected", reason_text
            _clean_and_save(value, update_fields=("status", "reversal_reason"))
            _event(
                tenant,
                "bank_reconciliation.match.rejected",
                "reconciliation_match",
                value.id,
                actor,
                {"reason_provided": True},
            )
            return value

    @classmethod
    def reverse_match(
        cls, tenant_id: UUID | str, match_id: UUID | str, actor_id: UUID | str, reason: str, idempotency_key: str
    ) -> ReconciliationMatch:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        reason_text = _text(reason, "reason", 500)
        _text(idempotency_key, "idempotency_key", 128)
        with transaction.atomic():
            value = (
                ReconciliationMatch.objects.select_for_update()
                .for_tenant(tenant)
                .select_related("reconciliation")
                .filter(pk=_uuid(match_id, "match_id"))
                .first()
            )
            if value is None:
                raise _not_found("Reconciliation match")
            if value.status == "reversed":
                return value
            if value.status != "confirmed" or value.reconciliation.status in ("finalized", "void"):
                raise BankReconciliationError("MATCH_LOCKED", "Certified or inactive matches cannot be reversed.")
            for line in value.lines.select_for_update().filter(side="bank"):
                tx = BankTransaction.objects.select_for_update().for_tenant(tenant).get(pk=line.bank_transaction_id)
                tx.match_status, tx.is_reconciled, tx.matched_payment_id = "unmatched", False, None
                _clean_and_save(tx)
            value.status, value.reversed_at, value.reversed_by_id, value.reversal_reason = (
                "reversed",
                timezone.now(),
                actor,
                reason_text,
            )
            _clean_and_save(value)
            reconciliation = ReconciliationSession.objects.select_for_update().get(
                pk=value.reconciliation_id, tenant_id=tenant
            )
            cls._recalculate(reconciliation)
            _event(
                tenant,
                "bank_reconciliation.match.reversed",
                "reconciliation_match",
                value.id,
                actor,
                {"reason_provided": True},
            )
            return value

    @classmethod
    def generate_candidates(
        cls, tenant_id: UUID | str, reconciliation_id: UUID | str, actor_id: UUID | str, idempotency_key: str
    ) -> CandidateResult:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        _text(idempotency_key, "idempotency_key", 128)
        with transaction.atomic():
            reconciliation = cls._locked(tenant, reconciliation_id)
            if reconciliation.status not in ("draft", "in_progress"):
                raise BankReconciliationError("RECONCILIATION_LOCKED", "Candidates cannot be generated in this state.")
            if _ledger_gateway is None or reconciliation.bank_account.ledger_account_id is None:
                raise BankReconciliationError(
                    "LEDGER_UNAVAILABLE", "No ledger candidate source is configured.", status_code=503
                )
            ledger_rows = _ledger_gateway.list_unreconciled(
                tenant,
                reconciliation.bank_account.ledger_account_id,
                (reconciliation.bank_statement.period_start, reconciliation.bank_statement.period_end),
            )
            from .matching import get_candidate_provider

            bank_rows = list(reconciliation.bank_statement.transactions.filter(match_status="unmatched"))
            candidates = get_candidate_provider("core").generate(tenant, reconciliation, bank_rows, ledger_rows)
            proposals: list[ReconciliationMatch] = []
            for candidate in candidates:
                if (
                    ReconciliationMatch.objects.for_tenant(tenant)
                    .filter(
                        reconciliation=reconciliation,
                        explanation__candidate_key=candidate.candidate_key,
                        status="proposed",
                    )
                    .exists()
                ):
                    continue
                match = ReconciliationMatch.objects.create(
                    tenant_id=tenant,
                    reconciliation=reconciliation,
                    match_type="auto",
                    status="proposed",
                    score=candidate.score,
                    explanation=candidate.explanation,
                    rule=candidate.rule,
                )
                ReconciliationMatchLine.objects.create(
                    tenant_id=tenant,
                    match=match,
                    side="bank",
                    bank_transaction=candidate.bank_transaction,
                    allocated_amount=candidate.amount,
                    currency=reconciliation.bank_account.currency,
                    ledger_entry_type="other",
                )
                ReconciliationMatchLine.objects.create(
                    tenant_id=tenant,
                    match=match,
                    side="ledger",
                    ledger_entry_id=candidate.ledger_entry_id,
                    ledger_entry_type=candidate.ledger_entry_type,
                    allocated_amount=candidate.amount,
                    currency=reconciliation.bank_account.currency,
                )
                candidate.bank_transaction.match_status = "proposed"
                _clean_and_save(candidate.bank_transaction, update_fields=("match_status",))
                proposals.append(match)
            _event(
                tenant,
                "bank_reconciliation.candidates.generated",
                "reconciliation",
                reconciliation.id,
                actor,
                {"proposal_count": len(proposals)},
            )
            return CandidateResult(reconciliation.id, tuple(proposals), len(bank_rows))

    @classmethod
    def submit_review(
        cls, tenant_id: UUID | str, reconciliation_id: UUID | str, actor_id: UUID | str, idempotency_key: str
    ) -> ReconciliationSession:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = cls._locked(tenant, reconciliation_id)
            if value.matches.filter(status="proposed").exists():
                raise BankReconciliationError("REVIEW_BLOCKED", "Resolve every proposed match before review.")
            blockers = list(
                value.bank_statement.transactions.exclude(match_status__in=("matched", "excluded")).values_list(
                    "id", flat=True
                )[:25]
            )
            if blockers:
                raise BankReconciliationError(
                    "REVIEW_BLOCKED",
                    "Match or exclude every transaction before review.",
                    detail={"transaction_ids": [str(item) for item in blockers]},
                )
            _transition_session(value, "submit_review", "review", actor, idempotency_key)
            value.reviewed_by_id, value.reviewed_at = actor, timezone.now()
            _clean_and_save(value)
            _event(tenant, "bank_reconciliation.reconciliation.review_submitted", "reconciliation", value.id, actor)
            return value

    @classmethod
    def return_to_work(
        cls,
        tenant_id: UUID | str,
        reconciliation_id: UUID | str,
        actor_id: UUID | str,
        reason: str,
        idempotency_key: str,
    ) -> ReconciliationSession:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        reason_text = _text(reason, "reason", 500)
        with transaction.atomic():
            value = cls._locked(tenant, reconciliation_id)
            _transition_session(value, "return_to_work", "in_progress", actor, idempotency_key, reason=reason_text)
            _clean_and_save(value)
            _event(
                tenant,
                "bank_reconciliation.reconciliation.returned",
                "reconciliation",
                value.id,
                actor,
                {"reason_provided": True},
            )
            return value

    @classmethod
    def finalize(
        cls, tenant_id: UUID | str, reconciliation_id: UUID | str, actor_id: UUID | str, idempotency_key: str
    ) -> ReconciliationSession:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = cls._locked(tenant, reconciliation_id)
            cls._recalculate(value)
            if abs(value.difference) > value.tolerance:
                raise BankReconciliationError(
                    "VARIANCE_EXCEEDS_TOLERANCE",
                    "Difference exceeds the allowed tolerance.",
                    detail={"difference": str(value.difference), "tolerance": str(value.tolerance)},
                )
            if value.unmatched_amount != MONEY_ZERO:
                raise BankReconciliationError(
                    "UNMATCHED_TRANSACTIONS", "All non-excluded transactions must be fully allocated."
                )
            if value.reviewed_by_id and value.reviewed_by_id == actor:
                raise BankReconciliationError(
                    "SEPARATION_OF_DUTIES", "The reviewer and finalizer must be different people."
                )
            _transition_session(value, "finalize", "finalized", actor, idempotency_key)
            value.finalized_by_id, value.finalized_at = actor, timezone.now()
            _clean_and_save(value)
            statement = BankStatement.objects.select_for_update().get(pk=value.bank_statement_id, tenant_id=tenant)
            statement.status, statement.is_reconciled, statement.reconciled_at = "reconciled", True, value.finalized_at
            _clean_and_save(statement)
            _event(
                tenant,
                "bank_reconciliation.reconciliation.finalized",
                "reconciliation",
                value.id,
                actor,
                {
                    "statement_id": str(statement.id),
                    "matched_amount": str(value.matched_amount),
                    "difference": str(value.difference),
                },
            )
            return value

    @classmethod
    def void(
        cls,
        tenant_id: UUID | str,
        reconciliation_id: UUID | str,
        actor_id: UUID | str,
        reason: str,
        idempotency_key: str,
    ) -> ReconciliationSession:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        reason_text = _text(reason, "reason", 500)
        with transaction.atomic():
            value = cls._locked(tenant, reconciliation_id)
            _transition_session(value, "void", "void", actor, idempotency_key, reason=reason_text)
            _clean_and_save(value)
            statement = BankStatement.objects.select_for_update().get(pk=value.bank_statement_id, tenant_id=tenant)
            statement.status = "imported"
            _clean_and_save(statement, update_fields=("status",))
            _event(
                tenant,
                "bank_reconciliation.reconciliation.voided",
                "reconciliation",
                value.id,
                actor,
                {"reason_provided": True},
            )
            return value

    @classmethod
    def summary(cls, tenant_id: UUID | str, reconciliation_id: UUID | str) -> ReconciliationSummary:
        value = cls.get(tenant_id, reconciliation_id)
        blockers: list[str] = []
        if value.matches.filter(status="proposed").exists():
            blockers.append("Resolve proposed matches.")
        if value.unmatched_amount != MONEY_ZERO:
            blockers.append("Allocate or exclude unmatched transactions.")
        if abs(value.difference) > value.tolerance:
            blockers.append("Bring the difference within tolerance.")
        return ReconciliationSummary(
            value.id,
            value.statement_balance,
            value.ledger_balance,
            value.matched_amount,
            value.unmatched_amount,
            value.difference,
            value.tolerance,
            not blockers[:2],
            value.status == "review" and not blockers,
            tuple(blockers),
        )

    @classmethod
    def export_report(
        cls,
        tenant_id: UUID | str,
        reconciliation_id: UUID | str,
        actor_id: UUID | str,
        report_format: str = "csv",
    ) -> Iterable[bytes]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        value = cls.get(tenant, reconciliation_id)
        if value.status != "finalized":
            raise BankReconciliationError("REPORT_NOT_READY", "Only finalized evidence can be exported.")
        if report_format not in {"csv", "pdf"}:
            raise BankReconciliationError("UNSUPPORTED_REPORT_FORMAT", "Report format must be csv or pdf.")
        _event(tenant, "bank_reconciliation.reconciliation.report_exported", "reconciliation", value.id, actor)
        matches = value.matches.prefetch_related("lines").order_by("created_at", "id")
        if report_format == "pdf":
            lines = [
                "SARAISE Bank Reconciliation Evidence",
                f"Reconciliation: {value.id}",
                f"Status: {value.status}",
                f"Statement balance: {value.statement_balance}",
                f"Ledger balance: {value.ledger_balance}",
                f"Matched amount: {value.matched_amount}",
                f"Unmatched amount: {value.unmatched_amount}",
                f"Difference: {value.difference}",
                f"Tolerance: {value.tolerance}",
                f"Reviewed by: {value.reviewed_by_id or ''}",
                f"Finalized by: {value.finalized_by_id or ''}",
                "Match evidence:",
            ]
            for match in matches:
                lines.append(f"{match.id} | {match.match_type} | {match.status} | score {match.score or ''}")
                for line in match.lines.all():
                    reference = line.bank_transaction_id or line.ledger_entry_id or ""
                    lines.append(f"  {line.side} | {reference} | {line.allocated_amount} {line.currency}")
            yield _pdf_document(lines)
            return
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            (
                "reconciliation_id",
                "status",
                "statement_balance",
                "ledger_balance",
                "matched_amount",
                "unmatched_amount",
                "difference",
                "tolerance",
            )
        )
        writer.writerow(
            (
                value.id,
                value.status,
                value.statement_balance,
                value.ledger_balance,
                value.matched_amount,
                value.unmatched_amount,
                value.difference,
                value.tolerance,
            )
        )
        writer.writerow(())
        writer.writerow(("transition_command", "from", "to", "occurred_at", "actor_id", "reason"))
        for item in value.transition_history:
            metadata = item.get("metadata", {})
            writer.writerow(
                (
                    item.get("command", ""),
                    item.get("from_state", ""),
                    item.get("to_state", ""),
                    item.get("occurred_at", ""),
                    metadata.get("actor_id", ""),
                    metadata.get("reason", ""),
                )
            )
        writer.writerow(())
        writer.writerow(
            ("match_id", "match_type", "match_status", "score", "side", "reference_id", "allocated_amount", "currency")
        )
        for match in matches:
            for line in match.lines.all():
                writer.writerow(
                    (
                        match.id,
                        match.match_type,
                        match.status,
                        match.score or "",
                        line.side,
                        line.bank_transaction_id or line.ledger_entry_id or "",
                        line.allocated_amount,
                        line.currency,
                    )
                )
        yield buffer.getvalue().encode("utf-8")

    @staticmethod
    def reconcile_statement(bank_statement: BankStatement) -> BankStatement:
        """Legacy entrypoint retained only to fail closed; certification needs a session."""

        raise BankReconciliationError(
            "RECONCILIATION_REQUIRED", "Create and finalize a reconciliation session instead."
        )


__all__ = [
    "AcceptedImport",
    "BankAccountService",
    "BankReconciliationError",
    "CandidateResult",
    "LedgerGateway",
    "MatchingRuleService",
    "ReconciliationService",
    "ReconciliationSummary",
    "StatementImportService",
    "StatementService",
    "register_ledger_gateway",
]
