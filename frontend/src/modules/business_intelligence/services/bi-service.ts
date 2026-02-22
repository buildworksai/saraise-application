/**
 * Business Intelligence Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Report, ReportCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const biService = {
  listReports: async (): Promise<Report[]> => {
    const response = await apiClient.get<Report[] | { results: Report[] }>(
      ENDPOINTS.REPORTS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getReport: async (id: string): Promise<Report> => {
    return apiClient.get<Report>(ENDPOINTS.REPORTS.DETAIL(id));
  },

  createReport: async (data: ReportCreate): Promise<Report> => {
    return apiClient.post<Report>(ENDPOINTS.REPORTS.CREATE, data);
  },

  updateReport: async (id: string, data: Partial<ReportCreate>): Promise<Report> => {
    return apiClient.patch<Report>(ENDPOINTS.REPORTS.UPDATE(id), data);
  },

  deleteReport: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.REPORTS.DELETE(id));
  },
};
