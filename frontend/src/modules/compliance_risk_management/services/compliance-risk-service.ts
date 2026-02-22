/**
 * Compliance Risk Management Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { ComplianceRisk, ComplianceRiskCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const complianceRiskService = {
  listRisks: async (): Promise<ComplianceRisk[]> => {
    const response = await apiClient.get<ComplianceRisk[] | { results: ComplianceRisk[] }>(
      ENDPOINTS.RISKS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getRisk: async (id: string): Promise<ComplianceRisk> => {
    return apiClient.get<ComplianceRisk>(ENDPOINTS.RISKS.DETAIL(id));
  },

  createRisk: async (data: ComplianceRiskCreate): Promise<ComplianceRisk> => {
    return apiClient.post<ComplianceRisk>(ENDPOINTS.RISKS.CREATE, data);
  },

  updateRisk: async (
    id: string,
    data: Partial<ComplianceRiskCreate>
  ): Promise<ComplianceRisk> => {
    return apiClient.patch<ComplianceRisk>(ENDPOINTS.RISKS.UPDATE(id), data);
  },

  deleteRisk: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.RISKS.DELETE(id));
  },
};
