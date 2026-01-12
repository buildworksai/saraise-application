/**
 * ProcessMining Service
 * 
 * Service client for ProcessMining module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';

// import type {
//   ProcessMiningResource,
//   ProcessMiningResourceCreate,
//   ProcessMiningResourceUpdate,
// } from '../contracts';

export const process_miningService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<ProcessMiningResource[]> => {
    return apiClient.get<ProcessMiningResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<ProcessMiningResource> => {
    return apiClient.get<ProcessMiningResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: ProcessMiningResourceCreate): Promise<ProcessMiningResource> => {
    return apiClient.post<ProcessMiningResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: ProcessMiningResourceUpdate): Promise<ProcessMiningResource> => {
    return apiClient.put<ProcessMiningResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
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
  activateResource: async (id: string): Promise<ProcessMiningResource> => {
    return apiClient.post<ProcessMiningResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<ProcessMiningResource> => {
    return apiClient.post<ProcessMiningResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
