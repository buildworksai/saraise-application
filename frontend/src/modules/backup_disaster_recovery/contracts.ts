/**
 * BackupDisasterRecovery Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules) *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for BackupDisasterRecovery are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** BackupDisasterRecovery resource entity */
export type BackupDisasterRecoveryResource = {
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

/** BackupDisasterRecovery resource create request */
export type BackupDisasterRecoveryResourceCreate = {
  name: string;
  description?: string;
  is_active?: boolean;
  config?: Record<string, unknown>;
};

/** BackupDisasterRecovery resource update request (partial) */
export type BackupDisasterRecoveryResourceUpdate = Partial<BackupDisasterRecoveryResourceCreate>;

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * BackupDisasterRecovery API Endpoints
 * * All endpoints should be prefixed with /api/v1/backup-disaster-recovery/
 */
export const MODULE_API_PREFIX = '/api/v1/backup-disaster-recovery';

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
