/**
 * MetadataModeling Service
 * 
 * Service client for MetadataModeling module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { METADATA_ENDPOINTS, DynamicResource } from '../contracts';

export type DynamicResourceCreate = {
  entity_definition: string;
  data: Record<string, any>;
};

export type DynamicResourceUpdate = Partial<DynamicResourceCreate>;

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
  createResource: async (data: DynamicResourceCreate): Promise<DynamicResource> => {
    return apiClient.post<DynamicResource>(METADATA_ENDPOINTS.RESOURCES, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: DynamicResourceUpdate): Promise<DynamicResource> => {
    return apiClient.put<DynamicResource>(`${METADATA_ENDPOINTS.RESOURCES}${id}/`, data);
  },

  /**
   * Delete resource
   */
  deleteResource: async (id: string): Promise<void> => {
    return apiClient.delete(`${METADATA_ENDPOINTS.RESOURCES}${id}/`);
  },
};
