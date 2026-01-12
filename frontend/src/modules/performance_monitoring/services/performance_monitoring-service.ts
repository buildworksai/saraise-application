/**
 * PerformanceMonitoring Service
 * 
 * Service client for PerformanceMonitoring module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import type {
  PerformanceMonitoringResource,
  PerformanceMonitoringResourceCreate,
  PerformanceMonitoringResourceUpdate,
} from '../contracts';

export const performance_monitoringService = {
  /**
   * List all resources
   */
  listResources: async (): Promise<PerformanceMonitoringResource[]> => {
    return apiClient.get<PerformanceMonitoringResource[]>(ENDPOINTS.RESOURCES.LIST);
  },

  /**
   * Get resource by ID
   */
  getResource: async (id: string): Promise<PerformanceMonitoringResource> => {
    return apiClient.get<PerformanceMonitoringResource>(ENDPOINTS.RESOURCES.DETAIL(id));
  },

  /**
   * Create new resource
   */
  createResource: async (data: PerformanceMonitoringResourceCreate): Promise<PerformanceMonitoringResource> => {
    return apiClient.post<PerformanceMonitoringResource>(ENDPOINTS.RESOURCES.CREATE, data);
  },

  /**
   * Update resource
   */
  updateResource: async (id: string, data: PerformanceMonitoringResourceUpdate): Promise<PerformanceMonitoringResource> => {
    return apiClient.put<PerformanceMonitoringResource>(ENDPOINTS.RESOURCES.UPDATE(id), data);
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
  activateResource: async (id: string): Promise<PerformanceMonitoringResource> => {
    return apiClient.post<PerformanceMonitoringResource>(ENDPOINTS.RESOURCES.ACTIVATE(id));
  },

  /**
   * Deactivate resource
   */
  deactivateResource: async (id: string): Promise<PerformanceMonitoringResource> => {
    return apiClient.post<PerformanceMonitoringResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id));
  },
};
