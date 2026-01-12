/**
 * DocumentIntelligence Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules) *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for DocumentIntelligence are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** DocumentIntelligence resource entity */
export type DocumentIntelligenceResource = {
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

/** DocumentIntelligence resource create request */
export type DocumentIntelligenceResourceCreate = {
  name: string;
  description?: string;
  is_active?: boolean;
  config?: Record<string, unknown>;
};

/** DocumentIntelligence resource update request (partial) */
export type DocumentIntelligenceResourceUpdate = Partial<DocumentIntelligenceResourceCreate>;

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * DocumentIntelligence API Endpoints
 * * All endpoints should be prefixed with /api/v1/document-intelligence/
 */
export const MODULE_API_PREFIX = '/api/v1/document-intelligence';

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
