/**
 * CustomizationFramework Service
 * 
 * Service client for CustomizationFramework module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type CustomizationFrameworkResource, type CustomizationFrameworkResourceCreate, type CustomizationFrameworkResourceUpdate } from '../contracts';

export const customization_frameworkService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<CustomizationFrameworkResource[]> => {
    return apiClient.get<CustomizationFrameworkResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<CustomizationFrameworkResource> => {
    return apiClient.get<CustomizationFrameworkResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: CustomizationFrameworkResourceCreate): Promise<CustomizationFrameworkResource> => {
    return apiClient.post<CustomizationFrameworkResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: CustomizationFrameworkResourceUpdate): Promise<CustomizationFrameworkResource> => {
    return apiClient.put<CustomizationFrameworkResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
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
  activateResource: async (id: string): Promise<CustomizationFrameworkResource> => {
    return apiClient.post<CustomizationFrameworkResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<CustomizationFrameworkResource> => {
    return apiClient.post<CustomizationFrameworkResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
