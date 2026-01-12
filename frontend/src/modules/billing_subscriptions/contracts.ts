/**
 * BillingSubscriptions Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for BillingSubscriptions are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** SubscriptionPlan entity */
export type SubscriptionPlan = {
  id: string;
  name: string;
  description?: string;
  price: string;
  billing_cycle: 'monthly' | 'yearly';
  features: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Subscription entity */
export type Subscription = {
  id: string;
  tenant_id: string;
  plan: string;
  plan_id?: string;
  status: 'active' | 'cancelled' | 'expired' | 'pending';
  current_period_start: string;
  current_period_end: string;
  created_at: string;
  updated_at: string;
};

/** Subscription create request */
export type SubscriptionCreate = {
  plan: string;
  billing_cycle?: 'monthly' | 'yearly';
};

/** Subscription update request (partial) */
export type SubscriptionUpdate = Partial<SubscriptionCreate>;

/** Invoice entity */
export type Invoice = {
  id: string;
  tenant_id: string;
  subscription: string;
  subscription_id?: string;
  invoice_number: string;
  amount: string;
  status: 'draft' | 'open' | 'paid' | 'void';
  due_date: string;
  created_at: string;
  updated_at: string;
};

/** InvoiceLineItem entity */
export type InvoiceLineItem = {
  id: string;
  invoice: string;
  invoice_id?: string;
  description: string;
  quantity: number;
  unit_price: string;
  total: string;
  created_at: string;
  updated_at: string;
};

/** Payment entity */
export type Payment = {
  id: string;
  tenant_id: string;
  invoice: string;
  invoice_id?: string;
  amount: string;
  status: 'pending' | 'completed' | 'failed' | 'refunded';
  payment_method: string;
  transaction_id?: string;
  created_at: string;
  updated_at: string;
};

/** Payment create request */
export type PaymentCreate = {
  invoice: string;
  amount: string;
  payment_method: string;
};

/** UsageRecord entity */
export type UsageRecord = {
  id: string;
  tenant_id: string;
  subscription: string;
  subscription_id?: string;
  metric: string;
  quantity: number;
  period_start: string;
  period_end: string;
  created_at: string;
  updated_at: string;
};

/** UsageRecord create request */
export type UsageRecordCreate = {
  subscription: string;
  metric: string;
  quantity: number;
  period_start: string;
  period_end: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * BillingSubscriptions API Endpoints
 *
 * All endpoints should be prefixed with /api/v1/billing-subscriptions/
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS } from './contracts';
 * apiClient.get(ENDPOINTS.PLANS.LIST);
 * apiClient.get(ENDPOINTS.SUBSCRIPTIONS.DETAIL(id));
 * ```
 */
export const MODULE_API_PREFIX = '/api/v1/billing-subscriptions';

export const ENDPOINTS = {
  PLANS: {
    LIST: `${MODULE_API_PREFIX}/plans/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/plans/${id}/` as const,
  },
  SUBSCRIPTIONS: {
    LIST: `${MODULE_API_PREFIX}/subscriptions/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/subscriptions/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/subscriptions/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/subscriptions/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/subscriptions/${id}/` as const,
    CANCEL: (id: string) => `${MODULE_API_PREFIX}/subscriptions/${id}/cancel/` as const,
    UPGRADE: (id: string) => `${MODULE_API_PREFIX}/subscriptions/${id}/upgrade/` as const,
  },
  INVOICES: {
    LIST: `${MODULE_API_PREFIX}/invoices/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/invoices/${id}/` as const,
    PDF: (id: string) => `${MODULE_API_PREFIX}/invoices/${id}/pdf/` as const,
  },
  PAYMENTS: {
    LIST: `${MODULE_API_PREFIX}/payments/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/payments/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/payments/`,
  },
  USAGE_RECORDS: {
    LIST: `${MODULE_API_PREFIX}/usage-records/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/usage-records/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/usage-records/`,
  },
  QUOTAS: {
    GET: `${MODULE_API_PREFIX}/quotas/`,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
