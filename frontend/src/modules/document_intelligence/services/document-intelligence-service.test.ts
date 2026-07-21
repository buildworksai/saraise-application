import { ApiError, apiClient } from '@/services/api-client';
import { DocumentIntelligenceApiError, documentIntelligenceService } from './document-intelligence-service';
import type { ApiV2Envelope, ApiV2PaginatedEnvelope, DocumentExtractionListItem, ModuleHealth } from '../contracts';

const meta = { correlation_id: 'corr-1', timestamp: '2026-07-21T10:00:00Z' };

describe('document intelligence v2 service', () => {
  afterEach(() => vi.restoreAllMocks());

  it('unwraps governed data without synthesizing health', async () => {
    const health: ModuleHealth = { status: 'healthy', live: true, ready: true, checked_at: meta.timestamp, dependencies: [] };
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: health, meta } satisfies ApiV2Envelope<ModuleHealth>);
    await expect(documentIntelligenceService.getHealth()).resolves.toEqual(health);
  });

  it('passes bounded server filters through URLSearchParams', async () => {
    const envelope: ApiV2PaginatedEnvelope<DocumentExtractionListItem> = { data: [], meta: { ...meta, pagination: { count: 0, page: 2, page_size: 25, total_pages: 0, has_next: false, has_previous: true } } };
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue(envelope);
    await documentIntelligenceService.listExtractions({ page: 2, status: 'needs_review', engine: 'tesseract', confidence_min: '0.8000', ordering: '-created_at' });
    expect(get).toHaveBeenCalledWith(expect.stringContaining('page=2'));
    expect(get).toHaveBeenCalledWith(expect.stringContaining('status=needs_review'));
    expect(get).toHaveBeenCalledWith(expect.stringContaining('confidence_min=0.8000'));
  });

  it('normalizes nested v2 failures with correlation and quota detail', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError('failed', 429, { error: { code: 'quota_exhausted', message: 'Quota exhausted', detail: { quota: { resource: 'pages', remaining: 0, reset_at: null } }, correlation_id: 'corr-quota' } }));
    const error = await documentIntelligenceService.getHealth().catch((failure: unknown) => failure);
    expect(error).toBeInstanceOf(DocumentIntelligenceApiError);
    if (!(error instanceof DocumentIntelligenceApiError)) throw new Error('Expected normalized module error');
    expect(error.code).toBe('quota_exhausted');
    expect(error.correlationId).toBe('corr-quota');
    expect(error.detail.quota?.remaining).toBe(0);
  });
});
