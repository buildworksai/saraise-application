/**
 * Public frontend contract for the Asset Management runtime module.
 *
 * Tenant identity and calculated balances are server-owned. Depreciation
 * history is append-only and can only be extended through the asset command.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

export type AssetCategory = 'fixed' | 'intangible' | 'current';
export type DepreciationMethod = 'straight_line' | 'declining_balance' | 'none';

export interface Asset {
  id: string;
  tenant_id: string;
  asset_code: string;
  asset_name: string;
  category: AssetCategory;
  purchase_date: string;
  purchase_cost: string;
  residual_value: string;
  current_value: string;
  depreciation_method: DepreciationMethod;
  useful_life_years: number | null;
  declining_balance_rate: string | null;
  location: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AssetCreate {
  asset_code: string;
  asset_name: string;
  category: AssetCategory;
  purchase_date: string;
  purchase_cost: string;
  residual_value: string;
  depreciation_method: DepreciationMethod;
  useful_life_years: number | null;
  declining_balance_rate: string | null;
  location: string;
  is_active: boolean;
}

export type AssetUpdate = Partial<AssetCreate>;

export interface DepreciationEntry {
  id: string;
  tenant_id: string;
  asset: string;
  asset_code: string;
  asset_name: string;
  entry_date: string;
  depreciation_amount: string;
  accumulated_depreciation: string;
  book_value: string;
  created_at: string;
}

export interface CalculateDepreciationRequest {
  entry_date: string;
}

export interface AssetFilters {
  search?: string;
  category?: AssetCategory;
  is_active?: boolean;
  purchase_date_after?: string;
  purchase_date_before?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export interface DepreciationFilters {
  asset_id?: string;
  entry_date_after?: string;
  entry_date_before?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

/** Normalized list shape returned by the module service. */
export interface ListResult<T> {
  items: readonly T[];
  count: number;
  next: string | null;
  previous: string | null;
}

/** DRF pagination shape accepted at the HTTP boundary. */
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiEnvelope<T> {
  data: T;
  meta?: {
    correlation_id?: string;
  };
}

export const MODULE_API_PREFIX = '/api/v1/asset-management';

/** Browser paths are owned beside the API contract to prevent route drift. */
export const ROUTES = {
  ASSETS: {
    LIST: '/asset-management/assets',
    CREATE: '/asset-management/assets/new',
    DETAIL_PATTERN: '/asset-management/assets/:id',
    EDIT_PATTERN: '/asset-management/assets/:id/edit',
    DETAIL: (id: string) => `/asset-management/assets/${id}` as const,
    EDIT: (id: string) => `/asset-management/assets/${id}/edit` as const,
  },
} as const;

export const ENDPOINTS = {
  ASSETS: {
    LIST: `${MODULE_API_PREFIX}/assets/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/assets/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
    CALCULATE_DEPRECIATION: (id: string) =>
      `${MODULE_API_PREFIX}/assets/${id}/calculate-depreciation/` as const,
  },
  DEPRECIATION_ENTRIES: {
    LIST: `${MODULE_API_PREFIX}/depreciation-entries/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/depreciation-entries/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
