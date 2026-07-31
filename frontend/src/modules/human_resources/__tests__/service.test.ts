/* eslint-disable max-lines-per-function -- HR service mutation coverage keeps endpoint matrices colocated with request assertions. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import { ENDPOINTS, hrKeys } from "../contracts";
import {
  HrApiError,
  clearIntentKey,
  fieldErrors,
  hrService,
  newIntentKey,
  persistentIntentKey,
} from "../services/hr-service";

const pagination = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};
const meta = { correlation_id: "corr-hr-1", timestamp: "2026-07-22T00:00:00Z" };
const configurationDocument = {};
const configurationDetail = {
  id: "config-1",
  environment: "default",
  version: 2,
  document: configurationDocument,
  updated_at: meta.timestamp,
};
const page = (data: readonly unknown[]) => ({
  data,
  meta: { ...meta, pagination, capabilities: ["hr.employee:create"] },
});
const detail = (data: unknown) => ({ data, meta });
const employee = {
  id: "employee-1",
  employee_number: "EMP-1",
  first_name: "Ada",
  last_name: "Lovelace",
  employment_status: "active",
};
const department = {
  id: "department-1",
  department_code: "ENG",
  department_name: "Engineering",
  is_active: true,
};
const attendance = {
  id: "attendance-1",
  employee: "employee-1",
  attendance_date: "2026-07-22",
  status: "present",
};
const balance = {
  id: "balance-1",
  employee: "employee-1",
  leave_type: "annual",
  remaining_days: "10.00",
};
const request = {
  id: "request-1",
  employee: "employee-1",
  leave_balance: "balance-1",
  status: "pending",
};

describe("hrService", () => {
  afterEach(() => vi.restoreAllMocks());

  it("publishes stable HR cache keys for every resource family", () => {
    expect(hrKeys.all).toEqual(["human-resources"]);
    expect(hrKeys.departments()).toEqual(["human-resources", "departments", {}]);
    expect(hrKeys.departments({ is_active: false })).toEqual([
      "human-resources",
      "departments",
      { is_active: false },
    ]);
    expect(hrKeys.department("department-1")).toEqual([
      "human-resources",
      "department",
      "department-1",
    ]);
    expect(hrKeys.hierarchy()).toEqual(["human-resources", "department-tree", "", false]);
    expect(hrKeys.hierarchy("department-1", true)).toEqual([
      "human-resources",
      "department-tree",
      "department-1",
      true,
    ]);
    expect(hrKeys.employees()).toEqual(["human-resources", "employees", {}]);
    expect(hrKeys.employee("employee-1")).toEqual(["human-resources", "employee", "employee-1"]);
    expect(hrKeys.reportingTree("employee-1", 3)).toEqual([
      "human-resources",
      "reporting-tree",
      "employee-1",
      3,
    ]);
    expect(hrKeys.attendances()).toEqual(["human-resources", "attendances", {}]);
    expect(hrKeys.attendance("attendance-1")).toEqual([
      "human-resources",
      "attendance",
      "attendance-1",
    ]);
    expect(hrKeys.leaveBalances()).toEqual(["human-resources", "leave-balances", {}]);
    expect(hrKeys.leaveBalance("balance-1")).toEqual([
      "human-resources",
      "leave-balance",
      "balance-1",
    ]);
    expect(hrKeys.leaveRequests()).toEqual(["human-resources", "leave-requests", {}]);
    expect(hrKeys.leaveRequest("request-1")).toEqual([
      "human-resources",
      "leave-request",
      "request-1",
    ]);
    expect(hrKeys.configuration).toEqual(["human-resources", "configuration"]);
    expect(hrKeys.configurationHistory).toEqual(["human-resources", "configuration", "history"]);
    expect(hrKeys.configurationAudit).toEqual(["human-resources", "configuration", "audit"]);
    expect(hrKeys.health).toEqual(["human-resources", "health"]);
  });

  it.each([
    [400, "validation"],
    [401, "authentication"],
    [403, "permission"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "validation"],
    [429, "rate_limit"],
    [503, "unavailable"],
    [418, "unexpected"],
  ] as const)("maps HTTP %s to %s errors", async (status, kind) => {
    vi.spyOn(apiClient, "get").mockRejectedValueOnce(
      new ApiError("Governed HR failure", status, {}, "hr_failure", "corr-http")
    );

    await expect(hrService.getEmployee("employee-1")).rejects.toMatchObject({
      kind,
      status,
      code: "hr_failure",
      correlationId: "corr-http",
    });
  });

  it("normalizes network, thrown Error, and non-Error failures", async () => {
    const governedFailure = new HrApiError(
      "Already normalized",
      "validation",
      422,
      "validation_error",
      "corr-normalized"
    );
    vi.spyOn(apiClient, "get").mockRejectedValueOnce(governedFailure);
    await expect(hrService.getHealth()).rejects.toBe(governedFailure);

    vi.spyOn(apiClient, "get").mockRejectedValueOnce(new TypeError("fetch failed"));
    await expect(hrService.getHealth()).rejects.toMatchObject({
      kind: "network",
      status: null,
      code: "network_error",
      message: "Human Resources could not be reached. Check your connection and retry.",
    });

    vi.spyOn(apiClient, "get").mockRejectedValueOnce(new Error("bad extension"));
    await expect(hrService.getHealth()).rejects.toMatchObject({
      kind: "unexpected",
      status: null,
      code: "unexpected_error",
      message: "bad extension",
    });

    vi.spyOn(apiClient, "get").mockRejectedValueOnce("boom");
    await expect(hrService.getHealth()).rejects.toMatchObject({
      kind: "unexpected",
      status: null,
      code: "unexpected_error",
      message: "Unexpected Human Resources failure.",
    });

    vi.spyOn(apiClient, "get").mockRejectedValueOnce(
      new ApiError("No code", 418, {}, undefined, undefined)
    );
    await expect(hrService.getHealth()).rejects.toMatchObject({
      kind: "unexpected",
      status: 418,
      code: "request_failed",
      correlationId: null,
    });
  });

  it("strictly decodes all five governed collections and preserves pagination/capabilities", async () => {
    const get = vi.spyOn(apiClient, "get");
    get
      .mockResolvedValueOnce(page([department]) as never)
      .mockResolvedValueOnce(page([employee]) as never)
      .mockResolvedValueOnce(page([attendance]) as never)
      .mockResolvedValueOnce(page([balance]) as never)
      .mockResolvedValueOnce(page([request]) as never);
    expect((await hrService.listDepartments()).pagination.count).toBe(1);
    expect((await hrService.listEmployees()).capabilities).toContain("hr.employee:create");
    expect((await hrService.listAttendances()).items[0]?.id).toBe("attendance-1");
    expect((await hrService.listLeaveBalances()).items[0]?.id).toBe("balance-1");
    expect((await hrService.listLeaveRequests()).correlationId).toBe("corr-hr-1");
  });
  it("sends lifecycle and leave action idempotency keys in headers", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValueOnce(detail(employee) as never)
      .mockResolvedValueOnce(detail(request) as never);
    await hrService.transitionEmployee("employee-1", "deactivate", { transition_key: "intent-1" });
    await hrService.approveLeaveRequest("request-1", { transition_key: "intent-2" });
    expect(post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.EMPLOYEES.DEACTIVATE("employee-1"),
      { transition_key: "intent-1" },
      { headers: { "Idempotency-Key": "intent-1" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.LEAVE_REQUESTS.APPROVE("request-1"),
      { transition_key: "intent-2" },
      { headers: { "Idempotency-Key": "intent-2" } }
    );
  });

  it("routes every employee lifecycle command to its governed endpoint", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(detail(employee) as never);

    await hrService.transitionEmployee("employee-1", "activate", {
      transition_key: "intent-activate",
    });
    await hrService.transitionEmployee("employee-1", "place_on_leave", {
      transition_key: "intent-leave",
    });
    await hrService.transitionEmployee("employee-1", "return_from_leave", {
      transition_key: "intent-return",
    });
    await hrService.transitionEmployee("employee-1", "terminate", {
      transition_key: "intent-terminate",
      effective_date: "2026-07-31",
      reason: "Contract ended",
    });

    expect(post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.EMPLOYEES.ACTIVATE("employee-1"),
      { transition_key: "intent-activate" },
      { headers: { "Idempotency-Key": "intent-activate" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.EMPLOYEES.PLACE_ON_LEAVE("employee-1"),
      { transition_key: "intent-leave" },
      { headers: { "Idempotency-Key": "intent-leave" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.EMPLOYEES.RETURN_FROM_LEAVE("employee-1"),
      { transition_key: "intent-return" },
      { headers: { "Idempotency-Key": "intent-return" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.EMPLOYEES.TERMINATE("employee-1"),
      {
        transition_key: "intent-terminate",
        effective_date: "2026-07-31",
        reason: "Contract ended",
      },
      { headers: { "Idempotency-Key": "intent-terminate" } }
    );
  });

  it("sends idempotency keys for department, attendance, leave request, and configuration mutations", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValueOnce(detail(department) as never)
      .mockResolvedValueOnce(detail(department) as never)
      .mockResolvedValueOnce(detail(attendance) as never)
      .mockResolvedValueOnce(detail(attendance) as never)
      .mockResolvedValueOnce(detail(request) as never)
      .mockResolvedValueOnce(detail(request) as never)
      .mockResolvedValueOnce(detail(request) as never)
      .mockResolvedValueOnce(detail(configurationDetail) as never);
    const patch = vi
      .spyOn(apiClient, "patch")
      .mockResolvedValue(detail(configurationDetail) as never);
    const deleteRequest = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined as never);

    await hrService.activateDepartment("department-1", {
      idempotency_key: "dept-activate",
      reason: "Department reopened",
    });
    await hrService.deactivateDepartment("department-1", {
      idempotency_key: "dept-deactivate",
      reason: "Department sunset",
    });
    await hrService.clockIn({ employee_id: "employee-1", idempotency_key: "clock-in" });
    await hrService.clockOut("attendance-1", { idempotency_key: "clock-out" });
    await hrService.createLeaveRequest({
      employee_id: "employee-1",
      leave_balance_id: "balance-1",
      leave_type: "annual",
      start_date: "2026-08-01",
      end_date: "2026-08-02",
      reason: "Family travel",
      idempotency_key: "request-create",
    });
    await hrService.rejectLeaveRequest("request-1", {
      transition_key: "request-reject",
      rejection_reason: "Insufficient evidence",
    });
    await hrService.cancelLeaveRequest("request-1", {
      transition_key: "request-cancel",
    });
    await hrService.rollbackConfiguration({
      environment: "default",
      version: 2,
      change_reason: "Restore tenant defaults",
      idempotency_key: "config-rollback",
    });
    await hrService.updateConfiguration({
      environment: "default",
      document: configurationDocument as never,
      change_reason: "Tune tenant controls",
      idempotency_key: "config-update",
    });
    await hrService.deleteLeaveRequest("request-1", "request-delete");

    expect(post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.DEPARTMENTS.ACTIVATE("department-1"),
      { idempotency_key: "dept-activate", reason: "Department reopened" },
      { headers: { "Idempotency-Key": "dept-activate" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.DEPARTMENTS.DEACTIVATE("department-1"),
      { idempotency_key: "dept-deactivate", reason: "Department sunset" },
      { headers: { "Idempotency-Key": "dept-deactivate" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.ATTENDANCES.CLOCK_IN,
      { employee_id: "employee-1", idempotency_key: "clock-in" },
      { headers: { "Idempotency-Key": "clock-in" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.ATTENDANCES.CLOCK_OUT("attendance-1"),
      { idempotency_key: "clock-out" },
      { headers: { "Idempotency-Key": "clock-out" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      5,
      ENDPOINTS.LEAVE_REQUESTS.CREATE,
      expect.objectContaining({ idempotency_key: "request-create" }),
      { headers: { "Idempotency-Key": "request-create" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      6,
      ENDPOINTS.LEAVE_REQUESTS.REJECT("request-1"),
      { transition_key: "request-reject", rejection_reason: "Insufficient evidence" },
      { headers: { "Idempotency-Key": "request-reject" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      7,
      ENDPOINTS.LEAVE_REQUESTS.CANCEL("request-1"),
      { transition_key: "request-cancel" },
      { headers: { "Idempotency-Key": "request-cancel" } }
    );
    expect(post).toHaveBeenNthCalledWith(
      8,
      ENDPOINTS.CONFIGURATION.ROLLBACK,
      {
        environment: "default",
        version: 2,
        change_reason: "Restore tenant defaults",
        idempotency_key: "config-rollback",
      },
      { headers: { "Idempotency-Key": "config-rollback" } }
    );
    expect(patch).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.BASE,
      {
        environment: "default",
        document: configurationDocument,
        change_reason: "Tune tenant controls",
        idempotency_key: "config-update",
      },
      { headers: { "Idempotency-Key": "config-update" } }
    );
    expect(deleteRequest).toHaveBeenCalledWith(ENDPOINTS.LEAVE_REQUESTS.DELETE("request-1"), {
      headers: { "Idempotency-Key": "request-delete" },
    });
  });

  it("rejects raw and legacy list shapes instead of fabricating an empty success", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValueOnce([] as never);
    await expect(hrService.listEmployees()).rejects.toMatchObject({
      kind: "invalid_response",
      code: "invalid_response",
    });
  });

  it("omits empty HR query filters while preserving false and zero values", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(page([department]) as never);

    await hrService.listDepartments({
      search: "",
      is_active: false,
      page: 0,
      parent_department_id: null,
    } as never);

    const url = get.mock.calls[0]?.[0] ?? "";
    expect(url).toContain("is_active=false");
    expect(url).toContain("page=0");
    expect(url).not.toContain("search=");
    expect(url).not.toContain("parent_department_id=");
  });

  it("covers base CRUD endpoints for departments, employees, attendance, balances, and requests", async () => {
    const get = vi.spyOn(apiClient, "get");
    const post = vi.spyOn(apiClient, "post");
    const patch = vi.spyOn(apiClient, "patch");
    const deleteRequest = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined as never);

    get
      .mockResolvedValueOnce(detail(department) as never)
      .mockResolvedValueOnce(detail(employee) as never)
      .mockResolvedValueOnce(detail(attendance) as never)
      .mockResolvedValueOnce(detail(balance) as never)
      .mockResolvedValueOnce(detail(request) as never);
    await expect(hrService.getDepartment("department-1")).resolves.toMatchObject({
      data: { department_code: "ENG" },
    });
    await expect(hrService.getEmployee("employee-1")).resolves.toMatchObject({
      data: { employee_number: "EMP-1" },
    });
    await expect(hrService.getAttendance("attendance-1")).resolves.toMatchObject({
      data: { status: "present" },
    });
    await expect(hrService.getLeaveBalance("balance-1")).resolves.toMatchObject({
      data: { leave_type: "annual" },
    });
    await expect(hrService.getLeaveRequest("request-1")).resolves.toMatchObject({
      data: { status: "pending" },
    });

    post
      .mockResolvedValueOnce(detail(department) as never)
      .mockResolvedValueOnce(detail(employee) as never)
      .mockResolvedValueOnce(detail(attendance) as never)
      .mockResolvedValueOnce(detail(balance) as never);
    await hrService.createDepartment({ department_code: "ENG", department_name: "Engineering" });
    await hrService.createEmployee({
      employee_number: "EMP-1",
      first_name: "Ada",
      last_name: "Lovelace",
      email: "ada@example.test",
      hire_date: "2026-07-22",
      employment_type: "full_time",
    });
    await hrService.createAttendance({
      employee_id: "employee-1",
      attendance_date: "2026-07-22",
      status: "present",
    });
    await hrService.createLeaveBalance({
      employee_id: "employee-1",
      leave_type: "annual",
      period_start: "2026-01-01",
      period_end: "2026-12-31",
      entitled_days: "12.00",
    });
    expect(post).toHaveBeenNthCalledWith(1, ENDPOINTS.DEPARTMENTS.CREATE, {
      department_code: "ENG",
      department_name: "Engineering",
    });
    expect(post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.EMPLOYEES.CREATE,
      expect.objectContaining({ employee_number: "EMP-1" })
    );
    expect(post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.ATTENDANCES.CREATE,
      expect.objectContaining({ status: "present" })
    );
    expect(post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.LEAVE_BALANCES.CREATE,
      expect.objectContaining({ leave_type: "annual" })
    );

    patch
      .mockResolvedValueOnce(detail(department) as never)
      .mockResolvedValueOnce(detail(employee) as never)
      .mockResolvedValueOnce(detail(attendance) as never)
      .mockResolvedValueOnce(detail(balance) as never)
      .mockResolvedValueOnce(detail(request) as never);
    await hrService.updateDepartment("department-1", { description: "R&D" });
    await hrService.updateEmployee("employee-1", { position: "Architect" });
    await hrService.updateAttendance("attendance-1", { notes: "Corrected", status: "late" });
    await hrService.updateLeaveBalance("balance-1", {
      entitled_days: "12.00",
      carried_days: "1.00",
      expected_version: 3,
      note: "Annual rollover",
    });
    await hrService.updateLeaveRequest("request-1", {
      start_date: "2026-08-01",
      end_date: "2026-08-03",
      reason: "Family travel",
    });
    expect(patch).toHaveBeenNthCalledWith(1, ENDPOINTS.DEPARTMENTS.UPDATE("department-1"), {
      description: "R&D",
    });
    expect(patch).toHaveBeenNthCalledWith(2, ENDPOINTS.EMPLOYEES.UPDATE("employee-1"), {
      position: "Architect",
    });
    expect(patch).toHaveBeenNthCalledWith(3, ENDPOINTS.ATTENDANCES.UPDATE("attendance-1"), {
      notes: "Corrected",
      status: "late",
    });
    expect(patch).toHaveBeenNthCalledWith(4, ENDPOINTS.LEAVE_BALANCES.UPDATE("balance-1"), {
      entitled_days: "12.00",
      carried_days: "1.00",
      expected_version: 3,
      note: "Annual rollover",
    });
    expect(patch).toHaveBeenNthCalledWith(5, ENDPOINTS.LEAVE_REQUESTS.UPDATE("request-1"), {
      start_date: "2026-08-01",
      end_date: "2026-08-03",
      reason: "Family travel",
    });

    await hrService.deleteDepartment("department-1");
    await hrService.deleteEmployee("employee-1");
    await hrService.deleteAttendance("attendance-1");
    await hrService.deleteLeaveBalance("balance-1");
    expect(deleteRequest).toHaveBeenNthCalledWith(1, ENDPOINTS.DEPARTMENTS.DELETE("department-1"));
    expect(deleteRequest).toHaveBeenNthCalledWith(2, ENDPOINTS.EMPLOYEES.DELETE("employee-1"));
    expect(deleteRequest).toHaveBeenNthCalledWith(3, ENDPOINTS.ATTENDANCES.DELETE("attendance-1"));
    expect(deleteRequest).toHaveBeenNthCalledWith(4, ENDPOINTS.LEAVE_BALANCES.DELETE("balance-1"));
  });

  it("rejects malformed detail, page item, hierarchy, reporting tree, health, and configuration envelopes", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValueOnce(detail({ id: "department-1" }) as never);
    await expect(hrService.getDepartment("department-1")).rejects.toMatchObject({
      kind: "invalid_response",
      correlationId: "corr-hr-1",
    });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(page([{ id: "employee-1" }]) as never);
    await expect(hrService.listEmployees()).rejects.toMatchObject({ kind: "invalid_response" });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(detail([{ id: "department-1" }]) as never);
    await expect(hrService.getDepartmentHierarchy()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(detail({ id: "employee-1" }) as never);
    await expect(hrService.getReportingTree("employee-1", 2)).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(
      detail({ module: "human_resources" }) as never
    );
    await expect(hrService.getHealth()).rejects.toMatchObject({ kind: "invalid_response" });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(detail({ id: "config-1" }) as never);
    await expect(hrService.getConfiguration()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: employee });
    await expect(hrService.getEmployee("employee-1")).rejects.toMatchObject({
      kind: "invalid_response",
      correlationId: null,
    });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce({
      data: [employee],
      meta: { ...meta, pagination: { count: 1 } },
    } as never);
    await expect(hrService.listEmployees()).rejects.toMatchObject({
      kind: "invalid_response",
      correlationId: "corr-hr-1",
    });
  });

  it("rejects HR guard property mutations across governed surfaces", async () => {
    const getCases = [
      [() => hrService.getDepartment("department-1"), { ...department, department_code: 7 }],
      [() => hrService.getDepartment("department-1"), { ...department, is_active: "true" }],
      [() => hrService.getEmployee("employee-1"), { ...employee, employee_number: 7 }],
      [() => hrService.getEmployee("employee-1"), { ...employee, employment_status: null }],
      [() => hrService.getAttendance("attendance-1"), { ...attendance, attendance_date: 20260722 }],
      [() => hrService.getAttendance("attendance-1"), { ...attendance, status: false }],
      [() => hrService.getLeaveBalance("balance-1"), { ...balance, remaining_days: 10 }],
      [() => hrService.getLeaveRequest("request-1"), { ...request, leave_balance: null }],
      [() => hrService.getDepartmentHierarchy(), [{ id: "department-1", children: {} }]],
      [() => hrService.getReportingTree("employee-1", 1), { id: "employee-1", direct_reports: {} }],
      [
        () => hrService.getHealth(),
        {
          module: "human_resources",
          status: "degraded",
          live: true,
          ready: true,
          checked_at: meta.timestamp,
          checks: {},
        },
      ],
      [() => hrService.getHealth(), { module: "human_resources", status: "healthy", live: "yes" }],
      [() => hrService.getConfiguration(), { ...configurationDetail, version: "2" }],
      [() => hrService.getConfiguration(), { ...configurationDetail, document: null }],
      [
        () => hrService.exportConfiguration(),
        {
          schema: "saraise.human_resources.configuration",
          environment: 7,
          version: 2,
          document: {},
        },
      ],
    ] as const;

    for (const [run, response] of getCases) {
      vi.spyOn(apiClient, "get").mockResolvedValueOnce(detail(response) as never);
      await expect(run()).rejects.toMatchObject({ kind: "invalid_response" });
    }

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(
      page([
        {
          id: "version-2",
          version: "2",
          environment: "default",
          document: {},
          correlation_id: "corr-version",
          created_at: meta.timestamp,
        },
      ]) as never
    );
    await expect(hrService.getConfigurationHistory()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(
      page([
        {
          id: "audit-1",
          version: 2,
          actor_id: "actor-1",
          correlation_id: 42,
          created_at: meta.timestamp,
          after_document: {},
        },
      ]) as never
    );
    await expect(hrService.getConfigurationAudit()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.spyOn(apiClient, "post").mockResolvedValueOnce(
      detail({ valid: true, normalized_document: null, changes: [] }) as never
    );
    await expect(
      hrService.previewConfiguration({
        environment: "default",
        document: {} as never,
        change_reason: "Preview",
      })
    ).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("rejects remaining HR guard boundary mutations", async () => {
    const getCases = [
      [() => hrService.getDepartmentHierarchy(), [{ id: "department-1", children: [] }, "bad"]],
      [
        () => hrService.getHealth(),
        {
          module: "human_resources",
          status: "unhealthy",
          live: true,
          ready: false,
          checked_at: 123,
          checks: {},
        },
      ],
      [
        () => hrService.getHealth(),
        {
          module: "wrong",
          status: "healthy",
          live: true,
          ready: true,
          checked_at: meta.timestamp,
          checks: {},
        },
      ],
      [() => hrService.getConfiguration(), { ...configurationDetail, id: 42 }],
      [() => hrService.getConfiguration(), { ...configurationDetail, environment: 42 }],
      [() => hrService.getConfiguration(), { ...configurationDetail, updated_at: 42 }],
      [
        () => hrService.exportConfiguration(),
        {
          schema: "wrong",
          environment: "default",
          version: 2,
          document: {},
        },
      ],
    ] as const;

    for (const [run, response] of getCases) {
      vi.spyOn(apiClient, "get").mockResolvedValueOnce(detail(response) as never);
      await expect(run()).rejects.toMatchObject({ kind: "invalid_response" });
    }

    vi.spyOn(apiClient, "post").mockResolvedValueOnce(
      detail({ valid: "true", normalized_document: {}, changes: [] }) as never
    );
    await expect(
      hrService.previewConfiguration({
        environment: "default",
        document: {} as never,
        change_reason: "Preview",
      })
    ).rejects.toMatchObject({ kind: "invalid_response" });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(
      page([
        {
          id: "version-2",
          version: 2,
          environment: 42,
          document: {},
          correlation_id: "corr-version",
          created_at: meta.timestamp,
        },
      ]) as never
    );
    await expect(hrService.getConfigurationHistory()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce(
      page([
        {
          id: "audit-1",
          version: 2,
          actor_id: 42,
          correlation_id: "corr-audit",
          created_at: meta.timestamp,
          after_document: {},
        },
      ]) as never
    );
    await expect(hrService.getConfigurationAudit()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.spyOn(apiClient, "get").mockResolvedValueOnce({
      data: [employee],
      meta: { ...meta, pagination },
    } as never);
    await expect(hrService.listEmployees()).resolves.toMatchObject({ capabilities: [] });
  });

  it("preserves default query parameters for hierarchy, reporting, and configuration reads", async () => {
    const get = vi.spyOn(apiClient, "get");
    get
      .mockResolvedValueOnce(detail([{ id: "department-1", children: [] }]) as never)
      .mockResolvedValueOnce(detail({ id: "employee-1", direct_reports: [] }) as never)
      .mockResolvedValueOnce(detail(configurationDetail) as never)
      .mockResolvedValueOnce(page([]) as never)
      .mockResolvedValueOnce(
        detail({
          schema: "saraise.human_resources.configuration",
          environment: "default",
          version: 2,
          document: configurationDocument,
        }) as never
      )
      .mockResolvedValueOnce(page([]) as never);

    await hrService.getDepartmentHierarchy();
    await hrService.getReportingTree("employee-1", 0);
    await hrService.getConfiguration();
    await hrService.getConfigurationHistory();
    await hrService.exportConfiguration();
    await hrService.getConfigurationAudit();

    expect(get).toHaveBeenNthCalledWith(1, `${ENDPOINTS.DEPARTMENTS.TREE}?include_inactive=false`);
    expect(get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.EMPLOYEES.REPORTING_TREE("employee-1")}?depth=0`
    );
    expect(get).toHaveBeenNthCalledWith(3, `${ENDPOINTS.CONFIGURATION.BASE}?environment=default`);
    expect(get).toHaveBeenNthCalledWith(
      4,
      `${ENDPOINTS.CONFIGURATION.HISTORY}?environment=default`
    );
    expect(get).toHaveBeenNthCalledWith(5, `${ENDPOINTS.CONFIGURATION.EXPORT}?environment=default`);
    expect(get).toHaveBeenNthCalledWith(6, `${ENDPOINTS.CONFIGURATION.AUDIT}?environment=default`);
  });

  it("uses resource-specific invalid response messages for every HR wrapper", async () => {
    const invalidDetail = detail({});
    const invalidPage = { data: [{}], meta: { ...meta, pagination } };
    const cases = [
      [() => hrService.listDepartments(), "get", invalidPage, "department page"],
      [() => hrService.getDepartment("department-1"), "get", invalidDetail, "department response"],
      [
        () =>
          hrService.createDepartment({ department_code: "ENG", department_name: "Engineering" }),
        "post",
        invalidDetail,
        "department response",
      ],
      [
        () => hrService.updateDepartment("department-1", { description: "R&D" }),
        "patch",
        invalidDetail,
        "department response",
      ],
      [
        () =>
          hrService.activateDepartment("department-1", { idempotency_key: "a", reason: "Open" }),
        "post",
        invalidDetail,
        "department activation response",
      ],
      [
        () =>
          hrService.deactivateDepartment("department-1", { idempotency_key: "d", reason: "Close" }),
        "post",
        invalidDetail,
        "department deactivation response",
      ],
      [
        () => hrService.getDepartmentHierarchy(),
        "get",
        invalidDetail,
        "department hierarchy response",
      ],
      [() => hrService.listEmployees(), "get", invalidPage, "employee page"],
      [() => hrService.getEmployee("employee-1"), "get", invalidDetail, "employee response"],
      [
        () =>
          hrService.createEmployee({
            employee_number: "EMP-1",
            first_name: "Ada",
            last_name: "Lovelace",
            email: "ada@example.test",
            hire_date: "2026-07-22",
            employment_type: "full_time",
          }),
        "post",
        invalidDetail,
        "employee response",
      ],
      [
        () => hrService.updateEmployee("employee-1", { position: "Architect" }),
        "patch",
        invalidDetail,
        "employee response",
      ],
      [
        () => hrService.getReportingTree("employee-1", 1),
        "get",
        invalidDetail,
        "reporting tree response",
      ],
      [
        () =>
          hrService.transitionEmployee("employee-1", "activate", { transition_key: "activate" }),
        "post",
        invalidDetail,
        "employee transition response",
      ],
      [() => hrService.listAttendances(), "get", invalidPage, "attendance page"],
      [() => hrService.getAttendance("attendance-1"), "get", invalidDetail, "attendance response"],
      [
        () =>
          hrService.createAttendance({
            employee_id: "employee-1",
            attendance_date: "2026-07-22",
            status: "present",
          }),
        "post",
        invalidDetail,
        "attendance response",
      ],
      [
        () => hrService.updateAttendance("attendance-1", { notes: "Corrected" }),
        "patch",
        invalidDetail,
        "attendance response",
      ],
      [
        () => hrService.clockIn({ employee_id: "employee-1", idempotency_key: "clock-in" }),
        "post",
        invalidDetail,
        "clock-in response",
      ],
      [
        () => hrService.clockOut("attendance-1", { idempotency_key: "clock-out" }),
        "post",
        invalidDetail,
        "clock-out response",
      ],
      [() => hrService.listLeaveBalances(), "get", invalidPage, "leave balance page"],
      [
        () => hrService.getLeaveBalance("balance-1"),
        "get",
        invalidDetail,
        "leave balance response",
      ],
      [
        () =>
          hrService.createLeaveBalance({
            employee_id: "employee-1",
            leave_type: "annual",
            period_start: "2026-01-01",
            period_end: "2026-12-31",
            entitled_days: "12.00",
          }),
        "post",
        invalidDetail,
        "leave balance response",
      ],
      [
        () =>
          hrService.updateLeaveBalance("balance-1", {
            entitled_days: "12.00",
            carried_days: "1.00",
            expected_version: 1,
            note: "Review",
          }),
        "patch",
        invalidDetail,
        "leave balance response",
      ],
      [() => hrService.listLeaveRequests(), "get", invalidPage, "leave request page"],
      [
        () => hrService.getLeaveRequest("request-1"),
        "get",
        invalidDetail,
        "leave request response",
      ],
      [
        () =>
          hrService.createLeaveRequest({
            employee_id: "employee-1",
            leave_balance_id: "balance-1",
            leave_type: "annual",
            start_date: "2026-08-01",
            end_date: "2026-08-02",
            idempotency_key: "leave-create",
          }),
        "post",
        invalidDetail,
        "leave request response",
      ],
      [
        () =>
          hrService.updateLeaveRequest("request-1", {
            start_date: "2026-08-01",
            end_date: "2026-08-02",
          }),
        "patch",
        invalidDetail,
        "leave request response",
      ],
      [
        () => hrService.approveLeaveRequest("request-1", { transition_key: "approve" }),
        "post",
        invalidDetail,
        "leave approval response",
      ],
      [
        () =>
          hrService.rejectLeaveRequest("request-1", {
            transition_key: "reject",
            rejection_reason: "Insufficient balance",
          }),
        "post",
        invalidDetail,
        "leave rejection response",
      ],
      [
        () => hrService.cancelLeaveRequest("request-1", { transition_key: "cancel" }),
        "post",
        invalidDetail,
        "leave cancellation response",
      ],
      [() => hrService.getConfiguration(), "get", invalidDetail, "configuration response"],
      [
        () =>
          hrService.updateConfiguration({
            environment: "default",
            document: {} as never,
            change_reason: "Update",
            idempotency_key: "config-update",
          }),
        "patch",
        invalidDetail,
        "configuration response",
      ],
      [
        () =>
          hrService.previewConfiguration({
            environment: "default",
            document: {} as never,
            change_reason: "Preview",
          }),
        "post",
        invalidDetail,
        "configuration preview response",
      ],
      [() => hrService.getConfigurationHistory(), "get", invalidPage, "configuration history page"],
      [
        () =>
          hrService.rollbackConfiguration({
            environment: "default",
            version: 1,
            change_reason: "Rollback",
            idempotency_key: "rollback",
          }),
        "post",
        invalidDetail,
        "configuration rollback response",
      ],
      [
        () =>
          hrService.importConfiguration({
            environment: "default",
            document: {} as never,
            change_reason: "Import",
            idempotency_key: "import",
          }),
        "post",
        invalidDetail,
        "configuration import response",
      ],
      [
        () => hrService.exportConfiguration(),
        "get",
        invalidDetail,
        "configuration export response",
      ],
      [() => hrService.getConfigurationAudit(), "get", invalidPage, "configuration audit page"],
      [() => hrService.getHealth(), "get", invalidDetail, "health response"],
    ] as const;

    for (const [run, method, response, label] of cases) {
      vi.restoreAllMocks();
      vi.spyOn(apiClient, method).mockResolvedValueOnce(response as never);
      await expect(run()).rejects.toMatchObject({
        kind: "invalid_response",
        message: `Human Resources returned an invalid ${label}.`,
      });
    }
  });

  it("governs hierarchy, reporting tree, health, configuration history, audit, preview, import, and export reads", async () => {
    const get = vi.spyOn(apiClient, "get");
    const post = vi.spyOn(apiClient, "post");
    get
      .mockResolvedValueOnce(detail([{ id: "department-1", children: [] }]) as never)
      .mockResolvedValueOnce(detail({ id: "employee-1", direct_reports: [] }) as never)
      .mockResolvedValueOnce(
        detail({
          module: "human_resources",
          status: "healthy",
          live: true,
          ready: true,
          checked_at: meta.timestamp,
          checks: {},
        }) as never
      )
      .mockResolvedValueOnce(
        page([
          {
            id: "version-2",
            version: 2,
            environment: "default",
            document: configurationDocument,
            created_by: "actor-1",
            correlation_id: "corr-version",
            created_at: meta.timestamp,
            change_reason: "Tune tenant controls",
            rolled_back_from_version: null,
          },
        ]) as never
      )
      .mockResolvedValueOnce(
        detail({
          schema: "saraise.human_resources.configuration",
          environment: "default",
          version: 2,
          document: configurationDocument,
        }) as never
      )
      .mockResolvedValueOnce(
        page([
          {
            id: "audit-1",
            version: 2,
            actor_id: "actor-1",
            correlation_id: "corr-audit",
            created_at: meta.timestamp,
            environment: "default",
            action: "update",
            change_reason: "Tune tenant controls",
            before_document: null,
            after_document: configurationDocument,
          },
        ]) as never
      );
    post
      .mockResolvedValueOnce(
        detail({ valid: true, normalized_document: configurationDocument, changes: [] }) as never
      )
      .mockResolvedValueOnce(detail(configurationDetail) as never);

    await expect(hrService.getDepartmentHierarchy("department-1", true)).resolves.toMatchObject({
      data: [{ id: "department-1", children: [] }],
    });
    const hierarchyUrl = get.mock.calls[0]?.[0] ?? "";
    expect(hierarchyUrl).toContain("root_id=department-1");
    expect(hierarchyUrl).toContain("include_inactive=true");
    await expect(hrService.getReportingTree("employee-1", 3)).resolves.toMatchObject({
      data: { id: "employee-1", direct_reports: [] },
    });
    await expect(hrService.getHealth()).resolves.toMatchObject({ data: { status: "healthy" } });
    await expect(hrService.getConfigurationHistory()).resolves.toMatchObject({
      items: [expect.objectContaining({ version: 2 })],
    });
    await expect(hrService.exportConfiguration()).resolves.toMatchObject({
      data: { schema: "saraise.human_resources.configuration" },
    });
    await expect(hrService.getConfigurationAudit()).resolves.toMatchObject({
      items: [expect.objectContaining({ id: "audit-1" })],
    });
    await expect(
      hrService.previewConfiguration({
        environment: "default",
        document: configurationDocument as never,
        change_reason: "Preview tenant controls",
      })
    ).resolves.toMatchObject({
      data: { valid: true },
    });
    await expect(
      hrService.importConfiguration({
        environment: "default",
        document: configurationDocument as never,
        change_reason: "Import tenant controls",
        idempotency_key: "config-import",
      })
    ).resolves.toMatchObject({ data: { id: "config-1" } });
    expect(post).toHaveBeenLastCalledWith(
      ENDPOINTS.CONFIGURATION.IMPORT,
      {
        environment: "default",
        document: configurationDocument as never,
        change_reason: "Import tenant controls",
        idempotency_key: "config-import",
      },
      { headers: { "Idempotency-Key": "config-import" } }
    );
  });
  it("normalizes governed conflicts with stable code and correlation ID", async () => {
    vi.spyOn(apiClient, "patch").mockRejectedValueOnce(
      new ApiError("Allocation changed", 409, {}, "version_conflict", "corr-conflict")
    );
    const failure = await hrService
      .updateLeaveBalance("balance-1", {
        entitled_days: "12",
        carried_days: "1",
        expected_version: 2,
        note: "Annual review",
      })
      .catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(HrApiError);
    expect(failure).toMatchObject({
      kind: "conflict",
      code: "version_conflict",
      correlationId: "corr-conflict",
    });
  });
  it("normalizes DRF field maps and optional field-error arrays", () => {
    const mapping = new HrApiError("Invalid", "validation", 400, "validation_error", "corr-map", {
      error: { detail: { employee_id: ["Select an employee."], reason: "Required." } },
    });
    expect(fieldErrors(mapping)).toEqual({
      employee_id: "Select an employee.",
      reason: "Required.",
    });
    const array = new HrApiError("Invalid", "validation", 400, "validation_error", "corr-array", {
      error: {
        detail: { field_errors: [{ field: "note", message: "A correction note is required." }] },
      },
    });
    expect(fieldErrors(array)).toEqual({ note: "A correction note is required." });
    expect(fieldErrors(new Error("not governed"))).toEqual({});
    expect(
      fieldErrors(
        new HrApiError("Invalid", "validation", 400, "validation_error", "corr-empty", {
          error: { detail: { field_errors: [{ field: "ignored" }, { message: "ignored" }] } },
        })
      )
    ).toEqual({});
    expect(
      fieldErrors(
        new HrApiError("Invalid", "validation", 400, "validation_error", "corr-mixed", {
          error: { detail: { employee_id: [42, "Select an employee."] } },
        })
      )
    ).toEqual({ employee_id: "Select an employee." });
    expect(
      fieldErrors(
        new HrApiError("Invalid", "validation", 400, "validation_error", "corr-no-detail", {
          error: { detail: null },
        })
      )
    ).toEqual({});
    expect(
      fieldErrors(
        new HrApiError("Invalid", "validation", 400, "validation_error", "corr-no-error", {
          error: null,
        })
      )
    ).toEqual({});
    expect(
      fieldErrors(
        new HrApiError("Invalid", "validation", 400, "validation_error", "corr-empty-array", {
          error: { detail: { employee_id: [42, false] } },
        })
      )
    ).toEqual({});
    expect(
      fieldErrors(
        new HrApiError("Invalid", "validation", 400, "validation_error", "corr-field-errors", {
          error: { detail: { field_errors: "not-array", reason: "Required." } },
        })
      )
    ).toEqual({ reason: "Required." });
    expect(
      fieldErrors(
        new HrApiError("Invalid", "validation", 400, "validation_error", "corr-array-empty", {
          error: { detail: { reason: [] } },
        })
      )
    ).toEqual({});
  });

  it("persists, clears, and falls back when creating intent keys", () => {
    sessionStorage.clear();
    const randomUUID = vi
      .spyOn(crypto, "randomUUID")
      .mockReturnValueOnce("11111111-1111-4111-8111-111111111111");

    expect(persistentIntentKey("leave-request")).toBe("11111111-1111-4111-8111-111111111111");
    expect(persistentIntentKey("leave-request")).toBe("11111111-1111-4111-8111-111111111111");
    clearIntentKey("leave-request");
    randomUUID.mockReturnValueOnce("22222222-2222-4222-8222-222222222222");
    expect(persistentIntentKey("leave-request")).toBe("22222222-2222-4222-8222-222222222222");

    randomUUID.mockRestore();
    const originalRandomUUID = crypto.randomUUID.bind(crypto);
    Object.defineProperty(crypto, "randomUUID", {
      configurable: true,
      value: undefined,
    });
    const now = vi.spyOn(Date, "now").mockReturnValue(12345);
    const random = vi.spyOn(Math, "random").mockReturnValue(0.5);

    expect(newIntentKey()).toBe("12345-8");

    now.mockRestore();
    random.mockRestore();
    Object.defineProperty(crypto, "randomUUID", {
      configurable: true,
      value: originalRandomUUID,
    });
  });
});
