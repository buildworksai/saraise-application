/**
 * Platform Management Service
 * 
 * Service client for Platform Management API endpoints.
 * Uses generated TypeScript types from OpenAPI schema.
 */

import { apiClient } from '@/services/api-client';
import type { components } from '@/types/api';

// Type aliases for cleaner code
type PlatformSetting = components['schemas']['PlatformSetting'];
type FeatureFlag = components['schemas']['FeatureFlag'];
type SystemHealth = components['schemas']['SystemHealth'];
type PlatformAuditEvent = components['schemas']['PlatformAuditEvent'];

// Request types
type PlatformSettingCreate = components['schemas']['PlatformSettingCreate'];
type PlatformSettingUpdate = components['schemas']['PatchedPlatformSettingCreateRequest'];
type FeatureFlagCreate = components['schemas']['FeatureFlagCreate'];
type FeatureFlagUpdate = components['schemas']['PatchedFeatureFlagCreateRequest'];

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

export interface PlatformHealth {
  status: string;
  checks?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  timestamp?: string;
}

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

export interface PlatformMetricsTimeseriesPoint {
  timestamp: string;
  date: string;
  value: number | null;
}

export interface PlatformMetricsTimeseries {
  metric_type: string;
  time_range: string;
  interval: string;
  data: Record<string, PlatformMetricsTimeseriesPoint[]>;
}

// Re-export types for use in components
export type {
  PlatformSetting,
  FeatureFlag,
  SystemHealth,
  PlatformAuditEvent,
  PlatformSettingCreate,
  PlatformSettingUpdate,
  FeatureFlagCreate,
  FeatureFlagUpdate,
};

export const platformService = {
  /**
   * Platform Settings
   */
  settings: {
    /**
     * List all platform settings
     */
    list: async (): Promise<PlatformSetting[]> => {
      return apiClient.get<PlatformSetting[]>('/api/v1/platform/settings/');
    },

    /**
     * Get setting by ID
     */
    get: async (id: string): Promise<PlatformSetting> => {
      return apiClient.get<PlatformSetting>(`/api/v1/platform/settings/${id}/`);
    },

    /**
     * Create setting
     */
    create: async (data: PlatformSettingCreate): Promise<PlatformSetting> => {
      return apiClient.post<PlatformSetting>('/api/v1/platform/settings/', data);
    },

    /**
     * Update setting
     */
    update: async (id: string, data: PlatformSettingUpdate): Promise<PlatformSetting> => {
      return apiClient.patch<PlatformSetting>(`/api/v1/platform/settings/${id}/`, data);
    },

    /**
     * Delete setting
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(`/api/v1/platform/settings/${id}/`);
    },
  },

  /**
   * Feature Flags
   */
  featureFlags: {
    /**
     * List all feature flags
     */
    list: async (): Promise<FeatureFlag[]> => {
      return apiClient.get<FeatureFlag[]>('/api/v1/platform/feature-flags/');
    },

    /**
     * Get feature flag by ID
     */
    get: async (id: string): Promise<FeatureFlag> => {
      return apiClient.get<FeatureFlag>(`/api/v1/platform/feature-flags/${id}/`);
    },

    /**
     * Create feature flag
     */
    create: async (data: FeatureFlagCreate): Promise<FeatureFlag> => {
      return apiClient.post<FeatureFlag>('/api/v1/platform/feature-flags/', data);
    },

    /**
     * Update feature flag
     */
    update: async (id: string, data: FeatureFlagUpdate): Promise<FeatureFlag> => {
      return apiClient.patch<FeatureFlag>(`/api/v1/platform/feature-flags/${id}/`, data);
    },

    /**
     * Toggle feature flag
     */
    toggle: async (id: string): Promise<FeatureFlag> => {
      return apiClient.post<FeatureFlag>(`/api/v1/platform/feature-flags/${id}/toggle/`);
    },

    /**
     * Delete feature flag
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(`/api/v1/platform/feature-flags/${id}/`);
    },
  },

  /**
   * System Health
   */
  health: {
    /**
     * List all health records
     */
    list: async (): Promise<SystemHealth[]> => {
      return apiClient.get<SystemHealth[]>('/api/v1/platform/health/');
    },

    /**
     * Get health summary
     */
    summary: async (): Promise<{
      status: string;
      healthy: number;
      degraded: number;
      unhealthy: number;
      total: number;
      timestamp: string;
    }> => {
      return apiClient.get('/api/v1/platform/health/summary/');
    },

    /**
     * Get health record by ID
     */
    get: async (id: string): Promise<SystemHealth> => {
      return apiClient.get<SystemHealth>(`/api/v1/platform/health/${id}/`);
    },

    /**
     * Get current health status with checks and metrics
     */
    getCurrent: async (): Promise<PlatformHealth> => {
      const [summary, records] = await Promise.all([
        platformService.health.summary(),
        platformService.health.list(),
      ]);

      const checks: Record<string, unknown> = {};
      records.forEach((record) => {
        if (record.service_name) {
          checks[record.service_name] = record.status ?? 'unknown';
        }
      });

      return {
        status: summary.status,
        checks,
        metrics: {},
        timestamp: summary.timestamp,
      };
    },
  },

  /**
   * Platform Audit Events
   */
  auditEvents: {
    /**
     * List all audit events
     */
    list: async (): Promise<PlatformAuditEvent[]> => {
      return apiClient.get<PlatformAuditEvent[]>('/api/v1/platform/audit-events/');
    },

    /**
     * Get audit event by ID
     */
    get: async (id: string): Promise<PlatformAuditEvent> => {
      return apiClient.get<PlatformAuditEvent>(`/api/v1/platform/audit-events/${id}/`);
    },
  },

  /**
   * Platform Metrics
   */
  metrics: {
    list: async (): Promise<PlatformMetricsRecord[]> => {
      return apiClient.get<PlatformMetricsRecord[]>('/api/v1/platform/metrics/');
    },

    get: async (id: string): Promise<PlatformMetricsRecord> => {
      return apiClient.get<PlatformMetricsRecord>(`/api/v1/platform/metrics/${id}/`);
    },

    getCurrent: async (timeRange: string, metricType: string): Promise<unknown> => {
      const response = await apiClient.get<{
        metrics_data?: unknown;
      }>(`/api/v1/platform/metrics/current/?time_range=${timeRange}&metric_type=${metricType}`);
      return response.metrics_data ?? {};
    },

    save: async (metricType: string, timeRange: string): Promise<PlatformMetricsRecord> => {
      return apiClient.post<PlatformMetricsRecord>('/api/v1/platform/metrics/save/', {
        metric_type: metricType,
        time_range: timeRange,
      });
    },

    getTimeseries: async (
      metricType: string,
      timeRange: string,
      interval: string
    ): Promise<PlatformMetricsTimeseries> => {
      return Promise.resolve({
        metric_type: metricType,
        time_range: timeRange,
        interval,
        data: {},
      });
    },
  },

  /**
   * Platform Alerts
   */
  alerts: {
    list: async (): Promise<PlatformAlert[]> => Promise.resolve([]),
    getActive: async (): Promise<PlatformAlert[]> => Promise.resolve([]),
    resolve: (id: string): Promise<PlatformAlert | null> => {
      void id;
      return Promise.resolve(null);
    },
  },
};
