from __future__ import annotations

from decimal import Decimal

import pytest

from ..serializers import BankAccountCreateSerializer, BankAccountDetailSerializer, ManualTransactionCreateSerializer
from .factories import BankAccountFactory

pytestmark = pytest.mark.django_db


def test_account_reads_are_masked_and_decimal_is_fixed() -> None:
    account = BankAccountFactory(
        account_number="SECRET-7890", opening_balance=Decimal("10.5000"), opening_balance_date="2026-01-01"
    )
    data = BankAccountDetailSerializer(account).data
    assert data["masked_account_number"].endswith("7890")
    assert "account_number" not in data and "tenant_id" not in data
    assert data["opening_balance"] == "10.5000"


@pytest.mark.parametrize("field", ["tenant_id", "status", "created_by_id", "account_number_hash"])
def test_create_rejects_server_owned_fields(field: str) -> None:
    payload = {
        "account_number": "ABCD1234",
        "bank_name": "Bank",
        "account_name": "Name",
        "currency": "USD",
        field: "spoofed",
    }
    serializer = BankAccountCreateSerializer(data=payload)
    assert not serializer.is_valid()
    assert field in serializer.errors


def test_transaction_amount_must_be_nonzero() -> None:
    serializer = ManualTransactionCreateSerializer(
        data={"transaction_date": "2026-01-01", "description": "Bad", "amount": "0.0000"}
    )
    assert not serializer.is_valid()
