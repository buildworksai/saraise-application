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

export interface InventoryResult<T> { data: T; correlationId: string; timestamp: string }
export interface InventoryPage<T> extends InventoryResult<T[]> { pagination: PaginationMeta }

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validMeta(value: unknown): value is ApiMeta {
  return object(value) && typeof value.correlation_id === "string" && typeof value.timestamp === "string";
}

function unwrap<T>(value: ApiEnvelope<T>): InventoryResult<T> {
  if (!object(value) || !("data" in value) || !validMeta(value.meta)) {
    throw new ApiError("Inventory API returned a malformed success envelope.", 502, value, "malformed_envelope");
  }
  return { data: value.data, correlationId: value.meta.correlation_id, timestamp: value.meta.timestamp };
}

function unwrapPage<T>(value: PaginatedEnvelope<T>): InventoryPage<T> {
  if (!object(value) || !Array.isArray(value.data) || !validMeta(value.meta) || !object(value.meta.pagination)) {
    throw new ApiError("Inventory API returned malformed pagination metadata.", 502, value, "malformed_pagination");
  }
  const pagination = value.meta.pagination;
  if (![pagination.page, pagination.page_size, pagination.total_count, pagination.total_pages].every(Number.isInteger)) {
    throw new ApiError("Inventory pagination counters are invalid.", 502, value, "malformed_pagination");
  }
  return { data: value.data, correlationId: value.meta.correlation_id, timestamp: value.meta.timestamp, pagination };
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
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `inventory:${scope}:${random}`;
}

const list = async <T>(url: string, filters: object): Promise<InventoryPage<T>> =>
  unwrapPage(await apiClient.get<PaginatedEnvelope<T>>(`${url}${query(filters)}`));
const get = async <T>(url: string): Promise<InventoryResult<T>> => unwrap(await apiClient.get<ApiEnvelope<T>>(url));
const create = async <T, B>(url: string, body: B, key: string): Promise<InventoryResult<T>> => unwrap(await apiClient.post<ApiEnvelope<T>>(url, body, idempotencyHeaders(key)));
const update = async <T, B>(url: string, body: B, version: number): Promise<InventoryResult<T>> => unwrap(await apiClient.patch<ApiEnvelope<T>>(url, body, versionHeaders(version)));
const command = async <T>(url: string, body: InventoryCommandRequest, key: string): Promise<InventoryResult<T>> => unwrap(await apiClient.post<ApiEnvelope<T>>(url, body, idempotencyHeaders(key)));

export const inventoryQueryKeys = {
  root: (tenantId: string) => ["inventory-management", tenantId] as const,
  resource: (tenantId: string, resource: string) => [...inventoryQueryKeys.root(tenantId), resource] as const,
  list: (tenantId: string, resource: string, filters: object) => [...inventoryQueryKeys.resource(tenantId, resource), "list", filters] as const,
  detail: (tenantId: string, resource: string, id: string) => [...inventoryQueryKeys.resource(tenantId, resource), "detail", id] as const,
  dashboard: (tenantId: string) => [...inventoryQueryKeys.root(tenantId), "dashboard"] as const,
};

export const inventoryService = {
  listWarehouses: (filters: WarehouseFilters = {}) => list<Warehouse>(ENDPOINTS.WAREHOUSES.LIST, filters),
  getWarehouse: (id: string) => get<Warehouse>(ENDPOINTS.WAREHOUSES.DETAIL(id)),
  createWarehouse: (body: WarehouseCreate, key: string) => create<Warehouse, WarehouseCreate>(ENDPOINTS.WAREHOUSES.CREATE, body, key),
  updateWarehouse: (id: string, body: WarehouseUpdate, expectedVersion: number) => update<Warehouse, WarehouseUpdate>(ENDPOINTS.WAREHOUSES.UPDATE(id), body, expectedVersion),
  archiveWarehouse: async (id: string, expectedVersion: number) => unwrap(await apiClient.delete<ApiEnvelope<Warehouse>>(ENDPOINTS.WAREHOUSES.ARCHIVE(id), versionHeaders(expectedVersion))),
  setDefaultWarehouse: (id: string, key: string) => command<Warehouse>(ENDPOINTS.WAREHOUSES.SET_DEFAULT(id), { transition_key: key }, key),

  listLocations: (filters: LocationFilters = {}) => list<StorageLocation>(ENDPOINTS.LOCATIONS.LIST, filters),
  getLocation: (id: string) => get<StorageLocation>(ENDPOINTS.LOCATIONS.DETAIL(id)),
  createLocation: (body: StorageLocationCreate, key: string) => create<StorageLocation, StorageLocationCreate>(ENDPOINTS.LOCATIONS.CREATE, body, key),
  updateLocation: (id: string, body: StorageLocationUpdate, expectedVersion: number) => update<StorageLocation, StorageLocationUpdate>(ENDPOINTS.LOCATIONS.UPDATE(id), body, expectedVersion),
  archiveLocation: async (id: string, expectedVersion: number) => unwrap(await apiClient.delete<ApiEnvelope<StorageLocation>>(ENDPOINTS.LOCATIONS.ARCHIVE(id), versionHeaders(expectedVersion))),

  listItems: (filters: ItemFilters = {}) => list<Item>(ENDPOINTS.ITEMS.LIST, filters),
  getItem: (id: string) => get<Item>(ENDPOINTS.ITEMS.DETAIL(id)),
  createItem: (body: ItemCreate, key: string) => create<Item, ItemCreate>(ENDPOINTS.ITEMS.CREATE, body, key),
  updateItem: (id: string, body: ItemUpdate, expectedVersion: number) => update<Item, ItemUpdate>(ENDPOINTS.ITEMS.UPDATE(id), body, expectedVersion),
  archiveItem: async (id: string, expectedVersion: number) => unwrap(await apiClient.delete<ApiEnvelope<Item>>(ENDPOINTS.ITEMS.ARCHIVE(id), versionHeaders(expectedVersion))),

  listBatches: (filters: BatchFilters = {}) => list<Batch>(ENDPOINTS.BATCHES.LIST, filters),
  getBatch: (id: string) => get<Batch>(ENDPOINTS.BATCHES.DETAIL(id)),
  createBatch: (body: BatchCreate, key: string) => create<Batch, BatchCreate>(ENDPOINTS.BATCHES.CREATE, body, key),
  updateBatch: (id: string, body: BatchUpdate, expectedVersion: number) => update<Batch, BatchUpdate>(ENDPOINTS.BATCHES.UPDATE(id), body, expectedVersion),
  commandBatch: (id: string, name: "activate" | "quarantine" | "release" | "recall", body: InventoryCommandRequest, key: string) => command<Batch>(ENDPOINTS.BATCHES.COMMAND(id, name), body, key),
  traceBatch: (id: string) => get<StockLedgerEntry[]>(ENDPOINTS.BATCHES.TRACE(id)),

  listSerials: (filters: SerialFilters = {}) => list<SerialNumber>(ENDPOINTS.SERIALS.LIST, filters),
  getSerial: (id: string) => get<SerialNumber>(ENDPOINTS.SERIALS.DETAIL(id)),
  createSerial: (body: SerialNumberCreate, key: string) => create<SerialNumber, SerialNumberCreate>(ENDPOINTS.SERIALS.CREATE, body, key),
  updateSerial: (id: string, body: SerialNumberUpdate, expectedVersion: number) => update<SerialNumber, SerialNumberUpdate>(ENDPOINTS.SERIALS.UPDATE(id), body, expectedVersion),
  traceSerial: (id: string) => get<StockLedgerEntry[]>(ENDPOINTS.SERIALS.TRACE(id)),

  listStockEntries: (filters: StockEntryFilters = {}) => list<StockEntry>(ENDPOINTS.STOCK_ENTRIES.LIST, filters),
  getStockEntry: (id: string) => get<StockEntry>(ENDPOINTS.STOCK_ENTRIES.DETAIL(id)),
  createStockEntry: (body: StockEntryCreate, key: string) => create<StockEntry, StockEntryCreate>(ENDPOINTS.STOCK_ENTRIES.CREATE, body, key),
  updateStockEntry: (id: string, body: StockEntryUpdate, expectedVersion: number) => update<StockEntry, StockEntryUpdate>(ENDPOINTS.STOCK_ENTRIES.UPDATE(id), body, expectedVersion),
  deleteStockEntryDraft: async (id: string, expectedVersion: number) => unwrap(await apiClient.delete<ApiEnvelope<StockEntry>>(ENDPOINTS.STOCK_ENTRIES.DELETE_DRAFT(id), versionHeaders(expectedVersion))),
  commandStockEntry: (id: string, name: "submit" | "approve" | "reject" | "post" | "cancel" | "reverse", body: InventoryCommandRequest, key: string) => command<StockEntry>(ENDPOINTS.STOCK_ENTRIES.COMMAND(id, name), body, key),
  previewStockEntry: (id: string) => get<PostPreview>(ENDPOINTS.STOCK_ENTRIES.PREVIEW(id)),

  listBalances: (filters: BalanceFilters = {}) => list<StockBalance>(ENDPOINTS.STOCK_BALANCES.LIST, filters),
  getBalance: (id: string) => get<StockBalance>(ENDPOINTS.STOCK_BALANCES.DETAIL(id)),
  listLedger: (filters: LedgerFilters = {}) => list<StockLedgerEntry>(ENDPOINTS.STOCK_LEDGER.LIST, filters),
  getLedgerEntry: (id: string) => get<StockLedgerEntry>(ENDPOINTS.STOCK_LEDGER.DETAIL(id)),

  listReservations: (filters: ReservationFilters = {}) => list<StockReservation>(ENDPOINTS.RESERVATIONS.LIST, filters),
  getReservation: (id: string) => get<StockReservation>(ENDPOINTS.RESERVATIONS.DETAIL(id)),
  createReservation: (body: ReservationCreate, key: string) => create<StockReservation, ReservationCreate>(ENDPOINTS.RESERVATIONS.CREATE, body, key),
  updateReservation: (id: string, body: ReservationUpdate, expectedVersion: number) => update<StockReservation, ReservationUpdate>(ENDPOINTS.RESERVATIONS.UPDATE(id), body, expectedVersion),
  commandReservation: (id: string, name: "release" | "consume" | "cancel", body: InventoryCommandRequest, key: string) => command<StockReservation>(ENDPOINTS.RESERVATIONS.COMMAND(id, name), body, key),

  listCycleCounts: (filters: CycleCountFilters = {}) => list<CycleCount>(ENDPOINTS.CYCLE_COUNTS.LIST, filters),
  getCycleCount: (id: string) => get<CycleCount>(ENDPOINTS.CYCLE_COUNTS.DETAIL(id)),
  createCycleCount: (body: CycleCountCreate, key: string) => create<CycleCount, CycleCountCreate>(ENDPOINTS.CYCLE_COUNTS.CREATE, body, key),
  updateCycleCount: (id: string, body: CycleCountUpdate, expectedVersion: number) => update<CycleCount, CycleCountUpdate>(ENDPOINTS.CYCLE_COUNTS.UPDATE(id), body, expectedVersion),
  commandCycleCount: (id: string, name: "start" | "submit" | "approve" | "reject" | "post" | "cancel", body: InventoryCommandRequest, key: string) => command<CycleCount>(ENDPOINTS.CYCLE_COUNTS.COMMAND(id, name), body, key),

  listConfigurations: () => list<InventoryConfiguration>(ENDPOINTS.CONFIGURATIONS.LIST, {}),
  getConfiguration: (environment: Environment) => get<InventoryConfiguration>(ENDPOINTS.CONFIGURATIONS.DETAIL(environment)),
  createConfigurationRevision: (environment: Environment, body: ConfigurationUpdate, expectedVersion: number) => update<InventoryConfiguration, ConfigurationUpdate>(ENDPOINTS.CONFIGURATIONS.UPDATE(environment), body, expectedVersion),
  previewConfiguration: async (environment: Environment, body: ConfigurationUpdate) => unwrap(await apiClient.post<ApiEnvelope<ConfigurationPreview>>(ENDPOINTS.CONFIGURATIONS.PREVIEW(environment), body)),
  activateConfiguration: (environment: Environment, body: ConfigurationActivateRequest, key: string) => create<InventoryConfiguration, ConfigurationActivateRequest>(ENDPOINTS.CONFIGURATIONS.ACTIVATE(environment), body, key),
  rollbackConfiguration: (environment: Environment, body: ConfigurationRollbackRequest, key: string) => create<InventoryConfiguration, ConfigurationRollbackRequest>(ENDPOINTS.CONFIGURATIONS.ROLLBACK(environment), body, key),
  importConfiguration: (environment: Environment, body: ConfigurationImportRequest, key: string) => create<InventoryConfiguration, ConfigurationImportRequest>(ENDPOINTS.CONFIGURATIONS.IMPORT(environment), body, key),
  exportConfiguration: (environment: Environment) => get<ConfigurationExportDocument>(ENDPOINTS.CONFIGURATIONS.EXPORT(environment)),
  configurationHistory: (environment: Environment) => list<InventoryConfigurationRevision>(ENDPOINTS.CONFIGURATIONS.HISTORY(environment), {}),

  dashboard: () => get<InventoryDashboard>(ENDPOINTS.DASHBOARD),
  enqueueImport: (body: ImportRequest, key: string) => create<InventoryJob, ImportRequest>(ENDPOINTS.IMPORTS, body, key),
  health: () => get<{ status: "healthy" | "degraded" | "unhealthy" }>(ENDPOINTS.HEALTH),
};
