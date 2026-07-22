/** Strict, session-authenticated client for the governed HR v2 API. */
import { ApiError as ClientApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS, isApiPageSuccess, isApiSuccess, isAttendance, isDepartment, isEmployee,
  isLeaveBalance, isLeaveRequest, withQuery,
} from '../contracts';
import type {
  Attendance, AttendanceCreate, AttendanceFilters, AttendanceUpdate, ClockInPayload, ClockOutPayload,
  Department, DepartmentCreate, DepartmentFilters, DepartmentHierarchyNode, DepartmentUpdate,
  DetailResult, Employee, EmployeeCreate, EmployeeFilters, EmployeeLifecycleCommand,
  EmployeeLifecyclePayload, EmployeeReportingTreeNode, EmployeeTerminationPayload, EmployeeUpdate,
  HumanResourcesHealth, LeaveApprovalPayload, LeaveBalance, LeaveBalanceCreate, LeaveBalanceFilters,
  LeaveBalanceUpdate, LeaveCancellationPayload, LeaveRejectionPayload, LeaveRequest,
  LeaveRequestCreate, LeaveRequestFilters, LeaveRequestUpdate, PageResult,
} from '../contracts';

export type HrErrorKind = 'authentication' | 'permission' | 'not_found' | 'validation' | 'conflict'
  | 'rate_limit' | 'unavailable' | 'network' | 'invalid_response' | 'unexpected';

export class HrApiError extends Error {
  constructor(
    message: string,
    readonly kind: HrErrorKind,
    readonly status: number | null,
    readonly code: string,
    readonly correlationId: string | null,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = 'HrApiError';
  }
}

type Guard<T> = (value: unknown) => value is T;
const isObject = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const isHierarchy = (value: unknown): value is readonly DepartmentHierarchyNode[] =>
  Array.isArray(value) && value.every((node) => isObject(node) && typeof node.id === 'string' && Array.isArray(node.children));
const isReportingTree = (value: unknown): value is EmployeeReportingTreeNode =>
  isObject(value) && typeof value.id === 'string' && Array.isArray(value.direct_reports);
const isHealth = (value: unknown): value is HumanResourcesHealth =>
  isObject(value) && value.module === 'human_resources'
  && (value.status === 'healthy' || value.status === 'unhealthy')
  && typeof value.live === 'boolean' && typeof value.ready === 'boolean'
  && typeof value.checked_at === 'string' && isObject(value.checks);

function kindForStatus(status: number): HrErrorKind {
  if (status === 401) return 'authentication';
  if (status === 403) return 'permission';
  if (status === 404) return 'not_found';
  if (status === 400 || status === 422) return 'validation';
  if (status === 409) return 'conflict';
  if (status === 429) return 'rate_limit';
  if (status === 503) return 'unavailable';
  return 'unexpected';
}

async function governed<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (error instanceof HrApiError) throw error;
    if (error instanceof ClientApiError) {
      throw new HrApiError(error.message, kindForStatus(error.status), error.status,
        error.code ?? 'request_failed', error.correlationId ?? null, error.details);
    }
    if (error instanceof TypeError) {
      throw new HrApiError('Human Resources could not be reached. Check your connection and retry.',
        'network', null, 'network_error', null);
    }
    throw new HrApiError(error instanceof Error ? error.message : 'Unexpected Human Resources failure.',
      'unexpected', null, 'unexpected_error', null);
  }
}

function decode<T>(value: unknown, guard: Guard<T>, label: string): DetailResult<T> {
  if (!isApiSuccess(value) || !guard(value.data)) {
    throw new HrApiError(`Human Resources returned an invalid ${label} response.`, 'invalid_response',
      null, 'invalid_response', isApiSuccess(value) ? value.meta.correlation_id : null, value);
  }
  return {
    data: value.data,
    correlationId: value.meta.correlation_id,
    capabilities: value.meta.capabilities ?? [],
  };
}

function decodePage<T>(value: unknown, guard: Guard<T>, label: string): PageResult<T> {
  if (!isApiPageSuccess(value) || !value.data.every(guard)) {
    throw new HrApiError(`Human Resources returned an invalid ${label} page.`, 'invalid_response',
      null, 'invalid_response', isApiSuccess(value) ? value.meta.correlation_id : null, value);
  }
  return {
    items: value.data,
    pagination: value.meta.pagination,
    correlationId: value.meta.correlation_id,
    capabilities: value.meta.capabilities ?? [],
  };
}

const idempotency = (key: string): RequestInit => ({ headers: { 'Idempotency-Key': key } });
const employeeAction = (command: EmployeeLifecycleCommand, id: string): string => {
  const endpoints: Record<EmployeeLifecycleCommand, (employeeId: string) => string> = {
    activate: ENDPOINTS.EMPLOYEES.ACTIVATE,
    deactivate: ENDPOINTS.EMPLOYEES.DEACTIVATE,
    place_on_leave: ENDPOINTS.EMPLOYEES.PLACE_ON_LEAVE,
    return_from_leave: ENDPOINTS.EMPLOYEES.RETURN_FROM_LEAVE,
    terminate: ENDPOINTS.EMPLOYEES.TERMINATE,
  };
  return endpoints[command](id);
};

export const hrService = {
  listDepartments: (filters?: DepartmentFilters) => governed(async () =>
    decodePage(await apiClient.get(withQuery(ENDPOINTS.DEPARTMENTS.LIST, filters)), isDepartment, 'department')),
  getDepartment: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.DEPARTMENTS.DETAIL(id)), isDepartment, 'department')),
  createDepartment: (payload: DepartmentCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.DEPARTMENTS.CREATE, payload), isDepartment, 'department')),
  updateDepartment: (id: string, payload: DepartmentUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.DEPARTMENTS.UPDATE(id), payload), isDepartment, 'department')),
  deleteDepartment: (id: string) => governed(async () => { await apiClient.delete(ENDPOINTS.DEPARTMENTS.DELETE(id)); }),
  getDepartmentHierarchy: (rootId?: string, includeInactive = false) => governed(async () =>
    decode(await apiClient.get(withQuery(ENDPOINTS.DEPARTMENTS.TREE, { root_id: rootId, include_inactive: includeInactive })), isHierarchy, 'department hierarchy')),

  listEmployees: (filters?: EmployeeFilters) => governed(async () =>
    decodePage(await apiClient.get(withQuery(ENDPOINTS.EMPLOYEES.LIST, filters)), isEmployee, 'employee')),
  getEmployee: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.EMPLOYEES.DETAIL(id)), isEmployee, 'employee')),
  createEmployee: (payload: EmployeeCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.EMPLOYEES.CREATE, payload), isEmployee, 'employee')),
  updateEmployee: (id: string, payload: EmployeeUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.EMPLOYEES.UPDATE(id), payload), isEmployee, 'employee')),
  deleteEmployee: (id: string) => governed(async () => { await apiClient.delete(ENDPOINTS.EMPLOYEES.DELETE(id)); }),
  getReportingTree: (id: string, depth = 5) => governed(async () => decode(await apiClient.get(withQuery(ENDPOINTS.EMPLOYEES.REPORTING_TREE(id), { depth })), isReportingTree, 'reporting tree')),
  transitionEmployee: (id: string, command: EmployeeLifecycleCommand, payload: EmployeeLifecyclePayload | EmployeeTerminationPayload) => governed(async () =>
    decode(await apiClient.post(employeeAction(command, id), payload, idempotency(payload.transition_key)), isEmployee, 'employee transition')),

  listAttendances: (filters?: AttendanceFilters) => governed(async () =>
    decodePage(await apiClient.get(withQuery(ENDPOINTS.ATTENDANCES.LIST, filters)), isAttendance, 'attendance')),
  getAttendance: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.ATTENDANCES.DETAIL(id)), isAttendance, 'attendance')),
  createAttendance: (payload: AttendanceCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.ATTENDANCES.CREATE, payload), isAttendance, 'attendance')),
  updateAttendance: (id: string, payload: AttendanceUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.ATTENDANCES.UPDATE(id), payload), isAttendance, 'attendance')),
  deleteAttendance: (id: string) => governed(async () => { await apiClient.delete(ENDPOINTS.ATTENDANCES.DELETE(id)); }),
  clockIn: (payload: ClockInPayload) => governed(async () => decode(await apiClient.post(ENDPOINTS.ATTENDANCES.CLOCK_IN, payload, idempotency(payload.idempotency_key)), isAttendance, 'clock-in')),
  clockOut: (id: string, payload: ClockOutPayload) => governed(async () => decode(await apiClient.post(ENDPOINTS.ATTENDANCES.CLOCK_OUT(id), payload, idempotency(payload.idempotency_key)), isAttendance, 'clock-out')),

  listLeaveBalances: (filters?: LeaveBalanceFilters) => governed(async () =>
    decodePage(await apiClient.get(withQuery(ENDPOINTS.LEAVE_BALANCES.LIST, filters)), isLeaveBalance, 'leave balance')),
  getLeaveBalance: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.LEAVE_BALANCES.DETAIL(id)), isLeaveBalance, 'leave balance')),
  createLeaveBalance: (payload: LeaveBalanceCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.LEAVE_BALANCES.CREATE, payload), isLeaveBalance, 'leave balance')),
  updateLeaveBalance: (id: string, payload: LeaveBalanceUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.LEAVE_BALANCES.UPDATE(id), payload), isLeaveBalance, 'leave balance')),
  deleteLeaveBalance: (id: string) => governed(async () => { await apiClient.delete(ENDPOINTS.LEAVE_BALANCES.DELETE(id)); }),

  listLeaveRequests: (filters?: LeaveRequestFilters) => governed(async () =>
    decodePage(await apiClient.get(withQuery(ENDPOINTS.LEAVE_REQUESTS.LIST, filters)), isLeaveRequest, 'leave request')),
  getLeaveRequest: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.LEAVE_REQUESTS.DETAIL(id)), isLeaveRequest, 'leave request')),
  createLeaveRequest: (payload: LeaveRequestCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.LEAVE_REQUESTS.CREATE, payload, idempotency(payload.idempotency_key)), isLeaveRequest, 'leave request')),
  updateLeaveRequest: (id: string, payload: LeaveRequestUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.LEAVE_REQUESTS.UPDATE(id), payload), isLeaveRequest, 'leave request')),
  deleteLeaveRequest: (id: string, transitionKey: string) => governed(async () => { await apiClient.delete(ENDPOINTS.LEAVE_REQUESTS.DELETE(id), idempotency(transitionKey)); }),
  approveLeaveRequest: (id: string, payload: LeaveApprovalPayload) => governed(async () => decode(await apiClient.post(ENDPOINTS.LEAVE_REQUESTS.APPROVE(id), payload, idempotency(payload.transition_key)), isLeaveRequest, 'leave approval')),
  rejectLeaveRequest: (id: string, payload: LeaveRejectionPayload) => governed(async () => decode(await apiClient.post(ENDPOINTS.LEAVE_REQUESTS.REJECT(id), payload, idempotency(payload.transition_key)), isLeaveRequest, 'leave rejection')),
  cancelLeaveRequest: (id: string, payload: LeaveCancellationPayload) => governed(async () => decode(await apiClient.post(ENDPOINTS.LEAVE_REQUESTS.CANCEL(id), payload, idempotency(payload.transition_key)), isLeaveRequest, 'leave cancellation')),

  getHealth: () => governed(async () => decode(await apiClient.get(ENDPOINTS.HEALTH), isHealth, 'health')),
};

export function newIntentKey(): string {
  return typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function persistentIntentKey(name: string): string {
  const storageKey = `saraise:hr:intent:${name}`;
  const existing = sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const created = newIntentKey(); sessionStorage.setItem(storageKey, created); return created;
}

export function clearIntentKey(name: string): void {
  sessionStorage.removeItem(`saraise:hr:intent:${name}`);
}

export function fieldErrors(error: unknown): Readonly<Record<string, string>> {
  if (!(error instanceof HrApiError) || !isObject(error.details)) return {};
  const envelope = isObject(error.details.error) ? error.details.error : null;
  const detail = envelope && isObject(envelope.detail) ? envelope.detail : null;
  const errors = detail?.field_errors;
  if (Array.isArray(errors)) {
    return errors.reduce<Record<string, string>>((result, item) => {
      if (isObject(item) && typeof item.field === 'string' && typeof item.message === 'string') result[item.field] = item.message;
      return result;
    }, {});
  }
  if (!detail) return {};
  return Object.entries(detail).reduce<Record<string, string>>((result, [field, value]) => {
    if (field === 'field_errors') return result;
    if (typeof value === 'string') result[field] = value;
    else if (Array.isArray(value)) {
      const firstMessage = value.find((entry): entry is string => typeof entry === 'string');
      if (firstMessage) result[field] = firstMessage;
    }
    return result;
  }, {});
}

export type { Attendance, Department, Employee, LeaveBalance, LeaveRequest };
