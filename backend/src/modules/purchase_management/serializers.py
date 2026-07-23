"""Strict input and complete output contracts for the procurement API."""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    ProcurementConfiguration,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    RequestForQuotation,
    RFQInvitation,
    RFQLine,
    Supplier,
    SupplierQuote,
    SupplierQuoteLine,
)


class StrictSerializer(serializers.Serializer):
    """Reject undeclared input keys, including tenant/status spoofing."""

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected a JSON object.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({field: ["Unknown field."] for field in sorted(unknown)})
        return super().to_internal_value(data)


class ReadModelSerializer(serializers.ModelSerializer):
    class Meta:
        pass


class SupplierListSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = Supplier
        fields = (
            "id",
            "supplier_code",
            "supplier_name",
            "email",
            "currency",
            "status",
            "lock_version",
            "created_at",
            "updated_at",
        )


class SupplierDetailSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = Supplier
        exclude = ("tenant_id",)


class SupplierWriteSerializer(StrictSerializer):
    supplier_code = serializers.CharField(max_length=50)
    supplier_name = serializers.CharField(max_length=255)
    email = serializers.EmailField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    payment_terms = serializers.CharField(max_length=50)
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    lock_version = serializers.IntegerField(min_value=1, required=False, write_only=True)


class SupplierStatusSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500)


class RequisitionLineSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = PurchaseRequisitionLine
        exclude = ("tenant_id", "requisition")


class RequisitionLineWriteSerializer(StrictSerializer):
    line_number = serializers.IntegerField(min_value=1, required=False)
    item_id = serializers.UUIDField(required=False, allow_null=True)
    item_code = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=500)
    quantity = serializers.DecimalField(max_digits=19, decimal_places=6, min_value=0.000001)
    estimated_unit_price = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=0, default=0)
    preferred_supplier_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class RequisitionListSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = PurchaseRequisition
        fields = (
            "id",
            "requisition_number",
            "requisition_date",
            "required_date",
            "purpose",
            "status",
            "requested_by",
            "total_amount",
            "currency",
            "lock_version",
            "created_at",
            "updated_at",
        )


class RequisitionDetailSerializer(ReadModelSerializer):
    lines = RequisitionLineSerializer(many=True)

    class Meta(ReadModelSerializer.Meta):
        model = PurchaseRequisition
        exclude = ("tenant_id",)


class RequisitionWriteSerializer(StrictSerializer):
    requisition_number = serializers.CharField(max_length=50, required=False)
    requisition_date = serializers.DateField()
    required_date = serializers.DateField()
    purpose = serializers.CharField()
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    lines = RequisitionLineWriteSerializer(many=True, allow_empty=True)
    lock_version = serializers.IntegerField(min_value=1, required=False, write_only=True)

    def validate(self, attrs):
        if attrs["required_date"] < attrs["requisition_date"]:
            raise serializers.ValidationError({"required_date": "Must be on or after requisition_date."})
        return attrs


class ReasonTransitionSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500)


class EmptyTransitionSerializer(StrictSerializer):
    pass


class RequisitionConvertSerializer(StrictSerializer):
    supplier_id = serializers.UUIDField()
    line_selections = serializers.ListField(child=serializers.DictField(), allow_empty=False)


class RFQLineSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = RFQLine
        exclude = ("tenant_id", "rfq")


class RFQInvitationSerializer(ReadModelSerializer):
    supplier_name = serializers.CharField(source="supplier.supplier_name", read_only=True)

    class Meta(ReadModelSerializer.Meta):
        model = RFQInvitation
        exclude = ("tenant_id", "rfq")


class RFQLineWriteSerializer(StrictSerializer):
    line_number = serializers.IntegerField(min_value=1, required=False)
    requisition_line_id = serializers.UUIDField(required=False, allow_null=True)
    item_id = serializers.UUIDField(required=False, allow_null=True)
    item_code = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=500)
    quantity = serializers.DecimalField(max_digits=19, decimal_places=6, min_value=0.000001)
    required_date = serializers.DateField()
    specification = serializers.CharField(required=False, allow_blank=True)


class RFQListSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = RequestForQuotation
        fields = (
            "id",
            "rfq_number",
            "title",
            "issue_date",
            "submission_deadline",
            "currency",
            "status",
            "lock_version",
            "created_at",
            "updated_at",
        )


class RFQDetailSerializer(ReadModelSerializer):
    lines = RFQLineSerializer(many=True)
    invitations = RFQInvitationSerializer(many=True)

    class Meta(ReadModelSerializer.Meta):
        model = RequestForQuotation
        exclude = ("tenant_id",)


class RFQWriteSerializer(StrictSerializer):
    rfq_number = serializers.CharField(max_length=50, required=False)
    title = serializers.CharField(max_length=255)
    requisition_id = serializers.UUIDField(required=False, allow_null=True)
    issue_date = serializers.DateField()
    submission_deadline = serializers.DateTimeField()
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    terms = serializers.CharField(required=False, allow_blank=True)
    delivery_requirements = serializers.CharField(required=False, allow_blank=True)
    lines = RFQLineWriteSerializer(many=True, allow_empty=True)
    lock_version = serializers.IntegerField(min_value=1, required=False, write_only=True)


class RFQPublishSerializer(StrictSerializer):
    supplier_ids = serializers.ListField(child=serializers.UUIDField(), min_length=2, max_length=20)


class RFQAwardSerializer(StrictSerializer):
    quote_id = serializers.UUIDField()
    create_purchase_order = serializers.BooleanField(default=False)


class QuoteLineSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = SupplierQuoteLine
        exclude = ("tenant_id", "quote")


class QuoteLineWriteSerializer(StrictSerializer):
    rfq_line_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=19, decimal_places=6, min_value=0.000001)
    unit_price = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=0)
    tax_amount = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=0, default=0)
    lead_time_days = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class QuoteListSerializer(ReadModelSerializer):
    supplier_name = serializers.CharField(source="supplier.supplier_name", read_only=True)

    class Meta(ReadModelSerializer.Meta):
        model = SupplierQuote
        fields = (
            "id",
            "quote_number",
            "rfq_id",
            "supplier_id",
            "supplier_name",
            "valid_until",
            "delivery_date",
            "currency",
            "status",
            "total_amount",
            "lock_version",
            "submitted_at",
            "created_at",
            "updated_at",
        )


class QuoteDetailSerializer(ReadModelSerializer):
    lines = QuoteLineSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.supplier_name", read_only=True)

    class Meta(ReadModelSerializer.Meta):
        model = SupplierQuote
        exclude = ("tenant_id",)


class QuoteWriteSerializer(StrictSerializer):
    quote_number = serializers.CharField(max_length=50, required=False)
    rfq_id = serializers.UUIDField()
    supplier_id = serializers.UUIDField()
    valid_until = serializers.DateField()
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    delivery_date = serializers.DateField(required=False, allow_null=True)
    payment_terms = serializers.CharField(max_length=50)
    shipping_amount = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=0, default=0)
    supplier_notes = serializers.CharField(required=False, allow_blank=True)
    lines = QuoteLineWriteSerializer(many=True, allow_empty=False)
    lock_version = serializers.IntegerField(min_value=1, required=False, write_only=True)


class PurchaseOrderLineSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = PurchaseOrderLine
        exclude = ("tenant_id", "purchase_order")


class PurchaseOrderLineWriteSerializer(StrictSerializer):
    line_number = serializers.IntegerField(min_value=1, required=False)
    requisition_line_id = serializers.UUIDField(required=False, allow_null=True)
    quote_line_id = serializers.UUIDField(required=False, allow_null=True)
    item_id = serializers.UUIDField(required=False, allow_null=True)
    item_code = serializers.CharField(max_length=100)
    item_name = serializers.CharField(max_length=255)
    quantity = serializers.DecimalField(max_digits=19, decimal_places=6, min_value=0.000001)
    unit_price = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=0)
    tax_amount = serializers.DecimalField(max_digits=19, decimal_places=4, min_value=0, default=0)


class PurchaseOrderListSerializer(ReadModelSerializer):
    supplier_name = serializers.CharField(source="supplier.supplier_name", read_only=True)

    class Meta(ReadModelSerializer.Meta):
        model = PurchaseOrder
        fields = (
            "id",
            "po_number",
            "po_date",
            "supplier_id",
            "supplier_name",
            "expected_delivery_date",
            "total_amount",
            "currency",
            "status",
            "dispatch_status",
            "lock_version",
            "created_at",
            "updated_at",
        )


class PurchaseOrderDetailSerializer(ReadModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.supplier_name", read_only=True)

    class Meta(ReadModelSerializer.Meta):
        model = PurchaseOrder
        exclude = ("tenant_id",)


class PurchaseOrderWriteSerializer(StrictSerializer):
    po_number = serializers.CharField(max_length=50, required=False)
    po_date = serializers.DateField()
    supplier_id = serializers.UUIDField()
    expected_delivery_date = serializers.DateField(required=False, allow_null=True)
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    requisition_id = serializers.UUIDField(required=False, allow_null=True)
    rfq_id = serializers.UUIDField(required=False, allow_null=True)
    accepted_quote_id = serializers.UUIDField(required=False, allow_null=True)
    payment_terms = serializers.CharField(max_length=50)
    delivery_terms = serializers.CharField(max_length=50, required=False, allow_blank=True)
    shipping_address = serializers.DictField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = PurchaseOrderLineWriteSerializer(many=True, allow_empty=True)
    lock_version = serializers.IntegerField(min_value=1, required=False, write_only=True)


class ReceiptLineSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = PurchaseReceiptLine
        exclude = ("tenant_id", "purchase_receipt")


class ReceiptLineWriteSerializer(StrictSerializer):
    line_number = serializers.IntegerField(min_value=1, required=False)
    purchase_order_line_id = serializers.UUIDField()
    quantity_received = serializers.DecimalField(max_digits=19, decimal_places=6, min_value=0.000001)
    condition = serializers.ChoiceField(choices=("accepted", "damaged", "rejected"), default="accepted")
    batch_no = serializers.CharField(max_length=100, required=False, allow_blank=True)
    serial_no = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class ReceiptListSerializer(ReadModelSerializer):
    po_number = serializers.CharField(source="purchase_order.po_number", read_only=True)

    class Meta(ReadModelSerializer.Meta):
        model = PurchaseReceipt
        fields = (
            "id",
            "receipt_number",
            "receipt_date",
            "purchase_order_id",
            "po_number",
            "warehouse_id",
            "status",
            "inventory_status",
            "lock_version",
            "created_at",
            "updated_at",
        )


class ReceiptDetailSerializer(ReadModelSerializer):
    lines = ReceiptLineSerializer(many=True)
    po_number = serializers.CharField(source="purchase_order.po_number", read_only=True)

    class Meta(ReadModelSerializer.Meta):
        model = PurchaseReceipt
        exclude = ("tenant_id",)


class ReceiptWriteSerializer(StrictSerializer):
    receipt_number = serializers.CharField(max_length=50, required=False)
    receipt_date = serializers.DateField()
    purchase_order_id = serializers.UUIDField()
    warehouse_id = serializers.UUIDField()
    lines = ReceiptLineWriteSerializer(many=True, allow_empty=True)
    lock_version = serializers.IntegerField(min_value=1, required=False, write_only=True)


class ReceiptCompleteSerializer(StrictSerializer):
    pass


class ConfigurationSerializer(ReadModelSerializer):
    class Meta(ReadModelSerializer.Meta):
        model = ProcurementConfiguration
        exclude = ("tenant_id",)


class ConfigurationWriteSerializer(StrictSerializer):
    default_currency = serializers.RegexField(r"^[A-Z]{3}$")
    default_payment_terms = serializers.CharField(max_length=50)
    supplier_code_prefix = serializers.CharField(max_length=20)
    requisition_prefix = serializers.CharField(max_length=20)
    rfq_prefix = serializers.CharField(max_length=20)
    po_prefix = serializers.CharField(max_length=20)
    receipt_prefix = serializers.CharField(max_length=20)
    approval_rules = serializers.ListField(child=serializers.DictField(), max_length=50)
    receipt_tolerance_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    minimum_rfq_suppliers = serializers.IntegerField(min_value=2, max_value=20)
    quote_scoring_weights = serializers.DictField()
    inventory_integration_enabled = serializers.BooleanField()
    accounting_integration_enabled = serializers.BooleanField()
    supplier_delivery_enabled = serializers.BooleanField()
    rollout = serializers.DictField()
    lock_version = serializers.IntegerField(min_value=1, required=False, write_only=True)


class ConfigurationPreviewSerializer(ConfigurationWriteSerializer):
    environment = serializers.ChoiceField(choices=("development", "staging", "production"))
    simulations = serializers.ListField(child=serializers.DictField(), required=False)


class ConfigurationImportSerializer(StrictSerializer):
    document = serializers.DictField()


class ConfigurationRollbackSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500)


class ModuleHealthSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=("healthy", "degraded", "unhealthy"), read_only=True)
    checks = serializers.DictField(read_only=True)
    correlation_id = serializers.CharField(read_only=True)


# Deprecated import names retained only for v1 representation compatibility.
SupplierSerializer = SupplierDetailSerializer
PurchaseRequisitionSerializer = RequisitionDetailSerializer
PurchaseOrderSerializer = PurchaseOrderDetailSerializer
PurchaseReceiptSerializer = ReceiptDetailSerializer
