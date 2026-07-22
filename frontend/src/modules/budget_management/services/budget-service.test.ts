import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/services/api-client';
import type * as ApiClientExports from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import { BudgetManagementApiError, budgetService } from './budget-service';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock('@/services/api-client', async (load) => { const actual = await load<typeof ApiClientExports>(); return { ...actual, apiClient: api }; });
const pagination = { page: 1, page_size: 25, count: 1, total_pages: 1, has_next: false, has_previous: false };
const meta = { correlation_id: 'corr-budget-1', timestamp: '2026-07-23T00:00:00Z', pagination };
const budget = { id: 'budget-1', budget_code: 'FY27', budget_name: 'Operations', fiscal_year: 2027, start_date: '2027-01-01', end_date: '2027-12-31', budget_type: 'operating', department_id: null, project_id: null, status: 'draft', currency: 'USD', budget_ceiling: '100.00', total_budget: '100.00', updated_at: '2026-07-23T00:00:00Z' };

describe('budgetService governed transport', () => {
  beforeEach(() => vi.clearAllMocks());
  it('preserves pagination and correlation evidence', async () => { api.get.mockResolvedValueOnce({ data: [budget], meta }); const result=await budgetService.listBudgets({search:'ops'}); expect(result.items).toEqual([budget]); expect(result.pagination).toEqual(pagination); expect(result.correlationId).toBe('corr-budget-1'); expect(api.get).toHaveBeenCalledWith(`${ENDPOINTS.BUDGETS.LIST}?search=ops`, {signal:undefined}); });
  it('moves transition idempotency into the required header', async () => { api.post.mockResolvedValueOnce({data:budget,meta}); await budgetService.submitBudget('budget-1',{idempotency_key:'submit:key',notes:'Ready'}); expect(api.post).toHaveBeenCalledWith(ENDPOINTS.BUDGETS.SUBMIT('budget-1'),{notes:'Ready'},{headers:{'Idempotency-Key':'submit:key'}}); });
  it('does not leak idempotency or unknown notes into rejection commands', async () => { api.post.mockResolvedValueOnce({data:budget,meta}); await budgetService.rejectBudget('budget-1',{idempotency_key:'reject:key',reason:'Revise dates',notes:'not sent'}); expect(api.post).toHaveBeenCalledWith(ENDPOINTS.BUDGETS.REJECT('budget-1'),{reason:'Revise dates'},{headers:{'Idempotency-Key':'reject:key'}}); });
  it('translates governed errors without losing evidence', async () => { api.get.mockRejectedValueOnce(new ApiError('Denied',403,{error:{fields:{status:['Denied']},retryable:false}},'POLICY_DENIED','corr-denied')); const error=await budgetService.getBudget('budget-1').catch((reason:unknown)=>reason); expect(error).toBeInstanceOf(BudgetManagementApiError); expect(error).toMatchObject({status:403,code:'POLICY_DENIED',correlationId:'corr-denied',fieldErrors:{status:['Denied']}}); });
});
