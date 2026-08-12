import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiEnvelope,
  type ApiMeta,
  type BalanceFilters,
  type Batch,
  type BatchCreate,
  type BatchFilters,
  type BatchUpdate,
  type ConfigurationActivateRequest,
  type ConfigurationExportDocument,
  type ConfigurationDiffItem,
  type ConfigurationImportRequest,
  type ConfigurationPreview,
  type ConfigurationRollbackRequest,
  type ConfigurationUpdate,
  type CycleCount,
  type CycleCountCreate,
  type CycleCountFilters,
  type CycleCountUpdate,
  type Environment,
  type InventoryCommandRequest,
  type InventoryConfiguration,
  type InventoryConfigurationRevision,
  type InventoryDashboard,
  type InventoryJob,
  type ImportRequest,
  type Item,
  type ItemCreate,
  type ItemFilters,
  type ItemUpdate,
  type LedgerFilters,
  type LocationFilters,
  type PaginatedEnvelope,
  type PaginationMeta,
  type PostPreview,
  type ReservationCreate,
  type ReservationFilters,
  type ReservationUpdate,
  type SerialFilters,
  type SerialNumber,
  type SerialNumberCreate,
  type SerialNumberUpdate,
  type StockBalance,
  type StockEntry,
  type StockEntryCreate,
  type StockEntryFilters,
  type StockEntryUpdate,
  type StockLedgerEntry,
  type StockReservation,
  type StorageLocation,
  type StorageLocationCreate,
  type StorageLocationUpdate,
  type Warehouse,
  type WarehouseCreate,
  type WarehouseFilters,
  type WarehouseUpdate,
} from "../contracts";

export interface InventoryResult<T> {
  data: T;
  correlationId: string;
  timestamp: string;
}
export interface InventoryPage<T> extends InventoryResult<T[]> {
  pagination: PaginationMeta;
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validMeta(value: unknown): value is ApiMeta {
  return (
    object(value) && typeof value.correlation_id === "string" && typeof value.timestamp === "string"
  );
}

function unwrap<T>(value: ApiEnvelope<T>): InventoryResult<T> {
  if (!object(value) || !("data" in value) || !validMeta(value.meta)) {
    throw new ApiError(
      "Inventory API returned a malformed success envelope.",
      502,
      value,
      "malformed_envelope"
    );
  }
  return {
    data: value.data,
    correlationId: value.meta.correlation_id,
    timestamp: value.meta.timestamp,
  };
}

function previewValue(value: unknown): ConfigurationDiffItem["previous"] {
  if (value === undefined || value === null) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  return JSON.stringify(value);
}

function behaviorImpact(field: string): string {
  if (
    [
      "allow_negative_stock",
      "require_stock_entry_approval",
      "max_lines_per_entry",
      "default_valuation_method",
    ].includes(field)
  ) {
    return "posting";
  }
  if (field === "reservation_ttl_minutes") return "reservations";
  if (["expiry_warning_days", "auto_expire_batches"].includes(field)) return "batch_monitoring";
  return "capability_rollout";
}

function configurationDiffItem(value: unknown): value is ConfigurationDiffItem {
  return (
    object(value) && typeof value.field === "string" && typeof value.behavior_impact === "string"
  );
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function normalizeConfigurationPreview(
  result: InventoryResult<unknown>
): InventoryResult<ConfigurationPreview> {
  const data = object(result.data) ? result.data : {};
  const rawDiff = Array.isArray(data.diff) ? data.diff.filter(configurationDiffItem) : [];
  const rawChanges = Array.isArray(data.changes) ? data.changes.filter(object) : [];
  const diff = rawDiff.length
    ? rawDiff
    : rawChanges.map((change): ConfigurationDiffItem => {
        const field = typeof change.field === "string" ? change.field : "unknown";
        return {
          field,
          previous: previewValue(change.before),
          proposed: previewValue(change.after),
          behavior_impact: behaviorImpact(field),
        };
      });
  return {
    ...result,
    data: {
      valid: data.valid === true,
      diff,
      affected_behaviors: stringArray(data.affected_behaviors),
      warnings: stringArray(data.warnings),
    },
  };
}

function unwrapPage<T>(value: PaginatedEnvelope<T>): InventoryPage<T> {
  if (
    !object(value) ||
    !Array.isArray(value.data) ||
    !validMeta(value.meta) ||
    !object(value.meta.pagination)
  ) {
    throw new ApiError(
      "Inventory API returned malformed pagination metadata.",
      502,
      value,
      "malformed_pagination"
    );
  }
  const rawPagination = value.meta.pagination as PaginationMeta & {
    count?: unknown;
    has_next?: unknown;
    has_previous?: unknown;
  };
  const totalCount = rawPagination.total_count ?? rawPagination.count;
  const next =
    rawPagination.next ?? (rawPagination.has_next === true ? String(rawPagination.page + 1) : null);
  const previous =
    rawPagination.previous ??
    (rawPagination.has_previous === true ? String(rawPagination.page - 1) : null);
  if (
    ![rawPagination.page, rawPagination.page_size, totalCount, rawPagination.total_pages].every(
      Number.isInteger
    )
  ) {
    throw new ApiError(
      "Inventory pagination counters are invalid.",
      502,
      value,
      "malformed_pagination"
    );
  }
  const pagination = {
    page: rawPagination.page,
    page_size: rawPagination.page_size,
    total_count: totalCount,
    total_pages: rawPagination.total_pages,
    next,
    previous,
  };
  return {
    data: value.data,
    correlationId: value.meta.correlation_id,
    timestamp: value.meta.timestamp,
    pagination,
  };
}

function query(filters: object): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

function versionHeaders(expectedVersion: number): RequestInit {
  return { headers: { "If-Match": String(expectedVersion) } };
}

function idempotencyHeaders(key: string): RequestInit {
  if (!key.trim()) throw new Error("An idempotency key is required.");
  return { headers: { "Idempotency-Key": key } };
}

export function createIdempotencyKey(scope: string): string {
  const random =
    globalThis.crypto && typeof globalThis.crypto.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `inventory:${scope}:${random}`;
}

async function list<T>(url: string, filters: object): Promise<InventoryPage<T>> {
  return unwrapPage(await apiClient.get<PaginatedEnvelope<T>>(`${url}${query(filters)}`));
}

async function get<T>(url: string): Promise<InventoryResult<T>> {
  return unwrap(await apiClient.get<ApiEnvelope<T>>(url));
}

async function create<T, B>(url: string, body: B, key: string): Promise<InventoryResult<T>> {
  return unwrap(await apiClient.post<ApiEnvelope<T>>(url, body, idempotencyHeaders(key)));
}

async function update<T, B>(url: string, body: B, version: number): Promise<InventoryResult<T>> {
  return unwrap(await apiClient.patch<ApiEnvelope<T>>(url, body, versionHeaders(version)));
}

async function command<T>(
  url: string,
  body: InventoryCommandRequest,
  key: string
): Promise<InventoryResult<T>> {
  return unwrap(await apiClient.post<ApiEnvelope<T>>(url, body, idempotencyHeaders(key)));
}

class InventoryQueryKeys {
  root(tenantId: string) {
    return ["inventory-management", tenantId] as const;
  }

  resource(tenantId: string, resource: string) {
    return [...this.root(tenantId), resource] as const;
  }

  list(tenantId: string, resource: string, filters: object) {
    return [...this.resource(tenantId, resource), "list", filters] as const;
  }

  detail(tenantId: string, resource: string, id: string) {
    return [...this.resource(tenantId, resource), "detail", id] as const;
  }

  dashboard(tenantId: string) {
    return [...this.root(tenantId), "dashboard"] as const;
  }
}

class InventoryService {
  listWarehouses(filters: WarehouseFilters = {}) {
    return list<Warehouse>(ENDPOINTS.WAREHOUSES.LIST, filters);
  }

  getWarehouse(id: string) {
    return get<Warehouse>(ENDPOINTS.WAREHOUSES.DETAIL(id));
  }

  createWarehouse(body: WarehouseCreate, key: string) {
    return create<Warehouse, WarehouseCreate>(ENDPOINTS.WAREHOUSES.CREATE, body, key);
  }

  updateWarehouse(id: string, body: WarehouseUpdate, expectedVersion: number) {
    return update<Warehouse, WarehouseUpdate>(
      ENDPOINTS.WAREHOUSES.UPDATE(id),
      body,
      expectedVersion
    );
  }

  async archiveWarehouse(id: string, expectedVersion: number) {
    return unwrap(
      await apiClient.delete<ApiEnvelope<Warehouse>>(
        ENDPOINTS.WAREHOUSES.ARCHIVE(id),
        versionHeaders(expectedVersion)
      )
    );
  }

  setDefaultWarehouse(id: string, key: string) {
    return command<Warehouse>(ENDPOINTS.WAREHOUSES.SET_DEFAULT(id), { transition_key: key }, key);
  }

  listLocations(filters: LocationFilters = {}) {
    return list<StorageLocation>(ENDPOINTS.LOCATIONS.LIST, filters);
  }

  getLocation(id: string) {
    return get<StorageLocation>(ENDPOINTS.LOCATIONS.DETAIL(id));
  }

  createLocation(body: StorageLocationCreate, key: string) {
    return create<StorageLocation, StorageLocationCreate>(ENDPOINTS.LOCATIONS.CREATE, body, key);
  }

  updateLocation(id: string, body: StorageLocationUpdate, expectedVersion: number) {
    return update<StorageLocation, StorageLocationUpdate>(
      ENDPOINTS.LOCATIONS.UPDATE(id),
      body,
      expectedVersion
    );
  }

  async archiveLocation(id: string, expectedVersion: number) {
    return unwrap(
      await apiClient.delete<ApiEnvelope<StorageLocation>>(
        ENDPOINTS.LOCATIONS.ARCHIVE(id),
        versionHeaders(expectedVersion)
      )
    );
  }

  listItems(filters: ItemFilters = {}) {
    return list<Item>(ENDPOINTS.ITEMS.LIST, filters);
  }

  getItem(id: string) {
    return get<Item>(ENDPOINTS.ITEMS.DETAIL(id));
  }

  createItem(body: ItemCreate, key: string) {
    return create<Item, ItemCreate>(ENDPOINTS.ITEMS.CREATE, body, key);
  }

  updateItem(id: string, body: ItemUpdate, expectedVersion: number) {
    return update<Item, ItemUpdate>(ENDPOINTS.ITEMS.UPDATE(id), body, expectedVersion);
  }

  async archiveItem(id: string, expectedVersion: number) {
    return unwrap(
      await apiClient.delete<ApiEnvelope<Item>>(
        ENDPOINTS.ITEMS.ARCHIVE(id),
        versionHeaders(expectedVersion)
      )
    );
  }

  listBatches(filters: BatchFilters = {}) {
    return list<Batch>(ENDPOINTS.BATCHES.LIST, filters);
  }

  getBatch(id: string) {
    return get<Batch>(ENDPOINTS.BATCHES.DETAIL(id));
  }

  createBatch(body: BatchCreate, key: string) {
    return create<Batch, BatchCreate>(ENDPOINTS.BATCHES.CREATE, body, key);
  }

  updateBatch(id: string, body: BatchUpdate, expectedVersion: number) {
    return update<Batch, BatchUpdate>(ENDPOINTS.BATCHES.UPDATE(id), body, expectedVersion);
  }

  commandBatch(
    id: string,
    name: "activate" | "quarantine" | "release" | "recall",
    body: InventoryCommandRequest,
    key: string
  ) {
    return command<Batch>(ENDPOINTS.BATCHES.COMMAND(id, name), body, key);
  }

  traceBatch(id: string) {
    return get<StockLedgerEntry[]>(ENDPOINTS.BATCHES.TRACE(id));
  }

  listSerials(filters: SerialFilters = {}) {
    return list<SerialNumber>(ENDPOINTS.SERIALS.LIST, filters);
  }

  getSerial(id: string) {
    return get<SerialNumber>(ENDPOINTS.SERIALS.DETAIL(id));
  }

  createSerial(body: SerialNumberCreate, key: string) {
    return create<SerialNumber, SerialNumberCreate>(ENDPOINTS.SERIALS.CREATE, body, key);
  }

  updateSerial(id: string, body: SerialNumberUpdate, expectedVersion: number) {
    return update<SerialNumber, SerialNumberUpdate>(
      ENDPOINTS.SERIALS.UPDATE(id),
      body,
      expectedVersion
    );
  }

  traceSerial(id: string) {
    return get<StockLedgerEntry[]>(ENDPOINTS.SERIALS.TRACE(id));
  }

  listStockEntries(filters: StockEntryFilters = {}) {
    return list<StockEntry>(ENDPOINTS.STOCK_ENTRIES.LIST, filters);
  }

  getStockEntry(id: string) {
    return get<StockEntry>(ENDPOINTS.STOCK_ENTRIES.DETAIL(id));
  }

  createStockEntry(body: StockEntryCreate, key: string) {
    return create<StockEntry, StockEntryCreate>(ENDPOINTS.STOCK_ENTRIES.CREATE, body, key);
  }

  updateStockEntry(id: string, body: StockEntryUpdate, expectedVersion: number) {
    return update<StockEntry, StockEntryUpdate>(
      ENDPOINTS.STOCK_ENTRIES.UPDATE(id),
      body,
      expectedVersion
    );
  }

  async deleteStockEntryDraft(id: string, expectedVersion: number) {
    return unwrap(
      await apiClient.delete<ApiEnvelope<StockEntry>>(
        ENDPOINTS.STOCK_ENTRIES.DELETE_DRAFT(id),
        versionHeaders(expectedVersion)
      )
    );
  }

  commandStockEntry(
    id: string,
    name: "submit" | "approve" | "reject" | "post" | "cancel" | "reverse",
    body: InventoryCommandRequest,
    key: string
  ) {
    return command<StockEntry>(ENDPOINTS.STOCK_ENTRIES.COMMAND(id, name), body, key);
  }

  previewStockEntry(id: string) {
    return get<PostPreview>(ENDPOINTS.STOCK_ENTRIES.PREVIEW(id));
  }

  listBalances(filters: BalanceFilters = {}) {
    return list<StockBalance>(ENDPOINTS.STOCK_BALANCES.LIST, filters);
  }

  getBalance(id: string) {
    return get<StockBalance>(ENDPOINTS.STOCK_BALANCES.DETAIL(id));
  }

  listLedger(filters: LedgerFilters = {}) {
    return list<StockLedgerEntry>(ENDPOINTS.STOCK_LEDGER.LIST, filters);
  }

  getLedgerEntry(id: string) {
    return get<StockLedgerEntry>(ENDPOINTS.STOCK_LEDGER.DETAIL(id));
  }

  listReservations(filters: ReservationFilters = {}) {
    return list<StockReservation>(ENDPOINTS.RESERVATIONS.LIST, filters);
  }

  getReservation(id: string) {
    return get<StockReservation>(ENDPOINTS.RESERVATIONS.DETAIL(id));
  }

  createReservation(body: ReservationCreate, key: string) {
    return create<StockReservation, ReservationCreate>(ENDPOINTS.RESERVATIONS.CREATE, body, key);
  }

  updateReservation(id: string, body: ReservationUpdate, expectedVersion: number) {
    return update<StockReservation, ReservationUpdate>(
      ENDPOINTS.RESERVATIONS.UPDATE(id),
      body,
      expectedVersion
    );
  }

  commandReservation(
    id: string,
    name: "release" | "consume" | "cancel",
    body: InventoryCommandRequest,
    key: string
  ) {
    return command<StockReservation>(ENDPOINTS.RESERVATIONS.COMMAND(id, name), body, key);
  }

  listCycleCounts(filters: CycleCountFilters = {}) {
    return list<CycleCount>(ENDPOINTS.CYCLE_COUNTS.LIST, filters);
  }

  getCycleCount(id: string) {
    return get<CycleCount>(ENDPOINTS.CYCLE_COUNTS.DETAIL(id));
  }

  createCycleCount(body: CycleCountCreate, key: string) {
    return create<CycleCount, CycleCountCreate>(ENDPOINTS.CYCLE_COUNTS.CREATE, body, key);
  }

  updateCycleCount(id: string, body: CycleCountUpdate, expectedVersion: number) {
    return update<CycleCount, CycleCountUpdate>(
      ENDPOINTS.CYCLE_COUNTS.UPDATE(id),
      body,
      expectedVersion
    );
  }

  commandCycleCount(
    id: string,
    name: "start" | "submit" | "approve" | "reject" | "post" | "cancel",
    body: InventoryCommandRequest,
    key: string
  ) {
    return command<CycleCount>(ENDPOINTS.CYCLE_COUNTS.COMMAND(id, name), body, key);
  }

  listConfigurations() {
    return list<InventoryConfiguration>(ENDPOINTS.CONFIGURATIONS.LIST, {});
  }

  getConfiguration(environment: Environment) {
    return get<InventoryConfiguration>(ENDPOINTS.CONFIGURATIONS.DETAIL(environment));
  }

  createConfigurationRevision(
    environment: Environment,
    body: ConfigurationUpdate,
    expectedVersion: number
  ) {
    return update<InventoryConfiguration, ConfigurationUpdate>(
      ENDPOINTS.CONFIGURATIONS.UPDATE(environment),
      body,
      expectedVersion
    );
  }

  async previewConfiguration(environment: Environment, body: ConfigurationUpdate) {
    const document = { ...body };
    delete (document as Partial<ConfigurationUpdate>).change_reason;
    return normalizeConfigurationPreview(
      unwrap(
        await apiClient.post<ApiEnvelope<unknown>>(ENDPOINTS.CONFIGURATIONS.PREVIEW(environment), {
          document,
        })
      )
    );
  }

  activateConfiguration(environment: Environment, body: ConfigurationActivateRequest, key: string) {
    return create<InventoryConfiguration, ConfigurationActivateRequest>(
      ENDPOINTS.CONFIGURATIONS.ACTIVATE(environment),
      body,
      key
    );
  }

  rollbackConfiguration(environment: Environment, body: ConfigurationRollbackRequest, key: string) {
    return create<InventoryConfiguration, ConfigurationRollbackRequest>(
      ENDPOINTS.CONFIGURATIONS.ROLLBACK(environment),
      body,
      key
    );
  }

  importConfiguration(environment: Environment, body: ConfigurationImportRequest, key: string) {
    return create<InventoryConfiguration, ConfigurationImportRequest>(
      ENDPOINTS.CONFIGURATIONS.IMPORT(environment),
      body,
      key
    );
  }

  exportConfiguration(environment: Environment) {
    return get<ConfigurationExportDocument>(ENDPOINTS.CONFIGURATIONS.EXPORT(environment));
  }

  configurationHistory(environment: Environment) {
    return list<InventoryConfigurationRevision>(ENDPOINTS.CONFIGURATIONS.HISTORY(environment), {});
  }

  dashboard() {
    return get<InventoryDashboard>(ENDPOINTS.DASHBOARD);
  }

  enqueueImport(body: ImportRequest, key: string) {
    return create<InventoryJob, ImportRequest>(ENDPOINTS.IMPORTS, body, key);
  }

  health() {
    return get<{ status: "healthy" | "degraded" | "unhealthy" }>(ENDPOINTS.HEALTH);
  }
}

export const inventoryQueryKeys = new InventoryQueryKeys();
export const inventoryService = new InventoryService();
