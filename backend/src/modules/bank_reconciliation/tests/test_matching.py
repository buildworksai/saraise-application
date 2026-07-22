"""Transparent deterministic candidate scoring tests."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from ..matching import CandidateProviderError, LedgerCandidate, get_candidate_provider


def test_exact_candidate_exposes_every_factor_and_stable_key() -> None:
    tenant, transaction_id, ledger_id = uuid4(), uuid4(), uuid4()
    transaction = {
        "id": transaction_id,
        "tenant_id": tenant,
        "transaction_date": date(2026, 7, 1),
        "amount": Decimal("100"),
        "reference_number": "INV-42",
        "counterparty_name": "ACME Ltd.",
    }
    ledger = LedgerCandidate(
        ledger_id,
        "payment",
        date(2026, 7, 1),
        Decimal("100"),
        "USD",
        reference="INV42",
        counterparty_name="acme ltd",
    )
    result = get_candidate_provider("core").generate(
        tenant, {"tenant_id": tenant, "currency": "USD"}, [transaction], [ledger]
    )
    assert len(result) == 1
    assert result[0].score == Decimal("1.0000")
    assert result[0].explanation["factors"] == {
        "amount": "1.0000",
        "reference": "1.0000",
        "date": "1.0000",
        "counterparty": "1.0000",
    }
    assert result[0].candidate_key.endswith(str(ledger_id))


def test_provider_rejects_cross_tenant_transaction() -> None:
    tenant = uuid4()
    transaction = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "transaction_date": date(2026, 7, 1),
        "amount": "10",
    }
    ledger = LedgerCandidate(uuid4(), "other", date(2026, 7, 1), Decimal("10"), "USD")
    with pytest.raises(CandidateProviderError):
        get_candidate_provider().generate(tenant, {"tenant_id": tenant, "currency": "USD"}, [transaction], [ledger])


def test_provider_filters_currency_mismatch() -> None:
    tenant = uuid4()
    transaction = {
        "id": uuid4(),
        "tenant_id": tenant,
        "transaction_date": date(2026, 7, 1),
        "amount": "10",
    }
    ledger = LedgerCandidate(uuid4(), "other", date(2026, 7, 1), Decimal("10"), "EUR")
    assert (
        get_candidate_provider().generate(tenant, {"tenant_id": tenant, "currency": "USD"}, [transaction], [ledger])
        == ()
    )
