/**
 * DocumentIntelligence Service
 * 
 * Service client for DocumentIntelligence module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';

import type {
  DocumentIntelligenceResource,
  DocumentIntelligenceResourceCreate,
  DocumentIntelligenceResourceUpdate,
} from '../contracts';

export const document_intelligenceService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<DocumentIntelligenceResource[]> => {
    return apiClient.get<DocumentIntelligenceResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<DocumentIntelligenceResource> => {
    return apiClient.get<DocumentIntelligenceResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: DocumentIntelligenceResourceCreate): Promise<DocumentIntelligenceResource> => {
    return apiClient.post<DocumentIntelligenceResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: DocumentIntelligenceResourceUpdate): Promise<DocumentIntelligenceResource> => {
    return apiClient.put<DocumentIntelligenceResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
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
  activateResource: async (id: string): Promise<DocumentIntelligenceResource> => {
    return apiClient.post<DocumentIntelligenceResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<DocumentIntelligenceResource> => {
    return apiClient.post<DocumentIntelligenceResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
