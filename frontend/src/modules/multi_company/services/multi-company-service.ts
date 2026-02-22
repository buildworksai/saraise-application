/**
 * Multi-Company Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Company, CompanyCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const multiCompanyService = {
  listCompanies: async (): Promise<Company[]> => {
    const response = await apiClient.get<Company[] | { results: Company[] }>(
      ENDPOINTS.COMPANIES.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getCompany: async (id: string): Promise<Company> => {
    return apiClient.get<Company>(ENDPOINTS.COMPANIES.DETAIL(id));
  },

  createCompany: async (data: CompanyCreate): Promise<Company> => {
    return apiClient.post<Company>(ENDPOINTS.COMPANIES.CREATE, data);
  },

  updateCompany: async (id: string, data: Partial<CompanyCreate>): Promise<Company> => {
    return apiClient.patch<Company>(ENDPOINTS.COMPANIES.UPDATE(id), data);
  },

  deleteCompany: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.COMPANIES.DELETE(id));
  },
};
