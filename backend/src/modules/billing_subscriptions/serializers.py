"""
DRF Serializers for BillingSubscriptions module.
Provides request/response validation for all models.
"""

from rest_framework import serializers

from .models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
    UsageRecord,
)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for SubscriptionPlan model (read-only, platform-level)."""

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "description",
            "price",
            "billing_cycle",
            "features",
            "limits",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for Subscription model."""

    plan_name = serializers.CharField(source="plan.name", read_only=True)
    plan_price = serializers.DecimalField(source="plan.price", read_only=True, max_digits=10, decimal_places=2)
    is_trial = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    invoices_count = serializers.IntegerField(source="invoices.count", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "tenant_id",
            "plan",
            "plan_name",
            "plan_price",
            "status",
            "start_date",
            "end_date",
            "trial_start_date",
            "trial_end_date",
            "cancelled_at",
            "cancellation_reason",
            "is_trial",
            "is_active",
            "invoices_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    """Serializer for InvoiceLineItem model."""

    class Meta:
        model = InvoiceLineItem
        fields = [
            "id",
            "invoice",
            "description",
            "quantity",
            "unit_price",
            "total_price",
        ]
        read_only_fields = ["id", "total_price"]


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Invoice model."""

    subscription_plan_name = serializers.CharField(source="subscription.plan.name", read_only=True)
    line_items = InvoiceLineItemSerializer(many=True, read_only=True)
    payments_count = serializers.IntegerField(source="payments.count", read_only=True)
    paid_amount = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "tenant_id",
            "subscription",
            "subscription_plan_name",
            "invoice_number",
            "amount",
            "tax_amount",
            "total_amount",
            "status",
            "due_date",
            "paid_at",
            "line_items",
            "payments_count",
            "paid_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "invoice_number",
            "paid_at",
            "created_at",
            "updated_at",
        ]

    def get_paid_amount(self, obj):
        """Calculate total paid amount from payments."""
        return sum(payment.amount for payment in obj.payments.filter(status="completed"))


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model."""

    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    invoice_total = serializers.DecimalField(source="invoice.total_amount", read_only=True, max_digits=10, decimal_places=2)

    class Meta:
        model = Payment
        fields = [
            "id",
            "tenant_id",
            "invoice",
            "invoice_number",
            "invoice_total",
            "amount",
            "payment_method",
            "status",
            "transaction_id",
            "processed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "processed_at", "created_at", "updated_at"]


class UsageRecordSerializer(serializers.ModelSerializer):
    """Serializer for UsageRecord model."""

    class Meta:
        model = UsageRecord
        fields = [
            "id",
            "tenant_id",
            "resource_type",
            "quantity",
            "recorded_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "recorded_at", "created_at", "updated_at"]
