/* eslint-disable @typescript-eslint/unbound-method */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import { ComplianceRiskApiError, complianceRiskQueryKeys, complianceRiskService as service } from './compliance-risk-service';

vi.mock('@/services/api-client', () => {
  class ApiError extends Error { constructor(message: string, public status: number, public details?: unknown, public code?: string, public correlationId?: string) { super(message); } }
  return { ApiError, apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const meta = { correlation_id: 'corr-1', timestamp: '2026-07-23T00:00:00Z', pagination: { page: 1, page_size: 25, count: 0, total_pages: 0, has_next: false, has_previous: false } };

describe('compliance risk service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('unwraps only governed paginated envelopes and URL-encodes typed filters', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta });
    await expect(service.listRisks({ search: 'policy & audit', status: 'assessed', page: 2, page_size: 50 })).resolves.toMatchObject({ items: [], correlation_id: 'corr-1' });
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.RISKS.LIST}?search=policy+%26+audit&status=assessed&page=2&page_size=50`);
  });

  it('rejects a fabricated collection without governed pagination', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: { correlation_id: 'corr-2', timestamp: meta.timestamp } });
    await expect(service.listControls()).rejects.toMatchObject({ code: 'INVALID_RESPONSE', correlationId: 'corr-2' });
  });

  it('preserves status, stable code, correlation ID, and detail', async () => {
    const { ApiError } = await import('@/services/api-client');
    vi.mocked(apiClient.get).mockRejectedValue(new ApiError('Dependency unavailable', 503, { error: { detail: 'safe' } }, 'CAPABILITY_UNAVAILABLE', 'corr-503'));
    const failure = await service.getRisk('risk-id').catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ComplianceRiskApiError);
    expect(failure).toMatchObject({ status: 503, code: 'CAPABILITY_UNAVAILABLE', correlationId: 'corr-503' });
  });

  it('uses tenant-separated stable query keys including filters and page size', () => {
    expect(complianceRiskQueryKeys.risks('tenant-a', { page: 1, page_size: 25 })).not.toEqual(complianceRiskQueryKeys.risks('tenant-b', { page: 1, page_size: 25 }));
    expect(complianceRiskQueryKeys.risks('tenant-a', { page: 1, page_size: 25 })).not.toEqual(complianceRiskQueryKeys.risks('tenant-a', { page: 2, page_size: 100 }));
  });
});
