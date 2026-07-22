/** Type-safe HTTP boundary for Asset Management. */
import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiEnvelope,
  type Asset,
  type AssetCreate,
  type AssetFilters,
  type AssetUpdate,
  type CalculateDepreciationRequest,
  type DepreciationEntry,
  type DepreciationFilters,
  type ListResult,
  type PaginatedResponse,
} from '../contracts';

type FieldErrors = Readonly<Record<string, string>>;

export class AssetManagementApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
    readonly fieldErrors: FieldErrors = {},
  ) {
    super(message);
    this.name = 'AssetManagementApiError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function asStringError(value: unknown): string | undefined {
  if (typeof value === 'string') return value;
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
  return undefined;
}

function extractFieldErrors(details: unknown): FieldErrors {
  if (!isRecord(details)) return {};
  const source = isRecord(details.error) && isRecord(details.error.field_errors)
    ? details.error.field_errors
    : details;
  return Object.fromEntries(
    Object.entries(source)
      .map(([field, value]) => [field, asStringError(value)] as const)
      .filter((entry): entry is readonly [string, string] => entry[1] !== undefined),
  );
}

async function translate<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (failure) {
    if (!(failure instanceof ApiError)) throw failure;
    throw new AssetManagementApiError(
      failure.message,
      failure.status,
      failure.code ?? 'REQUEST_FAILED',
      failure.correlationId ?? null,
      extractFieldErrors(failure.details),
    );
  }
}

function malformed(message: string): never {
  throw new AssetManagementApiError(message, 502, 'MALFORMED_RESPONSE', null);
}

function isAsset(value: unknown): value is Asset {
  if (!isRecord(value)) return false;
  const stringFields = [
    'id',
    'tenant_id',
    'asset_code',
    'asset_name',
    'purchase_date',
    'purchase_cost',
    'residual_value',
    'current_value',
    'location',
    'created_at',
    'updated_at',
  ] as const;
  return stringFields.every((field) => typeof value[field] === 'string')
    && ['fixed', 'intangible', 'current'].includes(String(value.category))
    && ['straight_line', 'declining_balance', 'none'].includes(String(value.depreciation_method))
    && (typeof value.useful_life_years === 'number' || value.useful_life_years === null)
    && (typeof value.declining_balance_rate === 'string' || value.declining_balance_rate === null)
    && typeof value.is_active === 'boolean';
}

function isDepreciationEntry(value: unknown): value is DepreciationEntry {
  if (!isRecord(value)) return false;
  return typeof value.id === 'string'
    && typeof value.tenant_id === 'string'
    && typeof value.asset === 'string'
    && typeof value.asset_code === 'string'
    && typeof value.asset_name === 'string'
    && typeof value.entry_date === 'string'
    && typeof value.depreciation_amount === 'string'
    && typeof value.accumulated_depreciation === 'string'
    && typeof value.book_value === 'string'
    && typeof value.created_at === 'string';
}

function unwrapDetail<T>(response: unknown, guard: (value: unknown) => value is T): T {
  if (guard(response)) return response;
  if (isRecord(response) && guard(response.data)) return response.data;
  return malformed('The server returned an invalid asset-management detail response.');
}

function unwrapList<T>(response: unknown, guard: (value: unknown) => value is T): ListResult<T> {
  const source = isRecord(response) && 'data' in response ? response.data : response;
  if (Array.isArray(source)) {
    if (!source.every(guard)) return malformed('The server returned invalid records in a list response.');
    return { items: source, count: source.length, next: null, previous: null };
  }

  if (!isRecord(source) || !Array.isArray(source.results)) {
    return malformed('The server returned an invalid paginated asset-management response.');
  }
  if (typeof source.count !== 'number'
    || !(source.next === null || typeof source.next === 'string')
    || !(source.previous === null || typeof source.previous === 'string')
    || !source.results.every(guard)) {
    return malformed('The server returned malformed asset-management pagination data.');
  }
  return {
    items: source.results,
    count: source.count,
    next: source.next,
    previous: source.previous,
  };
}

function withQuery(path: string, filters: object): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export const assetQueryKeys = {
  root: (tenantId: string | null) => ['asset-management', tenantId ?? 'no-tenant'] as const,
  assets: (tenantId: string | null, filters: AssetFilters = {}) =>
    [...assetQueryKeys.root(tenantId), 'assets', filters] as const,
  asset: (tenantId: string | null, id: string) =>
    [...assetQueryKeys.root(tenantId), 'asset', id] as const,
  depreciation: (tenantId: string | null, filters: DepreciationFilters = {}) =>
    [...assetQueryKeys.root(tenantId), 'depreciation', filters] as const,
};

export const assetService = {
  listAssets: async (filters: AssetFilters = {}): Promise<ListResult<Asset>> => {
    const response = await translate(apiClient.get<PaginatedResponse<Asset> | Asset[] | ApiEnvelope<PaginatedResponse<Asset>>>(
      withQuery(ENDPOINTS.ASSETS.LIST, filters),
    ));
    return unwrapList(response, isAsset);
  },

  getAsset: async (id: string): Promise<Asset> => {
    const response = await translate(apiClient.get<Asset | ApiEnvelope<Asset>>(
      ENDPOINTS.ASSETS.DETAIL(id),
    ));
    return unwrapDetail(response, isAsset);
  },

  createAsset: async (data: AssetCreate): Promise<Asset> => {
    const response = await translate(apiClient.post<Asset | ApiEnvelope<Asset>>(
      ENDPOINTS.ASSETS.CREATE,
      data,
    ));
    return unwrapDetail(response, isAsset);
  },

  updateAsset: async (id: string, data: AssetUpdate): Promise<Asset> => {
    const response = await translate(apiClient.patch<Asset | ApiEnvelope<Asset>>(
      ENDPOINTS.ASSETS.UPDATE(id),
      data,
    ));
    return unwrapDetail(response, isAsset);
  },

  deleteAsset: async (id: string): Promise<void> =>
    translate(apiClient.delete<void>(ENDPOINTS.ASSETS.DELETE(id))),

  listDepreciationEntries: async (
    filters: DepreciationFilters = {},
  ): Promise<ListResult<DepreciationEntry>> => {
    const response = await translate(apiClient.get<
      PaginatedResponse<DepreciationEntry> | DepreciationEntry[] | ApiEnvelope<PaginatedResponse<DepreciationEntry>>
    >(withQuery(ENDPOINTS.DEPRECIATION_ENTRIES.LIST, filters)));
    return unwrapList(response, isDepreciationEntry);
  },

  calculateDepreciation: async (
    id: string,
    data: CalculateDepreciationRequest,
  ): Promise<DepreciationEntry> => {
    const response = await translate(apiClient.post<DepreciationEntry | ApiEnvelope<DepreciationEntry>>(
      ENDPOINTS.ASSETS.CALCULATE_DEPRECIATION(id),
      data,
    ));
    return unwrapDetail(response, isDepreciationEntry);
  },
};
