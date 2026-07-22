import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiEnvelope,
  type AssetCategory,
  type AssetCategoryCreateRequest,
  type AssetCategoryUpdateRequest,
  type AssetFilters,
  type AssetTransaction,
  type CapitalizeRequest,
  type CategoryFilters,
  type DepreciationLine,
  type DepreciationSchedule,
  type DepreciationStrategyDescriptor,
  type DisposalRequest,
  type DuePostingRequest,
  type FixedAsset,
  type FixedAssetCreateRequest,
  type FixedAssetDashboard,
  type FixedAssetUpdateRequest,
  type GovernedErrorBody,
  type HealthStatus,
  type ImpairmentRequest,
  type JobStatusDto,
  type LineFilters,
  type LinePostingRequest,
  type LifecyclePreview,
  type ListResult,
  type PaginatedEnvelope,
  type ScheduleCalculateRequest,
  type ScheduleCreateRequest,
  type ScheduleFilters,
  type ScheduleTransitionRequest,
  type ScheduleUpdateRequest,
  type TransferRequest,
  type ValidationError,
} from '../contracts';

export class FixedAssetsApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
    readonly fieldErrors: readonly ValidationError[] = [],
  ) {
    super(message);
    this.name = 'FixedAssetsApiError';
  }
  fieldError(field: string): string | undefined {
    return this.fieldErrors.find((item) => item.field === field)?.message;
  }
}

function governedError(details: unknown): GovernedErrorBody['error'] | undefined {
  if (!details || typeof details !== 'object' || !('error' in details)) return undefined;
  const error = details.error;
  if (!error || typeof error !== 'object' || !('code' in error) || !('message' in error)) return undefined;
  return error as GovernedErrorBody['error'];
}

async function translate<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (failure) {
    if (!(failure instanceof ApiError)) throw failure;
    const error = governedError(failure.details);
    throw new FixedAssetsApiError(
      error?.message ?? failure.message,
      failure.status,
      error?.code ?? failure.code ?? 'REQUEST_FAILED',
      error?.correlation_id ?? failure.correlationId ?? null,
      error?.field_errors ?? [],
    );
  }
}

function query(path: string, filters: object = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const suffix = params.toString();
  return suffix ? `${path}?${suffix}` : path;
}

async function detail<T>(request: Promise<ApiEnvelope<T>>): Promise<T> {
  return (await translate(request)).data;
}

async function list<T>(request: Promise<PaginatedEnvelope<T>>): Promise<ListResult<T>> {
  const envelope = await translate(request);
  if (!envelope.meta?.pagination || !Array.isArray(envelope.data)) {
    throw new FixedAssetsApiError('The server returned an invalid paginated envelope.', 502, 'MALFORMED_RESPONSE', envelope.meta?.correlation_id ?? null);
  }
  return { items: envelope.data, pagination: envelope.meta.pagination, correlationId: envelope.meta.correlation_id };
}

function idempotencyHeaders(key: string): RequestInit {
  return { headers: { 'Idempotency-Key': key } };
}

async function allScheduleLines(scheduleId: string): Promise<readonly DepreciationLine[]> {
  const first = await list(apiClient.get<PaginatedEnvelope<DepreciationLine>>(query(ENDPOINTS.LINES.LIST, { schedule_id: scheduleId, page: 1, page_size: 100 })));
  const items = [...first.items];
  for (let page = 2; page <= first.pagination.total_pages; page += 1) {
    const result = await list(apiClient.get<PaginatedEnvelope<DepreciationLine>>(query(ENDPOINTS.LINES.LIST, { schedule_id: scheduleId, page, page_size: 100 })));
    items.push(...result.items);
  }
  return items;
}

export const fixedAssetQueryKeys = {
  root: (tenantId: string | null) => ['fixed-assets', tenantId ?? 'no-tenant'] as const,
  dashboard: (tenantId: string | null) => [...fixedAssetQueryKeys.root(tenantId), 'dashboard'] as const,
  assets: (tenantId: string | null, filters: AssetFilters = {}) => [...fixedAssetQueryKeys.root(tenantId), 'assets', filters] as const,
  asset: (tenantId: string | null, id: string) => [...fixedAssetQueryKeys.root(tenantId), 'asset', id] as const,
  categories: (tenantId: string | null, filters: CategoryFilters = {}) => [...fixedAssetQueryKeys.root(tenantId), 'categories', filters] as const,
  category: (tenantId: string | null, id: string) => [...fixedAssetQueryKeys.root(tenantId), 'category', id] as const,
  schedules: (tenantId: string | null, filters: ScheduleFilters = {}) => [...fixedAssetQueryKeys.root(tenantId), 'schedules', filters] as const,
  schedule: (tenantId: string | null, id: string) => [...fixedAssetQueryKeys.root(tenantId), 'schedule', id] as const,
  lines: (tenantId: string | null, filters: LineFilters = {}) => [...fixedAssetQueryKeys.root(tenantId), 'lines', filters] as const,
  line: (tenantId: string | null, id: string) => [...fixedAssetQueryKeys.root(tenantId), 'line', id] as const,
  transaction: (tenantId: string | null, id: string) => [...fixedAssetQueryKeys.root(tenantId), 'transaction', id] as const,
  job: (tenantId: string | null, id: string) => [...fixedAssetQueryKeys.root(tenantId), 'job', id] as const,
};

export const fixedAssetsService = {
  dashboard: () => detail(apiClient.get<ApiEnvelope<FixedAssetDashboard>>(ENDPOINTS.DASHBOARD)),
  health: () => detail(apiClient.get<ApiEnvelope<HealthStatus>>(ENDPOINTS.HEALTH)),

  listAssets: (filters: AssetFilters = {}) => list(apiClient.get<PaginatedEnvelope<FixedAsset>>(query(ENDPOINTS.ASSETS.LIST, filters))),
  getAsset: (id: string) => detail(apiClient.get<ApiEnvelope<FixedAsset>>(ENDPOINTS.ASSETS.DETAIL(id))),
  createAsset: (data: FixedAssetCreateRequest, key: string) => detail(apiClient.post<ApiEnvelope<FixedAsset>>(ENDPOINTS.ASSETS.CREATE, data, idempotencyHeaders(key))),
  updateAsset: (id: string, data: FixedAssetUpdateRequest) => detail(apiClient.patch<ApiEnvelope<FixedAsset>>(ENDPOINTS.ASSETS.UPDATE(id), data)),
  deleteAsset: (id: string) => translate(apiClient.delete<void>(ENDPOINTS.ASSETS.DELETE(id))),
  capitalize: (id: string, data: CapitalizeRequest, key: string) => detail(apiClient.post<ApiEnvelope<FixedAsset>>(ENDPOINTS.ASSETS.CAPITALIZE(id), data, idempotencyHeaders(key))),
  previewCapitalize: (id: string, data: CapitalizeRequest) => detail(apiClient.post<ApiEnvelope<LifecyclePreview>>(ENDPOINTS.ASSETS.PREVIEW_CAPITALIZE(id), data)),
  transfer: (id: string, data: TransferRequest, key: string) => detail(apiClient.post<ApiEnvelope<FixedAsset>>(ENDPOINTS.ASSETS.TRANSFER(id), data, idempotencyHeaders(key))),
  previewTransfer: (id: string, data: TransferRequest) => detail(apiClient.post<ApiEnvelope<LifecyclePreview>>(ENDPOINTS.ASSETS.PREVIEW_TRANSFER(id), data)),
  impair: (id: string, data: ImpairmentRequest, key: string) => detail(apiClient.post<ApiEnvelope<FixedAsset>>(ENDPOINTS.ASSETS.IMPAIR(id), data, idempotencyHeaders(key))),
  previewImpair: (id: string, data: ImpairmentRequest) => detail(apiClient.post<ApiEnvelope<LifecyclePreview>>(ENDPOINTS.ASSETS.PREVIEW_IMPAIR(id), data)),
  dispose: (id: string, data: DisposalRequest, key: string) => detail(apiClient.post<ApiEnvelope<FixedAsset>>(ENDPOINTS.ASSETS.DISPOSE(id), data, idempotencyHeaders(key))),
  previewDispose: (id: string, data: DisposalRequest) => detail(apiClient.post<ApiEnvelope<LifecyclePreview>>(ENDPOINTS.ASSETS.PREVIEW_DISPOSE(id), data)),
  assetTransactions: (id: string, page = 1) => list(apiClient.get<PaginatedEnvelope<AssetTransaction>>(query(ENDPOINTS.ASSETS.TRANSACTIONS(id), { page }))),

  listCategories: (filters: CategoryFilters = {}) => list(apiClient.get<PaginatedEnvelope<AssetCategory>>(query(ENDPOINTS.CATEGORIES.LIST, filters))),
  getCategory: (id: string) => detail(apiClient.get<ApiEnvelope<AssetCategory>>(ENDPOINTS.CATEGORIES.DETAIL(id))),
  createCategory: (data: AssetCategoryCreateRequest, key: string) => detail(apiClient.post<ApiEnvelope<AssetCategory>>(ENDPOINTS.CATEGORIES.CREATE, data, idempotencyHeaders(key))),
  updateCategory: (id: string, data: AssetCategoryUpdateRequest) => detail(apiClient.patch<ApiEnvelope<AssetCategory>>(ENDPOINTS.CATEGORIES.UPDATE(id), data)),
  deactivateCategory: (id: string) => translate(apiClient.delete<void>(ENDPOINTS.CATEGORIES.DELETE(id))),

  listSchedules: (filters: ScheduleFilters = {}) => list(apiClient.get<PaginatedEnvelope<DepreciationSchedule>>(query(ENDPOINTS.SCHEDULES.LIST, filters))),
  getSchedule: (id: string) => detail(apiClient.get<ApiEnvelope<DepreciationSchedule>>(ENDPOINTS.SCHEDULES.DETAIL(id))),
  createSchedule: (data: ScheduleCreateRequest, key: string) => detail(apiClient.post<ApiEnvelope<DepreciationSchedule>>(ENDPOINTS.SCHEDULES.CREATE, data, idempotencyHeaders(key))),
  updateSchedule: (id: string, data: ScheduleUpdateRequest) => detail(apiClient.patch<ApiEnvelope<DepreciationSchedule>>(ENDPOINTS.SCHEDULES.UPDATE(id), data)),
  deleteSchedule: (id: string) => translate(apiClient.delete<void>(ENDPOINTS.SCHEDULES.DELETE(id))),
  calculateSchedule: (id: string, data: ScheduleCalculateRequest, key: string) => detail(apiClient.post<ApiEnvelope<DepreciationSchedule>>(ENDPOINTS.SCHEDULES.CALCULATE(id), data, idempotencyHeaders(key))),
  activateSchedule: (id: string, data: ScheduleTransitionRequest, key: string) => detail(apiClient.post<ApiEnvelope<DepreciationSchedule>>(ENDPOINTS.SCHEDULES.ACTIVATE(id), { ...data, transition_key: key }, idempotencyHeaders(key))),
  supersedeSchedule: (id: string, data: ScheduleTransitionRequest, key: string) => detail(apiClient.post<ApiEnvelope<DepreciationSchedule>>(ENDPOINTS.SCHEDULES.SUPERSEDE(id), { ...data, transition_key: key }, idempotencyHeaders(key))),

  listLines: (filters: LineFilters = {}) => list(apiClient.get<PaginatedEnvelope<DepreciationLine>>(query(ENDPOINTS.LINES.LIST, filters))),
  getAllScheduleLines: allScheduleLines,
  getLine: (id: string) => detail(apiClient.get<ApiEnvelope<DepreciationLine>>(ENDPOINTS.LINES.DETAIL(id))),
  postLine: (id: string, data: LinePostingRequest, key: string) => detail(apiClient.post<ApiEnvelope<JobStatusDto>>(ENDPOINTS.LINES.POST(id), data, idempotencyHeaders(key))),
  postDue: (data: DuePostingRequest, key: string) => detail(apiClient.post<ApiEnvelope<JobStatusDto>>(ENDPOINTS.LINES.POST_DUE, data, idempotencyHeaders(key))),
  getTransaction: (id: string) => detail(apiClient.get<ApiEnvelope<AssetTransaction>>(ENDPOINTS.TRANSACTIONS.DETAIL(id))),
  getJob: (id: string) => detail(apiClient.get<ApiEnvelope<JobStatusDto>>(ENDPOINTS.JOBS.DETAIL(id))),
  listStrategies: () => list(apiClient.get<PaginatedEnvelope<DepreciationStrategyDescriptor>>(ENDPOINTS.STRATEGIES.LIST)),
};

export function shouldPollJob(job: JobStatusDto | undefined): boolean {
  return job?.status === 'queued' || job?.status === 'running';
}

export function createIdempotencyKey(operation: string): string {
  return `${operation}:${crypto.randomUUID()}`;
}
