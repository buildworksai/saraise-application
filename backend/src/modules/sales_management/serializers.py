"""
DRF Serializers for Sales Management module.
"""

from rest_framework import serializers

from .models import Customer, DeliveryNote, Quotation, SalesOrder


class CustomerSerializer(serializers.ModelSerializer):
    """Customer serializer."""

    class Meta:
        model = Customer
        fields = [
            "id",
            "tenant_id",
            "customer_code",
            "customer_name",
            "email",
            "phone",
            "address",
            "credit_limit",
            "currency",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class QuotationSerializer(serializers.ModelSerializer):
    """Quotation serializer."""

    customer_code = serializers.CharField(source="customer.customer_code", read_only=True)
    customer_name = serializers.CharField(source="customer.customer_name", read_only=True)

    class Meta:
        model = Quotation
        fields = [
            "id",
            "tenant_id",
            "quotation_number",
            "quotation_date",
            "valid_until",
            "customer",
            "customer_code",
            "customer_name",
            "total_amount",
            "currency",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "quotation_number", "total_amount", "created_at", "updated_at"]


class SalesOrderSerializer(serializers.ModelSerializer):
    """SalesOrder serializer."""

    customer_code = serializers.CharField(source="customer.customer_code", read_only=True)
    customer_name = serializers.CharField(source="customer.customer_name", read_only=True)

    class Meta:
        model = SalesOrder
        fields = [
            "id",
            "tenant_id",
            "order_number",
            "order_date",
            "delivery_date",
            "customer",
            "customer_code",
            "customer_name",
            "quotation",
            "total_amount",
            "currency",
            "status",
            "warehouse_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "order_number", "total_amount", "created_at", "updated_at"]


class DeliveryNoteSerializer(serializers.ModelSerializer):
    """DeliveryNote serializer."""

    order_number = serializers.CharField(source="sales_order.order_number", read_only=True)
    customer_name = serializers.CharField(source="sales_order.customer.customer_name", read_only=True)

    class Meta:
        model = DeliveryNote
        fields = [
            "id",
            "tenant_id",
            "delivery_number",
            "delivery_date",
            "sales_order",
            "order_number",
            "customer_name",
            "warehouse_id",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "delivery_number", "created_at", "updated_at"]
