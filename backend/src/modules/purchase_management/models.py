"""Tenant-safe procurement domain models.

Mutations are intentionally implemented in :mod:`services`; models contain
storage invariants only.  Every relationship is revalidated by the service
boundary and PostgreSQL receives additional composite foreign keys in 0006.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.core.tenancy.registry import TENANT_SCOPED, register_model_scope

MONEY_ZERO = Decimal("0.0000")
QUANTITY_ZERO = Decimal("0.000000")
POSITIVE_QUANTITY = Decimal("0.000001")
CURRENCY_VALIDATOR = RegexValidator(r"^[A-Z]{3}$", "Use an uppercase ISO-4217 currency code.")


class ProcurementRecord(TenantScopedModel, TimestampedModel):
    """Shared ownership, actor and optimistic-concurrency contract."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Defaults preserve migration compatibility for legacy rows. Public
    # services always replace both with the authenticated actor.
    created_by = models.UUIDField(default=uuid.uuid4)
    updated_by = models.UUIDField(default=uuid.uuid4)
    lock_version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class SupplierStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ARCHIVED = "archived", "Archived"


class Supplier(ProcurementRecord):
    supplier_code = models.CharField(max_length=50)
    supplier_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    payment_terms = models.CharField(max_length=50, default="Net 30")
    currency = models.CharField(max_length=3, default="USD", validators=[CURRENCY_VALIDATOR])
    status = models.CharField(max_length=16, choices=SupplierStatus.choices, default=SupplierStatus.ACTIVE)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "purchase_suppliers"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "supplier_code"), name="purchase_supplier_code_uq")]
        indexes = [
            models.Index(fields=("tenant_id", "status", "supplier_name"), name="purchase_supplier_status_idx"),
            models.Index(fields=("tenant_id", "created_at"), name="purchase_supplier_created_idx"),
        ]

    @property
    def is_active(self) -> bool:
        """Read-only compatibility projection for deprecated v1 clients."""
        return self.status == SupplierStatus.ACTIVE

    def __str__(self) -> str:
        return f"{self.supplier_code} - {self.supplier_name}"


class PurchaseRequisitionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CONVERTED = "converted", "Converted"
    CANCELLED = "cancelled", "Cancelled"


class PurchaseRequisition(ProcurementRecord):
    requisition_number = models.CharField(max_length=50)
    requisition_date = models.DateField()
    required_date = models.DateField()
    purpose = models.TextField(blank=True)
    status = models.CharField(
        max_length=24, choices=PurchaseRequisitionStatus.choices, default=PurchaseRequisitionStatus.DRAFT
    )
    requested_by = models.UUIDField(default=uuid.uuid4)
    approved_by = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    converted_order_id = models.UUIDField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    currency = models.CharField(max_length=3, default="USD", validators=[CURRENCY_VALIDATOR])
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "purchase_requisitions"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "requisition_number"), name="purchase_requisition_no_uq"),
            models.CheckConstraint(
                condition=Q(required_date__gte=models.F("requisition_date")), name="purchase_req_dates_ck"
            ),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="purchase_req_total_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "required_date"), name="purchase_req_status_idx"),
            models.Index(fields=("tenant_id", "requested_by", "created_at"), name="purchase_req_requester_idx"),
        ]

    def __str__(self) -> str:
        return self.requisition_number


class PurchaseRequisitionLine(ProcurementRecord):
    requisition = models.ForeignKey(PurchaseRequisition, on_delete=models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField()
    item_id = models.UUIDField(null=True, blank=True)
    item_code = models.CharField(max_length=100)
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=19, decimal_places=6, validators=[MinValueValidator(POSITIVE_QUANTITY)])
    estimated_unit_price = models.DecimalField(
        max_digits=19, decimal_places=4, default=MONEY_ZERO, validators=[MinValueValidator(MONEY_ZERO)]
    )
    estimated_total = models.DecimalField(max_digits=19, decimal_places=4)
    preferred_supplier_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "purchase_requisition_lines"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "requisition", "line_number"), name="purchase_req_line_no_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="purchase_req_line_qty_ck"),
            models.CheckConstraint(condition=Q(estimated_unit_price__gte=0), name="purchase_req_line_price_ck"),
        ]
        indexes = [models.Index(fields=("tenant_id", "item_id"), name="purchase_req_line_item_idx")]

    def __str__(self) -> str:
        return f"{self.requisition.requisition_number}/{self.line_number}"


class RFQStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    AWARDED = "awarded", "Awarded"
    CANCELLED = "cancelled", "Cancelled"


class RequestForQuotation(ProcurementRecord):
    rfq_number = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.PROTECT, null=True, blank=True, related_name="rfqs"
    )
    issue_date = models.DateField()
    submission_deadline = models.DateTimeField()
    currency = models.CharField(max_length=3, default="USD", validators=[CURRENCY_VALIDATOR])
    status = models.CharField(max_length=16, choices=RFQStatus.choices, default=RFQStatus.DRAFT)
    terms = models.TextField(blank=True)
    delivery_requirements = models.TextField(blank=True)
    awarded_quote_id = models.UUIDField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "purchase_rfqs"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "rfq_number"), name="purchase_rfq_no_uq")]
        indexes = [models.Index(fields=("tenant_id", "status", "submission_deadline"), name="purchase_rfq_status_idx")]

    def __str__(self) -> str:
        return self.rfq_number


class RFQLine(ProcurementRecord):
    rfq = models.ForeignKey(RequestForQuotation, on_delete=models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField()
    requisition_line = models.ForeignKey(PurchaseRequisitionLine, on_delete=models.PROTECT, null=True, blank=True)
    item_id = models.UUIDField(null=True, blank=True)
    item_code = models.CharField(max_length=100)
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=19, decimal_places=6, validators=[MinValueValidator(POSITIVE_QUANTITY)])
    required_date = models.DateField()
    specification = models.TextField(blank=True)

    class Meta:
        db_table = "purchase_rfq_lines"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "rfq", "line_number"), name="purchase_rfq_line_no_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="purchase_rfq_line_qty_ck"),
        ]


class RFQInvitationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    RESPONDED = "responded", "Responded"


class RFQInvitation(ProcurementRecord):
    rfq = models.ForeignKey(RequestForQuotation, on_delete=models.CASCADE, related_name="invitations")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="rfq_invitations")
    status = models.CharField(max_length=16, choices=RFQInvitationStatus.choices, default=RFQInvitationStatus.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    failure_message = models.TextField(blank=True)
    job_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "purchase_rfq_invitations"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "rfq", "supplier"), name="purchase_rfq_invite_uq")]
        indexes = [models.Index(fields=("tenant_id", "status", "created_at"), name="purchase_rfq_invite_idx")]


class QuoteStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    WITHDRAWN = "withdrawn", "Withdrawn"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class SupplierQuote(ProcurementRecord):
    quote_number = models.CharField(max_length=50)
    rfq = models.ForeignKey(RequestForQuotation, on_delete=models.PROTECT, related_name="quotes")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="quotes")
    valid_until = models.DateField()
    currency = models.CharField(max_length=3, validators=[CURRENCY_VALIDATOR])
    status = models.CharField(max_length=16, choices=QuoteStatus.choices, default=QuoteStatus.DRAFT)
    subtotal = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    tax_amount = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    shipping_amount = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    total_amount = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    delivery_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(max_length=50, default="Net 30")
    supplier_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "purchase_supplier_quotes"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "rfq", "supplier", "quote_number"), name="purchase_quote_supplier_uq"
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0, tax_amount__gte=0, shipping_amount__gte=0, total_amount__gte=0),
                name="purchase_quote_money_ck",
            ),
        ]
        indexes = [models.Index(fields=("tenant_id", "rfq", "status"), name="purchase_quote_status_idx")]

    def __str__(self) -> str:
        return self.quote_number


class SupplierQuoteLine(ProcurementRecord):
    quote = models.ForeignKey(SupplierQuote, on_delete=models.CASCADE, related_name="lines")
    rfq_line = models.ForeignKey(RFQLine, on_delete=models.PROTECT, related_name="quote_lines")
    quantity = models.DecimalField(max_digits=19, decimal_places=6, validators=[MinValueValidator(POSITIVE_QUANTITY)])
    unit_price = models.DecimalField(max_digits=19, decimal_places=4, validators=[MinValueValidator(MONEY_ZERO)])
    tax_amount = models.DecimalField(
        max_digits=19, decimal_places=4, default=MONEY_ZERO, validators=[MinValueValidator(MONEY_ZERO)]
    )
    line_total = models.DecimalField(max_digits=19, decimal_places=4)
    lead_time_days = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "purchase_supplier_quote_lines"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "quote", "rfq_line"), name="purchase_quote_line_uq"),
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_price__gte=0, tax_amount__gte=0), name="purchase_quote_line_values_ck"
            ),
        ]


class PurchaseOrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending approval"
    APPROVED = "approved", "Approved"
    SENT = "sent", "Sent"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"
    PARTIALLY_RECEIVED = "partially_received", "Partially received"
    RECEIVED = "received", "Received"
    CANCELLED = "cancelled", "Cancelled"


class PurchaseOrder(ProcurementRecord):
    po_number = models.CharField(max_length=50)
    po_date = models.DateField()
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    expected_delivery_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    currency = models.CharField(max_length=3, validators=[CURRENCY_VALIDATOR])
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders"
    )
    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders"
    )
    accepted_quote = models.ForeignKey(
        SupplierQuote, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_orders"
    )
    status = models.CharField(max_length=24, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.DRAFT)
    approved_by = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    payment_terms = models.CharField(max_length=50, default="Net 30")
    delivery_terms = models.CharField(max_length=50, blank=True)
    shipping_address = models.JSONField(default=dict)
    notes = models.TextField(blank=True)
    dispatch_status = models.CharField(
        max_length=16,
        choices=(("not_requested", "Not requested"), ("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed")),
        default="not_requested",
    )
    dispatch_job_id = models.UUIDField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "purchase_orders"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "po_number"), name="purchase_order_no_uq"),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="purchase_order_total_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "po_date"), name="purchase_order_status_idx"),
            models.Index(fields=("tenant_id", "supplier", "status"), name="purchase_order_supplier_idx"),
        ]

    def __str__(self) -> str:
        return self.po_number


class PurchaseOrderLine(ProcurementRecord):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField(default=1)
    requisition_line = models.ForeignKey(PurchaseRequisitionLine, on_delete=models.SET_NULL, null=True, blank=True)
    quote_line = models.ForeignKey(SupplierQuoteLine, on_delete=models.SET_NULL, null=True, blank=True)
    item_id = models.UUIDField(null=True, blank=True)
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=19, decimal_places=6, validators=[MinValueValidator(POSITIVE_QUANTITY)])
    unit_price = models.DecimalField(max_digits=19, decimal_places=4, validators=[MinValueValidator(MONEY_ZERO)])
    tax_amount = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    total_price = models.DecimalField(max_digits=19, decimal_places=4)
    received_quantity = models.DecimalField(max_digits=19, decimal_places=6, default=QUANTITY_ZERO)
    cancelled_quantity = models.DecimalField(max_digits=19, decimal_places=6, default=QUANTITY_ZERO)

    class Meta:
        db_table = "purchase_order_lines"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "purchase_order", "line_number"), name="purchase_order_line_no_uq"
            ),
            models.CheckConstraint(
                condition=Q(
                    quantity__gt=0,
                    unit_price__gte=0,
                    tax_amount__gte=0,
                    received_quantity__gte=0,
                    cancelled_quantity__gte=0,
                ),
                name="purchase_order_line_vals_ck",
            ),
            models.CheckConstraint(
                condition=Q(received_quantity__lte=models.F("quantity") - models.F("cancelled_quantity")),
                name="purchase_order_received_ck",
            ),
        ]
        indexes = [models.Index(fields=("tenant_id", "item_id"), name="purchase_order_line_item_idx")]

    def __str__(self) -> str:
        return f"{self.purchase_order.po_number}/{self.line_number}"


class PurchaseReceiptStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class PurchaseReceipt(ProcurementRecord):
    receipt_number = models.CharField(max_length=50)
    receipt_date = models.DateField()
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    warehouse_id = models.UUIDField()
    received_by = models.UUIDField(default=uuid.uuid4)
    status = models.CharField(max_length=16, choices=PurchaseReceiptStatus.choices, default=PurchaseReceiptStatus.DRAFT)
    completed_at = models.DateTimeField(null=True, blank=True)
    inventory_status = models.CharField(
        max_length=16,
        choices=(("not_required", "Not required"), ("pending", "Pending"), ("posted", "Posted"), ("failed", "Failed")),
        default="not_required",
    )
    inventory_reference = models.UUIDField(null=True, blank=True)
    inventory_job_id = models.UUIDField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True)
    failure_message = models.TextField(blank=True)

    class Meta:
        db_table = "purchase_receipts"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "receipt_number"), name="purchase_receipt_no_uq")]
        indexes = [
            models.Index(fields=("tenant_id", "status", "receipt_date"), name="purchase_receipt_status_idx"),
            models.Index(fields=("tenant_id", "purchase_order", "status"), name="purchase_receipt_order_idx"),
        ]

    def __str__(self) -> str:
        return self.receipt_number


class PurchaseReceiptLine(ProcurementRecord):
    purchase_receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.CASCADE, related_name="lines")
    purchase_order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipt_lines")
    line_number = models.PositiveIntegerField(default=1)
    item_id = models.UUIDField(null=True, blank=True)
    quantity_received = models.DecimalField(
        max_digits=19, decimal_places=6, validators=[MinValueValidator(POSITIVE_QUANTITY)]
    )
    condition = models.CharField(
        max_length=16,
        choices=(("accepted", "Accepted"), ("damaged", "Damaged"), ("rejected", "Rejected")),
        default="accepted",
    )
    batch_no = models.CharField(max_length=100, blank=True)
    serial_no = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "purchase_receipt_lines"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "purchase_receipt", "line_number"), name="purchase_receipt_line_no_uq"
            ),
            models.CheckConstraint(condition=Q(quantity_received__gt=0), name="purchase_receipt_line_qty_ck"),
        ]
        indexes = [models.Index(fields=("tenant_id", "item_id"), name="purchase_receipt_line_item_idx")]


class ConfigurationEnvironment(models.TextChoices):
    DEVELOPMENT = "development", "Development"
    STAGING = "staging", "Staging"
    PRODUCTION = "production", "Production"


class ConfigurationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class ProcurementConfiguration(ProcurementRecord):
    environment = models.CharField(max_length=16, choices=ConfigurationEnvironment.choices)
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=ConfigurationStatus.choices, default=ConfigurationStatus.DRAFT)
    default_currency = models.CharField(max_length=3, validators=[CURRENCY_VALIDATOR])
    default_payment_terms = models.CharField(max_length=50)
    supplier_code_prefix = models.CharField(max_length=20)
    requisition_prefix = models.CharField(max_length=20)
    rfq_prefix = models.CharField(max_length=20)
    po_prefix = models.CharField(max_length=20)
    receipt_prefix = models.CharField(max_length=20)
    approval_rules = models.JSONField(default=list)
    receipt_tolerance_percent = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    minimum_rfq_suppliers = models.PositiveSmallIntegerField(validators=[MinValueValidator(2), MaxValueValidator(20)])
    quote_scoring_weights = models.JSONField(default=dict)
    inventory_integration_enabled = models.BooleanField(default=False)
    accounting_integration_enabled = models.BooleanField(default=False)
    supplier_delivery_enabled = models.BooleanField(default=False)
    rollout = models.JSONField(default=dict)
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "purchase_configurations"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "environment", "version"), name="purchase_config_version_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "environment"),
                condition=Q(status=ConfigurationStatus.ACTIVE),
                name="purchase_config_one_active_uq",
            ),
            models.CheckConstraint(
                condition=Q(receipt_tolerance_percent__gte=0, receipt_tolerance_percent__lte=100),
                name="purchase_config_tolerance_ck",
            ),
            models.CheckConstraint(
                condition=Q(minimum_rfq_suppliers__gte=2, minimum_rfq_suppliers__lte=20),
                name="purchase_config_supplier_ck",
            ),
        ]
        indexes = [models.Index(fields=("tenant_id", "environment", "status"), name="purchase_config_status_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            prior = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if prior == ConfigurationStatus.ACTIVE:
                raise ValidationError("Activated configuration versions are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.status != ConfigurationStatus.DRAFT:
            raise ValidationError("Only draft configuration versions may be deleted.")
        return super().delete(*args, **kwargs)


# Explicit declarations supplement inheritance so startup diagnostics and
# extension tooling can enumerate the complete module contract without
# importing model MRO details.
for _tenant_model in (
    Supplier,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    RequestForQuotation,
    RFQLine,
    RFQInvitation,
    SupplierQuote,
    SupplierQuoteLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    ProcurementConfiguration,
):
    register_model_scope(_tenant_model, TENANT_SCOPED)
