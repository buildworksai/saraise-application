/**
 * Data Migration Service
 * 
 * Service client for Data Migration module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, MigrationJob, MigrationJobCreate, MigrationJobUpdate } from '../contracts';

export const migrationService = {
  jobs: {
    /**
     * List all migration jobs
     */
    list: async (): Promise<MigrationJob[]> => {
      return apiClient.get<MigrationJob[]>(ENDPOINTS.JOBS.LIST);
    },

    /**
     * Get migration job by ID
     */
    get: async (id: string): Promise<MigrationJob> => {
      return apiClient.get<MigrationJob>(ENDPOINTS.JOBS.DETAIL(id));
    },

    /**
     * Create new migration job
     */
    create: async (data: MigrationJobCreate): Promise<MigrationJob> => {
      return apiClient.post<MigrationJob>(ENDPOINTS.JOBS.CREATE, data);
    },

    /**
     * Update migration job
     */
    update: async (id: string, data: MigrationJobUpdate): Promise<MigrationJob> => {
      return apiClient.put<MigrationJob>(ENDPOINTS.JOBS.UPDATE(id), data);
    },

    /**
     * Delete migration job
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.JOBS.DELETE(id));
    },

    /**
     * Execute migration job
     */
    execute: async (id: string): Promise<{ success: boolean; message: string }> => {
      return apiClient.post<{ success: boolean; message: string }>(
        ENDPOINTS.JOBS.EXECUTE(id)
      );
    },

    /**
     * Dry run migration job
     */
    dryRun: async (id: string): Promise<{ success: boolean; message: string }> => {
      return apiClient.post<{ success: boolean; message: string }>(
        ENDPOINTS.JOBS.DRY_RUN(id)
      );
    },
  },
};
