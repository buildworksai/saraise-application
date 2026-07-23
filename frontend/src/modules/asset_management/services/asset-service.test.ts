/* eslint-disable @typescript-eslint/unbound-method */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiClient } from '@/services/api-client';
import { ENDPOINTS, type Asset, type DepreciationEntry } from '../contracts';
import { AssetManagementApiError, assetQueryKeys, assetService } from './asset-service';

vi.mock('@/services/api-client', () => ({
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      readonly status: number,
      readonly details?: unknown,
      readonly code?: string,
      readonly correlationId?: string,
    ) {
      super(message);
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const asset: Asset = {
  id: '00000000-0000-4000-8000-000000000001',
  asset_code: 'LAP-001',
  asset_name: 'Design laptop',
  category: 'fixed',
  purchase_date: '2026-01-01',
  purchase_cost: '1200.00',
  residual_value: '120.00',
  current_value: '1110.00',
  depreciation_method: 'straight_line',
  useful_life_years: 3,
  declining_balance_rate: null,
  location: 'Studio',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
};

const entry: DepreciationEntry = {
  id: '00000000-0000-4000-8000-000000000002',
  asset: asset.id,
  asset_code: asset.asset_code,
  asset_name: asset.asset_name,
  entry_date: '2026-02-01',
  depreciation_amount: '30.00',
  accumulated_depreciation: '90.00',
  book_value: '1110.00',
  created_at: '2026-02-01T00:00:00Z',
};

describe('asset management service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('retains pagination and safely encodes collection filters', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [asset],
    });

    await expect(assetService.listAssets({ search: 'plant & studio', is_active: false, page: 2 }))
      .resolves.toEqual({ items: [asset], count: 1, next: null, previous: null });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.ASSETS.LIST}?search=plant+%26+studio&is_active=false&page=2`,
    );
  });

  it('rejects malformed records instead of fabricating an empty success', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ count: 1, next: null, previous: null, results: [{}] });
    await expect(assetService.listAssets()).rejects.toMatchObject({
      status: 502,
      code: 'MALFORMED_RESPONSE',
    });
  });

  it('maps governed field errors and correlation evidence', async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new ApiError(
      'Validation failed',
      400,
      { error: { field_errors: { asset_code: ['This code is already in use.'] } } },
      'VALIDATION_ERROR',
      'corr-asset-1',
    ));

    await expect(assetService.createAsset({} as never)).rejects.toEqual(expect.objectContaining({
      status: 400,
      code: 'VALIDATION_ERROR',
      correlationId: 'corr-asset-1',
      fieldErrors: { asset_code: 'This code is already in use.' },
    }));
  });

  it('uses the command endpoint and validates depreciation results', async () => {
    vi.mocked(apiClient.post).mockResolvedValue(entry);
    await expect(assetService.calculateDepreciation(asset.id, { entry_date: entry.entry_date }))
      .resolves.toEqual(entry);
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.ASSETS.CALCULATE_DEPRECIATION(asset.id),
      { entry_date: entry.entry_date },
    );
  });

  it('keeps every cache key tenant-qualified', () => {
    expect(assetQueryKeys.assets('tenant-a')).not.toEqual(assetQueryKeys.assets('tenant-b'));
    expect(assetQueryKeys.asset('tenant-a', asset.id)).not.toEqual(
      assetQueryKeys.asset('tenant-b', asset.id),
    );
    expect(new AssetManagementApiError('Unavailable', 503, 'UNAVAILABLE', null)).toMatchObject({
      status: 503,
      code: 'UNAVAILABLE',
    });
  });
});
