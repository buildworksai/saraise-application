from __future__ import annotations

import uuid

import pytest

from ..adapters import ParserNotRegistered, get_parser
from ..services import BankAccountService, BankReconciliationError, register_ledger_gateway


def test_unknown_parser_fails_explicitly() -> None:
    with pytest.raises(ParserNotRegistered):
        get_parser("untrusted-format")


def test_unconfigured_ledger_never_fabricates_validation() -> None:
    register_ledger_gateway(None)
    with pytest.raises(BankReconciliationError) as caught:
        BankAccountService.validate_ledger_account(uuid.uuid4(), uuid.uuid4())
    assert caught.value.status_code == 503
