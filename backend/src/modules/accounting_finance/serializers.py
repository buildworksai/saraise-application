"""
DRF Serializers for Accounting & Finance module.

Provides request/response validation for all models.
"""

from rest_framework import serializers

from .models import Account, APInvoice, ARInvoice, JournalEntry, Payment, PostingPeriod


class AccountSerializer(serializers.ModelSerializer):
    """Account serializer."""

    class Meta:
        model = Account
        fields = [
            "id",
            "tenant_id",
            "code",
            "name",
            "account_type",
            "parent_account_id",
            "is_active",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class PostingPeriodSerializer(serializers.ModelSerializer):
    """PostingPeriod serializer."""

    class Meta:
        model = PostingPeriod
        fields = [
            "id",
            "tenant_id",
            "period_name",
            "start_date",
            "end_date",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class JournalEntrySerializer(serializers.ModelSerializer):
    """JournalEntry serializer."""

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "tenant_id",
            "entry_number",
            "posting_date",
            "posting_period",
            "description",
            "status",
            "debit_total",
            "credit_total",
            "posted_at",
            "posted_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "entry_number",
            "debit_total",
            "credit_total",
            "posted_at",
            "posted_by",
            "created_at",
            "updated_at",
        ]


class APInvoiceSerializer(serializers.ModelSerializer):
    """APInvoice serializer."""

    class Meta:
        model = APInvoice
        fields = [
            "id",
            "tenant_id",
            "invoice_number",
            "supplier_id",
            "invoice_date",
            "due_date",
            "amount",
            "tax_amount",
            "total_amount",
            "paid_amount",
            "status",
            "currency",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "paid_amount", "created_at", "updated_at"]


class ARInvoiceSerializer(serializers.ModelSerializer):
    """ARInvoice serializer."""

    class Meta:
        model = ARInvoice
        fields = [
            "id",
            "tenant_id",
            "invoice_number",
            "customer_id",
            "invoice_date",
            "due_date",
            "amount",
            "tax_amount",
            "total_amount",
            "paid_amount",
            "status",
            "currency",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "paid_amount", "created_at", "updated_at"]


class PaymentSerializer(serializers.ModelSerializer):
    """Payment serializer."""

    class Meta:
        model = Payment
        fields = [
            "id",
            "tenant_id",
            "payment_date",
            "amount",
            "payment_method",
            "currency",
            "reference_number",
            "ap_invoice",
            "ar_invoice",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
