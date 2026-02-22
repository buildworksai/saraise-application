/**
 * Inventory Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Inventory Management are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Warehouse - Physical storage location */
export type Warehouse = {
  id: string;
  tenant_id: string;
  warehouse_code: string;
  warehouse_name: string;
  warehouse_type: string;
  address?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Warehouse create request */
export type WarehouseCreate = {
  warehouse_code: string;
  warehouse_name: string;
  warehouse_type: string;
  address?: string;
  is_active?: boolean;
};

/** Item - Stock item / Product / SKU */
export type Item = {
  id: string;
  tenant_id: string;
  item_code: string;
  item_name: string;
  description?: string;
  category?: string;
  barcode?: string;
  has_batch_no: boolean;
  has_serial_no: boolean;
  valuation_method: string;
  reorder_point?: string;
  reorder_qty?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Stock Entry - Stock movement transaction */
export type StockEntry = {
  id: string;
  tenant_id: string;
  entry_number: string;
  entry_type: 'receipt' | 'issue' | 'transfer' | 'adjustment' | 'manufacturing' | 'return' | 'scrap';
  posting_date: string;
  warehouse: string;
  reference_document?: string;
  status: string;
  created_at: string;
  updated_at: string;
};

/** Stock Balance - Current stock level per item per warehouse */
export type StockBalance = {
  id: string;
  tenant_id: string;
  item: string;
  warehouse: string;
  quantity_on_hand: string;
  quantity_allocated: string;
  quantity_available: string;
  stock_value: string;
  valuation_rate?: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/inventory-management';

export const ENDPOINTS = {
  WAREHOUSES: {
    LIST: `${MODULE_API_PREFIX}/warehouses/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/warehouses/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/warehouses/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/warehouses/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/warehouses/${id}/` as const,
  },
  ITEMS: {
    LIST: `${MODULE_API_PREFIX}/items/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/items/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/items/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/items/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/items/${id}/` as const,
  },
  STOCK_ENTRIES: {
    LIST: `${MODULE_API_PREFIX}/stock-entries/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/stock-entries/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/stock-entries/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/stock-entries/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/stock-entries/${id}/` as const,
  },
  STOCK_BALANCES: {
    LIST: `${MODULE_API_PREFIX}/stock-balances/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/stock-balances/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/stock-balances/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/stock-balances/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/stock-balances/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
