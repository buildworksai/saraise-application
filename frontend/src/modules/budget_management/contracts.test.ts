import { describe, expect, it } from 'vitest';
import { ENDPOINTS, MODULE_API_PREFIX, withQuery } from './contracts';

describe('budget management v2 contracts', () => {
  it('publishes the single governed v2 authority', () => {
    expect(MODULE_API_PREFIX).toBe('/api/v2/budget-management');
    expect(ENDPOINTS.BUDGETS.LIST).toBe('/api/v2/budget-management/budgets/');
    expect(ENDPOINTS.BUDGETS.ALLOCATIONS('b1')).toBe('/api/v2/budget-management/budgets/b1/allocations/');
    expect(ENDPOINTS.BUDGETS.SUBMIT('b1')).toBe('/api/v2/budget-management/budgets/b1/submit/');
    expect(ENDPOINTS.BUDGETS.APPROVE('b1')).toBe('/api/v2/budget-management/budgets/b1/approve/');
    expect(ENDPOINTS.BUDGETS.REJECT('b1')).toBe('/api/v2/budget-management/budgets/b1/reject/');
    expect(ENDPOINTS.BUDGETS.REVISE('b1')).toBe('/api/v2/budget-management/budgets/b1/revise/');
    expect(ENDPOINTS.BUDGETS.CLOSE('b1')).toBe('/api/v2/budget-management/budgets/b1/close/');
    expect(ENDPOINTS.BUDGETS.VARIANCE('b1')).toBe('/api/v2/budget-management/budgets/b1/variance/');
    expect(ENDPOINTS.BUDGETS.SYNC_ACTUALS('b1')).toBe('/api/v2/budget-management/budgets/b1/sync-actuals/');
    expect(ENDPOINTS.APPROVALS.LIST).toBe('/api/v2/budget-management/approvals/');
    expect(ENDPOINTS.VARIANCE_ALERTS.GENERATE).toBe('/api/v2/budget-management/variance-alerts/generate/');
    expect(ENDPOINTS.AVAILABILITY).toBe('/api/v2/budget-management/availability/');
    expect(ENDPOINTS.HEALTH).toBe('/api/v2/budget-management/health/');
  });
  it('serializes only supplied filter values', () => { expect(withQuery(ENDPOINTS.BUDGETS.LIST, { page: 2, search: 'ops', status: undefined })).toBe(`${ENDPOINTS.BUDGETS.LIST}?page=2&search=ops`); });
});
