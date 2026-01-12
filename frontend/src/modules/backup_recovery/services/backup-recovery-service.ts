/**
 * Backup & Recovery (Extended) Service
 * 
 * Service client for Backup & Recovery module API calls.
 * 
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */

import { apiClient } from '@/services/api-client';
import type {
  BackupJob,
  BackupJobCreate,
  BackupSchedule,
  BackupScheduleCreate,
  BackupRetentionPolicy,
  BackupRetentionPolicyCreate,
  BackupArchive,
} from '../contracts';
import { ENDPOINTS } from '../contracts';

// Re-export types for use in components
export type {
  BackupJob,
  BackupJobCreate,
  BackupSchedule,
  BackupScheduleCreate,
  BackupRetentionPolicy,
  BackupRetentionPolicyCreate,
  BackupArchive,
};

export const backupRecoveryService = {
  /**
   * List all backup jobs
   */
  listBackupJobs: async (): Promise<BackupJob[]> => {
    return apiClient.get<BackupJob[]>(ENDPOINTS.JOBS.LIST);
  },

  /**
   * Get backup job by ID
   */
  getBackupJob: async (id: string): Promise<BackupJob> => {
    return apiClient.get<BackupJob>(ENDPOINTS.JOBS.DETAIL(id));
  },

  /**
   * Create new backup job
   */
  createBackupJob: async (data: BackupJobCreate): Promise<BackupJob> => {
    return apiClient.post<BackupJob>(ENDPOINTS.JOBS.CREATE, data);
  },

  /**
   * Update backup job
   */
  updateBackupJob: async (id: string, data: Partial<BackupJobCreate>): Promise<BackupJob> => {
    return apiClient.patch<BackupJob>(ENDPOINTS.JOBS.UPDATE(id), data);
  },

  /**
   * Delete backup job
   */
  deleteBackupJob: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.JOBS.DELETE(id));
  },

  /**
   * Start backup job
   */
  startBackupJob: async (id: string): Promise<BackupJob> => {
    return apiClient.post<BackupJob>(ENDPOINTS.JOBS.START(id), {});
  },

  /**
   * Complete backup job
   */
  completeBackupJob: async (
    id: string,
    backupSizeBytes?: number,
    storageLocation?: string
  ): Promise<BackupJob> => {
    return apiClient.post<BackupJob>(ENDPOINTS.JOBS.COMPLETE(id), {
      backup_size_bytes: backupSizeBytes,
      storage_location: storageLocation,
    });
  },

  /**
   * Fail backup job
   */
  failBackupJob: async (id: string, errorMessage?: string): Promise<BackupJob> => {
    return apiClient.post<BackupJob>(ENDPOINTS.JOBS.FAIL(id), {
      error_message: errorMessage,
    });
  },

  /**
   * List all backup schedules
   */
  listBackupSchedules: async (): Promise<BackupSchedule[]> => {
    return apiClient.get<BackupSchedule[]>(ENDPOINTS.SCHEDULES.LIST);
  },

  /**
   * Get backup schedule by ID
   */
  getBackupSchedule: async (id: string): Promise<BackupSchedule> => {
    return apiClient.get<BackupSchedule>(ENDPOINTS.SCHEDULES.DETAIL(id));
  },

  /**
   * Create new backup schedule
   */
  createBackupSchedule: async (data: BackupScheduleCreate): Promise<BackupSchedule> => {
    return apiClient.post<BackupSchedule>(ENDPOINTS.SCHEDULES.CREATE, data);
  },

  /**
   * Update backup schedule
   */
  updateBackupSchedule: async (
    id: string,
    data: Partial<BackupScheduleCreate>
  ): Promise<BackupSchedule> => {
    return apiClient.patch<BackupSchedule>(ENDPOINTS.SCHEDULES.UPDATE(id), data);
  },

  /**
   * Delete backup schedule
   */
  deleteBackupSchedule: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.SCHEDULES.DELETE(id));
  },

  /**
   * Activate backup schedule
   */
  activateBackupSchedule: async (id: string): Promise<BackupSchedule> => {
    return apiClient.post<BackupSchedule>(ENDPOINTS.SCHEDULES.ACTIVATE(id), {});
  },

  /**
   * Deactivate backup schedule
   */
  deactivateBackupSchedule: async (id: string): Promise<BackupSchedule> => {
    return apiClient.post<BackupSchedule>(ENDPOINTS.SCHEDULES.DEACTIVATE(id), {});
  },

  /**
   * List all retention policies
   */
  listRetentionPolicies: async (): Promise<BackupRetentionPolicy[]> => {
    return apiClient.get<BackupRetentionPolicy[]>(ENDPOINTS.RETENTION_POLICIES.LIST);
  },

  /**
   * Get retention policy by ID
   */
  getRetentionPolicy: async (id: string): Promise<BackupRetentionPolicy> => {
    return apiClient.get<BackupRetentionPolicy>(ENDPOINTS.RETENTION_POLICIES.DETAIL(id));
  },

  /**
   * Create new retention policy
   */
  createRetentionPolicy: async (
    data: BackupRetentionPolicyCreate
  ): Promise<BackupRetentionPolicy> => {
    return apiClient.post<BackupRetentionPolicy>(ENDPOINTS.RETENTION_POLICIES.CREATE, data);
  },

  /**
   * Update retention policy
   */
  updateRetentionPolicy: async (
    id: string,
    data: Partial<BackupRetentionPolicyCreate>
  ): Promise<BackupRetentionPolicy> => {
    return apiClient.patch<BackupRetentionPolicy>(ENDPOINTS.RETENTION_POLICIES.UPDATE(id), data);
  },

  /**
   * Delete retention policy
   */
  deleteRetentionPolicy: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.RETENTION_POLICIES.DELETE(id));
  },

  /**
   * List all backup archives
   */
  listBackupArchives: async (): Promise<BackupArchive[]> => {
    return apiClient.get<BackupArchive[]>(ENDPOINTS.ARCHIVES.LIST);
  },

  /**
   * Get backup archive by ID
   */
  getBackupArchive: async (id: string): Promise<BackupArchive> => {
    return apiClient.get<BackupArchive>(ENDPOINTS.ARCHIVES.DETAIL(id));
  },
};
