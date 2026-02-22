/**
 * Multi-Company Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Multi-Company are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Company - Company within a tenant */
export type Company = {
  id: string;
  tenant_id: string;
  company_code: string;
  company_name: string;
  legal_name?: string;
  tax_id?: string;
  address?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Company create request */
export type CompanyCreate = {
  company_code: string;
  company_name: string;
  legal_name?: string;
  tax_id?: string;
  address?: string;
  is_active?: boolean;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/multi-company';

export const ENDPOINTS = {
  COMPANIES: {
    LIST: `${MODULE_API_PREFIX}/companies/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/companies/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/companies/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/companies/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/companies/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
