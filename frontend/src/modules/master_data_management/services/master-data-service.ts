/**
 * Master Data Management Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { MasterDataEntity, MasterDataEntityCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const masterDataService = {
  listEntities: async (): Promise<MasterDataEntity[]> => {
    const response = await apiClient.get<
      MasterDataEntity[] | { results: MasterDataEntity[] }
    >(ENDPOINTS.ENTITIES.LIST);
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getEntity: async (id: string): Promise<MasterDataEntity> => {
    return apiClient.get<MasterDataEntity>(ENDPOINTS.ENTITIES.DETAIL(id));
  },

  createEntity: async (data: MasterDataEntityCreate): Promise<MasterDataEntity> => {
    return apiClient.post<MasterDataEntity>(ENDPOINTS.ENTITIES.CREATE, data);
  },

  updateEntity: async (
    id: string,
    data: Partial<MasterDataEntityCreate>
  ): Promise<MasterDataEntity> => {
    return apiClient.patch<MasterDataEntity>(ENDPOINTS.ENTITIES.UPDATE(id), data);
  },

  deleteEntity: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.ENTITIES.DELETE(id));
  },
};
