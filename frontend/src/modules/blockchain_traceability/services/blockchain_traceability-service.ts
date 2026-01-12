/**
 * BlockchainTraceability Service
 * 
 * Service client for BlockchainTraceability module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type BlockchainTraceabilityResource, type BlockchainTraceabilityResourceCreate, type BlockchainTraceabilityResourceUpdate } from '../contracts';

export const blockchain_traceabilityService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<BlockchainTraceabilityResource[]> => {
    return apiClient.get<BlockchainTraceabilityResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<BlockchainTraceabilityResource> => {
    return apiClient.get<BlockchainTraceabilityResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: BlockchainTraceabilityResourceCreate): Promise<BlockchainTraceabilityResource> => {
    return apiClient.post<BlockchainTraceabilityResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: BlockchainTraceabilityResourceUpdate): Promise<BlockchainTraceabilityResource> => {
    return apiClient.put<BlockchainTraceabilityResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
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
  activateResource: async (id: string): Promise<BlockchainTraceabilityResource> => {
    return apiClient.post<BlockchainTraceabilityResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<BlockchainTraceabilityResource> => {
    return apiClient.post<BlockchainTraceabilityResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
