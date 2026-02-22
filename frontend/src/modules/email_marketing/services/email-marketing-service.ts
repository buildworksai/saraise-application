/**
 * Email Marketing Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { EmailCampaign, EmailCampaignCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const emailMarketingService = {
  listCampaigns: async (): Promise<EmailCampaign[]> => {
    const response = await apiClient.get<
      EmailCampaign[] | { results: EmailCampaign[] }
    >(ENDPOINTS.CAMPAIGNS.LIST);
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getCampaign: async (id: string): Promise<EmailCampaign> => {
    return apiClient.get<EmailCampaign>(ENDPOINTS.CAMPAIGNS.DETAIL(id));
  },

  createCampaign: async (data: EmailCampaignCreate): Promise<EmailCampaign> => {
    return apiClient.post<EmailCampaign>(ENDPOINTS.CAMPAIGNS.CREATE, data);
  },

  updateCampaign: async (
    id: string,
    data: Partial<EmailCampaignCreate>
  ): Promise<EmailCampaign> => {
    return apiClient.patch<EmailCampaign>(ENDPOINTS.CAMPAIGNS.UPDATE(id), data);
  },

  deleteCampaign: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.CAMPAIGNS.DELETE(id));
  },
};
