/* eslint-disable max-lines-per-function -- dense governed page workflows need end-to-end RTL coverage. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type {
  FieldSecurity,
  Permission,
  Role,
  RowSecurityRule,
  SecurityAuditLog,
  SecurityConfiguration,
  SecurityConfigurationDocument,
  SecurityProfile,
  SecurityProfileAssignment,
  UserPermissionSet,
} from "../contracts";
import {
  AuditTimeline,
  ConfirmButton,
  EmptyPanel,
  formatDate,
  GovernedError,
  PageHeader,
  PageSkeleton,
  Pagination,
  ResourceGrid,
  ResourceTable,
  StatusChip,
  Surface,
  useUnsavedChanges,
} from "../components/SecurityUI";
import { AuditLogPage } from "./AuditLogPage";
import {
  FieldSecurityCreatePage,
  FieldSecurityDetailPage,
  FieldSecurityEditPage,
  FieldSecurityPage,
} from "./FieldSecurityPage";
import { PermissionDetailPage, PermissionsPage } from "./PermissionsPage";
import {
  ProfileAssignmentCreatePage,
  ProfileAssignmentDetailPage,
  ProfileAssignmentsPage,
} from "./ProfileAssignmentsPage";
import { RoleCreatePage, RoleDetailPage, RolesPage } from "./RolesPage";
import {
  RowSecurityCreatePage,
  RowSecurityDetailPage,
  RowSecurityEditPage,
  RowSecurityPage,
} from "./RowSecurityPage";
import {
  UserPermissionSetCreatePage,
  UserPermissionSetDetailPage,
  UserPermissionSetsPage,
} from "./UserPermissionSetsPage";

const mocks = vi.hoisted(() => ({
  configurationGet: vi.fn(),
  listRoles: vi.fn(),
  getRole: vi.fn(),
  createRole: vi.fn(),
  updateRole: vi.fn(),
  deleteRole: vi.fn(),
  setRolePermission: vi.fn(),
  removeRolePermission: vi.fn(),
  listPermissions: vi.fn(),
  getPermission: vi.fn(),
  listPermissionSets: vi.fn(),
  listFieldSecurity: vi.fn(),
  getFieldSecurity: vi.fn(),
  createFieldSecurity: vi.fn(),
  updateFieldSecurity: vi.fn(),
  deleteFieldSecurity: vi.fn(),
  listRowSecurity: vi.fn(),
  getRowSecurity: vi.fn(),
  createRowSecurity: vi.fn(),
  updateRowSecurity: vi.fn(),
  deleteRowSecurity: vi.fn(),
  listProfiles: vi.fn(),
  listProfileAssignments: vi.fn(),
  getProfileAssignment: vi.fn(),
  createProfileAssignment: vi.fn(),
  updateProfileAssignment: vi.fn(),
  revokeProfileAssignment: vi.fn(),
  listUserPermissionSets: vi.fn(),
  getUserPermissionSet: vi.fn(),
  createUserPermissionSet: vi.fn(),
  updateUserPermissionSet: vi.fn(),
  revokeUserPermissionSet: vi.fn(),
  listAuditLogs: vi.fn(),
}));

vi.mock("../services/security-service", () => ({
  securityService: {
    auditLogs: { list: mocks.listAuditLogs },
    configuration: { get: mocks.configurationGet },
    fieldSecurity: {
      create: mocks.createFieldSecurity,
      delete: mocks.deleteFieldSecurity,
      get: mocks.getFieldSecurity,
      list: mocks.listFieldSecurity,
      update: mocks.updateFieldSecurity,
    },
    permissions: { get: mocks.getPermission, list: mocks.listPermissions },
    permissionSets: { list: mocks.listPermissionSets },
    profileAssignments: {
      create: mocks.createProfileAssignment,
      get: mocks.getProfileAssignment,
      list: mocks.listProfileAssignments,
      revoke: mocks.revokeProfileAssignment,
      update: mocks.updateProfileAssignment,
    },
    roles: {
      create: mocks.createRole,
      delete: mocks.deleteRole,
      get: mocks.getRole,
      list: mocks.listRoles,
      removePermission: mocks.removeRolePermission,
      setPermission: mocks.setRolePermission,
      update: mocks.updateRole,
    },
    rowSecurity: {
      create: mocks.createRowSecurity,
      delete: mocks.deleteRowSecurity,
      get: mocks.getRowSecurity,
      list: mocks.listRowSecurity,
      update: mocks.updateRowSecurity,
    },
    securityProfiles: { list: mocks.listProfiles },
    userPermissionSets: {
      create: mocks.createUserPermissionSet,
      get: mocks.getUserPermissionSet,
      list: mocks.listUserPermissionSets,
      revoke: mocks.revokeUserPermissionSet,
      update: mocks.updateUserPermissionSet,
    },
  },
}));

const ids = {
  audit: "11111111-1111-4111-8111-111111111101",
  configUser: "11111111-1111-4111-8111-111111111102",
  field: "11111111-1111-4111-8111-111111111103",
  permission: "11111111-1111-4111-8111-111111111104",
  permissionSet: "11111111-1111-4111-8111-111111111105",
  profile: "11111111-1111-4111-8111-111111111106",
  profileAssignment: "11111111-1111-4111-8111-111111111107",
  role: "11111111-1111-4111-8111-111111111108",
  row: "11111111-1111-4111-8111-111111111109",
  tenant: "11111111-1111-4111-8111-111111111110",
  user: "11111111-1111-4111-8111-111111111111",
  userPermissionSet: "11111111-1111-4111-8111-111111111112",
} as const;

const pagination = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

const documentConfig: SecurityConfigurationDocument = {
  limits: {
    audit_collection_max_entries: 100,
    audit_default_window_days: 7,
    audit_max_window_days: 90,
    audit_payload_max_bytes: 65536,
    audit_reason_codes_max_entries: 10,
    audit_redaction_max_depth: 4,
    audit_string_max_length: 2000,
    correlation_id_max_length: 128,
    correlation_id_pattern: "^[a-z0-9-]+$",
    description_max_length: 500,
    list_page_size: 25,
    lookup_page_size: 10,
    mfa_methods_max_entries: 4,
    name_max_length: 80,
    name_min_length: 2,
    permission_set_duration_max_days: 90,
    permission_set_duration_min_days: 1,
    policy_array_max_entries: 50,
    predicate_compound_max_arguments: 8,
    predicate_hard_max_depth: 8,
    predicate_hard_max_in_values: 100,
    predicate_hard_max_nodes: 40,
    predicate_max_depth: 5,
    predicate_max_in_values: 50,
    predicate_max_nodes: 20,
    profile_absolute_timeout_max_hours: 24,
    profile_absolute_timeout_min_hours: 1,
    profile_concurrent_sessions_max: 5,
    profile_concurrent_sessions_min: 1,
    profile_idle_timeout_max_minutes: 480,
    profile_idle_timeout_min_minutes: 5,
    rate_requests_per_minute: 600,
    required_text_max_length: 120,
    role_hierarchy_max_depth: 5,
    row_priority_max: 1000,
    row_priority_min: 1,
    user_agent_max_length: 512,
  },
  defaults: {
    allowed_mfa_methods: ["totp", "webauthn"],
    automatic_revocation_reason: "Policy expired",
    field_edit_control: "read_only",
    field_visibility: "visible",
    mfa_precedence: { always: 4, conditional: 3, never: 1, sensitive_actions: 2 },
    row_owner_field: "owner_id",
    row_rule_priority: 100,
    row_rule_type: "ownership",
    profile_assignment_precedence: 10,
    security_profile: {
      absolute_session_timeout_hours: 8,
      access_notification: true,
      allowed_mfa_methods: ["totp"],
      copy_paste_allowed: false,
      download_allowed: true,
      login_notification: true,
      max_concurrent_sessions: 2,
      mfa_required: "conditional",
      mobile_access_allowed: true,
      print_allowed: false,
      profile_type: "standard",
      session_timeout_minutes: 30,
      time_restrictions: { timezone: "UTC", weekdays: [1, 2, 3, 4, 5], windows: [] },
    },
  },
  ordering: {
    audit_logs: ["-timestamp"],
    field_rules: ["module", "resource", "field"],
    permission_set_grants: ["-granted_at"],
    permission_sets: ["name"],
    profile_assignments: ["-valid_from"],
    role_assignments: ["-valid_from"],
    roles: ["name"],
    row_rules: ["module", "resource", "priority"],
    security_profiles: ["name"],
  },
  resilience: {
    connect_timeout_seconds: 2,
    failure_threshold: 3,
    max_retries: 2,
    read_timeout_seconds: 5,
    reset_timeout_seconds: 30,
  },
  remote_context_keys: ["tenant_id"],
  ui: { audit_timeline_page_size: 25, loading_skeleton_rows: 3 },
  semantic_tokens: {
    danger: "status-danger",
    neutral: "status-neutral",
    success: "status-success",
    warning: "status-warning",
  },
  commercial_controls: { entitlement: "security_access", quota: "policy_rules" },
  baseline_profile: {
    absolute_session_timeout_hours: 8,
    allowed_countries: ["US"],
    allowed_mfa_methods: ["totp"],
    blocked_countries: [],
    copy_paste_allowed: false,
    download_allowed: true,
    ip_blacklist: [],
    ip_whitelist: [],
    max_concurrent_sessions: 2,
    mfa_required: "conditional",
    mobile_access_allowed: true,
    print_allowed: false,
    session_timeout_minutes: 30,
  },
  feature_flags: {
    row_security: { cohorts: [], enabled: true, percentage: 100, roles: [] },
  },
};

const configuration: SecurityConfiguration = {
  id: "config-1",
  correlation_id: "corr-config",
  created_at: "2026-07-22T00:00:00Z",
  document: documentConfig,
  environment: "production",
  rollout: { cohorts: [], enabled: true, percentage: 100, role_ids: [] },
  updated_at: "2026-07-23T00:00:00Z",
  updated_by: ids.configUser,
  version: 7,
};

const permission: Permission = {
  id: ids.permission,
  action: "approve",
  code: "accounting_finance.invoice.approve",
  created_at: "2026-07-22T00:00:00Z",
  description: "Approve sensitive invoices",
  module: "accounting_finance",
  name: "Approve invoices",
  resource: "invoice",
  risk_level: "critical",
};

const role: Role = {
  id: ids.role,
  tenant_id: ids.tenant,
  assignment_count: 2,
  code: "finance_reviewer",
  created_at: "2026-07-22T00:00:00Z",
  created_by: ids.configUser,
  deleted_at: null,
  denied_permissions: [],
  description: "Reviews finance approvals",
  direct_permissions: [
    { id: "direct-1", is_granted: true, permission, source: "direct", source_name: "Direct" },
  ],
  hierarchy_level: 0,
  inherited_permissions: [],
  is_active: true,
  is_deleted: false,
  is_system: false,
  name: "Finance reviewer",
  parent_role_id: null,
  permission_set_permissions: [],
  role_type: "functional",
  updated_at: "2026-07-23T00:00:00Z",
  updated_by: ids.configUser,
};

const fieldRule: FieldSecurity = {
  id: ids.field,
  tenant_id: ids.tenant,
  created_at: "2026-07-22T00:00:00Z",
  created_by: ids.configUser,
  deleted_at: null,
  edit_control: "read_only",
  field: "tax_identifier",
  is_active: true,
  is_deleted: false,
  mask_pattern: "****-last4",
  module: "accounting_finance",
  resource: "vendor",
  role_id: ids.role,
  role_name: role.name,
  updated_at: "2026-07-23T00:00:00Z",
  updated_by: ids.configUser,
  visibility: "masked",
};

const rowRule: RowSecurityRule = {
  id: ids.row,
  tenant_id: ids.tenant,
  created_at: "2026-07-22T00:00:00Z",
  created_by: ids.configUser,
  deleted_at: null,
  filter_criteria: { field: "region", op: "eq", value: "NA" },
  is_active: true,
  is_deleted: false,
  module: "accounting_finance",
  priority: 100,
  resource: "invoice",
  role_id: ids.role,
  role_name: role.name,
  rule_type: "criteria",
  updated_at: "2026-07-23T00:00:00Z",
  updated_by: ids.configUser,
  version: 3,
};

const profile: SecurityProfile = {
  id: ids.profile,
  tenant_id: ids.tenant,
  absolute_session_timeout_hours: 8,
  access_notification: true,
  allowed_countries: ["US"],
  allowed_mfa_methods: ["webauthn"],
  assignment_count: 1,
  blocked_countries: [],
  copy_paste_allowed: false,
  created_at: "2026-07-22T00:00:00Z",
  created_by: ids.configUser,
  deleted_at: null,
  description: "Privileged finance controls",
  download_allowed: false,
  ip_blacklist: [],
  ip_whitelist: [],
  is_active: true,
  is_deleted: false,
  login_notification: true,
  max_concurrent_sessions: 1,
  mfa_required: "always",
  mobile_access_allowed: false,
  name: "Privileged finance",
  password_policy: { minimum_length: 14, require_symbol: true },
  print_allowed: false,
  profile_type: "privileged",
  session_timeout_minutes: 20,
  time_restrictions: { timezone: "UTC", weekdays: [1, 2, 3, 4, 5], windows: [] },
  updated_at: "2026-07-23T00:00:00Z",
  updated_by: ids.configUser,
};

const profileAssignment: SecurityProfileAssignment = {
  id: ids.profileAssignment,
  tenant_id: ids.tenant,
  assigned_by: ids.configUser,
  created_at: "2026-07-22T00:00:00Z",
  is_active: true,
  precedence: 10,
  reason: "Privileged review",
  revoked_at: null,
  revoked_by: null,
  revocation_reason: "",
  role_id: null,
  role_name: null,
  security_profile_id: ids.profile,
  security_profile_name: profile.name,
  updated_at: "2026-07-23T00:00:00Z",
  user_display: "Ada Lovelace",
  user_id: ids.user,
  valid_from: "2026-07-22T00:00:00Z",
  valid_until: null,
};

const userPermissionSet: UserPermissionSet = {
  id: ids.userPermissionSet,
  tenant_id: ids.tenant,
  created_at: "2026-07-22T00:00:00Z",
  expires_at: "2027-01-01T00:00:00Z",
  granted_at: "2026-07-22T00:00:00Z",
  granted_by: ids.configUser,
  is_active: true,
  permission_set_id: ids.permissionSet,
  permission_set_name: "Emergency close",
  reason: "Close window",
  revoked_at: null,
  revoked_by: null,
  revocation_reason: "",
  updated_at: "2026-07-23T00:00:00Z",
  user_display: "Ada Lovelace",
  user_id: ids.user,
};

const auditLog: SecurityAuditLog = {
  id: ids.audit,
  tenant_id: ids.tenant,
  action: "security.row_rule.evaluate",
  actor_type: "user",
  correlation_id: "corr-audit-row-deny",
  decision: "deny",
  details: { record_id: "invoice-778", redacted_fields: ["tax_identifier"] },
  ip_address: null,
  reason_codes: ["ROW_RULE_DENIED"],
  resource_id: ids.row,
  resource_type: "row_security_rule",
  timestamp: "2026-07-23T00:00:00Z",
};

function page<T>(items: readonly T[]) {
  return { correlationId: "corr-list", items, pagination, timestamp: "2026-07-23T00:00:00Z" };
}

function one<T>(data: T) {
  return { correlationId: "corr-one", data, timestamp: "2026-07-23T00:00:00Z" };
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>;
}

function renderPage(element: React.ReactNode, initial: string) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
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
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <LocationProbe />
        <Routes>
          <Route path={path} element={element} />
          <Route path="/security-access-control/roles/:id" element={<span>Role detail</span>} />
          <Route
            path="/security-access-control/field-security/:id"
            element={<span>Field detail</span>}
          />
          <Route
            path="/security-access-control/row-security/:id"
            element={<span>Row detail</span>}
          />
          <Route
            path="/security-access-control/assignments/profile-assignments/:id"
            element={<span>Profile assignment detail</span>}
          />
          <Route
            path="/security-access-control/assignments/permission-set-grants/:id"
            element={<span>Grant detail</span>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("security access-control disjoint slice", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.configurationGet.mockResolvedValue(one(configuration));
    mocks.listRoles.mockResolvedValue(page([role]));
    mocks.getRole.mockResolvedValue(one(role));
    mocks.createRole.mockResolvedValue(one(role));
    mocks.updateRole.mockResolvedValue(one(role));
    mocks.deleteRole.mockResolvedValue(undefined);
    mocks.setRolePermission.mockResolvedValue(one({ id: "role-permission-1" }));
    mocks.removeRolePermission.mockResolvedValue(undefined);
    mocks.listPermissions.mockResolvedValue(page([permission]));
    mocks.getPermission.mockResolvedValue(one(permission));
    mocks.listPermissionSets.mockResolvedValue(
      page([
        {
          id: ids.permissionSet,
          tenant_id: ids.tenant,
          active_grant_count: 1,
          created_at: "2026-07-22T00:00:00Z",
          created_by: ids.configUser,
          default_duration_days: 14,
          deleted_at: null,
          description: "Temporary close access",
          is_active: true,
          is_deleted: false,
          name: "Emergency close",
          permission_ids: [ids.permission],
          permissions: [permission],
          updated_at: "2026-07-23T00:00:00Z",
          updated_by: ids.configUser,
        },
      ])
    );
    mocks.listFieldSecurity.mockResolvedValue(page([fieldRule]));
    mocks.getFieldSecurity.mockResolvedValue(one(fieldRule));
    mocks.createFieldSecurity.mockResolvedValue(one(fieldRule));
    mocks.updateFieldSecurity.mockResolvedValue(one(fieldRule));
    mocks.deleteFieldSecurity.mockResolvedValue(undefined);
    mocks.listRowSecurity.mockResolvedValue(page([rowRule]));
    mocks.getRowSecurity.mockResolvedValue(one(rowRule));
    mocks.createRowSecurity.mockResolvedValue(one(rowRule));
    mocks.updateRowSecurity.mockResolvedValue(one(rowRule));
    mocks.deleteRowSecurity.mockResolvedValue(undefined);
    mocks.listProfiles.mockResolvedValue(page([profile]));
    mocks.listProfileAssignments.mockResolvedValue(page([profileAssignment]));
    mocks.getProfileAssignment.mockResolvedValue(one(profileAssignment));
    mocks.createProfileAssignment.mockResolvedValue(one(profileAssignment));
    mocks.updateProfileAssignment.mockResolvedValue(one(profileAssignment));
    mocks.revokeProfileAssignment.mockResolvedValue(undefined);
    mocks.listUserPermissionSets.mockResolvedValue(page([userPermissionSet]));
    mocks.getUserPermissionSet.mockResolvedValue(one(userPermissionSet));
    mocks.createUserPermissionSet.mockResolvedValue(one(userPermissionSet));
    mocks.updateUserPermissionSet.mockResolvedValue(one(userPermissionSet));
    mocks.revokeUserPermissionSet.mockResolvedValue(undefined);
    mocks.listAuditLogs.mockResolvedValue(page([]));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("applies role filters, resets filtered empty state, and creates roles only after validation passes", async () => {
    mocks.listRoles.mockResolvedValueOnce(page([])).mockResolvedValue(page([role]));
    const user = userEvent.setup();
    const list = renderPage(
      <RolesPage />,
      "/security-access-control/roles?search=ghost&role_type=custom&is_active=false&ordering=-created_at"
    );

    expect(await screen.findByText("No roles match these filters")).toBeInTheDocument();
    expect(mocks.listRoles).toHaveBeenCalledWith(
      expect.objectContaining({
        is_active: false,
        ordering: "-created_at",
        role_type: "custom",
        search: "ghost",
      })
    );
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Current route")).toHaveTextContent(
        "/security-access-control/roles"
      )
    );
    list.unmount();

    renderRoutePage({
      element: <RoleCreatePage />,
      initial: "/security-access-control/roles/new",
      path: "/security-access-control/roles/new",
    });
    expect(await screen.findByRole("heading", { name: "Create role" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Name"), "F");
    await user.type(screen.getByLabelText("Stable code"), "Bad Code");
    await user.click(screen.getByRole("button", { name: "Save role" }));
    expect(await screen.findByText("Use lowercase snake_case")).toBeInTheDocument();
    expect(mocks.createRole).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Finance reviewer");
    await user.clear(screen.getByLabelText("Stable code"));
    await user.type(screen.getByLabelText("Stable code"), "finance_reviewer");
    await user.selectOptions(screen.getByLabelText("Role type"), "temporary");
    await user.type(screen.getByLabelText("Description"), "Time-boxed review role");
    await user.click(screen.getByRole("button", { name: "Save role" }));

    await waitFor(() =>
      expect(mocks.createRole).toHaveBeenCalledWith({
        code: "finance_reviewer",
        description: "Time-boxed review role",
        parent_role_id: null,
        role_type: "temporary",
        name: "Finance reviewer",
      })
    );
  });

  it("executes governed role allow, deny, and inherit actions from detail", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "prompt").mockReturnValue("Decision removed after review");
    renderRoutePage({
      element: <RoleDetailPage />,
      initial: `/security-access-control/roles/${ids.role}`,
      path: "/security-access-control/roles/:id",
    });

    expect(await screen.findByRole("heading", { name: role.name })).toBeInTheDocument();
    const matrix = screen.getByRole("table");
    await user.click(within(matrix).getByRole("button", { name: "Deny" }));
    await waitFor(() =>
      expect(mocks.setRolePermission).toHaveBeenCalledWith(ids.role, {
        is_granted: false,
        permission_id: ids.permission,
      })
    );

    await user.click(within(matrix).getByRole("button", { name: "Allow" }));
    await waitFor(() =>
      expect(mocks.setRolePermission).toHaveBeenLastCalledWith(ids.role, {
        is_granted: true,
        permission_id: ids.permission,
      })
    );

    await user.click(within(matrix).getByRole("button", { name: "Inherit" }));
    await waitFor(() =>
      expect(mocks.removeRolePermission).toHaveBeenCalledWith(ids.role, ids.permission, {
        reason: "Decision removed after review",
      })
    );
  });

  it("keeps permissions behind configuration, applies filters, and surfaces RBAC errors with retry", async () => {
    const user = userEvent.setup();
    mocks.configurationGet.mockReturnValueOnce(new Promise(() => undefined));
    const loading = renderPage(<PermissionsPage />, "/security-access-control/permissions");
    expect(screen.getByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    expect(mocks.listPermissions).not.toHaveBeenCalled();
    loading.unmount();

    mocks.listPermissions
      .mockRejectedValueOnce(new ApiError("Denied", 403, undefined, "POLICY_DENIED", "corr-rbac"))
      .mockResolvedValueOnce(page([permission]));
    renderPage(<PermissionsPage />, "/security-access-control/permissions");
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText(/corr-rbac/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(permission.code)).toBeInTheDocument();

    cleanup();
    renderPage(
      <PermissionsPage />,
      "/security-access-control/permissions?search=approve&module=accounting_finance&risk_level=critical"
    );
    expect(await screen.findByText(permission.code)).toBeInTheDocument();
    await waitFor(() =>
      expect(mocks.listPermissions).toHaveBeenLastCalledWith(
        expect.objectContaining({
          module: "accounting_finance",
          ordering: "module,resource,action",
          page_size: 25,
          risk_level: "critical",
          search: "approve",
        })
      )
    );
  });

  it("lists row rules with governed filters and creates canonical predicates after validation", async () => {
    const user = userEvent.setup();
    const list = renderPage(
      <RowSecurityPage />,
      `/security-access-control/row-security?module=accounting_finance&resource=invoice&role_id=${ids.role}&rule_type=criteria&is_active=true`
    );

    expect(await screen.findByText(role.name)).toBeInTheDocument();
    expect(screen.getByText('region equals "NA"')).toBeInTheDocument();
    expect(mocks.listRowSecurity).toHaveBeenCalledWith(
      expect.objectContaining({
        is_active: true,
        module: "accounting_finance",
        ordering: "module,resource,priority",
        page_size: 25,
        resource: "invoice",
        role_id: ids.role,
        rule_type: "criteria",
      })
    );
    list.unmount();

    renderRoutePage({
      element: <RowSecurityCreatePage />,
      initial: "/security-access-control/row-security/new",
      path: "/security-access-control/row-security/new",
    });
    expect(await screen.findByRole("heading", { name: "Create row rule" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Module"), "Accounting_Finance");
    await user.type(screen.getByLabelText("Resource"), "Invoice");
    await user.selectOptions(screen.getByLabelText("Role"), ids.role);
    await user.selectOptions(screen.getByLabelText("Operator"), "in");
    await user.click(screen.getByRole("button", { name: "Save row rule" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A comparison value is required.");
    expect(mocks.createRowSecurity).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByLabelText("Rule type"), "criteria");
    await user.clear(screen.getByLabelText("Record field"));
    await user.type(screen.getByLabelText("Record field"), "region");
    await user.selectOptions(screen.getByLabelText("Operator"), "in");
    await user.type(screen.getByLabelText("Comma-separated values"), "NA, EU");
    expect(screen.getByText("region is one of NA, EU")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save row rule" }));

    await waitFor(() =>
      expect(mocks.createRowSecurity).toHaveBeenCalledWith({
        filter_criteria: { field: "region", op: "in", value: ["NA", "EU"] },
        is_active: true,
        module: "accounting_finance",
        priority: 100,
        resource: "invoice",
        role_id: ids.role,
        rule_type: "criteria",
      })
    );
  });

  it("renders field rule filters, handles configuration errors, and requires mask preview before create", async () => {
    const user = userEvent.setup();
    const list = renderPage(
      <FieldSecurityPage />,
      `/security-access-control/field-security?module=accounting_finance&field=tax_identifier&visibility=masked&edit_control=read_only&is_active=true`
    );

    expect(await screen.findByText("****-last4")).toBeInTheDocument();
    expect(mocks.listFieldSecurity).toHaveBeenCalledWith(
      expect.objectContaining({
        edit_control: "read_only",
        field: "tax_identifier",
        is_active: true,
        module: "accounting_finance",
        ordering: "module,resource,field",
        page_size: 25,
        visibility: "masked",
      })
    );
    list.unmount();

    mocks.configurationGet.mockRejectedValueOnce(
      new ApiError("Policy unavailable", 503, undefined, "SECURITY_NOT_READY", "corr-config-down")
    );
    const error = renderPage(<FieldSecurityPage />, "/security-access-control/field-security");
    expect(await screen.findByText("Security capability unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-config-down/u)).toBeInTheDocument();
    error.unmount();

    renderRoutePage({
      element: <FieldSecurityCreatePage />,
      initial: "/security-access-control/field-security/new",
      path: "/security-access-control/field-security/new",
    });
    expect(await screen.findByRole("heading", { name: "Create field rule" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Module"), "Accounting_Finance");
    await user.type(screen.getByLabelText("Resource"), "Vendor");
    await user.type(screen.getByLabelText("Field"), "Tax_Identifier");
    await user.selectOptions(screen.getByLabelText("Role"), ids.role);
    await user.selectOptions(screen.getByLabelText("Visibility"), "masked");
    await user.type(screen.getByLabelText("Mask pattern"), "x".repeat(101));
    await user.click(screen.getByRole("button", { name: "Save field rule" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "String must contain at most 100 character(s)"
    );
    expect(mocks.createFieldSecurity).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Mask pattern"));
    await user.type(screen.getByLabelText("Mask pattern"), "****-last4");
    await user.clear(screen.getByLabelText("Sample value (browser only)"));
    await user.type(screen.getByLabelText("Sample value (browser only)"), "123-45-6789");
    expect(screen.getByText("****-last4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save field rule" }));

    await waitFor(() =>
      expect(mocks.createFieldSecurity).toHaveBeenCalledWith({
        edit_control: "read_only",
        field: "tax_identifier",
        is_active: true,
        mask_pattern: "****-last4",
        module: "accounting_finance",
        resource: "vendor",
        role_id: ids.role,
        visibility: "masked",
      })
    );
  });

  it("guards row-rule delete reasons and normalizes edit payloads before mutation", async () => {
    const user = userEvent.setup();
    const prompt = vi
      .spyOn(window, "prompt")
      .mockReturnValueOnce("")
      .mockReturnValueOnce("x".repeat(121))
      .mockReturnValueOnce("Retiring superseded regional rule");

    const detail = renderRoutePage({
      element: <RowSecurityDetailPage />,
      initial: `/security-access-control/row-security/${ids.row}`,
      path: "/security-access-control/row-security/:id",
    });
    expect(
      await screen.findByRole("heading", { name: "accounting_finance.invoice" })
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete rule" }));
    await user.click(screen.getByRole("button", { name: "Delete rule" }));
    expect(mocks.deleteRowSecurity).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete rule" }));
    await waitFor(() =>
      expect(mocks.deleteRowSecurity).toHaveBeenCalledWith(ids.row, {
        reason: "Retiring superseded regional rule",
      })
    );
    detail.unmount();
    prompt.mockRestore();

    const inactiveRule: RowSecurityRule = { ...rowRule, is_active: false };
    mocks.getRowSecurity.mockResolvedValueOnce(one(inactiveRule));
    renderRoutePage({
      element: <RowSecurityEditPage />,
      initial: `/security-access-control/row-security/${ids.row}/edit`,
      path: "/security-access-control/row-security/:id/edit",
    });
    expect(await screen.findByRole("heading", { name: "Edit row rule" })).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Priority"));
    await user.type(screen.getByLabelText("Priority"), "250");
    await user.clear(screen.getByLabelText("Record field"));
    await user.type(screen.getByLabelText("Record field"), "tenant_id");
    await user.selectOptions(screen.getByLabelText("Operator"), "tenant");
    await user.click(screen.getByLabelText("Rule active"));
    await user.click(screen.getByRole("button", { name: "Save row rule" }));
    await waitFor(() =>
      expect(mocks.updateRowSecurity).toHaveBeenCalledWith(ids.row, {
        filter_criteria: { field: "tenant_id", op: "tenant" },
        is_active: true,
        module: "accounting_finance",
        priority: 250,
        resource: "invoice",
        role_id: ids.role,
        rule_type: "criteria",
      })
    );
  });

  it("guards field-rule delete reasons and normalizes hidden edit payloads", async () => {
    const user = userEvent.setup();
    const prompt = vi
      .spyOn(window, "prompt")
      .mockReturnValueOnce(null)
      .mockReturnValueOnce("Replacing field rule with registered metadata policy");

    const detail = renderRoutePage({
      element: <FieldSecurityDetailPage />,
      initial: `/security-access-control/field-security/${ids.field}`,
      path: "/security-access-control/field-security/:id",
    });
    expect(
      await screen.findByRole("heading", { name: "vendor.tax_identifier" })
    ).toBeInTheDocument();
    expect(screen.getAllByText("****-last4").length).toBeGreaterThanOrEqual(2);
    await user.click(screen.getByRole("button", { name: "Delete rule" }));
    expect(mocks.deleteFieldSecurity).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete rule" }));
    await waitFor(() =>
      expect(mocks.deleteFieldSecurity).toHaveBeenCalledWith(ids.field, {
        reason: "Replacing field rule with registered metadata policy",
      })
    );
    detail.unmount();
    prompt.mockRestore();

    renderRoutePage({
      element: <FieldSecurityEditPage />,
      initial: `/security-access-control/field-security/${ids.field}/edit`,
      path: "/security-access-control/field-security/:id/edit",
    });
    expect(await screen.findByRole("heading", { name: "Edit field rule" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Visibility"), "hidden");
    expect(screen.getByText("Field omitted from the rendered resource.")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Edit control"), "editable");
    await user.click(screen.getByLabelText("Rule is active"));
    await user.click(screen.getByRole("button", { name: "Save field rule" }));
    await waitFor(() =>
      expect(mocks.updateFieldSecurity).toHaveBeenCalledWith(ids.field, {
        edit_control: "editable",
        field: "tax_identifier",
        is_active: false,
        mask_pattern: "****-last4",
        module: "accounting_finance",
        resource: "vendor",
        role_id: ids.role,
        visibility: "hidden",
      })
    );
  });

  it("normalizes permission catalog filters, reset state, detail evidence, and empty audit filters", async () => {
    const user = userEvent.setup();
    mocks.listPermissions.mockResolvedValueOnce(page([])).mockResolvedValue(page([permission]));
    const list = renderPage(
      <PermissionsPage />,
      "/security-access-control/permissions?search=missing&module=accounting_finance" +
        "&resource=invoice&action=approve&risk_level=critical&ordering=action&page=3"
    );
    expect(await screen.findByText("No permissions match these filters")).toBeInTheDocument();
    expect(mocks.listPermissions).toHaveBeenCalledWith({
      action: "approve",
      module: "accounting_finance",
      ordering: "action",
      page: 3,
      page_size: 25,
      resource: "invoice",
      risk_level: "critical",
      search: "missing",
    });
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Current route")).toHaveTextContent(
        "/security-access-control/permissions"
      )
    );
    list.unmount();

    const detail = renderRoutePage({
      element: <PermissionDetailPage />,
      initial: `/security-access-control/permissions/${ids.permission}`,
      path: "/security-access-control/permissions/:id",
    });
    expect(await screen.findByRole("heading", { name: permission.name })).toBeInTheDocument();
    expect(screen.getByText(permission.code)).toBeInTheDocument();
    expect(screen.getByText(/This catalog entry is read-only/u)).toBeInTheDocument();
    expect(mocks.listAuditLogs).toHaveBeenLastCalledWith({
      ordering: "-timestamp",
      page_size: 25,
      resource_id: ids.permission,
      resource_type: "permission",
    });
    detail.unmount();

    mocks.listAuditLogs.mockResolvedValueOnce(page([]));
    const audit = renderPage(
      <AuditLogPage />,
      "/security-access-control/audit-logs?from=2026-07-20&to=2026-07-23&action=missing"
    );
    expect(await screen.findByText("No audit events match these filters")).toBeInTheDocument();
    const resetButtons = screen.getAllByRole("button", { name: "Reset filters" });
    await user.click(resetButtons.at(-1)!);
    await waitFor(() =>
      expect(screen.getByLabelText("Current route")).toHaveTextContent(
        "/security-access-control/audit-logs"
      )
    );
    audit.unmount();
  });

  it("filters profile assignments and submits valid role-scoped assignments only after date validation", async () => {
    const user = userEvent.setup();
    const list = renderPage(
      <ProfileAssignmentsPage />,
      `/security-access-control/assignments/profile-assignments?profile_id=${ids.profile}&user_id=${ids.user}&revoked=false`
    );

    expect(await screen.findByText(profile.name)).toBeInTheDocument();
    expect(mocks.listProfileAssignments).toHaveBeenCalledWith(
      expect.objectContaining({
        page_size: 25,
        profile_id: ids.profile,
        revoked: false,
        user_id: ids.user,
      })
    );
    list.unmount();

    renderRoutePage({
      element: <ProfileAssignmentCreatePage />,
      initial: "/security-access-control/assignments/profile-assignments/create",
      path: "/security-access-control/assignments/profile-assignments/create",
    });
    expect(
      await screen.findByRole("heading", { name: "Assign security profile" })
    ).toBeInTheDocument();
    await screen.findByRole("option", { name: profile.name });
    await user.selectOptions(screen.getByLabelText("Security profile"), ids.profile);
    await user.selectOptions(screen.getByLabelText("Subject type"), "role");
    await user.selectOptions(screen.getByLabelText("Role"), ids.role);
    await user.type(screen.getByLabelText("Precedence"), "10");
    await user.clear(screen.getByLabelText("Valid from"));
    await user.type(screen.getByLabelText("Valid from"), "2026-08-10T12:00");
    await user.type(screen.getByLabelText("Valid until"), "2026-08-10T11:00");
    await user.type(screen.getByLabelText("Assignment reason"), "Quarterly access review");
    await user.click(screen.getByRole("button", { name: "Save assignment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Validity end must be after start.");
    expect(mocks.createProfileAssignment).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Valid until"));
    await user.type(screen.getByLabelText("Valid until"), "2026-08-10T13:00");
    await user.click(screen.getByRole("button", { name: "Save assignment" }));
    await waitFor(() =>
      expect(mocks.createProfileAssignment).toHaveBeenCalledWith({
        precedence: 10,
        reason: "Quarterly access review",
        role_id: ids.role,
        security_profile_id: ids.profile,
        user_id: null,
        valid_from: "2026-08-10T06:30:00.000Z",
        valid_until: "2026-08-10T07:30:00.000Z",
      })
    );
  });

  it("filters permission-set grants and prevents expired grant submissions before server mutation", async () => {
    const user = userEvent.setup();
    mocks.listUserPermissionSets
      .mockResolvedValueOnce(page([]))
      .mockResolvedValue(page([userPermissionSet]));
    const list = renderPage(
      <UserPermissionSetsPage />,
      `/security-access-control/assignments/permission-set-grants?user_id=${ids.user}&permission_set_id=${ids.permissionSet}&revoked=true`
    );

    expect(
      await screen.findByText("No permission-set grants match these filters")
    ).toBeInTheDocument();
    expect(mocks.listUserPermissionSets).toHaveBeenCalledWith(
      expect.objectContaining({
        page_size: 25,
        permission_set_id: ids.permissionSet,
        revoked: true,
        user_id: ids.user,
      })
    );
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Current route")).toHaveTextContent(
        "/security-access-control/assignments/permission-set-grants"
      )
    );
    list.unmount();

    renderRoutePage({
      element: <UserPermissionSetCreatePage />,
      initial: "/security-access-control/assignments/permission-set-grants/create",
      path: "/security-access-control/assignments/permission-set-grants/create",
    });
    expect(
      await screen.findByRole("heading", { name: "Grant permission set" })
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("User UUID"), ids.user);
    await user.selectOptions(screen.getByLabelText("Permission set"), ids.permissionSet);
    await user.type(screen.getByLabelText("Expires at"), "2020-01-01T00:00");
    await user.type(screen.getByLabelText("Grant reason"), "Emergency close support");
    await user.click(screen.getByRole("button", { name: "Save grant" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Expiry must be in the future.");
    expect(mocks.createUserPermissionSet).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Expires at"));
    await user.type(screen.getByLabelText("Expires at"), "2027-01-01T00:00");
    await user.click(screen.getByRole("button", { name: "Save grant" }));
    await waitFor(() =>
      expect(mocks.createUserPermissionSet).toHaveBeenCalledWith({
        expires_at: "2026-12-31T18:30:00.000Z",
        permission_set_id: ids.permissionSet,
        reason: "Emergency close support",
        user_id: ids.user,
      })
    );
  });

  it("fails closed while security configuration is unavailable across row, field, and assignment policies", () => {
    mocks.configurationGet.mockReturnValue(new Promise(() => undefined));

    const row = renderPage(<RowSecurityPage />, "/security-access-control/row-security");
    expect(screen.getByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    row.unmount();

    const field = renderPage(<FieldSecurityPage />, "/security-access-control/field-security");
    expect(screen.getByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    field.unmount();

    const profileAssignments = renderPage(
      <ProfileAssignmentsPage />,
      "/security-access-control/assignments/profile-assignments"
    );
    expect(screen.getByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    profileAssignments.unmount();

    renderPage(
      <UserPermissionSetsPage />,
      "/security-access-control/assignments/permission-set-grants"
    );
    expect(screen.getByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    expect(mocks.listRowSecurity).not.toHaveBeenCalled();
    expect(mocks.listFieldSecurity).not.toHaveBeenCalled();
    expect(mocks.listProfileAssignments).not.toHaveBeenCalled();
    expect(mocks.listUserPermissionSets).not.toHaveBeenCalled();
  });

  it("bounds audit evidence windows, applies governed filters, resets them, and retries RBAC failures", async () => {
    const user = userEvent.setup();
    const invalid = renderPage(
      <AuditLogPage />,
      "/security-access-control/audit-logs?from=2026-01-01&to=2026-08-01"
    );
    expect(await screen.findByText("Security request failed")).toBeInTheDocument();
    expect(screen.getByText("Choose a date range from 0 to 90 days.")).toBeInTheDocument();
    expect(mocks.listAuditLogs).not.toHaveBeenCalled();
    invalid.unmount();

    mocks.listAuditLogs
      .mockRejectedValueOnce(
        new ApiError("Denied", 403, undefined, "POLICY_DENIED", "corr-audit-denied")
      )
      .mockResolvedValueOnce(page([auditLog]));
    const filteredAuditRoute =
      "/security-access-control/audit-logs?from=2026-07-20&to=2026-07-23" +
      `&action=security.row_rule.evaluate&actor_type=user&actor_id=${ids.user}` +
      `&resource_type=row_security_rule&resource_id=${ids.row}` +
      "&decision=deny&correlation_id=corr-audit-row-deny";
    renderPage(<AuditLogPage />, filteredAuditRoute);

    expect(await screen.findByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText(/corr-audit-denied/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("security.row_rule.evaluate")).toBeInTheDocument();
    expect(screen.getByText(`row_security_rule · ${ids.row}`)).toBeInTheDocument();
    expect(screen.getByText("corr-audit-row-deny")).toBeInTheDocument();
    await waitFor(() =>
      expect(mocks.listAuditLogs).toHaveBeenLastCalledWith({
        action: "security.row_rule.evaluate",
        actor_id: ids.user,
        actor_type: "user",
        correlation_id: "corr-audit-row-deny",
        decision: "deny",
        from: "2026-07-20",
        ordering: "-timestamp",
        page: 1,
        page_size: 25,
        resource_id: ids.row,
        resource_type: "row_security_rule",
        to: "2026-07-23",
      })
    );

    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Current route")).toHaveTextContent(
        "/security-access-control/audit-logs"
      )
    );
  });

  it("revokes profile assignments and permission-set grants only with governed audit reasons", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "prompt")
      .mockReturnValueOnce("")
      .mockReturnValueOnce("Profile access ended after review")
      .mockReturnValueOnce("x".repeat(121))
      .mockReturnValueOnce("Permission bundle expired after support close");

    const profileView = renderRoutePage({
      element: <ProfileAssignmentDetailPage />,
      initial: `/security-access-control/assignments/profile-assignments/${ids.profileAssignment}`,
      path: "/security-access-control/assignments/profile-assignments/:id",
    });
    expect(await screen.findByRole("heading", { name: profile.name })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Revoke" }));
    expect(mocks.revokeProfileAssignment).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() =>
      expect(mocks.revokeProfileAssignment).toHaveBeenCalledWith(ids.profileAssignment, {
        reason: "Profile access ended after review",
      })
    );
    profileView.unmount();

    renderRoutePage({
      element: <UserPermissionSetDetailPage />,
      initial: `/security-access-control/assignments/permission-set-grants/${ids.userPermissionSet}`,
      path: "/security-access-control/assignments/permission-set-grants/:id",
    });
    expect(
      await screen.findByRole("heading", { name: userPermissionSet.permission_set_name })
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Revoke" }));
    expect(mocks.revokeUserPermissionSet).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() =>
      expect(mocks.revokeUserPermissionSet).toHaveBeenCalledWith(ids.userPermissionSet, {
        reason: "Permission bundle expired after support close",
      })
    );
  });

  it("renders SecurityUI audit timelines and fail-closed confirm controls from configuration", async () => {
    const onConfirm = vi.fn();
    vi.spyOn(window, "prompt").mockReturnValue("Remove after owner approval");
    mocks.listAuditLogs.mockResolvedValueOnce(page([auditLog]));

    renderPage(
      <>
        <AuditTimeline resourceType="row_security_rule" resourceId={ids.row} />
        <ConfirmButton
          label="Delete rule"
          question="Delete this row rule?"
          pending={false}
          onConfirm={onConfirm}
        />
      </>,
      "/security-access-control/row-security"
    );

    expect(await screen.findByText("security.row_rule.evaluate")).toBeInTheDocument();
    expect(screen.getByText("deny")).toBeInTheDocument();
    expect(screen.getByText("corr-audit-row-deny")).toBeInTheDocument();
    expect(mocks.listAuditLogs).toHaveBeenCalledWith({
      ordering: "-timestamp",
      page_size: 25,
      resource_id: ids.row,
      resource_type: "row_security_rule",
    });
    await userEvent.click(screen.getByRole("button", { name: "Delete rule" }));
    expect(onConfirm).toHaveBeenCalledWith({ reason: "Remove after owner approval" });
  });

  it("covers SecurityUI shared fail-closed, pagination, and navigation edge states", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    const onReset = vi.fn();
    const onCreate = vi.fn();
    const onPage = vi.fn();

    function DirtyProbe({ dirty }: { readonly dirty: boolean }) {
      useUnsavedChanges(dirty);
      return <span>dirty guard</span>;
    }

    renderPage(
      <>
        <PageHeader title="Security console" description="Governed security administration" />
        <PageSkeleton rows={2} label="Loading governed security" />
        <GovernedError
          error={new ApiError("conflict", 409, undefined, "ACTIVE_ASSIGNMENT", "corr-conflict")}
          retry={retry}
        />
        <GovernedError error={new Error("plain failure")} />
        <EmptyPanel filtered onReset={onReset} noun="roles" />
        <EmptyPanel filtered={false} create={onCreate} noun="permission grants" />
        <Pagination
          value={{
            ...pagination,
            count: 75,
            has_next: true,
            has_previous: true,
            page: 2,
            total_pages: 3,
          }}
          onPage={onPage}
        />
        <StatusChip active />
        <StatusChip active={false} label="Suspended" />
        <Surface>
          <span>Untitled surface content</span>
        </Surface>
        <ResourceTable
          result={page([{ id: ids.permission, name: "Run import" }])}
          columns={[{ label: "Permission", render: (item) => item.name }]}
          detailRoute={(id) => `/security-access-control/permissions/${id}`}
          loadingMore
        />
        <ResourceGrid
          result={page([{ id: ids.role, name: "Auditor" }])}
          render={(item) => <span>{item.name}</span>}
          onPage={onPage}
          loadingMore
        />
        <DirtyProbe dirty />
      </>,
      "/security-access-control/roles"
    );

    expect(document.title).toBe("Security console · SARAISE");
    expect(screen.getByLabelText("Loading governed security")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Change conflict")).toBeInTheDocument();
    expect(screen.getByText(/Correlation ID:\s*corr-conflict/)).toBeInTheDocument();
    expect(screen.getByText("Security request failed")).toBeInTheDocument();
    expect(screen.getAllByText("Loading updated security records…")).toHaveLength(2);
    expect(screen.getByText("Untitled surface content")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Suspended")).toBeInTheDocument();
    expect(formatDate(null)).toBe("—");

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await user.click(screen.getByRole("button", { name: "Create first record" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(onReset).toHaveBeenCalledOnce();
    expect(onCreate).toHaveBeenCalledOnce();

    const previousButtons = screen.getAllByRole("button", { name: /Previous/i });
    const nextButtons = screen.getAllByRole("button", { name: /Next/i });
    const previousButton = previousButtons[0];
    const nextButton = nextButtons[0];
    if (!previousButton || !nextButton) throw new Error("Pagination controls were not rendered.");
    await user.click(previousButton);
    await user.click(nextButton);
    expect(onPage).toHaveBeenCalledWith(1);
    expect(onPage).toHaveBeenCalledWith(3);

    await user.click(screen.getByRole("link", { name: "View" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      `/security-access-control/permissions/${ids.permission}`
    );

    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });
});
