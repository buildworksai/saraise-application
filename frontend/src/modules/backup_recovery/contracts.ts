/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Backup & Recovery (Extended) Module Contracts
 *
 * Defines all types and API endpoints for the Backup & Recovery module.
 *
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */

// ==========================================
// Types
// ==========================================

export type BackupJobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export type BackupType = "full" | "incremental" | "differential";
export type BackupFrequency = "hourly" | "daily" | "weekly" | "monthly";

export interface BackupJob {
  id: string;
  tenant_id: string;
  backup_type: BackupType;
  status: BackupJobStatus;
  start_time?: string | null;
  end_time?: string | null;
  backup_size_bytes?: number | null;
  storage_location: string;
  description: string;
  error_message: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface BackupJobCreate {
  backup_type: BackupType;
  description?: string;
}

export interface BackupSchedule {
  id: string;
  tenant_id: string;
  frequency: BackupFrequency;
  schedule_time?: string | null;
  retention_days: number;
  is_active: boolean;
  backup_type: BackupType;
  description: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface BackupScheduleCreate {
  frequency: BackupFrequency;
  schedule_time?: string | null;
  retention_days: number;
  backup_type?: BackupType;
  description?: string;
}

export interface BackupRetentionPolicy {
  id: string;
  tenant_id: string;
  policy_name: string;
  retention_days: number;
  archive_after_days: number;
  is_active: boolean;
  description: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface BackupRetentionPolicyCreate {
  policy_name: string;
  retention_days: number;
  archive_after_days: number;
  description?: string;
}

export interface BackupArchive {
  id: string;
  tenant_id: string;
  backup_job: BackupJob;
  archive_location: string;
  archived_at: string;
  archive_size_bytes?: number | null;
  description: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

// ==========================================
// Endpoints
// ==========================================

export const MODULE_API_PREFIX = "/api/v1/backup-recovery";

export const ENDPOINTS = {
  JOBS: {
    LIST: `${MODULE_API_PREFIX}/jobs/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/`,
    CREATE: `${MODULE_API_PREFIX}/jobs/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/`,
    START: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/start/`,
    COMPLETE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/complete/`,
    FAIL: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/fail/`,
  },
  SCHEDULES: {
    LIST: `${MODULE_API_PREFIX}/schedules/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/`,
    CREATE: `${MODULE_API_PREFIX}/schedules/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/`,
    ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/activate/`,
    DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/deactivate/`,
  },
  RETENTION_POLICIES: {
    LIST: `${MODULE_API_PREFIX}/retention-policies/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/retention-policies/${id}/`,
    CREATE: `${MODULE_API_PREFIX}/retention-policies/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/retention-policies/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/retention-policies/${id}/`,
  },
  ARCHIVES: {
    LIST: `${MODULE_API_PREFIX}/archives/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/archives/${id}/`,
  },
} as const;
