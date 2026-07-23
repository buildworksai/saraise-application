/**
 * Security & Access Control public frontend contract.
 *
 * This file deliberately does not depend on generated v1 OpenAPI types.  The
 * governed v2 API is validated at runtime at the service boundary so malformed
 * authorization data can never be mistaken for an empty or successful result.
 */

export type UUID = string;
export type ISODateTime = string;
export type RoleType = "system" | "functional" | "custom" | "temporary";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type Visibility = "visible" | "hidden" | "masked" | "redacted";
export type EditControl = "read_only" | "editable" | "required";
export type RuleType = "ownership" | "hierarchy" | "attribute" | "criteria";
export type ProfileType = "standard" | "privileged" | "restricted" | "high_security";
export type MfaRequired = "always" | "conditional" | "sensitive_actions" | "never";
export type ActorType = "user" | "system" | "agent";
export type Decision = "allow" | "deny";
export type ReasonCode = string;

export interface V2PageMeta {
  readonly count: number;
  readonly page: number;
  readonly page_size: number;
  readonly total_pages: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}

export interface V2Meta {
  readonly correlation_id: string;
  readonly timestamp: ISODateTime;
  readonly pagination?: V2PageMeta;
}

export interface V2Envelope<T> {
  readonly data: T;
  readonly meta: V2Meta;
}

export interface V2ErrorEnvelope {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly detail: unknown;
    readonly correlation_id: string;
  };
}

export interface PaginatedResult<T> {
  readonly items: readonly T[];
  readonly pagination: V2PageMeta;
  readonly correlationId: string;
  readonly timestamp: ISODateTime;
}

export interface GovernedResult<T> {
  readonly data: T;
  readonly correlationId: string;
  readonly timestamp: ISODateTime;
}

export interface Permission {
  readonly id: UUID;
  readonly module: string;
  readonly resource: string;
  readonly action: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly risk_level: RiskLevel;
  readonly created_at: ISODateTime;
}

export interface RolePermissionDecision {
  readonly id: UUID;
  readonly permission: Permission;
  readonly is_granted: boolean;
  readonly source: "direct" | "inherited" | "permission_set";
  readonly source_name?: string;
}

export interface RolePermission {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly role_id: UUID;
  readonly permission_id: UUID;
  readonly is_granted: boolean;
  readonly created_by: UUID | null;
  readonly updated_by: UUID | null;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
}

export interface Role {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly name: string;
  readonly code: string;
  readonly description: string;
  readonly role_type: RoleType;
  readonly parent_role_id: UUID | null;
  readonly parent_role_name?: string | null;
  readonly hierarchy_level: number;
  readonly is_active: boolean;
  readonly is_system: boolean;
  readonly is_deleted: boolean;
  readonly created_by: UUID | null;
  readonly updated_by: UUID | null;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly deleted_at: ISODateTime | null;
  readonly direct_permissions?: readonly RolePermissionDecision[];
  readonly inherited_permissions?: readonly RolePermissionDecision[];
  readonly denied_permissions?: readonly RolePermissionDecision[];
  readonly permission_set_permissions?: readonly RolePermissionDecision[];
  readonly assignment_count?: number;
}

export interface RoleCreateInput {
  readonly name: string;
  readonly code: string;
  readonly description?: string;
  readonly role_type: RoleType;
  readonly parent_role_id?: UUID | null;
}
export type RoleUpdateInput = Partial<RoleCreateInput> & { readonly is_active?: boolean };

export interface SetRolePermissionInput {
  readonly permission_id: UUID;
  readonly is_granted: boolean;
}

export interface UserRole {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly user_id: UUID;
  readonly user_display?: string;
  readonly role_id: UUID;
  readonly role_name?: string;
  readonly valid_from: ISODateTime;
  readonly valid_until: ISODateTime | null;
  readonly assigned_by: UUID;
  readonly reason: string;
  readonly revoked_at: ISODateTime | null;
  readonly revoked_by: UUID | null;
  readonly revocation_reason: string;
  readonly is_active: boolean;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
}
export interface UserRoleCreateInput {
  readonly user_id: UUID;
  readonly role_id: UUID;
  readonly valid_from?: ISODateTime;
  readonly valid_until?: ISODateTime | null;
  readonly reason: string;
}
export interface UserRoleUpdateInput {
  readonly valid_from?: ISODateTime;
  readonly valid_until?: ISODateTime | null;
  readonly reason?: string;
}

export interface PermissionSet {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly name: string;
  readonly description: string;
  readonly default_duration_days: number | null;
  readonly is_active: boolean;
  readonly is_deleted: boolean;
  readonly permission_ids: readonly UUID[];
  readonly permissions?: readonly Permission[];
  readonly active_grant_count?: number;
  readonly created_by: UUID | null;
  readonly updated_by: UUID | null;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly deleted_at: ISODateTime | null;
}
export interface PermissionSetCreateInput {
  readonly name: string;
  readonly description?: string;
  readonly default_duration_days?: number | null;
  readonly is_active?: boolean;
  readonly permission_ids?: readonly UUID[];
}
export type PermissionSetUpdateInput = Partial<Omit<PermissionSetCreateInput, "permission_ids">>;
export interface ReplacePermissionSetPermissionsInput { readonly permission_ids: readonly UUID[] }

export interface UserPermissionSet {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly user_id: UUID;
  readonly user_display?: string;
  readonly permission_set_id: UUID;
  readonly permission_set_name?: string;
  readonly granted_at: ISODateTime;
  readonly expires_at: ISODateTime;
  readonly granted_by: UUID;
  readonly reason: string;
  readonly revoked_at: ISODateTime | null;
  readonly revoked_by: UUID | null;
  readonly revocation_reason: string;
  readonly is_active: boolean;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
}
export interface UserPermissionSetCreateInput {
  readonly user_id: UUID;
  readonly permission_set_id: UUID;
  readonly expires_at?: ISODateTime;
  readonly duration_days?: number;
  readonly reason: string;
}
export interface UserPermissionSetUpdateInput {
  readonly expires_at?: ISODateTime;
  readonly reason?: string;
}

export interface FieldSecurity {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly module: string;
  readonly resource: string;
  readonly field: string;
  readonly role_id: UUID;
  readonly role_name?: string;
  readonly visibility: Visibility;
  readonly edit_control: EditControl;
  readonly mask_pattern: string;
  readonly is_active: boolean;
  readonly is_deleted: boolean;
  readonly created_by: UUID | null;
  readonly updated_by: UUID | null;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly deleted_at: ISODateTime | null;
}
export interface FieldSecurityInput {
  readonly module: string;
  readonly resource: string;
  readonly field: string;
  readonly role_id: UUID;
  readonly visibility: Visibility;
  readonly edit_control: EditControl;
  readonly mask_pattern?: string;
  readonly is_active?: boolean;
}
export type FieldSecurityUpdateInput = Partial<FieldSecurityInput>;

export type PredicateValue = string | number | boolean | null;
export type PredicateSubjectReference = { readonly subject: string };
export type RowPredicate =
  | { readonly op: "and" | "or"; readonly args: readonly RowPredicate[] }
  | { readonly op: "not"; readonly arg: RowPredicate }
  | { readonly op: "eq"; readonly field: string; readonly value: PredicateValue | PredicateSubjectReference }
  | { readonly op: "in"; readonly field: string; readonly value: readonly PredicateValue[] }
  | { readonly op: "is_null" | "owner" | "tenant"; readonly field: string };

export interface RowSecurityRule {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly module: string;
  readonly resource: string;
  readonly role_id: UUID;
  readonly role_name?: string;
  readonly rule_type: RuleType;
  readonly filter_criteria: RowPredicate;
  readonly priority: number;
  readonly is_active: boolean;
  readonly version: number;
  readonly is_deleted: boolean;
  readonly created_by: UUID | null;
  readonly updated_by: UUID | null;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly deleted_at: ISODateTime | null;
}
export interface RowSecurityRuleInput {
  readonly module: string;
  readonly resource: string;
  readonly role_id: UUID;
  readonly rule_type: RuleType;
  readonly filter_criteria: RowPredicate;
  readonly priority?: number;
  readonly is_active?: boolean;
}
export type RowSecurityRuleUpdateInput = Partial<RowSecurityRuleInput>;

export interface TimeWindow { readonly start: string; readonly end: string }
export interface TimeRestrictions {
  readonly timezone: string;
  readonly weekdays: readonly number[];
  readonly windows: readonly TimeWindow[];
}
export interface PasswordPolicy {
  readonly minimum_length?: number;
  readonly require_uppercase?: boolean;
  readonly require_lowercase?: boolean;
  readonly require_number?: boolean;
  readonly require_symbol?: boolean;
  readonly history_count?: number;
}

export interface SecurityProfile {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly name: string;
  readonly description: string;
  readonly profile_type: ProfileType;
  readonly ip_whitelist: readonly string[];
  readonly ip_blacklist: readonly string[];
  readonly allowed_countries: readonly string[];
  readonly blocked_countries: readonly string[];
  readonly time_restrictions: TimeRestrictions;
  readonly mfa_required: MfaRequired;
  readonly allowed_mfa_methods: readonly string[];
  readonly password_policy: PasswordPolicy;
  readonly session_timeout_minutes: number;
  readonly absolute_session_timeout_hours: number;
  readonly max_concurrent_sessions: number;
  readonly download_allowed: boolean;
  readonly print_allowed: boolean;
  readonly copy_paste_allowed: boolean;
  readonly mobile_access_allowed: boolean;
  readonly login_notification: boolean;
  readonly access_notification: boolean;
  readonly is_active: boolean;
  readonly is_deleted: boolean;
  readonly assignment_count?: number;
  readonly created_by: UUID | null;
  readonly updated_by: UUID | null;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly deleted_at: ISODateTime | null;
}
export interface SecurityProfileInput {
  readonly name: string;
  readonly description?: string;
  readonly profile_type: ProfileType;
  readonly ip_whitelist?: readonly string[];
  readonly ip_blacklist?: readonly string[];
  readonly allowed_countries?: readonly string[];
  readonly blocked_countries?: readonly string[];
  readonly time_restrictions?: TimeRestrictions;
  readonly mfa_required: MfaRequired;
  readonly allowed_mfa_methods?: readonly string[];
  readonly password_policy?: PasswordPolicy;
  readonly session_timeout_minutes: number;
  readonly absolute_session_timeout_hours: number;
  readonly max_concurrent_sessions: number;
  readonly download_allowed?: boolean;
  readonly print_allowed?: boolean;
  readonly copy_paste_allowed?: boolean;
  readonly mobile_access_allowed?: boolean;
  readonly login_notification?: boolean;
  readonly access_notification?: boolean;
  readonly is_active?: boolean;
}
export type SecurityProfileUpdateInput = Partial<SecurityProfileInput>;

export interface SecurityProfileAssignment {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly security_profile_id: UUID;
  readonly security_profile_name?: string;
  readonly user_id: UUID | null;
  readonly user_display?: string | null;
  readonly role_id: UUID | null;
  readonly role_name?: string | null;
  readonly precedence: number;
  readonly valid_from: ISODateTime;
  readonly valid_until: ISODateTime | null;
  readonly assigned_by: UUID;
  readonly reason: string;
  readonly revoked_at: ISODateTime | null;
  readonly revoked_by: UUID | null;
  readonly revocation_reason: string;
  readonly is_active: boolean;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
}
export interface SecurityProfileAssignmentCreateInput {
  readonly security_profile_id: UUID;
  readonly user_id?: UUID | null;
  readonly role_id?: UUID | null;
  readonly precedence?: number;
  readonly valid_from?: ISODateTime;
  readonly valid_until?: ISODateTime | null;
  readonly reason: string;
}
export interface SecurityProfileAssignmentUpdateInput {
  readonly precedence?: number;
  readonly valid_from?: ISODateTime;
  readonly valid_until?: ISODateTime | null;
  readonly reason?: string;
}

export interface SecurityAuditLog {
  readonly id: UUID;
  readonly action: string;
  readonly actor_type: ActorType;
  readonly resource_type: string;
  readonly resource_id: UUID | null;
  readonly decision: Decision | null;
  readonly reason_codes: readonly ReasonCode[];
  readonly timestamp: ISODateTime;
  readonly details: Readonly<Record<string, unknown>>;
  readonly correlation_id: string;
  /** Present only on separately authorized diagnostic representations. */
  readonly tenant_id?: UUID;
  readonly ip_address?: string | null;
  readonly user_agent?: string;
  readonly outbox_event_id?: UUID | null;
}

export interface FieldAccessDecision {
  readonly field: string;
  readonly visibility: Visibility;
  readonly edit_control: EditControl;
  readonly mask_pattern?: string;
  readonly reason_codes: readonly ReasonCode[];
  readonly applied_policy_ids: readonly UUID[];
}
export interface RowAccessExplanation {
  readonly allowed: boolean;
  readonly applied_rule_ids: readonly UUID[];
  readonly reason_codes: readonly ReasonCode[];
  readonly explanation: string;
}
export interface CommercialDecision {
  readonly required: boolean;
  readonly allowed: boolean;
  readonly reason_code?: ReasonCode;
  readonly remaining?: number | null;
}
export interface AccessDecision {
  readonly subject_id: UUID;
  readonly permission_code: string;
  readonly decision: Decision;
  readonly reason_codes: readonly ReasonCode[];
  readonly applied_policy_ids: readonly UUID[];
  readonly entitlement: CommercialDecision;
  readonly quota: CommercialDecision;
  readonly field_decisions: readonly FieldAccessDecision[];
  readonly row_explanation: RowAccessExplanation | null;
  readonly audit_log_id: UUID | null;
  readonly correlation_id: string;
  readonly evaluated_at: ISODateTime;
}
export interface AccessSimulationInput {
  readonly subject_id: UUID;
  readonly permission_code: string;
  readonly resource_context: Readonly<Record<string, string | number | boolean | null>>;
}

export interface HealthStatus {
  readonly status: "ready" | "not_ready";
  readonly correlation_id: string;
  readonly components: Readonly<Record<string, "ready" | "not_ready" | "degraded">>;
}

export type SecuritySemanticToken = "status-success" | "status-danger" | "status-warning" | "status-neutral";
export interface SecurityConfigurationLimits {
  readonly rate_requests_per_minute: number;
  readonly correlation_id_max_length: number;
  readonly correlation_id_pattern: string;
  readonly role_hierarchy_max_depth: number;
  readonly permission_set_duration_min_days: number;
  readonly permission_set_duration_max_days: number;
  readonly profile_idle_timeout_min_minutes: number;
  readonly profile_idle_timeout_max_minutes: number;
  readonly profile_absolute_timeout_min_hours: number;
  readonly profile_absolute_timeout_max_hours: number;
  readonly profile_concurrent_sessions_min: number;
  readonly profile_concurrent_sessions_max: number;
  readonly predicate_max_depth: number;
  readonly predicate_max_nodes: number;
  readonly predicate_max_in_values: number;
  readonly predicate_hard_max_depth: number;
  readonly predicate_hard_max_nodes: number;
  readonly predicate_hard_max_in_values: number;
  readonly predicate_compound_max_arguments: number;
  readonly audit_payload_max_bytes: number;
  readonly policy_array_max_entries: number;
  readonly mfa_methods_max_entries: number;
  readonly audit_redaction_max_depth: number;
  readonly audit_collection_max_entries: number;
  readonly audit_string_max_length: number;
  readonly required_text_max_length: number;
  readonly audit_reason_codes_max_entries: number;
  readonly user_agent_max_length: number;
  readonly audit_default_window_days: number;
  readonly audit_max_window_days: number;
  readonly row_priority_min: number;
  readonly row_priority_max: number;
  readonly name_min_length: number;
  readonly name_max_length: number;
  readonly description_max_length: number;
  readonly list_page_size: number;
  readonly lookup_page_size: number;
}
export interface SecurityProfileDefaults {
  readonly profile_type: ProfileType;
  readonly mfa_required: MfaRequired;
  readonly allowed_mfa_methods: readonly string[];
  readonly time_restrictions: TimeRestrictions;
  readonly session_timeout_minutes: number;
  readonly absolute_session_timeout_hours: number;
  readonly max_concurrent_sessions: number;
  readonly download_allowed: boolean;
  readonly print_allowed: boolean;
  readonly copy_paste_allowed: boolean;
  readonly mobile_access_allowed: boolean;
  readonly login_notification: boolean;
  readonly access_notification: boolean;
}
export interface SecurityConfigurationDefaults {
  readonly field_visibility: Visibility;
  readonly field_edit_control: EditControl;
  readonly row_rule_type: RuleType;
  readonly row_rule_priority: number;
  readonly row_owner_field: string;
  readonly profile_assignment_precedence: number;
  readonly security_profile: SecurityProfileDefaults;
  readonly automatic_revocation_reason: string;
  readonly mfa_precedence: Readonly<Record<MfaRequired, number>>;
  readonly allowed_mfa_methods: readonly string[];
}
export interface SecurityConfigurationOrdering {
  readonly roles: readonly string[];
  readonly role_assignments: readonly string[];
  readonly permission_sets: readonly string[];
  readonly permission_set_grants: readonly string[];
  readonly field_rules: readonly string[];
  readonly row_rules: readonly string[];
  readonly security_profiles: readonly string[];
  readonly profile_assignments: readonly string[];
  readonly audit_logs: readonly string[];
}
export interface SecurityConfigurationRollout {
  readonly enabled: boolean;
  readonly percentage: number;
  readonly role_ids: readonly UUID[];
  readonly cohorts: readonly string[];
}
export interface SecurityConfigurationDocument {
  readonly limits: SecurityConfigurationLimits;
  readonly defaults: SecurityConfigurationDefaults;
  readonly ordering: SecurityConfigurationOrdering;
  readonly resilience: {
    readonly connect_timeout_seconds: number;
    readonly read_timeout_seconds: number;
    readonly max_retries: number;
    readonly failure_threshold: number;
    readonly reset_timeout_seconds: number;
  };
  readonly remote_context_keys: readonly string[];
  readonly ui: { readonly loading_skeleton_rows: number; readonly audit_timeline_page_size: number };
  readonly semantic_tokens: {
    readonly success: SecuritySemanticToken;
    readonly danger: SecuritySemanticToken;
    readonly warning: SecuritySemanticToken;
    readonly neutral: SecuritySemanticToken;
  };
  readonly commercial_controls: { readonly entitlement: string; readonly quota: string };
  readonly baseline_profile: Omit<SecurityProfileDefaults, "profile_type" | "time_restrictions" | "login_notification" | "access_notification"> & {
    readonly ip_whitelist: readonly string[];
    readonly ip_blacklist: readonly string[];
    readonly allowed_countries: readonly string[];
    readonly blocked_countries: readonly string[];
  };
  readonly feature_flags: Readonly<Record<string, { readonly enabled: boolean; readonly percentage: number; readonly roles: readonly UUID[]; readonly cohorts: readonly string[] }>>;
}
export interface SecurityConfiguration {
  readonly id: UUID;
  readonly environment: string;
  readonly version: number;
  readonly document: SecurityConfigurationDocument;
  readonly rollout: SecurityConfigurationRollout;
  readonly updated_by: UUID;
  readonly correlation_id: string;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
}
export interface SecurityConfigurationVersion {
  readonly id: UUID;
  readonly version: number;
  readonly environment: string;
  readonly previous_document: SecurityConfigurationDocument | null;
  readonly current_document: SecurityConfigurationDocument;
  readonly previous_rollout: SecurityConfigurationRollout | null;
  readonly current_rollout: SecurityConfigurationRollout;
  readonly actor_id: UUID;
  readonly correlation_id: string;
  readonly reason: string;
  readonly change_kind: string;
  readonly created_at: ISODateTime;
}
export interface SecurityConfigurationWriteInput { readonly document: SecurityConfigurationDocument; readonly environment: string; readonly reason: string; readonly rollout?: SecurityConfigurationRollout }
export interface SecurityConfigurationPreviewInput { readonly document: SecurityConfigurationDocument; readonly rollout?: SecurityConfigurationRollout }
export interface SecurityConfigurationPreview {
  readonly valid: boolean;
  readonly diff: readonly unknown[];
  readonly normalized_document: SecurityConfigurationDocument;
  readonly normalized_rollout: SecurityConfigurationRollout;
}
export interface SecurityConfigurationExport {
  readonly schema_version: string;
  readonly environment: string;
  readonly version: number;
  readonly document: SecurityConfigurationDocument;
  readonly rollout: SecurityConfigurationRollout;
}
export interface SecurityConfigurationRollbackInput { readonly reason: string }
export interface SecurityConfigurationRolloutInput { readonly rollout: SecurityConfigurationRollout; readonly reason: string }
export interface DeletionReasonInput { readonly reason: string }

export interface PageFilters { readonly page?: number; readonly page_size?: number; readonly search?: string; readonly ordering?: string }
export interface RoleFilters extends PageFilters { readonly role_type?: RoleType; readonly is_active?: boolean; readonly parent_role_id?: UUID }
export interface PermissionFilters extends PageFilters { readonly module?: string; readonly resource?: string; readonly action?: string; readonly risk_level?: RiskLevel }
export interface AssignmentFilters extends PageFilters { readonly user_id?: UUID; readonly role_id?: UUID; readonly permission_set_id?: UUID; readonly profile_id?: UUID; readonly active_at?: ISODateTime; readonly revoked?: boolean }
export interface PermissionSetFilters extends PageFilters { readonly is_active?: boolean }
export interface FieldSecurityFilters extends PageFilters { readonly module?: string; readonly resource?: string; readonly field?: string; readonly role_id?: UUID; readonly visibility?: Visibility; readonly edit_control?: EditControl; readonly is_active?: boolean }
export interface RowSecurityFilters extends PageFilters { readonly module?: string; readonly resource?: string; readonly role_id?: UUID; readonly rule_type?: RuleType; readonly is_active?: boolean }
export interface SecurityProfileFilters extends PageFilters { readonly profile_type?: ProfileType; readonly mfa_required?: MfaRequired; readonly is_active?: boolean }
export interface AuditLogFilters extends PageFilters { readonly from?: ISODateTime; readonly to?: ISODateTime; readonly action?: string; readonly actor_type?: ActorType; readonly actor_id?: UUID; readonly resource_type?: string; readonly resource_id?: UUID; readonly decision?: Decision; readonly correlation_id?: string }

const API_ROOT = "/api/v2/security-access-control" as const;
export const ENDPOINTS = {
  ROLES: { LIST: `${API_ROOT}/roles/`, CREATE: `${API_ROOT}/roles/`, DETAIL: (id: UUID) => `${API_ROOT}/roles/${id}/` as const, UPDATE: (id: UUID) => `${API_ROOT}/roles/${id}/` as const, DELETE: (id: UUID) => `${API_ROOT}/roles/${id}/` as const, PERMISSIONS: (id: UUID) => `${API_ROOT}/roles/${id}/permissions/` as const, PERMISSION: (id: UUID, permissionId: UUID) => `${API_ROOT}/roles/${id}/permissions/${permissionId}/` as const },
  PERMISSIONS: { LIST: `${API_ROOT}/permissions/`, DETAIL: (id: UUID) => `${API_ROOT}/permissions/${id}/` as const },
  USER_ROLES: { LIST: `${API_ROOT}/user-roles/`, CREATE: `${API_ROOT}/user-roles/`, DETAIL: (id: UUID) => `${API_ROOT}/user-roles/${id}/` as const, UPDATE: (id: UUID) => `${API_ROOT}/user-roles/${id}/` as const, DELETE: (id: UUID) => `${API_ROOT}/user-roles/${id}/` as const },
  PERMISSION_SETS: { LIST: `${API_ROOT}/permission-sets/`, CREATE: `${API_ROOT}/permission-sets/`, DETAIL: (id: UUID) => `${API_ROOT}/permission-sets/${id}/` as const, UPDATE: (id: UUID) => `${API_ROOT}/permission-sets/${id}/` as const, DELETE: (id: UUID) => `${API_ROOT}/permission-sets/${id}/` as const, PERMISSIONS: (id: UUID) => `${API_ROOT}/permission-sets/${id}/permissions/` as const },
  USER_PERMISSION_SETS: { LIST: `${API_ROOT}/user-permission-sets/`, CREATE: `${API_ROOT}/user-permission-sets/`, DETAIL: (id: UUID) => `${API_ROOT}/user-permission-sets/${id}/` as const, UPDATE: (id: UUID) => `${API_ROOT}/user-permission-sets/${id}/` as const, DELETE: (id: UUID) => `${API_ROOT}/user-permission-sets/${id}/` as const },
  FIELD_SECURITY: { LIST: `${API_ROOT}/field-security/`, CREATE: `${API_ROOT}/field-security/`, DETAIL: (id: UUID) => `${API_ROOT}/field-security/${id}/` as const, UPDATE: (id: UUID) => `${API_ROOT}/field-security/${id}/` as const, DELETE: (id: UUID) => `${API_ROOT}/field-security/${id}/` as const },
  ROW_SECURITY: { LIST: `${API_ROOT}/row-security-rules/`, CREATE: `${API_ROOT}/row-security-rules/`, DETAIL: (id: UUID) => `${API_ROOT}/row-security-rules/${id}/` as const, UPDATE: (id: UUID) => `${API_ROOT}/row-security-rules/${id}/` as const, DELETE: (id: UUID) => `${API_ROOT}/row-security-rules/${id}/` as const },
  SECURITY_PROFILES: { LIST: `${API_ROOT}/security-profiles/`, CREATE: `${API_ROOT}/security-profiles/`, DETAIL: (id: UUID) => `${API_ROOT}/security-profiles/${id}/` as const, UPDATE: (id: UUID) => `${API_ROOT}/security-profiles/${id}/` as const, DELETE: (id: UUID) => `${API_ROOT}/security-profiles/${id}/` as const },
  PROFILE_ASSIGNMENTS: { LIST: `${API_ROOT}/security-profile-assignments/`, CREATE: `${API_ROOT}/security-profile-assignments/`, DETAIL: (id: UUID) => `${API_ROOT}/security-profile-assignments/${id}/` as const, UPDATE: (id: UUID) => `${API_ROOT}/security-profile-assignments/${id}/` as const, DELETE: (id: UUID) => `${API_ROOT}/security-profile-assignments/${id}/` as const },
  AUDIT_LOGS: { LIST: `${API_ROOT}/audit-logs/`, DETAIL: (id: UUID) => `${API_ROOT}/audit-logs/${id}/` as const },
  ACCESS_DECISIONS: { SIMULATE: `${API_ROOT}/access-decisions/simulate/` },
  CONFIGURATION: {
    CURRENT: `${API_ROOT}/configuration/`,
    PREVIEW: `${API_ROOT}/configuration/preview/`,
    VERSIONS: `${API_ROOT}/configuration/versions/`,
    ROLLBACK: (version: number) => `${API_ROOT}/configuration/versions/${version}/rollback/` as const,
    IMPORT: `${API_ROOT}/configuration/import/`,
    EXPORT: `${API_ROOT}/configuration/export/`,
    ROLLOUT: `${API_ROOT}/configuration/rollout/`,
  },
  HEALTH: `${API_ROOT}/health/`,
} as const;

export const ROUTES = {
  ROLES: "/security-access-control/roles", ROLE_CREATE: "/security-access-control/roles/create", ROLE_DETAIL: (id: UUID) => `/security-access-control/roles/${id}` as const, ROLE_EDIT: (id: UUID) => `/security-access-control/roles/${id}/edit` as const,
  PERMISSIONS: "/security-access-control/permissions", PERMISSION_DETAIL: (id: UUID) => `/security-access-control/permissions/${id}` as const,
  ASSIGNMENTS: "/security-access-control/assignments", USER_ROLE_CREATE: "/security-access-control/assignments/create", USER_ROLE_DETAIL: (id: UUID) => `/security-access-control/assignments/${id}` as const, USER_ROLE_EDIT: (id: UUID) => `/security-access-control/assignments/${id}/edit` as const,
  PERMISSION_SETS: "/security-access-control/permission-sets", PERMISSION_SET_CREATE: "/security-access-control/permission-sets/create", PERMISSION_SET_DETAIL: (id: UUID) => `/security-access-control/permission-sets/${id}` as const, PERMISSION_SET_EDIT: (id: UUID) => `/security-access-control/permission-sets/${id}/edit` as const,
  USER_PERMISSION_SETS: "/security-access-control/assignments/permission-set-grants", USER_PERMISSION_SET_CREATE: "/security-access-control/assignments/permission-set-grants/create", USER_PERMISSION_SET_DETAIL: (id: UUID) => `/security-access-control/assignments/permission-set-grants/${id}` as const, USER_PERMISSION_SET_EDIT: (id: UUID) => `/security-access-control/assignments/permission-set-grants/${id}/edit` as const,
  FIELD_SECURITY: "/security-access-control/field-security", FIELD_SECURITY_CREATE: "/security-access-control/field-security/create", FIELD_SECURITY_DETAIL: (id: UUID) => `/security-access-control/field-security/${id}` as const, FIELD_SECURITY_EDIT: (id: UUID) => `/security-access-control/field-security/${id}/edit` as const,
  ROW_SECURITY: "/security-access-control/row-security", ROW_SECURITY_CREATE: "/security-access-control/row-security/create", ROW_SECURITY_DETAIL: (id: UUID) => `/security-access-control/row-security/${id}` as const, ROW_SECURITY_EDIT: (id: UUID) => `/security-access-control/row-security/${id}/edit` as const,
  SECURITY_PROFILES: "/security-access-control/security-profiles", SECURITY_PROFILE_CREATE: "/security-access-control/security-profiles/create", SECURITY_PROFILE_DETAIL: (id: UUID) => `/security-access-control/security-profiles/${id}` as const, SECURITY_PROFILE_EDIT: (id: UUID) => `/security-access-control/security-profiles/${id}/edit` as const,
  PROFILE_ASSIGNMENTS: "/security-access-control/assignments/profile-assignments", PROFILE_ASSIGNMENT_CREATE: "/security-access-control/assignments/profile-assignments/create", PROFILE_ASSIGNMENT_DETAIL: (id: UUID) => `/security-access-control/assignments/profile-assignments/${id}` as const, PROFILE_ASSIGNMENT_EDIT: (id: UUID) => `/security-access-control/assignments/profile-assignments/${id}/edit` as const,
  AUDIT_LOGS: "/security-access-control/audit-logs", AUDIT_LOG_DETAIL: (id: UUID) => `/security-access-control/audit-logs/${id}` as const,
  ACCESS_SIMULATOR: "/security-access-control/access-simulator",
  CONFIGURATION: "/security-access-control/configuration",
} as const;

function stableFilters(filters: object): readonly (readonly [string, string])[] {
  return Object.entries(filters).filter((entry) => entry[1] !== undefined && entry[1] !== "").map(([key, value]) => [key, String(value)] as const).sort(([left], [right]) => left.localeCompare(right));
}
export const QUERY_KEYS = {
  root: ["security-access-control"] as const,
  roles: (filters: RoleFilters = {}) => [...QUERY_KEYS.root, "roles", stableFilters(filters)] as const,
  role: (id: UUID) => [...QUERY_KEYS.root, "role", id] as const,
  permissions: (filters: PermissionFilters = {}) => [...QUERY_KEYS.root, "permissions", stableFilters(filters)] as const,
  permission: (id: UUID) => [...QUERY_KEYS.root, "permission", id] as const,
  userRoles: (filters: AssignmentFilters = {}) => [...QUERY_KEYS.root, "user-roles", stableFilters(filters)] as const,
  userRole: (id: UUID) => [...QUERY_KEYS.root, "user-role", id] as const,
  permissionSets: (filters: PermissionSetFilters = {}) => [...QUERY_KEYS.root, "permission-sets", stableFilters(filters)] as const,
  permissionSet: (id: UUID) => [...QUERY_KEYS.root, "permission-set", id] as const,
  userPermissionSets: (filters: AssignmentFilters = {}) => [...QUERY_KEYS.root, "user-permission-sets", stableFilters(filters)] as const,
  userPermissionSet: (id: UUID) => [...QUERY_KEYS.root, "user-permission-set", id] as const,
  fieldRules: (filters: FieldSecurityFilters = {}) => [...QUERY_KEYS.root, "field-security", stableFilters(filters)] as const,
  fieldRule: (id: UUID) => [...QUERY_KEYS.root, "field-security", id] as const,
  rowRules: (filters: RowSecurityFilters = {}) => [...QUERY_KEYS.root, "row-security", stableFilters(filters)] as const,
  rowRule: (id: UUID) => [...QUERY_KEYS.root, "row-security", id] as const,
  profiles: (filters: SecurityProfileFilters = {}) => [...QUERY_KEYS.root, "profiles", stableFilters(filters)] as const,
  profile: (id: UUID) => [...QUERY_KEYS.root, "profile", id] as const,
  profileAssignments: (filters: AssignmentFilters = {}) => [...QUERY_KEYS.root, "profile-assignments", stableFilters(filters)] as const,
  profileAssignment: (id: UUID) => [...QUERY_KEYS.root, "profile-assignment", id] as const,
  auditLogs: (filters: AuditLogFilters = {}) => [...QUERY_KEYS.root, "audit-logs", stableFilters(filters)] as const,
  auditLog: (id: UUID) => [...QUERY_KEYS.root, "audit-log", id] as const,
  configuration: () => [...QUERY_KEYS.root, "configuration"] as const,
  configurationVersions: () => [...QUERY_KEYS.root, "configuration", "versions"] as const,
} as const;

export function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
export function isString(value: unknown): value is string { return typeof value === "string"; }
function isNumber(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }
function isBoolean(value: unknown): value is boolean { return typeof value === "boolean"; }
function isNullableString(value: unknown): value is string | null { return value === null || isString(value); }
function isStringArray(value: unknown): value is readonly string[] { return Array.isArray(value) && value.every(isString); }
function hasEntityCore(value: unknown): value is Record<string, unknown> & { id: string } { return isRecord(value) && isString(value.id); }
function enumGuard<const T extends readonly string[]>(value: unknown, values: T): value is T[number] { return isString(value) && values.includes(value); }

export function isV2PageMeta(value: unknown): value is V2PageMeta { return isRecord(value) && isNumber(value.count) && isNumber(value.page) && isNumber(value.page_size) && isNumber(value.total_pages) && isBoolean(value.has_next) && isBoolean(value.has_previous); }
export function isV2Meta(value: unknown): value is V2Meta { return isRecord(value) && isString(value.correlation_id) && isString(value.timestamp) && (value.pagination === undefined || isV2PageMeta(value.pagination)); }
export function isVisibility(value: unknown): value is Visibility { return enumGuard(value, ["visible", "hidden", "masked", "redacted"] as const); }
export function isEditControl(value: unknown): value is EditControl { return enumGuard(value, ["read_only", "editable", "required"] as const); }
export function isPermission(value: unknown): value is Permission { return hasEntityCore(value) && isString(value.module) && isString(value.resource) && isString(value.action) && isString(value.name) && enumGuard(value.risk_level, ["low", "medium", "high", "critical"] as const); }
export function isRole(value: unknown): value is Role { return hasEntityCore(value) && isString(value.name) && isString(value.code) && enumGuard(value.role_type, ["system", "functional", "custom", "temporary"] as const) && isBoolean(value.is_active) && isNumber(value.hierarchy_level); }
export function isRolePermission(value: unknown): value is RolePermission { return hasEntityCore(value) && isString(value.role_id) && isString(value.permission_id) && isBoolean(value.is_granted); }
export function isUserRole(value: unknown): value is UserRole { return hasEntityCore(value) && isString(value.user_id) && isString(value.role_id) && isString(value.valid_from) && isNullableString(value.valid_until) && isBoolean(value.is_active); }
export function isPermissionSet(value: unknown): value is PermissionSet { return hasEntityCore(value) && isString(value.name) && isBoolean(value.is_active) && isStringArray(value.permission_ids); }
export function isUserPermissionSet(value: unknown): value is UserPermissionSet { return hasEntityCore(value) && isString(value.user_id) && isString(value.permission_set_id) && isString(value.expires_at) && isBoolean(value.is_active); }
export function isFieldSecurity(value: unknown): value is FieldSecurity { return hasEntityCore(value) && isString(value.module) && isString(value.resource) && isString(value.field) && isString(value.role_id) && isVisibility(value.visibility) && isEditControl(value.edit_control); }

// Recursive discriminated-union validation necessarily visits every supported node.
// eslint-disable-next-line complexity
export function isRowPredicate(value: unknown): value is RowPredicate {
  if (!isRecord(value) || !isString(value.op)) return false;
  if (value.op === "and" || value.op === "or") return Array.isArray(value.args) && value.args.length > 0 && value.args.every((item) => isRowPredicate(item));
  if (value.op === "not") return isRowPredicate(value.arg);
  if (!isString(value.field)) return false;
  if (value.op === "eq") return isRecord(value.value) ? isString(value.value.subject) && Object.keys(value.value).length === 1 : value.value === null || ["string", "number", "boolean"].includes(typeof value.value);
  if (value.op === "in") return Array.isArray(value.value) && value.value.length > 0 && value.value.every((item) => item === null || ["string", "number", "boolean"].includes(typeof item));
  return value.op === "is_null" || value.op === "owner" || value.op === "tenant";
}
export function isRowSecurityRule(value: unknown): value is RowSecurityRule { return hasEntityCore(value) && isString(value.module) && isString(value.resource) && isString(value.role_id) && enumGuard(value.rule_type, ["ownership", "hierarchy", "attribute", "criteria"] as const) && isRowPredicate(value.filter_criteria) && isNumber(value.version); }
export function isSecurityProfile(value: unknown): value is SecurityProfile { return hasEntityCore(value) && isString(value.name) && enumGuard(value.profile_type, ["standard", "privileged", "restricted", "high_security"] as const) && enumGuard(value.mfa_required, ["always", "conditional", "sensitive_actions", "never"] as const) && isNumber(value.session_timeout_minutes) && isBoolean(value.is_active); }
export function isProfileAssignment(value: unknown): value is SecurityProfileAssignment { return hasEntityCore(value) && isString(value.security_profile_id) && isNullableString(value.user_id) && isNullableString(value.role_id) && ((value.user_id === null) !== (value.role_id === null)) && isBoolean(value.is_active); }
export function isSecurityAuditLog(value: unknown): value is SecurityAuditLog { return hasEntityCore(value) && isString(value.action) && enumGuard(value.actor_type, ["user", "system", "agent"] as const) && isString(value.resource_type) && isString(value.timestamp) && isStringArray(value.reason_codes) && isString(value.correlation_id) && isRecord(value.details); }
function isCommercialDecision(value: unknown): value is CommercialDecision { return isRecord(value) && isBoolean(value.required) && isBoolean(value.allowed); }
function isFieldAccessDecision(value: unknown): value is FieldAccessDecision { return isRecord(value) && isString(value.field) && isVisibility(value.visibility) && isEditControl(value.edit_control) && isStringArray(value.reason_codes) && isStringArray(value.applied_policy_ids); }
function isRowExplanation(value: unknown): value is RowAccessExplanation { return isRecord(value) && isBoolean(value.allowed) && isStringArray(value.applied_rule_ids) && isStringArray(value.reason_codes) && isString(value.explanation); }
export function isAccessDecision(value: unknown): value is AccessDecision { return isRecord(value) && isString(value.subject_id) && isString(value.permission_code) && enumGuard(value.decision, ["allow", "deny"] as const) && isStringArray(value.reason_codes) && isStringArray(value.applied_policy_ids) && isCommercialDecision(value.entitlement) && isCommercialDecision(value.quota) && Array.isArray(value.field_decisions) && value.field_decisions.every(isFieldAccessDecision) && (value.row_explanation === null || isRowExplanation(value.row_explanation)) && isString(value.correlation_id) && isString(value.evaluated_at); }
export function isHealthStatus(value: unknown): value is HealthStatus { return isRecord(value) && enumGuard(value.status, ["ready", "not_ready"] as const) && isString(value.correlation_id) && isRecord(value.components); }
export function isSecurityConfigurationDocument(value: unknown): value is SecurityConfigurationDocument { return isRecord(value) && isRecord(value.limits) && isNumber(value.limits.list_page_size) && isRecord(value.defaults) && isRecord(value.defaults.security_profile) && isRecord(value.ordering) && isRecord(value.resilience) && Array.isArray(value.remote_context_keys) && isRecord(value.ui) && isNumber(value.ui.loading_skeleton_rows) && isRecord(value.semantic_tokens) && isRecord(value.commercial_controls) && isRecord(value.baseline_profile) && isRecord(value.feature_flags); }
export function isSecurityConfigurationRollout(value: unknown): value is SecurityConfigurationRollout { return isRecord(value) && isBoolean(value.enabled) && isNumber(value.percentage) && isStringArray(value.role_ids) && isStringArray(value.cohorts); }
export function isSecurityConfiguration(value: unknown): value is SecurityConfiguration { return hasEntityCore(value) && isString(value.environment) && isNumber(value.version) && isSecurityConfigurationDocument(value.document) && isSecurityConfigurationRollout(value.rollout) && isString(value.updated_by) && isString(value.correlation_id) && isString(value.created_at) && isString(value.updated_at); }
export function isSecurityConfigurationVersion(value: unknown): value is SecurityConfigurationVersion { return hasEntityCore(value) && isNumber(value.version) && isString(value.environment) && (value.previous_document === null || isSecurityConfigurationDocument(value.previous_document)) && isSecurityConfigurationDocument(value.current_document) && (value.previous_rollout === null || isSecurityConfigurationRollout(value.previous_rollout)) && isSecurityConfigurationRollout(value.current_rollout) && isString(value.actor_id) && isString(value.correlation_id) && isString(value.reason) && isString(value.change_kind) && isString(value.created_at); }
export function isSecurityConfigurationPreview(value: unknown): value is SecurityConfigurationPreview { return isRecord(value) && isBoolean(value.valid) && Array.isArray(value.diff) && isSecurityConfigurationDocument(value.normalized_document) && isSecurityConfigurationRollout(value.normalized_rollout); }
export function isSecurityConfigurationExport(value: unknown): value is SecurityConfigurationExport { return isRecord(value) && isString(value.schema_version) && isString(value.environment) && isNumber(value.version) && isSecurityConfigurationDocument(value.document) && isSecurityConfigurationRollout(value.rollout); }
