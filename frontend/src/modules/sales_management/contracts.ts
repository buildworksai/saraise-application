/**
 * Sales Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Sales Management are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Customer - Buyer entity */
export type Customer = {
  id: string;
  tenant_id: string;
  customer_code: string;
  customer_name: string;
  email?: string;
  phone?: string;
  address?: string;
  credit_limit?: string;
  currency: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Customer create request */
export type CustomerCreate = {
  customer_code: string;
  customer_name: string;
  email?: string;
  phone?: string;
  address?: string;
  credit_limit?: string;
  currency: string;
  is_active?: boolean;
};

/** Quotation - Sales quote (pre-order) */
export type Quotation = {
  id: string;
  tenant_id: string;
  quotation_number: string;
  quotation_date: string;
  valid_until?: string;
  customer: string;
  total_amount: string;
  currency: string;
  status: 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired' | 'converted';
  created_at: string;
  updated_at: string;
};

/** Sales Order - Confirmed customer order */
export type SalesOrder = {
  id: string;
  tenant_id: string;
  order_number: string;
  order_date: string;
  delivery_date?: string;
  customer: string;
  quotation?: string;
  total_amount: string;
  currency: string;
  status: 'draft' | 'confirmed' | 'picking' | 'packing' | 'ready_to_ship' | 'shipped' | 'delivered' | 'invoiced' | 'cancelled';
  warehouse_id?: string;
  created_at: string;
  updated_at: string;
};

/** Delivery Note - Shipment record */
export type DeliveryNote = {
  id: string;
  tenant_id: string;
  delivery_number: string;
  delivery_date: string;
  sales_order: string;
  warehouse_id: string;
  status: 'draft' | 'completed' | 'cancelled';
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/sales-management';

export const ENDPOINTS = {
  CUSTOMERS: {
    LIST: `${MODULE_API_PREFIX}/customers/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/customers/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/customers/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/customers/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/customers/${id}/` as const,
  },
  QUOTATIONS: {
    LIST: `${MODULE_API_PREFIX}/quotations/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/quotations/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/quotations/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/quotations/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/quotations/${id}/` as const,
  },
  SALES_ORDERS: {
    LIST: `${MODULE_API_PREFIX}/sales-orders/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/sales-orders/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/sales-orders/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/sales-orders/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/sales-orders/${id}/` as const,
  },
  DELIVERY_NOTES: {
    LIST: `${MODULE_API_PREFIX}/delivery-notes/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/delivery-notes/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/delivery-notes/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/delivery-notes/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/delivery-notes/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
