/**
 * Compliance Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Compliance Management are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Compliance Policy - Regulatory policy definition */
export type CompliancePolicy = {
  id: string;
  tenant_id: string;
  policy_code: string;
  policy_name: string;
  regulation_type: string;
  description?: string;
  effective_date: string;
  expiry_date?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Compliance Policy create request */
export type CompliancePolicyCreate = {
  policy_code: string;
  policy_name: string;
  regulation_type: string;
  description?: string;
  effective_date: string;
  expiry_date?: string;
  is_active?: boolean;
};

/** Compliance Requirement - Specific compliance requirement */
export type ComplianceRequirement = {
  id: string;
  tenant_id: string;
  policy: string;
  requirement_code: string;
  requirement_name: string;
  description?: string;
  status: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/compliance-management';

export const ENDPOINTS = {
  POLICIES: {
    LIST: `${MODULE_API_PREFIX}/policies/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/policies/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/policies/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/policies/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/policies/${id}/` as const,
  },
  REQUIREMENTS: {
    LIST: `${MODULE_API_PREFIX}/requirements/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/requirements/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/requirements/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/requirements/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/requirements/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
