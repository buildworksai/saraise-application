"""Statement parser contracts and built-in, dependency-free file adapters.

Parsers return normalized immutable values and never persist data.  The import
service owns tenant validation, atomic writes, arithmetic checks, and durable
failure evidence.  Paid modules may register additional parsers under stable
keys without importing their models into this module.
"""

from __future__ import annotations

import csv
import io
import re
import threading
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from typing import BinaryIO, Protocol, TextIO, runtime_checkable
from uuid import UUID

MAX_STATEMENT_BYTES = 25 * 1024 * 1024
MAX_TRANSACTIONS = 100_000
MAX_DIAGNOSTICS = 100
SUPPORTED_FORMATS = ("csv", "ofx", "qif", "bai2", "mt940", "camt053")
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d/%m/%y",
    "%m/%d/%y",
    "%Y%m%d",
    "%y%m%d",
)


class StatementParserError(ValueError):
    """A sanitized, stable parsing failure safe for durable diagnostics."""

    def __init__(self, code: str, message: str, *, row: int | None = None, field: str | None = None) -> None:
        self.code = code[:64]
        self.row = row
        self.field = field[:64] if field else None
        super().__init__(message[:300])

    def as_diagnostic(self) -> dict[str, object]:
        result: dict[str, object] = {"code": self.code, "message": str(self)}
        if self.row is not None:
            result["row"] = self.row
        if self.field:
            result["field"] = self.field
        return result


class ParserNotRegistered(LookupError):
    """Raised when an import requests an unavailable parser explicitly."""


class ParserAlreadyRegistered(ValueError):
    """Raised when extension load order would otherwise replace a parser."""


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    """Sanitized optional-dependency readiness safe for health responses."""

    available: bool
    code: str
    status: str = "available"

    def __post_init__(self) -> None:
        if self.status not in {"available", "degraded", "not_configured"}:
            raise ValueError("dependency status is invalid")
        if not self.code or len(self.code) > 64:
            raise ValueError("dependency code must be bounded")


@dataclass(frozen=True, slots=True)
class VerifiedLedgerBalance:
    amount: Decimal
    currency: str
    as_of_date: date
    verification_token: str
    provider_key: str
    provider_version: str


@runtime_checkable
class LedgerGateway(Protocol):
    key: str
    version: str

    def validate_account(self, tenant_id: UUID, ledger_account_id: UUID) -> None: ...

    def get_balance(self, tenant_id: UUID, ledger_account_id: UUID, as_of_date: date) -> VerifiedLedgerBalance: ...

    def list_unreconciled(
        self, tenant_id: UUID, ledger_account_id: UUID, date_range: tuple[date, date]
    ) -> Sequence[object]: ...

    def health(self) -> DependencyHealth: ...


@runtime_checkable
class AdjustmentPublisher(Protocol):
    key: str
    version: str

    def request_adjustment(
        self,
        tenant_id: UUID,
        reconciliation_id: UUID,
        payload: Mapping[str, object],
        idempotency_key: str,
    ) -> UUID: ...


@dataclass(frozen=True, slots=True)
class ParsedTransaction:
    transaction_date: date
    description: str
    amount: Decimal
    sequence_number: int
    external_id: str = ""
    value_date: date | None = None
    running_balance: Decimal | None = None
    reference_number: str = ""
    counterparty_name: str = ""
    counterparty_account_masked: str = ""
    source_data: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence_number < 1:
            raise StatementParserError("INVALID_SEQUENCE", "Transaction sequence must be positive.")
        amount = _money(self.amount, "amount")
        if amount == 0:
            raise StatementParserError("ZERO_AMOUNT", "Transaction amount must not be zero.")
        object.__setattr__(self, "amount", amount)
        if self.running_balance is not None:
            object.__setattr__(self, "running_balance", _money(self.running_balance, "running_balance"))
        description = " ".join(str(self.description).split())
        if not description or len(description) > 500:
            raise StatementParserError("INVALID_DESCRIPTION", "Transaction description is required and bounded.")
        object.__setattr__(self, "description", description)
        if len(self.external_id) > 128 or len(self.reference_number) > 100:
            raise StatementParserError("FIELD_TOO_LONG", "Transaction identifier is too long.")
        if not isinstance(self.source_data, Mapping):
            raise StatementParserError("INVALID_SOURCE_DATA", "Normalized source data must be an object.")

    def as_mapping(self) -> dict[str, object]:
        """Return the service-layer create contract without exposing raw input."""
        return {
            "sequence_number": self.sequence_number,
            "external_id": self.external_id,
            "transaction_date": self.transaction_date,
            "value_date": self.value_date,
            "description": self.description,
            "amount": self.amount,
            "running_balance": self.running_balance,
            "reference_number": self.reference_number,
            "counterparty_name": self.counterparty_name,
            "counterparty_account_masked": self.counterparty_account_masked,
            "source_data": dict(self.source_data),
        }


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    statement_reference: str
    period_start: date
    period_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    transactions: tuple[ParsedTransaction, ...]
    currency: str | None = None
    account_identifier: str = ""
    parser_key: str = ""
    parser_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.period_start > self.period_end:
            raise StatementParserError("INVALID_PERIOD", "Statement period start exceeds period end.")
        if not self.statement_reference or len(self.statement_reference) > 100:
            raise StatementParserError("INVALID_REFERENCE", "Statement reference is required and bounded.")
        object.__setattr__(self, "opening_balance", _money(self.opening_balance, "opening_balance"))
        object.__setattr__(self, "closing_balance", _money(self.closing_balance, "closing_balance"))
        if len(self.transactions) > MAX_TRANSACTIONS:
            raise StatementParserError("ROW_LIMIT_EXCEEDED", "Statement exceeds the transaction row limit.")
        if self.currency is not None:
            currency = self.currency.strip().upper()
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise StatementParserError("INVALID_CURRENCY", "Statement currency must be an ISO 4217 code.")
            object.__setattr__(self, "currency", currency)

    @property
    def transaction_total(self) -> Decimal:
        return sum((item.amount for item in self.transactions), Decimal("0.0000"))

    @property
    def calculated_closing_balance(self) -> Decimal:
        return self.opening_balance + self.transaction_total


@runtime_checkable
class StatementParser(Protocol):
    key: str
    version: str

    def parse(self, stream: BinaryIO | TextIO, mapping: Mapping[str, str] | None = None) -> ParsedStatement: ...


def _money(value: object, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, TypeError, ValueError, AttributeError) as exc:
        raise StatementParserError(
            "INVALID_DECIMAL", f"{field_name} must be a finite decimal.", field=field_name
        ) from exc
    if not amount.is_finite():
        raise StatementParserError("INVALID_DECIMAL", f"{field_name} must be a finite decimal.", field=field_name)
    return amount.quantize(Decimal("0.0001"))


def _date(value: object, field_name: str = "date") -> date:
    text = str(value).strip()
    # OFX permits a timestamp suffix and timezone annotation.
    text = re.sub(r"\[.*$", "", text)
    if re.fullmatch(r"\d{14}(?:\.\d+)?", text):
        text = text[:8]
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise StatementParserError("INVALID_DATE", f"{field_name} must be a supported calendar date.", field=field_name)


def _read_text(stream: BinaryIO | TextIO) -> str:
    if not hasattr(stream, "read"):
        raise TypeError("statement stream must be readable")
    content = stream.read(MAX_STATEMENT_BYTES + 1)
    if isinstance(content, str):
        byte_size = len(content.encode("utf-8"))
        text = content
    elif isinstance(content, (bytes, bytearray)):
        byte_size = len(content)
        try:
            text = bytes(content).decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = bytes(content).decode("latin-1")
            except UnicodeDecodeError as exc:
                raise StatementParserError("INVALID_ENCODING", "Statement text encoding is unsupported.") from exc
    else:
        raise StatementParserError("INVALID_CONTENT", "Statement content must be text or bytes.")
    if byte_size > MAX_STATEMENT_BYTES:
        raise StatementParserError("FILE_TOO_LARGE", "Statement file exceeds the configured size limit.")
    if not text.strip():
        raise StatementParserError("EMPTY_FILE", "Statement file is empty.")
    return text


def _reference(value: str, fallback: str) -> str:
    normalized = " ".join(value.split()).strip()[:100]
    return normalized or fallback[:100]


class CSVStatementParser:
    key = "csv"
    version = "1.0"
    _defaults = {
        "date": "date",
        "description": "description",
        "amount": "amount",
        "debit": "debit",
        "credit": "credit",
        "reference": "reference",
        "external_id": "external_id",
        "running_balance": "running_balance",
        "value_date": "value_date",
        "counterparty": "counterparty",
    }

    def parse(self, stream: BinaryIO | TextIO, mapping: Mapping[str, str] | None = None) -> ParsedStatement:
        text = _read_text(stream)
        columns = {**self._defaults, **dict(mapping or {})}
        allowed = set(self._defaults) | {"statement_reference", "opening_balance", "closing_balance", "currency"}
        if set(columns) - allowed:
            raise StatementParserError("INVALID_MAPPING", "CSV mapping contains unsupported semantic fields.")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise StatementParserError("MISSING_HEADER", "CSV header row is required.")
        required = {columns["date"], columns["description"]}
        amount_present = columns["amount"] in reader.fieldnames
        split_present = columns["debit"] in reader.fieldnames and columns["credit"] in reader.fieldnames
        if not required.issubset(reader.fieldnames) or not (amount_present or split_present):
            raise StatementParserError(
                "MISSING_COLUMN", "CSV requires date, description, and amount or debit/credit columns."
            )
        transactions: list[ParsedTransaction] = []
        for line_number, row in enumerate(reader, start=2):
            if len(transactions) >= MAX_TRANSACTIONS:
                raise StatementParserError("ROW_LIMIT_EXCEEDED", "CSV exceeds the transaction row limit.")
            try:
                if amount_present:
                    amount = _money(row.get(columns["amount"], ""), "amount")
                else:
                    debit = _money(row.get(columns["debit"]) or "0", "debit")
                    credit = _money(row.get(columns["credit"]) or "0", "credit")
                    if debit and credit:
                        raise StatementParserError("AMBIGUOUS_AMOUNT", "A row cannot contain both debit and credit.")
                    amount = credit - abs(debit)
                running = row.get(columns["running_balance"], "").strip()
                value_date = row.get(columns["value_date"], "").strip()
                transactions.append(
                    ParsedTransaction(
                        sequence_number=len(transactions) + 1,
                        transaction_date=_date(row.get(columns["date"], "")),
                        value_date=_date(value_date, "value_date") if value_date else None,
                        description=row.get(columns["description"], ""),
                        amount=amount,
                        external_id=row.get(columns["external_id"], "").strip(),
                        reference_number=row.get(columns["reference"], "").strip(),
                        running_balance=_money(running, "running_balance") if running else None,
                        counterparty_name=row.get(columns["counterparty"], "").strip(),
                        source_data={"source_row": line_number},
                    )
                )
            except StatementParserError as exc:
                raise StatementParserError(exc.code, str(exc), row=line_number, field=exc.field) from exc
        if not transactions:
            raise StatementParserError("NO_TRANSACTIONS", "CSV contains no transaction rows.")
        last = transactions[-1]
        opening = _money((mapping or {}).get("opening_balance", "0"), "opening_balance")
        calculated = opening + sum((item.amount for item in transactions), Decimal("0"))
        closing = _money((mapping or {}).get("closing_balance", calculated), "closing_balance")
        return ParsedStatement(
            statement_reference=_reference(
                (mapping or {}).get("statement_reference", ""), f"CSV-{last.transaction_date.isoformat()}"
            ),
            period_start=min(item.transaction_date for item in transactions),
            period_end=max(item.transaction_date for item in transactions),
            opening_balance=opening,
            closing_balance=closing,
            transactions=tuple(transactions),
            currency=(mapping or {}).get("currency") or None,
            parser_key=self.key,
            parser_version=self.version,
        )


def _tags(block: str) -> dict[str, str]:
    # Works for both OFX SGML (<TAG>value) and XML-ish payloads.
    result: dict[str, str] = {}
    for name, value in re.findall(r"<([A-Za-z0-9_.:-]+)>\s*([^<\r\n]+)", block):
        result[name.upper().split(":")[-1]] = value.strip()
    return result


class OFXStatementParser:
    key = "ofx"
    version = "1.0"

    def parse(self, stream: BinaryIO | TextIO, mapping: Mapping[str, str] | None = None) -> ParsedStatement:
        del mapping
        text = _read_text(stream)
        upper = text.upper()
        blocks = re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>|</BANKTRANLIST>))", text, re.I | re.S)
        if not blocks:
            raise StatementParserError("NO_TRANSACTIONS", "OFX contains no statement transactions.")
        transactions = []
        for index, block in enumerate(blocks, 1):
            values = _tags(block)
            transactions.append(
                ParsedTransaction(
                    sequence_number=index,
                    transaction_date=_date(values.get("DTPOSTED", "")),
                    description=values.get("MEMO") or values.get("NAME") or values.get("TRNTYPE", "Transaction"),
                    amount=_money(values.get("TRNAMT", ""), "amount"),
                    external_id=values.get("FITID", "")[:128],
                    reference_number=(values.get("CHECKNUM") or values.get("REFNUM", ""))[:100],
                    counterparty_name=values.get("NAME", "")[:255],
                    source_data={"transaction_kind": values.get("TRNTYPE", "")[:20]},
                )
            )
        header = _tags(upper[: upper.find("<STMTTRN>") if "<STMTTRN>" in upper else len(upper)])
        ledger = _tags(text[text.upper().rfind("<LEDGERBAL>") :])
        closing = _money(ledger.get("BALAMT", "0"), "closing_balance")
        total = sum((item.amount for item in transactions), Decimal("0"))
        start = _date(header.get("DTSTART", min(item.transaction_date for item in transactions)))
        end = _date(header.get("DTEND", max(item.transaction_date for item in transactions)))
        return ParsedStatement(
            statement_reference=_reference(header.get("STMTTRNUID", ""), f"OFX-{end.isoformat()}"),
            period_start=start,
            period_end=end,
            opening_balance=closing - total,
            closing_balance=closing,
            transactions=tuple(transactions),
            currency=header.get("CURDEF") or None,
            account_identifier=header.get("ACCTID", "")[-4:],
            parser_key=self.key,
            parser_version=self.version,
        )


class QIFStatementParser:
    key = "qif"
    version = "1.0"

    def parse(self, stream: BinaryIO | TextIO, mapping: Mapping[str, str] | None = None) -> ParsedStatement:
        text = _read_text(stream)
        text = re.sub(r"(?m)^!Type:[^\r\n]*\r?\n?", "", text)
        records = [part for part in re.split(r"(?m)^\^\s*$", text) if part.strip()]
        transactions = []
        balance_hint: Decimal | None = None
        for record in records:
            values: dict[str, str] = {}
            for line in record.splitlines():
                if line and line[0] in "DTPMNLA":
                    values.setdefault(line[0], line[1:].strip())
            if not values.get("D") or not values.get("T"):
                continue
            if values.get("L", "").lower().startswith("[balance"):
                balance_hint = _money(values["T"], "closing_balance")
                continue
            transactions.append(
                ParsedTransaction(
                    sequence_number=len(transactions) + 1,
                    transaction_date=_date(values["D"]),
                    description=values.get("M") or values.get("P") or "Transaction",
                    amount=_money(values["T"], "amount"),
                    external_id=values.get("N", "")[:128],
                    reference_number=values.get("N", "")[:100],
                    counterparty_name=values.get("P", "")[:255],
                    source_data={"category": values.get("L", "")[:100]},
                )
            )
        if not transactions:
            raise StatementParserError("NO_TRANSACTIONS", "QIF contains no transaction records.")
        total = sum((item.amount for item in transactions), Decimal("0"))
        opening = _money((mapping or {}).get("opening_balance", "0"), "opening_balance")
        closing = balance_hint if balance_hint is not None else opening + total
        end = max(item.transaction_date for item in transactions)
        return ParsedStatement(
            statement_reference=_reference((mapping or {}).get("statement_reference", ""), f"QIF-{end.isoformat()}"),
            period_start=min(item.transaction_date for item in transactions),
            period_end=end,
            opening_balance=opening,
            closing_balance=closing,
            transactions=tuple(transactions),
            currency=(mapping or {}).get("currency") or None,
            parser_key=self.key,
            parser_version=self.version,
        )


class BAI2StatementParser:
    key = "bai2"
    version = "1.0"

    def parse(self, stream: BinaryIO | TextIO, mapping: Mapping[str, str] | None = None) -> ParsedStatement:
        text = _read_text(stream)
        records = [line.rstrip("/").split(",") for line in text.splitlines() if line.strip()]
        account = next((row for row in records if row[0] == "03"), None)
        if account is None:
            raise StatementParserError("MISSING_ACCOUNT", "BAI2 account header is missing.")
        currency = account[2] if len(account) > 2 and re.fullmatch(r"[A-Z]{3}", account[2]) else None
        opening = Decimal("0")
        closing: Decimal | None = None
        # Type codes 010/015 are opening and 040/045 are closing balances.
        for offset in range(3, len(account) - 2, 3):
            code = account[offset]
            if code in {"010", "015"}:
                opening = _money(account[offset + 1], "opening_balance") / Decimal("100")
            elif code in {"040", "045"}:
                closing = _money(account[offset + 1], "closing_balance") / Decimal("100")
        transactions = []
        group_header = next((row for row in records if row[0] == "02"), None)
        source_date = group_header[4] if group_header and len(group_header) > 4 else ""
        if not source_date:
            source_date = (mapping or {}).get("statement_date", "")
        if not source_date:
            raise StatementParserError("MISSING_DATE", "BAI2 group as-of date is missing.")
        current_date = _date(source_date)
        for row in records:
            if row[0] != "16" or len(row) < 3:
                continue
            amount = _money(row[2], "amount") / Decimal("100")
            if row[1].startswith(("4", "5")):
                amount = -abs(amount)
            reference = row[4] if len(row) > 4 else ""
            description = row[6] if len(row) > 6 else f"BAI2 type {row[1]}"
            transactions.append(
                ParsedTransaction(
                    sequence_number=len(transactions) + 1,
                    transaction_date=current_date,
                    description=description,
                    amount=amount,
                    external_id=reference[:128],
                    reference_number=reference[:100],
                    source_data={"type_code": row[1][:3]},
                )
            )
        if not transactions:
            raise StatementParserError("NO_TRANSACTIONS", "BAI2 contains no detail records.")
        closing = (
            closing if closing is not None else opening + sum((item.amount for item in transactions), Decimal("0"))
        )
        return ParsedStatement(
            statement_reference=_reference(
                (mapping or {}).get("statement_reference", ""),
                f"BAI2-{account[1][-4:]}-{current_date.isoformat()}",
            ),
            period_start=current_date,
            period_end=current_date,
            opening_balance=opening,
            closing_balance=closing,
            transactions=tuple(transactions),
            currency=currency,
            account_identifier=account[1][-4:],
            parser_key=self.key,
            parser_version=self.version,
        )


class MT940StatementParser:
    key = "mt940"
    version = "1.0"
    _transaction = re.compile(
        r"(?m)^:61:(?P<date>\d{6})(?:\d{4})?(?P<dc>[R]?[CD])" r"(?P<amount>[\d,]+)(?:[A-Z])?(?P<ref>[^\r\n]*)"
    )

    def parse(self, stream: BinaryIO | TextIO, mapping: Mapping[str, str] | None = None) -> ParsedStatement:
        text = _read_text(stream)
        opening_match = re.search(
            r"(?m)^:60[FM]:(?P<dc>[CD])(?P<date>\d{6})(?P<currency>[A-Z]{3})(?P<amount>[\d,]+)",
            text,
        )
        closing_match = re.search(
            r"(?m)^:62[FM]:(?P<dc>[CD])(?P<date>\d{6})(?P<currency>[A-Z]{3})(?P<amount>[\d,]+)",
            text,
        )
        if not opening_match or not closing_match:
            raise StatementParserError("MISSING_BALANCE", "MT940 opening and closing balances are required.")
        transactions = []
        matches = list(self._transaction.finditer(text))
        for index, match in enumerate(matches, 1):
            next_start = matches[index].start() if index < len(matches) else len(text)
            continuation = text[match.end() : next_start]
            info = re.search(r"(?m)^:86:(.*(?:\n(?!:)[^\n]*)*)", continuation)
            raw_ref = match.group("ref").strip()
            description = " ".join((info.group(1) if info else raw_ref or "Transaction").split())
            amount = _money(match.group("amount").replace(",", "."), "amount")
            if match.group("dc").endswith("D"):
                amount = -abs(amount)
            transactions.append(
                ParsedTransaction(
                    sequence_number=index,
                    transaction_date=_date(match.group("date")),
                    description=description,
                    amount=amount,
                    external_id=raw_ref[:128],
                    reference_number=raw_ref[:100],
                    source_data={"funds_code": match.group("dc")},
                )
            )
        if not transactions:
            raise StatementParserError("NO_TRANSACTIONS", "MT940 contains no transaction records.")
        opening = _money(opening_match.group("amount").replace(",", "."), "opening_balance")
        closing = _money(closing_match.group("amount").replace(",", "."), "closing_balance")
        if opening_match.group("dc") == "D":
            opening = -opening
        if closing_match.group("dc") == "D":
            closing = -closing
        period_end = _date(closing_match.group("date"))
        reference_match = re.search(r"(?m)^:20:(.+)$", text)
        account_match = re.search(r"(?m)^:25:(.+)$", text)
        return ParsedStatement(
            statement_reference=_reference(
                reference_match.group(1) if reference_match else "", f"MT940-{period_end.isoformat()}"
            ),
            period_start=_date(opening_match.group("date")),
            period_end=period_end,
            opening_balance=opening,
            closing_balance=closing,
            transactions=tuple(transactions),
            currency=closing_match.group("currency"),
            account_identifier=(account_match.group(1).strip()[-4:] if account_match else ""),
            parser_key=self.key,
            parser_version=self.version,
        )


def _xml_text(element: ET.Element, suffixes: Sequence[str]) -> str:
    for child in element.iter():
        local = child.tag.rsplit("}", 1)[-1]
        if local in suffixes and child.text and child.text.strip():
            return child.text.strip()
    return ""


def _xml_nested_date(element: ET.Element, container_name: str) -> date | None:
    container = next(
        (child for child in element.iter() if child.tag.rsplit("}", 1)[-1] == container_name),
        None,
    )
    if container is None:
        return None
    value = _xml_text(container, ("Dt", "DtTm"))
    return _date(value[:10], container_name) if value else None


class CAMT053StatementParser:
    key = "camt053"
    version = "1.0"

    def parse(self, stream: BinaryIO | TextIO, mapping: Mapping[str, str] | None = None) -> ParsedStatement:
        text = _read_text(stream)
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise StatementParserError("UNSAFE_XML", "XML document type declarations are not permitted.")
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise StatementParserError("MALFORMED_XML", "CAMT.053 XML is malformed.") from exc
        statement = next((node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "Stmt"), None)
        if statement is None:
            raise StatementParserError("MISSING_STATEMENT", "CAMT.053 statement element is missing.")
        entries = [node for node in statement.iter() if node.tag.rsplit("}", 1)[-1] == "Ntry"]
        transactions = []
        for index, entry in enumerate(entries, 1):
            amount_node = next((node for node in entry.iter() if node.tag.rsplit("}", 1)[-1] == "Amt"), None)
            if amount_node is None or not amount_node.text:
                raise StatementParserError("MISSING_AMOUNT", "CAMT.053 entry amount is missing.", row=index)
            amount = _money(amount_node.text, "amount")
            if _xml_text(entry, ("CdtDbtInd",)) == "DBIT":
                amount = -abs(amount)
            booking_date = _xml_nested_date(entry, "BookgDt")
            if booking_date is None:
                raise StatementParserError("MISSING_DATE", "CAMT.053 entry booking date is missing.", row=index)
            transactions.append(
                ParsedTransaction(
                    sequence_number=index,
                    transaction_date=booking_date,
                    value_date=_xml_nested_date(entry, "ValDt"),
                    description=_xml_text(entry, ("AddtlNtryInf", "Ustrd", "Nm")) or "CAMT transaction",
                    amount=amount,
                    external_id=_xml_text(entry, ("NtryRef", "AcctSvcrRef"))[:128],
                    reference_number=_xml_text(entry, ("EndToEndId", "AcctSvcrRef"))[:100],
                    source_data={"status": _xml_text(entry, ("Sts",))[:20]},
                )
            )
        if not transactions:
            raise StatementParserError("NO_TRANSACTIONS", "CAMT.053 contains no entries.")
        balances: dict[str, Decimal] = {}
        currency = None
        for balance in (node for node in statement.iter() if node.tag.rsplit("}", 1)[-1] == "Bal"):
            code = _xml_text(balance, ("Cd",))
            amount_node = next((node for node in balance.iter() if node.tag.rsplit("}", 1)[-1] == "Amt"), None)
            if amount_node is not None and amount_node.text:
                amount = _money(amount_node.text, "balance")
                if _xml_text(balance, ("CdtDbtInd",)) == "DBIT":
                    amount = -abs(amount)
                balances[code] = amount
                currency = amount_node.attrib.get("Ccy", currency)
        total = sum((item.amount for item in transactions), Decimal("0"))
        opening = next((balances[key] for key in ("OPBD", "PRCD", "ITBD") if key in balances), Decimal("0"))
        closing = next((balances[key] for key in ("CLBD", "CLAV", "ITAV") if key in balances), opening + total)
        start = min(item.transaction_date for item in transactions)
        end = max(item.transaction_date for item in transactions)
        account = next(
            (child for child in statement.iter() if child.tag.rsplit("}", 1)[-1] == "Acct"),
            None,
        )
        account_identifier = _xml_text(account, ("IBAN", "Id"))[-4:] if account is not None else ""
        return ParsedStatement(
            statement_reference=_reference(_xml_text(statement, ("Id",)), f"CAMT053-{end.isoformat()}"),
            period_start=start,
            period_end=end,
            opening_balance=opening,
            closing_balance=closing,
            transactions=tuple(transactions),
            currency=currency,
            account_identifier=account_identifier,
            parser_key=self.key,
            parser_version=self.version,
        )


_parser_lock = threading.RLock()
_parsers: dict[str, StatementParser] = {}
_ledger_gateway: LedgerGateway | None = None


def register_parser(key: str, parser: StatementParser, *, replace: bool = False) -> StatementParser:
    normalized = str(key).strip().lower().replace(".", "")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,79}", normalized):
        raise ValueError("parser key must be a bounded stable identifier")
    if not isinstance(parser, StatementParser):
        raise TypeError("parser must implement StatementParser")
    if parser.key != normalized:
        raise ValueError("parser key does not match its registration key")
    with _parser_lock:
        if normalized in _parsers and not replace:
            raise ParserAlreadyRegistered(f"Parser {normalized!r} is already registered")
        _parsers[normalized] = parser
    return parser


def unregister_parser(key: str) -> StatementParser | None:
    with _parser_lock:
        return _parsers.pop(str(key).strip().lower().replace(".", ""), None)


def get_parser(format_key: str) -> StatementParser:
    normalized = str(format_key).strip().lower().replace(".", "")
    with _parser_lock:
        try:
            return _parsers[normalized]
        except KeyError as exc:
            raise ParserNotRegistered(f"No statement parser is registered for {normalized!r}") from exc


def parser_registry_status() -> dict[str, object]:
    """Return only bounded capability metadata; never provider configuration."""
    with _parser_lock:
        registered = tuple(sorted(_parsers))
        versions = {key: str(_parsers[key].version)[:20] for key in registered}
    missing = tuple(key for key in SUPPORTED_FORMATS if key not in registered)
    return {"ready": not missing, "registered": registered, "missing": missing, "versions": versions}


def configure_ledger_gateway(gateway: LedgerGateway | None) -> None:
    """Install or explicitly remove the optional accounting integration."""
    if gateway is not None and not isinstance(gateway, LedgerGateway):
        raise TypeError("ledger gateway must implement LedgerGateway")
    global _ledger_gateway
    with _parser_lock:
        _ledger_gateway = gateway


def get_ledger_gateway() -> LedgerGateway:
    with _parser_lock:
        if _ledger_gateway is None:
            raise ParserNotRegistered("No ledger gateway is configured")
        return _ledger_gateway


def ledger_gateway_status() -> DependencyHealth:
    with _parser_lock:
        gateway = _ledger_gateway
    if gateway is None:
        return DependencyHealth(False, "not_configured", "not_configured")
    try:
        result = gateway.health()
    except Exception:
        return DependencyHealth(False, "dependency_unavailable", "degraded")
    if not isinstance(result, DependencyHealth):
        return DependencyHealth(False, "invalid_health_contract", "degraded")
    return result


def safe_source_filename(value: str) -> str:
    """Return a basename after rejecting path-like upload names."""
    name = PurePath(str(value).replace("\\", "/")).name.strip()
    if not name or name in {".", ".."} or len(name) > 255:
        raise ValueError("source filename is invalid")
    return name


for _parser in (
    CSVStatementParser(),
    OFXStatementParser(),
    QIFStatementParser(),
    BAI2StatementParser(),
    MT940StatementParser(),
    CAMT053StatementParser(),
):
    register_parser(_parser.key, _parser)


__all__ = [
    "BAI2StatementParser",
    "CAMT053StatementParser",
    "CSVStatementParser",
    "AdjustmentPublisher",
    "DependencyHealth",
    "LedgerGateway",
    "MAX_DIAGNOSTICS",
    "MAX_STATEMENT_BYTES",
    "MAX_TRANSACTIONS",
    "MT940StatementParser",
    "OFXStatementParser",
    "ParsedStatement",
    "ParsedTransaction",
    "ParserAlreadyRegistered",
    "ParserNotRegistered",
    "QIFStatementParser",
    "SUPPORTED_FORMATS",
    "StatementParser",
    "StatementParserError",
    "VerifiedLedgerBalance",
    "configure_ledger_gateway",
    "get_parser",
    "get_ledger_gateway",
    "ledger_gateway_status",
    "parser_registry_status",
    "register_parser",
    "safe_source_filename",
    "unregister_parser",
]
