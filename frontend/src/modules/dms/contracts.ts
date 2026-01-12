/**
 * Dms Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Dms are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Folder entity */
export type Folder = {
  id: string;
  tenant_id: string;
  name: string;
  parent?: string;
  parent_id?: string;
  path: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

/** Folder create request */
export type FolderCreate = {
  name: string;
  parent?: string;
};

/** Folder update request (partial) */
export type FolderUpdate = Partial<FolderCreate>;

/** Document entity */
export type Document = {
  id: string;
  tenant_id: string;
  name: string;
  folder?: string;
  folder_id?: string;
  file_path: string;
  mime_type: string;
  size: number;
  checksum: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

/** Document create request */
export type DocumentCreate = {
  name: string;
  folder?: string;
  file_path: string;
  mime_type: string;
  size: number;
  checksum: string;
};

/** Document update request (partial) */
export type DocumentUpdate = Partial<DocumentCreate>;

/** DocumentVersion entity */
export type DocumentVersion = {
  id: string;
  document: string;
  document_id?: string;
  version_number: number;
  file_path: string;
  created_at: string;
  created_by: string;
};

/** DocumentPermission entity */
export type DocumentPermission = {
  id: string;
  tenant_id: string;
  document: string;
  document_id?: string;
  principal_type: 'user' | 'role' | 'group';
  principal_id: string;
  permission: 'read' | 'write' | 'delete' | 'share';
  created_at: string;
  updated_at: string;
};

/** DocumentPermission create request */
export type DocumentPermissionCreate = {
  document: string;
  principal_type: 'user' | 'role' | 'group';
  principal_id: string;
  permission: 'read' | 'write' | 'delete' | 'share';
};

/** DocumentPermission update request (partial) */
export type DocumentPermissionUpdate = Partial<DocumentPermissionCreate>;

/** DocumentShare entity */
export type DocumentShare = {
  id: string;
  tenant_id: string;
  document: string;
  document_id?: string;
  share_token: string;
  expires_at?: string;
  access_count: number;
  max_access_count?: number;
  created_by: string;
  created_at: string;
  updated_at: string;
};

/** DocumentShare create request */
export type DocumentShareCreate = {
  document: string;
  expires_at?: string;
  max_access_count?: number;
};

/** DocumentShare update request (partial) */
export type DocumentShareUpdate = Partial<DocumentShareCreate>;

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * Dms API Endpoints
 *
 * All endpoints should be prefixed with /api/v1/dms/
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS } from './contracts';
 * apiClient.get(ENDPOINTS.FOLDERS.LIST);
 * apiClient.get(ENDPOINTS.DOCUMENTS.DETAIL(id));
 * ```
 */
export const MODULE_API_PREFIX = '/api/v1/dms';

export const ENDPOINTS = {
  FOLDERS: {
    LIST: `${MODULE_API_PREFIX}/folders/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/folders/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/folders/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/folders/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/folders/${id}/` as const,
    MOVE: (id: string) => `${MODULE_API_PREFIX}/folders/${id}/move/` as const,
  },
  DOCUMENTS: {
    LIST: `${MODULE_API_PREFIX}/documents/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/documents/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/documents/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/documents/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/documents/${id}/` as const,
    UPLOAD: (id: string) => `${MODULE_API_PREFIX}/documents/${id}/upload/` as const,
    DOWNLOAD: (id: string) => `${MODULE_API_PREFIX}/documents/${id}/download/` as const,
  },
  DOCUMENT_VERSIONS: {
    LIST: `${MODULE_API_PREFIX}/document-versions/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/document-versions/${id}/` as const,
  },
  DOCUMENT_PERMISSIONS: {
    LIST: `${MODULE_API_PREFIX}/document-permissions/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/document-permissions/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/document-permissions/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/document-permissions/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/document-permissions/${id}/` as const,
  },
  DOCUMENT_SHARES: {
    LIST: `${MODULE_API_PREFIX}/document-shares/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/document-shares/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/document-shares/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/document-shares/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
