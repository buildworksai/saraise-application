/**
 * Purchase Management Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Supplier, SupplierCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const purchaseService = {
  listSuppliers: async (): Promise<Supplier[]> => {
    const response = await apiClient.get<Supplier[] | { results: Supplier[] }>(
      ENDPOINTS.SUPPLIERS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getSupplier: async (id: string): Promise<Supplier> => {
    return apiClient.get<Supplier>(ENDPOINTS.SUPPLIERS.DETAIL(id));
  },

  createSupplier: async (data: SupplierCreate): Promise<Supplier> => {
    return apiClient.post<Supplier>(ENDPOINTS.SUPPLIERS.CREATE, data);
  },

  updateSupplier: async (id: string, data: Partial<SupplierCreate>): Promise<Supplier> => {
    return apiClient.patch<Supplier>(ENDPOINTS.SUPPLIERS.UPDATE(id), data);
  },

  deleteSupplier: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.SUPPLIERS.DELETE(id));
  },
};
