import { ENDPOINTS, MODULE_API_PREFIX, ROUTES, type DocumentUpload } from './contracts';

describe('DMS v2 contracts', () => {
  it('owns only governed v2 API endpoints', () => {
    expect(MODULE_API_PREFIX).toBe('/api/v2/dms');
    expect(JSON.stringify(ENDPOINTS)).not.toContain('/api/v1/');
    expect(ENDPOINTS.FOLDERS.CONTENTS('folder id')).toBe('/api/v2/dms/folders/folder%20id/contents/');
    expect(ENDPOINTS.VERSIONS.RESTORE('version')).toBe('/api/v2/dms/document-versions/version/restore/');
    expect(ENDPOINTS.SHARES.REVOKE('share')).toBe('/api/v2/dms/document-shares/share/revoke/');
  });

  it('uses a browser File as upload input and exposes the seven canonical UI paths', () => {
    const request: DocumentUpload = { file: new File(['evidence'], 'evidence.txt'), name: 'Evidence' };
    expect(request.file).toBeInstanceOf(File);
    expect(ROUTES.DOCUMENTS).toBe('/dms/documents');
    expect(ROUTES.DOCUMENT_CREATE).toBe('/dms/documents/new');
    expect(ROUTES.DOCUMENT_DETAIL('id')).toBe('/dms/documents/id');
    expect(ROUTES.DOCUMENT_EDIT('id')).toBe('/dms/documents/id/edit');
    expect(ROUTES.FOLDER_CREATE).toBe('/dms/folders/new');
    expect(ROUTES.FOLDER_DETAIL('id')).toBe('/dms/folders/id');
    expect(ROUTES.FOLDER_EDIT('id')).toBe('/dms/folders/id/edit');
  });
});
