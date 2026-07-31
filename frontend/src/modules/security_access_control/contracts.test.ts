/* eslint-disable max-lines-per-function -- table-driven runtime guard matrix intentionally pins every exported guard for mutation hardening. */
import { describe, expect, it, vi } from "vitest";
import {
  ENDPOINTS,
  isAccessDecision,
  isEditControl,
  isFieldSecurity,
  isHealthStatus,
  isPermission,
  isPermissionSet,
  isPredicateScalar,
  isPredicateScalarArray,
  isPredicateSubjectReference,
  isProfileAssignment,
  isRole,
  isRolePermission,
  isRowPredicate,
  isRowSecurityRule,
  isSecurityAuditLog,
  isSecurityConfiguration,
  isSecurityConfigurationDocument,
  isSecurityConfigurationExport,
  isSecurityConfigurationPreview,
  isSecurityConfigurationRollout,
  isSecurityConfigurationVersion,
  isSecurityProfile,
  isUserPermissionSet,
  isUserRole,
  isV2Meta,
  isV2PageMeta,
  isVisibility,
} from "./contracts";

describe("security contracts", () => {
  it("uses only governed v2 endpoints", () => {
    expect(JSON.stringify(ENDPOINTS)).not.toContain("/api/v1/");
    expect(ENDPOINTS.ROLES.DETAIL("r1")).toBe("/api/v2/security-access-control/roles/r1/");
    expect(ENDPOINTS.PERMISSION_SETS.PERMISSIONS("s1")).toContain("/permissions/");
    expect(ENDPOINTS.ACCESS_DECISIONS.SIMULATE).toContain("access-decisions/simulate");
  });
  it("accepts redacted visibility and rejects unknown states", () => {
    expect(isVisibility("redacted")).toBe(true);
    expect(isVisibility("obscured")).toBe(false);
    expect(isEditControl("required")).toBe(true);
    expect(isEditControl("write_only")).toBe(false);
    expect(
      isFieldSecurity({
        id: "f",
        module: "crm",
        resource: "contact",
        field: "email",
        role_id: "r",
        visibility: "redacted",
        edit_control: "read_only",
      })
    ).toBe(true);
  });
  it("validates bounded safe predicate AST nodes", () => {
    expect(
      isRowPredicate({
        op: "and",
        args: [
          { op: "tenant", field: "tenant_id" },
          { op: "owner", field: "owner_id" },
        ],
      })
    ).toBe(true);
    expect(
      isRowPredicate({
        op: "or",
        args: [
          { op: "eq", field: "status", value: "open" },
          { op: "is_null", field: "closed_at" },
        ],
      })
    ).toBe(true);
    expect(isRowPredicate({ op: "raw_sql", value: "1=1" })).toBe(false);
    expect(isRowPredicate({ op: "raw_sql", field: "tenant_id", value: "1=1" })).toBe(false);
    expect(isRowPredicate({ op: "and", args: [] })).toBe(false);
    expect(
      isRowPredicate({
        op: "and",
        args: [
          { op: "tenant", field: "tenant_id" },
          { op: "raw_sql", field: "id" },
        ],
      })
    ).toBe(false);
  });
  it("rejects incomplete access decisions", () => {
    expect(isAccessDecision({ decision: "allow" })).toBe(false);
  });
  it("scopes query keys by normalized filters", async () => {
    vi.resetModules();
    const { QUERY_KEYS } = await import("./contracts");
    expect(QUERY_KEYS.roles({ search: "admin", page: 2 })).toEqual(
      QUERY_KEYS.roles({ page: 2, search: "admin" })
    );
    expect(QUERY_KEYS.role("role-1")).not.toEqual(QUERY_KEYS.role("role-2"));
    expect(QUERY_KEYS.roles({ search: "", page: 0, is_active: false })).toEqual([
      "security-access-control",
      "roles",
      [
        ["is_active", "false"],
        ["page", "0"],
      ],
    ]);
    expect(QUERY_KEYS.auditLogs({ actor_type: undefined, page_size: 50 })).toEqual([
      "security-access-control",
      "audit-logs",
      [["page_size", "50"]],
    ]);
  });

  it("rejects non-record and non-string primitives before entity validation", async () => {
    vi.resetModules();
    const { isPermission, isRecord, isString } = await import("./contracts");
    expect(isRecord({ id: "record-1" })).toBe(true);
    expect(isRecord(null)).toBe(false);
    expect(isRecord(["record-1"])).toBe(false);
    expect(isString("security.roles:read")).toBe(true);
    expect(isString(42)).toBe(false);
    expect(isPermission(null)).toBe(false);
    expect(isPermission({ id: 1 })).toBe(false);
  });

  it("pins every supported row predicate operator and rejects unsafe value shapes", async () => {
    vi.resetModules();
    const { isRowPredicate } = await import("./contracts");
    expect(isRowPredicate({ op: "eq", field: "owner_id", value: { subject: "user-1" } })).toBe(
      true
    );
    expect(isRowPredicate({ op: "eq", field: "status", value: "open" })).toBe(true);
    expect(isRowPredicate({ op: "eq", field: "priority", value: 1 })).toBe(true);
    expect(isRowPredicate({ op: "eq", field: "is_active", value: false })).toBe(true);
    expect(isRowPredicate({ op: "eq", field: "closed_at", value: null })).toBe(true);
    expect(isRowPredicate({ op: "in", field: "status", value: ["open", 1, false, null] })).toBe(
      true
    );
    expect(isRowPredicate({ op: "not", arg: { op: "tenant", field: "tenant_id" } })).toBe(true);
    expect(
      isRowPredicate({
        op: "or",
        args: [
          { op: "owner", field: "owner_id" },
          { op: "tenant", field: "tenant_id" },
        ],
      })
    ).toBe(true);
    expect(isRowPredicate({ op: "is_null", field: "deleted_at" })).toBe(true);
    expect(isRowPredicate({ op: "owner", field: "owner_id" })).toBe(true);
    expect(isRowPredicate({ op: "tenant", field: "tenant_id" })).toBe(true);

    expect(isRowPredicate(null)).toBe(false);
    expect(isRowPredicate({ op: 1, field: "owner_id" })).toBe(false);
    expect(
      isRowPredicate({ op: "eq", field: "owner_id", value: { subject: "user-1", extra: true } })
    ).toBe(false);
    expect(isRowPredicate({ op: "eq", field: "owner_id", value: { actor: "user-1" } })).toBe(false);
    expect(isRowPredicate({ op: "eq", field: "status", value: ["open"] })).toBe(false);
    expect(isRowPredicate({ op: "in", field: "status", value: [] })).toBe(false);
    expect(isRowPredicate({ op: "in", field: "status", value: [{}] })).toBe(false);
    expect(isRowPredicate({ op: "in", field: "status", value: "open" })).toBe(false);
    expect(isRowPredicate({ op: "not", arg: { op: "raw_sql", value: "1=1" } })).toBe(false);
    expect(isRowPredicate({ op: "not" })).toBe(false);
    expect(isRowPredicate({ op: "tenant" })).toBe(false);
    expect(isRowPredicate({ op: "is_null", field: 1 })).toBe(false);
    expect(isRowPredicate({ op: "owner", field: 1 })).toBe(false);
    expect(isRowPredicate({ op: "tenant", field: 1 })).toBe(false);
    expect(isRowPredicate({ op: "unknown", field: "tenant_id" })).toBe(false);
  });

  it("validates predicate scalar helper boundaries exactly", () => {
    expect(isPredicateScalar("open")).toBe(true);
    expect(isPredicateScalar(0)).toBe(true);
    expect(isPredicateScalar(false)).toBe(true);
    expect(isPredicateScalar(null)).toBe(true);
    expect(isPredicateScalar(undefined)).toBe(false);
    expect(isPredicateScalar({ subject: "user-1" })).toBe(false);
    expect(isPredicateScalar(["open"])).toBe(false);
  });

  it("validates predicate subject references without allowing extra keys", () => {
    expect(isPredicateSubjectReference({ subject: "user-1" })).toBe(true);
    expect(isPredicateSubjectReference({ subject: "" })).toBe(true);
    expect(isPredicateSubjectReference({ subject: 1 })).toBe(false);
    expect(isPredicateSubjectReference({ actor: "user-1" })).toBe(false);
    expect(isPredicateSubjectReference({ subject: "user-1", tenant: "tenant-1" })).toBe(false);
    expect(isPredicateSubjectReference(null)).toBe(false);
  });

  it("validates non-empty predicate scalar arrays", () => {
    expect(isPredicateScalarArray(["open", 1, false, null])).toBe(true);
    expect(isPredicateScalarArray([])).toBe(false);
    expect(isPredicateScalarArray(["open", undefined])).toBe(false);
    expect(isPredicateScalarArray([{ subject: "user-1" }])).toBe(false);
    expect(isPredicateScalarArray("open")).toBe(false);
  });

  it("table-drives runtime guard acceptance and rejection for governed entities", () => {
    const predicate = { op: "owner", field: "owner_id" };
    const configurationDocument = {
      limits: {
        rate_requests_per_minute: 60,
        correlation_id_max_length: 128,
        role_hierarchy_max_depth: 5,
        permission_set_duration_min_days: 1,
        permission_set_duration_max_days: 365,
        profile_idle_timeout_min_minutes: 5,
        profile_idle_timeout_max_minutes: 480,
        profile_absolute_timeout_min_hours: 1,
        profile_absolute_timeout_max_hours: 24,
        profile_concurrent_sessions_min: 1,
        profile_concurrent_sessions_max: 10,
        predicate_max_depth: 5,
        predicate_max_nodes: 50,
        predicate_max_in_values: 100,
        predicate_hard_max_depth: 10,
        predicate_hard_max_nodes: 200,
        predicate_hard_max_in_values: 500,
        predicate_compound_max_arguments: 10,
        audit_payload_max_bytes: 8192,
        policy_array_max_entries: 100,
        mfa_methods_max_entries: 5,
        audit_redaction_max_depth: 4,
        audit_collection_max_entries: 100,
        audit_string_max_length: 1000,
        required_text_max_length: 2000,
        audit_reason_codes_max_entries: 10,
        user_agent_max_length: 512,
        audit_default_window_days: 7,
        audit_max_window_days: 90,
        row_priority_min: 0,
        row_priority_max: 100,
        name_min_length: 2,
        name_max_length: 120,
        description_max_length: 1000,
        list_page_size: 25,
        lookup_page_size: 50,
      },
      defaults: { security_profile: {} },
      ordering: {},
      resilience: {},
      remote_context_keys: ["tenant_id"],
      ui: { loading_skeleton_rows: 5 },
      semantic_tokens: {},
      commercial_controls: {},
      baseline_profile: {},
      feature_flags: {},
    };
    const rollout = { enabled: true, percentage: 50, role_ids: ["role-1"], cohorts: ["beta"] };
    const accessDecision = {
      subject_id: "user-1",
      permission_code: "security.roles:read",
      decision: "allow",
      reason_codes: ["matched"],
      applied_policy_ids: ["policy-1"],
      entitlement: { required: true, allowed: true },
      quota: { required: false, allowed: true },
      field_decisions: [
        {
          field: "email",
          visibility: "masked",
          edit_control: "read_only",
          reason_codes: ["field-policy"],
          applied_policy_ids: ["policy-2"],
        },
      ],
      row_explanation: {
        allowed: true,
        applied_rule_ids: ["row-1"],
        reason_codes: ["owner"],
        explanation: "Owner policy matched",
      },
      audit_log_id: "audit-1",
      correlation_id: "corr-1",
      evaluated_at: "2026-07-31T00:00:00Z",
    };
    const cases = [
      {
        name: "page metadata",
        guard: isV2PageMeta,
        valid: {
          count: 1,
          page: 1,
          page_size: 25,
          total_pages: 1,
          has_next: false,
          has_previous: false,
        },
        invalid: { count: 1, page: 1, page_size: 25, total_pages: 1, has_next: "false" },
      },
      {
        name: "response metadata",
        guard: isV2Meta,
        valid: { correlation_id: "corr-1", timestamp: "2026-07-31T00:00:00Z" },
        invalid: { correlation_id: "corr-1", pagination: {} },
      },
      {
        name: "permission",
        guard: isPermission,
        valid: {
          id: "perm-1",
          module: "crm",
          resource: "contact",
          action: "read",
          name: "Read contact",
          risk_level: "low",
        },
        invalid: { id: "perm-1", module: "crm", resource: "contact", action: "read" },
      },
      {
        name: "role",
        guard: isRole,
        valid: {
          id: "role-1",
          name: "Administrator",
          code: "ADMIN",
          role_type: "system",
          is_active: true,
          hierarchy_level: 0,
        },
        invalid: {
          id: "role-1",
          name: "Administrator",
          code: "ADMIN",
          role_type: "external",
          is_active: true,
          hierarchy_level: 0,
        },
      },
      {
        name: "role permission",
        guard: isRolePermission,
        valid: { id: "rp-1", role_id: "role-1", permission_id: "perm-1", is_granted: true },
        invalid: { id: "rp-1", role_id: "role-1", permission_id: "perm-1", is_granted: "true" },
      },
      {
        name: "user role",
        guard: isUserRole,
        valid: {
          id: "ur-1",
          user_id: "user-1",
          role_id: "role-1",
          valid_from: "2026-07-31T00:00:00Z",
          valid_until: null,
          is_active: true,
        },
        invalid: { id: "ur-1", user_id: "user-1", role_id: "role-1", valid_until: null },
      },
      {
        name: "permission set",
        guard: isPermissionSet,
        valid: { id: "set-1", name: "Approver", is_active: true, permission_ids: ["perm-1"] },
        invalid: { id: "set-1", name: "Approver", is_active: true, permission_ids: [1] },
      },
      {
        name: "user permission set",
        guard: isUserPermissionSet,
        valid: {
          id: "ups-1",
          user_id: "user-1",
          permission_set_id: "set-1",
          expires_at: "2026-08-31T00:00:00Z",
          is_active: true,
        },
        invalid: {
          id: "ups-1",
          user_id: "user-1",
          permission_set_id: "set-1",
          expires_at: null,
          is_active: true,
        },
      },
      {
        name: "field security",
        guard: isFieldSecurity,
        valid: {
          id: "field-1",
          module: "crm",
          resource: "contact",
          field: "email",
          role_id: "role-1",
          visibility: "redacted",
          edit_control: "read_only",
        },
        invalid: {
          id: "field-1",
          module: "crm",
          resource: "contact",
          field: "email",
          role_id: "role-1",
          visibility: "obscured",
          edit_control: "read_only",
        },
      },
      {
        name: "row security rule",
        guard: isRowSecurityRule,
        valid: {
          id: "row-1",
          module: "crm",
          resource: "contact",
          role_id: "role-1",
          rule_type: "ownership",
          filter_criteria: predicate,
          version: 1,
        },
        invalid: {
          id: "row-1",
          module: "crm",
          resource: "contact",
          role_id: "role-1",
          rule_type: "ownership",
          filter_criteria: { op: "raw_sql", value: "1=1" },
          version: 1,
        },
      },
      {
        name: "security profile",
        guard: isSecurityProfile,
        valid: {
          id: "profile-1",
          name: "Privileged",
          profile_type: "privileged",
          mfa_required: "always",
          session_timeout_minutes: 30,
          is_active: true,
        },
        invalid: {
          id: "profile-1",
          name: "Privileged",
          profile_type: "privileged",
          mfa_required: "optional",
          session_timeout_minutes: 30,
          is_active: true,
        },
      },
      {
        name: "profile assignment",
        guard: isProfileAssignment,
        valid: {
          id: "assignment-1",
          security_profile_id: "profile-1",
          user_id: "user-1",
          role_id: null,
          is_active: true,
        },
        invalid: {
          id: "assignment-1",
          security_profile_id: "profile-1",
          user_id: "user-1",
          role_id: "role-1",
          is_active: true,
        },
      },
      {
        name: "audit log",
        guard: isSecurityAuditLog,
        valid: {
          id: "audit-1",
          action: "role.create",
          actor_type: "user",
          resource_type: "role",
          timestamp: "2026-07-31T00:00:00Z",
          reason_codes: ["created"],
          correlation_id: "corr-1",
          details: {},
        },
        invalid: {
          id: "audit-1",
          action: "role.create",
          actor_type: "bot",
          resource_type: "role",
          timestamp: "2026-07-31T00:00:00Z",
          reason_codes: ["created"],
          correlation_id: "corr-1",
          details: {},
        },
      },
      {
        name: "access decision",
        guard: isAccessDecision,
        valid: accessDecision,
        invalid: {
          ...accessDecision,
          field_decisions: [{ ...accessDecision.field_decisions[0], field: 1 }],
        },
      },
      {
        name: "health status",
        guard: isHealthStatus,
        valid: { status: "ready", correlation_id: "corr-1", components: { database: "ready" } },
        invalid: { status: "healthy", correlation_id: "corr-1", components: { database: "ready" } },
      },
      {
        name: "configuration document",
        guard: isSecurityConfigurationDocument,
        valid: configurationDocument,
        invalid: {
          ...configurationDocument,
          limits: { ...configurationDocument.limits, lookup_page_size: undefined },
        },
      },
      {
        name: "configuration rollout",
        guard: isSecurityConfigurationRollout,
        valid: rollout,
        invalid: { ...rollout, role_ids: ["role-1", 7] },
      },
      {
        name: "configuration",
        guard: isSecurityConfiguration,
        valid: {
          id: "configuration-1",
          environment: "development",
          version: 1,
          document: configurationDocument,
          rollout,
          updated_by: "user-1",
          correlation_id: "corr-1",
          created_at: "2026-07-31T00:00:00Z",
          updated_at: "2026-07-31T00:00:00Z",
        },
        invalid: {
          id: "configuration-1",
          environment: "development",
          version: 1,
          document: configurationDocument,
          rollout: { ...rollout, role_ids: [1] },
          updated_by: "user-1",
          correlation_id: "corr-1",
          created_at: "2026-07-31T00:00:00Z",
          updated_at: "2026-07-31T00:00:00Z",
        },
      },
      {
        name: "configuration version",
        guard: isSecurityConfigurationVersion,
        valid: {
          id: "version-1",
          version: 1,
          environment: "development",
          previous_document: null,
          current_document: configurationDocument,
          previous_rollout: null,
          current_rollout: rollout,
          actor_id: "user-1",
          correlation_id: "corr-1",
          reason: "Initial version",
          change_kind: "bootstrap",
          created_at: "2026-07-31T00:00:00Z",
        },
        invalid: {
          id: "version-1",
          version: 1,
          environment: "development",
          previous_document: {},
          current_document: configurationDocument,
          previous_rollout: null,
          current_rollout: rollout,
          actor_id: "user-1",
          correlation_id: "corr-1",
          reason: "Initial version",
          change_kind: "bootstrap",
          created_at: "2026-07-31T00:00:00Z",
        },
      },
      {
        name: "configuration preview",
        guard: isSecurityConfigurationPreview,
        valid: {
          valid: true,
          diff: [],
          normalized_document: configurationDocument,
          normalized_rollout: rollout,
        },
        invalid: {
          valid: true,
          diff: {},
          normalized_document: configurationDocument,
          normalized_rollout: rollout,
        },
      },
      {
        name: "configuration export",
        guard: isSecurityConfigurationExport,
        valid: {
          schema_version: "saraise.security-access-control.configuration/v1",
          environment: "development",
          version: 1,
          document: configurationDocument,
          rollout,
        },
        invalid: {
          schema_version: "saraise.security-access-control.configuration/v1",
          environment: "development",
          version: "1",
          document: configurationDocument,
          rollout,
        },
      },
    ] as const;

    for (const { name, guard, valid, invalid } of cases) {
      expect(guard(valid), `${name} accepts a complete governed payload`).toBe(true);
      expect(guard(invalid), `${name} rejects malformed or unsafe payloads`).toBe(false);
    }
  });
});
