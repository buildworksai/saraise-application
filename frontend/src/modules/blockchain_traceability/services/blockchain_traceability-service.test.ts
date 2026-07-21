import { ApiError, apiClient } from '@/services/api-client';
import type { ApiV2Envelope, ApiV2PaginatedEnvelope, LedgerNetwork, QueuedAnchor, TraceabilityAsset } from '../contracts';
import { BlockchainTraceabilityApiError, assetQuery, blockchainTraceabilityService } from './blockchain_traceability-service';

const meta = { correlation_id: 'corr-1', timestamp: '2026-07-22T10:00:00Z' };
const pagination = { page: 2, page_size: 25, total_pages: 3, count: 52, has_next: true, has_previous: true };

describe('blockchain traceability v2 service', () => {
  afterEach(() => vi.restoreAllMocks());

  it('serializes filters with URLSearchParams and preserves page metadata', async () => {
    const envelope = { data: [], meta: { ...meta, pagination } } satisfies ApiV2PaginatedEnvelope<TraceabilityAsset>;
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue(envelope);
    await expect(blockchainTraceabilityService.listAssets({ page: 2, status: 'recalled', product_ref: 'A&B', ordering: '-created_at' })).resolves.toEqual({ items: [], pagination, correlationId: 'corr-1' });
    expect(get).toHaveBeenCalledWith('/api/v2/blockchain-traceability/assets/?page=2&ordering=-created_at&status=recalled&product_ref=A%26B');
    expect(assetQuery({ search: 'serial 1' })).toContain('search=serial+1');
  });

  it('uses PATCH for partial network updates', async () => {
    const network = { id: 'network-1' } as LedgerNetwork;
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ data: network, meta } satisfies ApiV2Envelope<LedgerNetwork>);
    await blockchainTraceabilityService.updateNetwork('network-1', { name: 'Primary' });
    expect(patch).toHaveBeenCalledWith('/api/v2/blockchain-traceability/networks/network-1/', { name: 'Primary' });
  });

  it('keeps accepted anchor work distinct from completed work', async () => {
    const accepted = { queued: true, anchor: { id: 'anchor-1', status: 'queued' }, job: { id: 'job-1', status: 'queued' } } as QueuedAnchor;
    vi.spyOn(apiClient, 'post').mockResolvedValue({ data: accepted, meta } satisfies ApiV2Envelope<QueuedAnchor>);
    const result = await blockchainTraceabilityService.requestAnchor({ asset_id: 'asset-1', network_id: 'network-1', start_sequence: 1, end_sequence: 3, idempotency_key: 'anchor-once' });
    expect(result.queued).toBe(true);
    expect(result.anchor.status).toBe('queued');
  });

  it('maps governed failures with field and correlation evidence', async () => {
    vi.spyOn(apiClient, 'post').mockRejectedValue(new ApiError('failed', 503, { error: { code: 'provider_unavailable', message: 'Provider unavailable', detail: { field_errors: [{ field: 'network_id', code: 'unavailable', message: 'Network unavailable' }] }, correlation_id: 'corr-provider' } }));
    const failure = await blockchainTraceabilityService.requestAnchor({ asset_id: 'asset-1', network_id: 'network-1', start_sequence: 1, end_sequence: 1, idempotency_key: 'once' }).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(BlockchainTraceabilityApiError);
    if (!(failure instanceof BlockchainTraceabilityApiError)) throw new Error('Expected governed module error');
    expect(failure.status).toBe(503);
    expect(failure.correlationId).toBe('corr-provider');
    expect(failure.fieldErrors.get('network_id')).toBe('Network unavailable');
  });
});
