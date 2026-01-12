/**
 * Tenant Management Module - Type Contracts & Endpoint Registry
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Tenant Management are defined here.
 *
 * CRITICAL: This is a PLATFORM-LEVEL module.
 * Only platform owners can access these endpoints.
 *
 * DO NOT:
 * - Define ad-hoc types in page components
 * - Hardcode URL strings in service files
 * - Import directly from @/types/api in pages
 *
 * DO:
 * - Import types from this file
 * - Use ENDPOINTS constant for all API calls
 * - Add new types here when extending the module
 *
 * @module tenant_management/contracts
 */

import type { components } from '@/types/api';

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Tenant entity (full details) */
export type Tenant = components['schemas']['Tenant'];

/** Tenant entity (list view, lightweight) */
export type TenantList = components['schemas']['TenantList'];

/** Request body for creating a tenant */
export type TenantRequest = components['schemas']['TenantRequest'];

/** Request body for updating a tenant (partial) */
export type TenantUpdate = components['schemas']['PatchedTenantRequest'];

/** Tenant module entity */
export type TenantModule = components['schemas']['TenantModule'];

/** Request body for creating/updating tenant module */
export type TenantModuleRequest = components['schemas']['TenantModuleRequest'];

/** Request body for updating a tenant module (partial) */
export type TenantModuleUpdate = components['schemas']['PatchedTenantModuleRequest'];

/** Tenant resource usage entity */
export type TenantResourceUsage = components['schemas']['TenantResourceUsage'];

/** Tenant settings entity */
export type TenantSettings = components['schemas']['TenantSettings'];

/** Request body for creating/updating tenant settings */
export type TenantSettingsRequest = components['schemas']['TenantSettingsRequest'];

/** Request body for updating tenant settings (partial) */
export type TenantSettingsUpdate = components['schemas']['PatchedTenantSettingsRequest'];

/** Tenant health score entity */
export type TenantHealthScore = components['schemas']['TenantHealthScore'];

/** Tenant status enum */
export type TenantStatus = components['schemas']['StatusEd5Enum'];

/** Company size enum */
export type CompanySize = components['schemas']['CompanySizeEnum'];

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * Tenant Management API Endpoints
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS, Tenant } from './contracts';
 * apiClient.get<Tenant[]>(ENDPOINTS.TENANTS.LIST);
 * apiClient.get<Tenant>(ENDPOINTS.TENANTS.DETAIL('uuid'));
 * ```
 */
export const ENDPOINTS = {
  /** Tenant CRUD endpoints */
  TENANTS: {
    /** GET - List all tenants */
    LIST: '/api/v1/tenant-management/tenants/',
    /** GET - Get tenant by ID */
    DETAIL: (id: string) => `/api/v1/tenant-management/tenants/${id}/` as const,
    /** POST - Create new tenant */
    CREATE: '/api/v1/tenant-management/tenants/',
    /** PATCH - Update tenant by ID */
    UPDATE: (id: string) => `/api/v1/tenant-management/tenants/${id}/` as const,
    /** DELETE - Delete tenant by ID */
    DELETE: (id: string) => `/api/v1/tenant-management/tenants/${id}/` as const,
    /** POST - Suspend tenant */
    SUSPEND: (id: string) => `/api/v1/tenant-management/tenants/${id}/suspend/` as const,
    /** POST - Activate tenant */
    ACTIVATE: (id: string) => `/api/v1/tenant-management/tenants/${id}/activate/` as const,
    /** GET - Get tenant modules */
    MODULES: (id: string) => `/api/v1/tenant-management/tenants/${id}/modules/` as const,
    /** GET - Get tenant resource usage */
    RESOURCE_USAGE: (id: string) => `/api/v1/tenant-management/tenants/${id}/resource_usage/` as const,
    /** GET - Get tenant health scores */
    HEALTH_SCORES: (id: string) => `/api/v1/tenant-management/tenants/${id}/health_scores/` as const,
  },

  /** Tenant Module endpoints */
  MODULES: {
    /** GET - List all tenant modules */
    LIST: '/api/v1/tenant-management/modules/',
    /** GET - Get module by ID */
    DETAIL: (id: string) => `/api/v1/tenant-management/modules/${id}/` as const,
    /** POST - Create tenant module */
    CREATE: '/api/v1/tenant-management/modules/',
    /** PATCH - Update tenant module */
    UPDATE: (id: string) => `/api/v1/tenant-management/modules/${id}/` as const,
    /** DELETE - Delete tenant module */
    DELETE: (id: string) => `/api/v1/tenant-management/modules/${id}/` as const,
    /** POST - Enable module */
    ENABLE: (id: string) => `/api/v1/tenant-management/modules/${id}/enable/` as const,
    /** POST - Disable module */
    DISABLE: (id: string) => `/api/v1/tenant-management/modules/${id}/disable/` as const,
  },

  /** Tenant Resource Usage endpoints */
  RESOURCE_USAGE: {
    /** GET - List resource usage records */
    LIST: '/api/v1/tenant-management/resource-usage/',
    /** GET - Get resource usage by ID */
    DETAIL: (id: string) => `/api/v1/tenant-management/resource-usage/${id}/` as const,
  },

  /** Tenant Settings endpoints */
  SETTINGS: {
    /** GET - List tenant settings */
    LIST: '/api/v1/tenant-management/settings/',
    /** GET - Get setting by ID */
    DETAIL: (id: string) => `/api/v1/tenant-management/settings/${id}/` as const,
    /** POST - Create setting */
    CREATE: '/api/v1/tenant-management/settings/',
    /** PATCH - Update setting */
    UPDATE: (id: string) => `/api/v1/tenant-management/settings/${id}/` as const,
    /** DELETE - Delete setting */
    DELETE: (id: string) => `/api/v1/tenant-management/settings/${id}/` as const,
  },

  /** Tenant Health Score endpoints */
  HEALTH_SCORES: {
    /** GET - List health scores */
    LIST: '/api/v1/tenant-management/health-scores/',
    /** GET - Get health score by ID */
    DETAIL: (id: string) => `/api/v1/tenant-management/health-scores/${id}/` as const,
  },

  /** Health check endpoint */
  HEALTH: '/api/v1/tenant-management/health/',
} as const;

// =============================================================================
// TYPE GUARDS - Use for runtime type checking
// =============================================================================

/** Check if a value is a valid TenantStatus */
export function isTenantStatus(value: unknown): value is TenantStatus {
  return (
    value === 'trial' ||
    value === 'active' ||
    value === 'suspended' ||
    value === 'cancelled' ||
    value === 'archived'
  );
}

/** Check if a value is a valid CompanySize */
export function isCompanySize(value: unknown): value is CompanySize {
  return (
    value === '1-10' ||
    value === '11-50' ||
    value === '51-200' ||
    value === '201-500' ||
    value === '500+'
  );
}

// =============================================================================
// RESPONSE SHAPES - For custom API responses not in OpenAPI schema
// =============================================================================

/** Action response (for suspend/activate/enable/disable) */
export interface ActionResponse {
  status: string;
  message: string;
}

/** Tenant list query parameters */
export interface TenantListParams {
  status?: TenantStatus;
  subscription_plan_id?: string;
  search?: string;
}

/** Resource usage query parameters */
export interface ResourceUsageParams {
  tenant_id?: string;
  date_from?: string;
  date_to?: string;
}

/** Health scores query parameters */
export interface HealthScoresParams {
  tenant_id?: string;
  date_from?: string;
  date_to?: string;
  churn_risk_min?: number;
}

// =============================================================================
// DERIVED TYPES - Convenience types for common operations
// =============================================================================

/** Create tenant request (omit read-only fields) */
export type TenantCreate = Omit<Tenant, 'id' | 'created_at' | 'updated_at' | 'created_by'>;

/** Create tenant module request (omit read-only fields) */
export type TenantModuleCreate = Omit<TenantModule, 'id' | 'installed_at' | 'created_at' | 'updated_at'>;

/** Create tenant settings request (omit read-only fields) */
export type TenantSettingsCreate = Omit<TenantSettings, 'id' | 'created_at' | 'updated_at'>;

// =============================================================================
// EXAMPLES - Reference for agents writing new code
// =============================================================================

/**
 * Example usage patterns for agents:
 *
 * ```typescript
 * // Importing types
 * import {
 *   Tenant,
 *   TenantModule,
 *   TenantCreate,
 *   ENDPOINTS,
 *   ActionResponse,
 * } from './contracts';
 *
 * // Listing tenants with filters
 * const params = new URLSearchParams();
 * if (status) params.append('status', status);
 * const url = `${ENDPOINTS.TENANTS.LIST}?${params.toString()}`;
 * const tenants = await apiClient.get<Tenant[]>(url);
 *
 * // Getting a single tenant
 * const tenant = await apiClient.get<Tenant>(ENDPOINTS.TENANTS.DETAIL(tenantId));
 *
 * // Suspending a tenant
 * const result = await apiClient.post<ActionResponse>(ENDPOINTS.TENANTS.SUSPEND(tenantId));
 *
 * // Using with TanStack Query
 * const { data } = useQuery({
 *   queryKey: ['tenants', tenantId],
 *   queryFn: () => apiClient.get<Tenant>(ENDPOINTS.TENANTS.DETAIL(tenantId)),
 * });
 * ```
 */

/**
 * EXAMPLES - Type-safe examples for AI agents
 *
 * These examples use `satisfies` to ensure type correctness at compile time.
 */
export const EXAMPLES = {
  createTenant: {
    request: {
      name: 'Acme Corporation',
      slug: 'acme-corp',
      status: 'active',
      subscription_plan_id: 'plan-pro',
    } satisfies TenantRequest,
    response: {
      tenant_id: 'tenant-uuid-123',
      name: 'Acme Corporation',
      slug: 'acme-corp',
      status: 'active',
      subscription_plan_id: 'plan-pro',
      created_at: '2026-01-07T00:00:00Z',
      updated_at: '2026-01-07T00:00:00Z',
    } as Tenant,
  },
  suspendTenant: {
    request: {},
    response: {
      status: 'success',
      message: 'Tenant suspended successfully',
    },
  },
} as const;
