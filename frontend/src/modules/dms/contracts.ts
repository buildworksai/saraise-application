/** Governed v2 contracts for the document-management foundation. */

export type UUID = string;
export type ISODateTime = string;
export type JsonPrimitive = string | number | boolean | null;
export type DocumentMetadata = Readonly<Record<string, JsonPrimitive>>;

export type DmsAllowedAction =
  | 'read'
  | 'write'
  | 'manage'
  | 'create'
  | 'update'
  | 'move'
  | 'download'
  | 'delete'
  | 'create_version'
  | 'restore_version'
  | 'manage_permissions'
  | 'share';

export interface Folder {
  readonly id: UUID;
  readonly name: string;
  readonly description: string;
  readonly parent_id: UUID | null;
  readonly path: string;
  readonly depth: number;
  readonly sort_order: number;
  readonly created_by: UUID;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly allowed_actions: readonly DmsAllowedAction[];
}

export interface FolderCreate {
  readonly name: string;
  readonly description?: string;
  readonly parent_id?: UUID | null;
}

export interface FolderUpdate {
  readonly name?: string;
  readonly description?: string;
  readonly sort_order?: number;
}

export interface FolderMove { readonly parent_id: UUID | null }

export interface DocumentVersionSummary {
  readonly id: UUID;
  readonly version_number: number;
  readonly original_filename: string;
  readonly mime_type: string;
  readonly size_bytes: number;
  readonly checksum_sha256: string;
  readonly created_by: UUID;
  readonly created_at: ISODateTime;
}

export interface DocumentSummary {
  readonly id: UUID;
  readonly name: string;
  readonly description: string;
  readonly folder_id: UUID | null;
  readonly folder_name: string | null;
  readonly tags: readonly string[];
  readonly current_version: DocumentVersionSummary | null;
  readonly version_count: number;
  readonly created_by: UUID;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly allowed_actions: readonly DmsAllowedAction[];
}

export interface Document extends DocumentSummary {
  readonly metadata: DocumentMetadata;
}

export interface DocumentUpload {
  readonly file: File;
  readonly name: string;
  readonly folder_id?: UUID | null;
  readonly description?: string;
  readonly tags?: readonly string[];
  readonly metadata?: DocumentMetadata;
}

export interface DocumentUpdate {
  readonly name?: string;
  readonly description?: string;
  readonly tags?: readonly string[];
  readonly metadata?: DocumentMetadata;
  /** Optimistic concurrency precondition, not a user-editable audit value. */
  readonly expected_updated_at: ISODateTime;
}

export interface DocumentMove { readonly folder_id: UUID | null; readonly expected_updated_at?: ISODateTime }

export interface DocumentVersion extends DocumentVersionSummary {
  readonly document_id: UUID;
  readonly change_note: string;
  readonly source_version_id: UUID | null;
}

export interface DocumentVersionCreate {
  readonly document_id: UUID;
  readonly file: File;
  readonly change_note?: string;
}

export interface DocumentVersionRestore { readonly change_note?: string }

export type PrincipalType = 'user' | 'role' | 'group';
export type DocumentPermissionLevel = 'read' | 'write' | 'delete' | 'share' | 'manage';

export interface PrincipalSummary {
  readonly id: UUID;
  readonly type: PrincipalType;
  readonly display_name: string;
  readonly secondary_text: string;
}

export interface DocumentPermission {
  readonly id: UUID;
  readonly document_id: UUID;
  readonly principal_type: PrincipalType;
  readonly principal_id: UUID;
  readonly principal_display?: string;
  readonly permission: DocumentPermissionLevel;
  readonly created_by: UUID;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
}

export interface DocumentPermissionCreate {
  readonly document_id: UUID;
  readonly principal_type: PrincipalType;
  readonly principal_id: UUID;
  readonly permission: DocumentPermissionLevel;
}

export interface DocumentPermissionUpdate { readonly permission: DocumentPermissionLevel }

export interface DocumentShare {
  readonly id: UUID;
  readonly document_id: UUID;
  readonly version_id: UUID;
  readonly token_prefix: string;
  readonly expires_at: ISODateTime;
  readonly max_access_count: number | null;
  readonly access_count: number;
  readonly last_accessed_at: ISODateTime | null;
  readonly revoked_at: ISODateTime | null;
  readonly created_by: UUID;
  readonly created_at: ISODateTime;
  readonly state: 'active' | 'expired' | 'exhausted' | 'revoked';
}

export interface DocumentShareCreate {
  readonly document_id: UUID;
  readonly version_id?: UUID | null;
  readonly expires_at: ISODateTime;
  readonly max_access_count?: number | null;
}

export interface ShareCreated {
  readonly share: DocumentShare;
  readonly share_url: string;
}

export interface FolderContents {
  readonly folder: Folder | null;
  readonly breadcrumbs: readonly Folder[];
  readonly folders: readonly Folder[];
  readonly documents: readonly DocumentSummary[];
  readonly allowed_actions: readonly DmsAllowedAction[];
}

export type DocumentOrdering = 'name' | '-name' | 'updated_at' | '-updated_at' | 'created_at' | '-created_at';
export type FolderOrdering = 'name' | '-name' | 'sort_order' | '-sort_order' | 'updated_at' | '-updated_at';

export interface DmsListQuery {
  /** UUID or the explicit `root` sentinel accepted by the governed filter. */
  readonly folder?: string | null;
  readonly parent_id?: UUID | null;
  readonly document_id?: UUID;
  readonly mime_type?: string;
  readonly creator?: UUID;
  readonly tags?: readonly string[];
  readonly modified_after?: ISODateTime;
  readonly modified_before?: ISODateTime;
  readonly search?: string;
  readonly ordering?: DocumentOrdering | FolderOrdering;
  readonly page?: number;
  readonly page_size?: number;
}

export interface PaginationMeta {
  readonly count: number;
  readonly page: number;
  readonly page_size: number;
  readonly total_pages: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}

export interface ApiEnvelope<T> {
  readonly data: T;
  readonly meta: {
    readonly correlation_id: string;
    readonly timestamp: ISODateTime;
    readonly pagination?: PaginationMeta;
  };
}

export interface DmsPage<T> {
  readonly items: readonly T[];
  readonly pagination: PaginationMeta;
  readonly correlation_id: string;
}

export interface FieldError {
  readonly field: string;
  readonly code: string;
  readonly message: string;
}

export interface ApiErrorEnvelope {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly detail?: { readonly field_errors?: readonly FieldError[]; readonly retry_after_seconds?: number };
    readonly correlation_id: string;
  };
}

export type DmsFrontendError =
  | { readonly kind: 'denied'; readonly status: 401 | 403; readonly message: string; readonly correlation_id: string | null }
  | { readonly kind: 'not_found'; readonly status: 404; readonly message: string; readonly correlation_id: string | null }
  | { readonly kind: 'conflict'; readonly status: 409; readonly message: string; readonly correlation_id: string | null }
  | { readonly kind: 'validation'; readonly status: 400 | 422; readonly message: string; readonly field_errors: readonly FieldError[]; readonly correlation_id: string | null }
  | { readonly kind: 'rate_limited'; readonly status: 429; readonly message: string; readonly retry_after_seconds: number | null; readonly correlation_id: string | null }
  | { readonly kind: 'unavailable'; readonly status: 503; readonly message: string; readonly correlation_id: string | null }
  | { readonly kind: 'unexpected'; readonly status: number; readonly message: string; readonly correlation_id: string | null };

export interface DownloadResult { readonly blob: Blob; readonly filename: string; readonly mime_type: string }
export interface UploadProgress { readonly loaded: number; readonly total: number; readonly percent: number }
export interface UploadOptions { readonly signal?: AbortSignal; readonly onProgress?: (progress: UploadProgress) => void }
export interface DmsHealth { readonly status: 'healthy' | 'degraded' | 'unhealthy'; readonly checks: Readonly<Record<string, Readonly<Record<string, JsonPrimitive>>>> }

export const MODULE_API_PREFIX = '/api/v2/dms';

export const ENDPOINTS = {
  FOLDERS: {
    LIST: `${MODULE_API_PREFIX}/folders/`,
    CREATE: `${MODULE_API_PREFIX}/folders/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/folders/${encodeURIComponent(id)}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/folders/${encodeURIComponent(id)}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/folders/${encodeURIComponent(id)}/` as const,
    MOVE: (id: UUID) => `${MODULE_API_PREFIX}/folders/${encodeURIComponent(id)}/move/` as const,
    CONTENTS: (id: UUID) => `${MODULE_API_PREFIX}/folders/${encodeURIComponent(id)}/contents/` as const,
  },
  DOCUMENTS: {
    LIST: `${MODULE_API_PREFIX}/documents/`,
    UPLOAD: `${MODULE_API_PREFIX}/documents/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/documents/${encodeURIComponent(id)}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/documents/${encodeURIComponent(id)}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/documents/${encodeURIComponent(id)}/` as const,
    MOVE: (id: UUID) => `${MODULE_API_PREFIX}/documents/${encodeURIComponent(id)}/move/` as const,
    DOWNLOAD: (id: UUID) => `${MODULE_API_PREFIX}/documents/${encodeURIComponent(id)}/download/` as const,
  },
  VERSIONS: {
    LIST: `${MODULE_API_PREFIX}/document-versions/`,
    CREATE: `${MODULE_API_PREFIX}/document-versions/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/document-versions/${encodeURIComponent(id)}/` as const,
    RESTORE: (id: UUID) => `${MODULE_API_PREFIX}/document-versions/${encodeURIComponent(id)}/restore/` as const,
  },
  PERMISSIONS: {
    LIST: `${MODULE_API_PREFIX}/document-permissions/`,
    CREATE: `${MODULE_API_PREFIX}/document-permissions/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/document-permissions/${encodeURIComponent(id)}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/document-permissions/${encodeURIComponent(id)}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/document-permissions/${encodeURIComponent(id)}/` as const,
  },
  SHARES: {
    LIST: `${MODULE_API_PREFIX}/document-shares/`,
    CREATE: `${MODULE_API_PREFIX}/document-shares/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/document-shares/${encodeURIComponent(id)}/` as const,
    REVOKE: (id: UUID) => `${MODULE_API_PREFIX}/document-shares/${encodeURIComponent(id)}/revoke/` as const,
  },
  PRINCIPALS: `${MODULE_API_PREFIX}/principals/`,
  PUBLIC_SHARE_DOWNLOAD: (token: string) => `${MODULE_API_PREFIX}/public/shares/${encodeURIComponent(token)}/download/` as const,
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTES = {
  DOCUMENTS: '/dms/documents',
  DOCUMENT_CREATE: '/dms/documents/new',
  DOCUMENT_DETAIL: (id: UUID) => `/dms/documents/${encodeURIComponent(id)}` as const,
  DOCUMENT_EDIT: (id: UUID) => `/dms/documents/${encodeURIComponent(id)}/edit` as const,
  FOLDER_CREATE: '/dms/folders/new',
  FOLDER_DETAIL: (id: UUID) => `/dms/folders/${encodeURIComponent(id)}` as const,
  FOLDER_EDIT: (id: UUID) => `/dms/folders/${encodeURIComponent(id)}/edit` as const,
} as const;
