"""Transport serializers for the governed sales API.

Write serializers intentionally expose identifiers rather than unrestricted
related-field querysets.  Services resolve every identifier inside the tenant
boundary and own all aggregate mutations.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import (
    Customer,
    DeliveryNote,
    DeliveryNoteLine,
    Quotation,
    QuotationLine,
    SalesConfiguration,
    SalesConfigurationVersion,
    SalesOrder,
    SalesOrderLine,
)


class _TraceSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ("id", "tenant_id", "created_at", "updated_at", "lock_version")
        read_only_fields = fields


CUSTOMER_READ_FIELDS = (
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
    "created_by",
    "updated_by",
    "deleted_at",
    "deleted_by",
    "lock_version",
    "created_at",
    "updated_at",
)


class CustomerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = (
            "id",
            "tenant_id",
            "customer_code",
            "customer_name",
            "email",
            "phone",
            "credit_limit",
            "currency",
            "is_active",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class CustomerDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = CUSTOMER_READ_FIELDS
        read_only_fields = fields


class CustomerWriteSerializer(serializers.Serializer):
    customer_code = serializers.CharField(max_length=50, trim_whitespace=True)
    customer_name = serializers.CharField(max_length=255, trim_whitespace=True)
    email = serializers.EmailField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, trim_whitespace=True)
    address = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    credit_limit = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    is_active = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False, write_only=True)

    def validate_customer_code(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Customer code cannot be blank.")
        return value.strip()

    def validate_customer_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Customer name cannot be blank.")
        return value.strip()


class _LineWriteSerializer(serializers.Serializer):
    line_number = serializers.IntegerField(min_value=1)
    item_id = serializers.UUIDField(required=False, allow_null=True)
    item_code = serializers.CharField(max_length=100, trim_whitespace=True)
    item_name = serializers.CharField(max_length=255, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    quantity = serializers.DecimalField(
        max_digits=15, decimal_places=4, min_value=Decimal("0.0001"), max_value=Decimal("999999")
    )
    unit_price = serializers.DecimalField(
        max_digits=15, decimal_places=4, min_value=Decimal("0"), max_value=Decimal("999999999.99")
    )
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), default=Decimal("0")
    )
    tax_amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))


class QuotationLineWriteSerializer(_LineWriteSerializer):
    pass


class QuotationLineReadSerializer(serializers.ModelSerializer):
    quotation = serializers.UUIDField(source="quotation_id", read_only=True)

    class Meta:
        model = QuotationLine
        fields = (
            "id",
            "quotation",
            "line_number",
            "item_id",
            "item_code",
            "item_name",
            "description",
            "quantity",
            "unit_price",
            "discount_percent",
            "gross_amount",
            "discount_amount",
            "tax_amount",
            "line_total",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class QuotationListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.customer_name", read_only=True)
    customer = serializers.UUIDField(source="customer_id", read_only=True)

    class Meta:
        model = Quotation
        fields = (
            "id",
            "tenant_id",
            "quotation_number",
            "revision_number",
            "quotation_date",
            "valid_until",
            "customer",
            "customer_name",
            "currency",
            "total_amount",
            "status",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


QUOTATION_COMMANDS = {
    "draft": ("send",),
    "sent": ("accept", "reject", "expire", "revise"),
    "accepted": ("convert", "revise"),
    "rejected": (),
    "expired": ("revise",),
    "converted": (),
}


class QuotationDetailSerializer(serializers.ModelSerializer):
    lines = serializers.SerializerMethodField()
    customer = serializers.UUIDField(source="customer_id", read_only=True)
    customer_name = serializers.CharField(source="customer.customer_name", read_only=True)
    allowed_commands = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = (
            "id",
            "tenant_id",
            "quotation_number",
            "quotation_date",
            "valid_until",
            "customer",
            "customer_name",
            "currency",
            "subtotal_amount",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "status",
            "revision_number",
            "revision_of_id",
            "notes",
            "transition_history",
            "lines",
            "allowed_commands",
            "capabilities",
            "created_by",
            "updated_by",
            "deleted_at",
            "deleted_by",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_lines(self, obj: Quotation):
        return QuotationLineReadSerializer(
            obj.lines.filter(deleted_at__isnull=True).order_by("line_number"), many=True
        ).data

    def get_allowed_commands(self, obj: Quotation) -> tuple[str, ...]:
        return QUOTATION_COMMANDS.get(obj.status, ())

    def get_capabilities(self, obj: Quotation) -> list[dict[str, str]]:
        del obj
        return [{"key": "document_dispatch", "state": "not_configured", "reason_code": "PROVIDER_NOT_CONFIGURED"}]


class QuotationWriteSerializer(serializers.Serializer):
    quotation_date = serializers.DateField()
    valid_until = serializers.DateField(required=False)
    customer = serializers.UUIDField(source="customer_id")
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    notes = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    lines = QuotationLineWriteSerializer(many=True, allow_empty=False)
    expected_version = serializers.IntegerField(min_value=1, required=False, write_only=True)

    def validate(self, attrs):
        if attrs.get("valid_until") and attrs.get("quotation_date") and attrs["valid_until"] < attrs["quotation_date"]:
            raise serializers.ValidationError({"valid_until": "Must be on or after quotation_date."})
        numbers = [line["line_number"] for line in attrs.get("lines", [])]
        if len(numbers) != len(set(numbers)):
            raise serializers.ValidationError({"lines": "Line numbers must be unique."})
        return attrs


class QuotationPreviewSerializer(QuotationWriteSerializer):
    pass


class QuotationPreviewLineResultSerializer(serializers.Serializer):
    line_number = serializers.IntegerField(read_only=True)
    item_id = serializers.UUIDField(read_only=True, allow_null=True)
    item_code = serializers.CharField(read_only=True)
    item_name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    quantity = serializers.DecimalField(max_digits=15, decimal_places=4, read_only=True)
    unit_price = serializers.DecimalField(max_digits=15, decimal_places=4, read_only=True)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    gross_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)


class QuotationPreviewResultSerializer(serializers.Serializer):
    currency = serializers.CharField(read_only=True)
    subtotal_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    lines = QuotationPreviewLineResultSerializer(many=True, read_only=True)


class QuotationCommandSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=False, trim_whitespace=True)


class SalesOrderLineWriteSerializer(_LineWriteSerializer):
    source_quotation_line_id = serializers.UUIDField(required=False, allow_null=True)


class SalesOrderLineReadSerializer(serializers.ModelSerializer):
    remaining_quantity = serializers.SerializerMethodField()
    sales_order = serializers.UUIDField(source="sales_order_id", read_only=True)

    class Meta:
        model = SalesOrderLine
        fields = (
            "id",
            "sales_order",
            "source_quotation_line_id",
            "line_number",
            "item_id",
            "item_code",
            "item_name",
            "description",
            "quantity",
            "unit_price",
            "discount_percent",
            "gross_amount",
            "discount_amount",
            "tax_amount",
            "total_price",
            "delivered_quantity",
            "remaining_quantity",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_remaining_quantity(self, obj: SalesOrderLine):
        return obj.quantity - obj.delivered_quantity


class SalesOrderListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.customer_name", read_only=True)
    customer = serializers.UUIDField(source="customer_id", read_only=True)
    quotation = serializers.UUIDField(source="quotation_id", read_only=True, allow_null=True)

    class Meta:
        model = SalesOrder
        fields = (
            "id",
            "tenant_id",
            "order_number",
            "order_date",
            "delivery_date",
            "customer",
            "customer_name",
            "quotation",
            "currency",
            "total_amount",
            "status",
            "warehouse_id",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


ORDER_COMMANDS = {
    "draft": ("confirm", "cancel"),
    "confirmed": ("start_picking", "cancel"),
    "picking": ("start_packing", "cancel"),
    "packing": ("mark_ready", "cancel"),
    "ready_to_ship": ("ship", "cancel"),
    "shipped": ("deliver",),
    "delivered": ("mark_invoiced",),
    "invoiced": (),
    "cancelled": (),
}


class SalesOrderDetailSerializer(serializers.ModelSerializer):
    lines = serializers.SerializerMethodField()
    customer = serializers.UUIDField(source="customer_id", read_only=True)
    customer_name = serializers.CharField(source="customer.customer_name", read_only=True)
    quotation = serializers.UUIDField(source="quotation_id", read_only=True, allow_null=True)
    allowed_commands = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()

    class Meta:
        model = SalesOrder
        fields = (
            "id",
            "tenant_id",
            "order_number",
            "order_date",
            "delivery_date",
            "customer",
            "customer_name",
            "quotation",
            "currency",
            "subtotal_amount",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "status",
            "warehouse_id",
            "external_invoice_id",
            "notes",
            "transition_history",
            "lines",
            "allowed_commands",
            "capabilities",
            "created_by",
            "updated_by",
            "deleted_at",
            "deleted_by",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_lines(self, obj: SalesOrder):
        return SalesOrderLineReadSerializer(
            obj.lines.filter(deleted_at__isnull=True).order_by("line_number"), many=True
        ).data

    def get_allowed_commands(self, obj: SalesOrder) -> tuple[str, ...]:
        return ORDER_COMMANDS.get(obj.status, ())

    def get_capabilities(self, obj: SalesOrder) -> list[dict[str, str]]:
        del obj
        return [
            {"key": "inventory", "state": "not_configured", "reason_code": "PROVIDER_NOT_CONFIGURED"},
            {"key": "accounting", "state": "not_configured", "reason_code": "PROVIDER_NOT_CONFIGURED"},
        ]


class SalesOrderWriteSerializer(serializers.Serializer):
    order_date = serializers.DateField()
    delivery_date = serializers.DateField(required=False, allow_null=True)
    customer = serializers.UUIDField(source="customer_id")
    quotation = serializers.UUIDField(source="quotation_id", required=False, allow_null=True)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    warehouse_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    lines = SalesOrderLineWriteSerializer(many=True, allow_empty=False)
    expected_version = serializers.IntegerField(min_value=1, required=False, write_only=True)

    def validate(self, attrs):
        if attrs.get("delivery_date") and attrs.get("order_date") and attrs["delivery_date"] < attrs["order_date"]:
            raise serializers.ValidationError({"delivery_date": "Must be on or after order_date."})
        numbers = [line["line_number"] for line in attrs.get("lines", [])]
        if len(numbers) != len(set(numbers)):
            raise serializers.ValidationError({"lines": "Line numbers must be unique."})
        return attrs


class SalesOrderCommandSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=False, trim_whitespace=True)
    invoice_id = serializers.UUIDField(required=False)


class DeliveryNoteLineWriteSerializer(serializers.Serializer):
    line_number = serializers.IntegerField(min_value=1)
    sales_order_line = serializers.UUIDField(source="sales_order_line_id")
    item_id = serializers.UUIDField(required=False, allow_null=True)
    quantity_delivered = serializers.DecimalField(max_digits=15, decimal_places=4, min_value=Decimal("0.0001"))
    batch_number = serializers.CharField(max_length=100, required=False, allow_blank=True, trim_whitespace=True)
    serial_number = serializers.CharField(max_length=100, required=False, allow_blank=True, trim_whitespace=True)


class DeliveryNoteLineReadSerializer(serializers.ModelSerializer):
    delivery_note = serializers.UUIDField(source="delivery_note_id", read_only=True)
    sales_order_line = serializers.UUIDField(source="sales_order_line_id", read_only=True)

    class Meta:
        model = DeliveryNoteLine
        fields = (
            "id",
            "delivery_note",
            "sales_order_line",
            "line_number",
            "item_id",
            "quantity_delivered",
            "batch_number",
            "serial_number",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DeliveryNoteListSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="sales_order.order_number", read_only=True)
    sales_order = serializers.UUIDField(source="sales_order_id", read_only=True)

    class Meta:
        model = DeliveryNote
        fields = (
            "id",
            "tenant_id",
            "delivery_number",
            "delivery_date",
            "sales_order",
            "order_number",
            "warehouse_id",
            "carrier_name",
            "tracking_number",
            "status",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


DELIVERY_COMMANDS = {"draft": ("complete", "cancel"), "completed": (), "cancelled": ()}


class DeliveryNoteDetailSerializer(serializers.ModelSerializer):
    lines = serializers.SerializerMethodField()
    allowed_commands = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    sales_order = serializers.UUIDField(source="sales_order_id", read_only=True)
    order_number = serializers.CharField(source="sales_order.order_number", read_only=True)

    class Meta:
        model = DeliveryNote
        fields = (
            "id",
            "tenant_id",
            "delivery_number",
            "delivery_date",
            "sales_order",
            "order_number",
            "warehouse_id",
            "carrier_name",
            "tracking_number",
            "proof_document_id",
            "status",
            "notes",
            "transition_history",
            "lines",
            "allowed_commands",
            "capabilities",
            "created_by",
            "updated_by",
            "deleted_at",
            "deleted_by",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_lines(self, obj: DeliveryNote):
        return DeliveryNoteLineReadSerializer(
            obj.lines.filter(deleted_at__isnull=True).order_by("line_number"), many=True
        ).data

    def get_allowed_commands(self, obj: DeliveryNote) -> tuple[str, ...]:
        return DELIVERY_COMMANDS.get(obj.status, ())

    def get_capabilities(self, obj: DeliveryNote) -> list[dict[str, str]]:
        del obj
        return [{"key": "shipping", "state": "not_configured", "reason_code": "PROVIDER_NOT_CONFIGURED"}]


class DeliveryNoteWriteSerializer(serializers.Serializer):
    delivery_date = serializers.DateField()
    sales_order = serializers.UUIDField(source="sales_order_id")
    warehouse_id = serializers.UUIDField(required=False, allow_null=True)
    carrier_name = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    tracking_number = serializers.CharField(max_length=120, required=False, allow_blank=True, trim_whitespace=True)
    proof_document_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    lines = DeliveryNoteLineWriteSerializer(many=True, allow_empty=False)
    expected_version = serializers.IntegerField(min_value=1, required=False, write_only=True)

    def validate(self, attrs):
        if attrs.get("tracking_number") and not attrs.get("carrier_name"):
            raise serializers.ValidationError({"carrier_name": "Carrier is required with a tracking number."})
        numbers = [line["line_number"] for line in attrs.get("lines", [])]
        if len(numbers) != len(set(numbers)):
            raise serializers.ValidationError({"lines": "Line numbers must be unique."})
        return attrs


class DeliveryNoteCommandSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=False, trim_whitespace=True)


CONFIG_FIELDS = (
    "default_currency",
    "currency_decimal_places",
    "rounding_mode",
    "quotation_validity_days",
    "credit_check_enabled",
    "inventory_confirmation_required",
    "manual_discount_enabled",
    "maximum_manual_discount_percent",
    "manual_tax_enabled",
    "quotation_prefix",
    "order_prefix",
    "delivery_prefix",
    "sequence_padding",
)


class SalesConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesConfiguration
        fields = (
            "id",
            "tenant_id",
            "environment",
            *CONFIG_FIELDS,
            "version",
            "lock_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SalesConfigurationWriteSerializer(serializers.Serializer):
    default_currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    currency_decimal_places = serializers.IntegerField(min_value=0, max_value=4, required=False)
    rounding_mode = serializers.ChoiceField(choices=("ROUND_HALF_UP", "ROUND_HALF_EVEN"), required=False)
    quotation_validity_days = serializers.IntegerField(min_value=1, max_value=365, required=False)
    credit_check_enabled = serializers.BooleanField(required=False)
    inventory_confirmation_required = serializers.BooleanField(required=False)
    manual_discount_enabled = serializers.BooleanField(required=False)
    maximum_manual_discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False
    )
    manual_tax_enabled = serializers.BooleanField(required=False)
    quotation_prefix = serializers.RegexField(r"^[A-Z0-9-]{1,12}$", required=False)
    order_prefix = serializers.RegexField(r"^[A-Z0-9-]{1,12}$", required=False)
    delivery_prefix = serializers.RegexField(r"^[A-Z0-9-]{1,12}$", required=False)
    sequence_padding = serializers.IntegerField(min_value=4, max_value=12, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)
    reason = serializers.CharField(max_length=500, trim_whitespace=True, required=False)


class SalesConfigurationVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesConfigurationVersion
        fields = (
            "id",
            "tenant_id",
            "configuration_id",
            "version",
            "snapshot",
            "change_reason",
            "actor_id",
            "correlation_id",
            "created_at",
        )
        read_only_fields = fields


class ConfigurationImportSerializer(serializers.Serializer):
    document = serializers.JSONField()
    dry_run = serializers.BooleanField(default=True)
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500, trim_whitespace=True)


class ConfigurationRollbackSerializer(serializers.Serializer):
    target_version = serializers.IntegerField(min_value=1)
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500, trim_whitespace=True)


# Compatibility aliases are read-only; v2 views use the explicit serializers.
CustomerSerializer = CustomerDetailSerializer
QuotationSerializer = QuotationDetailSerializer
SalesOrderSerializer = SalesOrderDetailSerializer
DeliveryNoteSerializer = DeliveryNoteDetailSerializer
