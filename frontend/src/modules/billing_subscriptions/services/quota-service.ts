/**
 * Quota Service
 */

import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';

export interface QuotaInfo {
  used: number;
  limit: number;
}

export interface Quotas {
  users: QuotaInfo;
  storage: QuotaInfo;
  api_calls: QuotaInfo;
}

export const quotaService = {
  /**
   * Get current quota usage and limits
   */
  getQuotas: async (): Promise<Quotas> => {
    return apiClient.get<Quotas>(ENDPOINTS.QUOTAS.GET);
  },
};
