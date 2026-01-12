/**
 * Dms Service
 * 
 * Service client for Dms module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import type {
  Folder,
  FolderCreate,
  FolderUpdate,
  Document,
  DocumentCreate,
  DocumentUpdate,
} from '../contracts';

export const dmsService = {
  /**
   * List all folders
   */
  listFolders: async (): Promise<Folder[]> => {
    return apiClient.get<Folder[]>(ENDPOINTS.FOLDERS.LIST);
  },

  /**
   * Get folder by ID
   */
  getFolder: async (id: string): Promise<Folder> => {
    return apiClient.get<Folder>(ENDPOINTS.FOLDERS.DETAIL(id));
  },

  /**
   * Create new folder
   */
  createFolder: async (data: FolderCreate): Promise<Folder> => {
    return apiClient.post<Folder>(ENDPOINTS.FOLDERS.CREATE, data);
  },

  /**
   * Update folder
   */
  updateFolder: async (id: string, data: FolderUpdate): Promise<Folder> => {
    return apiClient.put<Folder>(ENDPOINTS.FOLDERS.UPDATE(id), data);
  },

  /**
   * Delete folder
   */
  deleteFolder: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.FOLDERS.DELETE(id));
  },

  /**
   * List all documents
   */
  listDocuments: async (): Promise<Document[]> => {
    return apiClient.get<Document[]>(ENDPOINTS.DOCUMENTS.LIST);
  },

  /**
   * Get document by ID
   */
  getDocument: async (id: string): Promise<Document> => {
    return apiClient.get<Document>(ENDPOINTS.DOCUMENTS.DETAIL(id));
  },

  /**
   * Create new document
   */
  createDocument: async (data: DocumentCreate): Promise<Document> => {
    return apiClient.post<Document>(ENDPOINTS.DOCUMENTS.CREATE, data);
  },

  /**
   * Update document
   */
  updateDocument: async (id: string, data: DocumentUpdate): Promise<Document> => {
    return apiClient.put<Document>(ENDPOINTS.DOCUMENTS.UPDATE(id), data);
  },

  /**
   * Delete document
   */
  deleteDocument: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.DOCUMENTS.DELETE(id));
  },

  // Legacy methods for backward compatibility with generic list pages
  /**
   * List all resources (legacy - returns documents)
   * @deprecated Use listDocuments() instead
   */
  listResources: async (): Promise<Document[]> => {
    return apiClient.get<Document[]>(ENDPOINTS.DOCUMENTS.LIST);
  },

  /**
   * Get resource by ID (legacy - returns document)
   * @deprecated Use getDocument() instead
   */
  getResource: async (id: string): Promise<Document> => {
    return apiClient.get<Document>(ENDPOINTS.DOCUMENTS.DETAIL(id));
  },

  /**
   * Create new resource (legacy - creates document)
   * @deprecated Use createDocument() instead
   */
  createResource: async (data: DocumentCreate): Promise<Document> => {
    return apiClient.post<Document>(ENDPOINTS.DOCUMENTS.CREATE, data);
  },

  /**
   * Update resource (legacy - updates document)
   * @deprecated Use updateDocument() instead
   */
  updateResource: async (id: string, data: DocumentUpdate): Promise<Document> => {
    return apiClient.put<Document>(ENDPOINTS.DOCUMENTS.UPDATE(id), data);
  },

  /**
   * Delete resource (legacy - deletes document)
   * @deprecated Use deleteDocument() instead
   */
  deleteResource: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.DOCUMENTS.DELETE(id));
  },
};
