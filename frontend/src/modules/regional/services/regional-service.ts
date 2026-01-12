/**
 * Regional Service
 * 
 * Service client for Regional module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import type {
  RegionalResource,
  RegionalResourceCreate,
  RegionalResourceUpdate,
} from '../contracts';
import type {
  RegionalResource,
  RegionalResourceCreate,
  RegionalResourceUpdate,
} from '../contracts';

import type {
  RegionalResource,
  RegionalResourceCreate,
  RegionalResourceUpdate,
} from '../contracts';

export const regionalService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<RegionalResource[]> => {
    return apiClient.get<RegionalResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<RegionalResource> => {
    return apiClient.get<RegionalResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: RegionalResourceCreate): Promise<RegionalResource> => {
    return apiClient.post<RegionalResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: RegionalResourceUpdate): Promise<RegionalResource> => {
    return apiClient.put<RegionalResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
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
  activateResource: async (id: string): Promise<RegionalResource> => {
    return apiClient.post<RegionalResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<RegionalResource> => {
    return apiClient.post<RegionalResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
