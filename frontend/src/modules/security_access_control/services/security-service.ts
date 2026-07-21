/** Sole HTTP integration surface for Security & Access Control. */
import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  isAccessDecision,
  isFieldSecurity,
  isHealthStatus,
  isPermission,
  isPermissionSet,
  isProfileAssignment,
  isRecord,
  isRole,
  isRolePermission,
  isRowSecurityRule,
  isSecurityAuditLog,
  isSecurityProfile,
  isUserPermissionSet,
  isUserRole,
  isV2Meta,
  type AccessDecision,
  type AccessSimulationInput,
  type AssignmentFilters,
  type AuditLogFilters,
  type FieldSecurityFilters,
  type FieldSecurityInput,
  type FieldSecurityUpdateInput,
  type GovernedResult,
  type HealthStatus,
  type PaginatedResult,
  type PermissionFilters,
  type PermissionSetCreateInput,
  type PermissionSetFilters,
  type PermissionSetUpdateInput,
  type ProfileType,
  type ReplacePermissionSetPermissionsInput,
  type RoleCreateInput,
  type RoleFilters,
  type RolePermission,
  type RoleUpdateInput,
  type RowSecurityFilters,
  type RowSecurityRuleInput,
  type RowSecurityRuleUpdateInput,
  type SecurityProfileAssignmentCreateInput,
  type SecurityProfileAssignmentUpdateInput,
  type SecurityProfileFilters,
  type SecurityProfileInput,
  type SecurityProfileUpdateInput,
  type SetRolePermissionInput,
  type UUID,
  type UserPermissionSetCreateInput,
  type UserPermissionSetUpdateInput,
  type UserRoleCreateInput,
  type UserRoleUpdateInput,
  type V2Envelope,
} from "../contracts";

type Guard<T> = (value: unknown) => value is T;

function malformed(message: string, correlationId?: string): ApiError {
  return new ApiError(message, 502, undefined, "MALFORMED_RESPONSE", correlationId);
}

function unwrap<T>(value: unknown, guard: Guard<T>): GovernedResult<T> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw malformed("The security API returned a malformed governed envelope.");
  }
  if (!isRecord(value)) throw malformed("The security API returned a malformed governed envelope.");
  const record = value;
  if (!isV2Meta(record.meta)) throw malformed("The security API response metadata is invalid.");
  if (!guard(record.data)) throw malformed("The security API response data does not match its contract.", record.meta.correlation_id);
  return { data: record.data, correlationId: record.meta.correlation_id, timestamp: record.meta.timestamp };
}

function unwrapPage<T>(value: unknown, guard: Guard<T>): PaginatedResult<T> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw malformed("The security API returned a malformed paginated envelope.");
  }
  if (!isRecord(value)) throw malformed("The security API returned a malformed paginated envelope.");
  const record = value;
  if (!isV2Meta(record.meta) || !record.meta.pagination) throw malformed("The security API omitted required pagination metadata.");
  if (!Array.isArray(record.data) || !record.data.every(guard)) throw malformed("The security API returned malformed list data.", record.meta.correlation_id);
  return { items: record.data, pagination: record.meta.pagination, correlationId: record.meta.correlation_id, timestamp: record.meta.timestamp };
}

function query(path: string, filters: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const encoded = params.toString();
  return encoded ? `${path}?${encoded}` : path;
}

async function getOne<T>(path: string, guard: Guard<T>): Promise<GovernedResult<T>> {
  return unwrap(await apiClient.get<unknown>(path), guard);
}
async function getPage<T>(path: string, filters: object, guard: Guard<T>): Promise<PaginatedResult<T>> {
  return unwrapPage(await apiClient.get<unknown>(query(path, filters)), guard);
}
async function postOne<T>(path: string, input: unknown, guard: Guard<T>): Promise<GovernedResult<T>> {
  return unwrap(await apiClient.post<unknown>(path, input), guard);
}
async function patchOne<T>(path: string, input: unknown, guard: Guard<T>): Promise<GovernedResult<T>> {
  return unwrap(await apiClient.patch<unknown>(path, input), guard);
}
async function putOne<T>(path: string, input: unknown, guard: Guard<T>): Promise<GovernedResult<T>> {
  return unwrap(await apiClient.put<unknown>(path, input), guard);
}

export const securityService = {
  roles: {
    list: (filters: RoleFilters = {}) => getPage(ENDPOINTS.ROLES.LIST, filters, isRole),
    get: (id: UUID) => getOne(ENDPOINTS.ROLES.DETAIL(id), isRole),
    create: (input: RoleCreateInput) => postOne(ENDPOINTS.ROLES.CREATE, input, isRole),
    update: (id: UUID, input: RoleUpdateInput) => patchOne(ENDPOINTS.ROLES.UPDATE(id), input, isRole),
    delete: (id: UUID) => apiClient.delete<void>(ENDPOINTS.ROLES.DELETE(id)),
    setPermission: (id: UUID, input: SetRolePermissionInput) => postOne(ENDPOINTS.ROLES.PERMISSIONS(id), input, isRolePermission),
    removePermission: (id: UUID, permissionId: UUID) => apiClient.delete<void>(ENDPOINTS.ROLES.PERMISSION(id, permissionId)),
  },
  permissions: {
    list: (filters: PermissionFilters = {}) => getPage(ENDPOINTS.PERMISSIONS.LIST, filters, isPermission),
    get: (id: UUID) => getOne(ENDPOINTS.PERMISSIONS.DETAIL(id), isPermission),
  },
  userRoles: {
    list: (filters: AssignmentFilters = {}) => getPage(ENDPOINTS.USER_ROLES.LIST, filters, isUserRole),
    get: (id: UUID) => getOne(ENDPOINTS.USER_ROLES.DETAIL(id), isUserRole),
    create: (input: UserRoleCreateInput) => postOne(ENDPOINTS.USER_ROLES.CREATE, input, isUserRole),
    update: (id: UUID, input: UserRoleUpdateInput) => patchOne(ENDPOINTS.USER_ROLES.UPDATE(id), input, isUserRole),
    revoke: (id: UUID) => apiClient.delete<void>(ENDPOINTS.USER_ROLES.DELETE(id)),
  },
  permissionSets: {
    list: (filters: PermissionSetFilters = {}) => getPage(ENDPOINTS.PERMISSION_SETS.LIST, filters, isPermissionSet),
    get: (id: UUID) => getOne(ENDPOINTS.PERMISSION_SETS.DETAIL(id), isPermissionSet),
    create: (input: PermissionSetCreateInput) => postOne(ENDPOINTS.PERMISSION_SETS.CREATE, input, isPermissionSet),
    update: (id: UUID, input: PermissionSetUpdateInput) => patchOne(ENDPOINTS.PERMISSION_SETS.UPDATE(id), input, isPermissionSet),
    delete: (id: UUID) => apiClient.delete<void>(ENDPOINTS.PERMISSION_SETS.DELETE(id)),
    replacePermissions: (id: UUID, input: ReplacePermissionSetPermissionsInput) => putOne(ENDPOINTS.PERMISSION_SETS.PERMISSIONS(id), input, isPermissionSet),
  },
  userPermissionSets: {
    list: (filters: AssignmentFilters = {}) => getPage(ENDPOINTS.USER_PERMISSION_SETS.LIST, filters, isUserPermissionSet),
    get: (id: UUID) => getOne(ENDPOINTS.USER_PERMISSION_SETS.DETAIL(id), isUserPermissionSet),
    create: (input: UserPermissionSetCreateInput) => postOne(ENDPOINTS.USER_PERMISSION_SETS.CREATE, input, isUserPermissionSet),
    update: (id: UUID, input: UserPermissionSetUpdateInput) => patchOne(ENDPOINTS.USER_PERMISSION_SETS.UPDATE(id), input, isUserPermissionSet),
    revoke: (id: UUID) => apiClient.delete<void>(ENDPOINTS.USER_PERMISSION_SETS.DELETE(id)),
  },
  fieldSecurity: {
    list: (filters: FieldSecurityFilters = {}) => getPage(ENDPOINTS.FIELD_SECURITY.LIST, filters, isFieldSecurity),
    get: (id: UUID) => getOne(ENDPOINTS.FIELD_SECURITY.DETAIL(id), isFieldSecurity),
    create: (input: FieldSecurityInput) => postOne(ENDPOINTS.FIELD_SECURITY.CREATE, input, isFieldSecurity),
    update: (id: UUID, input: FieldSecurityUpdateInput) => patchOne(ENDPOINTS.FIELD_SECURITY.UPDATE(id), input, isFieldSecurity),
    delete: (id: UUID) => apiClient.delete<void>(ENDPOINTS.FIELD_SECURITY.DELETE(id)),
  },
  rowSecurity: {
    list: (filters: RowSecurityFilters = {}) => getPage(ENDPOINTS.ROW_SECURITY.LIST, filters, isRowSecurityRule),
    get: (id: UUID) => getOne(ENDPOINTS.ROW_SECURITY.DETAIL(id), isRowSecurityRule),
    create: (input: RowSecurityRuleInput) => postOne(ENDPOINTS.ROW_SECURITY.CREATE, input, isRowSecurityRule),
    update: (id: UUID, input: RowSecurityRuleUpdateInput) => patchOne(ENDPOINTS.ROW_SECURITY.UPDATE(id), input, isRowSecurityRule),
    delete: (id: UUID) => apiClient.delete<void>(ENDPOINTS.ROW_SECURITY.DELETE(id)),
  },
  securityProfiles: {
    list: (filters: SecurityProfileFilters = {}) => getPage(ENDPOINTS.SECURITY_PROFILES.LIST, filters, isSecurityProfile),
    get: (id: UUID) => getOne(ENDPOINTS.SECURITY_PROFILES.DETAIL(id), isSecurityProfile),
    create: (input: SecurityProfileInput) => postOne(ENDPOINTS.SECURITY_PROFILES.CREATE, input, isSecurityProfile),
    update: (id: UUID, input: SecurityProfileUpdateInput) => patchOne(ENDPOINTS.SECURITY_PROFILES.UPDATE(id), input, isSecurityProfile),
    delete: (id: UUID) => apiClient.delete<void>(ENDPOINTS.SECURITY_PROFILES.DELETE(id)),
  },
  profileAssignments: {
    list: (filters: AssignmentFilters = {}) => getPage(ENDPOINTS.PROFILE_ASSIGNMENTS.LIST, filters, isProfileAssignment),
    get: (id: UUID) => getOne(ENDPOINTS.PROFILE_ASSIGNMENTS.DETAIL(id), isProfileAssignment),
    create: (input: SecurityProfileAssignmentCreateInput) => postOne(ENDPOINTS.PROFILE_ASSIGNMENTS.CREATE, input, isProfileAssignment),
    update: (id: UUID, input: SecurityProfileAssignmentUpdateInput) => patchOne(ENDPOINTS.PROFILE_ASSIGNMENTS.UPDATE(id), input, isProfileAssignment),
    revoke: (id: UUID) => apiClient.delete<void>(ENDPOINTS.PROFILE_ASSIGNMENTS.DELETE(id)),
  },
  auditLogs: {
    list: (filters: AuditLogFilters = {}) => getPage(ENDPOINTS.AUDIT_LOGS.LIST, filters, isSecurityAuditLog),
    get: (id: UUID) => getOne(ENDPOINTS.AUDIT_LOGS.DETAIL(id), isSecurityAuditLog),
  },
  accessDecisions: {
    simulate: (input: AccessSimulationInput): Promise<GovernedResult<AccessDecision>> => postOne(ENDPOINTS.ACCESS_DECISIONS.SIMULATE, input, isAccessDecision),
  },
  health: (): Promise<GovernedResult<HealthStatus>> => getOne(ENDPOINTS.HEALTH, isHealthStatus),
} as const;

export type { ProfileType, RolePermission, V2Envelope };
