import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ENDPOINTS } from '../contracts';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('@/services/api-client', () => ({
  apiClient: api,
  ApiError: class ApiError extends Error { constructor(message: string, public status: number) { super(message); } },
}));

import { IntegrationPlatformService } from '../services/integration-platform-service';

const meta = { correlation_id: 'corr-1', timestamp: '2026-07-22T00:00:00Z' };
const pagination = { count: 0, page: 2, page_size: 25, total_pages: 3, has_next: true, has_previous: true };

describe('IntegrationPlatformService', () => {
  const service = new IntegrationPlatformService();
  beforeEach(() => vi.clearAllMocks());

  it('serializes filters and flattens governed meta.pagination for pages', async () => {
    api.get.mockResolvedValue({ data: [], meta: { ...meta, pagination } });
    const result = await service.listIntegrations({ page: 2, status: 'active', search: 'ledger', ordering: '-updated_at' });
    expect(api.get).toHaveBeenCalledWith(`${ENDPOINTS.INTEGRATIONS.LIST}?page=2&search=ledger&status=active&ordering=-updated_at`);
    expect(result).toEqual({ items: [], meta: { ...pagination, ...meta } });
  });

  it('uses PATCH and unwraps the v2 envelope for updates', async () => {
    const integration = { id: 'integration-id', name: 'Warehouse' };
    api.patch.mockResolvedValue({ data: integration, meta });
    await expect(service.updateIntegration('integration-id', { name: 'Warehouse' })).resolves.toBe(integration);
    expect(api.patch).toHaveBeenCalledWith(ENDPOINTS.INTEGRATIONS.UPDATE('integration-id'), { name: 'Warehouse' });
  });

  it('returns durable receipts instead of discarding test and sync evidence', async () => {
    const receipt = { job_id: '68234291-2212-42e2-b236-fbc305e54a8e', status: 'queued', correlation_id: 'corr-1', accepted_at: meta.timestamp, poll_after_ms: 1000 };
    api.post.mockResolvedValue({ data: receipt, meta });
    await expect(service.testIntegration('integration-id', { idempotency_key: 'test-key' })).resolves.toBe(receipt);
    await expect(service.syncIntegration('integration-id', { direction: 'pull', mapping_ids: [], idempotency_key: 'sync-key' })).resolves.toBe(receipt);
    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.INTEGRATIONS.TEST('integration-id'), { idempotency_key: 'test-key' });
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.INTEGRATIONS.SYNC('integration-id'), { direction: 'pull', mapping_ids: [], idempotency_key: 'sync-key' });
  });

  it('never exposes a generic resource compatibility alias', () => {
    expect('listResources' in service).toBe(false);
    expect('createResource' in service).toBe(false);
  });

  it('preserves canonical inbound bytes and sends SARAISE signature headers', async () => {
    const receipt = { job_id: '68234291-2212-42e2-b236-fbc305e54a8e', correlation_id: 'corr-1', accepted_at: meta.timestamp };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: receipt, meta }), { status: 202, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const rawBody = '{"event":"invoice.created"}\n';
    await expect(service.receiveInboundWebhook('public-id', { timestamp: '1720000000', nonce: 'unique-nonce-1234', signature: `sha256=${'a'.repeat(64)}`, raw_body: rawBody })).resolves.toEqual(receipt);
    expect(fetchMock).toHaveBeenCalledWith(ENDPOINTS.WEBHOOKS.INBOUND('public-id'), expect.objectContaining({
      body: rawBody,
      headers: expect.objectContaining({
        'X-SARAISE-Webhook-Timestamp': '1720000000',
        'X-SARAISE-Webhook-Nonce': 'unique-nonce-1234',
        'X-SARAISE-Webhook-Signature': `sha256=${'a'.repeat(64)}`,
      }),
    }));
    vi.unstubAllGlobals();
  });
});
