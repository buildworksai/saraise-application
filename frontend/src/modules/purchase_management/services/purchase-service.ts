/** Strict transport adapter for purchase-management API v2. */
import { ApiError, apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import type {
  ApiV2Envelope, ApiV2PaginatedEnvelope, ConfigurationDocument, ConfigurationEnvironment,
  ConfigurationPreview, ConfigurationWrite, ListFilters, ModuleHealth, MutationContext,
  ProcurementConfiguration, ProcurementJob, PurchaseOrder, PurchaseOrderWrite, PurchaseReceipt,
  PurchaseRequisition, QuoteComparison, QuoteWrite, ReceiptWrite, RequestForQuotation,
  RequisitionWrite, RFQWrite, Supplier, SupplierQuote, SupplierWrite,
} from '../contracts';

export interface PageResult<T> { items: T[]; meta: ApiV2PaginatedEnvelope<T>['meta'] }
type QueryValue = string | number | undefined;

function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function unwrap<T>(response: ApiV2Envelope<T>): { value: T; meta: ApiV2Envelope<T>['meta'] } {
  if (!object(response) || !('data' in response) || !object(response.meta) || typeof response.meta.correlation_id !== 'string' || typeof response.meta.timestamp !== 'string') throw new ApiError('Malformed API v2 response', 502, response, 'INVALID_RESPONSE');
  return { value: response.data, meta: response.meta };
}
function unwrapPage<T>(response: ApiV2PaginatedEnvelope<T>): PageResult<T> {
  const result = unwrap(response);
  if (!Array.isArray(result.value) || !object(response.meta.pagination)) throw new ApiError('Malformed paginated API v2 response', 502, response, 'INVALID_RESPONSE');
  return { items: result.value, meta: response.meta };
}
function query(path: string, values: Record<string, QueryValue>): string {
  const params = new URLSearchParams(); Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)); });
  const suffix = params.toString(); return suffix ? `${path}?${suffix}` : path;
}
function headers(context: MutationContext): RequestInit {
  return { headers: { 'Idempotency-Key': context.idempotencyKey, ...(context.lockVersion === undefined ? {} : { 'If-Match': String(context.lockVersion) }) } };
}
async function list<T>(path: string, filters: ListFilters = {}): Promise<PageResult<T>> { return unwrapPage(await apiClient.get<ApiV2PaginatedEnvelope<T>>(query(path, filters))); }
async function detail<T>(path: string): Promise<T> { return unwrap(await apiClient.get<ApiV2Envelope<T>>(path)).value; }
async function post<T>(path: string, body: unknown, context: MutationContext): Promise<T> { return unwrap(await apiClient.post<ApiV2Envelope<T>>(path, body, headers(context))).value; }
async function patch<T>(path: string, body: unknown, context: MutationContext): Promise<T> { return unwrap(await apiClient.patch<ApiV2Envelope<T>>(path, body, headers(context))).value; }
async function remove<T>(path: string, reason: string, context: MutationContext): Promise<T> { return unwrap(await apiClient.delete<ApiV2Envelope<T>>(path, { ...headers(context), body: JSON.stringify({ reason }) })).value; }

export const purchaseService = {
  listSuppliers: (filters: ListFilters = {}) => list<Supplier>(ENDPOINTS.SUPPLIERS.LIST, filters),
  getSupplier: (id: string) => detail<Supplier>(ENDPOINTS.SUPPLIERS.DETAIL(id)),
  createSupplier: (data: SupplierWrite, context: MutationContext) => post<Supplier>(ENDPOINTS.SUPPLIERS.CREATE, data, context),
  updateSupplier: (id: string, data: Partial<SupplierWrite>, context: MutationContext) => patch<Supplier>(ENDPOINTS.SUPPLIERS.UPDATE(id), data, context),
  archiveSupplier: (id: string, reason: string, context: MutationContext) => remove<Supplier>(ENDPOINTS.SUPPLIERS.DELETE(id), reason, context),
  activateSupplier: (id: string, reason: string, context: MutationContext) => post<Supplier>(ENDPOINTS.SUPPLIERS.ACTIVATE(id), { reason }, context),
  deactivateSupplier: (id: string, reason: string, context: MutationContext) => post<Supplier>(ENDPOINTS.SUPPLIERS.DEACTIVATE(id), { reason }, context),

  listRequisitions: (filters: ListFilters = {}) => list<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.LIST, filters),
  getRequisition: (id: string) => detail<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.DETAIL(id)),
  createRequisition: (data: RequisitionWrite, context: MutationContext) => post<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.CREATE, data, context),
  updateRequisition: (id: string, data: Partial<RequisitionWrite>, context: MutationContext) => patch<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.UPDATE(id), data, context),
  deleteRequisition: (id: string, reason: string, context: MutationContext) => remove<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.DELETE(id), reason, context),
  submitRequisition: (id: string, context: MutationContext) => post<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.SUBMIT(id), {}, context),
  approveRequisition: (id: string, context: MutationContext) => post<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.APPROVE(id), {}, context),
  rejectRequisition: (id: string, reason: string, context: MutationContext) => post<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.REJECT(id), { reason }, context),
  reviseRequisition: (id: string, context: MutationContext) => post<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.REVISE(id), {}, context),
  cancelRequisition: (id: string, context: MutationContext) => post<PurchaseRequisition>(ENDPOINTS.REQUISITIONS.CANCEL(id), {}, context),
  convertRequisition: (id: string, supplierId: string, lineSelections: PurchaseOrderWrite['lines'], context: MutationContext) => post<PurchaseOrder>(ENDPOINTS.REQUISITIONS.CONVERT(id), { supplier_id: supplierId, line_selections: lineSelections }, context),

  listRFQs: (filters: ListFilters = {}) => list<RequestForQuotation>(ENDPOINTS.RFQS.LIST, filters),
  getRFQ: (id: string) => detail<RequestForQuotation>(ENDPOINTS.RFQS.DETAIL(id)),
  createRFQ: (data: RFQWrite, context: MutationContext) => post<RequestForQuotation>(ENDPOINTS.RFQS.CREATE, data, context),
  updateRFQ: (id: string, data: Partial<RFQWrite>, context: MutationContext) => patch<RequestForQuotation>(ENDPOINTS.RFQS.UPDATE(id), data, context),
  deleteRFQ: (id: string, reason: string, context: MutationContext) => remove<RequestForQuotation>(ENDPOINTS.RFQS.DELETE(id), reason, context),
  publishRFQ: (id: string, supplierIds: string[], context: MutationContext) => post<{ rfq: RequestForQuotation; job_id: string }>(ENDPOINTS.RFQS.PUBLISH(id), { supplier_ids: supplierIds }, context),
  closeRFQ: (id: string, context: MutationContext) => post<RequestForQuotation>(ENDPOINTS.RFQS.CLOSE(id), {}, context),
  cancelRFQ: (id: string, context: MutationContext) => post<RequestForQuotation>(ENDPOINTS.RFQS.CANCEL(id), {}, context),
  compareQuotes: (id: string) => detail<QuoteComparison>(ENDPOINTS.RFQS.COMPARE(id)),
  awardQuote: (id: string, quoteId: string, createPurchaseOrder: boolean, context: MutationContext) => post<{ quote: SupplierQuote; purchase_order: PurchaseOrder | null }>(ENDPOINTS.RFQS.AWARD(id), { quote_id: quoteId, create_purchase_order: createPurchaseOrder }, context),

  listQuotes: (filters: ListFilters = {}) => list<SupplierQuote>(ENDPOINTS.QUOTES.LIST, filters),
  getQuote: (id: string) => detail<SupplierQuote>(ENDPOINTS.QUOTES.DETAIL(id)),
  createQuote: (data: QuoteWrite, context: MutationContext) => post<SupplierQuote>(ENDPOINTS.QUOTES.CREATE, data, context),
  updateQuote: (id: string, data: Partial<QuoteWrite>, context: MutationContext) => patch<SupplierQuote>(ENDPOINTS.QUOTES.UPDATE(id), data, context),
  deleteQuote: (id: string, reason: string, context: MutationContext) => remove<SupplierQuote>(ENDPOINTS.QUOTES.DELETE(id), reason, context),
  submitQuote: (id: string, context: MutationContext) => post<SupplierQuote>(ENDPOINTS.QUOTES.SUBMIT(id), {}, context),
  withdrawQuote: (id: string, context: MutationContext) => post<SupplierQuote>(ENDPOINTS.QUOTES.WITHDRAW(id), {}, context),

  listPurchaseOrders: (filters: ListFilters = {}) => list<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.LIST, filters),
  getPurchaseOrder: (id: string) => detail<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.DETAIL(id)),
  createPurchaseOrder: (data: PurchaseOrderWrite, context: MutationContext) => post<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.CREATE, data, context),
  updatePurchaseOrder: (id: string, data: Partial<PurchaseOrderWrite>, context: MutationContext) => patch<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.UPDATE(id), data, context),
  deletePurchaseOrder: (id: string, reason: string, context: MutationContext) => remove<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.DELETE(id), reason, context),
  submitPurchaseOrder: (id: string, context: MutationContext) => post<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.SUBMIT(id), {}, context),
  approvePurchaseOrder: (id: string, context: MutationContext) => post<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.APPROVE(id), {}, context),
  rejectPurchaseOrder: (id: string, context: MutationContext) => post<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.REJECT(id), {}, context),
  dispatchPurchaseOrder: (id: string, context: MutationContext) => post<{ purchase_order: PurchaseOrder; job_id: string }>(ENDPOINTS.PURCHASE_ORDERS.DISPATCH(id), {}, context),
  acknowledgePurchaseOrder: (id: string, context: MutationContext) => post<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.ACKNOWLEDGE(id), {}, context),
  cancelPurchaseOrder: (id: string, context: MutationContext) => post<PurchaseOrder>(ENDPOINTS.PURCHASE_ORDERS.CANCEL(id), {}, context),

  listReceipts: (filters: ListFilters = {}) => list<PurchaseReceipt>(ENDPOINTS.RECEIPTS.LIST, filters),
  getReceipt: (id: string) => detail<PurchaseReceipt>(ENDPOINTS.RECEIPTS.DETAIL(id)),
  createReceipt: (data: ReceiptWrite, context: MutationContext) => post<PurchaseReceipt>(ENDPOINTS.RECEIPTS.CREATE, data, context),
  updateReceipt: (id: string, data: Partial<ReceiptWrite>, context: MutationContext) => patch<PurchaseReceipt>(ENDPOINTS.RECEIPTS.UPDATE(id), data, context),
  deleteReceipt: (id: string, reason: string, context: MutationContext) => remove<PurchaseReceipt>(ENDPOINTS.RECEIPTS.DELETE(id), reason, context),
  completeReceipt: (id: string, context: MutationContext) => post<PurchaseReceipt>(ENDPOINTS.RECEIPTS.COMPLETE(id), {}, context),
  cancelReceipt: (id: string, context: MutationContext) => post<PurchaseReceipt>(ENDPOINTS.RECEIPTS.CANCEL(id), {}, context),

  getActiveConfiguration: (environment: ConfigurationEnvironment) => detail<ProcurementConfiguration>(query(ENDPOINTS.CONFIGURATIONS.ACTIVE, { environment })),
  listConfigurationVersions: (environment: ConfigurationEnvironment, filters: ListFilters = {}) => list<ProcurementConfiguration>(ENDPOINTS.CONFIGURATIONS.VERSIONS, { ...filters, environment }),
  getConfigurationVersion: (id: string) => detail<ProcurementConfiguration>(ENDPOINTS.CONFIGURATIONS.VERSION(id)),
  createConfigurationDraft: (environment: ConfigurationEnvironment, data: ConfigurationWrite, context: MutationContext) => post<ProcurementConfiguration>(query(ENDPOINTS.CONFIGURATIONS.VERSIONS, { environment }), data, context),
  updateConfigurationDraft: (id: string, data: Partial<ConfigurationWrite>, context: MutationContext) => patch<ProcurementConfiguration>(ENDPOINTS.CONFIGURATIONS.VERSION(id), data, context),
  previewConfiguration: (environment: ConfigurationEnvironment, data: ConfigurationWrite, simulations: Record<string, unknown>[]) => post<ConfigurationPreview>(ENDPOINTS.CONFIGURATIONS.PREVIEW, { environment, ...data, simulations }, { idempotencyKey: crypto.randomUUID() }),
  activateConfiguration: (id: string, reason: string, context: MutationContext) => post<ProcurementConfiguration>(ENDPOINTS.CONFIGURATIONS.ACTIVATE(id), { reason }, context),
  rollbackConfiguration: (id: string, reason: string, context: MutationContext) => post<ProcurementConfiguration>(ENDPOINTS.CONFIGURATIONS.ROLLBACK(id), { reason }, context),
  exportConfiguration: (environment: ConfigurationEnvironment, version?: number) => detail<ConfigurationDocument>(query(ENDPOINTS.CONFIGURATIONS.EXPORT, { environment, version })),
  importConfiguration: (document: ConfigurationDocument, context: MutationContext) => post<ProcurementConfiguration>(ENDPOINTS.CONFIGURATIONS.IMPORT, { document }, context),
  getJob: (id: string) => detail<ProcurementJob>(ENDPOINTS.JOB(id)), getHealth: () => detail<ModuleHealth>(ENDPOINTS.HEALTH),
};
