/**
 * Asset Management Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Asset, AssetCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const assetService = {
  listAssets: async (): Promise<Asset[]> => {
    const response = await apiClient.get<Asset[] | { results: Asset[] }>(
      ENDPOINTS.ASSETS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getAsset: async (id: string): Promise<Asset> => {
    return apiClient.get<Asset>(ENDPOINTS.ASSETS.DETAIL(id));
  },

  createAsset: async (data: AssetCreate): Promise<Asset> => {
    return apiClient.post<Asset>(ENDPOINTS.ASSETS.CREATE, data);
  },

  updateAsset: async (id: string, data: Partial<AssetCreate>): Promise<Asset> => {
    return apiClient.patch<Asset>(ENDPOINTS.ASSETS.UPDATE(id), data);
  },

  deleteAsset: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.ASSETS.DELETE(id));
  },
};
