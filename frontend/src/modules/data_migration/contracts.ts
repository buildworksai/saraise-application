/**
 * DataMigration Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for DataMigration are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** MigrationJob entity */
export type MigrationJob = {
  id: string;
  tenant_id: string;
  name: string;
  source_type: 'csv' | 'excel' | 'json' | 'database' | 'api';
  source_config: Record<string, unknown>;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  started_at?: string;
  completed_at?: string;
  records_processed: number;
  records_failed: number;
  records_total: number;
  error_message?: string;
  mappings_count?: number;
  logs_count?: number;
  validations_count?: number;
  progress_percentage?: number;
  created_by: string;
  created_at: string;
  updated_at: string;
};

/** MigrationJob create request */
export type MigrationJobCreate = {
  name: string;
  source_type: 'csv' | 'excel' | 'json' | 'database' | 'api';
  source_config: Record<string, unknown>;
};

/** MigrationJob update request (partial) */
export type MigrationJobUpdate = Partial<MigrationJobCreate>;

/** MigrationMapping entity */
export type MigrationMapping = {
  id: string;
  tenant_id: string;
  job: string;
  job_id?: string;
  source_field: string;
  target_field: string;
  transform: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

/** MigrationMapping create request */
export type MigrationMappingCreate = {
  job: string;
  source_field: string;
  target_field: string;
  transform?: Record<string, unknown>;
};

/** MigrationMapping update request (partial) */
export type MigrationMappingUpdate = Partial<MigrationMappingCreate>;

/** MigrationLog entity */
export type MigrationLog = {
  id: string;
  tenant_id: string;
  job: string;
  job_id?: string;
  level: 'debug' | 'info' | 'warning' | 'error';
  message: string;
  timestamp: string;
  created_at: string;
  updated_at: string;
};

/** MigrationValidation entity */
export type MigrationValidation = {
  id: string;
  tenant_id: string;
  job: string;
  job_id?: string;
  field: string;
  rule: string;
  status: 'passed' | 'failed' | 'warning';
  message?: string;
  record_index?: number;
  created_at: string;
  updated_at: string;
};

/** MigrationRollback entity */
export type MigrationRollback = {
  id: string;
  tenant_id: string;
  job: string;
  job_id?: string;
  checkpoint_data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * DataMigration API Endpoints
 *
 * All endpoints should be prefixed with /api/v1/data-migration/
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS } from './contracts';
 * apiClient.get(ENDPOINTS.JOBS.LIST);
 * apiClient.post(ENDPOINTS.JOBS.EXECUTE(id));
 * ```
 */
export const MODULE_API_PREFIX = '/api/v1/data-migration';

export const ENDPOINTS = {
  JOBS: {
    LIST: `${MODULE_API_PREFIX}/jobs/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/jobs/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/` as const,
    EXECUTE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/execute/` as const,
    DRY_RUN: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/dry-run/` as const,
  },
  MAPPINGS: {
    LIST: `${MODULE_API_PREFIX}/mappings/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/mappings/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/mappings/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/mappings/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/mappings/${id}/` as const,
  },
  LOGS: {
    LIST: `${MODULE_API_PREFIX}/logs/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/logs/${id}/` as const,
  },
  VALIDATIONS: {
    LIST: `${MODULE_API_PREFIX}/validations/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/validations/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
