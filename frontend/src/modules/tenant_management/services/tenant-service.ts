/**
 * Tenant Management Service
 * 
 * Service client for Tenant Management API endpoints.
 * CRITICAL: Platform-level operations - only platform owners can access.
 */
import { apiClient } from '@/services/api-client';
import type { components } from '@/types/api';

// Use generated types from OpenAPI schema
export type Tenant = components['schemas']['Tenant'];
export type TenantModule = components['schemas']['TenantModule'];
export type TenantResourceUsage = components['schemas']['TenantResourceUsage'];
export type TenantSettings = components['schemas']['TenantSettings'];
export type TenantHealthScore = components['schemas']['TenantHealthScore'];

// Request types
export type TenantCreate = Omit<Tenant, 'id' | 'created_at' | 'updated_at' | 'created_by'>;
export type TenantUpdate = Partial<TenantCreate>;
export type TenantModuleCreate = Omit<TenantModule, 'id' | 'installed_at' | 'created_at' | 'updated_at'>;
export type TenantSettingsCreate = Omit<TenantSettings, 'id' | 'created_at' | 'updated_at'>;

export const tenantService = {
  /**
   * Tenants
   */
  tenants: {
    /**
     * List all tenants
     */
    list: async (params?: { status?: string; subscription_plan_id?: string; search?: string }): Promise<Tenant[]> => {
      const queryParams = new URLSearchParams();
      if (params?.status) queryParams.append('status', params.status);
      if (params?.subscription_plan_id) queryParams.append('subscription_plan_id', params.subscription_plan_id);
      if (params?.search) queryParams.append('search', params.search);
      const queryString = queryParams.toString();
      const url = `/api/v1/tenant-management/tenants/${queryString ? `?${queryString}` : ''}`;
      const response = await apiClient.get<Tenant[]>(url);
      return response ?? [];
    },

    /**
     * Get tenant by ID
     */
    get: async (id: string): Promise<Tenant> => {
      return apiClient.get<Tenant>(`/api/v1/tenant-management/tenants/${id}/`);
    },

    /**
     * Create tenant
     */
    create: async (data: TenantCreate): Promise<Tenant> => {
      return apiClient.post<Tenant>('/api/v1/tenant-management/tenants/', data);
    },

    /**
     * Update tenant
     */
    update: async (id: string, data: TenantUpdate): Promise<Tenant> => {
      return apiClient.patch<Tenant>(`/api/v1/tenant-management/tenants/${id}/`, data);
    },

    /**
     * Delete tenant
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(`/api/v1/tenant-management/tenants/${id}/`);
    },

    /**
     * Suspend tenant
     */
    suspend: async (id: string): Promise<{ status: string; message: string }> => {
      return apiClient.post<{ status: string; message: string }>(`/api/v1/tenant-management/tenants/${id}/suspend/`);
    },

    /**
     * Activate tenant
     */
    activate: async (id: string): Promise<{ status: string; message: string }> => {
      return apiClient.post<{ status: string; message: string }>(`/api/v1/tenant-management/tenants/${id}/activate/`);
    },

    /**
     * Get tenant modules
     */
    getModules: async (id: string): Promise<TenantModule[]> => {
      const response = await apiClient.get<TenantModule[]>(`/api/v1/tenant-management/tenants/${id}/modules/`);
      return response ?? [];
    },

    /**
     * Get tenant resource usage
     */
    getResourceUsage: async (id: string, params?: { date_from?: string; date_to?: string }): Promise<TenantResourceUsage[]> => {
      const queryParams = new URLSearchParams();
      if (params?.date_from) queryParams.append('date_from', params.date_from);
      if (params?.date_to) queryParams.append('date_to', params.date_to);
      const queryString = queryParams.toString();
      const url = `/api/v1/tenant-management/tenants/${id}/resource_usage/${queryString !== '' ? `?${queryString}` : ''}`;
      const response = await apiClient.get<TenantResourceUsage[]>(url);
      return response ?? [];
    },

    /**
     * Get tenant health scores
     */
    getHealthScores: async (id: string, params?: { date_from?: string; date_to?: string }): Promise<TenantHealthScore[]> => {
      const queryParams = new URLSearchParams();
      if (params?.date_from) queryParams.append('date_from', params.date_from);
      if (params?.date_to) queryParams.append('date_to', params.date_to);
      const queryString = queryParams.toString();
      const url = `/api/v1/tenant-management/tenants/${id}/health_scores/${queryString !== '' ? `?${queryString}` : ''}`;
      const response = await apiClient.get<TenantHealthScore[]>(url);
      return response ?? [];
    },
  },

  /**
   * Tenant Modules
   */
  modules: {
    /**
     * List tenant modules
     */
    list: async (params?: { tenant_id?: string; module_name?: string; is_enabled?: boolean }): Promise<TenantModule[]> => {
      const queryParams = new URLSearchParams();
      if (params?.tenant_id) queryParams.append('tenant_id', params.tenant_id);
      if (params?.module_name) queryParams.append('module_name', params.module_name);
      if (params?.is_enabled !== undefined) queryParams.append('is_enabled', String(params.is_enabled));
      const queryString = queryParams.toString();
      const url = `/api/v1/tenant-management/modules/${queryString !== '' ? `?${queryString}` : ''}`;
      const response = await apiClient.get<TenantModule[]>(url);
      return response ?? [];
    },

    /**
     * Get module by ID
     */
    get: async (id: string): Promise<TenantModule> => {
      return apiClient.get<TenantModule>(`/api/v1/tenant-management/modules/${id}/`);
    },

    /**
     * Create tenant module
     */
    create: async (data: TenantModuleCreate): Promise<TenantModule> => {
      return apiClient.post<TenantModule>('/api/v1/tenant-management/modules/', data);
    },

    /**
     * Update tenant module
     */
    update: async (id: string, data: Partial<TenantModuleCreate>): Promise<TenantModule> => {
      return apiClient.patch<TenantModule>(`/api/v1/tenant-management/modules/${id}/`, data);
    },

    /**
     * Delete tenant module
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(`/api/v1/tenant-management/modules/${id}/`);
    },

    /**
     * Enable module
     */
    enable: async (id: string): Promise<{ status: string; message: string }> => {
      return apiClient.post<{ status: string; message: string }>(`/api/v1/tenant-management/modules/${id}/enable/`);
    },

    /**
     * Disable module
     */
    disable: async (id: string): Promise<{ status: string; message: string }> => {
      return apiClient.post<{ status: string; message: string }>(`/api/v1/tenant-management/modules/${id}/disable/`);
    },
  },

  /**
   * Tenant Resource Usage
   */
  resourceUsage: {
    /**
     * List resource usage
     */
    list: async (params?: { tenant_id?: string; date_from?: string; date_to?: string }): Promise<TenantResourceUsage[]> => {
      const queryParams = new URLSearchParams();
      if (params?.tenant_id) queryParams.append('tenant_id', params.tenant_id);
      if (params?.date_from) queryParams.append('date_from', params.date_from);
      if (params?.date_to) queryParams.append('date_to', params.date_to);
      const queryString = queryParams.toString();
      const url = `/api/v1/tenant-management/resource-usage/${queryString !== '' ? `?${queryString}` : ''}`;
      const response = await apiClient.get<TenantResourceUsage[]>(url);
      return response ?? [];
    },

    /**
     * Get resource usage by ID
     */
    get: async (id: string): Promise<TenantResourceUsage> => {
      return apiClient.get<TenantResourceUsage>(`/api/v1/tenant-management/resource-usage/${id}/`);
    },
  },

  /**
   * Tenant Settings
   */
  settings: {
    /**
     * List tenant settings
     */
    list: async (params?: { tenant_id?: string; category?: string }): Promise<TenantSettings[]> => {
      const queryParams = new URLSearchParams();
      if (params?.tenant_id) queryParams.append('tenant_id', params.tenant_id);
      if (params?.category) queryParams.append('category', params.category);
      const queryString = queryParams.toString();
      const url = `/api/v1/tenant-management/settings/${queryString !== '' ? `?${queryString}` : ''}`;
      const response = await apiClient.get<TenantSettings[]>(url);
      return response ?? [];
    },

    /**
     * Get setting by ID
     */
    get: async (id: string): Promise<TenantSettings> => {
      return apiClient.get<TenantSettings>(`/api/v1/tenant-management/settings/${id}/`);
    },

    /**
     * Create setting
     */
    create: async (data: TenantSettingsCreate): Promise<TenantSettings> => {
      return apiClient.post<TenantSettings>('/api/v1/tenant-management/settings/', data);
    },

    /**
     * Update setting
     */
    update: async (id: string, data: Partial<TenantSettingsCreate>): Promise<TenantSettings> => {
      return apiClient.patch<TenantSettings>(`/api/v1/tenant-management/settings/${id}/`, data);
    },

    /**
     * Delete setting
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(`/api/v1/tenant-management/settings/${id}/`);
    },
  },

  /**
   * Tenant Health Scores
   */
  healthScores: {
    /**
     * List health scores
     */
    list: async (params?: { tenant_id?: string; date_from?: string; date_to?: string; churn_risk_min?: number }): Promise<TenantHealthScore[]> => {
      const queryParams = new URLSearchParams();
      if (params?.tenant_id) queryParams.append('tenant_id', params.tenant_id);
      if (params?.date_from) queryParams.append('date_from', params.date_from);
      if (params?.date_to) queryParams.append('date_to', params.date_to);
      if (params?.churn_risk_min !== undefined) queryParams.append('churn_risk_min', String(params.churn_risk_min));
      const queryString = queryParams.toString();
      const url = `/api/v1/tenant-management/health-scores/${queryString !== '' ? `?${queryString}` : ''}`;
      const response = await apiClient.get<TenantHealthScore[]>(url);
      return response ?? [];
    },

    /**
     * Get health score by ID
     */
    get: async (id: string): Promise<TenantHealthScore> => {
      return apiClient.get<TenantHealthScore>(`/api/v1/tenant-management/health-scores/${id}/`);
    },
  },
};

