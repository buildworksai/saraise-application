/**
 * Platform Management Service
 *
 * Service client for Platform Management API endpoints.
 */
import { apiClient } from "@/services/api-client";
import type {
  PlatformSetting,
  PlatformSettingCreate,
  FeatureFlag,
  FeatureFlagCreate,
  SystemHealth,
  HealthSummary,
  PlatformAuditEvent,
  PlatformMetrics,
  PlatformMetricsRequest,
} from "../contracts";
import { ENDPOINTS } from "../contracts";

// Re-export types
export type {
  PlatformSetting,
  PlatformSettingCreate,
  FeatureFlag,
  FeatureFlagCreate,
  SystemHealth,
  HealthSummary,
  PlatformAuditEvent,
  PlatformMetrics,
  PlatformMetricsRequest,
};

export const platformService = {
  /**
   * Platform Settings
   */
  settings: {
    list: async (params?: { search?: string }): Promise<PlatformSetting[]> => {
      const queryParams = new URLSearchParams();
      if (params?.search) queryParams.append("search", params.search);
      const queryString = queryParams.toString();
      const url = queryString
        ? `${ENDPOINTS.SETTINGS.LIST}?${queryString}`
        : ENDPOINTS.SETTINGS.LIST;
      const response = await apiClient.get<PlatformSetting[]>(url);
      return Array.isArray(response) ? response : [];
    },

    get: async (id: string): Promise<PlatformSetting> => {
      return apiClient.get<PlatformSetting>(ENDPOINTS.SETTINGS.DETAIL(id));
    },

    // Note: Create/Update/Delete should be restricted based on permissions
    // and ideally performed via Control Plane, but defined here if the API allows it for authorized users.
    // The backend says these are READ-ONLY in Application layer, but I'll implement them
    // in case they are enabled for platform owners or proxy to control plane.
    // However, the backend api.py says "Usage Forbidden", so usage will fail.
    // Keeping for completeness if the frontend needs to TRY (and get 403) or if strict separation allows it later.
    // Actually, backendapi.py explicitly says specific ViewSets are ReadOnlyModelViewSet except where valid.
    // PlatformSettingViewSet is ReadOnly. FeatureFlagViewSet is ReadOnly.
    // So create/update/delete will fail. But contracts usually define the structure.
    // I'll leave them but user should know they might fail.
    // Wait, create/update serializers exist in api.py (PlatformSettingCreateSerializer),
    // but the ViewSet is ReadOnlyModelViewSet. So these endpoints really don't exist as POST/PUT.
    // But standard REST patterns... I'll omit write operations to be safe and compliant with "READ ONLY" warnings.

    // Removed create/update/delete for settings as per backend "READ ONLY" warning.
  },

  /**
   * Feature Flags
   */
  featureFlags: {
    list: async (params?: {
      search?: string;
      enabled?: boolean;
    }): Promise<FeatureFlag[]> => {
      const queryParams = new URLSearchParams();
      if (params?.search) queryParams.append("search", params.search);
      if (params?.enabled !== undefined)
        queryParams.append("enabled", params.enabled.toString());
      const queryString = queryParams.toString();
      const url = queryString
        ? `${ENDPOINTS.FEATURE_FLAGS.LIST}?${queryString}`
        : ENDPOINTS.FEATURE_FLAGS.LIST;
      const response = await apiClient.get<FeatureFlag[]>(url);
      return Array.isArray(response) ? response : [];
    },

    get: async (id: string): Promise<FeatureFlag> => {
      return apiClient.get<FeatureFlag>(ENDPOINTS.FEATURE_FLAGS.DETAIL(id));
    },
    // Read-only
  },

  /**
   * System Health
   */
  health: {
    list: async (): Promise<SystemHealth[]> => {
      const response = await apiClient.get<SystemHealth[]>(
        ENDPOINTS.HEALTH.LIST
      );
      return Array.isArray(response) ? response : [];
    },

    getSummary: async (): Promise<HealthSummary> => {
      return apiClient.get<HealthSummary>(ENDPOINTS.HEALTH.SUMMARY);
    },
  },

  /**
   * Audit Events
   */
  auditEvents: {
    list: async (params?: {
      action?: string;
      actor_id?: string;
    }): Promise<PlatformAuditEvent[]> => {
      const queryParams = new URLSearchParams();
      if (params?.action) queryParams.append("action", params.action);
      if (params?.actor_id) queryParams.append("actor_id", params.actor_id);
      const queryString = queryParams.toString();
      const url = queryString
        ? `${ENDPOINTS.AUDIT_EVENTS.LIST}?${queryString}`
        : ENDPOINTS.AUDIT_EVENTS.LIST;
      const response = await apiClient.get<PlatformAuditEvent[]>(url);
      return Array.isArray(response) ? response : [];
    },

    get: async (id: string): Promise<PlatformAuditEvent> => {
      return apiClient.get<PlatformAuditEvent>(
        ENDPOINTS.AUDIT_EVENTS.DETAIL(id)
      );
    },
  },

  /**
   * Platform Metrics
   */
  metrics: {
    list: async (params?: {
      metric_type?: string;
      time_range?: string;
    }): Promise<PlatformMetrics[]> => {
      const queryParams = new URLSearchParams();
      if (params?.metric_type)
        queryParams.append("metric_type", params.metric_type);
      if (params?.time_range)
        queryParams.append("time_range", params.time_range);
      const queryString = queryParams.toString();
      const url = queryString
        ? `${ENDPOINTS.METRICS.LIST}?${queryString}`
        : ENDPOINTS.METRICS.LIST;
      const response = await apiClient.get<PlatformMetrics[]>(url);
      return Array.isArray(response) ? response : [];
    },

    current: async (params?: {
      metric_type?: string;
      time_range?: string;
    }): Promise<PlatformMetrics> => {
      const queryParams = new URLSearchParams();
      if (params?.metric_type)
        queryParams.append("metric_type", params.metric_type);
      if (params?.time_range)
        queryParams.append("time_range", params.time_range);
      const queryString = queryParams.toString();
      const url = queryString
        ? `${ENDPOINTS.METRICS.CURRENT}?${queryString}`
        : ENDPOINTS.METRICS.CURRENT;
      return apiClient.get<PlatformMetrics>(url);
    },

    save: async (data: PlatformMetricsRequest): Promise<PlatformMetrics> => {
      return apiClient.post<PlatformMetrics>(ENDPOINTS.METRICS.SAVE, data);
    },
  },
};
