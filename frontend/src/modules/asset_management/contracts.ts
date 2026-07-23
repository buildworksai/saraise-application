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
}

export type AssetUpdate = Partial<AssetCreate>;

export interface DepreciationEntry {
  id: string;
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

export interface AssetConfigurationDocument {
  environment: 'default' | 'development' | 'self-hosted' | 'saas';
  enabled: boolean;
  rollout_roles: string[];
  rollout_cohorts: string[];
  asset_code_max_length: number;
  asset_name_max_length: number;
  location_max_length: number;
  monetary_max_digits: number;
  monetary_decimal_places: number;
  minimum_purchase_cost: string;
  default_residual_value: string;
  default_current_value: string;
  new_asset_active_default: boolean;
  allowed_categories: AssetCategory[];
  default_category: AssetCategory;
  allowed_depreciation_methods: DepreciationMethod[];
  default_depreciation_method: DepreciationMethod;
  non_depreciable_categories: AssetCategory[];
  useful_life_min_years: number;
  useful_life_max_years: number;
  default_useful_life_years: number;
  declining_rate_min: string;
  declining_rate_max: string;
  percentage_divisor: string;
  double_declining_factor: string;
  annual_cap: string;
  accounting_periods_per_year: number;
  posting_frequency: 'monthly' | 'exact_date';
  require_chronological_depreciation: boolean;
  require_useful_life_for_depreciation: boolean;
  declining_rate_requires_declining_method: boolean;
  inactive_assets_depreciable: boolean;
  allow_depreciation_before_purchase: boolean;
  lock_financial_fields_after_history: boolean;
  archive_sets_inactive: boolean;
  archive_confirmation: 'asset_code' | 'asset_name';
  asset_list_page_size: number;
  asset_list_max_page_size: number;
  asset_list_default_ordering: string;
  asset_detail_history_page_size: number;
  asset_search_fields: string[];
  asset_ordering_fields: string[];
  tenant_throttle_rate: string;
  health_interval_seconds: number;
}

export interface AssetConfiguration {
  id: string;
  version: number;
  document: AssetConfigurationDocument;
  limits: Record<string, [number | string, number | string]>;
  updated_at: string;
}

export interface AssetConfigurationVersion {
  id: string;
  version: number;
  document: AssetConfigurationDocument;
  source: string;
  correlation_id: string;
  created_at: string;
}

export interface AssetConfigurationExport {
  schema_version: '1.0';
  module: 'asset_management';
  version: number;
  document: AssetConfigurationDocument;
}

export interface AssetConfigurationPreview {
  valid: true;
  current_version: number;
  changes: Record<string, { from: unknown; to: unknown }>;
  document: AssetConfigurationDocument;
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
    CONFIGURATION: '/asset-management/configuration',
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
  CONFIGURATION: {
    CURRENT: `${MODULE_API_PREFIX}/configuration/`,
    UPDATE: `${MODULE_API_PREFIX}/configuration/update/`,
    PREVIEW: `${MODULE_API_PREFIX}/configuration/preview/`,
    HISTORY: `${MODULE_API_PREFIX}/configuration/history/`,
    ROLLBACK: `${MODULE_API_PREFIX}/configuration/rollback/`,
    IMPORT: `${MODULE_API_PREFIX}/configuration/import/`,
    EXPORT: `${MODULE_API_PREFIX}/configuration/export/`,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
