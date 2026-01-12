/**
 * AutomationOrchestration Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules) *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for AutomationOrchestration are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** AutomationOrchestration resource entity */
export type AutomationOrchestrationResource = {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  is_active: boolean;
  config: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
};

/** AutomationOrchestration resource create request */
export type AutomationOrchestrationResourceCreate = {
  name: string;
  description?: string;
  is_active?: boolean;
  config?: Record<string, unknown>;
};

/** AutomationOrchestration resource update request (partial) */
export type AutomationOrchestrationResourceUpdate = Partial<AutomationOrchestrationResourceCreate>;

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * AutomationOrchestration API Endpoints
 * * All endpoints should be prefixed with /api/v1/automation-orchestration/
 */
export const MODULE_API_PREFIX = '/api/v1/automation-orchestration';

export const ENDPOINTS = {
  RESOURCES: {
    LIST: `${MODULE_API_PREFIX}/resources/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/resources/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/` as const,
    ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/activate/` as const,
    DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/deactivate/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
