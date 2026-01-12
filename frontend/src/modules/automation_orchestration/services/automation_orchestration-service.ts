/**
 * AutomationOrchestration Service
 * 
 * Service client for AutomationOrchestration module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type AutomationOrchestrationResource, type AutomationOrchestrationResourceCreate, type AutomationOrchestrationResourceUpdate } from '../contracts';

export const automation_orchestrationService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<AutomationOrchestrationResource[]> => {
    return apiClient.get<AutomationOrchestrationResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<AutomationOrchestrationResource> => {
    return apiClient.get<AutomationOrchestrationResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: AutomationOrchestrationResourceCreate): Promise<AutomationOrchestrationResource> => {
    return apiClient.post<AutomationOrchestrationResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: AutomationOrchestrationResourceUpdate): Promise<AutomationOrchestrationResource> => {
    return apiClient.put<AutomationOrchestrationResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
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
  activateResource: async (id: string): Promise<AutomationOrchestrationResource> => {
    return apiClient.post<AutomationOrchestrationResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<AutomationOrchestrationResource> => {
    return apiClient.post<AutomationOrchestrationResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
