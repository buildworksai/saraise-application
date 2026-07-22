/* eslint-disable @typescript-eslint/unbound-method -- Vitest replaces and inspects singleton client methods intentionally. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import { ComplianceContractError, complianceService, serializeQuery } from '../services/compliance-service';

vi.mock('@/services/api-client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));
const meta = { correlation_id: '8ca11dd6-1d4b-45eb-b9e6-9889df6be4df', timestamp: '2026-07-23T00:00:00Z' };

describe('compliance service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('preserves pagination metadata and serializes typed filters', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: { ...meta, pagination: { page: 2, page_size: 25, count: 30, total_pages: 2, has_next: false, has_previous: true } } });
    const result = await complianceService.policies.list({ page: 2, status: 'draft', search: 'privacy' });
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.POLICIES.LIST}?page=2&status=draft&search=privacy`);
    expect(result.meta.pagination.count).toBe(30);
  });

  it('rejects malformed responses instead of fabricating an empty list', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ results: [] });
    await expect(complianceService.frameworks.list()).rejects.toBeInstanceOf(ComplianceContractError);
  });

  it('sends the transition key as the Idempotency-Key header', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 'policy-1' }, meta });
    await complianceService.policies.transition('policy-1', 'submit', { transition_key: 'transition-1' });
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.POLICIES.SUBMIT('policy-1'), { transition_key: 'transition-1' }, { headers: { 'Idempotency-Key': 'transition-1' } });
  });

  it('omits blank query values deterministically', () => {
    expect(serializeQuery('/items/', { search: '', page: 1, status: undefined })).toBe('/items/?page=1');
  });
});
