/** Closed, versioned frontend contract for the governed Inventory API. */
export interface PaginationMeta { page: number; page_size: number; total_count: number; total_pages: number; next: string | null; previous: string | null }
export interface ApiMeta { correlation_id: string; timestamp: string; pagination?: PaginationMeta }
export interface ApiEnvelope<T> { data: T; meta: ApiMeta }
export interface PaginatedEnvelope<T> { data: T[]; meta: ApiMeta & { pagination: PaginationMeta } }

export type WarehouseType = "distribution_center" | "retail_store" | "manufacturing_plant" | "warehouse_3pl" | "transit" | "consignment";
export type ZoneType = "receiving" | "storage" | "picking" | "packing" | "shipping" | "quarantine" | "returns" | "transit";
export type LocationType = "bin" | "shelf" | "rack" | "pallet" | "floor" | "dock";
export type TrackingMode = "none" | "batch" | "serial";
export type ValuationMethod = "fifo" | "lifo" | "weighted_average" | "standard_cost";
export type BatchStatus = "planned" | "active" | "quarantined" | "recalled" | "exhausted" | "expired";
export type SerialStatus = "registered" | "in_stock" | "reserved" | "in_transit" | "sold" | "in_service" | "scrapped";
export type StockEntryType = "receipt" | "issue" | "transfer" | "adjustment" | "manufacturing" | "return" | "scrap";
export type StockEntryStatus = "draft" | "submitted" | "approved" | "posted" | "rejected" | "cancelled" | "reversed";
export type ReservationStatus = "active" | "released" | "consumed" | "expired" | "cancelled";
export type CycleCountType = "full" | "abc" | "random" | "location" | "item_specific";
export type CycleCountStatus = "scheduled" | "in_progress" | "submitted" | "approved" | "posted" | "cancelled";
export type Environment = "development" | "staging" | "production";
export type ConfigurationStatus = "draft" | "active" | "superseded";

export interface AllowedCommand { name: string; label: string; requires_confirmation: boolean; destructive: boolean }
export interface DenialReason { command: string; code: string; message: string }
export interface FieldError { field: string; code: string; message: string }
export interface InventoryProblem { code: string; message: string; detail?: string; correlation_id: string; field_errors?: FieldError[]; retryable?: boolean }
export interface InventoryJob { id: string; status: "queued" | "running" | "succeeded" | "failed" | "cancelled"; resource_type: string; idempotency_key: string; created_at: string; completed_at: string | null; problem: InventoryProblem | null }
export interface ResourceGovernance { allowed_commands: AllowedCommand[]; denial_reasons: DenialReason[] }
export interface AuditedResource { id: string; version: number; created_at: string; updated_at: string }
export interface NamedSummary { id: string; code: string; name: string }

export interface Warehouse extends AuditedResource, ResourceGovernance { warehouse_code: string; warehouse_name: string; warehouse_type: WarehouseType; address_line1: string; address_line2: string; city: string; state_region: string; postal_code: string; country_code: string; timezone: string; contact_name: string; contact_email: string; contact_phone: string; is_default: boolean; is_active: boolean; archived_at: string | null }
export interface WarehouseCreate { warehouse_code: string; warehouse_name: string; warehouse_type: WarehouseType; address_line1?: string; address_line2?: string; city?: string; state_region?: string; postal_code?: string; country_code: string; timezone: string; contact_name?: string; contact_email?: string; contact_phone?: string; is_default?: boolean; is_active?: boolean }
export type WarehouseUpdate = Partial<WarehouseCreate>;

export interface StorageLocation extends AuditedResource, ResourceGovernance { warehouse: NamedSummary; parent: NamedSummary | null; location_code: string; location_name: string; zone_type: ZoneType; location_type: LocationType; barcode: string; pick_sequence: number; capacity_units: string | null; capacity_weight_kg: string | null; capacity_volume_cbm: string | null; temperature_controlled: boolean; hazmat_approved: boolean; is_default: boolean; is_active: boolean; archived_at: string | null }
export interface StorageLocationCreate { warehouse_id: string; parent_id?: string | null; location_code: string; location_name: string; zone_type: ZoneType; location_type: LocationType; barcode?: string; pick_sequence?: number; capacity_units?: string | null; capacity_weight_kg?: string | null; capacity_volume_cbm?: string | null; temperature_controlled?: boolean; hazmat_approved?: boolean; is_default?: boolean; is_active?: boolean }
export type StorageLocationUpdate = Partial<Omit<StorageLocationCreate, "warehouse_id">>;

export interface Item extends AuditedResource, ResourceGovernance { item_code: string; item_name: string; description: string; category: string; brand: string; barcode: string; base_uom: string; tracking_mode: TrackingMode; tracks_expiry: boolean; valuation_method: ValuationMethod; standard_cost: string | null; reorder_point: string | null; reorder_quantity: string | null; safety_stock: string | null; default_warehouse: NamedSummary | null; abc_classification: "A" | "B" | "C" | ""; is_active: boolean; archived_at: string | null }
export interface ItemCreate { item_code: string; item_name: string; description?: string; category?: string; brand?: string; barcode?: string; base_uom: string; tracking_mode: TrackingMode; tracks_expiry?: boolean; valuation_method: ValuationMethod; standard_cost?: string | null; reorder_point?: string | null; reorder_quantity?: string | null; safety_stock?: string | null; default_warehouse_id?: string | null; abc_classification?: "A" | "B" | "C" | ""; is_active?: boolean }
export type ItemUpdate = Partial<ItemCreate>;

export interface Batch extends AuditedResource, ResourceGovernance { item: NamedSummary; batch_number: string; supplier_batch_number: string; manufactured_on: string | null; expires_on: string | null; status: BatchStatus; transition_history: TransitionRecord[] }
export interface BatchCreate { item_id: string; batch_number: string; supplier_batch_number?: string; manufactured_on?: string | null; expires_on?: string | null }
export interface BatchUpdate { supplier_batch_number?: string; manufactured_on?: string | null; expires_on?: string | null }
export interface SerialNumber extends AuditedResource, ResourceGovernance { item: NamedSummary; serial_number: string; status: SerialStatus; current_warehouse: NamedSummary | null; current_location: NamedSummary | null; manufacturer: string; model_number: string; warranty_starts_on: string | null; warranty_ends_on: string | null; transition_history: TransitionRecord[] }
export interface SerialNumberCreate { item_id: string; serial_number: string; manufacturer?: string; model_number?: string; warranty_starts_on?: string | null; warranty_ends_on?: string | null }
export interface SerialNumberUpdate { manufacturer?: string; model_number?: string; warranty_starts_on?: string | null; warranty_ends_on?: string | null }
export interface TransitionRecord { command: string; from: string; to: string; actor_id: string; occurred_at: string; transition_key: string }

export interface StockEntryLine { id?: string; line_number: number; item: NamedSummary; source_location: NamedSummary | null; destination_location: NamedSummary | null; batch: NamedSummary | null; serial_number: NamedSummary | null; quantity: string; uom: string; unit_cost: string | null; line_value: string; notes: string }
export interface StockEntryLineWrite { line_number: number; item_id: string; source_location_id?: string | null; destination_location_id?: string | null; batch_id?: string | null; serial_number_id?: string | null; quantity: string; uom: string; unit_cost?: string | null; notes?: string }
export interface StockEntry extends AuditedResource, ResourceGovernance { entry_number: string; entry_type: StockEntryType; posting_at: string; source_warehouse: NamedSummary | null; destination_warehouse: NamedSummary | null; reference_module: string; reference_type: string; reference_id: string | null; reason: string; status: StockEntryStatus; created_by_id: string | null; approved_by_id: string | null; posted_by_id: string | null; approved_at: string | null; posted_at: string | null; reversed_at: string | null; reversal_of_id: string | null; lines: StockEntryLine[]; transition_history: TransitionRecord[] }
export interface StockEntryCreate { entry_number: string; entry_type: StockEntryType; posting_at: string; source_warehouse_id?: string | null; destination_warehouse_id?: string | null; reference_module?: string; reference_type?: string; reference_id?: string | null; reason?: string; lines: StockEntryLineWrite[] }
export type StockEntryUpdate = Partial<Omit<StockEntryCreate, "entry_number">>;

export interface StockLedgerEntry { id: string; sequence: number; stock_entry_id: string; stock_entry_line_id: string; item: NamedSummary; warehouse: NamedSummary; location: NamedSummary; batch: NamedSummary | null; serial_number: NamedSummary | null; quantity_delta: string; quantity_after: string; unit_cost: string; value_delta: string; value_after: string; posted_at: string; correlation_id: string; created_at: string }
export interface StockBalance { id: string; item: NamedSummary; warehouse: NamedSummary; location: NamedSummary; batch: NamedSummary | null; serial_number: NamedSummary | null; quantity_on_hand: string; quantity_allocated: string; quantity_available: string; stock_value: string; valuation_rate: string; last_ledger_entry_id: string | null; created_at: string; updated_at: string }

export interface StockReservation extends AuditedResource, ResourceGovernance { reservation_number: string; reference_module: string; reference_type: string; reference_id: string; item: NamedSummary; warehouse: NamedSummary; location: NamedSummary | null; batch: NamedSummary | null; serial_number: NamedSummary | null; quantity: string; status: ReservationStatus; expires_at: string | null; transition_history: TransitionRecord[] }
export interface ReservationCreate { reservation_number: string; reference_module: string; reference_type: string; reference_id: string; item_id: string; warehouse_id: string; location_id?: string | null; batch_id?: string | null; serial_number_id?: string | null; quantity: string; expires_at?: string | null }
export interface ReservationUpdate { quantity?: string; expires_at?: string | null }

export interface CycleCountLine { id?: string; line_number: number; item: NamedSummary; location: NamedSummary; batch: NamedSummary | null; serial_number: NamedSummary | null; system_quantity: string | null; counted_quantity: string | null; variance_quantity: string; counted_by_id: string | null; counted_at: string | null }
export interface CycleCountLineWrite { line_number: number; item_id: string; location_id: string; batch_id?: string | null; serial_number_id?: string | null; counted_quantity?: string | null }
export interface CycleCount extends AuditedResource, ResourceGovernance { count_number: string; warehouse: NamedSummary; location: NamedSummary | null; count_type: CycleCountType; scheduled_for: string; assigned_to_id: string | null; status: CycleCountStatus; started_at: string | null; submitted_at: string | null; approved_at: string | null; posted_at: string | null; lines: CycleCountLine[]; transition_history: TransitionRecord[] }
export interface CycleCountCreate { count_number: string; warehouse_id: string; location_id?: string | null; count_type: CycleCountType; scheduled_for: string; assigned_to_id?: string | null; lines?: CycleCountLineWrite[] }
export type CycleCountUpdate = Partial<Omit<CycleCountCreate, "count_number" | "warehouse_id">>;

export interface EnabledCapabilities { barcode_scanning: boolean; bulk_import: boolean; batch_tracking: boolean; serial_tracking: boolean; cycle_counting: boolean }
export interface RolloutRules { enabled: boolean; percentage: number; tenant_cohort: string; allowed_role_ids: string[] }
export interface InventoryConfiguration extends AuditedResource, ResourceGovernance { environment: Environment; status: ConfigurationStatus; default_valuation_method: ValuationMethod; allow_negative_stock: boolean; require_stock_entry_approval: boolean; enforce_creator_approver_separation: boolean; max_lines_per_entry: number; reservation_ttl_minutes: number; expiry_warning_days: number; auto_expire_batches: boolean; enabled_capabilities: EnabledCapabilities; rollout_rules: RolloutRules; active_revision: number }
export interface ConfigurationUpdate { default_valuation_method: ValuationMethod; allow_negative_stock: boolean; require_stock_entry_approval: boolean; enforce_creator_approver_separation: boolean; max_lines_per_entry: number; reservation_ttl_minutes: number; expiry_warning_days: number; auto_expire_batches: boolean; enabled_capabilities: EnabledCapabilities; rollout_rules: RolloutRules; change_reason: string }
export interface InventoryConfigurationRevision { id: string; revision: number; snapshot: ConfigurationUpdate; change_reason: string; changed_by_id: string; correlation_id: string; created_at: string }
export interface ConfigurationDiffItem { field: string; previous: string | number | boolean | null; proposed: string | number | boolean | null; behavior_impact: string }
export interface ConfigurationPreview { valid: boolean; diff: ConfigurationDiffItem[]; affected_behaviors: string[]; warnings: string[] }
export interface ConfigurationExportDocument { schema_version: "1.0"; environment: Environment; exported_at: string; checksum: string; configuration: ConfigurationUpdate }
export interface ConfigurationImportRequest { document: ConfigurationExportDocument; change_reason: string }
export interface ConfigurationRollbackRequest { revision: number; change_reason: string }
export interface ConfigurationActivateRequest { revision: number; change_reason: string }

export interface DashboardMetric { label: string; value: string; trend: string | null }
export interface DashboardAlert { id: string; severity: "info" | "warning" | "critical"; title: string; detail: string; resource_url: string }
export interface InventoryDashboard { metrics: DashboardMetric[]; alerts: DashboardAlert[]; recent_entries: StockEntry[]; low_stock_items: StockBalance[]; onboarding: { warehouse_created: boolean; item_created: boolean; first_receipt_posted: boolean; first_issue_posted: boolean } }

export interface PageFilter { page?: number; page_size?: number; ordering?: string; search?: string }
export interface WarehouseFilters extends PageFilter { warehouse_type?: WarehouseType; is_active?: boolean; is_default?: boolean }
export interface LocationFilters extends PageFilter { warehouse_id?: string; zone_type?: ZoneType; location_type?: LocationType; is_active?: boolean; barcode?: string }
export interface ItemFilters extends PageFilter { category?: string; tracking_mode?: TrackingMode; valuation_method?: ValuationMethod; is_active?: boolean; below_reorder?: boolean }
export interface BatchFilters extends PageFilter { item_id?: string; status?: BatchStatus; expires_before?: string; expires_after?: string }
export interface SerialFilters extends PageFilter { item_id?: string; status?: SerialStatus; warehouse_id?: string; location_id?: string }
export interface StockEntryFilters extends PageFilter { entry_type?: StockEntryType; status?: StockEntryStatus; from?: string; to?: string; warehouse_id?: string; reference_id?: string }
export interface BalanceFilters extends PageFilter { item_id?: string; warehouse_id?: string; location_id?: string; batch_id?: string; serial_id?: string; nonzero?: boolean; below_reorder?: boolean }
export interface LedgerFilters extends PageFilter { item_id?: string; warehouse_id?: string; location_id?: string; batch_id?: string; serial_id?: string; from?: string; to?: string; entry_id?: string }
export interface ReservationFilters extends PageFilter { status?: ReservationStatus; item_id?: string; reference_id?: string; expires_before?: string }
export interface CycleCountFilters extends PageFilter { warehouse_id?: string; location_id?: string; status?: CycleCountStatus; scheduled_from?: string; scheduled_to?: string; assigned_to_id?: string }
export interface InventoryCommandRequest { transition_key: string; reason?: string; expected_version?: number }
export interface PostPreview { movements: { item_code: string; location_code: string; quantity_delta: string; value_delta: string }[]; warnings: string[] }
export interface ImportRequest { resource_type: "warehouses" | "locations" | "items" | "batches" | "serial_numbers" | "stock_entries" | "reservations" | "cycle_counts"; document_ref: string; row_count: number }

export const MODULE_API_PREFIX = "/api/v2/inventory-management";
const collection = (name: string) => `${MODULE_API_PREFIX}/${name}/` as const;
const detail = (name: string, id: string) => `${collection(name)}${encodeURIComponent(id)}/` as const;
const action = (name: string, id: string, command: string) => `${detail(name, id)}${command}/` as const;
export const ENDPOINTS = {
  WAREHOUSES: { LIST: collection("warehouses"), CREATE: collection("warehouses"), DETAIL: (id: string) => detail("warehouses", id), UPDATE: (id: string) => detail("warehouses", id), ARCHIVE: (id: string) => detail("warehouses", id), SET_DEFAULT: (id: string) => action("warehouses", id, "set-default") },
  LOCATIONS: { LIST: collection("locations"), CREATE: collection("locations"), DETAIL: (id: string) => detail("locations", id), UPDATE: (id: string) => detail("locations", id), ARCHIVE: (id: string) => detail("locations", id) },
  ITEMS: { LIST: collection("items"), CREATE: collection("items"), DETAIL: (id: string) => detail("items", id), UPDATE: (id: string) => detail("items", id), ARCHIVE: (id: string) => detail("items", id) },
  BATCHES: { LIST: collection("batches"), CREATE: collection("batches"), DETAIL: (id: string) => detail("batches", id), UPDATE: (id: string) => detail("batches", id), COMMAND: (id: string, command: "activate" | "quarantine" | "release" | "recall") => action("batches", id, command), TRACE: (id: string) => action("batches", id, "trace") },
  SERIALS: { LIST: collection("serial-numbers"), CREATE: collection("serial-numbers"), DETAIL: (id: string) => detail("serial-numbers", id), UPDATE: (id: string) => detail("serial-numbers", id), TRACE: (id: string) => action("serial-numbers", id, "trace") },
  STOCK_ENTRIES: { LIST: collection("stock-entries"), CREATE: collection("stock-entries"), DETAIL: (id: string) => detail("stock-entries", id), UPDATE: (id: string) => detail("stock-entries", id), DELETE_DRAFT: (id: string) => detail("stock-entries", id), COMMAND: (id: string, command: "submit" | "approve" | "reject" | "post" | "cancel" | "reverse") => action("stock-entries", id, command), PREVIEW: (id: string) => action("stock-entries", id, "preview") },
  STOCK_BALANCES: { LIST: collection("stock-balances"), DETAIL: (id: string) => detail("stock-balances", id) },
  STOCK_LEDGER: { LIST: collection("stock-ledger"), DETAIL: (id: string) => detail("stock-ledger", id) },
  RESERVATIONS: { LIST: collection("reservations"), CREATE: collection("reservations"), DETAIL: (id: string) => detail("reservations", id), UPDATE: (id: string) => detail("reservations", id), COMMAND: (id: string, command: "release" | "consume" | "cancel") => action("reservations", id, command) },
  CYCLE_COUNTS: { LIST: collection("cycle-counts"), CREATE: collection("cycle-counts"), DETAIL: (id: string) => detail("cycle-counts", id), UPDATE: (id: string) => detail("cycle-counts", id), COMMAND: (id: string, command: "start" | "submit" | "approve" | "reject" | "post" | "cancel") => action("cycle-counts", id, command) },
  CONFIGURATIONS: { LIST: collection("configurations"), DETAIL: (environment: Environment) => detail("configurations", environment), UPDATE: (environment: Environment) => detail("configurations", environment), PREVIEW: (environment: Environment) => action("configurations", environment, "preview"), ACTIVATE: (environment: Environment) => action("configurations", environment, "activate"), ROLLBACK: (environment: Environment) => action("configurations", environment, "rollback"), IMPORT: (environment: Environment) => action("configurations", environment, "import"), EXPORT: (environment: Environment) => action("configurations", environment, "export"), HISTORY: (environment: Environment) => action("configurations", environment, "history") },
  DASHBOARD: collection("dashboard"), IMPORTS: collection("imports"), HEALTH: collection("health"),
} as const;

export const ROUTES = {
  DASHBOARD: "/inventory-management", WAREHOUSES: "/inventory-management/warehouses", WAREHOUSE_NEW: "/inventory-management/warehouses/new", WAREHOUSE_DETAIL: "/inventory-management/warehouses/:id", WAREHOUSE_EDIT: "/inventory-management/warehouses/:id/edit",
  LOCATIONS: "/inventory-management/locations", LOCATION_NEW: "/inventory-management/locations/new", LOCATION_DETAIL: "/inventory-management/locations/:id", LOCATION_EDIT: "/inventory-management/locations/:id/edit",
  ITEMS: "/inventory-management/items", ITEM_NEW: "/inventory-management/items/new", ITEM_DETAIL: "/inventory-management/items/:id", ITEM_EDIT: "/inventory-management/items/:id/edit",
  BATCHES: "/inventory-management/batches", BATCH_NEW: "/inventory-management/batches/new", BATCH_DETAIL: "/inventory-management/batches/:id", BATCH_EDIT: "/inventory-management/batches/:id/edit", BATCH_TRACE: "/inventory-management/batches/:id/trace",
  SERIALS: "/inventory-management/serial-numbers", SERIAL_NEW: "/inventory-management/serial-numbers/new", SERIAL_DETAIL: "/inventory-management/serial-numbers/:id", SERIAL_EDIT: "/inventory-management/serial-numbers/:id/edit", SERIAL_TRACE: "/inventory-management/serial-numbers/:id/trace",
  STOCK_ENTRIES: "/inventory-management/stock-entries", STOCK_ENTRY_NEW: "/inventory-management/stock-entries/new", STOCK_ENTRY_DETAIL: "/inventory-management/stock-entries/:id", STOCK_ENTRY_EDIT: "/inventory-management/stock-entries/:id/edit",
  STOCK_BALANCES: "/inventory-management/stock-balances", STOCK_BALANCE_DETAIL: "/inventory-management/stock-balances/:id", STOCK_LEDGER: "/inventory-management/stock-ledger", STOCK_LEDGER_DETAIL: "/inventory-management/stock-ledger/:id",
  RESERVATIONS: "/inventory-management/reservations", RESERVATION_NEW: "/inventory-management/reservations/new", RESERVATION_DETAIL: "/inventory-management/reservations/:id", RESERVATION_EDIT: "/inventory-management/reservations/:id/edit",
  CYCLE_COUNTS: "/inventory-management/cycle-counts", CYCLE_COUNT_NEW: "/inventory-management/cycle-counts/new", CYCLE_COUNT_DETAIL: "/inventory-management/cycle-counts/:id", CYCLE_COUNT_EDIT: "/inventory-management/cycle-counts/:id/edit",
  IMPORT: "/inventory-management/import",
  SETTINGS: "/inventory-management/settings", CONFIGURATION_DETAIL: "/inventory-management/settings/:environment", CONFIGURATION_EDIT: "/inventory-management/settings/:environment/edit", CONFIGURATION_HISTORY: "/inventory-management/settings/:environment/history", CONFIGURATION_PREVIEW: "/inventory-management/settings/:environment/preview", CONFIGURATION_IMPORT: "/inventory-management/settings/:environment/import", CONFIGURATION_EXPORT: "/inventory-management/settings/:environment/export", CONFIGURATION_ROLLBACK: "/inventory-management/settings/:environment/rollback",
} as const;
