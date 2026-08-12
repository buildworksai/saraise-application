/* eslint-disable max-lines-per-function -- focused page workflows assert capability gates, filters, and lifecycle payloads. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Attendance,
  Department,
  DepartmentHierarchyNode,
  Employee,
  EmployeeReportingTreeNode,
  HumanResourcesConfiguration,
  LeaveBalance,
  LeaveRequest,
  PageResult,
} from "../contracts";
import { ROUTES } from "../contracts";
import { AttendanceListPage } from "../pages/AttendanceListPage";
import { AttendanceDetailPage } from "../pages/AttendanceDetailPage";
import { DepartmentDetailPage } from "../pages/DepartmentDetailPage";
import { DepartmentListPage } from "../pages/DepartmentListPage";
import { EmployeeDetailPage } from "../pages/EmployeeDetailPage";
import { HumanResourcesOverviewPage } from "../pages/HumanResourcesOverviewPage";
import { LeaveBalanceDetailPage } from "../pages/LeaveBalanceDetailPage";
import { LeaveRequestDetailPage } from "../pages/LeaveRequestDetailPage";
import { LeaveWorkspacePage } from "../pages/LeaveWorkspacePage";
import { HrApiError, hrService } from "../services/hr-service";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const pagination = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 2,
  has_next: true,
  has_previous: false,
};

const configuration: HumanResourcesConfiguration = {
  id: "config-1",
  environment: "default",
  version: 1,
  updated_at: "2026-01-01T00:00:00Z",
  document: {
    schema_version: 1,
    allowed_values: {
      employment_types: ["full_time", "part_time", "contractor", "temporary"],
      employment_statuses: ["active", "on_leave", "inactive", "terminated"],
      attendance_statuses: ["present", "absent", "late", "half_day", "on_leave"],
      attendance_sources: ["manual", "clock", "import"],
      leave_types: ["annual", "sick", "personal", "maternity", "paternity", "unpaid"],
      leave_states: ["pending", "approved", "rejected", "cancelled"],
      leave_scopes: ["all", "self", "team", "approval_queue"],
    },
    limits: {
      actor_identifier_max_length: 255,
      idempotency_key_max_length: 255,
      department_code_max_length: 50,
      department_name_max_length: 255,
      employee_number_max_length: 50,
      employee_name_max_length: 100,
      employee_email_max_length: 255,
      employee_phone_max_length: 50,
      employee_position_max_length: 100,
      hierarchy_max_depth: 100,
      reporting_tree_default_depth: 5,
      reporting_tree_max_depth: 20,
      department_tree_max_nodes: 500,
      max_hours_per_day: "24.00",
      leave_amount_minimum: "0.01",
      list_page_size: 25,
      lookup_page_size: 100,
      leave_input_minimum: "0.00",
      leave_input_step: "0.25",
      decimal_quantum: "0.01",
    },
    defaults: {
      department_active: true,
      employment_type: "full_time",
      employment_status: "active",
      attendance_hours: "0.00",
      attendance_status: "present",
      attendance_source: "manual",
      leave_type: "annual",
      leave_request_status: "pending",
      leave_entitled_days: "0.00",
      leave_carried_days: "0.00",
      leave_adjustment_version: 1,
      leave_adjustment_note: "Initial allocation",
      leave_scope: "all",
      department_ordering: "department_code",
      event_schema_version: 1,
    },
    policies: {
      manager_eligible_statuses: ["active", "on_leave"],
      employee_active_statuses: ["active", "on_leave"],
      attendance_eligible_statuses: ["active", "on_leave"],
      clock_in_eligible_statuses: ["active"],
      leave_eligible_statuses: ["active", "on_leave"],
      attendance_zero_work_statuses: ["absent", "on_leave"],
      leave_overlap_blocking_statuses: ["pending", "approved"],
      department_deactivation_blocks_active_children: true,
      department_deactivation_blocks_active_employees: true,
      employee_inactivation_requires_no_managed_departments: true,
      employee_archive_statuses: ["terminated"],
      employee_archive_blocks_pending_leave: true,
      leave_balance_enforce_capacity: true,
      leave_submission_blocks_insufficient_balance: true,
      allow_future_employee_transitions: false,
      approved_leave_cancel_before_start_only: true,
      leave_duration_calendar: "inclusive",
      one_attendance_per_employee_date: true,
    },
    workflows: {
      employee_terminal_states: ["terminated"],
      employee_transitions: [],
      leave_terminal_states: ["rejected", "cancelled"],
      leave_transitions: [
        ["approve", "pending", "approved"],
        ["reject", "pending", "rejected"],
        ["cancel", "approved", "cancelled"],
      ],
    },
    feature_rollout: { enabled: true, percentage: 100, roles: [], cohorts: [] },
    visual: { positive_status_token: "status-positive", warning_status_token: "status-warning" },
    operations: { health_staleness_seconds: 30 },
  },
};

const department: Department = {
  id: "dept-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  department_code: "ENG",
  department_name: "Engineering",
  parent_department: null,
  parent_department_name: null,
  manager: "employee-1",
  manager_name: "Ada Lovelace",
  is_active: true,
  description: "Builds governed systems.",
};

const hierarchy: DepartmentHierarchyNode = {
  id: "dept-1",
  department_code: "ENG",
  department_name: "Engineering",
  manager: "employee-1",
  manager_name: "Ada Lovelace",
  is_active: true,
  children: [
    {
      id: "dept-2",
      department_code: "PLAT",
      department_name: "Platform",
      manager: null,
      manager_name: null,
      is_active: true,
      children: [],
    },
  ],
};

const leaveRequest: LeaveRequest = {
  id: "leave-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  employee: "employee-1",
  employee_number: "EMP-1",
  employee_name: "Ada Lovelace",
  leave_balance: "balance-1",
  leave_type: "annual",
  start_date: "2027-01-10",
  end_date: "2027-01-12",
  days_requested: "3.00",
  reason: "Planned leave",
  status: "pending",
  approved_by: "",
  approved_at: null,
  rejection_reason: "",
  cancelled_by: "",
  cancelled_at: null,
  transition_history: [
    {
      transition_key: "leave-create-1",
      command: "create",
      from_state: "none",
      to_state: "pending",
      occurred_at: "2026-01-01T00:00:00Z",
      metadata: { source: "ui" },
    },
  ],
};

const balance: LeaveBalance = {
  id: "balance-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  employee: "employee-1",
  employee_number: "EMP-1",
  employee_name: "Ada Lovelace",
  leave_type: "annual",
  period_start: "2027-01-01",
  period_end: "2027-12-31",
  entitled_days: "20.00",
  carried_days: "0.00",
  used_days: "2.00",
  pending_days: "3.00",
  remaining_days: "15.00",
  adjustment_version: 2,
  last_adjusted_by: "hr-1",
  adjustment_note: "Annual grant",
};

const attendance: Attendance = {
  id: "attendance-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  employee: "employee-1",
  employee_number: "EMP-1",
  employee_name: "Ada Lovelace",
  attendance_date: "2027-01-10",
  check_in_time: "2027-01-10T09:00:00Z",
  check_out_time: null,
  hours_worked: "4.00",
  status: "present",
  source: "clock",
  notes: "Morning clock-in",
};

const employee: Employee = {
  id: "employee-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  employee_number: "EMP-1",
  first_name: "Ada",
  last_name: "Lovelace",
  full_name: "Ada Lovelace",
  email: "ada@example.test",
  phone: "",
  department: "dept-1",
  department_name: "Engineering",
  manager: "manager-1",
  manager_name: "Grace Hopper",
  position: "Engineer",
  hire_date: "2026-01-01",
  employment_type: "full_time",
  employment_status: "active",
  is_active: true,
  termination_date: null,
  termination_reason: "",
  transition_history: [
    {
      transition_key: "employee-create-1",
      command: "create",
      from_state: "none",
      to_state: "active",
      occurred_at: "2026-01-01T00:00:00Z",
      metadata: { source: "ui" },
    },
  ],
};

const reportingTree: EmployeeReportingTreeNode = {
  id: "employee-1",
  employee_number: "EMP-1",
  full_name: "Ada Lovelace",
  position: "Engineer",
  employment_status: "active",
  direct_reports: [
    {
      id: "employee-2",
      employee_number: "EMP-2",
      full_name: "Katherine Johnson",
      position: "",
      employment_status: "active",
      direct_reports: [],
    },
  ],
};

function page<T>(items: readonly T[], capabilities: readonly string[] = []): PageResult<T> {
  return {
    items,
    pagination: { ...pagination, count: items.length },
    correlationId: "corr-hr-page",
    capabilities,
  };
}

function detail<T>(data: T, capabilities: readonly string[] = []) {
  return { data, correlationId: "corr-hr-detail", capabilities };
}

function renderRoute(ui: React.ReactElement, path: string, entry = path) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path={path} element={ui} />
          <Route path={`${ROUTES.LEAVE}/requests/new`} element={<LocationProbe />} />
          <Route path={`${ROUTES.LEAVE}/balances/new`} element={<LocationProbe />} />
          <Route path={`${ROUTES.LEAVE}/balances/:id/edit`} element={<LocationProbe />} />
          <Route path={`${ROUTES.ATTENDANCE}/new`} element={<LocationProbe />} />
          <Route path={`${ROUTES.ATTENDANCE}/:id/edit`} element={<LocationProbe />} />
          <Route path={`${ROUTES.ATTENDANCE}/:id`} element={<LocationProbe />} />
          <Route path={`${ROUTES.EMPLOYEES}`} element={<LocationProbe />} />
          <Route path={`${ROUTES.EMPLOYEES}/:id/edit`} element={<LocationProbe />} />
          <Route path={`${ROUTES.EMPLOYEES}/:id`} element={ui} />
          <Route path={`${ROUTES.DEPARTMENTS}`} element={<LocationProbe />} />
          <Route path={`${ROUTES.DEPARTMENTS}/new`} element={<LocationProbe />} />
          <Route path={`${ROUTES.DEPARTMENTS}/:id`} element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

describe("Human Resources leave, department, and attendance pages", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    let key = 0;
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => `hr-key-${(key += 1)}`) });
    vi.spyOn(hrService, "getConfiguration").mockResolvedValue(detail(configuration));
    vi.spyOn(hrService, "listLeaveRequests").mockResolvedValue(
      page([leaveRequest], ["hr.leave_request:create", "hr.leave_balance:create"])
    );
    vi.spyOn(hrService, "listLeaveBalances").mockResolvedValue(page([balance]));
    vi.spyOn(hrService, "getLeaveRequest").mockResolvedValue(
      detail(leaveRequest, [
        "hr.leave_request:update",
        "hr.leave_request:approve",
        "hr.leave_request:reject",
        "hr.leave_request:cancel",
      ])
    );
    vi.spyOn(hrService, "approveLeaveRequest").mockResolvedValue(
      detail({ ...leaveRequest, status: "approved", approved_at: "2026-01-02T00:00:00Z" })
    );
    vi.spyOn(hrService, "rejectLeaveRequest").mockResolvedValue(
      detail({ ...leaveRequest, status: "rejected", rejection_reason: "Insufficient coverage" })
    );
    vi.spyOn(hrService, "getDepartment").mockResolvedValue(
      detail(department, ["hr.department:update", "hr.department:delete"])
    );
    vi.spyOn(hrService, "getDepartmentHierarchy").mockResolvedValue(detail([hierarchy]));
    vi.spyOn(hrService, "deactivateDepartment").mockResolvedValue(
      detail({ ...department, is_active: false })
    );
    vi.spyOn(hrService, "deleteDepartment").mockResolvedValue(undefined);
    vi.spyOn(hrService, "getLeaveBalance").mockResolvedValue(
      detail({ ...balance, used_days: "0.00", pending_days: "0.00" }, [
        "hr.leave_balance:adjust",
        "hr.leave_balance:delete",
      ])
    );
    vi.spyOn(hrService, "deleteLeaveBalance").mockResolvedValue(undefined);
    vi.spyOn(hrService, "listDepartments").mockResolvedValue(
      page([department], ["hr.department:create"])
    );
    vi.spyOn(hrService, "listAttendances").mockResolvedValue(
      page([attendance], ["hr.attendance:create", "hr.attendance:clock"])
    );
    vi.spyOn(hrService, "listEmployees").mockResolvedValue(page([employee]));
    vi.spyOn(hrService, "getEmployee").mockResolvedValue(
      detail(employee, ["hr.employee:update", "hr.employee:transition"])
    );
    vi.spyOn(hrService, "getReportingTree").mockResolvedValue(detail(reportingTree));
    vi.spyOn(hrService, "transitionEmployee").mockResolvedValue(
      detail({ ...employee, employment_status: "on_leave" })
    );
    vi.spyOn(hrService, "deleteEmployee").mockResolvedValue(undefined);
    vi.spyOn(hrService, "clockIn").mockResolvedValue(detail(attendance));
    vi.spyOn(hrService, "getAttendance").mockResolvedValue(
      detail(attendance, ["hr.attendance:clock", "hr.attendance:update", "hr.attendance:delete"])
    );
    vi.spyOn(hrService, "clockOut").mockResolvedValue(
      detail({ ...attendance, check_out_time: "2027-01-10T17:00:00Z", hours_worked: "8.00" })
    );
    vi.spyOn(hrService, "deleteAttendance").mockResolvedValue(undefined);
    vi.spyOn(hrService, "getHealth").mockResolvedValue({
      data: {
        module: "human_resources",
        status: "healthy",
        live: true,
        ready: true,
        checked_at: "2026-01-01T00:00:00Z",
        checks: {
          database: {
            name: "Database",
            status: "healthy",
            code: "database_ready",
            latency_ms: 2,
            critical: true,
          },
        },
      },
      correlationId: "corr-health",
      capabilities: [],
    });
  });

  it("filters leave scopes, shows balance evidence, and navigates create actions by capability", async () => {
    const user = userEvent.setup();
    renderRoute(<LeaveWorkspacePage />, ROUTES.LEAVE);

    expect(await screen.findByRole("heading", { name: "Leave" })).toBeInTheDocument();
    expect(screen.getByText("15.00 days")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Leave scope"), "approval_queue");
    await user.selectOptions(screen.getByLabelText("Leave status"), "pending");

    await waitFor(() =>
      expect(hrService.listLeaveRequests).toHaveBeenLastCalledWith(
        expect.objectContaining({
          scope: "approval_queue",
          status: "pending",
          page: 1,
          page_size: 25,
        })
      )
    );
    await user.click(screen.getByRole("button", { name: "Request leave" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/human-resources/leave/requests/new");
  });

  it("fails closed for protected leave views and withholds privileged empty-state actions", async () => {
    vi.spyOn(hrService, "listLeaveRequests").mockRejectedValueOnce(
      new HrApiError("Leave queue denied", "permission", 403, "permission", "corr-leave-403")
    );
    vi.spyOn(hrService, "listLeaveBalances").mockResolvedValueOnce(page([]));
    renderRoute(<LeaveWorkspacePage />, ROUTES.LEAVE, `${ROUTES.LEAVE}?scope=self`);

    expect(await screen.findByRole("alert")).toHaveTextContent("Access denied");
    expect(screen.getByText(/corr-leave-403/u)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request leave" })).not.toBeInTheDocument();
  });

  it("requires rejection reason and sends leave transition keys for approval and rejection", async () => {
    const user = userEvent.setup();
    renderRoute(
      <LeaveRequestDetailPage />,
      `${ROUTES.LEAVE}/requests/:id`,
      ROUTES.LEAVE_REQUEST_DETAIL("leave-1")
    );

    expect(await screen.findByRole("heading", { name: /Ada Lovelace/u })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Approve request" }));
    await waitFor(() =>
      expect(hrService.approveLeaveRequest).toHaveBeenCalledWith("leave-1", {
        transition_key: "hr-key-1",
      })
    );

    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByRole("button", { name: "Reject request" })).toBeDisabled();
    await user.type(screen.getByLabelText("Rejection reason"), "Insufficient coverage");
    await user.click(screen.getByRole("button", { name: "Reject request" }));
    await waitFor(() =>
      expect(hrService.rejectLeaveRequest).toHaveBeenCalledWith("leave-1", {
        transition_key: "hr-key-2",
        rejection_reason: "Insufficient coverage",
      })
    );
  });

  it("executes department lifecycle/archive commands with explicit reason and hierarchy evidence", async () => {
    const user = userEvent.setup();
    renderRoute(
      <DepartmentDetailPage />,
      `${ROUTES.DEPARTMENTS}/:id`,
      ROUTES.DEPARTMENT_DETAIL("dept-1")
    );

    expect(await screen.findByRole("heading", { name: "Engineering" })).toBeInTheDocument();
    expect(screen.getByText("Platform")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(screen.getByRole("button", { name: "Confirm lifecycle change" })).toBeDisabled();
    await user.type(screen.getByLabelText("Lifecycle reason"), "Org restructure");
    await user.click(screen.getByRole("button", { name: "Confirm lifecycle change" }));
    await waitFor(() =>
      expect(hrService.deactivateDepartment).toHaveBeenCalledWith("dept-1", {
        idempotency_key: "hr-key-1",
        reason: "Org restructure",
      })
    );

    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(screen.getByRole("button", { name: "Archive department" }));
    await waitFor(() => expect(hrService.deleteDepartment).toHaveBeenCalledWith("dept-1"));
  });

  it("filters department lists through configured defaults and exposes create/detail navigation", async () => {
    const user = userEvent.setup();
    renderRoute(<DepartmentListPage />, ROUTES.DEPARTMENTS, `${ROUTES.DEPARTMENTS}?search=eng`);

    expect(await screen.findByRole("heading", { name: "Departments" })).toBeInTheDocument();
    await waitFor(() =>
      expect(hrService.listDepartments).toHaveBeenLastCalledWith(
        expect.objectContaining({
          search: "eng",
          ordering: "department_code",
          page: 1,
          page_size: 25,
        })
      )
    );
    await user.selectOptions(screen.getByLabelText("Department state"), "false");
    await waitFor(() =>
      expect(hrService.listDepartments).toHaveBeenLastCalledWith(
        expect.objectContaining({ is_active: false, page: 1 })
      )
    );
    await user.click(screen.getByRole("button", { name: "New department" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/human-resources/departments/new");
  });

  it("renders overview totals, health evidence, and retryable fail-closed state", async () => {
    const user = userEvent.setup();
    const employees = vi
      .spyOn(hrService, "listEmployees")
      .mockRejectedValueOnce(
        new HrApiError("Employee service down", "unavailable", 503, "unavailable", "corr-hr-down")
      )
      .mockResolvedValueOnce(page([], []));

    renderRoute(<HumanResourcesOverviewPage />, ROUTES.OVERVIEW);

    expect(await screen.findByRole("alert")).toHaveTextContent("Employee service down");
    await user.click(screen.getByRole("button", { name: /try again/iu }));
    await waitFor(() => expect(employees).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "Human Resources" })).toBeInTheDocument();
    expect(screen.getByText("Departments")).toBeInTheDocument();
    expect(screen.getByText("healthy")).toBeInTheDocument();
  });

  it("renders employee detail evidence, navigates edit/back, and sends lifecycle payloads", async () => {
    const user = userEvent.setup();
    renderRoute(
      <EmployeeDetailPage />,
      `${ROUTES.EMPLOYEES}/:id`,
      ROUTES.EMPLOYEE_DETAIL("employee-1")
    );

    expect(await screen.findByRole("heading", { name: "Ada Lovelace" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Engineering" })).toHaveAttribute(
      "href",
      ROUTES.DEPARTMENT_DETAIL("dept-1")
    );
    expect(screen.getByRole("link", { name: "Grace Hopper" })).toHaveAttribute(
      "href",
      ROUTES.EMPLOYEE_DETAIL("manager-1")
    );
    expect(screen.getByRole("link", { name: "Katherine Johnson" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "annual" })).toHaveAttribute(
      "href",
      ROUTES.LEAVE_BALANCE_DETAIL("balance-1")
    );
    expect(screen.getByText(/create · none/u)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "terminate" }));
    expect(screen.getByRole("button", { name: "Confirm transition" })).toBeDisabled();
    await user.clear(screen.getByLabelText("Effective date"));
    await user.type(screen.getByLabelText("Effective date"), "2027-02-01");
    await user.type(screen.getByLabelText(/Reason/u), "Role ended");
    await user.click(screen.getByRole("button", { name: "Confirm transition" }));
    await waitFor(() =>
      expect(hrService.transitionEmployee).toHaveBeenCalledWith("employee-1", "terminate", {
        transition_key: "hr-key-1",
        effective_date: "2027-02-01",
        reason: "Role ended",
      })
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByTestId("location")).toHaveTextContent(ROUTES.EMPLOYEE_EDIT("employee-1"));
  });

  it("renders employee empty states, inactive actions, and archives terminated profiles", async () => {
    const user = userEvent.setup();
    vi.spyOn(hrService, "getConfiguration").mockResolvedValueOnce(
      detail({
        ...configuration,
        document: {
          ...configuration.document,
          limits: { ...configuration.document.limits, reporting_tree_default_depth: 0 },
        },
      })
    );
    vi.spyOn(hrService, "getEmployee").mockResolvedValueOnce(
      detail(
        {
          ...employee,
          full_name: "",
          phone: "",
          department: null,
          department_name: null,
          manager: null,
          manager_name: null,
          position: "",
          employment_status: "inactive",
          transition_history: [],
        },
        ["hr.employee:transition"]
      )
    );
    vi.spyOn(hrService, "listAttendances").mockResolvedValueOnce(page([]));
    vi.spyOn(hrService, "listLeaveBalances").mockResolvedValueOnce(page([]));
    vi.spyOn(hrService, "listLeaveRequests").mockResolvedValueOnce(page([]));

    const firstRender = renderRoute(
      <EmployeeDetailPage />,
      `${ROUTES.EMPLOYEES}/:id`,
      ROUTES.EMPLOYEE_DETAIL("employee-1")
    );

    expect(await screen.findByRole("heading", { name: "Ada Lovelace" })).toBeInTheDocument();
    expect(screen.getByText(/Position not assigned/u)).toBeInTheDocument();
    expect(screen.getByText("Not recorded")).toBeInTheDocument();
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
    expect(screen.getByText("No manager")).toBeInTheDocument();
    expect(screen.getByText("No reporting relationships.")).toBeInTheDocument();
    expect(screen.getByText("No attendance evidence recorded.")).toBeInTheDocument();
    expect(screen.getByText("No current leave allocation.")).toBeInTheDocument();
    expect(screen.getByText("No leave requests.")).toBeInTheDocument();
    expect(screen.getByText("No lifecycle transitions recorded.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "activate" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    firstRender.unmount();

    vi.spyOn(hrService, "getEmployee").mockResolvedValueOnce(
      detail(
        {
          ...employee,
          employment_status: "terminated",
          termination_date: "2026-12-31",
          termination_reason: "Contract completed",
        },
        ["hr.employee:delete", "hr.employee:transition"]
      )
    );
    renderRoute(
      <EmployeeDetailPage />,
      `${ROUTES.EMPLOYEES}/:id`,
      ROUTES.EMPLOYEE_DETAIL("employee-1")
    );

    expect(
      await screen.findByText("Terminated employees have no further lifecycle actions.")
    ).toBeInTheDocument();
    expect(screen.getByText("Dec 31, 2026")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(screen.getByRole("button", { name: "Archive employee" }));
    await waitFor(() => expect(hrService.deleteEmployee).toHaveBeenCalledWith("employee-1"));
    expect(screen.getByTestId("location")).toHaveTextContent(ROUTES.EMPLOYEES);
  });

  it("fails closed and exposes retry plus mutation errors on employee detail", async () => {
    const user = userEvent.setup();
    const getEmployee = vi
      .spyOn(hrService, "getEmployee")
      .mockRejectedValueOnce(
        new HrApiError("Employee service down", "unavailable", 503, "unavailable", "corr-emp-down")
      )
      .mockResolvedValueOnce(
        detail({ ...employee, employment_status: "on_leave" }, ["hr.employee:transition"])
      );

    renderRoute(
      <EmployeeDetailPage />,
      `${ROUTES.EMPLOYEES}/:id`,
      ROUTES.EMPLOYEE_DETAIL("employee-1")
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Employee service down");
    expect(screen.getByText(/corr-emp-down/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /try again/iu }));
    await waitFor(() => expect(getEmployee).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("button", { name: "return from leave" })).toBeInTheDocument();

    vi.spyOn(hrService, "transitionEmployee").mockRejectedValueOnce(
      new HrApiError("Transition denied", "permission", 403, "permission", "corr-transition")
    );
    await user.click(screen.getByRole("button", { name: "return from leave" }));
    await user.click(screen.getByRole("button", { name: "Confirm transition" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Access denied");
    expect(screen.getByText(/corr-transition/u)).toBeInTheDocument();
  });

  it("filters attendance, clocks in with idempotency evidence, and navigates rows", async () => {
    const user = userEvent.setup();
    renderRoute(
      <AttendanceListPage />,
      ROUTES.ATTENDANCE,
      `${ROUTES.ATTENDANCE}?search=Ada&status=present`
    );

    expect(await screen.findByRole("heading", { name: "Attendance" })).toBeInTheDocument();
    await waitFor(() =>
      expect(hrService.listAttendances).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "Ada", status: "present", page: 1, page_size: 25 })
      )
    );

    await user.selectOptions(screen.getByLabelText("Employee to clock in"), "employee-1");
    await user.click(screen.getByRole("button", { name: "Clock in" }));
    await waitFor(() =>
      expect(hrService.clockIn).toHaveBeenCalledWith({
        employee_id: "employee-1",
        idempotency_key: "hr-key-1",
      })
    );
    await user.click(screen.getByRole("link", { name: "Ada Lovelace" }));
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/human-resources/attendance/attendance-1"
    );
  });

  it("archives unused leave balances only behind capability and confirmation", async () => {
    const user = userEvent.setup();
    const firstRender = renderRoute(
      <LeaveBalanceDetailPage />,
      `${ROUTES.LEAVE}/balances/:id`,
      ROUTES.LEAVE_BALANCE_DETAIL("balance-1")
    );

    expect(
      await screen.findByRole("heading", { name: /Ada Lovelace · annual leave/u })
    ).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "15");
    await user.click(screen.getByRole("button", { name: "Adjust allocation" }));
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/human-resources/leave/balances/balance-1/edit"
    );
    firstRender.unmount();

    renderRoute(
      <LeaveBalanceDetailPage />,
      `${ROUTES.LEAVE}/balances/:id`,
      ROUTES.LEAVE_BALANCE_DETAIL("balance-1")
    );
    await screen.findByRole("heading", { name: /Ada Lovelace · annual leave/u });
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(screen.getByRole("button", { name: "Archive allocation" }));
    await waitFor(() => expect(hrService.deleteLeaveBalance).toHaveBeenCalledWith("balance-1"));
  });

  it("clocks out, corrects, and archives attendance detail with guarded payloads", async () => {
    const user = userEvent.setup();
    const firstRender = renderRoute(
      <AttendanceDetailPage />,
      `${ROUTES.ATTENDANCE}/:id`,
      ROUTES.ATTENDANCE_DETAIL("attendance-1")
    );

    expect(
      await screen.findByRole("heading", { name: /Ada Lovelace · 2027-01-10/u })
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clock out" }));
    await waitFor(() =>
      expect(hrService.clockOut).toHaveBeenCalledWith("attendance-1", {
        idempotency_key: "hr-key-1",
      })
    );
    await user.click(screen.getByRole("button", { name: "Correct" }));
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/human-resources/attendance/attendance-1/edit"
    );
    firstRender.unmount();

    renderRoute(
      <AttendanceDetailPage />,
      `${ROUTES.ATTENDANCE}/:id`,
      ROUTES.ATTENDANCE_DETAIL("attendance-1")
    );
    await screen.findByRole("heading", { name: /Ada Lovelace · 2027-01-10/u });
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(screen.getByRole("button", { name: "Archive record" }));
    await waitFor(() => expect(hrService.deleteAttendance).toHaveBeenCalledWith("attendance-1"));
  });
});
