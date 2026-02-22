/**
 * Bank Reconciliation Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { BankAccount, BankAccountCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const bankReconciliationService = {
  listBankAccounts: async (): Promise<BankAccount[]> => {
    const response = await apiClient.get<BankAccount[] | { results: BankAccount[] }>(
      ENDPOINTS.ACCOUNTS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getBankAccount: async (id: string): Promise<BankAccount> => {
    return apiClient.get<BankAccount>(ENDPOINTS.ACCOUNTS.DETAIL(id));
  },

  createBankAccount: async (data: BankAccountCreate): Promise<BankAccount> => {
    return apiClient.post<BankAccount>(ENDPOINTS.ACCOUNTS.CREATE, data);
  },

  updateBankAccount: async (
    id: string,
    data: Partial<BankAccountCreate>
  ): Promise<BankAccount> => {
    return apiClient.patch<BankAccount>(ENDPOINTS.ACCOUNTS.UPDATE(id), data);
  },

  deleteBankAccount: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.ACCOUNTS.DELETE(id));
  },
};
