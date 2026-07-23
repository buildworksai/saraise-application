import { apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiV2Envelope,
  type ApiV2Page,
  type CommandPayload,
  type CommandResponse,
  type ConfigurationChange,
  type ConfigurationExport,
  type ConfigurationImport,
  type ConfigurationPreview,
  type ConfigurationRollback,
  type Customer,
  type CustomerCreate,
  type CustomerFilters,
  type CustomerUpdate,
  type DeliveryNote,
  type DeliveryNoteCreate,
  type DeliveryNoteFilters,
  type DeliveryNoteUpdate,
  type Quotation,
  type QuotationCreate,
  type QuotationFilters,
  type QuotationPreview,
  type QuotationUpdate,
  type SalesConfiguration,
  type SalesConfigurationValues,
  type SalesConfigurationVersion,
  type SalesHealth,
  type SalesDashboardSummary,
  type SalesExtensionCapability,
  type SalesOrder,
  type SalesOrderCreate,
  type SalesOrderFilters,
  type SalesOrderUpdate,
  type UUID,
} from '../contracts';

type JsonRecord = Record<string, unknown>;
type FilterValue = string | number | boolean | null | undefined;

export class SalesGatewayError extends Error {
  readonly code = 'MALFORMED_GATEWAY_RESPONSE';
  constructor(readonly correlationId?: string) {
    super('The sales service returned a malformed governed response.');
    this.name = 'SalesGatewayError';
  }
}

const isRecord = (value: unknown): value is JsonRecord => value !== null && typeof value === 'object' && !Array.isArray(value);
const isMeta = (value: unknown): value is JsonRecord => isRecord(value) && typeof value.correlation_id === 'string' && typeof value.timestamp === 'string';
const requireObject = <T>(value: unknown, correlationId?: string): T => {
  if (!isRecord(value) || typeof value.id !== 'string') throw new SalesGatewayError(correlationId);
  return value as T;
};

function unwrap<T>(value: unknown, validate: (data: unknown, correlationId?: string) => T): T {
  if (!isRecord(value) || !('data' in value) || !isMeta(value.meta)) throw new SalesGatewayError();
  return validate(value.data, value.meta.correlation_id as string);
}

function unwrapPage<T>(value: unknown, validate: (data: unknown, correlationId?: string) => T): ApiV2Page<T> {
  if (!isRecord(value) || !Array.isArray(value.data)) throw new SalesGatewayError();
  const meta = value.meta;
  if (!isMeta(meta) || !isRecord(meta.pagination)) throw new SalesGatewayError();
  const pagination = meta.pagination;
  if (![pagination.page, pagination.page_size, pagination.count, pagination.total_pages].every((entry) => typeof entry === 'number') || typeof pagination.has_next !== 'boolean' || typeof pagination.has_previous !== 'boolean') throw new SalesGatewayError(meta.correlation_id as string);
  return { data: value.data.map((item) => validate(item, meta.correlation_id as string)), meta: meta as unknown as ApiV2Page<T>['meta'] };
}

function query(path: string, filters: object = {}): string {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, rawValue]) => {
    const value = rawValue as FilterValue;
    if (value !== undefined && value !== null && String(value).trim() !== '') parameters.set(key, String(value));
  });
  const serialized = parameters.toString();
  return serialized ? `${path}?${serialized}` : path;
}

const idempotency = (key: UUID): RequestInit => ({ headers: { 'Idempotency-Key': key } });
const deleteVersion = (expectedVersion: number): RequestInit => ({ headers: { 'If-Match': String(expectedVersion) } });
const object = <T>(value: unknown, correlationId?: string) => requireObject<T>(value, correlationId);
const configuration = (value: unknown, correlationId?: string): SalesConfiguration => object<SalesConfiguration>(value, correlationId);

export const salesQueryKeys = {
  all: ['sales-management'] as const,
  dashboard: () => [...salesQueryKeys.all, 'dashboard'] as const,
  customers: (filters: CustomerFilters = {}) => [...salesQueryKeys.all, 'customers', filters] as const,
  customer: (id: UUID) => [...salesQueryKeys.all, 'customer', id] as const,
  quotations: (filters: QuotationFilters = {}) => [...salesQueryKeys.all, 'quotations', filters] as const,
  quotation: (id: UUID) => [...salesQueryKeys.all, 'quotation', id] as const,
  orders: (filters: SalesOrderFilters = {}) => [...salesQueryKeys.all, 'orders', filters] as const,
  order: (id: UUID) => [...salesQueryKeys.all, 'order', id] as const,
  deliveries: (filters: DeliveryNoteFilters = {}) => [...salesQueryKeys.all, 'deliveries', filters] as const,
  delivery: (id: UUID) => [...salesQueryKeys.all, 'delivery', id] as const,
  configuration: () => [...salesQueryKeys.all, 'configuration'] as const,
  configurationVersions: (page = 1) => [...salesQueryKeys.all, 'configuration-versions', page] as const,
  configurationVersion: (version: number) => [...salesQueryKeys.all, 'configuration-version', version] as const,
};

async function getEntity<T>(path: string): Promise<T> { return unwrap(await apiClient.get<unknown>(path), object<T>); }
async function createEntity<T, P>(path: string, payload: P, key: UUID): Promise<T> { return unwrap(await apiClient.post<unknown>(path, payload, idempotency(key)), object<T>); }
async function updateEntity<T, P>(path: string, payload: P): Promise<T> { return unwrap(await apiClient.patch<unknown>(path, payload), object<T>); }
async function commandEntity<T>(path: string, payload: CommandPayload): Promise<CommandResponse<T>> {
  const { idempotency_key: key, ...body } = payload;
  return unwrap(await apiClient.post<unknown>(path, body, idempotency(key)), (data, correlationId) => {
    if (!isRecord(data) || typeof data.command !== 'string') throw new SalesGatewayError(correlationId);
    return { ...data, resource: object<T>(data.resource, correlationId) } as CommandResponse<T>;
  });
}
async function quotationCommandEntity<T>(path: string, payload: CommandPayload): Promise<T> {
  const { idempotency_key: key, ...body } = payload;
  return unwrap(await apiClient.post<unknown>(path, body, idempotency(key)), object<T>);
}

export const salesService = {
  getSummary: async (): Promise<SalesDashboardSummary> => unwrap(await apiClient.get<unknown>(ENDPOINTS.SUMMARY), (data, correlationId) => {
    if (!isRecord(data) || typeof data.open_quotations !== 'number' || typeof data.confirmed_orders !== 'number' || !isRecord(data.fulfillment_stages) || !Array.isArray(data.recent_deliveries)) throw new SalesGatewayError(correlationId);
    if (!data.recent_deliveries.every((item) => isRecord(item) && typeof item.id === 'string' && typeof item.delivery_number === 'string' && typeof item.delivery_date === 'string' && typeof item.status === 'string')) throw new SalesGatewayError(correlationId);
    return data as unknown as SalesDashboardSummary;
  }),
  getCapabilities: async (): Promise<SalesExtensionCapability[]> => unwrap(await apiClient.get<unknown>(ENDPOINTS.CAPABILITIES), (data, correlationId) => {
    if (!Array.isArray(data) || !data.every((item) => isRecord(item) && typeof item.capability === 'string' && typeof item.status === 'string' && typeof item.reason_code === 'string')) throw new SalesGatewayError(correlationId);
    return data as SalesExtensionCapability[];
  }),
  listCustomers: async (filters: CustomerFilters = {}): Promise<ApiV2Page<Customer>> => unwrapPage(await apiClient.get<unknown>(query(ENDPOINTS.CUSTOMERS.LIST, filters)), object<Customer>),
  getCustomer: (id: UUID) => getEntity<Customer>(ENDPOINTS.CUSTOMERS.DETAIL(id)),
  createCustomer: (data: CustomerCreate, key: UUID) => createEntity<Customer, CustomerCreate>(ENDPOINTS.CUSTOMERS.CREATE, data, key),
  updateCustomer: (id: UUID, data: CustomerUpdate) => updateEntity<Customer, CustomerUpdate>(ENDPOINTS.CUSTOMERS.UPDATE(id), data),
  deleteCustomer: async (id: UUID, expectedVersion: number): Promise<void> => { unwrap(await apiClient.delete<unknown>(ENDPOINTS.CUSTOMERS.DELETE(id), deleteVersion(expectedVersion)), object<Customer>); },

  listQuotations: async (filters: QuotationFilters = {}): Promise<ApiV2Page<Quotation>> => unwrapPage(await apiClient.get<unknown>(query(ENDPOINTS.QUOTATIONS.LIST, filters)), object<Quotation>),
  getQuotation: (id: UUID) => getEntity<Quotation>(ENDPOINTS.QUOTATIONS.DETAIL(id)),
  previewQuotation: async (data: QuotationCreate): Promise<QuotationPreview> => unwrap(await apiClient.post<unknown>(ENDPOINTS.QUOTATIONS.PREVIEW, data), (value, correlationId) => {
    if (!isRecord(value) || typeof value.total_amount !== 'string' || !Array.isArray(value.lines)) throw new SalesGatewayError(correlationId);
    return value as unknown as QuotationPreview;
  }),
  createQuotation: (data: QuotationCreate, key: UUID) => createEntity<Quotation, QuotationCreate>(ENDPOINTS.QUOTATIONS.CREATE, data, key),
  updateQuotation: (id: UUID, data: QuotationUpdate) => updateEntity<Quotation, QuotationUpdate>(ENDPOINTS.QUOTATIONS.UPDATE(id), data),
  deleteQuotation: async (id: UUID, expectedVersion: number): Promise<void> => { unwrap(await apiClient.delete<unknown>(ENDPOINTS.QUOTATIONS.DELETE(id), deleteVersion(expectedVersion)), object<Quotation>); },
  quotationCommand: (id: UUID, command: 'send'|'accept'|'reject'|'expire'|'revise'|'convert', payload: CommandPayload) => quotationCommandEntity<Quotation | SalesOrder>(ENDPOINTS.QUOTATIONS.COMMAND(id, command), payload),
  sendQuotation: (id: UUID, payload: CommandPayload) => quotationCommandEntity<Quotation>(ENDPOINTS.QUOTATIONS.COMMAND(id, 'send'), payload),
  acceptQuotation: (id: UUID, payload: CommandPayload) => quotationCommandEntity<Quotation>(ENDPOINTS.QUOTATIONS.COMMAND(id, 'accept'), payload),
  rejectQuotation: (id: UUID, payload: CommandPayload) => quotationCommandEntity<Quotation>(ENDPOINTS.QUOTATIONS.COMMAND(id, 'reject'), payload),
  expireQuotation: (id: UUID, payload: CommandPayload) => quotationCommandEntity<Quotation>(ENDPOINTS.QUOTATIONS.COMMAND(id, 'expire'), payload),
  reviseQuotation: (id: UUID, payload: CommandPayload) => quotationCommandEntity<Quotation>(ENDPOINTS.QUOTATIONS.COMMAND(id, 'revise'), payload),
  convertQuotation: (id: UUID, payload: CommandPayload) => quotationCommandEntity<SalesOrder>(ENDPOINTS.QUOTATIONS.COMMAND(id, 'convert'), payload),

  listOrders: async (filters: SalesOrderFilters = {}): Promise<ApiV2Page<SalesOrder>> => unwrapPage(await apiClient.get<unknown>(query(ENDPOINTS.SALES_ORDERS.LIST, filters)), object<SalesOrder>),
  getOrder: (id: UUID) => getEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.DETAIL(id)),
  createOrder: (data: SalesOrderCreate, key: UUID) => createEntity<SalesOrder, SalesOrderCreate>(ENDPOINTS.SALES_ORDERS.CREATE, data, key),
  updateOrder: (id: UUID, data: SalesOrderUpdate) => updateEntity<SalesOrder, SalesOrderUpdate>(ENDPOINTS.SALES_ORDERS.UPDATE(id), data),
  deleteOrder: async (id: UUID, expectedVersion: number): Promise<void> => { unwrap(await apiClient.delete<unknown>(ENDPOINTS.SALES_ORDERS.DELETE(id), deleteVersion(expectedVersion)), object<SalesOrder>); },
  orderCommand: (id: UUID, command: 'confirm'|'start-picking'|'start-packing'|'mark-ready'|'ship'|'deliver'|'mark-invoiced'|'cancel', payload: CommandPayload) => commandEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.COMMAND(id, command), payload),
  confirmOrder: (id: UUID, payload: CommandPayload) => commandEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.COMMAND(id, 'confirm'), payload),
  startOrderPicking: (id: UUID, payload: CommandPayload) => commandEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.COMMAND(id, 'start-picking'), payload),
  startOrderPacking: (id: UUID, payload: CommandPayload) => commandEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.COMMAND(id, 'start-packing'), payload),
  markOrderReady: (id: UUID, payload: CommandPayload) => commandEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.COMMAND(id, 'mark-ready'), payload),
  shipOrder: (id: UUID, payload: CommandPayload) => commandEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.COMMAND(id, 'ship'), payload),
  deliverOrder: (id: UUID, payload: CommandPayload) => commandEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.COMMAND(id, 'deliver'), payload),
  markOrderInvoiced: (id: UUID, payload: CommandPayload) => commandEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.COMMAND(id, 'mark-invoiced'), payload),
  cancelOrder: (id: UUID, payload: CommandPayload) => commandEntity<SalesOrder>(ENDPOINTS.SALES_ORDERS.COMMAND(id, 'cancel'), payload),

  listDeliveryNotes: async (filters: DeliveryNoteFilters = {}): Promise<ApiV2Page<DeliveryNote>> => unwrapPage(await apiClient.get<unknown>(query(ENDPOINTS.DELIVERY_NOTES.LIST, filters)), object<DeliveryNote>),
  getDeliveryNote: (id: UUID) => getEntity<DeliveryNote>(ENDPOINTS.DELIVERY_NOTES.DETAIL(id)),
  createDeliveryNote: (data: DeliveryNoteCreate, key: UUID) => createEntity<DeliveryNote, DeliveryNoteCreate>(ENDPOINTS.DELIVERY_NOTES.CREATE, data, key),
  updateDeliveryNote: (id: UUID, data: DeliveryNoteUpdate) => updateEntity<DeliveryNote, DeliveryNoteUpdate>(ENDPOINTS.DELIVERY_NOTES.UPDATE(id), data),
  deleteDeliveryNote: async (id: UUID, expectedVersion: number): Promise<void> => { unwrap(await apiClient.delete<unknown>(ENDPOINTS.DELIVERY_NOTES.DELETE(id), deleteVersion(expectedVersion)), object<DeliveryNote>); },
  deliveryCommand: (id: UUID, command: 'complete'|'cancel', payload: CommandPayload) => commandEntity<DeliveryNote>(ENDPOINTS.DELIVERY_NOTES.COMMAND(id, command), payload),
  completeDeliveryNote: (id: UUID, payload: CommandPayload) => commandEntity<DeliveryNote>(ENDPOINTS.DELIVERY_NOTES.COMMAND(id, 'complete'), payload),
  cancelDeliveryNote: (id: UUID, payload: CommandPayload) => commandEntity<DeliveryNote>(ENDPOINTS.DELIVERY_NOTES.COMMAND(id, 'cancel'), payload),

  getConfiguration: async (): Promise<SalesConfiguration> => unwrap(await apiClient.get<unknown>(ENDPOINTS.CONFIGURATION.CURRENT), configuration),
  previewConfiguration: async (values: Partial<SalesConfigurationValues>): Promise<ConfigurationPreview> => unwrap(await apiClient.post<unknown>(ENDPOINTS.CONFIGURATION.PREVIEW, values), (data, correlationId) => {
    if (!isRecord(data) || typeof data.valid !== 'boolean' || !Array.isArray(data.diff)) throw new SalesGatewayError(correlationId);
    return data as unknown as ConfigurationPreview;
  }),
  applyConfiguration: async (change: ConfigurationChange): Promise<SalesConfiguration> => unwrap(await apiClient.put<unknown>(ENDPOINTS.CONFIGURATION.CURRENT, { ...change.values, expected_version: change.expected_version, reason: change.reason }), configuration),
  listConfigurationVersions: async (page = 1): Promise<ApiV2Page<SalesConfigurationVersion>> => unwrapPage(await apiClient.get<unknown>(query(ENDPOINTS.CONFIGURATION.VERSIONS, { page })), object<SalesConfigurationVersion>),
  getConfigurationVersion: (version: number) => getEntity<SalesConfigurationVersion>(ENDPOINTS.CONFIGURATION.VERSION(version)),
  rollbackConfiguration: async (payload: ConfigurationRollback): Promise<SalesConfiguration> => {
    const { idempotency_key: key, ...body } = payload;
    return unwrap(await apiClient.post<unknown>(ENDPOINTS.CONFIGURATION.ROLLBACK, body, idempotency(key)), configuration);
  },
  exportConfiguration: async (): Promise<ConfigurationExport> => unwrap(await apiClient.get<unknown>(ENDPOINTS.CONFIGURATION.EXPORT), (data, correlationId) => {
    if (!isRecord(data) || data.schema_version !== 1 || !isRecord(data.values)) throw new SalesGatewayError(correlationId);
    return data as unknown as ConfigurationExport;
  }),
  importConfiguration: async (payload: ConfigurationImport): Promise<ConfigurationPreview | SalesConfiguration> => unwrap(await apiClient.post<unknown>(ENDPOINTS.CONFIGURATION.IMPORT, payload), (data, correlationId) => {
    if (!isRecord(data)) throw new SalesGatewayError(correlationId);
    if ('valid' in data) return data as unknown as ConfigurationPreview;
    return configuration(data, correlationId);
  }),
  getHealth: async (): Promise<SalesHealth> => unwrap(await apiClient.get<unknown>(ENDPOINTS.HEALTH), (data, correlationId) => {
    if (!isRecord(data) || !['available', 'degraded', 'unavailable'].includes(String(data.status))) throw new SalesGatewayError(correlationId);
    return data as unknown as SalesHealth;
  }),
};

export type GovernedEnvelope<T> = ApiV2Envelope<T>;
