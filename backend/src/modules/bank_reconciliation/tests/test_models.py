"""
Model tests for Bank Reconciliation module.
"""

import uuid
import pytest

from src.modules.bank_reconciliation.models import BankAccount


@pytest.mark.django_db
class TestBankAccountModel:
    """Test BankAccount model."""

    def test_create_bank_account(self):
        """Test creating a bank account."""
        tenant_id = uuid.uuid4()
        account = BankAccount.objects.create(
            tenant_id=tenant_id,
            account_number="ACC-001",
            bank_name="Test Bank",
            account_name="Test Account",
        )
        assert account.account_number == "ACC-001"
        assert account.bank_name == "Test Bank"
        assert account.is_active is True
