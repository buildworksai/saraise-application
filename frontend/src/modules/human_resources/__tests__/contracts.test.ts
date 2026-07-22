import { describe, expect, it } from 'vitest';
import { ENDPOINTS, MODULE_API_PREFIX, ROUTES, hrKeys, isApiPageSuccess, isApiSuccess, withQuery } from '../contracts';
describe('Human Resources contracts', () => {
  it('constructs every action beneath the canonical v2 prefix', () => {
    const id = 'resource-id';
    const paths = [ENDPOINTS.DEPARTMENTS.LIST, ENDPOINTS.DEPARTMENTS.TREE, ENDPOINTS.DEPARTMENTS.DETAIL(id), ENDPOINTS.EMPLOYEES.REPORTING_TREE(id), ENDPOINTS.EMPLOYEES.ACTIVATE(id), ENDPOINTS.EMPLOYEES.DEACTIVATE(id), ENDPOINTS.EMPLOYEES.PLACE_ON_LEAVE(id), ENDPOINTS.EMPLOYEES.RETURN_FROM_LEAVE(id), ENDPOINTS.EMPLOYEES.TERMINATE(id), ENDPOINTS.ATTENDANCES.CLOCK_IN, ENDPOINTS.ATTENDANCES.CLOCK_OUT(id), ENDPOINTS.LEAVE_BALANCES.DETAIL(id), ENDPOINTS.LEAVE_REQUESTS.APPROVE(id), ENDPOINTS.LEAVE_REQUESTS.REJECT(id), ENDPOINTS.LEAVE_REQUESTS.CANCEL(id), ENDPOINTS.HEALTH];
    expect(paths.every((path) => path.startsWith(MODULE_API_PREFIX))).toBe(true);
    expect(ENDPOINTS.EMPLOYEES.PLACE_ON_LEAVE(id)).toContain('place-on-leave');
  });
  it('serializes only defined query values', () => {
    expect(withQuery(ENDPOINTS.EMPLOYEES.LIST, { page: 2, search: 'Ada Lovelace', department: undefined })).toContain('page=2');
    expect(withQuery(ENDPOINTS.EMPLOYEES.LIST, { page: 2, search: 'Ada Lovelace', department: undefined })).toContain('search=Ada+Lovelace');
    expect(withQuery(ENDPOINTS.EMPLOYEES.LIST, { department: undefined })).toBe(ENDPOINTS.EMPLOYEES.LIST);
  });
  it('strictly recognizes governed envelopes', () => {
    const meta = { correlation_id: 'corr-1', timestamp: '2026-07-22T00:00:00Z' };
    expect(isApiSuccess({ data: {}, meta })).toBe(true);
    expect(isApiPageSuccess({ data: [], meta: { ...meta, pagination: { count: 0, page: 1, page_size: 25, total_pages: 0, has_next: false, has_previous: false } } })).toBe(true);
    expect(isApiSuccess([])).toBe(false); expect(isApiPageSuccess({ results: [] })).toBe(false);
  });
  it('publishes stable route and query-key factories', () => {
    expect(ROUTES.EMPLOYEE_DETAIL('employee-id')).toBe(`${ROUTES.EMPLOYEES}/employee-id`);
    expect(hrKeys.employee('employee-id')).toEqual(['human-resources', 'employee', 'employee-id']);
  });
});
