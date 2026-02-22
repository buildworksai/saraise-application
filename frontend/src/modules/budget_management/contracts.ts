/**
 * Budget Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Budget Management are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Budget - Budget container for a period */
export type Budget = {
  id: string;
  tenant_id: string;
  budget_code: string;
  budget_name: string;
  fiscal_year: number;
  start_date: string;
  end_date: string;
  status: string;
  currency: string;
  total_budget: string;
  created_at: string;
  updated_at: string;
};

/** Budget create request */
export type BudgetCreate = {
  budget_code: string;
  budget_name: string;
  fiscal_year: number;
  start_date: string;
  end_date: string;
  status: string;
  currency: string;
  total_budget: string;
};

/** Budget Line - Individual account budget allocation */
export type BudgetLine = {
  id: string;
  tenant_id: string;
  budget: string;
  account_id: string;
  account_code: string;
  budget_amount: string;
  actual_amount: string;
  variance: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/budget-management';

export const ENDPOINTS = {
  BUDGETS: {
    LIST: `${MODULE_API_PREFIX}/budgets/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/budgets/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/budgets/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/budgets/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/budgets/${id}/` as const,
  },
  BUDGET_LINES: {
    LIST: `${MODULE_API_PREFIX}/budget-lines/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/budget-lines/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/budget-lines/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/budget-lines/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/budget-lines/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
