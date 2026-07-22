/* eslint-disable @typescript-eslint/unbound-method */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiClient } from '@/services/api-client';
import type { AssetCategory, PaginatedEnvelope } from '../contracts';
import { ENDPOINTS } from '../contracts';
import { createIdempotencyKey, fixedAssetQueryKeys, fixedAssetsService, shouldPollJob } from './fixed-assets-service';

vi.mock('@/services/api-client', () => ({
  ApiError: class ApiError extends Error {
    constructor(message: string, readonly status: number, readonly details?: unknown, readonly code?: string, readonly correlationId?: string) { super(message); }
  },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const pagination = { page: 1, page_size: 25, total_pages: 1, count: 1, has_next: false, has_previous: false } as const;
const category: AssetCategory = { id: 'category-1', code: 'EQUIPMENT', name: 'Equipment', description: '', default_depreciation_method: 'straight_line', default_useful_life_months: 60, default_residual_value_percent: '0.00', default_declining_balance_rate: null, asset_account_id: null, accumulated_depreciation_account_id: null, depreciation_expense_account_id: null, impairment_loss_account_id: null, disposal_gain_account_id: null, disposal_loss_account_id: null, is_active: true, version: 1, created_at: '2026-07-22T00:00:00Z', updated_at: '2026-07-22T00:00:00Z' };
const envelope: PaginatedEnvelope<AssetCategory> = { data: [category], meta: { correlation_id: 'corr-list', timestamp: '2026-07-22T00:00:00Z', pagination } };

describe('fixed assets service', () => {
  beforeEach(() => vi.clearAllMocks());

  it('unwraps the governed collection once and retains pagination', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope);
    await expect(fixedAssetsService.listCategories({ search: 'plant & machinery', page: 1 })).resolves.toEqual({ items: [category], pagination, correlationId: 'corr-list' });
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.CATEGORIES.LIST}?search=plant+%26+machinery&page=1`);
  });

  it('rejects malformed list responses rather than fabricating an empty list', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: { correlation_id: 'corr-bad', timestamp: '2026-07-22T00:00:00Z' } });
    await expect(fixedAssetsService.listCategories()).rejects.toMatchObject({ code: 'MALFORMED_RESPONSE', correlationId: 'corr-bad' });
  });

  it('propagates stable governed field and domain errors', async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new ApiError('Invalid category', 422, { error: { code: 'VALIDATION_ERROR', message: 'Invalid category', correlation_id: 'corr-error', field_errors: [{ field: 'code', code: 'duplicate', message: 'Code is in use' }] } }));
    await expect(fixedAssetsService.createCategory({ code: 'EQUIPMENT', name: 'Equipment', default_depreciation_method: 'straight_line', default_useful_life_months: 60, default_residual_value_percent: '0.00' }, 'category-key')).rejects.toMatchObject({ status: 422, code: 'VALIDATION_ERROR', correlationId: 'corr-error', fieldErrors: [{ field: 'code', code: 'duplicate' }] });
  });

  it('sends idempotency keys on lifecycle commands', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 'asset-1' }, meta: { correlation_id: 'corr-action', timestamp: '2026-07-22T00:00:00Z' } });
    await fixedAssetsService.capitalize('asset-1', { effective_date: '2026-07-22', expected_version: 2 }, 'capitalize-key');
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.ASSETS.CAPITALIZE('asset-1'), { effective_date: '2026-07-22', expected_version: 2 }, { headers: { 'Idempotency-Key': 'capitalize-key' } });
  });

  it('keeps cache keys tenant-qualified and polls only intermediate jobs', () => {
    expect(fixedAssetQueryKeys.asset('tenant-a', 'asset-1')).not.toEqual(fixedAssetQueryKeys.asset('tenant-b', 'asset-1'));
    expect(shouldPollJob({ status: 'queued' } as never)).toBe(true);
    expect(shouldPollJob({ status: 'running' } as never)).toBe(true);
    expect(shouldPollJob({ status: 'retrying' } as never)).toBe(false);
    expect(shouldPollJob({ status: 'failed' } as never)).toBe(false);
    expect(createIdempotencyKey('transfer')).toMatch(/^transfer:/u);
  });
});
