/**
 * Accounting & Finance Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Account, AccountCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const accountingService = {
  listAccounts: async (): Promise<Account[]> => {
    const response = await apiClient.get<Account[] | { results: Account[] }>(
      ENDPOINTS.ACCOUNTS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getAccount: async (id: string): Promise<Account> => {
    return apiClient.get<Account>(ENDPOINTS.ACCOUNTS.DETAIL(id));
  },

  createAccount: async (data: AccountCreate): Promise<Account> => {
    return apiClient.post<Account>(ENDPOINTS.ACCOUNTS.CREATE, data);
  },

  updateAccount: async (id: string, data: Partial<AccountCreate>): Promise<Account> => {
    return apiClient.patch<Account>(ENDPOINTS.ACCOUNTS.UPDATE(id), data);
  },

  deleteAccount: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.ACCOUNTS.DELETE(id));
  },
};
