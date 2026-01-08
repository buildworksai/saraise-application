/**
 * Platform Management Module - Type Contracts & Endpoint Registry
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Platform Management are defined here.
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
 * @module platform_management/contracts
 */

import type { components } from '@/types/api';

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Platform setting entity */
export type PlatformSetting = components['schemas']['PlatformSetting'];

/** Request body for creating a platform setting */
export type PlatformSettingCreate = components['schemas']['PlatformSettingCreate'];

/** Request body for creating a platform setting (API request format) */
export type PlatformSettingCreateRequest = components['schemas']['PlatformSettingCreateRequest'];

/** Request body for updating a platform setting (partial) */
export type PlatformSettingUpdate = components['schemas']['PatchedPlatformSettingCreateRequest'];

/** Feature flag entity */
export type FeatureFlag = components['schemas']['FeatureFlag'];

/** Request body for creating a feature flag */
export type FeatureFlagCreate = components['schemas']['FeatureFlagCreate'];

/** Request body for creating a feature flag (API request format) */
export type FeatureFlagCreateRequest = components['schemas']['FeatureFlagCreateRequest'];

/** Request body for updating a feature flag (partial) */
export type FeatureFlagUpdate = components['schemas']['PatchedFeatureFlagCreateRequest'];

/** System health status entity */
export type SystemHealth = components['schemas']['SystemHealth'];

/** System health status enum values */
export type SystemHealthStatus = components['schemas']['SystemHealthStatusEnum'];

/** Platform audit event entity */
export type PlatformAuditEvent = components['schemas']['PlatformAuditEvent'];

/** Data type enum for settings */
export type DataType = components['schemas']['DataTypeEnum'];

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * Platform Management API Endpoints
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS } from './contracts';
 * apiClient.get<PlatformSetting[]>(ENDPOINTS.SETTINGS.LIST);
 * apiClient.get<PlatformSetting>(ENDPOINTS.SETTINGS.DETAIL('uuid'));
 * ```
 */
export const ENDPOINTS = {
  /** Platform Settings endpoints */
  SETTINGS: {
    /** GET - List all platform settings */
    LIST: '/api/v1/platform/settings/',
    /** GET - Get setting by ID */
    DETAIL: (id: string) => `/api/v1/platform/settings/${id}/` as const,
    /** POST - Create new setting */
    CREATE: '/api/v1/platform/settings/',
    /** PATCH - Update setting by ID */
    UPDATE: (id: string) => `/api/v1/platform/settings/${id}/` as const,
    /** DELETE - Delete setting by ID */
    DELETE: (id: string) => `/api/v1/platform/settings/${id}/` as const,
  },

  /** Feature Flags endpoints */
  FEATURE_FLAGS: {
    /** GET - List all feature flags */
    LIST: '/api/v1/platform/feature-flags/',
    /** GET - Get feature flag by ID */
    DETAIL: (id: string) => `/api/v1/platform/feature-flags/${id}/` as const,
    /** POST - Create new feature flag */
    CREATE: '/api/v1/platform/feature-flags/',
    /** PATCH - Update feature flag by ID */
    UPDATE: (id: string) => `/api/v1/platform/feature-flags/${id}/` as const,
    /** POST - Toggle feature flag */
    TOGGLE: (id: string) => `/api/v1/platform/feature-flags/${id}/toggle/` as const,
    /** DELETE - Delete feature flag by ID */
    DELETE: (id: string) => `/api/v1/platform/feature-flags/${id}/` as const,
  },

  /** System Health endpoints */
  HEALTH: {
    /** GET - List all health records */
    LIST: '/api/v1/platform/health/',
    /** GET - Get health record by ID */
    DETAIL: (id: string) => `/api/v1/platform/health/${id}/` as const,
    /** GET - Get health summary */
    SUMMARY: '/api/v1/platform/health/summary/',
  },

  /** Platform Audit Events endpoints */
  AUDIT_EVENTS: {
    /** GET - List all audit events */
    LIST: '/api/v1/platform/audit-events/',
    /** GET - Get audit event by ID */
    DETAIL: (id: string) => `/api/v1/platform/audit-events/${id}/` as const,
  },

  /** Platform Metrics endpoints */
  METRICS: {
    /** GET - List all metrics records */
    LIST: '/api/v1/platform/metrics/',
    /** GET - Get metrics record by ID */
    DETAIL: (id: string) => `/api/v1/platform/metrics/${id}/` as const,
    /** GET - Get current metrics */
    CURRENT: '/api/v1/platform/metrics/current/',
    /** POST - Save metrics */
    SAVE: '/api/v1/platform/metrics/save/',
  },
} as const;

// =============================================================================
// TYPE GUARDS - Use for runtime type checking
// =============================================================================

/** Check if a value is a valid SystemHealthStatus */
export function isSystemHealthStatus(value: unknown): value is SystemHealthStatus {
  return value === 'healthy' || value === 'degraded' || value === 'unhealthy';
}

/** Check if a value is a valid DataType */
export function isDataType(value: unknown): value is DataType {
  return value === 'string' || value === 'integer' || value === 'boolean' || value === 'json';
}

// =============================================================================
// RESPONSE SHAPES - For custom API responses not in OpenAPI schema
// =============================================================================

/** Health summary response shape */
export interface HealthSummaryResponse {
  status: string;
  healthy: number;
  degraded: number;
  unhealthy: number;
  total: number;
  timestamp: string;
}

/** Platform alert (custom type for UI) */
export interface PlatformAlert {
  id?: string;
  title: string;
  description: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'active' | 'resolved';
  category?: string | null;
  source?: string | null;
  created_at?: string;
}

/** Aggregated platform health (for dashboard) */
export interface PlatformHealth {
  status: string;
  checks?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  timestamp?: string;
}

/** Platform metrics record */
export interface PlatformMetricsRecord {
  id?: string;
  metric_type?: string;
  time_range?: string;
  metrics_data?: unknown;
  recorded_at?: string;
  created_at?: string;
  updated_at?: string;
  created_by?: string | null;
  updated_by?: string | null;
}

/** Platform metrics timeseries point */
export interface MetricsTimeseriesPoint {
  timestamp: string;
  date: string;
  value: number | null;
}

/** Platform metrics timeseries response */
export interface MetricsTimeseries {
  metric_type: string;
  time_range: string;
  interval: string;
  data: Record<string, MetricsTimeseriesPoint[]>;
}

/** Alias for backward compatibility */
export type PlatformMetricsTimeseries = MetricsTimeseries;

// =============================================================================
// EXAMPLES - Reference for agents writing new code
// =============================================================================

/**
 * Example usage patterns for agents:
 *
 * ```typescript
 * // Importing types
 * import {
 *   PlatformSetting,
 *   PlatformSettingCreate,
 *   FeatureFlag,
 *   ENDPOINTS,
 * } from './contracts';
 *
 * // Using endpoints with apiClient
 * const settings = await apiClient.get<PlatformSetting[]>(ENDPOINTS.SETTINGS.LIST);
 * const setting = await apiClient.get<PlatformSetting>(ENDPOINTS.SETTINGS.DETAIL(id));
 * const created = await apiClient.post<PlatformSetting>(ENDPOINTS.SETTINGS.CREATE, data);
 *
 * // Using with TanStack Query
 * const { data } = useQuery({
 *   queryKey: ['platform', 'settings'],
 *   queryFn: () => apiClient.get<PlatformSetting[]>(ENDPOINTS.SETTINGS.LIST),
 * });
 * ```
 */

/**
 * EXAMPLES - Type-safe examples for AI agents
 * 
 * These examples use `satisfies` to ensure type correctness at compile time.
 */
export const EXAMPLES = {
  createSetting: {
    request: {
      key: 'theme',
      value: 'dark',
      description: 'UI theme preference',
      category: 'ui',
      data_type: 'string',
    } satisfies PlatformSettingCreate,
    response: {
      id: 'uuid-123',
      key: 'theme',
      value: 'dark',
      description: 'UI theme preference',
      category: 'ui',
      data_type: 'string',
      created_at: '2026-01-07T00:00:00Z',
      updated_at: '2026-01-07T00:00:00Z',
    } as PlatformSetting,
  },
  createFeatureFlag: {
    request: {
      name: 'new_dashboard',
      enabled: true,
      description: 'Enable new dashboard UI',
    } satisfies FeatureFlagCreate,
    response: {
      id: 'uuid-456',
      name: 'new_dashboard',
      enabled: true,
      description: 'Enable new dashboard UI',
      created_at: '2026-01-07T00:00:00Z',
      updated_at: '2026-01-07T00:00:00Z',
    } as FeatureFlag,
  },
} as const;

