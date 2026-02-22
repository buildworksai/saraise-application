/**
 * Fixed Assets Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Fixed Assets are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Fixed Asset - Fixed asset record */
export type FixedAsset = {
  id: string;
  tenant_id: string;
  asset_code: string;
  asset_name: string;
  asset_category: string;
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

/** Fixed Asset create request */
export type FixedAssetCreate = {
  asset_code: string;
  asset_name: string;
  asset_category: string;
  purchase_date: string;
  purchase_cost: string;
  current_value: string;
  depreciation_method: string;
  useful_life_years?: number;
  location?: string;
  is_active?: boolean;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/fixed-assets';

export const ENDPOINTS = {
  ASSETS: {
    LIST: `${MODULE_API_PREFIX}/assets/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/assets/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
