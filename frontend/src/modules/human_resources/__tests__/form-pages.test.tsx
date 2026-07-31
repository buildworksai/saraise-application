/* eslint-disable max-lines-per-function -- focused form-page regression suite intentionally keeps shared fixtures local. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Attendance,
  Department,
  Employee,
  HumanResourcesConfiguration,
  LeaveBalance,
  LeaveRequest,
  PageResult,
} from "../contracts";
import { ROUTES } from "../contracts";
import {
  CreateAttendancePage,
  CreateDepartmentPage,
  CreateEmployeePage,
  CreateLeaveBalancePage,
  CreateLeaveRequestPage,
  EditAttendancePage,
  EditEmployeePage,
  EditLeaveBalancePage,
  EditLeaveRequestPage,
} from "../pages/form-pages";
import { HrApiError, hrService } from "../services/hr-service";

const pagination = {
  count: 1,
  page: 1,
  page_size: 100,
  total_pages: 1,
  has_next: false,
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
      employee_transitions: [
        ["place_on_leave", "active", "on_leave"],
        ["return_from_leave", "on_leave", "active"],
        ["deactivate", "active", "inactive"],
        ["deactivate", "on_leave", "inactive"],
        ["activate", "inactive", "active"],
        ["terminate", "active", "terminated"],
      ],
      leave_terminal_states: ["rejected", "cancelled"],
      leave_transitions: [
        ["approve", "pending", "approved"],
        ["reject", "pending", "rejected"],
        ["cancel", "pending", "cancelled"],
        ["cancel", "approved", "cancelled"],
      ],
    },
    feature_rollout: { enabled: true, percentage: 100, roles: [], cohorts: [] },
    visual: { positive_status_token: "status-positive", warning_status_token: "status-warning" },
    operations: { health_staleness_seconds: 30 },
  },
};

const employee: Employee = {
  id: "employee-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  employee_number: "EMP-001",
  first_name: "Ada",
  last_name: "Lovelace",
  full_name: "Ada Lovelace",
  email: "ada@example.test",
  phone: "",
  department: "department-1",
  department_name: "Engineering",
  manager: null,
  manager_name: null,
  position: "Engineer",
  hire_date: "2026-01-01",
  employment_type: "full_time",
  employment_status: "active",
  is_active: true,
  termination_date: null,
  termination_reason: "",
  transition_history: [],
};

const department: Department = {
  id: "department-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  department_code: "ENG",
  department_name: "Engineering",
  parent_department: null,
  parent_department_name: null,
  manager: "employee-1",
  manager_name: "Ada Lovelace",
  is_active: true,
  description: "",
};

const leaveBalance: LeaveBalance = {
  id: "balance-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  employee: "employee-1",
  employee_number: "EMP-001",
  employee_name: "Ada Lovelace",
  leave_type: "annual",
  period_start: "2026-01-01",
  period_end: "2026-12-31",
  entitled_days: "20.00",
  carried_days: "0.00",
  used_days: "0.00",
  pending_days: "0.00",
  remaining_days: "20.00",
  adjustment_version: 1,
  last_adjusted_by: "hr-admin",
  adjustment_note: "Initial allocation",
};

const attendance: Attendance = {
  id: "attendance-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  employee: "employee-1",
  employee_number: "EMP-001",
  employee_name: "Ada Lovelace",
  attendance_date: "2026-01-02",
  check_in_time: "2026-01-02T09:00:00Z",
  check_out_time: "2026-01-02T17:00:00Z",
  hours_worked: "8.00",
  status: "present",
  source: "manual",
  notes: "On site",
};

const leaveRequest: LeaveRequest = {
  id: "request-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  employee: "employee-1",
  employee_number: "EMP-001",
  employee_name: "Ada Lovelace",
  leave_balance: "balance-1",
  leave_type: "annual",
  start_date: "2026-03-10",
  end_date: "2026-03-12",
  days_requested: "3.00",
  reason: "Family travel",
  status: "pending",
  approved_by: "",
  approved_at: null,
  rejection_reason: "",
  cancelled_by: "",
  cancelled_at: null,
  transition_history: [],
};

function page<T>(items: readonly T[] = []): PageResult<T> {
  return {
    items,
    pagination: { ...pagination, count: items.length, total_pages: items.length ? 1 : 0 },
    correlationId: "corr-list",
    capabilities: [],
  };
}

function renderAt(element: React.ReactNode, path: string, route = path) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
          <Route path={ROUTES.EMPLOYEES} element={<p>Employee index</p>} />
          <Route path={`${ROUTES.EMPLOYEES}/:id`} element={<p>Employee detail reached</p>} />
          <Route path={ROUTES.DEPARTMENTS} element={<p>Department index</p>} />
          <Route path={`${ROUTES.DEPARTMENTS}/:id`} element={<p>Department detail reached</p>} />
          <Route path={ROUTES.ATTENDANCE} element={<p>Attendance index</p>} />
          <Route path={`${ROUTES.ATTENDANCE}/:id`} element={<p>Attendance detail reached</p>} />
          <Route path={ROUTES.LEAVE} element={<p>Leave index</p>} />
          <Route path={`${ROUTES.LEAVE}/balances/:id`} element={<p>Leave balance detail reached</p>} />
          <Route path={`${ROUTES.LEAVE}/requests/:id`} element={<p>Leave request detail reached</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function mockChoiceSuccess() {
  vi.spyOn(hrService, "getConfiguration").mockResolvedValue({
    data: configuration,
    correlationId: "corr-config",
    capabilities: ["hr.configuration:read"],
  });
  vi.spyOn(hrService, "listEmployees").mockResolvedValue(page([employee]));
  vi.spyOn(hrService, "listDepartments").mockResolvedValue(page([department]));
  vi.spyOn(hrService, "listLeaveBalances").mockResolvedValue(page([leaveBalance]));
}

describe("Human Resources form pages", () => {
  beforeEach(() => {
    mockChoiceSuccess();
  });

  afterEach(() => vi.restoreAllMocks());

  it("shows a layout skeleton while required form choices are loading", () => {
    vi.spyOn(hrService, "getConfiguration").mockReturnValue(new Promise(() => undefined));

    renderAt(<CreateEmployeePage />, ROUTES.EMPLOYEE_CREATE);

    expect(screen.getByRole("status", { name: "Loading Human Resources" })).toBeInTheDocument();
  });

  it("renders a governed retry error when required choices fail to load", async () => {
    const listEmployees = vi
      .spyOn(hrService, "listEmployees")
      .mockRejectedValueOnce(
        new HrApiError("Lookup service unavailable", "unavailable", 503, "hr_lookup_down", "corr-choice")
      )
      .mockResolvedValueOnce(page([employee]));

    renderAt(<CreateEmployeePage />, ROUTES.EMPLOYEE_CREATE);

    expect(await screen.findByRole("heading", { name: "Form choices unavailable" })).toBeInTheDocument();
    expect(screen.getByText(/corr-choice/u)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "Create employee" })).toBeInTheDocument());
    expect(listEmployees).toHaveBeenCalledTimes(2);
  });

  it("stops leave request entry when a required choice set is empty", async () => {
    vi.spyOn(hrService, "listLeaveBalances").mockResolvedValue(page([]));

    renderAt(<CreateLeaveRequestPage />, ROUTES.LEAVE_REQUEST_CREATE);

    expect(await screen.findByRole("heading", { name: "Required choices unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Create or activate the required tenant resource, then retry this form.")).toBeInTheDocument();
  });

  it("validates employee fields locally before creating and navigating to the new detail page", async () => {
    const createEmployee = vi.spyOn(hrService, "createEmployee").mockResolvedValue({
      data: { ...employee, id: "employee-new", employee_number: "EMP-002", first_name: "Grace" },
      correlationId: "corr-create",
      capabilities: [],
    });
    const user = userEvent.setup();

    renderAt(<CreateEmployeePage />, ROUTES.EMPLOYEE_CREATE);

    await user.click(await screen.findByRole("button", { name: "Create employee" }));

    expect(createEmployee).not.toHaveBeenCalled();
    expect(screen.getAllByRole("alert").map((alert) => alert.textContent)).toContain("This field is required.");

    await user.type(screen.getByLabelText("Employee number"), "EMP-002");
    await user.type(screen.getByLabelText("First name"), "Grace");
    await user.type(screen.getByLabelText("Last name"), "Hopper");
    await user.type(screen.getByLabelText("Email"), "grace@example.test");
    await user.selectOptions(screen.getByLabelText("Department"), "department-1");
    await user.selectOptions(screen.getByLabelText("Manager"), "employee-1");
    await user.type(screen.getByLabelText("Position"), "Compiler Engineer");
    await user.click(screen.getByRole("button", { name: "Create employee" }));

    await waitFor(() =>
      expect(createEmployee).toHaveBeenCalledWith(
        expect.objectContaining({
          employee_number: "EMP-002",
          first_name: "Grace",
          last_name: "Hopper",
          email: "grace@example.test",
          department_id: "department-1",
          manager_id: "employee-1",
          position: "Compiler Engineer",
          employment_type: "full_time",
        })
      )
    );
    expect(await screen.findByText("Employee detail reached")).toBeInTheDocument();
  });

  it("protects dirty department forms through cancel and back navigation", async () => {
    const user = userEvent.setup();

    renderAt(<CreateDepartmentPage />, ROUTES.DEPARTMENT_CREATE);

    await user.type(await screen.findByLabelText("Department code"), "OPS");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByRole("dialog")).toHaveTextContent("Discard unsaved changes?");
    await user.click(screen.getByRole("button", { name: "Keep" }));
    expect(screen.getByRole("heading", { name: "Create department" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Go back" }));
    await user.click(screen.getByRole("button", { name: "Discard changes" }));

    expect(await screen.findByText("Department index")).toBeInTheDocument();
  });

  it("creates attendance only after an employee is selected and carries configured defaults", async () => {
    const createAttendance = vi.spyOn(hrService, "createAttendance").mockResolvedValue({
      data: { ...attendance, id: "attendance-new" },
      correlationId: "corr-attendance",
      capabilities: [],
    });
    const user = userEvent.setup();

    renderAt(<CreateAttendancePage />, ROUTES.ATTENDANCE_CREATE);

    await user.click(await screen.findByRole("button", { name: "Record attendance" }));
    expect(createAttendance).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByLabelText("Employee"), "employee-1");
    await user.click(screen.getByRole("button", { name: "Record attendance" }));

    await waitFor(() =>
      expect(createAttendance).toHaveBeenCalledWith(
        expect.objectContaining({
          employee_id: "employee-1",
          status: "present",
        })
      )
    );
    expect(await screen.findByText("Attendance detail reached")).toBeInTheDocument();
  });

  it("submits leave allocation payloads with employee selection and configuration defaults", async () => {
    const createLeaveBalance = vi.spyOn(hrService, "createLeaveBalance").mockResolvedValue({
      data: { ...leaveBalance, id: "balance-new" },
      correlationId: "corr-balance",
      capabilities: [],
    });
    const user = userEvent.setup();

    renderAt(<CreateLeaveBalancePage />, ROUTES.LEAVE_BALANCE_CREATE);

    await user.click(await screen.findByRole("button", { name: "Create allocation" }));
    expect(createLeaveBalance).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByLabelText("Employee"), "employee-1");
    await user.clear(screen.getByLabelText("Entitled days"));
    await user.clear(screen.getByLabelText("Carried days"));
    await user.click(screen.getByRole("button", { name: "Create allocation" }));

    await waitFor(() =>
      expect(createLeaveBalance).toHaveBeenCalledWith(
        expect.objectContaining({
          employee_id: "employee-1",
          leave_type: "annual",
          entitled_days: "0.00",
          carried_days: "0.00",
        })
      )
    );
    expect(await screen.findByText("Leave balance detail reached")).toBeInTheDocument();
  });

  it("updates employee edit pages with the current employee removed from manager choices", async () => {
    const updateEmployee = vi.spyOn(hrService, "updateEmployee").mockResolvedValue({
      data: { ...employee, first_name: "Ada-Updated" },
      correlationId: "corr-employee-update",
      capabilities: [],
    });
    vi.spyOn(hrService, "getEmployee").mockResolvedValue({
      data: employee,
      correlationId: "corr-employee-detail",
      capabilities: [],
    });
    const user = userEvent.setup();

    renderAt(<EditEmployeePage />, ROUTES.EMPLOYEE_EDIT("employee-1"), ROUTES.EMPLOYEE_EDIT(":id"));

    expect(await screen.findByRole("heading", { name: "Edit employee" })).toBeInTheDocument();
    expect(screen.getByLabelText("Manager")).not.toHaveTextContent("Ada Lovelace");

    await user.clear(screen.getByLabelText("First name"));
    await user.type(screen.getByLabelText("First name"), "Ada-Updated");
    await user.click(screen.getByRole("button", { name: "Save employee" }));

    await waitFor(() =>
      expect(updateEmployee).toHaveBeenCalledWith(
        "employee-1",
        expect.objectContaining({ first_name: "Ada-Updated" })
      )
    );
    expect(await screen.findByText("Employee detail reached")).toBeInTheDocument();
  });

  it("requires an adjustment note before updating a leave allocation", async () => {
    const updateLeaveBalance = vi.spyOn(hrService, "updateLeaveBalance").mockResolvedValue({
      data: { ...leaveBalance, adjustment_version: 2 },
      correlationId: "corr-balance-update",
      capabilities: [],
    });
    vi.spyOn(hrService, "getLeaveBalance").mockResolvedValue({
      data: leaveBalance,
      correlationId: "corr-balance-detail",
      capabilities: [],
    });
    const user = userEvent.setup();

    renderAt(
      <EditLeaveBalancePage />,
      ROUTES.LEAVE_BALANCE_EDIT("balance-1"),
      ROUTES.LEAVE_BALANCE_EDIT(":id")
    );

    await user.click(await screen.findByRole("button", { name: "Apply adjustment" }));
    expect(updateLeaveBalance).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Entitled days"));
    await user.type(screen.getByLabelText("Entitled days"), "24.00");
    await user.type(screen.getByLabelText("Adjustment note"), "Annual entitlement correction");
    await user.click(screen.getByRole("button", { name: "Apply adjustment" }));

    await waitFor(() =>
      expect(updateLeaveBalance).toHaveBeenCalledWith(
        "balance-1",
        expect.objectContaining({
          entitled_days: "24",
          expected_version: 1,
          note: "Annual entitlement correction",
        })
      )
    );
    expect(await screen.findByText("Leave balance detail reached")).toBeInTheDocument();
  });

  it("requires an attendance correction note before saving edit changes", async () => {
    const updateAttendance = vi.spyOn(hrService, "updateAttendance").mockResolvedValue({
      data: { ...attendance, notes: "Corrected source entry" },
      correlationId: "corr-attendance-update",
      capabilities: [],
    });
    vi.spyOn(hrService, "getAttendance").mockResolvedValue({
      data: attendance,
      correlationId: "corr-attendance-detail",
      capabilities: [],
    });
    const user = userEvent.setup();

    renderAt(
      <EditAttendancePage />,
      ROUTES.ATTENDANCE_EDIT("attendance-1"),
      ROUTES.ATTENDANCE_EDIT(":id")
    );

    await user.click(await screen.findByRole("button", { name: "Save correction" }));
    expect(updateAttendance).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Correction note (required)"), "Corrected source entry");
    await user.click(screen.getByRole("button", { name: "Save correction" }));

    await waitFor(() =>
      expect(updateAttendance).toHaveBeenCalledWith(
        "attendance-1",
        expect.objectContaining({ notes: "Corrected source entry" })
      )
    );
    expect(await screen.findByText("Attendance detail reached")).toBeInTheDocument();
  });

  it("blocks non-pending leave request edits and updates pending request dates", async () => {
    const updateLeaveRequest = vi.spyOn(hrService, "updateLeaveRequest").mockResolvedValue({
      data: { ...leaveRequest, start_date: "2026-03-11" },
      correlationId: "corr-request-update",
      capabilities: [],
    });
    const getLeaveRequest = vi
      .spyOn(hrService, "getLeaveRequest")
      .mockResolvedValueOnce({
        data: { ...leaveRequest, status: "approved" },
        correlationId: "corr-approved-request",
        capabilities: [],
      })
      .mockResolvedValueOnce({
        data: leaveRequest,
        correlationId: "corr-pending-request",
        capabilities: [],
      });
    const user = userEvent.setup();

    const { unmount } = renderAt(
      <EditLeaveRequestPage />,
      ROUTES.LEAVE_REQUEST_EDIT("request-1"),
      ROUTES.LEAVE_REQUEST_EDIT(":id")
    );

    expect(
      await screen.findByRole("heading", { name: "Human Resources is unavailable" })
    ).toBeInTheDocument();
    expect(screen.getByText("Only pending requests can change.")).toBeInTheDocument();
    expect(updateLeaveRequest).not.toHaveBeenCalled();
    unmount();

    renderAt(
      <EditLeaveRequestPage />,
      ROUTES.LEAVE_REQUEST_EDIT("request-1"),
      ROUTES.LEAVE_REQUEST_EDIT(":id")
    );

    await user.clear(await screen.findByLabelText("Start date"));
    await user.type(screen.getByLabelText("Start date"), "2026-03-11");
    await user.type(screen.getByLabelText("Reason"), "Updated itinerary");
    await user.click(screen.getByRole("button", { name: "Save request" }));

    await waitFor(() =>
      expect(updateLeaveRequest).toHaveBeenCalledWith(
        "request-1",
        expect.objectContaining({
          start_date: "2026-03-11",
          end_date: "2026-03-12",
          reason: "Family travelUpdated itinerary",
        })
      )
    );
    expect(getLeaveRequest).toHaveBeenCalled();
    expect(await screen.findByText("Leave request detail reached")).toBeInTheDocument();
  });
});
