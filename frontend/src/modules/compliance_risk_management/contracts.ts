/**
 * Compliance Risk Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Compliance Risk Management are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Compliance Risk - Risk assessment record */
export type ComplianceRisk = {
  id: string;
  tenant_id: string;
  risk_code: string;
  risk_name: string;
  description?: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  status: string;
  mitigation_plan?: string;
  created_at: string;
  updated_at: string;
};

/** Compliance Risk create request */
export type ComplianceRiskCreate = {
  risk_code: string;
  risk_name: string;
  description?: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  status: string;
  mitigation_plan?: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/compliance-risk-management';

export const ENDPOINTS = {
  RISKS: {
    LIST: `${MODULE_API_PREFIX}/risks/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/risks/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/risks/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/risks/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/risks/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
