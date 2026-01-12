/**
 * Localization Service
 * 
 * Service client for Localization module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import type {
  Translation,
  TranslationCreate,
  TranslationUpdate,
} from '../contracts';

export const localizationService = {
  /**
   * List all translations
   */
  listTranslations: async (): Promise<Translation[]> => {
    return apiClient.get<Translation[]>(ENDPOINTS.TRANSLATIONS.LIST);
  },

  /**
   * Get translation by ID
   */
  getTranslation: async (id: string): Promise<Translation> => {
    return apiClient.get<Translation>(ENDPOINTS.TRANSLATIONS.DETAIL(id));
  },

  /**
   * Create new translation
   */
  createTranslation: async (data: TranslationCreate): Promise<Translation> => {
    return apiClient.post<Translation>(ENDPOINTS.TRANSLATIONS.CREATE, data);
  },

  /**
   * Update translation
   */
  updateTranslation: async (id: string, data: TranslationUpdate): Promise<Translation> => {
    return apiClient.put<Translation>(ENDPOINTS.TRANSLATIONS.UPDATE(id), data);
  },

  /**
   * Delete translation
   */
  deleteTranslation: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.TRANSLATIONS.DELETE(id));
  },

  // Legacy methods for backward compatibility with generic list pages
  /**
   * List all resources (legacy - returns translations)
   * @deprecated Use listTranslations() instead
   */
  listResources: async (): Promise<Translation[]> => {
    return apiClient.get<Translation[]>(ENDPOINTS.TRANSLATIONS.LIST);
  },

  /**
   * Get resource by ID (legacy - returns translation)
   * @deprecated Use getTranslation() instead
   */
  getResource: async (id: string): Promise<Translation> => {
    return apiClient.get<Translation>(ENDPOINTS.TRANSLATIONS.DETAIL(id));
  },

  /**
   * Create new resource (legacy - creates translation)
   * @deprecated Use createTranslation() instead
   */
  createResource: async (data: TranslationCreate): Promise<Translation> => {
    return apiClient.post<Translation>(ENDPOINTS.TRANSLATIONS.CREATE, data);
  },

  /**
   * Update resource (legacy - updates translation)
   * @deprecated Use updateTranslation() instead
   */
  updateResource: async (id: string, data: TranslationUpdate): Promise<Translation> => {
    return apiClient.put<Translation>(ENDPOINTS.TRANSLATIONS.UPDATE(id), data);
  },

  /**
   * Delete resource (legacy - deletes translation)
   * @deprecated Use deleteTranslation() instead
   */
  deleteResource: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.TRANSLATIONS.DELETE(id));
  },
};
