import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import { HrApiError, fieldErrors, hrService } from '../services/hr-service';

const pagination = { count: 1, page: 1, page_size: 25, total_pages: 1, has_next: false, has_previous: false };
const meta = { correlation_id: 'corr-hr-1', timestamp: '2026-07-22T00:00:00Z' };
const page = (data: readonly unknown[]) => ({ data, meta: { ...meta, pagination, capabilities: ['hr.employee:create'] } });
const detail = (data: unknown) => ({ data, meta });
const employee = { id: 'employee-1', employee_number: 'EMP-1', first_name: 'Ada', last_name: 'Lovelace', employment_status: 'active' };
const department = { id: 'department-1', department_code: 'ENG', department_name: 'Engineering', is_active: true };
const attendance = { id: 'attendance-1', employee: 'employee-1', attendance_date: '2026-07-22', status: 'present' };
const balance = { id: 'balance-1', employee: 'employee-1', leave_type: 'annual', remaining_days: '10.00' };
const request = { id: 'request-1', employee: 'employee-1', leave_balance: 'balance-1', status: 'pending' };

describe('hrService', () => {
  afterEach(() => vi.restoreAllMocks());
  it('strictly decodes all five governed collections and preserves pagination/capabilities', async () => {
    const get = vi.spyOn(apiClient, 'get');
    get.mockResolvedValueOnce(page([department]) as never).mockResolvedValueOnce(page([employee]) as never).mockResolvedValueOnce(page([attendance]) as never).mockResolvedValueOnce(page([balance]) as never).mockResolvedValueOnce(page([request]) as never);
    expect((await hrService.listDepartments()).pagination.count).toBe(1);
    expect((await hrService.listEmployees()).capabilities).toContain('hr.employee:create');
    expect((await hrService.listAttendances()).items[0]?.id).toBe('attendance-1');
    expect((await hrService.listLeaveBalances()).items[0]?.id).toBe('balance-1');
    expect((await hrService.listLeaveRequests()).correlationId).toBe('corr-hr-1');
  });
  it('sends lifecycle and leave action idempotency keys in headers', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValueOnce(detail(employee) as never).mockResolvedValueOnce(detail(request) as never);
    await hrService.transitionEmployee('employee-1', 'deactivate', { transition_key: 'intent-1' });
    await hrService.approveLeaveRequest('request-1', { transition_key: 'intent-2' });
    expect(post).toHaveBeenNthCalledWith(1, ENDPOINTS.EMPLOYEES.DEACTIVATE('employee-1'), { transition_key: 'intent-1' }, { headers: { 'Idempotency-Key': 'intent-1' } });
    expect(post).toHaveBeenNthCalledWith(2, ENDPOINTS.LEAVE_REQUESTS.APPROVE('request-1'), { transition_key: 'intent-2' }, { headers: { 'Idempotency-Key': 'intent-2' } });
  });
  it('rejects raw and legacy list shapes instead of fabricating an empty success', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce([] as never);
    await expect(hrService.listEmployees()).rejects.toMatchObject({ kind: 'invalid_response', code: 'invalid_response' });
  });
  it('normalizes governed conflicts with stable code and correlation ID', async () => {
    vi.spyOn(apiClient, 'patch').mockRejectedValueOnce(new ApiError('Allocation changed', 409, {}, 'version_conflict', 'corr-conflict'));
    const failure = await hrService.updateLeaveBalance('balance-1', { entitled_days: '12', carried_days: '1', expected_version: 2, note: 'Annual review' }).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(HrApiError);
    expect(failure).toMatchObject({ kind: 'conflict', code: 'version_conflict', correlationId: 'corr-conflict' });
  });
  it('normalizes DRF field maps and optional field-error arrays', () => {
    const mapping = new HrApiError('Invalid', 'validation', 400, 'validation_error', 'corr-map', { error: { detail: { employee_id: ['Select an employee.'], reason: 'Required.' } } });
    expect(fieldErrors(mapping)).toEqual({ employee_id: 'Select an employee.', reason: 'Required.' });
    const array = new HrApiError('Invalid', 'validation', 400, 'validation_error', 'corr-array', { error: { detail: { field_errors: [{ field: 'note', message: 'A correction note is required.' }] } } });
    expect(fieldErrors(array)).toEqual({ note: 'A correction note is required.' });
  });
});
