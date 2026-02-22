/**
 * Fixed Assets Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { FixedAsset, FixedAssetCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const fixedAssetsService = {
  listFixedAssets: async (): Promise<FixedAsset[]> => {
    const response = await apiClient.get<FixedAsset[] | { results: FixedAsset[] }>(
      ENDPOINTS.ASSETS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getFixedAsset: async (id: string): Promise<FixedAsset> => {
    return apiClient.get<FixedAsset>(ENDPOINTS.ASSETS.DETAIL(id));
  },

  createFixedAsset: async (data: FixedAssetCreate): Promise<FixedAsset> => {
    return apiClient.post<FixedAsset>(ENDPOINTS.ASSETS.CREATE, data);
  },

  updateFixedAsset: async (
    id: string,
    data: Partial<FixedAssetCreate>
  ): Promise<FixedAsset> => {
    return apiClient.patch<FixedAsset>(ENDPOINTS.ASSETS.UPDATE(id), data);
  },

  deleteFixedAsset: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.ASSETS.DELETE(id));
  },
};
