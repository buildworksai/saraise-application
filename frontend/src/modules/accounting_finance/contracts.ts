/**
 * Accounting & Finance Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Accounting & Finance are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Chart of Accounts - Ledger account */
export type Account = {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  account_type: 'asset' | 'liability' | 'equity' | 'revenue' | 'expense';
  parent_account_id?: string;
  is_active: boolean;
  description?: string;
  created_at: string;
  updated_at: string;
};

/** Account create request */
export type AccountCreate = {
  code: string;
  name: string;
  account_type: string;
  parent_account_id?: string;
  is_active?: boolean;
  description?: string;
};

/** Posting period for financial transactions */
export type PostingPeriod = {
  id: string;
  tenant_id: string;
  period_name: string;
  start_date: string;
  end_date: string;
  status: 'open' | 'closed';
  created_at: string;
  updated_at: string;
};

/** Journal entry */
export type JournalEntry = {
  id: string;
  tenant_id: string;
  entry_number: string;
  posting_date: string;
  posting_period: string;
  description?: string;
  status: 'draft' | 'posted' | 'reversed';
  debit_total: string;
  credit_total: string;
  posted_at?: string;
  posted_by?: string;
  created_at: string;
  updated_at: string;
};

/** AP Invoice (Accounts Payable) */
export type APInvoice = {
  id: string;
  tenant_id: string;
  invoice_number: string;
  supplier_id: string;
  invoice_date: string;
  due_date: string;
  amount: string;
  tax_amount: string;
  total_amount: string;
  paid_amount: string;
  status: 'draft' | 'pending' | 'partially_paid' | 'paid' | 'cancelled';
  currency: string;
  description?: string;
  created_at: string;
  updated_at: string;
};

/** AR Invoice (Accounts Receivable) */
export type ARInvoice = {
  id: string;
  tenant_id: string;
  invoice_number: string;
  customer_id: string;
  invoice_date: string;
  due_date: string;
  amount: string;
  tax_amount: string;
  total_amount: string;
  paid_amount: string;
  status: 'draft' | 'pending' | 'partially_paid' | 'paid' | 'overdue' | 'cancelled';
  currency: string;
  description?: string;
  created_at: string;
  updated_at: string;
};

/** Payment */
export type Payment = {
  id: string;
  tenant_id: string;
  payment_date: string;
  amount: string;
  payment_method: string;
  currency: string;
  reference_number?: string;
  ap_invoice?: string;
  ar_invoice?: string;
  description?: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/accounting-finance';

export const ENDPOINTS = {
  ACCOUNTS: {
    LIST: `${MODULE_API_PREFIX}/accounts/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/accounts/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const,
  },
  POSTING_PERIODS: {
    LIST: `${MODULE_API_PREFIX}/posting-periods/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/posting-periods/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/posting-periods/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/posting-periods/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/posting-periods/${id}/` as const,
  },
  JOURNAL_ENTRIES: {
    LIST: `${MODULE_API_PREFIX}/journal-entries/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/journal-entries/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/journal-entries/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/journal-entries/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/journal-entries/${id}/` as const,
  },
  AP_INVOICES: {
    LIST: `${MODULE_API_PREFIX}/ap-invoices/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/ap-invoices/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/` as const,
  },
  AR_INVOICES: {
    LIST: `${MODULE_API_PREFIX}/ar-invoices/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/ar-invoices/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/ar-invoices/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/ar-invoices/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/ar-invoices/${id}/` as const,
  },
  PAYMENTS: {
    LIST: `${MODULE_API_PREFIX}/payments/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/payments/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/payments/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/payments/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/payments/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
