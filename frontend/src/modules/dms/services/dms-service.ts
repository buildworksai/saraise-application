import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiEnvelope,
  type ApiErrorEnvelope,
  type DmsFrontendError,
  type DmsHealth,
  type DmsConfiguration,
  type DmsConfigurationAuditRecord,
  type DmsConfigurationExportDocument,
  type DmsConfigurationPreview,
  type DmsConfigurationWrite,
  type DmsConfigurationVersion,
  type DmsEnvironment,
  type DmsListQuery,
  type DmsPage,
  type Document,
  type DocumentMove,
  type DocumentPermission,
  type DocumentPermissionCreate,
  type DocumentPermissionUpdate,
  type DocumentShare,
  type DocumentShareCreate,
  type DocumentSummary,
  type DocumentUpdate,
  type DocumentUpload,
  type DocumentVersion,
  type DocumentVersionCreate,
  type DocumentVersionRestore,
  type DownloadResult,
  type FieldError,
  type Folder,
  type FolderContents,
  type FolderCreate,
  type FolderMove,
  type FolderUpdate,
  type PrincipalSummary,
  type PrincipalType,
  type ShareCreated,
  type UploadOptions,
  type UUID,
} from '../contracts';

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function apiErrorBody(value: unknown): ApiErrorEnvelope['error'] | null {
  if (!isObject(value) || !isObject(value.error)) return null;
  const valueError = value.error;
  if (typeof valueError.code !== 'string' || typeof valueError.message !== 'string' || typeof valueError.correlation_id !== 'string') return null;
  return {
    code: valueError.code,
    message: valueError.message,
    correlation_id: valueError.correlation_id,
    detail: isObject(valueError.detail)
      ? {
          field_errors: Array.isArray(valueError.detail.field_errors)
            ? valueError.detail.field_errors.flatMap((item): readonly FieldError[] => {
                if (!isObject(item) || typeof item.field !== 'string' || typeof item.code !== 'string' || typeof item.message !== 'string') return [];
                return [{ field: item.field, code: item.code, message: item.message }];
              })
            : undefined,
          retry_after_seconds: typeof valueError.detail.retry_after_seconds === 'number' ? valueError.detail.retry_after_seconds : undefined,
        }
      : undefined,
  };
}

function normalizeError(status: number, fallback: string, body?: unknown): DmsFrontendError {
  const parsed = apiErrorBody(body);
  const message = parsed?.message ?? fallback;
  const correlation_id = parsed?.correlation_id ?? null;
  if (status === 401 || status === 403) return { kind: 'denied', status, message, correlation_id };
  if (status === 404) return { kind: 'not_found', status, message, correlation_id };
  if (status === 409) return { kind: 'conflict', status, message, correlation_id };
  if (status === 400 || status === 422) return { kind: 'validation', status, message, field_errors: parsed?.detail?.field_errors ?? [], correlation_id };
  if (status === 429) return { kind: 'rate_limited', status, message, retry_after_seconds: parsed?.detail?.retry_after_seconds ?? null, correlation_id };
  if (status === 503) return { kind: 'unavailable', status, message, correlation_id };
  return { kind: 'unexpected', status, message, correlation_id };
}

export class DmsApiError extends Error {
  constructor(readonly problem: DmsFrontendError) {
    super(problem.message);
    this.name = 'DmsApiError';
  }
}

async function governed<T>(operation: () => Promise<ApiEnvelope<T>>): Promise<T> {
  try {
    return (await operation()).data;
  } catch (error) {
    if (error instanceof ApiError) throw new DmsApiError(normalizeError(error.status, error.message, error.details));
    throw error;
  }
}

async function governedVoid(operation: () => Promise<void>): Promise<void> {
  try {
    await operation();
  } catch (error) {
    if (error instanceof ApiError) throw new DmsApiError(normalizeError(error.status, error.message, error.details));
    throw error;
  }
}

async function governedPage<T>(operation: () => Promise<ApiEnvelope<readonly T[]>>): Promise<DmsPage<T>> {
  try {
    const response = await operation();
    const pagination = response.meta.pagination;
    if (!pagination) throw new DmsApiError({ kind: 'unexpected', status: 502, message: 'The DMS returned a collection without pagination evidence.', correlation_id: response.meta.correlation_id });
    return { items: response.data, pagination, correlation_id: response.meta.correlation_id };
  } catch (error) {
    if (error instanceof ApiError) throw new DmsApiError(normalizeError(error.status, error.message, error.details));
    throw error;
  }
}

function queryPath(path: string, query: DmsListQuery = {}): string {
  const parameters = new URLSearchParams();
  const entries: readonly [string, string | number | undefined][] = [
    ['folder', query.folder ?? undefined],
    ['parent_id', query.parent_id ?? undefined],
    ['document_id', query.document_id],
    ['mime_type', query.mime_type],
    ['creator', query.creator],
    ['modified_after', query.modified_after],
    ['modified_before', query.modified_before],
    ['search', query.search],
    ['ordering', query.ordering],
    ['environment', query.environment],
    ['page', query.page],
    ['page_size', query.page_size],
  ];
  for (const [key, value] of entries) if (value !== undefined && value !== '') parameters.set(key, String(value));
  for (const tag of query.tags ?? []) parameters.append('tags', tag);
  const serialized = parameters.toString();
  return serialized ? `${path}?${serialized}` : path;
}

function principalQueryPath(search: string, type: PrincipalType, limit: number): string {
  const parameters = new URLSearchParams({ search, type, limit: String(limit) });
  return `${ENDPOINTS.PRINCIPALS}?${parameters.toString()}`;
}

function csrfToken(): string | null {
  const match = document.cookie.split('; ').find((item) => item.startsWith('saraise_csrftoken='));
  return match ? decodeURIComponent(match.slice('saraise_csrftoken='.length)) : null;
}

function transportUrl(path: string): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  return configured && configured !== '' ? `${configured}${path}` : path;
}

function multipart(request: DocumentUpload | DocumentVersionCreate): FormData {
  const body = new FormData();
  body.set('file', request.file);
  if ('name' in request) {
    body.set('name', request.name);
    if (request.folder_id) body.set('folder_id', request.folder_id);
    if (request.description) body.set('description', request.description);
    for (const tag of request.tags ?? []) body.append('tags', tag);
    body.set('metadata', JSON.stringify(request.metadata ?? {}));
  } else {
    body.set('document_id', request.document_id);
    if (request.change_note) body.set('change_note', request.change_note);
  }
  return body;
}

function parseJson(value: string): unknown {
  if (!value) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed;
  } catch {
    return null;
  }
}

function isDocument(value: unknown): value is Document {
  return isObject(value)
    && typeof value.id === 'string'
    && typeof value.name === 'string'
    && typeof value.description === 'string'
    && Array.isArray(value.tags)
    && isObject(value.metadata)
    && typeof value.version_count === 'number'
    && typeof value.created_by === 'string'
    && typeof value.created_at === 'string'
    && typeof value.updated_at === 'string'
    && Array.isArray(value.allowed_actions);
}

function isDocumentVersion(value: unknown): value is DocumentVersion {
  return isObject(value)
    && typeof value.id === 'string'
    && typeof value.document_id === 'string'
    && typeof value.version_number === 'number'
    && typeof value.original_filename === 'string'
    && typeof value.mime_type === 'string'
    && typeof value.size_bytes === 'number'
    && typeof value.checksum_sha256 === 'string'
    && typeof value.change_note === 'string'
    && typeof value.created_by === 'string'
    && typeof value.created_at === 'string';
}

let uploadCircuitFailures = 0;
let uploadCircuitOpenUntil = 0;

function uploadAttempt<T>(
  path: string,
  request: DocumentUpload | DocumentVersionCreate,
  accepts: (value: unknown) => value is T,
  options: UploadOptions,
  idempotencyKey: string,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', transportUrl(path));
    xhr.withCredentials = true;
    xhr.timeout = options.transport.timeout_ms;
    xhr.setRequestHeader('Idempotency-Key', idempotencyKey);
    const token = csrfToken();
    if (token) xhr.setRequestHeader('X-CSRFToken', token);
    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable) return;
      options.onProgress?.({ loaded: event.loaded, total: event.total, percent: Math.round((event.loaded / event.total) * 100) });
    });
    xhr.addEventListener('load', () => {
      const parsed = parseJson(xhr.responseText);
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new DmsApiError(normalizeError(xhr.status, 'The upload could not be completed.', parsed)));
        return;
      }
      if (!isObject(parsed) || !accepts(parsed.data)) {
        reject(new DmsApiError({ kind: 'unexpected', status: 502, message: 'The upload completed without a governed response.', correlation_id: null }));
        return;
      }
      resolve(parsed.data);
    });
    xhr.addEventListener('error', () => reject(new DmsApiError({ kind: 'unavailable', status: 503, message: 'The upload connection failed. Your document was not reported as saved.', correlation_id: null })));
    xhr.addEventListener('timeout', () => reject(new DmsApiError({ kind: 'unavailable', status: 503, message: 'The upload timed out before durable storage was confirmed.', correlation_id: null })));
    xhr.addEventListener('abort', () => reject(new DOMException('Upload cancelled', 'AbortError')));
    options.signal?.addEventListener('abort', () => xhr.abort(), { once: true });
    xhr.send(multipart(request));
  });
}

function uploadRetryable(error: unknown): boolean {
  return error instanceof DmsApiError && (error.problem.kind === 'unavailable' || error.problem.kind === 'rate_limited');
}

async function retryDelay(attempt: number, options: UploadOptions): Promise<void> {
  const retryWindow = options.transport.timeout_ms / (options.transport.max_retries + 1);
  const exponential = Math.min(options.transport.circuit_breaker_reset_ms, retryWindow * 2 ** attempt);
  const jittered = exponential / 2 + Math.random() * exponential / 2;
  await new Promise<void>((resolve) => setTimeout(resolve, jittered));
}

async function upload<T>(
  path: string,
  request: DocumentUpload | DocumentVersionCreate,
  accepts: (value: unknown) => value is T,
  options: UploadOptions,
): Promise<T> {
  if (Date.now() < uploadCircuitOpenUntil) {
    throw new DmsApiError({ kind: 'unavailable', status: 503, message: 'Uploads are temporarily paused after repeated transport failures. Retry after the circuit reset window.', correlation_id: null });
  }
  const idempotencyKey = crypto.randomUUID();
  for (let attempt = 0; attempt <= options.transport.max_retries; attempt += 1) {
    try {
      const result = await uploadAttempt(path, request, accepts, options, idempotencyKey);
      uploadCircuitFailures = 0;
      uploadCircuitOpenUntil = 0;
      return result;
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') throw error;
      uploadCircuitFailures += 1;
      if (uploadCircuitFailures >= options.transport.circuit_breaker_failure_threshold) {
        uploadCircuitOpenUntil = Date.now() + options.transport.circuit_breaker_reset_ms;
      }
      if (!uploadRetryable(error) || attempt >= options.transport.max_retries || Date.now() < uploadCircuitOpenUntil) throw error;
      await retryDelay(attempt, options);
    }
  }
  throw new DmsApiError({ kind: 'unavailable', status: 503, message: 'The upload retry policy was exhausted.', correlation_id: null });
}

function filenameFromDisposition(value: string | null, fallback: string): string {
  if (!value) return fallback;
  const encoded = /filename\*=UTF-8''([^;]+)/iu.exec(value)?.[1];
  if (encoded) {
    try { return decodeURIComponent(encoded); } catch { return fallback; }
  }
  return /filename="([^"]+)"/u.exec(value)?.[1] ?? fallback;
}

async function download(path: string, fallbackName: string): Promise<DownloadResult> {
  const response = await fetch(transportUrl(path), { credentials: 'include' });
  if (!response.ok) {
    let body: unknown;
    try { body = await response.json(); } catch { body = null; }
    throw new DmsApiError(normalizeError(response.status, response.statusText || 'Download failed.', body));
  }
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get('Content-Disposition'), fallbackName),
    mime_type: response.headers.get('Content-Type') ?? 'application/octet-stream',
  };
}

export const DMS_QUERY_KEYS = {
  root: ['dms'] as const,
  folders: (query: DmsListQuery = {}) => ['dms', 'folders', query] as const,
  folder: (id: UUID) => ['dms', 'folder', id] as const,
  contents: (id: UUID) => ['dms', 'folder', id, 'contents'] as const,
  documents: (query: DmsListQuery = {}) => ['dms', 'documents', query] as const,
  document: (id: UUID) => ['dms', 'document', id] as const,
  versions: (documentId: UUID) => ['dms', 'document', documentId, 'versions'] as const,
  version: (id: UUID) => ['dms', 'version', id] as const,
  permissions: (documentId: UUID) => ['dms', 'document', documentId, 'permissions'] as const,
  permission: (id: UUID) => ['dms', 'permission', id] as const,
  shares: (documentId: UUID) => ['dms', 'document', documentId, 'shares'] as const,
  share: (id: UUID) => ['dms', 'share', id] as const,
  principals: (search: string, type: PrincipalType) => ['dms', 'principals', type, search] as const,
  health: ['dms', 'health'] as const,
  configuration: (environment?: string) => ['dms', 'configuration', environment ?? 'current'] as const,
  configurationHistory: (environment: string) => ['dms', 'configuration', environment, 'history'] as const,
  configurationAudit: (environment: string) => ['dms', 'configuration', environment, 'audit'] as const,
};

export const dmsService = {
  listFolders: (query: DmsListQuery = {}) => governedPage(() => apiClient.get<ApiEnvelope<readonly Folder[]>>(queryPath(ENDPOINTS.FOLDERS.LIST, query))),
  getFolder: (id: UUID) => governed(() => apiClient.get<ApiEnvelope<Folder>>(ENDPOINTS.FOLDERS.DETAIL(id))),
  createFolder: (request: FolderCreate) => governed(() => apiClient.post<ApiEnvelope<Folder>>(ENDPOINTS.FOLDERS.CREATE, request)),
  updateFolder: (id: UUID, request: FolderUpdate) => governed(() => apiClient.patch<ApiEnvelope<Folder>>(ENDPOINTS.FOLDERS.UPDATE(id), request)),
  deleteFolder: (id: UUID) => governedVoid(() => apiClient.delete<void>(ENDPOINTS.FOLDERS.DELETE(id))),
  moveFolder: (id: UUID, request: FolderMove) => governed(() => apiClient.post<ApiEnvelope<Folder>>(ENDPOINTS.FOLDERS.MOVE(id), request)),
  getFolderContents: (id: UUID) => governed(() => apiClient.get<ApiEnvelope<FolderContents>>(ENDPOINTS.FOLDERS.CONTENTS(id))),

  listDocuments: (query: DmsListQuery = {}) => governedPage(() => apiClient.get<ApiEnvelope<readonly DocumentSummary[]>>(queryPath(ENDPOINTS.DOCUMENTS.LIST, query))),
  getDocument: (id: UUID) => governed(() => apiClient.get<ApiEnvelope<Document>>(ENDPOINTS.DOCUMENTS.DETAIL(id))),
  uploadDocument: (request: DocumentUpload, options: UploadOptions) => upload<Document>(ENDPOINTS.DOCUMENTS.UPLOAD, request, isDocument, options),
  updateDocument: (id: UUID, request: DocumentUpdate) => governed(() => apiClient.patch<ApiEnvelope<Document>>(ENDPOINTS.DOCUMENTS.UPDATE(id), request)),
  deleteDocument: (id: UUID) => governedVoid(() => apiClient.delete<void>(ENDPOINTS.DOCUMENTS.DELETE(id))),
  moveDocument: (id: UUID, request: DocumentMove) => governed(() => apiClient.post<ApiEnvelope<Document>>(ENDPOINTS.DOCUMENTS.MOVE(id), request)),
  downloadDocument: (id: UUID, versionId?: UUID) => download(versionId ? `${ENDPOINTS.DOCUMENTS.DOWNLOAD(id)}?version_id=${encodeURIComponent(versionId)}` : ENDPOINTS.DOCUMENTS.DOWNLOAD(id), 'document'),

  listVersions: (documentId: UUID, query: DmsListQuery = {}) => governedPage(() => apiClient.get<ApiEnvelope<readonly DocumentVersion[]>>(queryPath(ENDPOINTS.VERSIONS.LIST, { ...query, document_id: documentId }))),
  createVersion: (request: DocumentVersionCreate, options: UploadOptions) => upload<DocumentVersion>(ENDPOINTS.VERSIONS.CREATE, request, isDocumentVersion, options),
  getVersion: (id: UUID) => governed(() => apiClient.get<ApiEnvelope<DocumentVersion>>(ENDPOINTS.VERSIONS.DETAIL(id))),
  restoreVersion: (id: UUID, request: DocumentVersionRestore) => governed(() => apiClient.post<ApiEnvelope<DocumentVersion>>(ENDPOINTS.VERSIONS.RESTORE(id), request)),

  listPermissions: (documentId: UUID) => governedPage(() => apiClient.get<ApiEnvelope<readonly DocumentPermission[]>>(queryPath(ENDPOINTS.PERMISSIONS.LIST, { document_id: documentId, page_size: 100 }))),
  createPermission: (request: DocumentPermissionCreate) => governed(() => apiClient.post<ApiEnvelope<DocumentPermission>>(ENDPOINTS.PERMISSIONS.CREATE, request)),
  getPermission: (id: UUID) => governed(() => apiClient.get<ApiEnvelope<DocumentPermission>>(ENDPOINTS.PERMISSIONS.DETAIL(id))),
  updatePermission: (id: UUID, request: DocumentPermissionUpdate) => governed(() => apiClient.patch<ApiEnvelope<DocumentPermission>>(ENDPOINTS.PERMISSIONS.UPDATE(id), request)),
  revokePermission: (id: UUID) => governedVoid(() => apiClient.delete<void>(ENDPOINTS.PERMISSIONS.DELETE(id))),

  listShares: (documentId: UUID) => governedPage(() => apiClient.get<ApiEnvelope<readonly DocumentShare[]>>(queryPath(ENDPOINTS.SHARES.LIST, { document_id: documentId, page_size: 100 }))),
  createShare: (request: DocumentShareCreate) => governed(() => apiClient.post<ApiEnvelope<ShareCreated>>(ENDPOINTS.SHARES.CREATE, request)),
  getShare: (id: UUID) => governed(() => apiClient.get<ApiEnvelope<DocumentShare>>(ENDPOINTS.SHARES.DETAIL(id))),
  revokeShare: (id: UUID) => governed(() => apiClient.post<ApiEnvelope<DocumentShare>>(ENDPOINTS.SHARES.REVOKE(id))),
  searchPrincipals: (search: string, type: PrincipalType, limit: number) => governed(() => apiClient.get<ApiEnvelope<readonly PrincipalSummary[]>>(principalQueryPath(search, type, limit))),
  downloadPublicShare: (token: string) => download(ENDPOINTS.PUBLIC_SHARE_DOWNLOAD(token), 'shared-document'),
  health: () => governed(() => apiClient.get<ApiEnvelope<DmsHealth>>(ENDPOINTS.HEALTH)),
  getConfiguration: (environment: DmsEnvironment = 'default') => governed(() => apiClient.get<ApiEnvelope<DmsConfiguration>>(queryPath(ENDPOINTS.CONFIGURATION.CURRENT, { environment }))),
  updateConfiguration: (request: DmsConfigurationWrite) => governed(() => apiClient.put<ApiEnvelope<DmsConfiguration>>(ENDPOINTS.CONFIGURATION.CURRENT, request)),
  previewConfiguration: (request: DmsConfigurationWrite) => governed(() => apiClient.post<ApiEnvelope<DmsConfigurationPreview>>(ENDPOINTS.CONFIGURATION.PREVIEW, request)),
  configurationHistory: (environment: DmsEnvironment, query: DmsListQuery = {}) => governedPage(() => apiClient.get<ApiEnvelope<readonly DmsConfigurationVersion[]>>(queryPath(ENDPOINTS.CONFIGURATION.HISTORY, { ...query, environment }))),
  configurationAudit: (environment: DmsEnvironment, query: DmsListQuery = {}) => governedPage(() => apiClient.get<ApiEnvelope<readonly DmsConfigurationAuditRecord[]>>(queryPath(ENDPOINTS.CONFIGURATION.AUDIT, { ...query, environment }))),
  rollbackConfiguration: (version: number, environment: DmsEnvironment) => governed(() => apiClient.post<ApiEnvelope<DmsConfiguration>>(ENDPOINTS.CONFIGURATION.ROLLBACK, { version, environment })),
  importConfiguration: (request: DmsConfigurationExportDocument) => governed(() => apiClient.post<ApiEnvelope<DmsConfiguration>>(ENDPOINTS.CONFIGURATION.IMPORT, request)),
  exportConfiguration: (environment: DmsEnvironment) => governed(() => apiClient.get<ApiEnvelope<DmsConfigurationExportDocument>>(queryPath(ENDPOINTS.CONFIGURATION.EXPORT, { environment }))),
};

export { queryPath as serializeDmsQuery };
