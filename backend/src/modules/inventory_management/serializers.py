"""Strict transport contracts for the governed inventory API.

Input serializers deliberately use UUID identifiers rather than model-backed
relation fields.  Tenant ownership and relational validity are service-layer
concerns and must be checked inside the transaction that performs the command.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from src.core.async_jobs.models import AsyncJob

from .models import (
    Batch,
    CycleCount,
    InventoryConfiguration,
    InventoryConfigurationRevision,
    Item,
    SerialNumber,
    StockBalance,
    StockEntry,
    StockLedgerEntry,
    StockReservation,
    StorageLocation,
    Warehouse,
)


class StrictSerializer(serializers.Serializer):
    """Reject unknown input fields instead of silently discarding them."""

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        unknown = set(getattr(self, "initial_data", {})) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {name: "Field is not accepted from clients." for name in sorted(unknown)}
            )
        return super().validate(attrs)


class CommandAwareModelSerializer(serializers.ModelSerializer):
    """Expose server-adjudicated command affordances on aggregate responses."""

    allowed_commands = serializers.SerializerMethodField()
    denial_reasons = serializers.SerializerMethodField()

    def get_allowed_commands(self, obj):  # type: ignore[no-untyped-def]
        values = getattr(obj, "allowed_commands", None)
        if values is None:
            values = self.context.get("allowed_commands", ())
        return list(values)

    def get_denial_reasons(self, obj):  # type: ignore[no-untyped-def]
        values = getattr(obj, "denial_reasons", None)
        if values is None:
            values = self.context.get("denial_reasons", ())
        return list(values)


WAREHOUSE_READ_FIELDS = [
    "id", "warehouse_code", "warehouse_name", "warehouse_type", "address_line1",
    "address_line2", "city", "state_region", "postal_code", "country_code", "timezone",
    "contact_name", "contact_email", "contact_phone", "is_default", "is_active", "version",
    "archived_at", "created_at", "updated_at", "allowed_commands", "denial_reasons",
]


class WarehouseListSerializer(CommandAwareModelSerializer):
    class Meta:
        model = Warehouse
        fields = WAREHOUSE_READ_FIELDS
        read_only_fields = fields


class WarehouseDetailSerializer(WarehouseListSerializer):
    pass


class WarehouseCreateSerializer(StrictSerializer):
    warehouse_code = serializers.CharField(max_length=50)
    warehouse_name = serializers.CharField(max_length=255)
    warehouse_type = serializers.ChoiceField(choices=Warehouse.WarehouseType.choices)
    address_line1 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state_region = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country_code = serializers.CharField(min_length=2, max_length=2)
    timezone = serializers.CharField(max_length=64)
    contact_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    is_default = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


class WarehouseUpdateSerializer(WarehouseCreateSerializer):
    warehouse_code = serializers.CharField(max_length=50, required=False)
    warehouse_name = serializers.CharField(max_length=255, required=False)
    warehouse_type = serializers.ChoiceField(choices=Warehouse.WarehouseType.choices, required=False)
    country_code = serializers.CharField(min_length=2, max_length=2, required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)


LOCATION_READ_FIELDS = [
    "id", "warehouse_id", "parent_id", "location_code", "location_name", "zone_type",
    "location_type", "barcode", "pick_sequence", "capacity_units", "capacity_weight_kg",
    "capacity_volume_cbm", "temperature_controlled", "hazmat_approved", "is_default",
    "is_active", "version", "archived_at", "created_at", "updated_at", "allowed_commands",
    "denial_reasons",
]


class StorageLocationListSerializer(CommandAwareModelSerializer):
    class Meta:
        model = StorageLocation
        fields = LOCATION_READ_FIELDS
        read_only_fields = fields


class StorageLocationDetailSerializer(StorageLocationListSerializer):
    pass


class StorageLocationCreateSerializer(StrictSerializer):
    warehouse_id = serializers.UUIDField()
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    location_code = serializers.CharField(max_length=100)
    location_name = serializers.CharField(max_length=255)
    zone_type = serializers.ChoiceField(choices=StorageLocation.ZoneType.choices)
    location_type = serializers.ChoiceField(choices=StorageLocation.LocationType.choices)
    barcode = serializers.CharField(max_length=128, required=False, allow_blank=True)
    pick_sequence = serializers.IntegerField(min_value=0, required=False)
    capacity_units = serializers.DecimalField(18, 6, required=False, allow_null=True, min_value=0)
    capacity_weight_kg = serializers.DecimalField(18, 6, required=False, allow_null=True, min_value=0)
    capacity_volume_cbm = serializers.DecimalField(18, 6, required=False, allow_null=True, min_value=0)
    temperature_controlled = serializers.BooleanField(required=False)
    hazmat_approved = serializers.BooleanField(required=False)
    is_default = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


class StorageLocationUpdateSerializer(StorageLocationCreateSerializer):
    warehouse_id = serializers.UUIDField(required=False)
    location_code = serializers.CharField(max_length=100, required=False)
    location_name = serializers.CharField(max_length=255, required=False)
    zone_type = serializers.ChoiceField(choices=StorageLocation.ZoneType.choices, required=False)
    location_type = serializers.ChoiceField(choices=StorageLocation.LocationType.choices, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)


ITEM_READ_FIELDS = [
    "id", "item_code", "item_name", "description", "category", "brand", "barcode", "base_uom",
    "tracking_mode", "tracks_expiry", "valuation_method", "standard_cost", "reorder_point",
    "reorder_quantity", "safety_stock", "default_warehouse_id", "abc_classification", "is_active",
    "version", "archived_at", "created_at", "updated_at", "allowed_commands", "denial_reasons",
]


class ItemListSerializer(CommandAwareModelSerializer):
    class Meta:
        model = Item
        fields = ITEM_READ_FIELDS
        read_only_fields = fields


class ItemDetailSerializer(ItemListSerializer):
    pass


class ItemCreateSerializer(StrictSerializer):
    item_code = serializers.CharField(max_length=100)
    item_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(max_length=100, required=False, allow_blank=True)
    brand = serializers.CharField(max_length=100, required=False, allow_blank=True)
    barcode = serializers.CharField(max_length=128, required=False, allow_blank=True)
    base_uom = serializers.CharField(max_length=32)
    tracking_mode = serializers.ChoiceField(choices=Item.TrackingMode.choices)
    tracks_expiry = serializers.BooleanField(required=False)
    valuation_method = serializers.ChoiceField(choices=Item.ValuationMethod.choices)
    standard_cost = serializers.DecimalField(19, 4, required=False, allow_null=True, min_value=0)
    reorder_point = serializers.DecimalField(18, 6, required=False, allow_null=True, min_value=0)
    reorder_quantity = serializers.DecimalField(18, 6, required=False, allow_null=True, min_value=0)
    safety_stock = serializers.DecimalField(18, 6, required=False, allow_null=True, min_value=0)
    default_warehouse_id = serializers.UUIDField(required=False, allow_null=True)
    abc_classification = serializers.ChoiceField(choices=Item.ABCClassification.choices, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class ItemUpdateSerializer(ItemCreateSerializer):
    item_code = serializers.CharField(max_length=100, required=False)
    item_name = serializers.CharField(max_length=255, required=False)
    base_uom = serializers.CharField(max_length=32, required=False)
    tracking_mode = serializers.ChoiceField(choices=Item.TrackingMode.choices, required=False)
    valuation_method = serializers.ChoiceField(choices=Item.ValuationMethod.choices, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)


BATCH_READ_FIELDS = [
    "id", "item_id", "batch_number", "supplier_batch_number", "manufactured_on", "expires_on",
    "status", "version", "transition_history", "created_at", "updated_at", "allowed_commands",
    "denial_reasons",
]


class BatchListSerializer(CommandAwareModelSerializer):
    class Meta:
        model = Batch
        fields = BATCH_READ_FIELDS
        read_only_fields = fields


class BatchDetailSerializer(BatchListSerializer):
    pass


class BatchCreateSerializer(StrictSerializer):
    item_id = serializers.UUIDField()
    batch_number = serializers.CharField(max_length=100)
    supplier_batch_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    manufactured_on = serializers.DateField(required=False, allow_null=True)
    expires_on = serializers.DateField(required=False, allow_null=True)


class BatchUpdateSerializer(StrictSerializer):
    supplier_batch_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    manufactured_on = serializers.DateField(required=False, allow_null=True)
    expires_on = serializers.DateField(required=False, allow_null=True)
    expected_version = serializers.IntegerField(min_value=1, required=False)


SERIAL_READ_FIELDS = [
    "id", "item_id", "serial_number", "status", "current_warehouse_id", "current_location_id",
    "manufacturer", "model_number", "warranty_starts_on", "warranty_ends_on", "version",
    "transition_history", "created_at", "updated_at", "allowed_commands", "denial_reasons",
]


class SerialNumberListSerializer(CommandAwareModelSerializer):
    class Meta:
        model = SerialNumber
        fields = SERIAL_READ_FIELDS
        read_only_fields = fields


class SerialNumberDetailSerializer(SerialNumberListSerializer):
    pass


class SerialNumberCreateSerializer(StrictSerializer):
    item_id = serializers.UUIDField()
    serial_number = serializers.CharField(max_length=128)
    manufacturer = serializers.CharField(max_length=255, required=False, allow_blank=True)
    model_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    warranty_starts_on = serializers.DateField(required=False, allow_null=True)
    warranty_ends_on = serializers.DateField(required=False, allow_null=True)


class SerialNumberUpdateSerializer(StrictSerializer):
    manufacturer = serializers.CharField(max_length=255, required=False, allow_blank=True)
    model_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    warranty_starts_on = serializers.DateField(required=False, allow_null=True)
    warranty_ends_on = serializers.DateField(required=False, allow_null=True)
    expected_version = serializers.IntegerField(min_value=1, required=False)


class StockEntryLineInputSerializer(StrictSerializer):
    line_number = serializers.IntegerField(min_value=1)
    item_id = serializers.UUIDField()
    source_location_id = serializers.UUIDField(required=False, allow_null=True)
    destination_location_id = serializers.UUIDField(required=False, allow_null=True)
    batch_id = serializers.UUIDField(required=False, allow_null=True)
    serial_number_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.DecimalField(18, 6, min_value=Decimal("0.000001"))
    uom = serializers.CharField(max_length=32)
    unit_cost = serializers.DecimalField(19, 4, required=False, allow_null=True, min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True)


class StockEntryLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    line_number = serializers.IntegerField(read_only=True)
    item_id = serializers.UUIDField(read_only=True)
    source_location_id = serializers.UUIDField(read_only=True, allow_null=True)
    destination_location_id = serializers.UUIDField(read_only=True, allow_null=True)
    batch_id = serializers.UUIDField(read_only=True, allow_null=True)
    serial_number_id = serializers.UUIDField(read_only=True, allow_null=True)
    quantity = serializers.DecimalField(18, 6, read_only=True)
    uom = serializers.CharField(read_only=True)
    unit_cost = serializers.DecimalField(19, 4, read_only=True, allow_null=True)
    line_value = serializers.DecimalField(19, 4, read_only=True)
    notes = serializers.CharField(read_only=True)


STOCK_ENTRY_READ_FIELDS = [
    "id", "entry_number", "entry_type", "posting_at", "source_warehouse_id",
    "destination_warehouse_id", "reference_module", "reference_type", "reference_id", "reason",
    "status", "approved_at", "posted_at", "reversed_at", "reversal_of_id", "version",
    "archived_at", "created_at", "updated_at", "allowed_commands", "denial_reasons",
]


class StockEntryListSerializer(CommandAwareModelSerializer):
    class Meta:
        model = StockEntry
        fields = STOCK_ENTRY_READ_FIELDS
        read_only_fields = fields


class StockEntryDetailSerializer(StockEntryListSerializer):
    lines = StockEntryLineSerializer(many=True, read_only=True)

    class Meta(StockEntryListSerializer.Meta):
        fields = [*STOCK_ENTRY_READ_FIELDS, "lines"]


class StockEntryCreateSerializer(StrictSerializer):
    entry_number = serializers.CharField(max_length=50)
    entry_type = serializers.ChoiceField(choices=StockEntry.EntryType.choices)
    posting_at = serializers.DateTimeField()
    source_warehouse_id = serializers.UUIDField(required=False, allow_null=True)
    destination_warehouse_id = serializers.UUIDField(required=False, allow_null=True)
    reference_module = serializers.CharField(max_length=64, required=False, allow_blank=True)
    reference_type = serializers.CharField(max_length=64, required=False, allow_blank=True)
    reference_id = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    lines = StockEntryLineInputSerializer(many=True)


class StockEntryUpdateSerializer(StockEntryCreateSerializer):
    entry_number = serializers.CharField(max_length=50, required=False)
    entry_type = serializers.ChoiceField(choices=StockEntry.EntryType.choices, required=False)
    posting_at = serializers.DateTimeField(required=False)
    lines = StockEntryLineInputSerializer(many=True, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)


class StockBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockBalance
        fields = [
            "id", "item_id", "warehouse_id", "location_id", "batch_id", "serial_number_id",
            "quantity_on_hand", "quantity_allocated", "quantity_available", "stock_value",
            "valuation_rate", "last_ledger_entry_id", "created_at", "updated_at",
        ]
        read_only_fields = fields


class StockLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLedgerEntry
        fields = [
            "id", "stock_entry_id", "stock_entry_line_id", "sequence", "item_id", "warehouse_id",
            "location_id", "batch_id", "serial_number_id", "quantity_delta", "quantity_after",
            "unit_cost", "value_delta", "value_after", "posted_at", "correlation_id", "created_at",
        ]
        read_only_fields = fields


RESERVATION_READ_FIELDS = [
    "id", "reservation_number", "reference_module", "reference_type", "reference_id", "item_id",
    "warehouse_id", "location_id", "batch_id", "serial_number_id", "quantity", "status",
    "expires_at", "version", "transition_history", "created_at", "updated_at", "allowed_commands",
    "denial_reasons",
]


class ReservationListSerializer(CommandAwareModelSerializer):
    class Meta:
        model = StockReservation
        fields = RESERVATION_READ_FIELDS
        read_only_fields = fields


class ReservationDetailSerializer(ReservationListSerializer):
    pass


class ReservationCreateSerializer(StrictSerializer):
    reservation_number = serializers.CharField(max_length=50)
    reference_module = serializers.CharField(max_length=64)
    reference_type = serializers.CharField(max_length=64)
    reference_id = serializers.UUIDField()
    item_id = serializers.UUIDField()
    warehouse_id = serializers.UUIDField()
    location_id = serializers.UUIDField(required=False, allow_null=True)
    batch_id = serializers.UUIDField(required=False, allow_null=True)
    serial_number_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.DecimalField(18, 6, min_value=Decimal("0.000001"))
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class ReservationUpdateSerializer(StrictSerializer):
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    expected_version = serializers.IntegerField(min_value=1, required=False)


class CycleCountLineInputSerializer(StrictSerializer):
    line_number = serializers.IntegerField(min_value=1)
    item_id = serializers.UUIDField()
    location_id = serializers.UUIDField()
    batch_id = serializers.UUIDField(required=False, allow_null=True)
    serial_number_id = serializers.UUIDField(required=False, allow_null=True)
    counted_quantity = serializers.DecimalField(18, 6, required=False, allow_null=True, min_value=0)


class CycleCountLineSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    line_number = serializers.IntegerField(read_only=True)
    item_id = serializers.UUIDField(read_only=True)
    location_id = serializers.UUIDField(read_only=True)
    batch_id = serializers.UUIDField(read_only=True, allow_null=True)
    serial_number_id = serializers.UUIDField(read_only=True, allow_null=True)
    system_quantity = serializers.DecimalField(18, 6, read_only=True, allow_null=True)
    counted_quantity = serializers.DecimalField(18, 6, read_only=True, allow_null=True)
    variance_quantity = serializers.DecimalField(18, 6, read_only=True)
    counted_at = serializers.DateTimeField(read_only=True, allow_null=True)


CYCLE_COUNT_READ_FIELDS = [
    "id", "count_number", "warehouse_id", "location_id", "count_type", "scheduled_for", "status",
    "started_at", "submitted_at", "approved_at", "posted_at", "version", "transition_history",
    "created_at", "updated_at", "allowed_commands", "denial_reasons",
]


class CycleCountListSerializer(CommandAwareModelSerializer):
    class Meta:
        model = CycleCount
        fields = CYCLE_COUNT_READ_FIELDS
        read_only_fields = fields


class CycleCountDetailSerializer(CycleCountListSerializer):
    lines = CycleCountLineSerializer(many=True, read_only=True)

    class Meta(CycleCountListSerializer.Meta):
        fields = [*CYCLE_COUNT_READ_FIELDS, "lines"]


class CycleCountCreateSerializer(StrictSerializer):
    count_number = serializers.CharField(max_length=50)
    warehouse_id = serializers.UUIDField()
    location_id = serializers.UUIDField(required=False, allow_null=True)
    count_type = serializers.ChoiceField(choices=CycleCount.CountType.choices)
    scheduled_for = serializers.DateField()
    assigned_to_id = serializers.UUIDField(required=False, allow_null=True)
    lines = CycleCountLineInputSerializer(many=True, required=False)


class CycleCountUpdateSerializer(CycleCountCreateSerializer):
    count_number = serializers.CharField(max_length=50, required=False)
    warehouse_id = serializers.UUIDField(required=False)
    count_type = serializers.ChoiceField(choices=CycleCount.CountType.choices, required=False)
    scheduled_for = serializers.DateField(required=False)
    lines = CycleCountLineInputSerializer(many=True, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)


CONFIGURATION_READ_FIELDS = [
    "id", "environment", "status", "default_valuation_method", "allow_negative_stock",
    "require_stock_entry_approval", "enforce_creator_approver_separation", "max_lines_per_entry",
    "reservation_ttl_minutes", "expiry_warning_days", "auto_expire_batches", "enabled_capabilities",
    "rollout_rules", "active_revision", "version", "created_at", "updated_at", "allowed_commands",
    "denial_reasons",
]


class ConfigurationListSerializer(CommandAwareModelSerializer):
    class Meta:
        model = InventoryConfiguration
        fields = CONFIGURATION_READ_FIELDS
        read_only_fields = fields


class ConfigurationDetailSerializer(ConfigurationListSerializer):
    pass


class ConfigurationCreateSerializer(StrictSerializer):
    environment = serializers.ChoiceField(choices=InventoryConfiguration.Environment.choices)
    default_valuation_method = serializers.ChoiceField(choices=Item.ValuationMethod.choices, required=False)
    allow_negative_stock = serializers.BooleanField(required=False)
    require_stock_entry_approval = serializers.BooleanField(required=False)
    enforce_creator_approver_separation = serializers.BooleanField(required=False)
    max_lines_per_entry = serializers.IntegerField(min_value=1, max_value=5000, required=False)
    reservation_ttl_minutes = serializers.IntegerField(min_value=5, max_value=10080, required=False)
    expiry_warning_days = serializers.IntegerField(min_value=1, max_value=3650, required=False)
    auto_expire_batches = serializers.BooleanField(required=False)
    enabled_capabilities = serializers.DictField(required=False)
    rollout_rules = serializers.DictField(required=False)
    change_reason = serializers.CharField()


class ConfigurationUpdateSerializer(ConfigurationCreateSerializer):
    environment = serializers.ChoiceField(choices=InventoryConfiguration.Environment.choices, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)


class ConfigurationRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryConfigurationRevision
        fields = ["id", "configuration_id", "revision", "snapshot", "change_reason", "changed_by_id", "correlation_id", "created_at"]
        read_only_fields = fields


class EmptyCommandSerializer(StrictSerializer):
    pass


class VersionedCommandSerializer(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=1, required=False)
    transition_key = serializers.CharField(max_length=255, required=False)


class ReasonCommandSerializer(VersionedCommandSerializer):
    reason = serializers.CharField()


class ReservationConsumeSerializer(VersionedCommandSerializer):
    quantity = serializers.DecimalField(18, 6, required=False, min_value=Decimal("0.000001"))


class CycleCountRecordSerializer(VersionedCommandSerializer):
    lines = CycleCountLineInputSerializer(many=True)


class ConfigurationPreviewSerializer(StrictSerializer):
    document = serializers.DictField()


class ConfigurationActivateSerializer(StrictSerializer):
    revision = serializers.IntegerField(min_value=1)


class ConfigurationRollbackSerializer(StrictSerializer):
    revision = serializers.IntegerField(min_value=1)
    change_reason = serializers.CharField()


class ConfigurationImportSerializer(StrictSerializer):
    document = serializers.DictField()
    change_reason = serializers.CharField()


class BulkImportSerializer(StrictSerializer):
    resource_type = serializers.ChoiceField(choices=(
        "warehouses", "locations", "items", "batches", "serial_numbers",
        "stock_entries", "reservations", "cycle_counts",
    ))
    document_ref = serializers.CharField(max_length=2048)
    row_count = serializers.IntegerField(min_value=1, max_value=100000)


class InventoryJobSerializer(serializers.ModelSerializer):
    """Durable import job response; never claim acceptance without a job row."""

    class Meta:
        model = AsyncJob
        fields = [
            "id", "command", "status", "idempotency_key", "correlation_id",
            "attempts", "created_at", "updated_at",
        ]
        read_only_fields = fields


# Compatibility aliases for older imports; all are now safe read-only outputs.
WarehouseSerializer = WarehouseDetailSerializer
ItemSerializer = ItemDetailSerializer
StockEntrySerializer = StockEntryDetailSerializer


__all__ = [name for name in globals() if name.endswith("Serializer")]
