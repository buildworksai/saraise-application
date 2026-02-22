/**
 * Master Data Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Master Data Management are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Master Data Entity - Generic master data container */
export type MasterDataEntity = {
  id: string;
  tenant_id: string;
  entity_type: string;
  entity_code: string;
  entity_name: string;
  data: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Master Data Entity create request */
export type MasterDataEntityCreate = {
  entity_type: string;
  entity_code: string;
  entity_name: string;
  data?: Record<string, unknown>;
  is_active?: boolean;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/master-data-management';

export const ENDPOINTS = {
  ENTITIES: {
    LIST: `${MODULE_API_PREFIX}/entities/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/entities/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/entities/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/entities/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/entities/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
