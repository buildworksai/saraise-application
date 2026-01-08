/**
 * Security & Access Control Service
 * 
 * Service client for Security & Access Control API endpoints.
 * CRITICAL: Tenant-scoped operations - users can only manage their tenant's security.
 * 
 * MIGRATED: Now uses contracts.ts for types and endpoints.
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */
import { apiClient } from '@/services/api-client';
import type {
  Role,
  Permission,
  UserRole,
  PermissionSet,
  UserPermissionSet,
  FieldSecurity,
  RowSecurityRule,
  SecurityProfile,
  SecurityAuditLog,
  RoleCreate,
  RoleUpdate,
  PermissionSetCreate,
  PermissionSetUpdate,
  UserRoleCreate,
  SecurityProfileCreate,
  SecurityProfileUpdate,
} from '../contracts';
import { ENDPOINTS } from '../contracts';

// Re-export types for backward compatibility
export type {
  Role,
  Permission,
  UserRole,
  PermissionSet,
  UserPermissionSet,
  FieldSecurity,
  RowSecurityRule,
  SecurityProfile,
  SecurityAuditLog,
  RoleCreate,
  RoleUpdate,
  PermissionSetCreate,
  PermissionSetUpdate,
  UserRoleCreate,
  SecurityProfileCreate,
  SecurityProfileUpdate,
};

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
      const url = queryString ? `${ENDPOINTS.ROLES.LIST}?${queryString}` : ENDPOINTS.ROLES.LIST;
      const response = await apiClient.get<Role[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Get role by ID
     */
    get: async (id: string): Promise<Role> => {
      return apiClient.get<Role>(ENDPOINTS.ROLES.DETAIL(id));
    },

    /**
     * Create role
     */
    create: async (data: RoleCreate): Promise<Role> => {
      return apiClient.post<Role>(ENDPOINTS.ROLES.CREATE, data);
    },

    /**
     * Update role
     */
    update: async (id: string, data: RoleUpdate): Promise<Role> => {
      return apiClient.patch<Role>(ENDPOINTS.ROLES.UPDATE(id), data);
    },

    /**
     * Delete role
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.ROLES.DELETE(id));
    },

    /**
     * Assign permission to role
     */
    assignPermission: async (roleId: string, permissionId: string, isGranted = true): Promise<Role> => {
      return apiClient.post<Role>(
        ENDPOINTS.ROLES.ASSIGN_PERMISSION(roleId),
        { permission_id: permissionId, is_granted: isGranted }
      );
    },

    /**
     * Revoke permission from role
     */
    revokePermission: async (roleId: string, permissionId: string): Promise<Role> => {
      return apiClient.post<Role>(ENDPOINTS.ROLES.REVOKE_PERMISSION(roleId), {
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
      const url = queryString ? `${ENDPOINTS.PERMISSIONS.LIST}?${queryString}` : ENDPOINTS.PERMISSIONS.LIST;
      const response = await apiClient.get<Permission[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Get permission by ID
     */
    get: async (id: string): Promise<Permission> => {
      return apiClient.get<Permission>(ENDPOINTS.PERMISSIONS.DETAIL(id));
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
      const url = queryString ? `${ENDPOINTS.USER_ROLES.LIST}?${queryString}` : ENDPOINTS.USER_ROLES.LIST;
      const response = await apiClient.get<UserRole[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Assign role to user
     */
    assign: async (data: UserRoleCreate): Promise<UserRole> => {
      return apiClient.post<UserRole>(ENDPOINTS.USER_ROLES.CREATE, data);
    },

    /**
     * Revoke role from user
     */
    revoke: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.USER_ROLES.DELETE(id));
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
      const url = queryString ? `${ENDPOINTS.PERMISSION_SETS.LIST}?${queryString}` : ENDPOINTS.PERMISSION_SETS.LIST;
      const response = await apiClient.get<PermissionSet[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Get permission set by ID
     */
    get: async (id: string): Promise<PermissionSet> => {
      return apiClient.get<PermissionSet>(ENDPOINTS.PERMISSION_SETS.DETAIL(id));
    },

    /**
     * Create permission set
     */
    create: async (data: PermissionSetCreate): Promise<PermissionSet> => {
      return apiClient.post<PermissionSet>(ENDPOINTS.PERMISSION_SETS.CREATE, data);
    },

    /**
     * Update permission set
     */
    update: async (id: string, data: PermissionSetUpdate): Promise<PermissionSet> => {
      return apiClient.patch<PermissionSet>(ENDPOINTS.PERMISSION_SETS.UPDATE(id), data);
    },

    /**
     * Delete permission set
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.PERMISSION_SETS.DELETE(id));
    },

    /**
     * Add permission to permission set
     */
    addPermission: async (permissionSetId: string, permissionId: string): Promise<PermissionSet> => {
      return apiClient.post<PermissionSet>(
        ENDPOINTS.PERMISSION_SETS.ADD_PERMISSION(permissionSetId),
        { permission_id: permissionId }
      );
    },

    /**
     * Remove permission from permission set
     */
    removePermission: async (permissionSetId: string, permissionId: string): Promise<PermissionSet> => {
      return apiClient.post<PermissionSet>(
        ENDPOINTS.PERMISSION_SETS.REMOVE_PERMISSION(permissionSetId),
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
      const url = queryString ? `${ENDPOINTS.SECURITY_PROFILES.LIST}?${queryString}` : ENDPOINTS.SECURITY_PROFILES.LIST;
      const response = await apiClient.get<SecurityProfile[]>(url);
      return (Array.isArray(response) ? response : []);
    },

    /**
     * Get security profile by ID
     */
    get: async (id: string): Promise<SecurityProfile> => {
      return apiClient.get<SecurityProfile>(ENDPOINTS.SECURITY_PROFILES.DETAIL(id));
    },

    /**
     * Create security profile
     */
    create: async (data: SecurityProfileCreate): Promise<SecurityProfile> => {
      return apiClient.post<SecurityProfile>(ENDPOINTS.SECURITY_PROFILES.CREATE, data);
    },

    /**
     * Update security profile
     */
    update: async (id: string, data: SecurityProfileUpdate): Promise<SecurityProfile> => {
      return apiClient.patch<SecurityProfile>(ENDPOINTS.SECURITY_PROFILES.UPDATE(id), data);
    },

    /**
     * Delete security profile
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.SECURITY_PROFILES.DELETE(id));
    },
  },

  /**
   * Audit Logs
   */
  auditLogs: {
    /**
     * List security audit logs for the current tenant
     */
    list: async (params?: { action?: string; decision?: string; actor_id?: string; resource_type?: string }): Promise<SecurityAuditLog[]> => {
      const queryParams = new URLSearchParams();
      if (params?.action) queryParams.append('action', params.action);
      if (params?.decision) queryParams.append('decision', params.decision);
      if (params?.actor_id) queryParams.append('actor_id', params.actor_id);
      if (params?.resource_type) queryParams.append('resource_type', params.resource_type);
      const queryString = queryParams.toString();
      const url = queryString ? `${ENDPOINTS.AUDIT_LOGS.LIST}?${queryString}` : ENDPOINTS.AUDIT_LOGS.LIST;
      const response = await apiClient.get<SecurityAuditLog[]>(url);
      return (Array.isArray(response) ? response : []);
    },
  },
};

