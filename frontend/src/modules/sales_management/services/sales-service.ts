/**
 * Sales Management Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Customer, CustomerCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const salesService = {
  listCustomers: async (): Promise<Customer[]> => {
    const response = await apiClient.get<Customer[] | { results: Customer[] }>(
      ENDPOINTS.CUSTOMERS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getCustomer: async (id: string): Promise<Customer> => {
    return apiClient.get<Customer>(ENDPOINTS.CUSTOMERS.DETAIL(id));
  },

  createCustomer: async (data: CustomerCreate): Promise<Customer> => {
    return apiClient.post<Customer>(ENDPOINTS.CUSTOMERS.CREATE, data);
  },

  updateCustomer: async (id: string, data: Partial<CustomerCreate>): Promise<Customer> => {
    return apiClient.patch<Customer>(ENDPOINTS.CUSTOMERS.UPDATE(id), data);
  },

  deleteCustomer: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.CUSTOMERS.DELETE(id));
  },
};
