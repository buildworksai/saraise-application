/**
 * Tenant Management Module - Read-Only Contracts
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * Tenant lifecycle and configuration writes belong to the Control Plane.
 */

import type { components } from '@/types/api';

export type Tenant = components['schemas']['Tenant'];
export type TenantList = components['schemas']['TenantList'];
export type TenantModule = components['schemas']['TenantModule'];
export type TenantResourceUsage = components['schemas']['TenantResourceUsage'];
export type TenantSettings = components['schemas']['TenantSettings'];
export type TenantHealthScore = components['schemas']['TenantHealthScore'];
export type TenantStatus = components['schemas']['StatusEd5Enum'];
export type CompanySize = components['schemas']['CompanySizeEnum'];

export const ENDPOINTS = {
  TENANTS: {
    LIST: '/api/v1/tenant-management/tenants/',
    DETAIL: (id: string) => `/api/v1/tenant-management/tenants/${id}/` as const,
    MODULES: (id: string) => `/api/v1/tenant-management/tenants/${id}/modules/` as const,
    RESOURCE_USAGE: (id: string) => `/api/v1/tenant-management/tenants/${id}/resource_usage/` as const,
    HEALTH_SCORES: (id: string) => `/api/v1/tenant-management/tenants/${id}/health_scores/` as const,
  },
  MODULES: {
    LIST: '/api/v1/tenant-management/modules/',
    DETAIL: (id: string) => `/api/v1/tenant-management/modules/${id}/` as const,
  },
  RESOURCE_USAGE: {
    LIST: '/api/v1/tenant-management/resource-usage/',
    DETAIL: (id: string) => `/api/v1/tenant-management/resource-usage/${id}/` as const,
  },
  SETTINGS: {
    LIST: '/api/v1/tenant-management/settings/',
    DETAIL: (id: string) => `/api/v1/tenant-management/settings/${id}/` as const,
  },
  HEALTH_SCORES: {
    LIST: '/api/v1/tenant-management/health-scores/',
    DETAIL: (id: string) => `/api/v1/tenant-management/health-scores/${id}/` as const,
  },
  HEALTH: '/api/v1/tenant-management/health/',
} as const;

export function isTenantStatus(value: unknown): value is TenantStatus {
  return (
    value === 'trial' ||
    value === 'active' ||
    value === 'suspended' ||
    value === 'cancelled' ||
    value === 'archived'
  );
}

export function isCompanySize(value: unknown): value is CompanySize {
  return (
    value === '1-10' ||
    value === '11-50' ||
    value === '51-200' ||
    value === '201-500' ||
    value === '500+'
  );
}

export interface TenantListParams {
  status?: TenantStatus;
  subscription_plan_id?: string;
  search?: string;
}

export interface ResourceUsageParams {
  tenant_id?: string;
  date_from?: string;
  date_to?: string;
}

export interface HealthScoresParams extends ResourceUsageParams {
  churn_risk_min?: number;
}
