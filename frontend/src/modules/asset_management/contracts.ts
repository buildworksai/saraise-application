/**
 * Asset Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Asset Management are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Asset - Fixed or intangible asset */
export type Asset = {
  id: string;
  tenant_id: string;
  asset_code: string;
  asset_name: string;
  category: 'fixed' | 'intangible' | 'current';
  purchase_date: string;
  purchase_cost: string;
  current_value: string;
  depreciation_method: string;
  useful_life_years?: number;
  location?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Asset create request */
export type AssetCreate = {
  asset_code: string;
  asset_name: string;
  category: 'fixed' | 'intangible' | 'current';
  purchase_date: string;
  purchase_cost: string;
  current_value: string;
  depreciation_method: string;
  useful_life_years?: number;
  location?: string;
  is_active?: boolean;
};

/** Depreciation Entry - Monthly/Annual depreciation record */
export type DepreciationEntry = {
  id: string;
  tenant_id: string;
  asset: string;
  entry_date: string;
  depreciation_amount: string;
  accumulated_depreciation: string;
  book_value: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/asset-management';

export const ENDPOINTS = {
  ASSETS: {
    LIST: `${MODULE_API_PREFIX}/assets/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/assets/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
  },
  DEPRECIATION_ENTRIES: {
    LIST: `${MODULE_API_PREFIX}/depreciation-entries/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/depreciation-entries/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/depreciation-entries/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/depreciation-entries/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/depreciation-entries/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
