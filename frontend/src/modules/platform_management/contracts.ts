/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Platform Management Module Contracts
 *
 * Defines all types and API endpoints for the Platform Management module.
 *
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */

// ==========================================
// Types
// ==========================================

export interface PlatformSetting {
  id: string;
  key: string;
  value: string;
  description?: string;
  is_secret: boolean;
  tenant_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlatformSettingCreate {
  key: string;
  value: string;
  description?: string;
  is_secret?: boolean;
  tenant_id?: string | null;
}

export interface FeatureFlag {
  id: string;
  key: string;
  enabled: boolean;
  description?: string;
  tenant_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeatureFlagCreate {
  key: string;
  enabled?: boolean;
  description?: string;
  tenant_id?: string | null;
}

export interface SystemHealth {
  service: string;
  status: "healthy" | "degraded" | "unhealthy";
  latency_ms: number;
  last_check: string;
  details?: Record<string, unknown>;
}

export interface HealthSummary {
  status: "healthy" | "degraded" | "unhealthy";
  healthy: number;
  degraded: number;
  unhealthy: number;
  total: number;
  timestamp: string;
}

export interface PlatformAuditEvent {
  id: string;
  action: string;
  actor_id: string;
  resource_type?: string;
  resource_id?: string;
  details?: Record<string, unknown>;
  timestamp: string;
  tenant_id?: string | null;
}

export interface PlatformMetrics {
  id: string;
  metric_type: string;
  time_range: string;
  metrics_data: Record<string, unknown>;
  recorded_at: string;
  created_by?: string;
}

export interface PlatformMetricsRequest {
  metric_type: string;
  time_range: string;
}

// ==========================================
// License Types
// ==========================================

export interface ModuleLicense {
  module_id: string;
  module_name: string;
  tier_required: string;
  is_licensed: boolean;
  expires_at?: string;
  features: string[];
}

export interface LicenseInfo {
  organization_name: string;
  tier: string;
  status: string;
  expires_at: string;
  days_remaining: number;
  is_valid: boolean;
  features: Array<{
    module: string;
    licensed: boolean;
    tier_required: string;
  }>;
}

export interface LicenseActivationRequest {
  license_key: string;
}

// ==========================================
// Endpoints
// ==========================================

export const MODULE_API_PREFIX = "/api/v1/platform";

export const ENDPOINTS = {
  SETTINGS: {
    LIST: `${MODULE_API_PREFIX}/settings/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/settings/${id}/`,
    CREATE: `${MODULE_API_PREFIX}/settings/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/settings/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/settings/${id}/`,
  },
  FEATURE_FLAGS: {
    LIST: `${MODULE_API_PREFIX}/feature-flags/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/feature-flags/${id}/`,
    CREATE: `${MODULE_API_PREFIX}/feature-flags/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/feature-flags/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/feature-flags/${id}/`,
  },
  HEALTH: {
    LIST: `${MODULE_API_PREFIX}/health/`,
    SUMMARY: `${MODULE_API_PREFIX}/health/summary/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/health/${id}/`,
  },
  AUDIT_EVENTS: {
    LIST: `${MODULE_API_PREFIX}/audit-events/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/audit-events/${id}/`,
  },
  METRICS: {
    LIST: `${MODULE_API_PREFIX}/metrics/`,
    CURRENT: `${MODULE_API_PREFIX}/metrics/current/`,
    SAVE: `${MODULE_API_PREFIX}/metrics/save/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/metrics/${id}/`,
  },
  LICENSING: {
    STATUS: "/api/v1/licensing/status/",
    ACTIVATE: "/api/v1/licensing/activate/",
    SYNC: "/api/v1/licensing/sync/",
  },
} as const;
