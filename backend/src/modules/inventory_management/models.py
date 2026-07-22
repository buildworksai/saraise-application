"""Canonical tenant-safe inventory domain model.

The few ``legacy_*`` columns retained on existing tables are migration bridges.
They are intentionally not part of the v2 domain contract and can only be
removed after a separately verified parity migration.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from src.core.tenancy import TenantScopedModel, TimestampedModel

QUANTITY_ZERO = Decimal("0")
QUANTITY_ONE = Decimal("1")
MONEY_ZERO = Decimal("0")


class ImmutableRecordError(RuntimeError):
    """Raised when callers attempt to tamper with append-only evidence."""


class AppendOnlyQuerySet(models.QuerySet):
    """Reject bulk mutation of audit and ledger evidence."""

    def update(self, **kwargs):  # type: ignore[no-untyped-def]
        raise ImmutableRecordError("append-only records cannot be updated")

    def delete(self):  # type: ignore[no-untyped-def]
        raise ImmutableRecordError("append-only records cannot be deleted")


class AppendOnlyTenantManager(models.Manager.from_queryset(AppendOnlyQuerySet)):
    """Tenant-aware manager whose queryset also enforces immutability."""

    def for_tenant(self, tenant_id: uuid.UUID) -> AppendOnlyQuerySet:
        return self.get_queryset().filter(tenant_id=tenant_id)


class UUIDIdentityModel(models.Model):
    """Shared UUID identity without adding ownership or timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class VersionedModel(models.Model):
    """Optimistic concurrency token for mutable aggregates."""

    version = models.PositiveBigIntegerField(default=1)

    class Meta:
        abstract = True


class StatefulModel(VersionedModel):
    """Aggregate state audit storage owned by the core state machine."""

    transition_history = models.JSONField(default=list, blank=True)

    class Meta:
        abstract = True


class WarehouseType(models.TextChoices):
    DISTRIBUTION_CENTER = "distribution_center", "Distribution center"
    RETAIL_STORE = "retail_store", "Retail store"
    MANUFACTURING_PLANT = "manufacturing_plant", "Manufacturing plant"
    WAREHOUSE_3PL = "warehouse_3pl", "Third-party warehouse"
    TRANSIT = "transit", "Transit"
    CONSIGNMENT = "consignment", "Consignment"


class Warehouse(UUIDIdentityModel, TenantScopedModel, TimestampedModel, VersionedModel):
    WarehouseType = WarehouseType
    warehouse_code = models.CharField(max_length=50)
    warehouse_name = models.CharField(max_length=255)
    warehouse_type = models.CharField(max_length=32, choices=WarehouseType.choices)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state_region = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=2)
    timezone = models.CharField(max_length=64)
    contact_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    # 0001 compatibility column. V2 writes structured address fields only.
    address = models.TextField(blank=True)

    class Meta:
        db_table = "inventory_warehouses"
        ordering = ("warehouse_code", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_wh_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "warehouse_code"), name="unique_warehouse_code_per_tenant"),
            models.UniqueConstraint(
                fields=("tenant_id",),
                condition=Q(is_default=True, archived_at__isnull=True),
                name="inv_wh_one_default_uq",
            ),
        )
        indexes = (
            models.Index(fields=("tenant_id", "is_active", "warehouse_code"), name="inv_wh_active_code_ix"),
            models.Index(fields=("tenant_id", "warehouse_type", "warehouse_code"), name="inv_wh_type_code_ix"),
        )

    def __str__(self) -> str:
        return f"{self.warehouse_code} - {self.warehouse_name}"


class ZoneType(models.TextChoices):
    RECEIVING = "receiving", "Receiving"
    STORAGE = "storage", "Storage"
    PICKING = "picking", "Picking"
    PACKING = "packing", "Packing"
    SHIPPING = "shipping", "Shipping"
    QUARANTINE = "quarantine", "Quarantine"
    RETURNS = "returns", "Returns"
    TRANSIT = "transit", "Transit"


class LocationType(models.TextChoices):
    BIN = "bin", "Bin"
    SHELF = "shelf", "Shelf"
    RACK = "rack", "Rack"
    PALLET = "pallet", "Pallet"
    FLOOR = "floor", "Floor"
    DOCK = "dock", "Dock"


class StorageLocation(UUIDIdentityModel, TenantScopedModel, TimestampedModel, VersionedModel):
    ZoneType = ZoneType
    LocationType = LocationType
    warehouse = models.ForeignKey(Warehouse, models.PROTECT, related_name="locations")
    parent = models.ForeignKey("self", models.PROTECT, null=True, blank=True, related_name="children")
    location_code = models.CharField(max_length=100)
    location_name = models.CharField(max_length=255)
    zone_type = models.CharField(max_length=16, choices=ZoneType.choices)
    location_type = models.CharField(max_length=16, choices=LocationType.choices)
    barcode = models.CharField(max_length=128, blank=True)
    pick_sequence = models.PositiveIntegerField(default=0)
    capacity_units = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    capacity_weight_kg = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    capacity_volume_cbm = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    temperature_controlled = models.BooleanField(default=False)
    hazmat_approved = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inventory_storage_locations"
        ordering = ("warehouse_id", "pick_sequence", "location_code", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_loc_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "warehouse", "location_code"), name="inv_loc_code_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "warehouse", "barcode"),
                condition=~Q(barcode=""),
                name="inv_loc_barcode_uq",
            ),
            models.UniqueConstraint(
                fields=("tenant_id", "warehouse"),
                condition=Q(is_default=True, is_active=True, archived_at__isnull=True),
                name="inv_loc_default_uq",
            ),
            models.CheckConstraint(
                condition=Q(capacity_units__isnull=True) | Q(capacity_units__gt=0), name="inv_loc_capacity_units_ck"
            ),
            models.CheckConstraint(
                condition=Q(capacity_weight_kg__isnull=True) | Q(capacity_weight_kg__gt=0),
                name="inv_loc_capacity_weight_ck",
            ),
            models.CheckConstraint(
                condition=Q(capacity_volume_cbm__isnull=True) | Q(capacity_volume_cbm__gt=0),
                name="inv_loc_capacity_volume_ck",
            ),
        )
        indexes = (
            models.Index(fields=("tenant_id", "warehouse", "zone_type", "is_active"), name="inv_loc_zone_active_ix"),
            models.Index(fields=("tenant_id", "barcode"), name="inv_loc_barcode_ix"),
        )

    def __str__(self) -> str:
        return f"{self.warehouse.warehouse_code}/{self.location_code} - {self.location_name}"


class TrackingMode(models.TextChoices):
    NONE = "none", "None"
    BATCH = "batch", "Batch"
    SERIAL = "serial", "Serial"


class ValuationMethod(models.TextChoices):
    FIFO = "fifo", "FIFO"
    LIFO = "lifo", "LIFO"
    WEIGHTED_AVERAGE = "weighted_average", "Weighted average"
    STANDARD_COST = "standard_cost", "Standard cost"


class ABCClassification(models.TextChoices):
    A = "A", "A"
    B = "B", "B"
    C = "C", "C"


class Item(UUIDIdentityModel, TenantScopedModel, TimestampedModel, VersionedModel):
    TrackingMode = TrackingMode
    ValuationMethod = ValuationMethod
    ABCClassification = ABCClassification
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=128, blank=True)
    base_uom = models.CharField(max_length=32)
    tracking_mode = models.CharField(max_length=8, choices=TrackingMode.choices, default=TrackingMode.NONE)
    tracks_expiry = models.BooleanField(default=False)
    valuation_method = models.CharField(max_length=20, choices=ValuationMethod.choices, default=ValuationMethod.FIFO)
    standard_cost = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    reorder_point = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    reorder_quantity = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    safety_stock = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    default_warehouse = models.ForeignKey(Warehouse, models.PROTECT, null=True, blank=True, related_name="default_items")
    abc_classification = models.CharField(max_length=1, choices=ABCClassification.choices, blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    # 0001 compatibility columns.
    has_batch_no = models.BooleanField(default=False)
    has_serial_no = models.BooleanField(default=False)
    reorder_qty = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "inventory_items"
        ordering = ("item_code", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_item_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "item_code"), name="unique_item_code_per_tenant"),
            models.UniqueConstraint(fields=("tenant_id", "barcode"), condition=~Q(barcode=""), name="inv_item_barcode_uq"),
            models.CheckConstraint(condition=Q(reorder_point__isnull=True) | Q(reorder_point__gte=0), name="inv_item_reorder_point_ck"),
            models.CheckConstraint(condition=Q(reorder_quantity__isnull=True) | Q(reorder_quantity__gte=0), name="inv_item_reorder_qty_ck"),
            models.CheckConstraint(condition=Q(safety_stock__isnull=True) | Q(safety_stock__gte=0), name="inv_item_safety_ck"),
            models.CheckConstraint(condition=Q(standard_cost__isnull=True) | Q(standard_cost__gte=0), name="inv_item_std_cost_ck"),
            models.CheckConstraint(
                condition=~Q(valuation_method=ValuationMethod.STANDARD_COST) | Q(standard_cost__isnull=False),
                name="inv_item_std_cost_required_ck",
            ),
            models.CheckConstraint(
                condition=Q(tracks_expiry=False) | Q(tracking_mode=TrackingMode.BATCH),
                name="inv_item_expiry_batch_ck",
            ),
        )
        indexes = (
            models.Index(fields=("tenant_id", "is_active", "item_code"), name="inv_item_active_code_ix"),
            models.Index(fields=("tenant_id", "category", "item_code"), name="inv_item_category_code_ix"),
            models.Index(fields=("tenant_id", "tracking_mode"), name="inv_item_tracking_ix"),
        )

    def __str__(self) -> str:
        return f"{self.item_code} - {self.item_name}"


class BatchStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    ACTIVE = "active", "Active"
    QUARANTINED = "quarantined", "Quarantined"
    RECALLED = "recalled", "Recalled"
    EXHAUSTED = "exhausted", "Exhausted"
    EXPIRED = "expired", "Expired"


class Batch(UUIDIdentityModel, TenantScopedModel, TimestampedModel, StatefulModel):
    Status = BatchStatus
    item = models.ForeignKey(Item, models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=100)
    supplier_batch_number = models.CharField(max_length=100, blank=True)
    manufactured_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=BatchStatus.choices, default=BatchStatus.PLANNED)

    class Meta:
        db_table = "inventory_batches"
        ordering = ("item_id", "batch_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_batch_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "item", "batch_number"), name="inv_batch_number_uq"),
            models.CheckConstraint(
                condition=Q(expires_on__isnull=True) | Q(manufactured_on__isnull=True) | Q(expires_on__gte=F("manufactured_on")),
                name="inv_batch_dates_ck",
            ),
        )
        indexes = (
            models.Index(fields=("tenant_id", "item", "status"), name="inv_batch_item_status_ix"),
            models.Index(fields=("tenant_id", "expires_on", "status"), name="inv_batch_expiry_status_ix"),
        )

    def __str__(self) -> str:
        return f"{self.item.item_code}/{self.batch_number}"


class SerialStatus(models.TextChoices):
    REGISTERED = "registered", "Registered"
    IN_STOCK = "in_stock", "In stock"
    RESERVED = "reserved", "Reserved"
    IN_TRANSIT = "in_transit", "In transit"
    SOLD = "sold", "Sold"
    IN_SERVICE = "in_service", "In service"
    SCRAPPED = "scrapped", "Scrapped"


class SerialNumber(UUIDIdentityModel, TenantScopedModel, TimestampedModel, StatefulModel):
    Status = SerialStatus
    item = models.ForeignKey(Item, models.PROTECT, related_name="serial_numbers")
    serial_number = models.CharField(max_length=128)
    status = models.CharField(max_length=16, choices=SerialStatus.choices, default=SerialStatus.REGISTERED)
    current_warehouse = models.ForeignKey(Warehouse, models.PROTECT, null=True, blank=True, related_name="serial_numbers")
    current_location = models.ForeignKey(StorageLocation, models.PROTECT, null=True, blank=True, related_name="serial_numbers")
    manufacturer = models.CharField(max_length=255, blank=True)
    model_number = models.CharField(max_length=100, blank=True)
    warranty_starts_on = models.DateField(null=True, blank=True)
    warranty_ends_on = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "inventory_serial_numbers"
        ordering = ("serial_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_serial_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "serial_number"), name="inv_serial_number_uq"),
            models.CheckConstraint(
                condition=Q(warranty_ends_on__isnull=True) | Q(warranty_starts_on__isnull=True) | Q(warranty_ends_on__gte=F("warranty_starts_on")),
                name="inv_serial_warranty_ck",
            ),
            models.CheckConstraint(
                condition=(Q(current_warehouse__isnull=True) & Q(current_location__isnull=True))
                | (Q(current_warehouse__isnull=False) & Q(current_location__isnull=False)),
                name="inv_serial_dimensions_ck",
            ),
        )
        indexes = (
            models.Index(fields=("tenant_id", "item", "status"), name="inv_serial_item_status_ix"),
            models.Index(fields=("tenant_id", "current_warehouse", "status"), name="inv_serial_wh_status_ix"),
        )

    def __str__(self) -> str:
        return self.serial_number


class StockEntryType(models.TextChoices):
    RECEIPT = "receipt", "Receipt"
    ISSUE = "issue", "Issue"
    TRANSFER = "transfer", "Transfer"
    ADJUSTMENT = "adjustment", "Adjustment"
    MANUFACTURING = "manufacturing", "Manufacturing"
    RETURN = "return", "Return"
    SCRAP = "scrap", "Scrap"


class StockEntryStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    POSTED = "posted", "Posted"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    REVERSED = "reversed", "Reversed"


class StockEntry(UUIDIdentityModel, TenantScopedModel, TimestampedModel, StatefulModel):
    EntryType = StockEntryType
    Status = StockEntryStatus
    entry_number = models.CharField(max_length=50)
    entry_type = models.CharField(max_length=20, choices=StockEntryType.choices)
    posting_at = models.DateTimeField()
    source_warehouse = models.ForeignKey(Warehouse, models.PROTECT, null=True, blank=True, related_name="outbound_entries")
    destination_warehouse = models.ForeignKey(Warehouse, models.PROTECT, null=True, blank=True, related_name="inbound_entries")
    reference_module = models.CharField(max_length=64, blank=True)
    reference_type = models.CharField(max_length=64, blank=True)
    reference_id = models.UUIDField(null=True, blank=True)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=StockEntryStatus.choices, default=StockEntryStatus.DRAFT)
    idempotency_key = models.CharField(max_length=255)
    created_by_id = models.UUIDField(null=True, blank=True)
    approved_by_id = models.UUIDField(null=True, blank=True)
    posted_by_id = models.UUIDField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_of = models.OneToOneField("self", models.PROTECT, null=True, blank=True, related_name="reversal_entry")
    archived_at = models.DateTimeField(null=True, blank=True)
    # 0001 compatibility columns.
    posting_date = models.DateField(null=True, blank=True)
    warehouse = models.ForeignKey(Warehouse, models.PROTECT, null=True, blank=True, related_name="legacy_stock_entries")
    reference_document = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "inventory_stock_entries"
        ordering = ("-posting_at", "entry_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_entry_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "entry_number"), name="inventory_unique_entry_number_per_tenant"),
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="inv_entry_idempotency_uq"),
            models.CheckConstraint(
                condition=~Q(entry_type=StockEntryType.TRANSFER)
                | (Q(source_warehouse__isnull=False) & Q(destination_warehouse__isnull=False) & ~Q(source_warehouse=F("destination_warehouse"))),
                name="inv_entry_transfer_wh_ck",
            ),
            models.CheckConstraint(
                condition=~Q(entry_type__in=(StockEntryType.RECEIPT, StockEntryType.RETURN)) | Q(destination_warehouse__isnull=False),
                name="inv_entry_destination_ck",
            ),
            models.CheckConstraint(
                condition=~Q(entry_type__in=(StockEntryType.ISSUE, StockEntryType.SCRAP)) | Q(source_warehouse__isnull=False),
                name="inv_entry_source_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=StockEntryStatus.POSTED) | (Q(posted_by_id__isnull=False) & Q(posted_at__isnull=False)),
                name="inv_entry_posted_audit_ck",
            ),
        )
        indexes = (
            models.Index(fields=("tenant_id", "status", "posting_at"), name="inv_entry_status_post_ix"),
            models.Index(fields=("tenant_id", "entry_type", "posting_at"), name="inv_entry_type_post_ix"),
            models.Index(fields=("tenant_id", "reference_module", "reference_type", "reference_id"), name="inv_entry_reference_ix"),
        )

    def __str__(self) -> str:
        return f"{self.entry_number} - {self.entry_type}"


class StockEntryLine(UUIDIdentityModel, TenantScopedModel, TimestampedModel):
    stock_entry = models.ForeignKey(StockEntry, models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField()
    item = models.ForeignKey(Item, models.PROTECT, related_name="stock_entry_lines")
    source_location = models.ForeignKey(StorageLocation, models.PROTECT, null=True, blank=True, related_name="+")
    destination_location = models.ForeignKey(StorageLocation, models.PROTECT, null=True, blank=True, related_name="+")
    batch = models.ForeignKey(Batch, models.PROTECT, null=True, blank=True, related_name="stock_entry_lines")
    serial_number = models.ForeignKey(SerialNumber, models.PROTECT, null=True, blank=True, related_name="stock_entry_lines")
    quantity = models.DecimalField(max_digits=18, decimal_places=6, validators=(MinValueValidator(Decimal("0.000001")),))
    uom = models.CharField(max_length=32)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    line_value = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    notes = models.TextField(blank=True)
    # 0001 compatibility columns.
    batch_no = models.CharField(max_length=100, blank=True)
    serial_no = models.CharField(max_length=100, blank=True)
    cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "inventory_stock_entry_lines"
        ordering = ("stock_entry_id", "line_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_line_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "stock_entry", "line_number"), name="inv_line_number_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="inv_line_quantity_ck"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "stock_entry", "line_number"), name="inv_line_entry_number_ix"),
            models.Index(fields=("tenant_id", "item", "created_at"), name="inv_line_item_created_ix"),
        )

    def __str__(self) -> str:
        return f"{self.stock_entry.entry_number}/{self.line_number} - {self.item.item_code}"


class AppendOnlyModel(models.Model):
    """Instance-level append-only guard; database triggers add defense in depth."""

    objects = AppendOnlyTenantManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise ImmutableRecordError(f"{self._meta.label} records cannot be updated")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ImmutableRecordError(f"{self._meta.label} records cannot be deleted")


class StockLedgerEntry(UUIDIdentityModel, TenantScopedModel, AppendOnlyModel):
    objects = AppendOnlyTenantManager()

    stock_entry = models.ForeignKey(StockEntry, models.PROTECT, related_name="ledger_entries")
    stock_entry_line = models.ForeignKey(StockEntryLine, models.PROTECT, related_name="ledger_entries")
    sequence = models.PositiveBigIntegerField()
    item = models.ForeignKey(Item, models.PROTECT, related_name="ledger_entries")
    warehouse = models.ForeignKey(Warehouse, models.PROTECT, related_name="ledger_entries")
    location = models.ForeignKey(StorageLocation, models.PROTECT, related_name="ledger_entries")
    batch = models.ForeignKey(Batch, models.PROTECT, null=True, blank=True, related_name="ledger_entries")
    serial_number = models.ForeignKey(SerialNumber, models.PROTECT, null=True, blank=True, related_name="ledger_entries")
    quantity_delta = models.DecimalField(max_digits=18, decimal_places=6)
    quantity_after = models.DecimalField(max_digits=18, decimal_places=6)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4)
    value_delta = models.DecimalField(max_digits=19, decimal_places=4)
    value_after = models.DecimalField(max_digits=19, decimal_places=4)
    posted_at = models.DateTimeField()
    correlation_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_stock_ledger_entries"
        ordering = ("sequence", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_ledger_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "sequence"), name="inv_ledger_sequence_uq"),
            models.UniqueConstraint(fields=("tenant_id", "stock_entry_line", "warehouse", "location"), name="inv_ledger_line_dimension_uq"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "item", "warehouse", "location", "sequence"), name="inv_ledger_dimension_ix"),
            models.Index(fields=("tenant_id", "batch", "sequence"), name="inv_ledger_batch_ix"),
            models.Index(fields=("tenant_id", "serial_number", "sequence"), name="inv_ledger_serial_ix"),
        )

    def __str__(self) -> str:
        return f"{self.sequence}: {self.item_id} {self.quantity_delta}"


class StockCostLayer(UUIDIdentityModel, TenantScopedModel, TimestampedModel):
    item = models.ForeignKey(Item, models.PROTECT, related_name="cost_layers")
    warehouse = models.ForeignKey(Warehouse, models.PROTECT, related_name="cost_layers")
    location = models.ForeignKey(StorageLocation, models.PROTECT, related_name="cost_layers")
    batch = models.ForeignKey(Batch, models.PROTECT, null=True, blank=True, related_name="cost_layers")
    originating_ledger_entry = models.ForeignKey(StockLedgerEntry, models.PROTECT, related_name="cost_layers")
    received_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    remaining_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4)
    acquired_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inventory_stock_cost_layers"
        ordering = ("acquired_at", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_layer_tenant_id_uq"),
            models.CheckConstraint(condition=Q(received_quantity__gt=0), name="inv_layer_received_ck"),
            models.CheckConstraint(condition=Q(remaining_quantity__gte=0) & Q(remaining_quantity__lte=F("received_quantity")), name="inv_layer_remaining_ck"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "item", "warehouse", "location", "acquired_at"), name="inv_layer_acquired_ix"),
            models.Index(fields=("tenant_id", "item", "remaining_quantity"), name="inv_layer_remaining_ix"),
        )


class StockBalance(UUIDIdentityModel, TenantScopedModel, TimestampedModel):
    item = models.ForeignKey(Item, models.PROTECT, related_name="stock_balances")
    warehouse = models.ForeignKey(Warehouse, models.PROTECT, related_name="stock_balances")
    location = models.ForeignKey(StorageLocation, models.PROTECT, related_name="stock_balances")
    batch = models.ForeignKey(Batch, models.PROTECT, null=True, blank=True, related_name="stock_balances")
    serial_number = models.ForeignKey(SerialNumber, models.PROTECT, null=True, blank=True, related_name="stock_balances")
    quantity_on_hand = models.DecimalField(max_digits=18, decimal_places=6, default=QUANTITY_ZERO)
    quantity_allocated = models.DecimalField(max_digits=18, decimal_places=6, default=QUANTITY_ZERO)
    quantity_available = models.DecimalField(max_digits=18, decimal_places=6, default=QUANTITY_ZERO)
    stock_value = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    valuation_rate = models.DecimalField(max_digits=19, decimal_places=4, default=MONEY_ZERO)
    last_ledger_entry = models.ForeignKey(StockLedgerEntry, models.PROTECT, null=True, blank=True, related_name="resulting_balances")

    class Meta:
        db_table = "inventory_stock_balances"
        ordering = ("warehouse_id", "item_id", "location_id", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_balance_tenant_id_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "item", "warehouse", "location", "batch", "serial_number"),
                name="unique_stock_balance_per_dimensions",
                nulls_distinct=False,
            ),
            models.CheckConstraint(condition=Q(quantity_allocated__gte=0), name="inv_balance_allocated_ck"),
            models.CheckConstraint(condition=Q(quantity_available=F("quantity_on_hand") - F("quantity_allocated")), name="inv_balance_available_ck"),
            models.CheckConstraint(
                condition=Q(serial_number__isnull=True) | Q(quantity_on_hand__in=(QUANTITY_ZERO, QUANTITY_ONE)),
                name="inv_balance_serial_quantity_ck",
            ),
        )
        indexes = (
            models.Index(fields=("tenant_id", "warehouse", "item"), name="inv_balance_wh_item_ix"),
            models.Index(fields=("tenant_id", "item", "quantity_available"), name="inv_balance_available_ix"),
        )

    def __str__(self) -> str:
        return f"{self.item.item_code} @ {self.location.location_code}: {self.quantity_on_hand}"


class ReservationStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RELEASED = "released", "Released"
    CONSUMED = "consumed", "Consumed"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class StockReservation(UUIDIdentityModel, TenantScopedModel, TimestampedModel, StatefulModel):
    Status = ReservationStatus
    reservation_number = models.CharField(max_length=50)
    reference_module = models.CharField(max_length=64)
    reference_type = models.CharField(max_length=64)
    reference_id = models.UUIDField()
    item = models.ForeignKey(Item, models.PROTECT, related_name="reservations")
    warehouse = models.ForeignKey(Warehouse, models.PROTECT, related_name="reservations")
    location = models.ForeignKey(StorageLocation, models.PROTECT, null=True, blank=True, related_name="reservations")
    batch = models.ForeignKey(Batch, models.PROTECT, null=True, blank=True, related_name="reservations")
    serial_number = models.ForeignKey(SerialNumber, models.PROTECT, null=True, blank=True, related_name="reservations")
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    status = models.CharField(max_length=12, choices=ReservationStatus.choices, default=ReservationStatus.ACTIVE)
    expires_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255)

    class Meta:
        db_table = "inventory_stock_reservations"
        ordering = ("-created_at", "reservation_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_res_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "reservation_number"), name="inv_res_number_uq"),
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="inv_res_idempotency_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="inv_res_quantity_ck"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "status", "expires_at"), name="inv_res_status_expiry_ix"),
            models.Index(fields=("tenant_id", "reference_module", "reference_type", "reference_id"), name="inv_res_reference_ix"),
        )

    def __str__(self) -> str:
        return self.reservation_number


class CycleCountType(models.TextChoices):
    FULL = "full", "Full"
    ABC = "abc", "ABC"
    RANDOM = "random", "Random"
    LOCATION = "location", "Location"
    ITEM_SPECIFIC = "item_specific", "Item specific"


class CycleCountStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    POSTED = "posted", "Posted"
    CANCELLED = "cancelled", "Cancelled"


class CycleCount(UUIDIdentityModel, TenantScopedModel, TimestampedModel, StatefulModel):
    CountType = CycleCountType
    Status = CycleCountStatus
    count_number = models.CharField(max_length=50)
    warehouse = models.ForeignKey(Warehouse, models.PROTECT, related_name="cycle_counts")
    location = models.ForeignKey(StorageLocation, models.PROTECT, null=True, blank=True, related_name="cycle_counts")
    count_type = models.CharField(max_length=16, choices=CycleCountType.choices)
    scheduled_for = models.DateField()
    assigned_to_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=CycleCountStatus.choices, default=CycleCountStatus.SCHEDULED)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inventory_cycle_counts"
        ordering = ("-scheduled_for", "count_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_count_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "count_number"), name="inv_count_number_uq"),
        )
        indexes = (
            models.Index(fields=("tenant_id", "warehouse", "status", "scheduled_for"), name="inv_count_wh_status_ix"),
            models.Index(fields=("tenant_id", "assigned_to_id", "status"), name="inv_count_assignee_ix"),
        )

    def __str__(self) -> str:
        return self.count_number


class CycleCountLine(UUIDIdentityModel, TenantScopedModel, TimestampedModel):
    cycle_count = models.ForeignKey(CycleCount, models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField()
    item = models.ForeignKey(Item, models.PROTECT, related_name="cycle_count_lines")
    location = models.ForeignKey(StorageLocation, models.PROTECT, related_name="cycle_count_lines")
    batch = models.ForeignKey(Batch, models.PROTECT, null=True, blank=True, related_name="cycle_count_lines")
    serial_number = models.ForeignKey(SerialNumber, models.PROTECT, null=True, blank=True, related_name="cycle_count_lines")
    system_quantity = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    counted_quantity = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    variance_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=QUANTITY_ZERO)
    counted_by_id = models.UUIDField(null=True, blank=True)
    counted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inventory_cycle_count_lines"
        ordering = ("cycle_count_id", "line_number", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_count_line_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "cycle_count", "line_number"), name="inv_count_line_number_uq"),
            models.UniqueConstraint(
                fields=("tenant_id", "cycle_count", "item", "location", "batch", "serial_number"),
                name="inv_count_line_dimension_uq",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(counted_quantity__isnull=True) | Q(variance_quantity=F("counted_quantity") - F("system_quantity")),
                name="inv_count_line_variance_ck",
            ),
        )


class DeploymentEnvironment(models.TextChoices):
    DEVELOPMENT = "development", "Development"
    STAGING = "staging", "Staging"
    PRODUCTION = "production", "Production"


class ConfigurationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    SUPERSEDED = "superseded", "Superseded"


class InventoryConfiguration(UUIDIdentityModel, TenantScopedModel, TimestampedModel, VersionedModel):
    Environment = DeploymentEnvironment
    Status = ConfigurationStatus
    environment = models.CharField(max_length=16, choices=DeploymentEnvironment.choices)
    status = models.CharField(max_length=12, choices=ConfigurationStatus.choices, default=ConfigurationStatus.DRAFT)
    default_valuation_method = models.CharField(max_length=20, choices=ValuationMethod.choices, default=ValuationMethod.FIFO)
    allow_negative_stock = models.BooleanField(default=False)
    require_stock_entry_approval = models.BooleanField(default=True)
    enforce_creator_approver_separation = models.BooleanField(default=True)
    max_lines_per_entry = models.PositiveIntegerField(default=500, validators=(MinValueValidator(1), MaxValueValidator(5000)))
    reservation_ttl_minutes = models.PositiveIntegerField(default=1440, validators=(MinValueValidator(5), MaxValueValidator(10080)))
    expiry_warning_days = models.PositiveIntegerField(default=30, validators=(MinValueValidator(1), MaxValueValidator(3650)))
    auto_expire_batches = models.BooleanField(default=True)
    enabled_capabilities = models.JSONField(default=dict)
    rollout_rules = models.JSONField(default=dict)
    active_revision = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "inventory_configurations"
        ordering = ("environment", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_config_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "environment"), name="inv_config_environment_uq"),
            models.CheckConstraint(condition=Q(max_lines_per_entry__gte=1, max_lines_per_entry__lte=5000), name="inv_config_lines_bounds_ck"),
            models.CheckConstraint(condition=Q(reservation_ttl_minutes__gte=5, reservation_ttl_minutes__lte=10080), name="inv_config_ttl_bounds_ck"),
            models.CheckConstraint(condition=Q(expiry_warning_days__gte=1, expiry_warning_days__lte=3650), name="inv_config_expiry_bounds_ck"),
        )

    def __str__(self) -> str:
        return f"Inventory configuration ({self.environment})"


class InventoryConfigurationRevision(UUIDIdentityModel, TenantScopedModel, AppendOnlyModel):
    objects = AppendOnlyTenantManager()

    configuration = models.ForeignKey(InventoryConfiguration, models.PROTECT, related_name="revisions")
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField()
    change_reason = models.TextField()
    changed_by_id = models.UUIDField()
    correlation_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_configuration_revisions"
        ordering = ("configuration_id", "revision", "id")
        constraints = (
            models.UniqueConstraint(fields=("tenant_id", "id"), name="inv_config_rev_tenant_id_uq"),
            models.UniqueConstraint(fields=("tenant_id", "configuration", "revision"), name="inv_config_revision_uq"),
        )

    def __str__(self) -> str:
        return f"{self.configuration.environment} revision {self.revision}"
