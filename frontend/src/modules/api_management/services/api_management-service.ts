/**
 * ApiManagement Service
 * 
 * Service client for ApiManagement module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type ApiManagementResource, type ApiManagementResourceCreate, type ApiManagementResourceUpdate } from '../contracts';

export const api_managementService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<ApiManagementResource[]> => {
    return apiClient.get<ApiManagementResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<ApiManagementResource> => {
    return apiClient.get<ApiManagementResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: ApiManagementResourceCreate): Promise<ApiManagementResource> => {
    return apiClient.post<ApiManagementResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: ApiManagementResourceUpdate): Promise<ApiManagementResource> => {
    return apiClient.put<ApiManagementResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
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
  activateResource: async (id: string): Promise<ApiManagementResource> => {
    return apiClient.post<ApiManagementResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<ApiManagementResource> => {
    return apiClient.post<ApiManagementResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
