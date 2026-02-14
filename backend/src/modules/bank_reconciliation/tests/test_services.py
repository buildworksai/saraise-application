"""
Service tests for Bank Reconciliation module.
"""

import uuid
import pytest

from src.modules.bank_reconciliation.models import BankAccount
from src.modules.bank_reconciliation.services import BankAccountService


@pytest.mark.django_db
class TestBankAccountService:
    """Test BankAccountService."""

    def test_create_bank_account(self):
        """Test creating a bank account via service."""
        tenant_id = uuid.uuid4()
        account = BankAccountService.create_bank_account(
            tenant_id=str(tenant_id),
            account_number="ACC-001",
            bank_name="Test Bank",
            account_name="Test Account",
        )

        assert account.account_number == "ACC-001"
        assert account.bank_name == "Test Bank"
        assert str(account.tenant_id) == str(tenant_id)
