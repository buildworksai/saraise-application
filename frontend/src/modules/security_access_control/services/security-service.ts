/**
 * Security & Access Control Service
 * 
 * Service client for Security & Access Control API endpoints.
 * CRITICAL: Tenant-scoped operations - users can only manage their tenant's security.
 */
import { apiClient } from '@/services/api-client';
import type { components } from '@/types/api';

// Use generated types from OpenAPI schema
export type Role = components['schemas']['Role'];
export type Permission = components['schemas']['Permission'];
export type UserRole = components['schemas']['UserRole'];
export type PermissionSet = components['schemas']['PermissionSet'];
export type UserPermissionSet = components['schemas']['UserPermissionSet'];
export type FieldSecurity = components['schemas']['FieldSecurity'];
export type RowSecurityRule = components['schemas']['RowSecurityRule'];
export type SecurityProfile = components['schemas']['SecurityProfile'];
export type SecurityAuditLog = components['schemas']['SecurityAuditLog'];

// Request types
export type RoleCreate = Omit<Role, 'id' | 'tenant_id' | 'created_at' | 'updated_at' | 'created_by' | 'updated_by' | 'permissions' | 'permission_count'>;
export type RoleUpdate = Partial<RoleCreate>;
export type PermissionSetCreate = Omit<PermissionSet, 'id' | 'tenant_id' | 'created_at' | 'updated_at' | 'created_by' | 'updated_by' | 'permission_count'>;
export type PermissionSetUpdate = Partial<PermissionSetCreate>;
export type UserRoleCreate = Omit<UserRole, 'id' | 'role' | 'is_active' | 'created_at'>;
export type SecurityProfileCreate = Omit<SecurityProfile, 'id' | 'tenant_id' | 'created_at' | 'updated_at'>;
export type SecurityProfileUpdate = Partial<SecurityProfileCreate>;

export const securityService = {
  /**
   * Roles
   */
  roles: {
    /**
     * List all roles for the current tenant
     */
    list: async (params?: { role_type?: string; is_active?: boolean; search?: string }): Promise<Role[]> => {
      const queryParams = new URLSearchParams();
      if (params?.role_type) queryParams.append('role_type', params.role_type);
      if (params?.is_active !== undefined) queryParams.append('is_active', params.is_active.toString());
      if (params?.search) queryParams.append('search', params.search);
      const queryString = queryParams.toString();
      const url = `/api/v1/security-access-control/roles/${queryString ? `?${queryString}` : ''}`;
      const response = await apiClient.get<Role[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Get role by ID
     */
    get: async (id: string): Promise<Role> => {
      return apiClient.get<Role>(`/api/v1/security-access-control/roles/${id}/`);
    },

    /**
     * Create role
     */
    create: async (data: RoleCreate): Promise<Role> => {
      return apiClient.post<Role>('/api/v1/security-access-control/roles/', data);
    },

    /**
     * Update role
     */
    update: async (id: string, data: RoleUpdate): Promise<Role> => {
      return apiClient.patch<Role>(`/api/v1/security-access-control/roles/${id}/`, data);
    },

    /**
     * Delete role
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(`/api/v1/security-access-control/roles/${id}/`);
    },

    /**
     * Assign permission to role
     */
    assignPermission: async (roleId: string, permissionId: string, isGranted = true): Promise<Role> => {
      return apiClient.post<Role>(
        `/api/v1/security-access-control/roles/${roleId}/assign_permission/`,
        { permission_id: permissionId, is_granted: isGranted }
      );
    },

    /**
     * Revoke permission from role
     */
    revokePermission: async (roleId: string, permissionId: string): Promise<Role> => {
      return apiClient.post<Role>(`/api/v1/security-access-control/roles/${roleId}/revoke_permission/`, {
        permission_id: permissionId,
      });
    },
  },

  /**
   * Permissions
   */
  permissions: {
    /**
     * List all permissions (platform-level, read-only)
     */
    list: async (params?: { module?: string; search?: string }): Promise<Permission[]> => {
      const queryParams = new URLSearchParams();
      if (params?.module) queryParams.append('module', params.module);
      if (params?.search) queryParams.append('search', params.search);
      const queryString = queryParams.toString();
      const url = `/api/v1/security-access-control/permissions/${queryString ? `?${queryString}` : ''}`;
      const response = await apiClient.get<Permission[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Get permission by ID
     */
    get: async (id: string): Promise<Permission> => {
      return apiClient.get<Permission>(`/api/v1/security-access-control/permissions/${id}/`);
    },
  },

  /**
   * User Roles
   */
  userRoles: {
    /**
     * List user-role assignments
     */
    list: async (params?: { user_id?: string; role_id?: string }): Promise<UserRole[]> => {
      const queryParams = new URLSearchParams();
      if (params?.user_id) queryParams.append('user_id', params.user_id);
      if (params?.role_id) queryParams.append('role_id', params.role_id);
      const queryString = queryParams.toString();
      const url = `/api/v1/security-access-control/user-roles/${queryString ? `?${queryString}` : ''}`;
      const response = await apiClient.get<UserRole[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Assign role to user
     */
    assign: async (data: UserRoleCreate): Promise<UserRole> => {
      return apiClient.post<UserRole>('/api/v1/security-access-control/user-roles/', data);
    },

    /**
     * Revoke role from user
     */
    revoke: async (id: string): Promise<void> => {
      return apiClient.delete(`/api/v1/security-access-control/user-roles/${id}/`);
    },
  },

  /**
   * Permission Sets
   */
  permissionSets: {
    /**
     * List all permission sets for the current tenant
     */
    list: async (params?: { search?: string }): Promise<PermissionSet[]> => {
      const queryParams = new URLSearchParams();
      if (params?.search) queryParams.append('search', params.search);
      const queryString = queryParams.toString();
      const url = `/api/v1/security-access-control/permission-sets/${queryString ? `?${queryString}` : ''}`;
      const response = await apiClient.get<PermissionSet[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Get permission set by ID
     */
    get: async (id: string): Promise<PermissionSet> => {
      return apiClient.get<PermissionSet>(`/api/v1/security-access-control/permission-sets/${id}/`);
    },

    /**
     * Create permission set
     */
    create: async (data: PermissionSetCreate): Promise<PermissionSet> => {
      return apiClient.post<PermissionSet>('/api/v1/security-access-control/permission-sets/', data);
    },

    /**
     * Update permission set
     */
    update: async (id: string, data: PermissionSetUpdate): Promise<PermissionSet> => {
      return apiClient.patch<PermissionSet>(`/api/v1/security-access-control/permission-sets/${id}/`, data);
    },

    /**
     * Delete permission set
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(`/api/v1/security-access-control/permission-sets/${id}/`);
    },

    /**
     * Add permission to permission set
     */
    addPermission: async (permissionSetId: string, permissionId: string): Promise<PermissionSet> => {
      return apiClient.post<PermissionSet>(
        `/api/v1/security-access-control/permission-sets/${permissionSetId}/add_permission/`,
        { permission_id: permissionId }
      );
    },

    /**
     * Remove permission from permission set
     */
    removePermission: async (permissionSetId: string, permissionId: string): Promise<PermissionSet> => {
      return apiClient.post<PermissionSet>(
        `/api/v1/security-access-control/permission-sets/${permissionSetId}/remove_permission/`,
        { permission_id: permissionId }
      );
    },
  },

  /**
   * Security Profiles
   */
  securityProfiles: {
    /**
     * List all security profiles for the current tenant
     */
    list: async (params?: { profile_type?: string; search?: string }): Promise<SecurityProfile[]> => {
      const queryParams = new URLSearchParams();
      if (params?.profile_type) queryParams.append('profile_type', params.profile_type);
      if (params?.search) queryParams.append('search', params.search);
      const queryString = queryParams.toString();
      const url = `/api/v1/security-access-control/security-profiles/${queryString ? `?${queryString}` : ''}`;
      const response = await apiClient.get<SecurityProfile[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Get security profile by ID
     */
    get: async (id: string): Promise<SecurityProfile> => {
      return apiClient.get<SecurityProfile>(`/api/v1/security-access-control/security-profiles/${id}/`);
    },

    /**
     * Create security profile
     */
    create: async (data: SecurityProfileCreate): Promise<SecurityProfile> => {
      return apiClient.post<SecurityProfile>('/api/v1/security-access-control/security-profiles/', data);
    },

    /**
     * Update security profile
     */
    update: async (id: string, data: SecurityProfileUpdate): Promise<SecurityProfile> => {
      return apiClient.patch<SecurityProfile>(`/api/v1/security-access-control/security-profiles/${id}/`, data);
    },

    /**
     * Delete security profile
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(`/api/v1/security-access-control/security-profiles/${id}/`);
    },
  },

  /**
   * Audit Logs
   */
  auditLogs: {
    /**
     * List security audit logs for the current tenant
     */
    list: async (params?: { action?: string; decision?: string; actorId?: string; resourceType?: string }): Promise<SecurityAuditLog[]> => {
      const queryParams = new URLSearchParams();
      if (params?.action) queryParams.append('action', params.action);
      if (params?.decision) queryParams.append('decision', params.decision);
      if (params?.actorId) queryParams.append('actor_id', params.actorId);
      if (params?.resourceType) queryParams.append('resource_type', params.resourceType);
      const queryString = queryParams.toString();
      const url = `/api/v1/security-access-control/audit-logs/${queryString ? `?${queryString}` : ''}`;
      const response = await apiClient.get<SecurityAuditLog[]>(url);
      return (Array.isArray(response) ? response : []);
    },
  },
};

