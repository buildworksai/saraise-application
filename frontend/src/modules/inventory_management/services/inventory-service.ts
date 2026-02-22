/**
 * Inventory Management Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Warehouse, WarehouseCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const inventoryService = {
  listWarehouses: async (): Promise<Warehouse[]> => {
    const response = await apiClient.get<Warehouse[] | { results: Warehouse[] }>(
      ENDPOINTS.WAREHOUSES.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getWarehouse: async (id: string): Promise<Warehouse> => {
    return apiClient.get<Warehouse>(ENDPOINTS.WAREHOUSES.DETAIL(id));
  },

  createWarehouse: async (data: WarehouseCreate): Promise<Warehouse> => {
    return apiClient.post<Warehouse>(ENDPOINTS.WAREHOUSES.CREATE, data);
  },

  updateWarehouse: async (id: string, data: Partial<WarehouseCreate>): Promise<Warehouse> => {
    return apiClient.patch<Warehouse>(ENDPOINTS.WAREHOUSES.UPDATE(id), data);
  },

  deleteWarehouse: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.WAREHOUSES.DELETE(id));
  },
};
