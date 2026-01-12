/**
 * WorkflowAutomation Service
 * 
 * Service client for WorkflowAutomation module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import type {
  WorkflowAutomationResource,
  WorkflowAutomationResourceCreate,
  WorkflowAutomationResourceUpdate,
} from '../contracts';

export const workflow_automationService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<WorkflowAutomationResource[]> => {
    return apiClient.get<WorkflowAutomationResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<WorkflowAutomationResource> => {
    return apiClient.get<WorkflowAutomationResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: WorkflowAutomationResourceCreate): Promise<WorkflowAutomationResource> => {
    return apiClient.post<WorkflowAutomationResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: WorkflowAutomationResourceUpdate): Promise<WorkflowAutomationResource> => {
    return apiClient.put<WorkflowAutomationResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
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
  activateResource: async (id: string): Promise<WorkflowAutomationResource> => {
    return apiClient.post<WorkflowAutomationResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<WorkflowAutomationResource> => {
    return apiClient.post<WorkflowAutomationResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
