/* eslint-disable max-lines-per-function */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type { AssignmentFilters } from "../contracts";
import { AccessSimulatorPage } from "./AccessSimulatorPage";
import {
  AssignmentsPage,
  UserRoleCreatePage,
  UserRoleDetailPage,
  UserRoleEditPage,
} from "./AssignmentsPage";
import { RoleCreatePage, RolesPage } from "./RolesPage";

const mocks = vi.hoisted(() => ({
  getConfiguration: vi.fn(),
  listRoles: vi.fn(),
  listUserRoles: vi.fn(),
  getUserRole: vi.fn(),
  createUserRole: vi.fn(),
  updateUserRole: vi.fn(),
  revokeUserRole: vi.fn(),
  listAuditLogs: vi.fn(),
  createRole: vi.fn(),
  simulate: vi.fn(),
}));
vi.mock("../services/security-service", () => ({
  securityService: {
    configuration: { get: mocks.getConfiguration },
    roles: { list: mocks.listRoles, create: mocks.createRole },
    userRoles: {
      list: mocks.listUserRoles,
      get: mocks.getUserRole,
      create: mocks.createUserRole,
      update: mocks.updateUserRole,
      revoke: mocks.revokeUserRole,
    },
    auditLogs: { list: mocks.listAuditLogs },
    accessDecisions: { simulate: mocks.simulate },
  },
}));

const pagination = {
  count: 0,
  page: 1,
  page_size: 25,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};
const empty = {
  items: [],
  pagination,
  correlationId: "corr-list",
  timestamp: "2026-07-22T00:00:00Z",
};
const assignment = {
  id: "11111111-1111-4111-8111-111111111110",
  tenant_id: "11111111-1111-4111-8111-111111111120",
  user_id: "11111111-1111-4111-8111-111111111121",
  user_display: "Ada Lovelace",
  role_id: "11111111-1111-4111-8111-111111111122",
  role_name: "Security reviewer",
  valid_from: "2026-07-22T00:00:00Z",
  valid_until: null,
  assigned_by: "11111111-1111-4111-8111-111111111123",
  reason: "Quarterly access review",
  revoked_at: null,
  revoked_by: null,
  revocation_reason: "",
  is_active: true,
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
};
const configuration = {
  data: {
    id: "security-config-1",
    environment: "development",
    version: 1,
    document: {
      limits: {
        list_page_size: 25,
        lookup_page_size: 10,
        required_text_max_length: 120,
      },
      ordering: { audit_logs: ["-timestamp"], roles: ["name"] },
      ui: { loading_skeleton_rows: 3, audit_timeline_page_size: 25 },
      semantic_tokens: {
        success: "status-success",
        danger: "status-danger",
        warning: "status-warning",
        neutral: "status-neutral",
      },
    },
    rollout: { enabled: true, percentage: 100, role_ids: [], cohorts: [] },
    updated_by: "00000000-0000-0000-0000-000000000000",
    correlation_id: "corr-config",
    created_at: "2026-07-22T00:00:00Z",
    updated_at: "2026-07-22T00:00:00Z",
  },
  correlationId: "corr-config",
  timestamp: "2026-07-22T00:00:00Z",
};
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>;
}

function renderPage(page: React.ReactNode, initial = "/security-access-control/roles") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <LocationProbe />
        {page}
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
          <Route path="/security-access-control/assignments/:id" element={<span />} />
          <Route path="/security-access-control/assignments/:id/edit" element={<span />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("security administration page states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getConfiguration.mockResolvedValue(configuration);
    mocks.listRoles.mockResolvedValue({
      items: [
        {
          id: "11111111-1111-4111-8111-111111111122",
          name: "Security reviewer",
          code: "security_reviewer",
          description: "Reviews access evidence",
          role_type: "functional",
          hierarchy_level: 0,
          is_active: true,
        },
      ],
      pagination,
      correlationId: "corr-roles",
      timestamp: "2026-07-22T00:00:00Z",
    });
    mocks.listAuditLogs.mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-audit",
      timestamp: "2026-07-22T00:00:00Z",
    });
  });
  it("renders an initial list skeleton", () => {
    mocks.listRoles.mockReturnValue(new Promise(() => undefined));
    renderPage(<RolesPage />);
    expect(screen.getByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
  });
  it("distinguishes unfiltered and filtered empty states", async () => {
    mocks.listRoles.mockResolvedValue(empty);
    const first = renderPage(<RolesPage />);
    expect(await screen.findByText("No roles yet")).toBeInTheDocument();
    first.unmount();
    renderPage(<RolesPage />, "/security-access-control/roles?search=missing");
    expect(await screen.findByText("No roles match these filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset filters" })).toBeInTheDocument();
  });
  it("surfaces governed correlation IDs and retry", async () => {
    mocks.listRoles.mockRejectedValue(
      new ApiError("Denied", 403, undefined, "POLICY_DENIED", "corr-denied")
    );
    renderPage(<RolesPage />);
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText(/corr-denied/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(mocks.listRoles).toHaveBeenCalledTimes(2);
  });
  it("renders successful role data and loads the next bounded page", async () => {
    mocks.listRoles.mockResolvedValue({
      items: [
        {
          id: "role-1",
          name: "Support",
          code: "support",
          description: "Support access",
          role_type: "functional",
          hierarchy_level: 0,
          is_active: true,
        },
      ],
      pagination: { ...pagination, count: 26, total_pages: 2, has_next: true },
      correlationId: "corr-list",
      timestamp: "2026-07-22T00:00:00Z",
    });
    renderPage(<RolesPage />);
    expect(await screen.findByText("Support")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Next/u }));
    await waitFor(() =>
      expect(mocks.listRoles).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2, page_size: 25 })
      )
    );
  });
  it("waits for security configuration before loading governed assignments", () => {
    mocks.getConfiguration.mockReturnValue(new Promise(() => undefined));
    mocks.listUserRoles.mockResolvedValue(empty);
    renderPage(<AssignmentsPage />, "/security-access-control/assignments");
    expect(screen.getByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    expect(screen.queryByText("Security request failed")).not.toBeInTheDocument();
    expect(mocks.listUserRoles).not.toHaveBeenCalled();
  });
  it("uses configured page limits for governed assignments", async () => {
    mocks.listUserRoles.mockResolvedValue(empty);
    renderPage(<AssignmentsPage />, "/security-access-control/assignments");
    expect(await screen.findByText("No role assignments yet")).toBeInTheDocument();
    expect(mocks.listUserRoles).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 25 })
    );
  });
  it("surfaces assignment loading, empty response, query errors, retry, and pagination state", async () => {
    mocks.listUserRoles.mockReturnValueOnce(new Promise(() => undefined));
    const loading = renderPage(<AssignmentsPage />, "/security-access-control/assignments");
    expect(await screen.findByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    loading.unmount();

    mocks.listUserRoles.mockRejectedValueOnce(
      new ApiError("Assignments unavailable", 503, undefined, "DOWN", "corr-assignments")
    );
    mocks.listUserRoles.mockImplementation(({ page = 1 }: AssignmentFilters) =>
      Promise.resolve({
        items: [assignment],
        pagination: {
          ...pagination,
          count: 51,
          page,
          total_pages: 3,
          has_next: page < 3,
          has_previous: page > 1,
        },
        correlationId: "corr-list",
        timestamp: "2026-07-22T00:00:00Z",
      })
    );
    renderPage(<AssignmentsPage />, "/security-access-control/assignments?page=2");
    expect(await screen.findByText("Security capability unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-assignments/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 3 · 51 records")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Previous/u }));
    await waitFor(() =>
      expect(mocks.listUserRoles).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, page_size: 25 })
      )
    );
    await userEvent.click(screen.getByRole("button", { name: /Next/u }));
    await waitFor(() =>
      expect(mocks.listUserRoles).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2, page_size: 25 })
      )
    );
  });
  it("loads governed assignments with URL filters, bounded page, and default ordering", async () => {
    mocks.listUserRoles.mockResolvedValue({
      items: [assignment],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-list",
      timestamp: "2026-07-22T00:00:00Z",
    });
    renderPage(
      <AssignmentsPage />,
      "/security-access-control/assignments?user_id=11111111-1111-4111-8111-111111111121&role_id=11111111-1111-4111-8111-111111111122&revoked=false&active_at=2026-07-22T08:30&page=0"
    );
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Security reviewer")).toBeInTheDocument();
    expect(screen.getByText("Quarterly access review")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(mocks.listUserRoles).toHaveBeenCalledWith(
      expect.objectContaining({
        user_id: "11111111-1111-4111-8111-111111111121",
        role_id: "11111111-1111-4111-8111-111111111122",
        revoked: false,
        active_at: "2026-07-22T08:30",
        ordering: "-valid_from",
        page: 1,
        page_size: 25,
      })
    );
  });
  it("applies assignment filters, resets them, and creates from empty states", async () => {
    mocks.listUserRoles.mockResolvedValue(empty);
    renderPage(<AssignmentsPage />, "/security-access-control/assignments?page=2");
    expect(await screen.findByText("No role assignments yet")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter by user UUID"), {
      target: { value: "11111111-1111-4111-8111-111111111121" },
    });
    expect(await screen.findByText("No role assignments match these filters")).toBeInTheDocument();
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments?user_id=11111111-1111-4111-8111-111111111121"
    );
    fireEvent.change(screen.getByLabelText("Filter by role UUID"), {
      target: { value: "11111111-1111-4111-8111-111111111122" },
    });
    expect(await screen.findByText("No role assignments match these filters")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Revocation state"), {
      target: { value: "true" },
    });
    expect(await screen.findByText("No role assignments match these filters")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Active at"), {
      target: { value: "2026-07-22T08:30" },
    });
    expect(await screen.findByText("No role assignments match these filters")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Sort assignments"), {
      target: { value: "valid_from" },
    });
    await waitFor(() =>
      expect(mocks.listUserRoles).toHaveBeenLastCalledWith(
        expect.objectContaining({
          user_id: "11111111-1111-4111-8111-111111111121",
          role_id: "11111111-1111-4111-8111-111111111122",
          revoked: true,
          active_at: "2026-07-22T08:30",
          ordering: "valid_from",
          page: 1,
          page_size: 25,
        })
      )
    );
    const user = userEvent.setup();
    expect(await screen.findByText("No role assignments match these filters")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await waitFor(() =>
      expect(mocks.listUserRoles).toHaveBeenLastCalledWith(
        expect.objectContaining({
          ordering: "-valid_from",
          page: 1,
          page_size: 25,
        })
      )
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments"
    );
    await user.click(screen.getByRole("button", { name: "Create first record" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments/create"
    );
  });
  it("routes assignment action buttons to governed assignment workspaces", async () => {
    mocks.listUserRoles.mockResolvedValue(empty);
    renderPage(<AssignmentsPage />, "/security-access-control/assignments");
    expect(await screen.findByText("No role assignments yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Permission-set grants" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments/permission-set-grants"
    );
    await userEvent.click(screen.getByRole("button", { name: "Profile assignments" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments/profile-assignments"
    );
    await userEvent.click(screen.getByRole("button", { name: "Assign role" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments/create"
    );
  });
  it("renders assignment detail evidence, navigates to edit, and revokes with an audit reason", async () => {
    mocks.getUserRole.mockResolvedValue({
      data: assignment,
      correlationId: "corr-assignment",
      timestamp: "2026-07-22T00:00:00Z",
    });
    mocks.revokeUserRole.mockResolvedValue(undefined);
    const prompt = vi.spyOn(window, "prompt").mockReturnValue("Emergency access ended");
    renderRoutePage({
      element: <UserRoleDetailPage />,
      initial: "/security-access-control/assignments/11111111-1111-4111-8111-111111111110",
      path: "/security-access-control/assignments/:id",
    });
    expect(await screen.findByRole("heading", { name: "Security reviewer" })).toBeInTheDocument();
    expect(screen.getByText("Assigned to Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Quarterly access review")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("No audit event is linked to this resource.")).toBeInTheDocument();
    expect(mocks.listAuditLogs).toHaveBeenCalledWith({
      ordering: "-timestamp",
      page_size: 25,
      resource_id: "11111111-1111-4111-8111-111111111110",
      resource_type: "user_role",
    });
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() =>
      expect(mocks.revokeUserRole).toHaveBeenCalledWith("11111111-1111-4111-8111-111111111110", {
        reason: "Emergency access ended",
      })
    );
    await waitFor(() => expect(mocks.getUserRole).toHaveBeenCalledTimes(2));
    await userEvent.click(screen.getByRole("button", { name: "Edit assignment" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments/11111111-1111-4111-8111-111111111110/edit"
    );
    prompt.mockRestore();
  });
  it("renders revoked and scheduled assignment detail states without mutable actions", async () => {
    const revoked = {
      ...assignment,
      id: "11111111-1111-4111-8111-111111111130",
      is_active: false,
      revoked_at: "2026-07-23T00:00:00Z",
      revoked_by: "11111111-1111-4111-8111-111111111124",
      revocation_reason: "Emergency access ended",
    };
    const scheduled = {
      ...assignment,
      id: "11111111-1111-4111-8111-111111111131",
      is_active: false,
      role_name: null,
      user_display: null,
      valid_until: "2026-08-22T00:00:00Z",
    };
    mocks.getUserRole.mockResolvedValueOnce({
      data: revoked,
      correlationId: "corr-revoked",
      timestamp: "2026-07-22T00:00:00Z",
    });
    const revokedView = renderRoutePage({
      element: <UserRoleDetailPage />,
      initial: "/security-access-control/assignments/11111111-1111-4111-8111-111111111130",
      path: "/security-access-control/assignments/:id",
    });
    expect((await screen.findAllByText("Revoked")).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Revocation reason")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit assignment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
    revokedView.unmount();

    mocks.getUserRole.mockResolvedValueOnce({
      data: scheduled,
      correlationId: "corr-scheduled",
      timestamp: "2026-07-22T00:00:00Z",
    });
    renderRoutePage({
      element: <UserRoleDetailPage />,
      initial: "/security-access-control/assignments/11111111-1111-4111-8111-111111111131",
      path: "/security-access-control/assignments/:id",
    });
    expect(await screen.findByRole("heading", { name: "Role assignment" })).toBeInTheDocument();
    expect(
      screen.getByText("Assigned to 11111111-1111-4111-8111-111111111121")
    ).toBeInTheDocument();
    expect(screen.getByText("Scheduled / expired")).toBeInTheDocument();
  });
  it("surfaces assignment detail loading and governed errors", async () => {
    mocks.getUserRole.mockReturnValueOnce(new Promise(() => undefined));
    const loading = renderRoutePage({
      element: <UserRoleDetailPage />,
      initial: "/security-access-control/assignments/11111111-1111-4111-8111-111111111110",
      path: "/security-access-control/assignments/:id",
    });
    expect(await screen.findByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    loading.unmount();

    mocks.getUserRole
      .mockRejectedValueOnce(
        new ApiError("Not found", 404, undefined, "NOT_FOUND", "corr-detail-missing")
      )
      .mockResolvedValueOnce({
        data: assignment,
        correlationId: "corr-assignment",
        timestamp: "2026-07-22T00:00:00Z",
      });
    renderRoutePage({
      element: <UserRoleDetailPage />,
      initial: "/security-access-control/assignments/11111111-1111-4111-8111-111111111110",
      path: "/security-access-control/assignments/:id",
    });
    expect(await screen.findByText("Record not found")).toBeInTheDocument();
    expect(screen.getByText(/corr-detail-missing/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Security reviewer" })).toBeInTheDocument();
  });
  it("validates and submits governed role assignments", async () => {
    mocks.createUserRole.mockResolvedValue({
      data: assignment,
      correlationId: "corr-create-assignment",
      timestamp: "2026-07-22T00:00:00Z",
    });
    renderPage(<UserRoleCreatePage />, "/security-access-control/assignments/create");
    const save = await screen.findByRole("button", { name: "Save assignment" });
    const form = save.closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form!);
    expect(mocks.createUserRole).not.toHaveBeenCalled();
    expect(await screen.findByText("Enter a valid user UUID")).toBeInTheDocument();
    expect(screen.getByText("Select a role")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("User UUID"), {
      target: { value: "11111111-1111-4111-8111-111111111121" },
    });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "11111111-1111-4111-8111-111111111122" },
    });
    fireEvent.change(screen.getByLabelText("Valid from"), {
      target: { value: "2026-07-22T08:30" },
    });
    fireEvent.change(screen.getByLabelText("Valid until (optional)"), {
      target: { value: "2026-07-21T08:30" },
    });
    fireEvent.change(screen.getByLabelText("Assignment reason"), {
      target: { value: "Quarterly review approval" },
    });
    fireEvent.submit(form!);
    expect(await screen.findByText("Expiry must be after the start")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Valid until (optional)"), {
      target: { value: "2026-07-22T08:30" },
    });
    fireEvent.submit(form!);
    expect(await screen.findByText("Expiry must be after the start")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Valid until (optional)"), {
      target: { value: "2026-08-22T08:30" },
    });
    fireEvent.submit(form!);
    await waitFor(() =>
      expect(mocks.createUserRole).toHaveBeenCalledWith({
        user_id: "11111111-1111-4111-8111-111111111121",
        role_id: "11111111-1111-4111-8111-111111111122",
        valid_from: "2026-07-22T03:00:00.000Z",
        valid_until: "2026-08-22T03:00:00.000Z",
        reason: "Quarterly review approval",
      })
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments/11111111-1111-4111-8111-111111111110"
    );
  });
  it("uses governed role lookup configuration and handles clean create cancellation", async () => {
    const confirm = vi.spyOn(window, "confirm");
    renderPage(<UserRoleCreatePage />, "/security-access-control/assignments/create");
    expect(await screen.findByRole("heading", { name: "Assign a role" })).toBeInTheDocument();
    expect(
      await screen.findByRole("option", { name: "Security reviewer · security_reviewer" })
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save assignment" })).toBeEnabled();
    expect(mocks.listRoles).toHaveBeenCalledWith({
      is_active: true,
      ordering: "name",
      page_size: 10,
    });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments"
    );
    confirm.mockRestore();
  });
  it("treats user, role, and reason changes as dirty create-state evidence", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage(<UserRoleCreatePage />, "/security-access-control/assignments/create");
    expect(
      await screen.findByRole("option", { name: "Security reviewer · security_reviewer" })
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeEnabled();
    fireEvent.change(screen.getByLabelText("User UUID"), {
      target: { value: "11111111-1111-4111-8111-111111111121" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalledWith("Discard unsaved assignment changes?");
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments/create"
    );
    fireEvent.change(screen.getByLabelText("User UUID"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "11111111-1111-4111-8111-111111111122" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalledTimes(2);
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("Assignment reason"), {
      target: { value: "Role review" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalledTimes(3);
    confirm.mockRestore();
  });
  it("rejects whitespace-only assignment reasons after trimming", async () => {
    renderPage(<UserRoleCreatePage />, "/security-access-control/assignments/create");
    const save = await screen.findByRole("button", { name: "Save assignment" });
    fireEvent.change(screen.getByLabelText("User UUID"), {
      target: { value: "11111111-1111-4111-8111-111111111121" },
    });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "11111111-1111-4111-8111-111111111122" },
    });
    fireEvent.change(screen.getByLabelText("Valid from"), {
      target: { value: "2026-07-22T08:30" },
    });
    fireEvent.change(screen.getByLabelText("Assignment reason"), {
      target: { value: "        " },
    });
    fireEvent.submit(save.closest("form")!);
    expect(mocks.createUserRole).not.toHaveBeenCalled();
    expect(
      await screen.findByText("Give an auditable reason of at least 8 characters")
    ).toBeInTheDocument();
  });
  it("disables assignment submission while roles load and reports role lookup failures", async () => {
    mocks.listRoles
      .mockReturnValueOnce(new Promise(() => undefined))
      .mockRejectedValueOnce(
        new ApiError("Lookup denied", 403, undefined, "DENIED", "corr-roles-denied")
      )
      .mockResolvedValueOnce({
        items: [
          {
            id: "11111111-1111-4111-8111-111111111122",
            name: "Security reviewer",
            code: "security_reviewer",
            description: "Reviews access evidence",
            role_type: "functional",
            hierarchy_level: 0,
            is_active: true,
          },
        ],
        pagination,
        correlationId: "corr-roles",
        timestamp: "2026-07-22T00:00:00Z",
      });
    const loading = renderPage(
      <UserRoleCreatePage />,
      "/security-access-control/assignments/create"
    );
    expect(await screen.findByRole("combobox")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save assignment" })).toBeDisabled();
    loading.unmount();

    renderPage(<UserRoleCreatePage />, "/security-access-control/assignments/create");
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText(/corr-roles-denied/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(
      await screen.findByRole("option", { name: "Security reviewer · security_reviewer" })
    ).toBeInTheDocument();
  });
  it("reports assignment create mutation failures and disables the pending submit", async () => {
    let rejectCreate: (error: Error) => void = () => undefined;
    mocks.createUserRole.mockReturnValue(
      new Promise((_, reject) => {
        rejectCreate = reject;
      })
    );
    renderPage(<UserRoleCreatePage />, "/security-access-control/assignments/create");
    const save = await screen.findByRole("button", { name: "Save assignment" });
    fireEvent.change(screen.getByLabelText("User UUID"), {
      target: { value: "11111111-1111-4111-8111-111111111121" },
    });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "11111111-1111-4111-8111-111111111122" },
    });
    fireEvent.change(screen.getByLabelText("Valid from"), {
      target: { value: "2026-07-22T08:30" },
    });
    fireEvent.change(screen.getByLabelText("Assignment reason"), {
      target: { value: "Quarterly review approval" },
    });
    fireEvent.submit(save.closest("form")!);
    expect(await screen.findByRole("button", { name: /Saving/u })).toBeDisabled();
    rejectCreate(
      new ApiError("Create conflict", 409, undefined, "CONFLICT", "corr-create-conflict")
    );
    expect(await screen.findByText("Change conflict")).toBeInTheDocument();
    expect(screen.getByText(/corr-create-conflict/u)).toBeInTheDocument();
  });
  it("loads, edits, and cancels governed role assignments", async () => {
    const updated = { ...assignment, reason: "Extended emergency cover" };
    mocks.getUserRole.mockResolvedValue({
      data: assignment,
      correlationId: "corr-assignment",
      timestamp: "2026-07-22T00:00:00Z",
    });
    mocks.updateUserRole.mockResolvedValue({
      data: updated,
      correlationId: "corr-update-assignment",
      timestamp: "2026-07-22T00:00:00Z",
    });
    const confirm = vi
      .spyOn(window, "confirm")
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    renderRoutePage({
      element: <UserRoleEditPage />,
      initial: "/security-access-control/assignments/11111111-1111-4111-8111-111111111110/edit",
      path: "/security-access-control/assignments/:id/edit",
    });
    expect(await screen.findByDisplayValue("11111111-1111-4111-8111-111111111121")).toBeDisabled();
    expect(screen.getByRole("heading", { name: "Edit role assignment" })).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeDisabled();
    expect(mocks.getUserRole).toHaveBeenCalledWith("11111111-1111-4111-8111-111111111110");
    fireEvent.change(screen.getByLabelText("Assignment reason"), {
      target: { value: "Extended emergency cover" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalledWith("Discard unsaved assignment changes?");
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments/11111111-1111-4111-8111-111111111110/edit"
    );
    fireEvent.submit(screen.getByRole("button", { name: "Save assignment" }).closest("form")!);
    await waitFor(() =>
      expect(mocks.updateUserRole).toHaveBeenCalledWith("11111111-1111-4111-8111-111111111110", {
        valid_from: "2026-07-21T18:30:00.000Z",
        valid_until: null,
        reason: "Extended emergency cover",
      })
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/security-access-control/assignments/11111111-1111-4111-8111-111111111110"
    );
    confirm.mockRestore();
  });
  it("surfaces edit loading, missing assignment, and governed lookup errors", async () => {
    mocks.getUserRole.mockReturnValueOnce(new Promise(() => undefined));
    const loading = renderRoutePage({
      element: <UserRoleEditPage />,
      initial: "/security-access-control/assignments/11111111-1111-4111-8111-111111111110/edit",
      path: "/security-access-control/assignments/:id/edit",
    });
    expect(await screen.findByLabelText("Loading security administration data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    loading.unmount();

    mocks.getUserRole
      .mockRejectedValueOnce(
        new ApiError("Not found", 404, undefined, "NOT_FOUND", "corr-missing-assignment")
      )
      .mockResolvedValueOnce({
        data: assignment,
        correlationId: "corr-assignment",
        timestamp: "2026-07-22T00:00:00Z",
      });
    renderRoutePage({
      element: <UserRoleEditPage />,
      initial: "/security-access-control/assignments/11111111-1111-4111-8111-111111111110/edit",
      path: "/security-access-control/assignments/:id/edit",
    });
    expect(await screen.findByText("Record not found")).toBeInTheDocument();
    expect(screen.getByText(/corr-missing-assignment/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByDisplayValue("11111111-1111-4111-8111-111111111121")).toBeDisabled();
  });
  it("validates create fields before submitting", async () => {
    mocks.listRoles.mockResolvedValue(empty);
    renderPage(<RoleCreatePage />, "/security-access-control/roles/create");
    await userEvent.type(screen.getByLabelText("Name"), "A");
    await userEvent.type(screen.getByLabelText("Stable code"), "A");
    await userEvent.click(screen.getByRole("button", { name: "Save role" }));
    expect(mocks.createRole).not.toHaveBeenCalled();
    expect(await screen.findByText(/at least 2 character/u)).toBeInTheDocument();
  });
  it("explains an authoritative simulation result", async () => {
    mocks.simulate.mockResolvedValue({
      data: {
        subject_id: "00000000-0000-0000-0000-000000000001",
        permission_code: "security.roles:read",
        decision: "deny",
        reason_codes: ["NO_MATCHING_GRANT"],
        applied_policy_ids: [],
        entitlement: { required: false, allowed: true },
        quota: { required: false, allowed: true },
        field_decisions: [],
        row_explanation: null,
        audit_log_id: null,
        correlation_id: "corr-sim",
        evaluated_at: "2026-07-22T00:00:00Z",
      },
      correlationId: "corr-sim",
      timestamp: "2026-07-22T00:00:00Z",
    });
    renderPage(<AccessSimulatorPage />, "/security-access-control/access-simulator");
    await userEvent.type(
      await screen.findByLabelText("Subject UUID"),
      "00000000-0000-0000-0000-000000000001"
    );
    await userEvent.type(screen.getByLabelText("Permission code"), "security.roles:read");
    await userEvent.click(screen.getByRole("button", { name: "Explain access" }));
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText("NO_MATCHING_GRANT")).toBeInTheDocument();
    expect(screen.getByText(/corr-sim/u)).toBeInTheDocument();
  });

  it("normalizes simulator context values and fails closed on duplicate keys", async () => {
    const user = userEvent.setup();
    let id = 0;
    vi.stubGlobal("crypto", { randomUUID: () => `context-${++id}` });
    mocks.simulate.mockResolvedValue({
      data: {
        subject_id: "00000000-0000-0000-0000-000000000001",
        permission_code: "security.roles:read",
        decision: "allow",
        reason_codes: [],
        applied_policy_ids: ["policy-1"],
        entitlement: { required: true, allowed: true },
        quota: { required: true, allowed: true, remaining: 4 },
        field_decisions: [{ field: "amount", visibility: "masked", edit_control: "read_only" }],
        row_explanation: {
          allowed: true,
          explanation: "owner_id belongs to the authenticated subject",
          reason_codes: ["OWNER_MATCH"],
        },
        audit_log_id: "11111111-1111-4111-8111-111111111101",
        correlation_id: "corr-sim-allow",
        evaluated_at: "2026-07-22T00:00:00Z",
      },
      correlationId: "corr-sim-allow",
      timestamp: "2026-07-22T00:00:00Z",
    });
    renderPage(<AccessSimulatorPage />, "/security-access-control/access-simulator");

    await user.type(
      await screen.findByLabelText("Subject UUID"),
      "00000000-0000-0000-0000-000000000001"
    );
    await user.type(screen.getByLabelText("Permission code"), "SECURITY.ROLES:READ");
    await user.click(screen.getByRole("button", { name: "Add attribute" }));
    await user.click(screen.getByRole("button", { name: "Add attribute" }));
    const keys = screen.getAllByLabelText("Context key");
    await user.type(keys[0]!, "record_count");
    await user.type(keys[1]!, "record_count");
    const values = screen.getAllByPlaceholderText("Value");
    await user.type(values[0]!, "42");
    await user.type(values[1]!, "true");
    await user.click(screen.getByRole("button", { name: "Explain access" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Resource-context keys must be unique."
    );
    expect(mocks.simulate).not.toHaveBeenCalled();

    await user.clear(keys[1]!);
    await user.type(keys[1]!, "approved");
    await user.click(screen.getByRole("button", { name: "Add attribute" }));
    const nextKeys = screen.getAllByLabelText("Context key");
    const nextValues = screen.getAllByPlaceholderText("Value");
    await user.type(nextKeys[2]!, "deleted_at");
    await user.type(nextValues[2]!, "null");
    await user.click(screen.getByRole("button", { name: "Explain access" }));

    await waitFor(() =>
      expect(mocks.simulate).toHaveBeenCalledWith({
        subject_id: "00000000-0000-0000-0000-000000000001",
        permission_code: "security.roles:read",
        resource_context: { approved: true, deleted_at: null, record_count: 42 },
      })
    );
    expect(await screen.findByText("Access allowed")).toBeInTheDocument();
    expect(screen.getByText("Open immutable simulation audit evidence")).toBeInTheDocument();
  });
});
