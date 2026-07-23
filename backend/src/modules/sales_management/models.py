"""Tenant-safe persistence for the open-source quote-to-delivery funnel.

Models deliberately contain persistence invariants, not workflow behaviour.
Money calculation, numbering, transitions, and aggregate mutation belong to
``services.py`` so callers cannot obtain a different result by choosing a
different write surface.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q

from src.core.tenancy import TenantScopedModel, TimestampedModel

ZERO = Decimal("0")
HUNDRED = Decimal("100")
MAX_QUANTITY = Decimal("999999")
MAX_UNIT_PRICE = Decimal("999999999.99")
SYSTEM_ACTOR_ID = uuid.UUID(int=0)
SALES_ENVIRONMENTS = ("development", "self-hosted", "saas")

CURRENCY_VALIDATOR = RegexValidator(r"^[A-Z]{3}$", "Use a three-letter uppercase ISO-4217 currency code.")
PREFIX_VALIDATOR = RegexValidator(r"^[A-Z0-9-]{1,12}$", "Use 1-12 uppercase letters, digits, or hyphens.")


class MutableSalesModel(TenantScopedModel, TimestampedModel):
    """Shared auditable and optimistic-concurrency fields for aggregates."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.UUIDField(default=SYSTEM_ACTOR_ID, editable=False)
    updated_by = models.UUIDField(default=SYSTEM_ACTOR_ID, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.UUIDField(null=True, blank=True, editable=False)
    lock_version = models.PositiveBigIntegerField(default=1, editable=False)

    class Meta:
        abstract = True


class ImmutableRecordError(ValidationError):
    """Raised when append-only configuration evidence is tampered with."""


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableRecordError("Configuration version records are append-only.", code="immutable_record")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableRecordError("Configuration version records are append-only.", code="immutable_record")


class AppendOnlyTenantManager(models.Manager.from_queryset(AppendOnlyQuerySet)):
    def for_tenant(self, tenant_id: uuid.UUID) -> AppendOnlyQuerySet:
        return self.get_queryset().filter(tenant_id=tenant_id)


class Customer(MutableSalesModel):
    customer_code = models.CharField(max_length=50)
    customer_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD", validators=[CURRENCY_VALIDATOR])
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "sales_customers"
        ordering = ("customer_code", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="sales_customer_tenant_id_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "customer_code"),
                condition=Q(deleted_at__isnull=True),
                name="sales_customer_code_tenant_uniq",
            ),
            models.CheckConstraint(
                condition=Q(credit_limit__isnull=True) | Q(credit_limit__gte=0),
                name="sales_customer_credit_nonnegative",
            ),
            models.CheckConstraint(condition=Q(currency__regex=r"^[A-Z]{3}$"), name="sales_customer_currency_ck"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "customer_code"), name="sales_cust_code_ix"),
            models.Index(fields=("tenant_id", "is_active", "customer_name"), name="sales_cust_active_name_ix"),
            models.Index(fields=("tenant_id", "currency"), name="sales_cust_currency_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="sales_cust_deleted_ix"),
        )

    def clean(self) -> None:
        super().clean()
        self.customer_code = self.customer_code.strip()
        self.customer_name = self.customer_name.strip()
        if not self.customer_code:
            raise ValidationError({"customer_code": "Customer code cannot be blank."})
        if not self.customer_name:
            raise ValidationError({"customer_name": "Customer name cannot be blank."})

    def __str__(self) -> str:
        return f"{self.customer_code} - {self.customer_name}"


class QuotationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    CONVERTED = "converted", "Converted to order"


class Quotation(MutableSalesModel):
    quotation_number = models.CharField(max_length=50)
    quotation_date = models.DateField()
    valid_until = models.DateField(default=date.today)
    customer = models.ForeignKey(Customer, models.PROTECT, related_name="quotations")
    currency = models.CharField(max_length=3, default="USD", validators=[CURRENCY_VALIDATOR])
    subtotal_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    status = models.CharField(max_length=20, choices=QuotationStatus.choices, default=QuotationStatus.DRAFT)
    revision_number = models.PositiveIntegerField(default=1)
    revision_of = models.ForeignKey("self", models.PROTECT, null=True, blank=True, related_name="revisions")
    notes = models.TextField(blank=True)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    class Meta:
        db_table = "sales_quotations"
        ordering = ("-quotation_date", "quotation_number", "-revision_number")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="sales_quote_tenant_id_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "quotation_number", "revision_number"),
                condition=Q(deleted_at__isnull=True),
                name="sales_quote_number_rev_uq",
            ),
            models.CheckConstraint(condition=Q(valid_until__gte=F("quotation_date")), name="sales_quote_dates_ck"),
            models.CheckConstraint(condition=Q(subtotal_amount__gte=0), name="sales_quote_subtotal_ck"),
            models.CheckConstraint(condition=Q(discount_amount__gte=0), name="sales_quote_discount_ck"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="sales_quote_tax_ck"),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="sales_quote_total_ck"),
            models.CheckConstraint(condition=Q(revision_number__gte=1), name="sales_quote_revision_ck"),
            models.CheckConstraint(condition=Q(currency__regex=r"^[A-Z]{3}$"), name="sales_quote_currency_ck"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "quotation_number"), name="sales_quote_number_ix"),
            models.Index(fields=("tenant_id", "customer", "quotation_date"), name="sales_quote_customer_date_ix"),
            models.Index(fields=("tenant_id", "status", "valid_until"), name="sales_quote_status_valid_ix"),
            models.Index(fields=("tenant_id", "created_at"), name="sales_quote_created_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="sales_quote_deleted_ix"),
        )

    def clean(self) -> None:
        super().clean()
        if self.customer_id and self.customer.tenant_id != self.tenant_id:
            raise ValidationError({"customer": "Customer must belong to the quotation tenant."})
        if self.revision_of_id and self.revision_of.tenant_id != self.tenant_id:
            raise ValidationError({"revision_of": "Prior revision must belong to the quotation tenant."})

    def __str__(self) -> str:
        return f"{self.quotation_number} r{self.revision_number} - {self.customer.customer_name}"


class QuotationLine(MutableSalesModel):
    quotation = models.ForeignKey(Quotation, models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField(default=1)
    item_id = models.UUIDField(null=True, blank=True)
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit_price = models.DecimalField(max_digits=15, decimal_places=4)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    gross_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO)
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4, default=ZERO)
    tax_source = models.CharField(max_length=64, blank=True)
    tax_snapshot = models.JSONField(default=dict, blank=True)
    line_total = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)

    class Meta:
        db_table = "sales_quotation_lines"
        ordering = ("line_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="sales_quote_line_tenant_id_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "quotation", "line_number"),
                condition=Q(deleted_at__isnull=True),
                name="sales_quote_line_number_uq",
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0) & Q(quantity__lte=MAX_QUANTITY), name="sales_ql_qty_ck"),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0) & Q(unit_price__lte=MAX_UNIT_PRICE), name="sales_ql_price_ck"
            ),
            models.CheckConstraint(
                condition=Q(discount_percent__gte=0) & Q(discount_percent__lte=100), name="sales_ql_discount_pct_ck"
            ),
            models.CheckConstraint(condition=Q(gross_amount__gte=0), name="sales_ql_gross_ck"),
            models.CheckConstraint(condition=Q(discount_amount__gte=0), name="sales_ql_discount_ck"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="sales_ql_tax_ck"),
            models.CheckConstraint(condition=Q(tax_rate__gte=0) & Q(tax_rate__lte=100), name="sales_ql_tax_rate_ck"),
            models.CheckConstraint(condition=Q(line_total__gte=0), name="sales_ql_total_ck"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "quotation", "line_number"), name="sales_ql_quote_line_ix"),
            models.Index(fields=("tenant_id", "item_id"), name="sales_ql_item_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="sales_ql_deleted_ix"),
        )

    def clean(self) -> None:
        super().clean()
        if self.quotation_id and self.quotation.tenant_id != self.tenant_id:
            raise ValidationError({"quotation": "Quotation line and quotation tenants must match."})

    def __str__(self) -> str:
        return f"{self.quotation.quotation_number}/{self.line_number} - {self.item_code}"


class SalesOrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    CONFIRMED = "confirmed", "Confirmed"
    PICKING = "picking", "Picking"
    PACKING = "packing", "Packing"
    READY_TO_SHIP = "ready_to_ship", "Ready to ship"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    INVOICED = "invoiced", "Invoiced"
    CANCELLED = "cancelled", "Cancelled"


class SalesOrder(MutableSalesModel):
    order_number = models.CharField(max_length=50)
    order_date = models.DateField()
    delivery_date = models.DateField(null=True, blank=True)
    customer = models.ForeignKey(Customer, models.PROTECT, related_name="sales_orders")
    quotation = models.ForeignKey(Quotation, models.PROTECT, null=True, blank=True, related_name="sales_orders")
    currency = models.CharField(max_length=3, default="USD", validators=[CURRENCY_VALIDATOR])
    subtotal_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    status = models.CharField(max_length=30, choices=SalesOrderStatus.choices, default=SalesOrderStatus.DRAFT)
    warehouse_id = models.UUIDField(null=True, blank=True)
    external_invoice_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    class Meta:
        db_table = "sales_orders"
        ordering = ("-order_date", "order_number")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="sales_order_tenant_id_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "order_number"),
                condition=Q(deleted_at__isnull=True),
                name="sales_order_number_tenant_uq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "quotation"),
                condition=Q(quotation__isnull=False, deleted_at__isnull=True),
                name="sales_order_quote_once_uq",
            ),
            models.CheckConstraint(
                condition=Q(delivery_date__isnull=True) | Q(delivery_date__gte=F("order_date")),
                name="sales_order_dates_ck",
            ),
            models.CheckConstraint(condition=Q(subtotal_amount__gte=0), name="sales_order_subtotal_ck"),
            models.CheckConstraint(condition=Q(discount_amount__gte=0), name="sales_order_discount_ck"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="sales_order_tax_ck"),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="sales_order_total_ck"),
            models.CheckConstraint(condition=Q(currency__regex=r"^[A-Z]{3}$"), name="sales_order_currency_ck"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "order_number"), name="sales_order_number_ix"),
            models.Index(fields=("tenant_id", "customer", "order_date"), name="sales_order_customer_date_ix"),
            models.Index(fields=("tenant_id", "status", "delivery_date"), name="sales_order_status_date_ix"),
            models.Index(fields=("tenant_id", "warehouse_id"), name="sales_order_warehouse_ix"),
            models.Index(fields=("tenant_id", "quotation"), name="sales_order_quote_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="sales_order_deleted_ix"),
        )

    def clean(self) -> None:
        super().clean()
        if self.customer_id and self.customer.tenant_id != self.tenant_id:
            raise ValidationError({"customer": "Customer must belong to the sales-order tenant."})
        if self.quotation_id:
            if self.quotation.tenant_id != self.tenant_id:
                raise ValidationError({"quotation": "Quotation must belong to the sales-order tenant."})
            if self.quotation.customer_id != self.customer_id:
                raise ValidationError({"quotation": "Quotation and order customer must match."})

    def __str__(self) -> str:
        return f"{self.order_number} - {self.customer.customer_name}"


class SalesOrderLine(MutableSalesModel):
    sales_order = models.ForeignKey(SalesOrder, models.CASCADE, related_name="lines")
    source_quotation_line_id = models.UUIDField(null=True, blank=True)
    line_number = models.PositiveIntegerField(default=1)
    item_id = models.UUIDField(null=True, blank=True)
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit_price = models.DecimalField(max_digits=15, decimal_places=4)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    gross_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO)
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4, default=ZERO)
    tax_source = models.CharField(max_length=64, blank=True)
    tax_snapshot = models.JSONField(default=dict, blank=True)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=ZERO, editable=False)
    delivered_quantity = models.DecimalField(max_digits=15, decimal_places=4, default=ZERO, editable=False)

    class Meta:
        db_table = "sales_order_lines"
        ordering = ("line_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="sales_order_line_tenant_id_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "sales_order", "line_number"),
                condition=Q(deleted_at__isnull=True),
                name="sales_order_line_number_uq",
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0) & Q(quantity__lte=MAX_QUANTITY), name="sales_ol_qty_ck"),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0) & Q(unit_price__lte=MAX_UNIT_PRICE), name="sales_ol_price_ck"
            ),
            models.CheckConstraint(
                condition=Q(discount_percent__gte=0) & Q(discount_percent__lte=100), name="sales_ol_discount_pct_ck"
            ),
            models.CheckConstraint(condition=Q(gross_amount__gte=0), name="sales_ol_gross_ck"),
            models.CheckConstraint(condition=Q(discount_amount__gte=0), name="sales_ol_discount_ck"),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name="sales_ol_tax_ck"),
            models.CheckConstraint(condition=Q(tax_rate__gte=0) & Q(tax_rate__lte=100), name="sales_ol_tax_rate_ck"),
            models.CheckConstraint(condition=Q(total_price__gte=0), name="sales_ol_total_ck"),
            models.CheckConstraint(
                condition=Q(delivered_quantity__gte=0) & Q(delivered_quantity__lte=F("quantity")),
                name="sales_ol_delivered_ck",
            ),
        )
        indexes = (
            models.Index(fields=("tenant_id", "sales_order", "line_number"), name="sales_ol_order_line_ix"),
            models.Index(fields=("tenant_id", "item_id"), name="sales_ol_item_ix"),
            models.Index(fields=("tenant_id", "delivered_quantity"), name="sales_ol_delivered_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="sales_ol_deleted_ix"),
        )

    def clean(self) -> None:
        super().clean()
        if self.sales_order_id and self.sales_order.tenant_id != self.tenant_id:
            raise ValidationError({"sales_order": "Order line and order tenants must match."})

    def __str__(self) -> str:
        return f"{self.sales_order.order_number}/{self.line_number} - {self.item_code}"


class DeliveryNoteStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class DeliveryNote(MutableSalesModel):
    delivery_number = models.CharField(max_length=50)
    delivery_date = models.DateField()
    sales_order = models.ForeignKey(SalesOrder, models.PROTECT, related_name="delivery_notes")
    warehouse_id = models.UUIDField(null=True, blank=True)
    carrier_name = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)
    proof_document_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=DeliveryNoteStatus.choices, default=DeliveryNoteStatus.DRAFT)
    notes = models.TextField(blank=True)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    class Meta:
        db_table = "sales_delivery_notes"
        ordering = ("-delivery_date", "delivery_number")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="sales_delivery_tenant_id_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "delivery_number"),
                condition=Q(deleted_at__isnull=True),
                name="sales_delivery_number_uq",
            ),
            models.CheckConstraint(
                condition=Q(tracking_number="") | ~Q(carrier_name=""), name="sales_delivery_tracking_ck"
            ),
        )
        indexes = (
            models.Index(fields=("tenant_id", "delivery_number"), name="sales_delivery_number_ix"),
            models.Index(fields=("tenant_id", "sales_order", "delivery_date"), name="sales_delivery_order_date_ix"),
            models.Index(fields=("tenant_id", "status", "delivery_date"), name="sales_delivery_status_date_ix"),
            models.Index(fields=("tenant_id", "tracking_number"), name="sales_delivery_tracking_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="sales_delivery_deleted_ix"),
        )

    def clean(self) -> None:
        super().clean()
        if self.sales_order_id and self.sales_order.tenant_id != self.tenant_id:
            raise ValidationError({"sales_order": "Delivery note and order tenants must match."})

    def __str__(self) -> str:
        return f"{self.delivery_number} - {self.sales_order.order_number}"


class DeliveryNoteLine(MutableSalesModel):
    delivery_note = models.ForeignKey(DeliveryNote, models.CASCADE, related_name="lines")
    sales_order_line = models.ForeignKey(SalesOrderLine, models.PROTECT, related_name="delivery_lines")
    line_number = models.PositiveIntegerField(default=1)
    item_id = models.UUIDField(null=True, blank=True)
    quantity_delivered = models.DecimalField(max_digits=15, decimal_places=4)
    batch_number = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "sales_delivery_note_lines"
        ordering = ("line_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="sales_delivery_line_tenant_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "delivery_note", "line_number"),
                condition=Q(deleted_at__isnull=True),
                name="sales_delivery_line_number_uq",
            ),
            models.CheckConstraint(condition=Q(quantity_delivered__gt=0), name="sales_dl_quantity_ck"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "delivery_note", "line_number"), name="sales_dl_note_line_ix"),
            models.Index(fields=("tenant_id", "sales_order_line"), name="sales_dl_order_line_ix"),
            models.Index(fields=("tenant_id", "item_id"), name="sales_dl_item_ix"),
            models.Index(fields=("tenant_id", "serial_number"), name="sales_dl_serial_ix"),
            models.Index(fields=("tenant_id", "deleted_at"), name="sales_dl_deleted_ix"),
        )

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.delivery_note_id and self.delivery_note.tenant_id != self.tenant_id:
            errors["delivery_note"] = "Delivery line and delivery-note tenants must match."
        if self.sales_order_line_id:
            source = self.sales_order_line
            if source.tenant_id != self.tenant_id:
                errors["sales_order_line"] = "Delivery line and order-line tenants must match."
            elif self.delivery_note_id and source.sales_order_id != self.delivery_note.sales_order_id:
                errors["sales_order_line"] = "Order line must belong to the delivery note's order."
            if self.item_id != source.item_id:
                errors["item_id"] = "Item must equal the source order-line item."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.delivery_note.delivery_number}/{self.line_number} - {self.quantity_delivered}"


CONFIGURATION_FIELDS = frozenset(
    {
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
    }
)


def validate_configuration_snapshot(value: Any) -> None:
    """Validate the portable configuration document without trusting clients."""

    if not isinstance(value, dict):
        raise ValidationError("Configuration snapshot must be a JSON object.", code="invalid_snapshot")
    unknown = set(value) - CONFIGURATION_FIELDS
    missing = CONFIGURATION_FIELDS - set(value)
    if unknown or missing:
        raise ValidationError(
            "Snapshot keys do not match the configuration schema; "
            f"missing={sorted(missing)}, unknown={sorted(unknown)}.",
            code="invalid_snapshot_schema",
        )
    currency = value["default_currency"]
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
        raise ValidationError("default_currency must be an uppercase three-letter code.", code="invalid_currency")
    integer_bounds = {
        "currency_decimal_places": (0, 4),
        "quotation_validity_days": (1, 365),
        "sequence_padding": (4, 12),
    }
    for key, (minimum, maximum) in integer_bounds.items():
        item = value[key]
        if not isinstance(item, int) or isinstance(item, bool) or not minimum <= item <= maximum:
            raise ValidationError(f"{key} must be between {minimum} and {maximum}.", code="invalid_bound")
    for key in (
        "credit_check_enabled",
        "inventory_confirmation_required",
        "manual_discount_enabled",
        "manual_tax_enabled",
    ):
        if not isinstance(value[key], bool):
            raise ValidationError(f"{key} must be boolean.", code="invalid_boolean")
    try:
        discount = Decimal(str(value["maximum_manual_discount_percent"]))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("maximum_manual_discount_percent must be decimal.", code="invalid_discount") from exc
    if not ZERO <= discount <= HUNDRED:
        raise ValidationError("maximum_manual_discount_percent must be between 0 and 100.", code="invalid_discount")
    for key in ("quotation_prefix", "order_prefix", "delivery_prefix"):
        PREFIX_VALIDATOR(value[key])
    if value["rounding_mode"] not in SalesRoundingMode.values:
        raise ValidationError("rounding_mode is not supported.", code="invalid_rounding_mode")


class SalesRoundingMode(models.TextChoices):
    HALF_UP = "ROUND_HALF_UP", "Half up"
    HALF_EVEN = "ROUND_HALF_EVEN", "Half even"


class SalesConfiguration(MutableSalesModel):
    environment = models.CharField(max_length=32, choices=tuple((item, item) for item in SALES_ENVIRONMENTS))
    default_currency = models.CharField(max_length=3, default="USD", validators=[CURRENCY_VALIDATOR])
    currency_decimal_places = models.PositiveSmallIntegerField(default=2, validators=[MaxValueValidator(4)])
    rounding_mode = models.CharField(
        max_length=20, choices=SalesRoundingMode.choices, default=SalesRoundingMode.HALF_UP
    )
    quotation_validity_days = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(1), MaxValueValidator(365)]
    )
    credit_check_enabled = models.BooleanField(default=True)
    inventory_confirmation_required = models.BooleanField(default=False)
    manual_discount_enabled = models.BooleanField(default=True)
    maximum_manual_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20"),
        validators=[MinValueValidator(ZERO), MaxValueValidator(HUNDRED)],
    )
    manual_tax_enabled = models.BooleanField(default=True)
    quotation_prefix = models.CharField(max_length=12, default="QT", validators=[PREFIX_VALIDATOR])
    order_prefix = models.CharField(max_length=12, default="SO", validators=[PREFIX_VALIDATOR])
    delivery_prefix = models.CharField(max_length=12, default="DN", validators=[PREFIX_VALIDATOR])
    sequence_padding = models.PositiveSmallIntegerField(
        default=6, validators=[MinValueValidator(4), MaxValueValidator(12)]
    )
    version = models.PositiveBigIntegerField(default=1, editable=False)

    class Meta:
        db_table = "sales_configurations"
        ordering = ("environment",)
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="sales_config_tenant_id_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "environment"),
                condition=Q(deleted_at__isnull=True),
                name="sales_config_environment_uq",
            ),
            models.CheckConstraint(condition=Q(environment__in=SALES_ENVIRONMENTS), name="sales_config_environment_ck"),
            models.CheckConstraint(condition=Q(default_currency__regex=r"^[A-Z]{3}$"), name="sales_config_currency_ck"),
            models.CheckConstraint(
                condition=Q(quotation_prefix__regex=r"^[A-Z0-9-]{1,12}$"), name="sales_config_quote_prefix_ck"
            ),
            models.CheckConstraint(
                condition=Q(order_prefix__regex=r"^[A-Z0-9-]{1,12}$"), name="sales_config_order_prefix_ck"
            ),
            models.CheckConstraint(
                condition=Q(delivery_prefix__regex=r"^[A-Z0-9-]{1,12}$"), name="sales_config_delivery_prefix_ck"
            ),
            models.CheckConstraint(
                condition=Q(quotation_validity_days__gte=1) & Q(quotation_validity_days__lte=365),
                name="sales_config_validity_ck",
            ),
            models.CheckConstraint(
                condition=Q(currency_decimal_places__gte=0) & Q(currency_decimal_places__lte=4),
                name="sales_config_precision_ck",
            ),
            models.CheckConstraint(
                condition=Q(maximum_manual_discount_percent__gte=0) & Q(maximum_manual_discount_percent__lte=100),
                name="sales_config_discount_ck",
            ),
            models.CheckConstraint(
                condition=Q(sequence_padding__gte=4) & Q(sequence_padding__lte=12), name="sales_config_padding_ck"
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="sales_config_version_ck"),
        )
        indexes = (models.Index(fields=("tenant_id", "environment"), name="sales_config_environment_ix"),)

    def __str__(self) -> str:
        return f"{self.environment} v{self.version}"


class SalesConfigurationVersion(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    configuration = models.ForeignKey(SalesConfiguration, models.PROTECT, related_name="versions")
    version = models.PositiveBigIntegerField()
    snapshot = models.JSONField(validators=[validate_configuration_snapshot])
    change_reason = models.CharField(max_length=500)
    actor_id = models.UUIDField()
    correlation_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyTenantManager()

    class Meta:
        db_table = "sales_configuration_versions"
        ordering = ("-version", "-created_at")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "configuration", "version"), name="sales_config_version_uq"),
            models.CheckConstraint(condition=Q(version__gte=1), name="sales_config_hist_version_ck"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "configuration", "-version"), name="sales_config_hist_version_ix"),
            models.Index(fields=("tenant_id", "-created_at"), name="sales_config_hist_created_ix"),
            models.Index(fields=("tenant_id", "correlation_id"), name="sales_config_hist_corr_ix"),
        )

    def clean(self) -> None:
        super().clean()
        if self.configuration_id and self.configuration.tenant_id != self.tenant_id:
            raise ValidationError({"configuration": "Configuration version and configuration tenants must match."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableRecordError("Configuration version records are append-only.", code="immutable_record")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableRecordError("Configuration version records are append-only.", code="immutable_record")

    def __str__(self) -> str:
        return f"{self.configuration.environment} v{self.version}"


class SalesDocumentKind(models.TextChoices):
    QUOTATION = "quotation", "Quotation"
    SALES_ORDER = "sales_order", "Sales order"
    DELIVERY_NOTE = "delivery_note", "Delivery note"


class SalesDocumentSequence(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.CharField(max_length=32, choices=tuple((item, item) for item in SALES_ENVIRONMENTS))
    document_kind = models.CharField(max_length=20, choices=SalesDocumentKind.choices)
    next_value = models.PositiveBigIntegerField(default=1)
    lock_version = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sales_document_sequences"
        ordering = ("environment", "document_kind")
        constraints = (
            models.UniqueConstraint(
                fields=("tenant_id", "environment", "document_kind"), name="sales_document_sequence_uq"
            ),
            models.CheckConstraint(
                condition=Q(environment__in=SALES_ENVIRONMENTS), name="sales_sequence_environment_ck"
            ),
            models.CheckConstraint(condition=Q(next_value__gte=1), name="sales_sequence_next_ck"),
            models.CheckConstraint(condition=Q(lock_version__gte=1), name="sales_sequence_lock_ck"),
        )
        indexes = (models.Index(fields=("tenant_id", "environment", "document_kind"), name="sales_sequence_lookup_ix"),)

    def __str__(self) -> str:
        return f"{self.environment}:{self.document_kind}={self.next_value}"
