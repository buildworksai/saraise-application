/**
 * Business Intelligence Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Business Intelligence are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Report - BI report definition */
export type Report = {
  id: string;
  tenant_id: string;
  report_code: string;
  report_name: string;
  report_type: string;
  query: string;
  parameters: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Report create request */
export type ReportCreate = {
  report_code: string;
  report_name: string;
  report_type: string;
  query: string;
  parameters?: Record<string, unknown>;
  is_active?: boolean;
};

/** Dashboard - BI dashboard configuration */
export type Dashboard = {
  id: string;
  tenant_id: string;
  dashboard_code: string;
  dashboard_name: string;
  layout: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/business-intelligence';

export const ENDPOINTS = {
  REPORTS: {
    LIST: `${MODULE_API_PREFIX}/reports/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/reports/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/` as const,
  },
  DASHBOARDS: {
    LIST: `${MODULE_API_PREFIX}/dashboards/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/dashboards/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
