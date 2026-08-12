/* eslint-disable max-lines-per-function -- policy pages expose dense governed workflows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type {
  FieldSecurity,
  Permission,
  PermissionSet,
  RowSecurityRule,
  SecurityAuditLog,
  SecurityConfiguration,
  SecurityConfigurationDocument,
  SecurityConfigurationRollout,
  SecurityConfigurationVersion,
  SecurityProfile,
  SecurityProfileAssignment,
  SecurityProfileInput,
  SecurityProfileUpdateInput,
  UserPermissionSet,
} from "../contracts";
import { AuditLogPage } from "./AuditLogPage";
import { FieldSecurityPage } from "./FieldSecurityPage";
import {
  PermissionSetCreatePage,
  PermissionSetDetailPage,
  PermissionSetEditPage,
  PermissionSetsPage,
} from "./PermissionSetsPage";
import { ProfileAssignmentsPage } from "./ProfileAssignmentsPage";
import { RowSecurityPage } from "./RowSecurityPage";
import { SecurityConfigurationPage } from "./SecurityConfigurationPage";
import {
  SecurityProfileCreatePage,
  SecurityProfileDetailPage,
  SecurityProfileEditPage,
  SecurityProfilesPage,
} from "./SecurityProfilesPage";
import { UserPermissionSetsPage } from "./UserPermissionSetsPage";

const mocks = vi.hoisted(() => ({
  configurationGet: vi.fn(),
  configurationVersions: vi.fn(),
  configurationPreview: vi.fn(),
  configurationUpdate: vi.fn(),
  configurationRollback: vi.fn(),
  configurationImport: vi.fn(),
  configurationExport: vi.fn(),
  configurationUpdateRollout: vi.fn(),
  listAuditLogs: vi.fn(),
  listFieldSecurity: vi.fn(),
  listPermissions: vi.fn(),
  createPermissionSet: vi.fn(),
  deletePermissionSet: vi.fn(),
  getPermissionSet: vi.fn(),
  listPermissionSets: vi.fn(),
  replacePermissionSetPermissions: vi.fn(),
  updatePermissionSet: vi.fn(),
  listProfileAssignments: vi.fn(),
  listRowSecurity: vi.fn(),
  createSecurityProfile: vi.fn(),
  deleteSecurityProfile: vi.fn(),
  getSecurityProfile: vi.fn(),
  listSecurityProfiles: vi.fn(),
  updateSecurityProfile: vi.fn(),
  listUserPermissionSets: vi.fn(),
}));

vi.mock("../services/security-service", () => ({
  securityService: {
    auditLogs: { list: mocks.listAuditLogs },
    configuration: {
      exportDocument: mocks.configurationExport,
      get: mocks.configurationGet,
      importDocument: mocks.configurationImport,
      preview: mocks.configurationPreview,
      rollback: mocks.configurationRollback,
      update: mocks.configurationUpdate,
      updateRollout: mocks.configurationUpdateRollout,
      versions: mocks.configurationVersions,
    },
    fieldSecurity: { list: mocks.listFieldSecurity },
    permissions: { list: mocks.listPermissions },
    permissionSets: {
      create: mocks.createPermissionSet,
      delete: mocks.deletePermissionSet,
      get: mocks.getPermissionSet,
      list: mocks.listPermissionSets,
      replacePermissions: mocks.replacePermissionSetPermissions,
      update: mocks.updatePermissionSet,
    },
    profileAssignments: { list: mocks.listProfileAssignments },
    rowSecurity: { list: mocks.listRowSecurity },
    securityProfiles: {
      create: mocks.createSecurityProfile,
      delete: mocks.deleteSecurityProfile,
      get: mocks.getSecurityProfile,
      list: mocks.listSecurityProfiles,
      update: mocks.updateSecurityProfile,
    },
    userPermissionSets: { list: mocks.listUserPermissionSets },
  },
}));

const pagination = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

const rollout: SecurityConfigurationRollout = {
  enabled: true,
  percentage: 50,
  role_ids: ["role-1"],
  cohorts: ["beta"],
};

const securityDocument: SecurityConfigurationDocument = {
  limits: {
    rate_requests_per_minute: 600,
    correlation_id_max_length: 128,
    correlation_id_pattern: "^[a-z0-9-]+$",
    role_hierarchy_max_depth: 5,
    permission_set_duration_min_days: 1,
    permission_set_duration_max_days: 90,
    profile_idle_timeout_min_minutes: 5,
    profile_idle_timeout_max_minutes: 480,
    profile_absolute_timeout_min_hours: 1,
    profile_absolute_timeout_max_hours: 24,
    profile_concurrent_sessions_min: 1,
    profile_concurrent_sessions_max: 5,
    predicate_max_depth: 5,
    predicate_max_nodes: 20,
    predicate_max_in_values: 50,
    predicate_hard_max_depth: 8,
    predicate_hard_max_nodes: 40,
    predicate_hard_max_in_values: 100,
    predicate_compound_max_arguments: 8,
    audit_payload_max_bytes: 65536,
    policy_array_max_entries: 50,
    mfa_methods_max_entries: 4,
    audit_redaction_max_depth: 4,
    audit_collection_max_entries: 100,
    audit_string_max_length: 2000,
    required_text_max_length: 120,
    audit_reason_codes_max_entries: 10,
    user_agent_max_length: 512,
    audit_default_window_days: 7,
    audit_max_window_days: 90,
    row_priority_min: 1,
    row_priority_max: 1000,
    name_min_length: 2,
    name_max_length: 80,
    description_max_length: 500,
    list_page_size: 25,
    lookup_page_size: 10,
  },
  defaults: {
    field_visibility: "visible",
    field_edit_control: "read_only",
    row_rule_type: "ownership",
    row_rule_priority: 100,
    row_owner_field: "owner_id",
    profile_assignment_precedence: 10,
    security_profile: {
      profile_type: "standard",
      mfa_required: "conditional",
      allowed_mfa_methods: ["totp"],
      time_restrictions: { timezone: "UTC", weekdays: [1, 2, 3, 4, 5], windows: [] },
      session_timeout_minutes: 30,
      absolute_session_timeout_hours: 8,
      max_concurrent_sessions: 2,
      download_allowed: true,
      print_allowed: false,
      copy_paste_allowed: false,
      mobile_access_allowed: true,
      login_notification: true,
      access_notification: true,
    },
    automatic_revocation_reason: "Policy expired",
    mfa_precedence: { always: 4, conditional: 3, sensitive_actions: 2, never: 1 },
    allowed_mfa_methods: ["totp", "webauthn"],
  },
  ordering: {
    roles: ["name"],
    role_assignments: ["-valid_from"],
    permission_sets: ["name"],
    permission_set_grants: ["-granted_at"],
    field_rules: ["module", "resource", "field"],
    row_rules: ["module", "resource", "priority"],
    security_profiles: ["name"],
    profile_assignments: ["-valid_from"],
    audit_logs: ["-timestamp"],
  },
  resilience: {
    connect_timeout_seconds: 2,
    read_timeout_seconds: 5,
    max_retries: 2,
    failure_threshold: 3,
    reset_timeout_seconds: 30,
  },
  remote_context_keys: ["tenant_id"],
  ui: { loading_skeleton_rows: 3, audit_timeline_page_size: 25 },
  semantic_tokens: {
    success: "status-success",
    danger: "status-danger",
    warning: "status-warning",
    neutral: "status-neutral",
  },
  commercial_controls: { entitlement: "security_access", quota: "policy_rules" },
  baseline_profile: {
    mfa_required: "conditional",
    allowed_mfa_methods: ["totp"],
    session_timeout_minutes: 30,
    absolute_session_timeout_hours: 8,
    max_concurrent_sessions: 2,
    download_allowed: true,
    print_allowed: false,
    copy_paste_allowed: false,
    mobile_access_allowed: true,
    ip_whitelist: [],
    ip_blacklist: [],
    allowed_countries: ["US"],
    blocked_countries: [],
  },
  feature_flags: {
    row_security: { enabled: true, percentage: 100, roles: [], cohorts: [] },
  },
};

const configuration: SecurityConfiguration = {
  id: "config-1",
  environment: "production",
  version: 9,
  document: securityDocument,
  rollout,
  updated_by: "operator-1",
  correlation_id: "corr-security-config",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
};

const version: SecurityConfigurationVersion = {
  id: "version-8",
  version: 8,
  environment: "production",
  previous_document: null,
  current_document: securityDocument,
  previous_rollout: null,
  current_rollout: rollout,
  actor_id: "operator-2",
  correlation_id: "corr-v8",
  reason: "Prior policy baseline",
  change_kind: "update",
  created_at: "2026-07-21T00:00:00Z",
};

const permission: Permission = {
  id: "permission-1",
  module: "accounting_finance",
  resource: "journal_entry",
  action: "approve",
  code: "accounting_finance.journal_entry.approve",
  name: "Approve journals",
  description: "Approve journal entries",
  risk_level: "high",
  created_at: "2026-07-22T00:00:00Z",
};

const permissionSet: PermissionSet = {
  id: "set-1",
  tenant_id: "tenant-1",
  name: "Quarter close operators",
  description: "Temporary close capabilities",
  default_duration_days: 14,
  is_active: true,
  is_deleted: false,
  permission_ids: [permission.id],
  permissions: [permission],
  active_grant_count: 2,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
  deleted_at: null,
};

const fieldRule: FieldSecurity = {
  id: "field-1",
  tenant_id: "tenant-1",
  module: "accounting_finance",
  resource: "vendor",
  field: "tax_identifier",
  role_id: "role-1",
  role_name: "Auditor",
  visibility: "masked",
  edit_control: "read_only",
  mask_pattern: "****-last4",
  is_active: true,
  is_deleted: false,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
  deleted_at: null,
};

const rowRule: RowSecurityRule = {
  id: "row-1",
  tenant_id: "tenant-1",
  module: "accounting_finance",
  resource: "invoice",
  role_id: "role-1",
  role_name: "Regional collector",
  rule_type: "criteria",
  filter_criteria: { op: "eq", field: "region", value: "NA" },
  priority: 100,
  is_active: true,
  version: 3,
  is_deleted: false,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
  deleted_at: null,
};

const profile: SecurityProfile = {
  id: "profile-1",
  tenant_id: "tenant-1",
  name: "Privileged finance",
  description: "Tightened posture for finance operators",
  profile_type: "privileged",
  ip_whitelist: ["10.0.0.0/8"],
  ip_blacklist: [],
  allowed_countries: ["US"],
  blocked_countries: ["KP"],
  time_restrictions: { timezone: "UTC", weekdays: [1, 2, 3, 4, 5], windows: [] },
  mfa_required: "always",
  allowed_mfa_methods: ["webauthn"],
  password_policy: { minimum_length: 14, require_symbol: true },
  session_timeout_minutes: 20,
  absolute_session_timeout_hours: 8,
  max_concurrent_sessions: 1,
  download_allowed: false,
  print_allowed: false,
  copy_paste_allowed: false,
  mobile_access_allowed: false,
  login_notification: true,
  access_notification: true,
  is_active: true,
  is_deleted: false,
  assignment_count: 3,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
  deleted_at: null,
};

const profileAssignment: SecurityProfileAssignment = {
  id: "profile-assignment-1",
  tenant_id: "tenant-1",
  security_profile_id: profile.id,
  security_profile_name: profile.name,
  user_id: "user-1",
  user_display: "Ada Lovelace",
  role_id: null,
  role_name: null,
  precedence: 10,
  valid_from: "2026-07-22T00:00:00Z",
  valid_until: null,
  assigned_by: "operator-1",
  reason: "Privileged access review",
  revoked_at: null,
  revoked_by: null,
  revocation_reason: "",
  is_active: true,
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
};

const userPermissionSet: UserPermissionSet = {
  id: "grant-1",
  tenant_id: "tenant-1",
  user_id: "user-1",
  user_display: "Ada Lovelace",
  permission_set_id: permissionSet.id,
  permission_set_name: permissionSet.name,
  granted_at: "2026-07-22T00:00:00Z",
  expires_at: "2026-08-05T00:00:00Z",
  granted_by: "operator-1",
  reason: "Close window",
  revoked_at: null,
  revoked_by: null,
  revocation_reason: "",
  is_active: true,
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
};

const auditLog: SecurityAuditLog = {
  id: "audit-1",
  action: "permission_set.update",
  actor_type: "user",
  resource_type: "permission_set",
  resource_id: permissionSet.id,
  decision: "allow",
  reason_codes: ["POLICY_MATCH"],
  timestamp: "2026-07-23T00:00:00Z",
  details: { path: "permission_ids" },
  correlation_id: "corr-audit",
};

function page<T>(items: readonly T[]) {
  return { items, pagination, correlationId: "corr-list", timestamp: "2026-07-23T00:00:00Z" };
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>;
}

function renderPage(element: React.ReactNode, initial: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <LocationProbe />
        {element}
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderRoutePage({
  element,
  initial,
  path,
}: {
  readonly element: React.ReactNode;
  readonly initial: string;
  readonly path: string;
}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <LocationProbe />
        <Routes>
          <Route path={path} element={element} />
          <Route path="/security-access-control/permission-sets" element={<span />} />
          <Route path="/security-access-control/permission-sets/:id" element={<span />} />
          <Route path="/security-access-control/profiles/:id" element={<span />} />
          <Route path="/security-access-control/security-profiles" element={<span />} />
          <Route path="/security-access-control/security-profiles/:id" element={<span />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("security governed pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.configurationGet.mockResolvedValue({
      data: configuration,
      correlationId: "corr-security-config",
      timestamp: "2026-07-23T00:00:00Z",
    });
    mocks.configurationVersions.mockResolvedValue(page([version]));
    mocks.configurationPreview.mockResolvedValue({
      data: {
        valid: true,
        diff: [{ path: "limits.list_page_size", before: 20, after: 25 }],
        normalized_document: securityDocument,
        normalized_rollout: rollout,
      },
      correlationId: "corr-preview",
      timestamp: "2026-07-23T00:00:00Z",
    });
    mocks.configurationUpdate.mockResolvedValue({ data: configuration });
    mocks.configurationUpdateRollout.mockResolvedValue({ data: configuration });
    mocks.configurationRollback.mockResolvedValue({ data: configuration });
    mocks.configurationImport.mockResolvedValue({ data: configuration });
    mocks.configurationExport.mockResolvedValue({
      data: {
        schema_version: "1.0",
        environment: "production",
        version: 9,
        document: securityDocument,
        rollout,
      },
    });
    mocks.listPermissions.mockResolvedValue(page([permission]));
    mocks.createPermissionSet.mockResolvedValue({ data: permissionSet });
    mocks.getPermissionSet.mockResolvedValue({ data: permissionSet });
    mocks.listPermissionSets.mockResolvedValue(page([permissionSet]));
    mocks.replacePermissionSetPermissions.mockResolvedValue({ data: permissionSet });
    mocks.updatePermissionSet.mockResolvedValue({ data: permissionSet });
    mocks.deletePermissionSet.mockResolvedValue({ data: permissionSet });
    mocks.listFieldSecurity.mockResolvedValue(page([fieldRule]));
    mocks.listRowSecurity.mockResolvedValue(page([rowRule]));
    mocks.createSecurityProfile.mockResolvedValue({ data: profile });
    mocks.deleteSecurityProfile.mockResolvedValue({ data: profile });
    mocks.getSecurityProfile.mockResolvedValue({ data: profile });
    mocks.listSecurityProfiles.mockResolvedValue(page([profile]));
    mocks.updateSecurityProfile.mockResolvedValue({ data: profile });
    mocks.listProfileAssignments.mockResolvedValue(page([profileAssignment]));
    mocks.listUserPermissionSets.mockResolvedValue(page([userPermissionSet]));
    mocks.listAuditLogs.mockResolvedValue(page([auditLog]));
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:security"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    if (!File.prototype.text) {
      Object.defineProperty(File.prototype, "text", {
        configurable: true,
        value(this: File) {
          return new Response(this).text();
        },
      });
    }
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("requires server preview before saving configuration and supports rollout, import, export, and rollback", async () => {
    const user = userEvent.setup();
    renderPage(<SecurityConfigurationPage />, "/security-access-control/configuration");

    expect(
      await screen.findByRole("heading", { name: "Security configuration" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save new version" })).toBeDisabled();
    await user.type(screen.getByLabelText("Mandatory change reason"), "Quarterly policy review");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Server preview" })).not.toBeDisabled()
    );
    await user.click(screen.getByRole("button", { name: "Server preview" }));

    await waitFor(() =>
      expect(mocks.configurationPreview).toHaveBeenCalledWith({
        document: securityDocument,
        rollout,
      })
    );
    expect(await screen.findByText("Server validation passed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save new version" }));
    await waitFor(() =>
      expect(mocks.configurationUpdate).toHaveBeenCalledWith({
        document: securityDocument,
        environment: "production",
        reason: "Quarterly policy review",
      })
    );

    await user.type(screen.getByLabelText("Mandatory change reason"), " rollout");
    await user.clear(screen.getByLabelText("Percentage (0–100)"));
    await user.type(screen.getByLabelText("Percentage (0–100)"), "25");
    await user.click(screen.getByRole("button", { name: "Apply rollout as new version" }));
    await waitFor(() => expect(mocks.configurationUpdateRollout).toHaveBeenCalled());
    const rolloutRequest = mocks.configurationUpdateRollout.mock.calls.at(-1)?.[0] as
      | { rollout: SecurityConfigurationRollout; reason: string }
      | undefined;
    expect(rolloutRequest?.rollout.percentage).toBe(25);
    expect(rolloutRequest?.reason).toBe(" rollout");

    await user.type(screen.getByLabelText("Mandatory change reason"), "Import reviewed config");
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    const importedText = JSON.stringify({
      schema_version: "1.0",
      environment: "production",
      version: 9,
      document: securityDocument,
      rollout,
    });
    const importedFile = new File([importedText], "security-config.json", {
      type: "application/json",
    });
    Object.defineProperty(importedFile, "text", {
      configurable: true,
      value: vi.fn().mockResolvedValue(importedText),
    });
    await user.upload(input!, importedFile);
    await waitFor(() =>
      expect(mocks.configurationImport).toHaveBeenCalledWith(
        expect.objectContaining({
          document: securityDocument,
          environment: "production",
          rollout,
          reason: "Import reviewed config",
        })
      )
    );

    await user.click(screen.getByRole("button", { name: "Export" }));
    expect(mocks.configurationExport).toHaveBeenCalled();

    await user.type(
      screen.getByLabelText("Mandatory change reason"),
      "Rollback to stable baseline"
    );
    await user.click(screen.getByRole("button", { name: "Rollback" }));
    await waitFor(() =>
      expect(mocks.configurationRollback).toHaveBeenCalledWith(8, {
        reason: "Rollback to stable baseline",
      })
    );
  }, 10_000);

  it("renders policy lists with governed filters, previews, pagination settings, and audit evidence", async () => {
    const first = renderPage(<PermissionSetsPage />, "/security-access-control/permission-sets");
    expect(await screen.findByText("Quarter close operators")).toBeInTheDocument();
    expect(mocks.listPermissionSets).toHaveBeenCalledWith(
      expect.objectContaining({ ordering: "name", page_size: 25 })
    );
    fireEvent.change(screen.getByLabelText("Search permission sets"), {
      target: { value: "quarter" },
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Current route")).toHaveTextContent("search=quarter")
    );
    first.unmount();

    const fields = renderPage(<FieldSecurityPage />, "/security-access-control/field-security");
    expect(
      await screen.findByRole("link", {
        name: /accounting_finance.*vendor.*tax_identifier/u,
      })
    ).toBeInTheDocument();
    expect(screen.getByText("****-last4")).toBeInTheDocument();
    expect(mocks.listFieldSecurity).toHaveBeenCalledWith(
      expect.objectContaining({ ordering: "module,resource,field", page_size: 25 })
    );
    fields.unmount();

    const rows = renderPage(<RowSecurityPage />, "/security-access-control/row-security");
    expect(await screen.findByText("Regional collector")).toBeInTheDocument();
    expect(screen.getByText('region equals "NA"')).toBeInTheDocument();
    rows.unmount();

    const profiles = renderPage(<SecurityProfilesPage />, "/security-access-control/profiles");
    expect(await screen.findByText("Privileged finance")).toBeInTheDocument();
    expect(screen.getByText(/privileged.*MFA.*always/u)).toBeInTheDocument();
    expect(screen.getByText(/20m idle.*1 sessions.*3 assignments/u)).toBeInTheDocument();
    profiles.unmount();

    const profileAssignments = renderPage(
      <ProfileAssignmentsPage />,
      "/security-access-control/profile-assignments"
    );
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Privileged finance")).toBeInTheDocument();
    expect(screen.getByText(/Priority\s+10/u)).toBeInTheDocument();
    profileAssignments.unmount();

    const grants = renderPage(
      <UserPermissionSetsPage />,
      "/security-access-control/permission-set-grants"
    );
    expect(await screen.findByText("Close window")).toBeInTheDocument();
    expect(screen.getByText("Quarter close operators")).toBeInTheDocument();
    grants.unmount();

    renderPage(<AuditLogPage />, "/security-access-control/audit-log");
    expect(await screen.findByText("permission_set.update")).toBeInTheDocument();
    expect(screen.getByText("corr-audit")).toBeInTheDocument();
  });

  it("surfaces permission-denied responses with retryable correlation evidence", async () => {
    mocks.listSecurityProfiles
      .mockRejectedValueOnce(new ApiError("Denied", 403, undefined, "POLICY_DENIED", "corr-denied"))
      .mockResolvedValueOnce(page([profile]));
    const user = userEvent.setup();
    renderPage(<SecurityProfilesPage />, "/security-access-control/profiles");

    expect(await screen.findByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText(/corr-denied/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Privileged finance")).toBeInTheDocument();
  });

  it("creates and edits permission sets through atomic membership replacement", async () => {
    const user = userEvent.setup();
    const created = renderPage(
      <PermissionSetCreatePage />,
      "/security-access-control/permission-sets/new"
    );

    expect(
      await screen.findByRole("heading", { name: "Create permission set" })
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Name"), "Emergency close operators");
    await user.type(screen.getByLabelText("Description"), "Break-glass quarter close access");
    await user.type(screen.getByLabelText("Default duration (days)"), "7");
    await user.click(screen.getByLabelText(`Include ${permission.code}`));
    await user.click(screen.getByRole("button", { name: "Save permission set" }));

    await waitFor(() =>
      expect(mocks.createPermissionSet).toHaveBeenCalledWith({
        default_duration_days: 7,
        description: "Break-glass quarter close access",
        is_active: true,
        name: "Emergency close operators",
      })
    );
    expect(mocks.replacePermissionSetPermissions).toHaveBeenCalledWith(permissionSet.id, {
      permission_ids: [permission.id],
    });
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      `/security-access-control/permission-sets/${permissionSet.id}`
    );
    created.unmount();

    renderRoutePage({
      element: <PermissionSetEditPage />,
      initial: `/security-access-control/permission-sets/${permissionSet.id}/edit`,
      path: "/security-access-control/permission-sets/:id/edit",
    });
    expect(
      await screen.findByRole("heading", { name: `Edit ${permissionSet.name}` })
    ).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Default duration (days)"));
    await user.type(screen.getByLabelText("Default duration (days)"), "21");
    await user.click(screen.getByLabelText(`Include ${permission.code}`));
    await user.click(screen.getByRole("button", { name: "Save permission set" }));

    await waitFor(() =>
      expect(mocks.updatePermissionSet).toHaveBeenCalledWith(permissionSet.id, {
        default_duration_days: 21,
        description: permissionSet.description,
        is_active: true,
        name: permissionSet.name,
      })
    );
    expect(mocks.replacePermissionSetPermissions).toHaveBeenLastCalledWith(permissionSet.id, {
      permission_ids: [],
    });
  });

  it("requires governed confirmation before deleting permission sets from detail", async () => {
    const prompt = vi.spyOn(window, "prompt").mockReturnValue("Retired after access review");
    renderRoutePage({
      element: <PermissionSetDetailPage />,
      initial: `/security-access-control/permission-sets/${permissionSet.id}`,
      path: "/security-access-control/permission-sets/:id",
    });

    expect(await screen.findByRole("heading", { name: permissionSet.name })).toBeInTheDocument();
    expect(screen.getByText(permission.code)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete set" }));

    expect(prompt).toHaveBeenCalledWith(
      "Soft-delete this permission set? Active protected grants will prevent removal.\n\nEnter the mandatory audit reason:"
    );
    await waitFor(() =>
      expect(mocks.deletePermissionSet).toHaveBeenCalledWith(permissionSet.id, {
        reason: "Retired after access review",
      })
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/permission-sets"
    );
  });

  it("validates and submits security profile restrictions with normalized tokens", async () => {
    const user = userEvent.setup();
    renderPage(<SecurityProfileCreatePage />, "/security-access-control/security-profiles/create");

    expect(
      await screen.findByRole("heading", { name: "Create security profile" })
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Name"), "Finance lockdown");
    await user.type(screen.getByLabelText("Description"), "Restrict finance data handling");
    await user.clear(screen.getByLabelText("Allowed countries (ISO codes)"));
    await user.type(screen.getByLabelText("Allowed countries (ISO codes)"), "us, ca");
    await user.clear(screen.getByLabelText("Blocked countries"));
    await user.type(screen.getByLabelText("Blocked countries"), "US");
    await user.click(screen.getByRole("button", { name: "Save security profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Allowed and blocked countries cannot overlap."
    );
    expect(mocks.createSecurityProfile).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Blocked countries"));
    await user.type(screen.getByLabelText("Blocked countries"), "KP");
    await user.clear(screen.getByLabelText("Window start"));
    await user.type(screen.getByLabelText("Window start"), "09:00");
    await user.clear(screen.getByLabelText("Window end"));
    await user.type(screen.getByLabelText("Window end"), "17:30");
    await user.click(screen.getByLabelText("Downloads allowed"));
    await user.click(screen.getByRole("button", { name: "Save security profile" }));

    await waitFor(() => expect(mocks.createSecurityProfile).toHaveBeenCalled());
    const createProfileInput = mocks.createSecurityProfile.mock.calls.at(-1)?.[0] as
      | SecurityProfileInput
      | undefined;
    expect(createProfileInput).toMatchObject({
      allowed_countries: ["US", "CA"],
      blocked_countries: ["KP"],
      download_allowed: false,
      name: "Finance lockdown",
      time_restrictions: {
        windows: [{ start: "09:00", end: "17:30" }],
      },
    });
    await waitFor(
      () =>
        expect(screen.getByLabelText("Current route")).toHaveTextContent(
          `/security-access-control/security-profiles/${profile.id}`
        ),
      { timeout: 5_000 }
    );
  }, 10_000);

  it("renders security profile detail controls and submits governed deletion reasons", async () => {
    const prompt = vi.spyOn(window, "prompt").mockReturnValue("Profile superseded");
    renderRoutePage({
      element: <SecurityProfileDetailPage />,
      initial: `/security-access-control/profiles/${profile.id}`,
      path: "/security-access-control/profiles/:id",
    });

    expect(await screen.findByRole("heading", { name: profile.name })).toBeInTheDocument();
    expect(screen.getByText("Countries allowed: US")).toBeInTheDocument();
    expect(screen.getByText("1 allowed networks")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete profile" }));

    expect(prompt).toHaveBeenCalledWith(
      "Soft-delete this profile? Active assignments will prevent removal.\n\nEnter the mandatory audit reason:"
    );
    await waitFor(() =>
      expect(mocks.deleteSecurityProfile).toHaveBeenCalledWith(profile.id, {
        reason: "Profile superseded",
      })
    );
  });

  it("loads existing security profiles before edit and updates only after validation passes", async () => {
    const user = userEvent.setup();
    renderRoutePage({
      element: <SecurityProfileEditPage />,
      initial: `/security-access-control/profiles/${profile.id}/edit`,
      path: "/security-access-control/profiles/:id/edit",
    });

    expect(
      await screen.findByRole("heading", { name: "Edit security profile" })
    ).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Window start"));
    await user.type(screen.getByLabelText("Window start"), "18:00");
    await user.clear(screen.getByLabelText("Window end"));
    await user.type(screen.getByLabelText("Window end"), "17:00");
    await user.click(screen.getByRole("button", { name: "Save security profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The time window end must be after its start."
    );
    expect(mocks.updateSecurityProfile).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Window end"));
    await user.type(screen.getByLabelText("Window end"), "19:00");
    await user.click(screen.getByLabelText("Printing allowed"));
    await user.click(screen.getByRole("button", { name: "Save security profile" }));

    await waitFor(() => expect(mocks.updateSecurityProfile).toHaveBeenCalled());
    const updateProfileInput = mocks.updateSecurityProfile.mock.calls.at(-1)?.[1] as
      | SecurityProfileUpdateInput
      | undefined;
    expect(mocks.updateSecurityProfile).toHaveBeenLastCalledWith(profile.id, updateProfileInput);
    expect(updateProfileInput).toMatchObject({
      print_allowed: true,
      time_restrictions: {
        windows: [{ start: "18:00", end: "19:00" }],
      },
    });
  });
});
