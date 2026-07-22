"""Golden and malformed-sample tests for built-in statement parsers."""

from decimal import Decimal
from io import BytesIO

import pytest

from ..adapters import StatementParserError, get_parser, parser_registry_status


def test_all_required_parsers_are_registered() -> None:
    status = parser_registry_status()
    assert status["ready"] is True
    assert status["missing"] == ()


def test_csv_parser_normalizes_signed_amounts_and_balances() -> None:
    parsed = get_parser("csv").parse(
        BytesIO(
            b"date,description,debit,credit,reference\n"
            b"2026-07-01,Customer deposit,,100.25,INV-1\n"
            b"2026-07-02,Bank fee,2.25,,FEE-1\n"
        ),
        {"opening_balance": "50", "currency": "usd", "statement_reference": "JUL-2026"},
    )
    assert parsed.statement_reference == "JUL-2026"
    assert parsed.currency == "USD"
    assert parsed.transaction_total == Decimal("98.0000")
    assert parsed.closing_balance == Decimal("148.0000")
    assert parsed.transactions[1].amount == Decimal("-2.2500")
    assert parsed.transactions[0].as_mapping()["source_data"] == {"source_row": 2}


def test_csv_parser_reports_sanitized_row_diagnostic() -> None:
    with pytest.raises(StatementParserError) as failure:
        get_parser("csv").parse(BytesIO(b"date,description,amount\nnot-a-date,Payment,10\n"))
    assert failure.value.code == "INVALID_DATE"
    assert failure.value.row == 2
    assert "Payment" not in str(failure.value)


def test_qif_parser_is_functional() -> None:
    parsed = get_parser("qif").parse(BytesIO(b"!Type:Bank\nD2026-07-01\nT10.50\nPShop\nNREF1\n^\n"))
    assert parsed.transactions[0].reference_number == "REF1"
    assert parsed.transactions[0].amount == Decimal("10.5000")


def test_ofx_parser_is_functional() -> None:
    parsed = get_parser("ofx").parse(
        BytesIO(
            b"<OFX><CURDEF>USD<ACCTID>123456789<DTSTART>20260701<DTEND>20260731"
            b"<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260702<TRNAMT>10.50<FITID>F1<MEMO>Deposit</STMTTRN>"
            b"<LEDGERBAL><BALAMT>110.50<DTASOF>20260731</LEDGERBAL></OFX>"
        )
    )
    assert parsed.account_identifier == "6789"
    assert parsed.opening_balance == Decimal("100.0000")
    assert parsed.transactions[0].external_id == "F1"


def test_bai2_parser_uses_source_as_of_date() -> None:
    parsed = get_parser("bai2").parse(
        BytesIO(
            b"01,SENDER,RECEIVER,260701,1200,1,80,2/\n"
            b"02,RECEIVER,SENDER,1,260701,1200,USD,2/\n"
            b"03,123456789,USD,010,10000,,040,10500,,/\n"
            b"16,195,500,,REF1,,Deposit/\n49,10500,1/\n98,10500,1,4/\n99,10500,1,6/\n"
        )
    )
    assert parsed.period_end.isoformat() == "2026-07-01"
    assert parsed.opening_balance == Decimal("100.0000")
    assert parsed.closing_balance == Decimal("105.0000")


def test_mt940_parser_is_functional() -> None:
    parsed = get_parser("mt940").parse(
        BytesIO(
            b":20:STATEMENT-1\n:25:NL00BANK0123456789\n:60F:C260701EUR100,00\n"
            b":61:260702D2,50NTRFREF1\n:86:Service fee\n:62F:C260702EUR97,50\n"
        )
    )
    assert parsed.currency == "EUR"
    assert parsed.transactions[0].amount == Decimal("-2.5000")
    assert parsed.closing_balance == Decimal("97.5000")


def test_camt_rejects_doctype_before_xml_parse() -> None:
    with pytest.raises(StatementParserError) as failure:
        get_parser("camt053").parse(BytesIO(b"<!DOCTYPE x [<!ENTITY secret SYSTEM 'file:///etc/passwd'>]><x/>"))
    assert failure.value.code == "UNSAFE_XML"


def test_camt053_parser_is_functional() -> None:
    parsed = get_parser("camt053").parse(
        BytesIO(
            b"<Document><BkToCstmrStmt><Stmt><Id>S-1</Id><Acct><Id><IBAN>GB12345678</IBAN></Id></Acct>"
            b"<Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy='GBP'>100.00</Amt>"
            b"<CdtDbtInd>CRDT</CdtDbtInd></Bal>"
            b"<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy='GBP'>110.00</Amt>"
            b"<CdtDbtInd>CRDT</CdtDbtInd></Bal>"
            b"<Ntry><Amt Ccy='GBP'>10.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>"
            b"<BookgDt><Dt>2026-07-02</Dt></BookgDt><NtryRef>N-1</NtryRef>"
            b"<AddtlNtryInf>Deposit</AddtlNtryInf></Ntry></Stmt></BkToCstmrStmt></Document>"
        )
    )
    assert parsed.currency == "GBP"
    assert parsed.closing_balance == Decimal("110.0000")
    assert parsed.transactions[0].amount == Decimal("10.0000")
