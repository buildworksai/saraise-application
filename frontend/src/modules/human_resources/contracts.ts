/** Human Resources v2 wire contract. DTOs, routes, endpoints, and query keys live here. */

export type UUID = string;
export type ISODate = string;
export type ISODateTime = string;
export type DecimalString = string;
export type SortDirection = '' | '-';

export type EmploymentType = 'full_time' | 'part_time' | 'contractor' | 'temporary';
export type EmploymentStatus = 'active' | 'on_leave' | 'inactive' | 'terminated';
export type EmployeeLifecycleCommand =
  | 'activate'
  | 'deactivate'
  | 'place_on_leave'
  | 'return_from_leave'
  | 'terminate';
export type AttendanceStatus = 'present' | 'absent' | 'late' | 'half_day' | 'on_leave';
export type AttendanceSource = 'manual' | 'clock' | 'import';
export type LeaveType = 'annual' | 'sick' | 'personal' | 'maternity' | 'paternity' | 'unpaid';
export type LeaveRequestStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';
export type LeaveWorkspaceScope = 'all' | 'self' | 'team' | 'approval_queue';

export interface TransitionRecord {
  readonly transition_key: string;
  readonly command: string;
  readonly from_state: string;
  readonly to_state: string;
  readonly occurred_at: ISODateTime;
  readonly metadata: Readonly<Record<string, string | boolean | null>>;
}

export interface AuditFields {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly created_by: string;
  readonly updated_by: string;
  readonly deleted_at: ISODateTime | null;
  readonly deleted_by: string;
}

export interface Department extends AuditFields {
  readonly department_code: string;
  readonly department_name: string;
  readonly parent_department: UUID | null;
  readonly parent_department_name: string | null;
  readonly manager: UUID | null;
  readonly manager_name: string | null;
  readonly is_active: boolean;
  readonly description: string;
}
export type DepartmentList = Department;
export type DepartmentDetail = Department;
export interface DepartmentCreate {
  department_code: string;
  department_name: string;
  parent_department_id?: UUID | null;
  manager_id?: UUID | null;
  description?: string;
}
export type DepartmentUpdate = Partial<DepartmentCreate> & { is_active?: boolean };
export interface DepartmentHierarchyNode {
  readonly id: UUID;
  readonly department_code: string;
  readonly department_name: string;
  readonly manager: UUID | null;
  readonly manager_name: string | null;
  readonly is_active: boolean;
  readonly children: readonly DepartmentHierarchyNode[];
}

export interface Employee extends AuditFields {
  readonly employee_number: string;
  readonly first_name: string;
  readonly last_name: string;
  readonly full_name: string;
  readonly email: string;
  readonly phone: string;
  readonly department: UUID | null;
  readonly department_name: string | null;
  readonly manager: UUID | null;
  readonly manager_name: string | null;
  readonly position: string;
  readonly hire_date: ISODate;
  readonly employment_type: EmploymentType;
  readonly employment_status: EmploymentStatus;
  readonly is_active: boolean;
  readonly termination_date: ISODate | null;
  readonly termination_reason: string;
  readonly transition_history: readonly TransitionRecord[];
}
export type EmployeeList = Omit<Employee, 'transition_history' | 'termination_reason'>;
export type EmployeeDetail = Employee;
export interface EmployeeCreate {
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  department_id?: UUID | null;
  manager_id?: UUID | null;
  position?: string;
  hire_date: ISODate;
  employment_type: EmploymentType;
}
export type EmployeeUpdate = Partial<EmployeeCreate>;
export interface EmployeeLifecyclePayload {
  transition_key: string;
  effective_date?: ISODate;
  reason?: string;
}
export interface EmployeeTerminationPayload extends EmployeeLifecyclePayload {
  effective_date: ISODate;
  reason: string;
}
export interface EmployeeReportingTreeNode {
  readonly id: UUID;
  readonly employee_number: string;
  readonly full_name: string;
  readonly position: string;
  readonly employment_status: EmploymentStatus;
  readonly direct_reports: readonly EmployeeReportingTreeNode[];
}

export interface Attendance extends AuditFields {
  readonly employee: UUID;
  readonly employee_number: string;
  readonly employee_name: string;
  readonly attendance_date: ISODate;
  readonly check_in_time: ISODateTime | null;
  readonly check_out_time: ISODateTime | null;
  readonly hours_worked: DecimalString;
  readonly status: AttendanceStatus;
  readonly source: AttendanceSource;
  readonly notes: string;
}
export type AttendanceList = Attendance;
export type AttendanceDetail = Attendance;
export interface AttendanceCreate {
  employee_id: UUID;
  attendance_date: ISODate;
  check_in_time?: ISODateTime | null;
  check_out_time?: ISODateTime | null;
  status: AttendanceStatus;
  notes?: string;
}
export interface AttendanceUpdate {
  check_in_time?: ISODateTime | null;
  check_out_time?: ISODateTime | null;
  hours_worked?: DecimalString;
  status?: AttendanceStatus;
  notes: string;
}
export interface ClockInPayload { employee_id: UUID; occurred_at?: ISODateTime; idempotency_key: string }
export interface ClockOutPayload { occurred_at?: ISODateTime; idempotency_key: string }

export interface LeaveBalance extends AuditFields {
  readonly employee: UUID;
  readonly employee_number: string;
  readonly employee_name: string;
  readonly leave_type: LeaveType;
  readonly period_start: ISODate;
  readonly period_end: ISODate;
  readonly entitled_days: DecimalString;
  readonly carried_days: DecimalString;
  readonly used_days: DecimalString;
  readonly pending_days: DecimalString;
  readonly remaining_days: DecimalString;
  readonly adjustment_version: number;
  readonly last_adjusted_by: string;
  readonly adjustment_note: string;
}
export interface LeaveBalanceCreate {
  employee_id: UUID;
  leave_type: LeaveType;
  period_start: ISODate;
  period_end: ISODate;
  entitled_days: DecimalString;
  carried_days?: DecimalString;
}
export interface LeaveBalanceUpdate {
  entitled_days: DecimalString;
  carried_days: DecimalString;
  expected_version: number;
  note: string;
}

export interface LeaveRequest extends AuditFields {
  readonly employee: UUID;
  readonly employee_number: string;
  readonly employee_name: string;
  readonly leave_balance: UUID;
  readonly leave_type: LeaveType;
  readonly start_date: ISODate;
  readonly end_date: ISODate;
  readonly days_requested: DecimalString;
  readonly reason: string;
  readonly status: LeaveRequestStatus;
  readonly approved_by: string;
  readonly approved_at: ISODateTime | null;
  readonly rejection_reason: string;
  readonly cancelled_by: string;
  readonly cancelled_at: ISODateTime | null;
  readonly transition_history: readonly TransitionRecord[];
}
export type LeaveRequestList = Omit<LeaveRequest, 'transition_history'>;
export type LeaveRequestDetail = LeaveRequest;
export interface LeaveRequestCreate {
  employee_id: UUID;
  leave_balance_id: UUID;
  leave_type: LeaveType;
  start_date: ISODate;
  end_date: ISODate;
  reason?: string;
  idempotency_key: string;
}
export type LeaveRequestUpdate = Pick<LeaveRequestCreate, 'start_date' | 'end_date' | 'reason'>;
export interface LeaveApprovalPayload { transition_key: string }
export interface LeaveRejectionPayload { transition_key: string; rejection_reason: string }
export interface LeaveCancellationPayload { transition_key: string }

export interface ApiPageMeta {
  readonly count: number;
  readonly page: number;
  readonly page_size: number;
  readonly total_pages: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}
export interface ApiResponseMeta {
  readonly correlation_id: string;
  readonly timestamp: ISODateTime;
  readonly capabilities?: readonly string[];
}
export interface ApiSuccess<T> { readonly data: T; readonly meta: ApiResponseMeta }
export interface ApiPageSuccess<T> {
  readonly data: readonly T[];
  readonly meta: ApiResponseMeta & { readonly pagination: ApiPageMeta };
}
export interface ApiFieldError { readonly field: string; readonly code: string; readonly message: string }
export interface ApiErrorDetail { readonly field_errors?: readonly ApiFieldError[]; readonly [key: string]: unknown }
export interface ApiError {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly detail: ApiErrorDetail | null;
    readonly correlation_id: string;
  };
}
export interface PageResult<T> {
  readonly items: readonly T[];
  readonly pagination: ApiPageMeta;
  readonly correlationId: string;
  readonly capabilities: readonly string[];
}
export interface DetailResult<T> {
  readonly data: T;
  readonly correlationId: string;
  readonly capabilities: readonly string[];
}

export interface PageQuery { page?: number; page_size?: number; search?: string }
export interface DepartmentFilters extends PageQuery {
  is_active?: boolean; parent_department?: UUID; manager?: UUID;
  ordering?: `${SortDirection}${'department_code' | 'department_name' | 'created_at'}`;
}
export interface EmployeeFilters extends PageQuery {
  department?: UUID; manager?: UUID; employment_type?: EmploymentType;
  employment_status?: EmploymentStatus; hire_date_from?: ISODate; hire_date_to?: ISODate;
  is_active?: boolean;
  ordering?: `${SortDirection}${'employee_number' | 'last_name' | 'hire_date' | 'created_at'}`;
}
export interface AttendanceFilters extends PageQuery {
  employee?: UUID; status?: AttendanceStatus; source?: AttendanceSource;
  attendance_date_from?: ISODate; attendance_date_to?: ISODate;
  ordering?: `${SortDirection}${'attendance_date' | 'hours_worked' | 'created_at'}`;
}
export interface LeaveBalanceFilters extends PageQuery {
  employee?: UUID; leave_type?: LeaveType; period_start?: ISODate; period_end?: ISODate;
  active_period?: boolean;
  ordering?: `${SortDirection}${'employee' | 'leave_type' | 'period_start' | 'remaining_days'}`;
}
export interface LeaveRequestFilters extends PageQuery {
  employee?: UUID; leave_type?: LeaveType; status?: LeaveRequestStatus;
  start_date?: ISODate; end_date?: ISODate; scope?: LeaveWorkspaceScope;
  ordering?: `${SortDirection}${'start_date' | 'days_requested' | 'status' | 'created_at'}`;
}

export interface HumanResourcesHealth {
  readonly module: 'human_resources';
  readonly status: 'healthy' | 'unhealthy';
  readonly live: boolean;
  readonly ready: boolean;
  readonly checked_at: ISODateTime;
  readonly checks: Readonly<Record<string, {
    readonly name: string;
    readonly status: 'healthy' | 'unhealthy';
    readonly code: string;
    readonly latency_ms: number;
    readonly critical: boolean;
  }>>;
}

export const MODULE_API_PREFIX = '/api/v2/human-resources';
export const MODULE_PATH = '/human-resources';

export const ENDPOINTS = {
  DEPARTMENTS: {
    LIST: `${MODULE_API_PREFIX}/departments/`, CREATE: `${MODULE_API_PREFIX}/departments/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/departments/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/departments/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/departments/${id}/` as const,
    TREE: `${MODULE_API_PREFIX}/departments/tree/`,
  },
  EMPLOYEES: {
    LIST: `${MODULE_API_PREFIX}/employees/`, CREATE: `${MODULE_API_PREFIX}/employees/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/employees/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/employees/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/employees/${id}/` as const,
    REPORTING_TREE: (id: UUID) => `${MODULE_API_PREFIX}/employees/${id}/reporting-tree/` as const,
    ACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/employees/${id}/activate/` as const,
    DEACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/employees/${id}/deactivate/` as const,
    PLACE_ON_LEAVE: (id: UUID) => `${MODULE_API_PREFIX}/employees/${id}/place-on-leave/` as const,
    RETURN_FROM_LEAVE: (id: UUID) => `${MODULE_API_PREFIX}/employees/${id}/return-from-leave/` as const,
    TERMINATE: (id: UUID) => `${MODULE_API_PREFIX}/employees/${id}/terminate/` as const,
  },
  ATTENDANCES: {
    LIST: `${MODULE_API_PREFIX}/attendances/`, CREATE: `${MODULE_API_PREFIX}/attendances/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/attendances/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/attendances/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/attendances/${id}/` as const,
    CLOCK_IN: `${MODULE_API_PREFIX}/attendances/clock-in/`,
    CLOCK_OUT: (id: UUID) => `${MODULE_API_PREFIX}/attendances/${id}/clock-out/` as const,
  },
  LEAVE_BALANCES: {
    LIST: `${MODULE_API_PREFIX}/leave-balances/`, CREATE: `${MODULE_API_PREFIX}/leave-balances/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/leave-balances/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/leave-balances/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/leave-balances/${id}/` as const,
  },
  LEAVE_REQUESTS: {
    LIST: `${MODULE_API_PREFIX}/leave-requests/`, CREATE: `${MODULE_API_PREFIX}/leave-requests/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/leave-requests/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/leave-requests/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/leave-requests/${id}/` as const,
    APPROVE: (id: UUID) => `${MODULE_API_PREFIX}/leave-requests/${id}/approve/` as const,
    REJECT: (id: UUID) => `${MODULE_API_PREFIX}/leave-requests/${id}/reject/` as const,
    CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/leave-requests/${id}/cancel/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTES = {
  OVERVIEW: MODULE_PATH,
  EMPLOYEES: `${MODULE_PATH}/employees`, EMPLOYEE_CREATE: `${MODULE_PATH}/employees/new`,
  EMPLOYEE_DETAIL: (id: UUID) => `${MODULE_PATH}/employees/${id}` as const,
  EMPLOYEE_EDIT: (id: UUID) => `${MODULE_PATH}/employees/${id}/edit` as const,
  DEPARTMENTS: `${MODULE_PATH}/departments`, DEPARTMENT_CREATE: `${MODULE_PATH}/departments/new`,
  DEPARTMENT_DETAIL: (id: UUID) => `${MODULE_PATH}/departments/${id}` as const,
  DEPARTMENT_EDIT: (id: UUID) => `${MODULE_PATH}/departments/${id}/edit` as const,
  ATTENDANCE: `${MODULE_PATH}/attendance`, ATTENDANCE_CREATE: `${MODULE_PATH}/attendance/new`,
  ATTENDANCE_DETAIL: (id: UUID) => `${MODULE_PATH}/attendance/${id}` as const,
  ATTENDANCE_EDIT: (id: UUID) => `${MODULE_PATH}/attendance/${id}/edit` as const,
  LEAVE: `${MODULE_PATH}/leave`, LEAVE_BALANCE_CREATE: `${MODULE_PATH}/leave/balances/new`,
  LEAVE_BALANCE_DETAIL: (id: UUID) => `${MODULE_PATH}/leave/balances/${id}` as const,
  LEAVE_BALANCE_EDIT: (id: UUID) => `${MODULE_PATH}/leave/balances/${id}/edit` as const,
  LEAVE_REQUEST_CREATE: `${MODULE_PATH}/leave/requests/new`,
  LEAVE_REQUEST_DETAIL: (id: UUID) => `${MODULE_PATH}/leave/requests/${id}` as const,
  LEAVE_REQUEST_EDIT: (id: UUID) => `${MODULE_PATH}/leave/requests/${id}/edit` as const,
} as const;

export const hrKeys = {
  all: ['human-resources'] as const,
  departments: (filters?: DepartmentFilters) => ['human-resources', 'departments', filters ?? {}] as const,
  department: (id: UUID) => ['human-resources', 'department', id] as const,
  hierarchy: (rootId?: UUID, includeInactive?: boolean) => ['human-resources', 'department-tree', rootId ?? '', includeInactive ?? false] as const,
  employees: (filters?: EmployeeFilters) => ['human-resources', 'employees', filters ?? {}] as const,
  employee: (id: UUID) => ['human-resources', 'employee', id] as const,
  reportingTree: (id: UUID, depth = 5) => ['human-resources', 'reporting-tree', id, depth] as const,
  attendances: (filters?: AttendanceFilters) => ['human-resources', 'attendances', filters ?? {}] as const,
  attendance: (id: UUID) => ['human-resources', 'attendance', id] as const,
  leaveBalances: (filters?: LeaveBalanceFilters) => ['human-resources', 'leave-balances', filters ?? {}] as const,
  leaveBalance: (id: UUID) => ['human-resources', 'leave-balance', id] as const,
  leaveRequests: (filters?: LeaveRequestFilters) => ['human-resources', 'leave-requests', filters ?? {}] as const,
  leaveRequest: (id: UUID) => ['human-resources', 'leave-request', id] as const,
  health: ['human-resources', 'health'] as const,
};

export function withQuery<T extends object>(endpoint: string, filters?: T): string {
  if (!filters) return endpoint;
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') parameters.set(key, String(value));
  });
  const query = parameters.toString();
  return query ? `${endpoint}?${query}` : endpoint;
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
export function isApiSuccess(value: unknown): value is ApiSuccess<unknown> {
  return object(value) && 'data' in value && object(value.meta)
    && typeof value.meta.correlation_id === 'string' && typeof value.meta.timestamp === 'string';
}
export function isApiPageSuccess(value: unknown): value is ApiPageSuccess<unknown> {
  if (!isApiSuccess(value) || !Array.isArray(value.data)) return false;
  const meta: unknown = value.meta;
  return object(meta) && object(meta.pagination) && typeof meta.pagination.count === 'number'
    && typeof meta.pagination.page === 'number' && typeof meta.pagination.page_size === 'number';
}
export function isDepartment(value: unknown): value is Department {
  return object(value) && typeof value.id === 'string' && typeof value.department_code === 'string'
    && typeof value.department_name === 'string' && typeof value.is_active === 'boolean';
}
export function isEmployee(value: unknown): value is Employee {
  return object(value) && typeof value.id === 'string' && typeof value.employee_number === 'string'
    && typeof value.first_name === 'string' && typeof value.last_name === 'string'
    && typeof value.employment_status === 'string';
}
export function isAttendance(value: unknown): value is Attendance {
  return object(value) && typeof value.id === 'string' && typeof value.employee === 'string'
    && typeof value.attendance_date === 'string' && typeof value.status === 'string';
}
export function isLeaveBalance(value: unknown): value is LeaveBalance {
  return object(value) && typeof value.id === 'string' && typeof value.employee === 'string'
    && typeof value.leave_type === 'string' && typeof value.remaining_days === 'string';
}
export function isLeaveRequest(value: unknown): value is LeaveRequest {
  return object(value) && typeof value.id === 'string' && typeof value.employee === 'string'
    && typeof value.leave_balance === 'string' && typeof value.status === 'string';
}
