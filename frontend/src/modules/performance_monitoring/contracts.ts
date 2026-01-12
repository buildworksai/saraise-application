/**
 * PerformanceMonitoring Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules) *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for PerformanceMonitoring are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** PerformanceMonitoring resource entity */
export type PerformanceMonitoringResource = {
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

/** PerformanceMonitoring resource create request */
export type PerformanceMonitoringResourceCreate = {
  name: string;
  description?: string;
  is_active?: boolean;
  config?: Record<string, unknown>;
};

/** PerformanceMonitoring resource update request (partial) */
export type PerformanceMonitoringResourceUpdate = Partial<PerformanceMonitoringResourceCreate>;

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * PerformanceMonitoring API Endpoints
 * * All endpoints should be prefixed with /api/v1/performance-monitoring/
 */
export const MODULE_API_PREFIX = '/api/v1/performance-monitoring';

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
