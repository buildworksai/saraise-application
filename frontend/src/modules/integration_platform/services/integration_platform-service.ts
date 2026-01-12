/**
 * IntegrationPlatform Service
 * 
 * Service client for IntegrationPlatform module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import type {
  Integration,
  IntegrationCreate,
  IntegrationUpdate,
} from '../contracts';

export const integration_platformService = {
  /**
   * List all integrations
   */
  listIntegrations: async (): Promise<Integration[]> => {
    return apiClient.get<Integration[]>(ENDPOINTS.INTEGRATIONS.LIST);
  },

  /**
   * Get integration by ID
   */
  getIntegration: async (id: string): Promise<Integration> => {
    return apiClient.get<Integration>(ENDPOINTS.INTEGRATIONS.DETAIL(id));
  },

  /**
   * Create new integration
   */
  createIntegration: async (data: IntegrationCreate): Promise<Integration> => {
    return apiClient.post<Integration>(ENDPOINTS.INTEGRATIONS.CREATE, data);
  },

  /**
   * Update integration
   */
  updateIntegration: async (id: string, data: IntegrationUpdate): Promise<Integration> => {
    return apiClient.put<Integration>(ENDPOINTS.INTEGRATIONS.UPDATE(id), data);
  },

  /**
   * Delete integration
   */
  deleteIntegration: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.INTEGRATIONS.DELETE(id));
  },

  /**
   * Test integration
   */
  testIntegration: async (id: string): Promise<void> => {
    return apiClient.post(ENDPOINTS.INTEGRATIONS.TEST(id));
  },

  /**
   * Sync integration
   */
  syncIntegration: async (id: string): Promise<void> => {
    return apiClient.post(ENDPOINTS.INTEGRATIONS.SYNC(id));
  },

  // Legacy methods for backward compatibility with generic list pages
  /**
   * List all resources (legacy - returns integrations)
   * @deprecated Use listIntegrations() instead
   */
  listResources: async (): Promise<Integration[]> => {
    return apiClient.get<Integration[]>(ENDPOINTS.INTEGRATIONS.LIST);
  },

  /**
   * Get resource by ID (legacy - returns integration)
   * @deprecated Use getIntegration() instead
   */
  getResource: async (id: string): Promise<Integration> => {
    return apiClient.get<Integration>(ENDPOINTS.INTEGRATIONS.DETAIL(id));
  },

  /**
   * Create new resource (legacy - creates integration)
   * @deprecated Use createIntegration() instead
   */
  createResource: async (data: IntegrationCreate): Promise<Integration> => {
    return apiClient.post<Integration>(ENDPOINTS.INTEGRATIONS.CREATE, data);
  },

  /**
   * Update resource (legacy - updates integration)
   * @deprecated Use updateIntegration() instead
   */
  updateResource: async (id: string, data: IntegrationUpdate): Promise<Integration> => {
    return apiClient.put<Integration>(ENDPOINTS.INTEGRATIONS.UPDATE(id), data);
  },

  /**
   * Delete resource (legacy - deletes integration)
   * @deprecated Use deleteIntegration() instead
   */
  deleteResource: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.INTEGRATIONS.DELETE(id));
  },
};
