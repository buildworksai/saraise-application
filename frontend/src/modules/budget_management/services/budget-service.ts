/**
 * Budget Management Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Budget, BudgetCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const budgetService = {
  listBudgets: async (): Promise<Budget[]> => {
    const response = await apiClient.get<Budget[] | { results: Budget[] }>(
      ENDPOINTS.BUDGETS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getBudget: async (id: string): Promise<Budget> => {
    return apiClient.get<Budget>(ENDPOINTS.BUDGETS.DETAIL(id));
  },

  createBudget: async (data: BudgetCreate): Promise<Budget> => {
    return apiClient.post<Budget>(ENDPOINTS.BUDGETS.CREATE, data);
  },

  updateBudget: async (id: string, data: Partial<BudgetCreate>): Promise<Budget> => {
    return apiClient.patch<Budget>(ENDPOINTS.BUDGETS.UPDATE(id), data);
  },

  deleteBudget: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.BUDGETS.DELETE(id));
  },
};
