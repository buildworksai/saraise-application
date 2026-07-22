import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS, withQuery,
  type AcceptedJob, type ActualsSyncRequest, type AllocationReplaceRequest, type ApiV2Envelope,
  type ApiV2PaginatedEnvelope, type ApprovalFilters, type BudgetApproval, type BudgetAvailabilityRequest,
  type BudgetAvailabilityResult, type BudgetCreateRequest, type BudgetDetail, type BudgetLine,
  type BudgetLineCreateRequest, type BudgetLineFilters, type BudgetLineUpdateRequest, type BudgetListFilters,
  type BudgetListItem, type BudgetUpdateRequest, type HealthResult, type PaginatedResult, type RejectRequest,
  type TransitionRequest, type UUID, type VarianceAlert,
  type VarianceAlertFilters, type VarianceAlertGenerateRequest, type VarianceFilters, type VarianceReport,
} from '../contracts';

export class BudgetManagementApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId?: string,
    readonly fieldErrors?: Readonly<Record<string, readonly string[]>>,
    readonly retryable = false,
  ) { super(message); this.name = 'BudgetManagementApiError'; }
}

function governedError(error: unknown): BudgetManagementApiError {
  if (error instanceof BudgetManagementApiError) return error;
  if (error instanceof ApiError) {
    let fields: Readonly<Record<string, readonly string[]>> | undefined;
    let retryable = false;
    if (isRecord(error.details) && isRecord(error.details.error)) {
      const nested = error.details.error;
      if (isFieldMap(nested.fields)) fields = nested.fields;
      retryable = nested.retryable === true;
    }
    return new BudgetManagementApiError(error.message, error.status, error.code ?? 'REQUEST_FAILED', error.correlationId, fields, retryable);
  }
  return new BudgetManagementApiError(error instanceof Error ? error.message : 'Budget Management request failed.', 0, 'NETWORK_ERROR', undefined, undefined, true);
}
function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function isFieldMap(value: unknown): value is Readonly<Record<string, readonly string[]>> { return isRecord(value) && Object.values(value).every((item) => Array.isArray(item) && item.every((entry) => typeof entry === 'string')); }
async function call<T>(operation: () => Promise<T>): Promise<T> { try { return await operation(); } catch (error) { throw governedError(error); } }
function item<T>(envelope: ApiV2Envelope<T>): T { return envelope.data; }
function page<T>(envelope: ApiV2PaginatedEnvelope<T>): PaginatedResult<T> { return { items: envelope.data, pagination: envelope.meta.pagination, correlationId: envelope.meta.correlation_id, receivedAt: envelope.meta.timestamp }; }
function read<T>(path: string, signal?: AbortSignal): Promise<T> { return call(async () => item(await apiClient.get<ApiV2Envelope<T>>(path, { signal }))); }
function readPage<T>(path: string, signal?: AbortSignal): Promise<PaginatedResult<T>> { return call(async () => page(await apiClient.get<ApiV2PaginatedEnvelope<T>>(path, { signal }))); }
function post<T>(path: string, body: object): Promise<T> { return call(async () => item(await apiClient.post<ApiV2Envelope<T>>(path, body))); }
function postIdempotent<T>(path: string, key: string, body: object = {}): Promise<T> { return call(async () => item(await apiClient.post<ApiV2Envelope<T>>(path, body, { headers: { 'Idempotency-Key': key } }))); }

export const budgetService = {
  listBudgets: (filters: BudgetListFilters = {}, signal?: AbortSignal) => readPage<BudgetListItem>(withQuery(ENDPOINTS.BUDGETS.LIST, filters), signal),
  getBudget: (id: UUID, signal?: AbortSignal) => read<BudgetDetail>(ENDPOINTS.BUDGETS.DETAIL(id), signal),
  createBudget: (request: BudgetCreateRequest) => post<BudgetDetail>(ENDPOINTS.BUDGETS.CREATE, request),
  updateBudget: (id: UUID, request: BudgetUpdateRequest) => call(async () => item(await apiClient.patch<ApiV2Envelope<BudgetDetail>>(ENDPOINTS.BUDGETS.UPDATE(id), request))),
  deleteBudget: (id: UUID, expectedUpdatedAt: string) => call(async () => { await apiClient.delete<void>(ENDPOINTS.BUDGETS.DELETE(id), { body: JSON.stringify({ expected_updated_at: expectedUpdatedAt }) }); }),
  replaceAllocations: (id: UUID, request: AllocationReplaceRequest) => call(async () => item(await apiClient.put<ApiV2Envelope<BudgetDetail>>(ENDPOINTS.BUDGETS.ALLOCATIONS(id), request))),
  submitBudget: (id: UUID, request: TransitionRequest) => postIdempotent<BudgetDetail>(ENDPOINTS.BUDGETS.SUBMIT(id), request.idempotency_key, { notes: request.notes ?? '' }),
  approveBudget: (id: UUID, request: TransitionRequest) => postIdempotent<BudgetDetail>(ENDPOINTS.BUDGETS.APPROVE(id), request.idempotency_key, { notes: request.notes ?? '' }),
  rejectBudget: (id: UUID, request: RejectRequest) => postIdempotent<BudgetDetail>(ENDPOINTS.BUDGETS.REJECT(id), request.idempotency_key, { reason: request.reason }),
  reviseBudget: (id: UUID, request: TransitionRequest) => postIdempotent<BudgetDetail>(ENDPOINTS.BUDGETS.REVISE(id), request.idempotency_key, { notes: request.notes ?? '' }),
  closeBudget: (id: UUID, request: TransitionRequest) => postIdempotent<BudgetDetail>(ENDPOINTS.BUDGETS.CLOSE(id), request.idempotency_key),
  getVariance: (id: UUID, filters: VarianceFilters = {}, signal?: AbortSignal) => read<VarianceReport>(withQuery(ENDPOINTS.BUDGETS.VARIANCE(id), filters), signal),
  requestActualsSync: (id: UUID, request: ActualsSyncRequest) => postIdempotent<AcceptedJob>(ENDPOINTS.BUDGETS.SYNC_ACTUALS(id), request.idempotency_key),
  listLines: (filters: BudgetLineFilters, signal?: AbortSignal) => readPage<BudgetLine>(withQuery(ENDPOINTS.BUDGET_LINES.LIST, filters), signal),
  getLine: (id: UUID, signal?: AbortSignal) => read<BudgetLine>(ENDPOINTS.BUDGET_LINES.DETAIL(id), signal),
  createLine: (request: BudgetLineCreateRequest) => post<BudgetLine>(ENDPOINTS.BUDGET_LINES.CREATE, request),
  updateLine: (id: UUID, request: BudgetLineUpdateRequest) => call(async () => item(await apiClient.patch<ApiV2Envelope<BudgetLine>>(ENDPOINTS.BUDGET_LINES.UPDATE(id), request))),
  deleteLine: (id: UUID, expectedUpdatedAt: string) => call(async () => { await apiClient.delete<void>(ENDPOINTS.BUDGET_LINES.DELETE(id), { body: JSON.stringify({ expected_updated_at: expectedUpdatedAt }) }); }),
  listApprovals: (filters: ApprovalFilters = {}, signal?: AbortSignal) => readPage<BudgetApproval>(withQuery(ENDPOINTS.APPROVALS.LIST, filters), signal),
  getApproval: (id: UUID, signal?: AbortSignal) => read<BudgetApproval>(ENDPOINTS.APPROVALS.DETAIL(id), signal),
  listAlerts: (filters: VarianceAlertFilters = {}, signal?: AbortSignal) => readPage<VarianceAlert>(withQuery(ENDPOINTS.VARIANCE_ALERTS.LIST, filters), signal),
  getAlert: (id: UUID, signal?: AbortSignal) => read<VarianceAlert>(ENDPOINTS.VARIANCE_ALERTS.DETAIL(id), signal),
  generateAlerts: (request: VarianceAlertGenerateRequest) => postIdempotent<AcceptedJob>(ENDPOINTS.VARIANCE_ALERTS.GENERATE, request.idempotency_key, { threshold_percentage: request.threshold_percentage, alert_type: request.alert_type }),
  acknowledgeAlert: (id: UUID) => post<VarianceAlert>(ENDPOINTS.VARIANCE_ALERTS.ACKNOWLEDGE(id), {}),
  checkAvailability: (request: BudgetAvailabilityRequest) => post<BudgetAvailabilityResult>(ENDPOINTS.AVAILABILITY, request),
  getHealth: (signal?: AbortSignal) => read<HealthResult>(ENDPOINTS.HEALTH, signal),
};

export type BudgetService = typeof budgetService;
