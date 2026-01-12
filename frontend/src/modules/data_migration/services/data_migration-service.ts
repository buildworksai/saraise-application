/**
 * DataMigration Service
 * 
 * Service client for DataMigration module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type MigrationJob, type MigrationJobCreate, type MigrationJobUpdate } from '../contracts';

export const data_migrationService = {
  /**
   * List all migration jobs
   */
  listJobs: async (): Promise<MigrationJob[]> => {
    return apiClient.get<MigrationJob[]>(ENDPOINTS.JOBS.LIST);
  },

  /**
   * Get migration job by ID
   */
  getJob: async (id: string): Promise<MigrationJob> => {
    return apiClient.get<MigrationJob>(ENDPOINTS.JOBS.DETAIL(id));
  },

  /**
   * Create new migration job
   */
  createJob: async (data: MigrationJobCreate): Promise<MigrationJob> => {
    return apiClient.post<MigrationJob>(ENDPOINTS.JOBS.CREATE, data);
  },

  /**
   * Update migration job
   */
  updateJob: async (id: string, data: MigrationJobUpdate): Promise<MigrationJob> => {
    return apiClient.put<MigrationJob>(ENDPOINTS.JOBS.UPDATE(id), data);
  },

  /**
   * Delete migration job
   */
  deleteJob: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.JOBS.DELETE(id));
  },
};
