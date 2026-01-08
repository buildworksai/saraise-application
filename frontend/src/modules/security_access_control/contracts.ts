/**
 * Security & Access Control Module - Type Contracts & Endpoint Registry
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Security & Access Control are defined here.
 *
 * DO NOT:
 * - Define ad-hoc types in page components
 * - Hardcode URL strings in service files
 * - Import directly from @/types/api in pages
 *
 * DO:
 * - Import types from this file
 * - Use ENDPOINTS constant for all API calls
 * - Add new types here when extending the module
 *
 * @module security_access_control/contracts
 */

import type { components } from '@/types/api';

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Role entity */
export type Role = components['schemas']['Role'];

/** Role create request */
export type RoleCreate = components['schemas']['RoleCreate'];

/** Role create request (API format) */
export type RoleCreateRequest = components['schemas']['RoleCreateRequest'];

/** Role update request (partial) */
export type RoleUpdate = components['schemas']['PatchedRoleCreateRequest'];

/** Role type enum */
export type RoleType = components['schemas']['RoleTypeEnum'];

/** Permission entity (read-only) */
export type Permission = components['schemas']['Permission'];

/** User role entity */
export type UserRole = components['schemas']['UserRole'];

/** User role create request */
export type UserRoleCreate = components['schemas']['UserRoleRequest'];

/** Permission set entity */
export type PermissionSet = components['schemas']['PermissionSet'];

/** User permission set entity */
export type UserPermissionSet = components['schemas']['UserPermissionSet'];

/** Permission set create request */
export type PermissionSetCreate = components['schemas']['PermissionSetCreate'];

/** Permission set create request (API format) */
export type PermissionSetCreateRequest = components['schemas']['PermissionSetCreateRequest'];

/** Permission set update request (partial) */
export type PermissionSetUpdate = components['schemas']['PatchedPermissionSetCreateRequest'];

/** Field security entity */
export type FieldSecurity = components['schemas']['FieldSecurity'];

/** Field security create request */
export type FieldSecurityCreate = components['schemas']['FieldSecurityCreate'];

/** Field security create request (API format) */
export type FieldSecurityCreateRequest = components['schemas']['FieldSecurityCreateRequest'];

/** Field security update request (partial) */
export type FieldSecurityUpdate = components['schemas']['PatchedFieldSecurityCreateRequest'];

/** Row security rule entity */
export type RowSecurityRule = components['schemas']['RowSecurityRule'];

/** Row security rule create request */
export type RowSecurityRuleCreate = components['schemas']['RowSecurityRuleCreate'];

/** Row security rule create request (API format) */
export type RowSecurityRuleCreateRequest = components['schemas']['RowSecurityRuleCreateRequest'];

/** Row security rule update request (partial) */
export type RowSecurityRuleUpdate = components['schemas']['PatchedRowSecurityRuleCreateRequest'];

/** Security profile entity */
export type SecurityProfile = components['schemas']['SecurityProfile'];

/** Security profile create request */
export type SecurityProfileCreate = components['schemas']['SecurityProfileCreate'];

/** Security profile create request (API format) */
export type SecurityProfileCreateRequest = components['schemas']['SecurityProfileCreateRequest'];

/** Security profile update request (partial) */
export type SecurityProfileUpdate = components['schemas']['PatchedSecurityProfileCreateRequest'];

/** Security audit log entity (read-only) */
export type SecurityAuditLog = components['schemas']['SecurityAuditLog'];

/** Visibility enum for field security */
export type Visibility = components['schemas']['VisibilityEnum'];

/** Edit control enum for field security */
export type EditControl = components['schemas']['EditControlEnum'];

/** Profile type enum for security profiles */
export type ProfileType = components['schemas']['ProfileTypeEnum'];

/** MFA required enum */
export type MfaRequired = components['schemas']['MfaRequiredEnum'];

/** Rule type enum for row security */
export type RuleType = components['schemas']['RuleTypeEnum'];

/** Decision enum for audit logs */
export type Decision = components['schemas']['DecisionEnum'];

/** Actor type enum */
export type ActorType = components['schemas']['ActorTypeEnum'];

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * Security & Access Control API Endpoints
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS, Role } from './contracts';
 * apiClient.get<Role[]>(ENDPOINTS.ROLES.LIST);
 * apiClient.get<Role>(ENDPOINTS.ROLES.DETAIL('uuid'));
 * ```
 */
export const ENDPOINTS = {
  /** Roles endpoints */
  ROLES: {
    /** GET - List all roles */
    LIST: '/api/v1/security-access-control/roles/',
    /** GET - Get role by ID */
    DETAIL: (id: string) => `/api/v1/security-access-control/roles/${id}/` as const,
    /** POST - Create new role */
    CREATE: '/api/v1/security-access-control/roles/',
    /** PATCH - Update role by ID */
    UPDATE: (id: string) => `/api/v1/security-access-control/roles/${id}/` as const,
    /** DELETE - Delete role by ID */
    DELETE: (id: string) => `/api/v1/security-access-control/roles/${id}/` as const,
    /** POST - Assign permission to role */
    ASSIGN_PERMISSION: (roleId: string) => `/api/v1/security-access-control/roles/${roleId}/assign_permission/` as const,
    /** POST - Revoke permission from role */
    REVOKE_PERMISSION: (roleId: string) => `/api/v1/security-access-control/roles/${roleId}/revoke_permission/` as const,
  },

  /** Permissions endpoints */
  PERMISSIONS: {
    /** GET - List all permissions */
    LIST: '/api/v1/security-access-control/permissions/',
    /** GET - Get permission by ID */
    DETAIL: (id: string) => `/api/v1/security-access-control/permissions/${id}/` as const,
  },

  /** User Roles endpoints */
  USER_ROLES: {
    /** GET - List user role assignments */
    LIST: '/api/v1/security-access-control/user-roles/',
    /** GET - Get user role by ID */
    DETAIL: (id: string) => `/api/v1/security-access-control/user-roles/${id}/` as const,
    /** POST - Create user role assignment */
    CREATE: '/api/v1/security-access-control/user-roles/',
    /** PATCH - Update user role assignment */
    UPDATE: (id: string) => `/api/v1/security-access-control/user-roles/${id}/` as const,
    /** DELETE - Delete user role assignment */
    DELETE: (id: string) => `/api/v1/security-access-control/user-roles/${id}/` as const,
  },

  /** Permission Sets endpoints */
  PERMISSION_SETS: {
    /** GET - List all permission sets */
    LIST: '/api/v1/security-access-control/permission-sets/',
    /** GET - Get permission set by ID */
    DETAIL: (id: string) => `/api/v1/security-access-control/permission-sets/${id}/` as const,
    /** POST - Create new permission set */
    CREATE: '/api/v1/security-access-control/permission-sets/',
    /** PATCH - Update permission set */
    UPDATE: (id: string) => `/api/v1/security-access-control/permission-sets/${id}/` as const,
    /** DELETE - Delete permission set */
    DELETE: (id: string) => `/api/v1/security-access-control/permission-sets/${id}/` as const,
    /** POST - Add permission to permission set */
    ADD_PERMISSION: (id: string) => `/api/v1/security-access-control/permission-sets/${id}/add_permission/` as const,
    /** POST - Remove permission from permission set */
    REMOVE_PERMISSION: (id: string) => `/api/v1/security-access-control/permission-sets/${id}/remove_permission/` as const,
  },

  /** User Permission Sets endpoints */
  USER_PERMISSION_SETS: {
    /** GET - List user permission set grants */
    LIST: '/api/v1/security-access-control/user-permission-sets/',
    /** GET - Get user permission set by ID */
    DETAIL: (id: string) => `/api/v1/security-access-control/user-permission-sets/${id}/` as const,
    /** POST - Grant permission set to user */
    CREATE: '/api/v1/security-access-control/user-permission-sets/',
    /** PATCH - Update user permission set */
    UPDATE: (id: string) => `/api/v1/security-access-control/user-permission-sets/${id}/` as const,
    /** DELETE - Revoke permission set from user */
    DELETE: (id: string) => `/api/v1/security-access-control/user-permission-sets/${id}/` as const,
  },

  /** Field Security endpoints */
  FIELD_SECURITY: {
    /** GET - List field security rules */
    LIST: '/api/v1/security-access-control/field-security/',
    /** GET - Get field security rule by ID */
    DETAIL: (id: string) => `/api/v1/security-access-control/field-security/${id}/` as const,
    /** POST - Create field security rule */
    CREATE: '/api/v1/security-access-control/field-security/',
    /** PATCH - Update field security rule */
    UPDATE: (id: string) => `/api/v1/security-access-control/field-security/${id}/` as const,
    /** DELETE - Delete field security rule */
    DELETE: (id: string) => `/api/v1/security-access-control/field-security/${id}/` as const,
  },

  /** Row Security Rules endpoints */
  ROW_SECURITY_RULES: {
    /** GET - List row security rules */
    LIST: '/api/v1/security-access-control/row-security-rules/',
    /** GET - Get row security rule by ID */
    DETAIL: (id: string) => `/api/v1/security-access-control/row-security-rules/${id}/` as const,
    /** POST - Create row security rule */
    CREATE: '/api/v1/security-access-control/row-security-rules/',
    /** PATCH - Update row security rule */
    UPDATE: (id: string) => `/api/v1/security-access-control/row-security-rules/${id}/` as const,
    /** DELETE - Delete row security rule */
    DELETE: (id: string) => `/api/v1/security-access-control/row-security-rules/${id}/` as const,
  },

  /** Security Profiles endpoints */
  SECURITY_PROFILES: {
    /** GET - List security profiles */
    LIST: '/api/v1/security-access-control/security-profiles/',
    /** GET - Get security profile by ID */
    DETAIL: (id: string) => `/api/v1/security-access-control/security-profiles/${id}/` as const,
    /** POST - Create security profile */
    CREATE: '/api/v1/security-access-control/security-profiles/',
    /** PATCH - Update security profile */
    UPDATE: (id: string) => `/api/v1/security-access-control/security-profiles/${id}/` as const,
    /** DELETE - Delete security profile */
    DELETE: (id: string) => `/api/v1/security-access-control/security-profiles/${id}/` as const,
  },

  /** Audit Logs endpoints */
  AUDIT_LOGS: {
    /** GET - List audit logs */
    LIST: '/api/v1/security-access-control/audit-logs/',
    /** GET - Get audit log by ID */
    DETAIL: (id: string) => `/api/v1/security-access-control/audit-logs/${id}/` as const,
  },

  /** Health check endpoint */
  HEALTH: '/api/v1/security-access-control/health/',
} as const;

// =============================================================================
// TYPE GUARDS - Use for runtime type checking
// =============================================================================

/** Check if a value is a valid RoleType */
export function isRoleType(value: unknown): value is RoleType {
  return (
    value === 'system' || value === 'functional' || value === 'custom' || value === 'temporary'
  );
}

/** Check if a value is a valid Visibility */
export function isVisibility(value: unknown): value is Visibility {
  return value === 'visible' || value === 'hidden' || value === 'masked';
}

/** Check if a value is a valid EditControl */
export function isEditControl(value: unknown): value is EditControl {
  return value === 'read_only' || value === 'editable' || value === 'required';
}

/** Check if a value is a valid ProfileType */
export function isProfileType(value: unknown): value is ProfileType {
  return (
    value === 'standard' ||
    value === 'privileged' ||
    value === 'restricted' ||
    value === 'high_security'
  );
}

/** Check if a value is a valid MfaRequired */
export function isMfaRequired(value: unknown): value is MfaRequired {
  return (
    value === 'always' ||
    value === 'conditional' ||
    value === 'sensitive_actions' ||
    value === 'never'
  );
}

/** Check if a value is a valid RuleType */
export function isRuleType(value: unknown): value is RuleType {
  return (
    value === 'ownership' ||
    value === 'hierarchy' ||
    value === 'attribute' ||
    value === 'criteria'
  );
}

/** Check if a value is a valid Decision */
export function isDecision(value: unknown): value is Decision {
  return value === 'allow' || value === 'deny';
}

/** Check if a value is a valid ActorType */
export function isActorType(value: unknown): value is ActorType {
  return value === 'user' || value === 'system' || value === 'agent';
}

// =============================================================================
// EXAMPLES - Reference for agents writing new code
// =============================================================================

/**
 * Example usage patterns for agents:
 *
 * ```typescript
 * // Importing types
 * import {
 *   Role,
 *   RoleCreateRequest,
 *   Permission,
 *   PermissionSet,
 *   ENDPOINTS,
 * } from './contracts';
 *
 * // Listing roles
 * const roles = await apiClient.get<Role[]>(ENDPOINTS.ROLES.LIST);
 *
 * // Creating a role
 * const newRole: RoleCreateRequest = {
 *   name: 'Invoice Manager',
 *   code: 'invoice_manager',
 *   role_type: 'functional',
 * };
 * const created = await apiClient.post<Role>(ENDPOINTS.ROLES.CREATE, newRole);
 *
 * // Using with TanStack Query
 * const { data: roles } = useQuery({
 *   queryKey: ['security', 'roles'],
 *   queryFn: () => apiClient.get<Role[]>(ENDPOINTS.ROLES.LIST),
 * });
 * ```
 */

/**
 * EXAMPLES - Type-safe examples for AI agents
 * 
 * These examples use `satisfies` to ensure type correctness at compile time.
 */
export const EXAMPLES = {
  createRole: {
    request: {
      name: 'Invoice Manager',
      code: 'invoice_manager',
      role_type: 'functional',
      description: 'Manages invoice operations',
    } satisfies RoleCreateRequest,
    response: {
      id: 'role-uuid-123',
      name: 'Invoice Manager',
      code: 'invoice_manager',
      role_type: 'functional',
      description: 'Manages invoice operations',
      is_active: true,
      permission_count: 0,
      created_at: '2026-01-07T00:00:00Z',
      updated_at: '2026-01-07T00:00:00Z',
    } as unknown as Role,
  },
  createPermissionSet: {
    request: {
      name: 'Invoice Operations',
      description: 'Permissions for invoice operations',
    } satisfies PermissionSetCreateRequest,
    response: {
      id: 'permset-uuid-456',
      name: 'Invoice Operations',
      description: 'Permissions for invoice operations',
      permission_count: 0,
      created_at: '2026-01-07T00:00:00Z',
      updated_at: '2026-01-07T00:00:00Z',
    } as unknown as PermissionSet,
  },
} as const;

