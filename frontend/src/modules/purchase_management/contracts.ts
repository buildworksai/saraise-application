/**
 * Purchase Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Purchase Management are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Supplier - Vendor entity */
export type Supplier = {
  id: string;
  tenant_id: string;
  supplier_code: string;
  supplier_name: string;
  email?: string;
  phone?: string;
  address?: string;
  payment_terms: string;
  currency: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Supplier create request */
export type SupplierCreate = {
  supplier_code: string;
  supplier_name: string;
  email?: string;
  phone?: string;
  address?: string;
  payment_terms: string;
  currency: string;
  is_active?: boolean;
};

/** Purchase Requisition - Internal purchase request */
export type PurchaseRequisition = {
  id: string;
  tenant_id: string;
  requisition_number: string;
  requisition_date: string;
  required_date: string;
  purpose?: string;
  status: 'draft' | 'pending_approval' | 'approved' | 'rejected' | 'converted' | 'cancelled';
  requested_by?: string;
  approved_by?: string;
  approved_at?: string;
  created_at: string;
  updated_at: string;
};

/** Purchase Order - PO to supplier */
export type PurchaseOrder = {
  id: string;
  tenant_id: string;
  po_number: string;
  po_date: string;
  supplier: string;
  expected_delivery_date?: string;
  total_amount: string;
  currency: string;
  status: 'draft' | 'pending_approval' | 'approved' | 'sent' | 'acknowledged' | 'partially_received' | 'received' | 'cancelled';
  requisition?: string;
  approved_by?: string;
  approved_at?: string;
  created_at: string;
  updated_at: string;
};

/** Purchase Receipt - Goods receipt from supplier */
export type PurchaseReceipt = {
  id: string;
  tenant_id: string;
  receipt_number: string;
  receipt_date: string;
  purchase_order: string;
  warehouse_id: string;
  status: 'draft' | 'completed' | 'cancelled';
  received_by?: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/purchase-management';

export const ENDPOINTS = {
  SUPPLIERS: {
    LIST: `${MODULE_API_PREFIX}/suppliers/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/suppliers/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/suppliers/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/suppliers/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/suppliers/${id}/` as const,
  },
  REQUISITIONS: {
    LIST: `${MODULE_API_PREFIX}/requisitions/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/requisitions/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/requisitions/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/requisitions/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/requisitions/${id}/` as const,
  },
  PURCHASE_ORDERS: {
    LIST: `${MODULE_API_PREFIX}/purchase-orders/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/purchase-orders/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/purchase-orders/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/purchase-orders/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/purchase-orders/${id}/` as const,
  },
  RECEIPTS: {
    LIST: `${MODULE_API_PREFIX}/receipts/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/receipts/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/receipts/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/receipts/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/receipts/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
