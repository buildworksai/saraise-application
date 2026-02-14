"""
DRF Serializers for Bank Reconciliation module.
"""

from rest_framework import serializers

from .models import BankAccount, BankStatement, BankTransaction


class BankAccountSerializer(serializers.ModelSerializer):
    """BankAccount serializer."""

    class Meta:
        model = BankAccount
        fields = [
            "id",
            "tenant_id",
            "account_number",
            "bank_name",
            "account_name",
            "account_type",
            "currency",
            "ledger_account_id",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class BankStatementSerializer(serializers.ModelSerializer):
    """BankStatement serializer."""

    bank_name = serializers.CharField(source="bank_account.bank_name", read_only=True)
    account_number = serializers.CharField(source="bank_account.account_number", read_only=True)

    class Meta:
        model = BankStatement
        fields = [
            "id",
            "tenant_id",
            "bank_account",
            "bank_name",
            "account_number",
            "statement_date",
            "opening_balance",
            "closing_balance",
            "is_reconciled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class BankTransactionSerializer(serializers.ModelSerializer):
    """BankTransaction serializer."""

    class Meta:
        model = BankTransaction
        fields = [
            "id",
            "tenant_id",
            "bank_statement",
            "transaction_date",
            "description",
            "amount",
            "transaction_type",
            "reference_number",
            "is_reconciled",
            "matched_payment_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
