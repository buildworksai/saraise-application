"""
Service tests for Accounting & Finance module.
"""

import uuid
import pytest
from decimal import Decimal
from datetime import date

from src.modules.accounting_finance.models import Account, PostingPeriod
from src.modules.accounting_finance.services import AccountService, JournalEntryService


@pytest.mark.django_db
class TestAccountService:
    """Test AccountService."""

    def test_create_account(self):
        """Test creating an account via service."""
        tenant_id = uuid.uuid4()
        account = AccountService.create_account(
            tenant_id=str(tenant_id),
            code="1000",
            name="Cash",
            account_type="asset",
        )

        assert account.code == "1000"
        assert account.name == "Cash"
        assert str(account.tenant_id) == str(tenant_id)


@pytest.mark.django_db
class TestJournalEntryService:
    """Test JournalEntryService."""

    def test_post_journal_entry(self):
        """Test posting a journal entry."""
        tenant_id = uuid.uuid4()

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

        from src.modules.accounting_finance.models import JournalEntry, JournalLine

        entry = JournalEntry.objects.create(
            tenant_id=tenant_id,
            entry_number="JE-001",
            posting_date=date(2024, 1, 15),
            posting_period=period,
            status="draft",
        )

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

        # Post the entry
        posted_entry = JournalEntryService.post_journal_entry(entry, "user-123")

        assert posted_entry.status == "posted"
        assert posted_entry.posted_at is not None
        assert posted_entry.posted_by == "user-123"
