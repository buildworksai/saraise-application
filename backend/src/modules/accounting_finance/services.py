"""
Business logic services for Accounting & Finance module.

All business logic should be in services, not in views.
"""

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .models import Account, APInvoice, ARInvoice, JournalEntry, JournalLine, Payment


class AccountService:
    """Service for account operations."""

    @staticmethod
    def create_account(tenant_id: str, code: str, name: str, account_type: str, **kwargs) -> Account:
        """Create a new account."""
        return Account.objects.create(
            tenant_id=tenant_id,
            code=code,
            name=name,
            account_type=account_type,
            **kwargs,
        )


class JournalEntryService:
    """Service for journal entry operations."""

    @staticmethod
    @transaction.atomic
    def post_journal_entry(journal_entry: JournalEntry, posted_by: str) -> JournalEntry:
        """Post a journal entry (make it immutable)."""
        if journal_entry.status != JournalEntry.status.field.default:
            raise ValueError("Only draft entries can be posted")

        # Validate debits equal credits
        lines = journal_entry.lines.all()
        debit_total = sum(line.debit_amount for line in lines)
        credit_total = sum(line.credit_amount for line in lines)

        if abs(debit_total - credit_total) > Decimal("0.01"):
            raise ValueError("Debits must equal credits")

        journal_entry.debit_total = debit_total
        journal_entry.credit_total = credit_total
        journal_entry.status = "posted"
        journal_entry.posted_at = timezone.now()
        journal_entry.posted_by = posted_by
        journal_entry.save()

        return journal_entry


class PaymentService:
    """Service for payment operations."""

    @staticmethod
    @transaction.atomic
    def record_payment(
        tenant_id: str,
        payment_date: str,
        amount: Decimal,
        payment_method: str,
        ap_invoice_id: Optional[str] = None,
        ar_invoice_id: Optional[str] = None,
    ) -> Payment:
        """Record a payment against an AP or AR invoice."""
        payment = Payment.objects.create(
            tenant_id=tenant_id,
            payment_date=payment_date,
            amount=amount,
            payment_method=payment_method,
            ap_invoice_id=ap_invoice_id,
            ar_invoice_id=ar_invoice_id,
        )

        # Update invoice paid amount
        if ap_invoice_id:
            invoice = APInvoice.objects.get(id=ap_invoice_id, tenant_id=tenant_id)
            invoice.paid_amount += amount
            if invoice.paid_amount >= invoice.total_amount:
                invoice.status = "paid"
            elif invoice.paid_amount > 0:
                invoice.status = "partially_paid"
            invoice.save()

        if ar_invoice_id:
            invoice = ARInvoice.objects.get(id=ar_invoice_id, tenant_id=tenant_id)
            invoice.paid_amount += amount
            if invoice.paid_amount >= invoice.total_amount:
                invoice.status = "paid"
            elif invoice.paid_amount > 0:
                invoice.status = "partially_paid"
            invoice.save()

        return payment
