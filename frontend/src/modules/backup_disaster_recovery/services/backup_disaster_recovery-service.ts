/**
 * BackupDisasterRecovery Service
 * 
 * Service client for BackupDisasterRecovery module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type BackupDisasterRecoveryResource, type BackupDisasterRecoveryResourceCreate, type BackupDisasterRecoveryResourceUpdate } from '../contracts';

export const backup_disaster_recoveryService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<BackupDisasterRecoveryResource[]> => {
    return apiClient.get<BackupDisasterRecoveryResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<BackupDisasterRecoveryResource> => {
    return apiClient.get<BackupDisasterRecoveryResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: BackupDisasterRecoveryResourceCreate): Promise<BackupDisasterRecoveryResource> => {
    return apiClient.post<BackupDisasterRecoveryResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: BackupDisasterRecoveryResourceUpdate): Promise<BackupDisasterRecoveryResource> => {
    return apiClient.put<BackupDisasterRecoveryResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
  },

  /**
   * Delete resource
   */
  deleteResource: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.RESOURCES.DELETE(id));
  },

  /**
   * Activate resource
   */
  activateResource: async (id: string): Promise<BackupDisasterRecoveryResource> => {
    return apiClient.post<BackupDisasterRecoveryResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<BackupDisasterRecoveryResource> => {
    return apiClient.post<BackupDisasterRecoveryResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
