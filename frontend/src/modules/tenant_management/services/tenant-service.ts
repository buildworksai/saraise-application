/**
 * Tenant Management Service
 * 
 * Service client for Tenant Management API endpoints.
 * CRITICAL: Platform-level operations - only platform owners can access.
 * 
 * MIGRATED: Now uses contracts.ts for types and endpoints.
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */
import { apiClient } from '@/services/api-client';
import type {
  Tenant,
  TenantModule,
  TenantResourceUsage,
  TenantSettings,
  TenantHealthScore,
  TenantRequest,
  TenantUpdate,
  TenantModuleRequest,
  TenantModuleUpdate,
  TenantSettingsRequest,
  TenantSettingsUpdate,
} from '../contracts';
import { ENDPOINTS } from '../contracts';

// Re-export types for backward compatibility
export type {
  Tenant,
  TenantModule,
  TenantResourceUsage,
  TenantSettings,
  TenantHealthScore,
};

// Request types (aliases for backward compatibility)
export type TenantCreate = TenantRequest;
export type TenantModuleCreate = TenantModuleRequest;
export type TenantSettingsCreate = TenantSettingsRequest;

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
      const url = queryString ? `${ENDPOINTS.TENANTS.LIST}?${queryString}` : ENDPOINTS.TENANTS.LIST;
      const response = await apiClient.get<Tenant[]>(url);
      return response ?? [];
    },

    /**
     * Get tenant by ID
     */
    get: async (id: string): Promise<Tenant> => {
      return apiClient.get<Tenant>(ENDPOINTS.TENANTS.DETAIL(id));
    },

    /**
     * Create tenant
     */
    create: async (data: TenantCreate): Promise<Tenant> => {
      return apiClient.post<Tenant>(ENDPOINTS.TENANTS.CREATE, data);
    },

    /**
     * Update tenant
     */
    update: async (id: string, data: TenantUpdate): Promise<Tenant> => {
      return apiClient.patch<Tenant>(ENDPOINTS.TENANTS.UPDATE(id), data);
    },

    /**
     * Delete tenant
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.TENANTS.DELETE(id));
    },

    /**
     * Suspend tenant
     */
    suspend: async (id: string): Promise<{ status: string; message: string }> => {
      return apiClient.post<{ status: string; message: string }>(ENDPOINTS.TENANTS.SUSPEND(id));
    },

    /**
     * Activate tenant
     */
    activate: async (id: string): Promise<{ status: string; message: string }> => {
      return apiClient.post<{ status: string; message: string }>(ENDPOINTS.TENANTS.ACTIVATE(id));
    },

    /**
     * Get tenant modules
     */
    getModules: async (id: string): Promise<TenantModule[]> => {
      const response = await apiClient.get<TenantModule[]>(ENDPOINTS.TENANTS.MODULES(id));
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
      const url = queryString ? `${ENDPOINTS.TENANTS.RESOURCE_USAGE(id)}?${queryString}` : ENDPOINTS.TENANTS.RESOURCE_USAGE(id);
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
      const url = queryString ? `${ENDPOINTS.TENANTS.HEALTH_SCORES(id)}?${queryString}` : ENDPOINTS.TENANTS.HEALTH_SCORES(id);
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
      const url = queryString ? `${ENDPOINTS.MODULES.LIST}?${queryString}` : ENDPOINTS.MODULES.LIST;
      const response = await apiClient.get<TenantModule[]>(url);
      return response ?? [];
    },

    /**
     * Get module by ID
     */
    get: async (id: string): Promise<TenantModule> => {
      return apiClient.get<TenantModule>(ENDPOINTS.MODULES.DETAIL(id));
    },

    /**
     * Create tenant module
     */
    create: async (data: TenantModuleCreate): Promise<TenantModule> => {
      return apiClient.post<TenantModule>(ENDPOINTS.MODULES.CREATE, data);
    },

    /**
     * Update tenant module
     */
    update: async (id: string, data: Partial<TenantModuleCreate>): Promise<TenantModule> => {
      return apiClient.patch<TenantModule>(ENDPOINTS.MODULES.UPDATE(id), data);
    },

    /**
     * Delete tenant module
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.MODULES.DELETE(id));
    },

    /**
     * Enable module
     */
    enable: async (id: string): Promise<{ status: string; message: string }> => {
      return apiClient.post<{ status: string; message: string }>(ENDPOINTS.MODULES.ENABLE(id));
    },

    /**
     * Disable module
     */
    disable: async (id: string): Promise<{ status: string; message: string }> => {
      return apiClient.post<{ status: string; message: string }>(ENDPOINTS.MODULES.DISABLE(id));
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
      const url = queryString ? `${ENDPOINTS.RESOURCE_USAGE.LIST}?${queryString}` : ENDPOINTS.RESOURCE_USAGE.LIST;
      const response = await apiClient.get<TenantResourceUsage[]>(url);
      return response ?? [];
    },

    /**
     * Get resource usage by ID
     */
    get: async (id: string): Promise<TenantResourceUsage> => {
      return apiClient.get<TenantResourceUsage>(ENDPOINTS.RESOURCE_USAGE.DETAIL(id));
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
      const url = queryString ? `${ENDPOINTS.SETTINGS.LIST}?${queryString}` : ENDPOINTS.SETTINGS.LIST;
      const response = await apiClient.get<TenantSettings[]>(url);
      return response ?? [];
    },

    /**
     * Get setting by ID
     */
    get: async (id: string): Promise<TenantSettings> => {
      return apiClient.get<TenantSettings>(ENDPOINTS.SETTINGS.DETAIL(id));
    },

    /**
     * Create setting
     */
    create: async (data: TenantSettingsCreate): Promise<TenantSettings> => {
      return apiClient.post<TenantSettings>(ENDPOINTS.SETTINGS.CREATE, data);
    },

    /**
     * Update setting
     */
    update: async (id: string, data: Partial<TenantSettingsCreate>): Promise<TenantSettings> => {
      return apiClient.patch<TenantSettings>(ENDPOINTS.SETTINGS.UPDATE(id), data);
    },

    /**
     * Delete setting
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.SETTINGS.DELETE(id));
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
      const url = queryString ? `${ENDPOINTS.HEALTH_SCORES.LIST}?${queryString}` : ENDPOINTS.HEALTH_SCORES.LIST;
      const response = await apiClient.get<TenantHealthScore[]>(url);
      return response ?? [];
    },

    /**
     * Get health score by ID
     */
    get: async (id: string): Promise<TenantHealthScore> => {
      return apiClient.get<TenantHealthScore>(ENDPOINTS.HEALTH_SCORES.DETAIL(id));
    },
  },
};

