import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type * as ApiClientExports from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import type { RowPredicate } from "../contracts";
import { securityService } from "./security-service";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("@/services/api-client", async (load) => { const actual = await load<typeof ApiClientExports>(); return { ...actual, apiClient: api }; });

const pagination = { count: 1, page: 1, page_size: 25, total_pages: 1, has_next: false, has_previous: false };
const meta = { correlation_id: "corr-security-1", timestamp: "2026-07-22T00:00:00Z", pagination };
const role = { id: "role-1", name: "Administrator", code: "administrator", role_type: "custom", is_active: true, hierarchy_level: 0 };
const permission = { id: "permission-1", module: "security", resource: "roles", action: "read", name: "Read roles", risk_level: "medium" };
const userRole = { id: "user-role-1", user_id: "user-1", role_id: "role-1", valid_from: "2026-07-22T00:00:00Z", valid_until: null, is_active: true };
const permissionSet = { id: "set-1", name: "Support", is_active: true, permission_ids: ["permission-1"] };
const userSet = { id: "grant-1", user_id: "user-1", permission_set_id: "set-1", expires_at: "2026-08-22T00:00:00Z", is_active: true };
const fieldRule = { id: "field-1", module: "crm", resource: "contacts", field: "email", role_id: "role-1", visibility: "redacted", edit_control: "read_only" };
const predicate: RowPredicate = { op: "owner", field: "owner_id" };
const rowRule = { id: "row-1", module: "crm", resource: "contacts", role_id: "role-1", rule_type: "ownership", filter_criteria: predicate, version: 1 };
const profile = { id: "profile-1", name: "Restricted", profile_type: "restricted", mfa_required: "always", session_timeout_minutes: 15, is_active: true };
const profileAssignment = { id: "profile-assignment-1", security_profile_id: "profile-1", user_id: "user-1", role_id: null, is_active: true };
const audit = { id: "audit-1", action: "security.role.changed", actor_type: "user", actor_id: "user-1", resource_type: "role", timestamp: "2026-07-22T00:00:00Z", reason_codes: ["ROLE_CREATED"], correlation_id: "corr-security-1", details: {} };
const rolePermission = { id: "rp-1", role_id: "role-1", permission_id: "permission-1", is_granted: true };
const access = { subject_id: "user-1", permission_code: "security.roles:read", decision: "allow", reason_codes: ["EXPLICIT_GRANT"], applied_policy_ids: ["role-1"], entitlement: { required: false, allowed: true }, quota: { required: false, allowed: true }, field_decisions: [], row_explanation: null, correlation_id: "corr-security-1", evaluated_at: "2026-07-22T00:00:00Z" };
const health = { status: "ready", correlation_id: "corr-security-1", components: { database: "ready" } };
const envelope = (data: unknown, includePage = false) => ({ data, meta: includePage ? meta : { correlation_id: meta.correlation_id, timestamp: meta.timestamp } });

describe("securityService governed v2 integration", () => {
  beforeEach(() => vi.clearAllMocks());

  const listCases = [
    ["roles", role, () => securityService.roles.list({ search: "admin" }), ENDPOINTS.ROLES.LIST],
    ["permissions", permission, () => securityService.permissions.list({ module: "security" }), ENDPOINTS.PERMISSIONS.LIST],
    ["user roles", userRole, () => securityService.userRoles.list({ user_id: "user-1" }), ENDPOINTS.USER_ROLES.LIST],
    ["permission sets", permissionSet, () => securityService.permissionSets.list({ is_active: true }), ENDPOINTS.PERMISSION_SETS.LIST],
    ["user permission sets", userSet, () => securityService.userPermissionSets.list({ revoked: false }), ENDPOINTS.USER_PERMISSION_SETS.LIST],
    ["field rules", fieldRule, () => securityService.fieldSecurity.list({ visibility: "redacted" }), ENDPOINTS.FIELD_SECURITY.LIST],
    ["row rules", rowRule, () => securityService.rowSecurity.list({ rule_type: "ownership" }), ENDPOINTS.ROW_SECURITY.LIST],
    ["profiles", profile, () => securityService.securityProfiles.list({ profile_type: "restricted" }), ENDPOINTS.SECURITY_PROFILES.LIST],
    ["profile assignments", profileAssignment, () => securityService.profileAssignments.list({ profile_id: "profile-1" }), ENDPOINTS.PROFILE_ASSIGNMENTS.LIST],
    ["audit logs", audit, () => securityService.auditLogs.list({ correlation_id: "corr-security-1" }), ENDPOINTS.AUDIT_LOGS.LIST],
  ] as const;
  it.each(listCases)("parses paginated %s", async (_name, item, call, endpoint) => { api.get.mockResolvedValueOnce(envelope([item], true)); const result = await call(); expect(result.items).toEqual([item]); expect(result.pagination).toEqual(pagination); expect(result.correlationId).toBe("corr-security-1"); expect(api.get).toHaveBeenCalledWith(expect.stringContaining(endpoint)); });

  const getCases = [
    ["role", role, () => securityService.roles.get("role-1")], ["permission", permission, () => securityService.permissions.get("permission-1")], ["user role", userRole, () => securityService.userRoles.get("user-role-1")], ["permission set", permissionSet, () => securityService.permissionSets.get("set-1")], ["grant", userSet, () => securityService.userPermissionSets.get("grant-1")], ["field rule", fieldRule, () => securityService.fieldSecurity.get("field-1")], ["row rule", rowRule, () => securityService.rowSecurity.get("row-1")], ["profile", profile, () => securityService.securityProfiles.get("profile-1")], ["profile assignment", profileAssignment, () => securityService.profileAssignments.get("profile-assignment-1")], ["audit", audit, () => securityService.auditLogs.get("audit-1")],
  ] as const;
  it.each(getCases)("parses %s detail", async (_name, item, call) => { api.get.mockResolvedValueOnce(envelope(item)); await expect(call()).resolves.toMatchObject({ data: item, correlationId: "corr-security-1" }); });

  it("covers every governed create and update method", async () => {
    const operations = [
      [api.post, role, () => securityService.roles.create({ name: "Admin", code: "admin", role_type: "custom" })], [api.patch, role, () => securityService.roles.update("role-1", { name: "Admin 2" })], [api.post, userRole, () => securityService.userRoles.create({ user_id: "user-1", role_id: "role-1", reason: "Approved access" })], [api.patch, userRole, () => securityService.userRoles.update("user-role-1", { reason: "Renewed access" })], [api.post, permissionSet, () => securityService.permissionSets.create({ name: "Support" })], [api.patch, permissionSet, () => securityService.permissionSets.update("set-1", { name: "Support 2" })], [api.put, permissionSet, () => securityService.permissionSets.replacePermissions("set-1", { permission_ids: ["permission-1"] })], [api.post, userSet, () => securityService.userPermissionSets.create({ user_id: "user-1", permission_set_id: "set-1", expires_at: "2026-08-22T00:00:00Z", reason: "Approved access" })], [api.patch, userSet, () => securityService.userPermissionSets.update("grant-1", { reason: "Renewed access" })], [api.post, fieldRule, () => securityService.fieldSecurity.create({ module: "crm", resource: "contacts", field: "email", role_id: "role-1", visibility: "redacted", edit_control: "read_only" })], [api.patch, fieldRule, () => securityService.fieldSecurity.update("field-1", { visibility: "hidden" })], [api.post, rowRule, () => securityService.rowSecurity.create({ module: "crm", resource: "contacts", role_id: "role-1", rule_type: "ownership", filter_criteria: predicate })], [api.patch, rowRule, () => securityService.rowSecurity.update("row-1", { priority: 10 })], [api.post, profile, () => securityService.securityProfiles.create({ name: "Restricted", profile_type: "restricted", mfa_required: "always", session_timeout_minutes: 15, absolute_session_timeout_hours: 12, max_concurrent_sessions: 2 })], [api.patch, profile, () => securityService.securityProfiles.update("profile-1", { max_concurrent_sessions: 1 })], [api.post, profileAssignment, () => securityService.profileAssignments.create({ security_profile_id: "profile-1", user_id: "user-1", reason: "Approved access" })], [api.patch, profileAssignment, () => securityService.profileAssignments.update("profile-assignment-1", { precedence: 10 })],
    ] as const;
    for (const [mock, response, call] of operations) { mock.mockResolvedValueOnce(envelope(response)); await expect(call()).resolves.toMatchObject({ data: response }); }
  });

  it("covers nested role decisions, simulation, health, and every revocation/delete", async () => {
    api.post.mockResolvedValueOnce(envelope(rolePermission)); await expect(securityService.roles.setPermission("role-1", { permission_id: "permission-1", is_granted: true })).resolves.toMatchObject({ data: rolePermission });
    api.post.mockResolvedValueOnce(envelope(access)); await expect(securityService.accessDecisions.simulate({ subject_id: "user-1", permission_code: "security.roles:read", resource_context: {} })).resolves.toMatchObject({ data: access });
    api.get.mockResolvedValueOnce(envelope(health)); await expect(securityService.health()).resolves.toMatchObject({ data: health });
    api.delete.mockResolvedValue(undefined);
    const reason = { reason: "Approved security-policy cleanup" };
    await Promise.all([securityService.roles.delete("role-1", reason),
securityService.roles.removePermission("role-1", "permission-1", reason),
securityService.userRoles.revoke("user-role-1", reason),
securityService.permissionSets.delete("set-1", reason),
securityService.userPermissionSets.revoke("grant-1", reason),
securityService.fieldSecurity.delete("field-1", reason),
securityService.rowSecurity.delete("row-1", reason),
securityService.securityProfiles.delete("profile-1", reason),
securityService.profileAssignments.revoke("profile-assignment-1", reason)]);
    expect(api.delete).toHaveBeenCalledTimes(9);
  });

  it("rejects malformed envelopes instead of fabricating empty success", async () => { api.get.mockResolvedValueOnce({ results: [] }); await expect(securityService.roles.list()).rejects.toMatchObject({ code: "MALFORMED_RESPONSE", status: 502 }); });
  it("requires pagination metadata on list responses", async () => { api.get.mockResolvedValueOnce(envelope([])); await expect(securityService.roles.list()).rejects.toMatchObject({ code: "MALFORMED_RESPONSE" }); });
  it("preserves governed ApiError code and correlation ID", async () => { api.get.mockRejectedValueOnce(new ApiError("Denied", 403, undefined, "POLICY_DENIED", "corr-denied")); await expect(securityService.roles.list()).rejects.toMatchObject({ code: "POLICY_DENIED", correlationId: "corr-denied" }); });
});
