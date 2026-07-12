/**
 * MetadataModeling Service
 * 
 * Service client for MetadataModeling module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { METADATA_ENDPOINTS } from '../contracts';
import type { DynamicResource } from '../contracts';

export const metadata_modelingService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<DynamicResource[]> => {
    return apiClient.get<DynamicResource[]>(METADATA_ENDPOINTS.RESOURCES);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<DynamicResource> => {
    return apiClient.get<DynamicResource>(`${METADATA_ENDPOINTS.RESOURCES}${id}/`);
  },

  /**
   * Create new resource
   */
  createResource: async (data: Record<string, unknown>): Promise<DynamicResource> => {
    return apiClient.post<DynamicResource>(METADATA_ENDPOINTS.RESOURCES, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: Record<string, unknown>): Promise<DynamicResource> => {
    return apiClient.put<DynamicResource>(`${METADATA_ENDPOINTS.RESOURCES}${id}/`, data);
  },

  /**
   * Delete resource
   */
  deleteResource: async (id: string): Promise<void> => {
    return apiClient.delete(`${METADATA_ENDPOINTS.RESOURCES}${id}/`);
  },
};
