import { beforeEach, describe, expect, it, vi } from 'vitest';
import { multiCompanyService } from './multi-company-service';

const clientMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('@/services/api-client', () => ({
  apiClient: clientMocks,
  ApiError: class ApiError extends Error {
    constructor(message: string, public status: number, public details?: unknown, public code?: string, public correlationId?: string) { super(message); }
  },
}));

const meta = { correlation_id: 'corr-1', timestamp: '2026-07-23T00:00:00Z' };

describe('multiCompanyService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('unwraps only governed paginated responses and preserves support metadata', async () => {
    clientMocks.get.mockResolvedValue({ data: [], meta: { ...meta, pagination: { count: 27, page: 2, page_size: 25, total_pages: 2, has_next: false, has_previous: true } } });
    const result = await multiCompanyService.listCompanies({ page: 2, search: 'ACME' });
    expect(clientMocks.get).toHaveBeenCalledWith('/api/v2/multi-company/companies/?page=2&search=ACME');
    expect(result.meta.correlation_id).toBe('corr-1');
    expect(result.pagination.count).toBe(27);
  });

  it('fails explicitly when a list response is malformed instead of fabricating an empty result', async () => {
    clientMocks.get.mockResolvedValue({ results: [] });
    await expect(multiCompanyService.listTransactions()).rejects.toMatchObject({ status: 502, code: 'INVALID_API_ENVELOPE' });
  });

  it('sends idempotency evidence for durable financial commands', async () => {
    clientMocks.post.mockResolvedValue({ data: { id: 'job-1' }, meta });
    await multiCompanyService.postTransaction('transaction-1', { expected_version: 4, transition_key: 'transition-1' }, 'idem-1');
    expect(clientMocks.post).toHaveBeenCalledWith('/api/v2/multi-company/transactions/transaction-1/post/', { expected_version: 4, transition_key: 'transition-1' }, { headers: { 'Idempotency-Key': 'idem-1' } });
  });
});
