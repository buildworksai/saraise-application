import { ApiError, apiClient } from '@/services/api-client';
import { ENDPOINTS, type ApiEnvelope, type Document, type DocumentSummary, type Folder } from '../contracts';
import { DMS_QUERY_KEYS, DmsApiError, dmsService, serializeDmsQuery } from './dms-service';

const pagination = { count: 1, page: 1, page_size: 25, total_pages: 1, has_next: false, has_previous: false } as const;
const meta = { correlation_id: 'corr-dms', timestamp: '2026-07-22T00:00:00Z', pagination } as const;
const version = { id: 'version-1', version_number: 1, original_filename: 'policy.pdf', mime_type: 'application/pdf', size_bytes: 42, checksum_sha256: 'a'.repeat(64), created_by: 'actor-1', created_at: '2026-07-22T00:00:00Z' } as const;
const document: Document = { id: 'document-1', name: 'Policy', description: '', folder_id: null, folder_name: null, tags: ['policy'], metadata: { department: 'legal' }, current_version: version, version_count: 1, created_by: 'actor-1', created_at: '2026-07-22T00:00:00Z', updated_at: '2026-07-22T00:00:00Z', allowed_actions: ['read', 'download', 'update'] };
const folder: Folder = { id: 'folder-1', name: 'Legal', description: '', parent_id: null, path: '/Legal', depth: 0, sort_order: 0, created_by: 'actor-1', created_at: '2026-07-22T00:00:00Z', updated_at: '2026-07-22T00:00:00Z', allowed_actions: ['read', 'update'] };

describe('dmsService', () => {
  afterEach(() => vi.restoreAllMocks());

  it('serializes bounded collection queries deterministically', () => {
    expect(serializeDmsQuery(ENDPOINTS.DOCUMENTS.LIST, { folder: 'folder-1', tags: ['legal', 'signed'], search: 'policy', ordering: '-updated_at', page: 2, page_size: 25 })).toBe('/api/v2/dms/documents/?folder=folder-1&search=policy&ordering=-updated_at&page=2&page_size=25&tags=legal&tags=signed');
  });

  it('unwraps governed pages and exports stable query keys', async () => {
    const response: ApiEnvelope<readonly DocumentSummary[]> = { data: [document], meta };
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue(response);
    await expect(dmsService.listDocuments({ page: 1 })).resolves.toEqual({ items: [document], pagination, correlation_id: 'corr-dms' });
    expect(get).toHaveBeenCalledWith(`${ENDPOINTS.DOCUMENTS.LIST}?page=1`);
    expect(DMS_QUERY_KEYS.documents({ page: 1 })).toEqual(['dms', 'documents', { page: 1 }]);
  });

  it('uses PATCH with optimistic concurrency and never PUT', async () => {
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ data: document, meta });
    await dmsService.updateDocument(document.id, { name: 'Policy 2026', expected_updated_at: document.updated_at });
    expect(patch).toHaveBeenCalledWith(ENDPOINTS.DOCUMENTS.UPDATE(document.id), { name: 'Policy 2026', expected_updated_at: document.updated_at });
  });

  it('delegates folder mutations to exact registry paths', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: folder, meta });
    await dmsService.createFolder({ name: 'Legal' });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.FOLDERS.CREATE, { name: 'Legal' });
  });

  it('normalizes governed denials into a discriminated module error', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError('Denied', 403, { error: { code: 'PERMISSION_DENIED', message: 'Denied', correlation_id: 'corr-denied' } }));
    const failure = await dmsService.getDocument('hidden').catch((error: Error) => error);
    expect(failure).toBeInstanceOf(DmsApiError);
    if (!(failure instanceof DmsApiError)) throw new Error('Expected normalized DMS error');
    expect(failure.problem).toEqual({ kind: 'denied', status: 403, message: 'Denied', correlation_id: 'corr-denied' });
  });
});
