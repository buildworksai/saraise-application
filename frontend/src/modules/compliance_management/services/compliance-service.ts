/**
 * Compliance Management Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { CompliancePolicy, CompliancePolicyCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const complianceService = {
  listPolicies: async (): Promise<CompliancePolicy[]> => {
    const response = await apiClient.get<
      CompliancePolicy[] | { results: CompliancePolicy[] }
    >(ENDPOINTS.POLICIES.LIST);
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getPolicy: async (id: string): Promise<CompliancePolicy> => {
    return apiClient.get<CompliancePolicy>(ENDPOINTS.POLICIES.DETAIL(id));
  },

  createPolicy: async (data: CompliancePolicyCreate): Promise<CompliancePolicy> => {
    return apiClient.post<CompliancePolicy>(ENDPOINTS.POLICIES.CREATE, data);
  },

  updatePolicy: async (
    id: string,
    data: Partial<CompliancePolicyCreate>
  ): Promise<CompliancePolicy> => {
    return apiClient.patch<CompliancePolicy>(ENDPOINTS.POLICIES.UPDATE(id), data);
  },

  deletePolicy: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.POLICIES.DELETE(id));
  },
};
