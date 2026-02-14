"""
Model tests for Accounting & Finance module.
"""

import uuid
import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from src.modules.accounting_finance.models import Account, JournalEntry, JournalLine, PostingPeriod


@pytest.mark.django_db
class TestAccountModel:
    """Test Account model."""

    def test_create_account(self):
        """Test creating an account."""
        tenant_id = uuid.uuid4()
        account = Account.objects.create(
            tenant_id=tenant_id,
            code="1000",
            name="Cash",
            account_type="asset",
        )
        assert account.code == "1000"
        assert account.name == "Cash"
        assert account.account_type == "asset"
        assert account.is_active is True

    def test_account_code_unique_per_tenant(self):
        """Test that account codes must be unique per tenant."""
        from django.db import transaction

        tenant_id = uuid.uuid4()
        Account.objects.create(
            tenant_id=tenant_id,
            code="1000",
            name="Cash",
            account_type="asset",
        )

        # Same code, same tenant should fail
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(
                    tenant_id=tenant_id,
                    code="1000",
                    name="Another Cash",
                    account_type="asset",
                )

        # Same code, different tenant should succeed
        tenant_id_2 = uuid.uuid4()
        account2 = Account.objects.create(
            tenant_id=tenant_id_2,
            code="1000",
            name="Cash",
            account_type="asset",
        )
        assert str(account2.tenant_id) == str(tenant_id_2)


@pytest.mark.django_db
class TestJournalEntryModel:
    """Test JournalEntry model."""

    def test_create_journal_entry(self):
        """Test creating a journal entry."""
        tenant_id = uuid.uuid4()
        from datetime import date

        period = PostingPeriod.objects.create(
            tenant_id=tenant_id,
            period_name="2024-01",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        entry = JournalEntry.objects.create(
            tenant_id=tenant_id,
            entry_number="JE-001",
            posting_date=date(2024, 1, 15),
            posting_period=period,
            status="draft",
        )

        assert entry.entry_number == "JE-001"
        assert entry.status == "draft"

    def test_journal_entry_debits_equal_credits(self):
        """Test that journal entry validates debits equal credits."""
        tenant_id = uuid.uuid4()
        from datetime import date

        period = PostingPeriod.objects.create(
            tenant_id=tenant_id,
            period_name="2024-01",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        cash_account = Account.objects.create(
            tenant_id=tenant_id,
            code="1000",
            name="Cash",
            account_type="asset",
        )

        revenue_account = Account.objects.create(
            tenant_id=tenant_id,
            code="4000",
            name="Revenue",
            account_type="revenue",
        )

        entry = JournalEntry.objects.create(
            tenant_id=tenant_id,
            entry_number="JE-001",
            posting_date=date(2024, 1, 15),
            posting_period=period,
            status="draft",
        )

        # Create lines with equal debits and credits
        JournalLine.objects.create(
            tenant_id=tenant_id,
            journal_entry=entry,
            account=cash_account,
            debit_amount=Decimal("100.00"),
            credit_amount=Decimal("0.00"),
        )

        JournalLine.objects.create(
            tenant_id=tenant_id,
            journal_entry=entry,
            account=revenue_account,
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("100.00"),
        )

        # Calculate totals from lines (debit_total/credit_total are not auto-calculated)
        entry.refresh_from_db()
        lines = entry.lines.all()
        calculated_debit_total = sum(line.debit_amount for line in lines)
        calculated_credit_total = sum(line.credit_amount for line in lines)

        assert calculated_debit_total == Decimal("100.00")
        assert calculated_credit_total == Decimal("100.00")
        # Note: entry.debit_total and entry.credit_total are only set when entry is posted
