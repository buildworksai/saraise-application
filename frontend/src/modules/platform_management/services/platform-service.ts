/**
 * Platform Management Service
 * 
 * Service client for Platform Management API endpoints.
 * 
 * MIGRATED: Now uses contracts.ts for types and endpoints.
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */

import { apiClient } from '@/services/api-client';
import type {
  PlatformSetting,
  FeatureFlag,
  SystemHealth,
  PlatformAuditEvent,
  PlatformSettingCreate,
  PlatformSettingUpdate,
  FeatureFlagCreate,
  FeatureFlagUpdate,
  PlatformHealth,
  PlatformAlert,
  PlatformMetricsRecord,
  PlatformMetricsTimeseries,
  HealthSummaryResponse,
} from '../contracts';
import { ENDPOINTS } from '../contracts';

// Re-export types for backward compatibility
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

// Re-export additional types
export type {
  PlatformHealth,
  PlatformAlert,
  PlatformMetricsRecord,
  PlatformMetricsTimeseries,
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
      return apiClient.get<PlatformSetting[]>(ENDPOINTS.SETTINGS.LIST);
    },

    /**
     * Get setting by ID
     */
    get: async (id: string): Promise<PlatformSetting> => {
      return apiClient.get<PlatformSetting>(ENDPOINTS.SETTINGS.DETAIL(id));
    },

    /**
     * Create setting
     */
    create: async (data: PlatformSettingCreate): Promise<PlatformSetting> => {
      return apiClient.post<PlatformSetting>(ENDPOINTS.SETTINGS.CREATE, data);
    },

    /**
     * Update setting
     */
    update: async (id: string, data: PlatformSettingUpdate): Promise<PlatformSetting> => {
      return apiClient.patch<PlatformSetting>(ENDPOINTS.SETTINGS.UPDATE(id), data);
    },

    /**
     * Delete setting
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.SETTINGS.DELETE(id));
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
      return apiClient.get<FeatureFlag[]>(ENDPOINTS.FEATURE_FLAGS.LIST);
    },

    /**
     * Get feature flag by ID
     */
    get: async (id: string): Promise<FeatureFlag> => {
      return apiClient.get<FeatureFlag>(ENDPOINTS.FEATURE_FLAGS.DETAIL(id));
    },

    /**
     * Create feature flag
     */
    create: async (data: FeatureFlagCreate): Promise<FeatureFlag> => {
      return apiClient.post<FeatureFlag>(ENDPOINTS.FEATURE_FLAGS.CREATE, data);
    },

    /**
     * Update feature flag
     */
    update: async (id: string, data: FeatureFlagUpdate): Promise<FeatureFlag> => {
      return apiClient.patch<FeatureFlag>(ENDPOINTS.FEATURE_FLAGS.UPDATE(id), data);
    },

    /**
     * Toggle feature flag
     */
    toggle: async (id: string): Promise<FeatureFlag> => {
      return apiClient.post<FeatureFlag>(ENDPOINTS.FEATURE_FLAGS.TOGGLE(id));
    },

    /**
     * Delete feature flag
     */
    delete: async (id: string): Promise<void> => {
      return apiClient.delete(ENDPOINTS.FEATURE_FLAGS.DELETE(id));
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
      return apiClient.get<SystemHealth[]>(ENDPOINTS.HEALTH.LIST);
    },

    /**
     * Get health summary
     */
    summary: async (): Promise<HealthSummaryResponse> => {
      return apiClient.get<HealthSummaryResponse>(ENDPOINTS.HEALTH.SUMMARY);
    },

    /**
     * Get health record by ID
     */
    get: async (id: string): Promise<SystemHealth> => {
      return apiClient.get<SystemHealth>(ENDPOINTS.HEALTH.DETAIL(id));
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
      return apiClient.get<PlatformAuditEvent[]>(ENDPOINTS.AUDIT_EVENTS.LIST);
    },

    /**
     * Get audit event by ID
     */
    get: async (id: string): Promise<PlatformAuditEvent> => {
      return apiClient.get<PlatformAuditEvent>(ENDPOINTS.AUDIT_EVENTS.DETAIL(id));
    },
  },

  /**
   * Platform Metrics
   */
  metrics: {
    list: async (): Promise<PlatformMetricsRecord[]> => {
      return apiClient.get<PlatformMetricsRecord[]>(ENDPOINTS.METRICS.LIST);
    },

    get: async (id: string): Promise<PlatformMetricsRecord> => {
      return apiClient.get<PlatformMetricsRecord>(ENDPOINTS.METRICS.DETAIL(id));
    },

    getCurrent: async (timeRange: string, metricType: string): Promise<unknown> => {
      const queryParams = new URLSearchParams();
      queryParams.append('time_range', timeRange);
      queryParams.append('metric_type', metricType);
      const url = `${ENDPOINTS.METRICS.CURRENT}?${queryParams.toString()}`;
      const response = await apiClient.get<{
        metrics_data?: unknown;
      }>(url);
      return response.metrics_data ?? {};
    },

    save: async (metricType: string, timeRange: string): Promise<PlatformMetricsRecord> => {
      return apiClient.post<PlatformMetricsRecord>(ENDPOINTS.METRICS.SAVE, {
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
