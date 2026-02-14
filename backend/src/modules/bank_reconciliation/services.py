"""
Business logic services for Bank Reconciliation module.
"""

from .models import BankAccount, BankStatement


class BankAccountService:
    """Service for bank account operations."""

    @staticmethod
    def create_bank_account(tenant_id: str, account_number: str, bank_name: str, account_name: str, **kwargs) -> BankAccount:
        """Create a new bank account."""
        return BankAccount.objects.create(
            tenant_id=tenant_id,
            account_number=account_number,
            bank_name=bank_name,
            account_name=account_name,
            **kwargs,
        )


class ReconciliationService:
    """Service for reconciliation operations."""

    @staticmethod
    def reconcile_statement(bank_statement: BankStatement) -> BankStatement:
        """Mark a bank statement as reconciled."""
        bank_statement.is_reconciled = True
        bank_statement.save()
        return bank_statement
