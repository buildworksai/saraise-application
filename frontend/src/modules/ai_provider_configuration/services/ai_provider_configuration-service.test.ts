import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import { aiProviderConfigurationService, normalizeList } from './ai_provider_configuration-service';

/* API client methods are intentionally passed to Vitest's mock assertions. */
/* eslint-disable @typescript-eslint/unbound-method */

vi.mock('@/services/api-client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

describe('aiProviderConfigurationService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('normalizes plain and DRF-paginated lists', () => {
    expect(normalizeList([1, 2])).toEqual([1, 2]);
    expect(normalizeList({ count: 1, next: null, previous: null, results: [3] })).toEqual([3]);
  });

  it('uses endpoint registry paths and encodes filters', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    await aiProviderConfigurationService.listModels({ provider_id: 'provider with spaces', search: 'vision & tools' });
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.MODELS.LIST}?provider_id=provider+with+spaces&search=vision+%26+tools`);
  });

  it('uses explicit deployment lifecycle endpoints for status transitions', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({});
    await aiProviderConfigurationService.deactivateDeployment('deployment-1');
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.DEPLOYMENTS.DEACTIVATE('deployment-1'));
  });
});
