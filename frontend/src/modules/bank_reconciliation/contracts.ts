/**
 * Bank Reconciliation Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Bank Reconciliation are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Bank Account - Bank account for reconciliation */
export type BankAccount = {
  id: string;
  tenant_id: string;
  account_number: string;
  bank_name: string;
  account_name: string;
  account_type: string;
  currency: string;
  ledger_account_id?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Bank Account create request */
export type BankAccountCreate = {
  account_number: string;
  bank_name: string;
  account_name: string;
  account_type: string;
  currency: string;
  ledger_account_id?: string;
  is_active?: boolean;
};

/** Bank Statement - Imported bank statement */
export type BankStatement = {
  id: string;
  tenant_id: string;
  bank_account: string;
  statement_date: string;
  opening_balance: string;
  closing_balance: string;
  is_reconciled: boolean;
  created_at: string;
  updated_at: string;
};

/** Bank Transaction - Individual transaction in a statement */
export type BankTransaction = {
  id: string;
  tenant_id: string;
  bank_statement: string;
  transaction_date: string;
  description: string;
  amount: string;
  transaction_type: 'debit' | 'credit';
  reference_number?: string;
  is_reconciled: boolean;
  matched_payment_id?: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/bank-reconciliation';

export const ENDPOINTS = {
  ACCOUNTS: {
    LIST: `${MODULE_API_PREFIX}/accounts/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/accounts/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const,
  },
  STATEMENTS: {
    LIST: `${MODULE_API_PREFIX}/statements/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/statements/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/statements/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/statements/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/statements/${id}/` as const,
  },
  TRANSACTIONS: {
    LIST: `${MODULE_API_PREFIX}/transactions/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/transactions/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/transactions/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/transactions/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/transactions/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
