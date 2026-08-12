/* eslint-disable max-lines-per-function -- endpoint matrix coverage is clearer when kept in one service-boundary test file. */
/* eslint-disable @typescript-eslint/unbound-method -- assertions intentionally inspect Vitest mocks. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiEnvelope,
  type MonitoringConfigurationDocument,
  type PaginationMeta,
} from "../contracts";
import { performanceMonitoringService } from "../services/performance-monitoring-service";
import type { PerformanceMonitoringApiError } from "../services/performance-monitoring-service";

vi.mock("@/services/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      readonly status: number,
      readonly body?: unknown,
      readonly code?: string,
      readonly correlationId?: string
    ) {
      super(message);
      this.name = "ApiError";
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const meta = {
  correlation_id: "corr-performance-request",
  timestamp: "2026-07-22T00:00:00Z",
  pagination: {
    page: 1,
    page_size: 25,
    count: 0,
    total_pages: 0,
    has_next: false,
    has_previous: false,
  } satisfies PaginationMeta,
};

const governed = <T>(data: T): ApiEnvelope<T> => ({ data, meta });
const page = <T>(data: readonly T[] = []): ApiEnvelope<readonly T[]> => ({ data, meta });

const configurationDocument: MonitoringConfigurationDocument = {
  schema_version: "1.0",
  allowlists: {
    source_types: ["otlp", "prometheus"],
    metric_types: ["gauge", "counter"],
    alert_conditions: ["above_threshold"],
    severities: ["warning", "critical"],
    sla_comparisons: ["gte"],
    report_periods: ["calendar_month"],
  },
  defaults: {
    telemetry_source: {
      sampling_rate: 1,
      retention_days: 30,
      daily_event_quota: 1000,
      redaction_fields: ["authorization"],
    },
    environment: { kind: "production" },
    service: { namespace: "core" },
    metric: {
      namespace: "api",
      unit: "ms",
      expected_interval_seconds: 60,
      retention_days: 30,
    },
    dashboard: {
      refresh_interval_seconds: 30,
      service_list_limit: 5,
      alert_list_limit: 5,
    },
    alert_rule: {
      threshold: 500,
      aggregation: "p95",
      evaluation_window_minutes: 5,
      evaluation_interval_seconds: 60,
      cooldown_minutes: 15,
      severity: "warning",
      notification_channels: ["in_app"],
    },
    alert: { initial_occurrence_count: 1 },
    sla: {
      target_percentage: 99.9,
      window: "calendar_month",
      expected_interval_seconds: 60,
      timezone: "UTC",
      initial_version: 1,
    },
    slo: { window_days: 30, expected_interval_seconds: 60, error_budget_minutes: 43 },
  },
  limits: {
    sampling_rate_min: 0,
    sampling_rate_max: 1,
    retention_days_min: 1,
    retention_days_max: 365,
    daily_event_quota_min: 1,
    daily_event_quota_max: 100000,
    metric_name_max_length: 120,
    metric_name_pattern: "^[a-z.]+$",
    max_tags_per_data_point: 20,
    max_batch_data_points: 500,
    metric_query_max_range_days: 30,
    max_alert_rules: 100,
    alert_evaluation_timeout_seconds: 10,
    compliance_max_range_days: 31,
    log_message_max_length: 4000,
    max_spans_per_trace: 1000,
    evaluation_window_max_minutes: 1440,
    cooldown_max_minutes: 1440,
    sla_cadence_min_seconds: 60,
    sla_cadence_max_seconds: 3600,
  },
  rules: { require_evidence: true },
  query: {
    interval_seconds: { "5m": 300 },
    summary_period_seconds: { "1h": 3600 },
    automatic_buckets: [{ max_range_seconds: 3600, bucket_seconds: 60 }],
    summary_percentiles: [50, 95, 99],
    explorer_time_ranges_minutes: [15, 60],
    metric_stale_interval_multiplier: 3,
    global_stale_threshold_minutes: 10,
  },
  delivery: {
    timeout_seconds: 10,
    max_attempts: 3,
    initial_backoff_seconds: 1,
    max_backoff_seconds: 30,
    jitter_ratio: 0.2,
    circuit_failure_threshold: 5,
    circuit_recovery_seconds: 60,
  },
  health: { cache_probe_timeout_seconds: 1, critical_dependencies: ["redis"] },
  evidence: { retention_days: 90, archival_enabled: true, archive_provider: "s3" },
  pagination: { default_page_size: 25, max_page_size: 100 },
  rollout: { enabled: true, percentage: 100, roles: [], cohorts: [] },
  visual: {
    status_tokens: {
      success: "status-success",
      warning: "status-warning",
      danger: "status-danger",
      stale: "status-stale",
      degraded: "status-degraded",
    },
    log_level_tokens: {
      trace: "log-trace",
      debug: "log-debug",
      info: "log-info",
      warning: "log-warning",
      error: "log-error",
    },
  },
};

describe("performanceMonitoringService request coverage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shapes catalog and telemetry registration requests through endpoint constants", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(page());
    vi.mocked(apiClient.post).mockResolvedValue(governed({ id: "created" }));

    await performanceMonitoringService.listTelemetrySources({
      page: 2,
      page_size: 10,
      search: "otlp",
      ordering: "-last_seen_at",
    });
    await performanceMonitoringService.createTelemetrySource({
      name: "Collector",
      source_type: "otlp",
      sampling_rate: 0.5,
    });
    await performanceMonitoringService.listEnvironments({ search: "prod" });
    await performanceMonitoringService.createEnvironment({
      name: "Production",
      slug: "production",
      kind: "production",
      is_active: true,
    });
    await performanceMonitoringService.listServices({ ordering: "name" });
    await performanceMonitoringService.getService("service-id");
    await performanceMonitoringService.listDashboards({ page_size: 5 });
    await performanceMonitoringService.createDashboard({
      name: "Operations",
      description: "Production telemetry",
      layout: {},
      refresh_interval_seconds: 30,
      is_default: false,
    });

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.TELEMETRY_SOURCES.LIST}?page=2&page_size=10&search=otlp&ordering=-last_seen_at`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.TELEMETRY_SOURCES.LIST, {
      name: "Collector",
      source_type: "otlp",
      sampling_rate: 0.5,
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(2, `${ENDPOINTS.ENVIRONMENTS.LIST}?search=prod`);
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.ENVIRONMENTS.LIST, {
      name: "Production",
      slug: "production",
      kind: "production",
      is_active: true,
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(3, `${ENDPOINTS.SERVICES.LIST}?ordering=name`);
    expect(apiClient.get).toHaveBeenNthCalledWith(4, ENDPOINTS.SERVICES.DETAIL("service-id"));
    expect(apiClient.get).toHaveBeenNthCalledWith(5, `${ENDPOINTS.DASHBOARDS.LIST}?page_size=5`);
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.DASHBOARDS.LIST, {
      name: "Operations",
      description: "Production telemetry",
      layout: {},
      refresh_interval_seconds: 30,
      is_default: false,
    });
  });

  it("encodes log, trace, summary, and compliance query filters without empty values", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(page());

    await performanceMonitoringService.summarizeMetrics(["api.latency", "api.errors"]);
    await performanceMonitoringService.listLogs({
      from: "2026-07-22T00:00:00Z",
      to: "2026-07-22T01:00:00Z",
      level: "error",
      service_id: "service-id",
      environment_id: "",
      trace_id: "trace-1",
    });
    await performanceMonitoringService.listTraces({
      status: "error",
      min_duration_ms: 500,
      service_id: "service-id",
    });
    await performanceMonitoringService.listTraceSpans("trace-id");
    await performanceMonitoringService.listComplianceRecords({ page: 3 });

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.METRICS.SUMMARY}?metric_names=api.latency%2Capi.errors&period=1h`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.LOGS.LIST}?from=2026-07-22T00%3A00%3A00Z&to=2026-07-22T01%3A00%3A00Z&level=error&service_id=service-id&trace_id=trace-1`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.TRACES.LIST}?service_id=service-id&status=error&min_duration_ms=500`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(4, ENDPOINTS.SPANS.FOR_TRACE("trace-id"));
    expect(apiClient.get).toHaveBeenNthCalledWith(5, `${ENDPOINTS.COMPLIANCE_RECORDS.LIST}?page=3`);
  });

  it("preserves configuration governance requests for history, audit, import, export, and rollback", async () => {
    const request = {
      document: configurationDocument,
      environment: "production",
      expected_version: 7,
      change_reason: "Raise service list bound",
    };
    vi.mocked(apiClient.get).mockResolvedValue(governed([]));
    vi.mocked(apiClient.post).mockResolvedValue(governed({ id: "config" }));

    await performanceMonitoringService.listConfigurationHistory("production");
    await performanceMonitoringService.listConfigurationAudit("production");
    await performanceMonitoringService.exportConfiguration("production");
    await performanceMonitoringService.importConfiguration(request);
    await performanceMonitoringService.rollbackConfiguration({
      version: 6,
      environment: "production",
      expected_version: 7,
      change_reason: "Rollback unsafe change",
    });

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.CONFIGURATION.HISTORY}?environment=production`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.CONFIGURATION.AUDIT}?environment=production`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.CONFIGURATION.EXPORT}?environment=production`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.CONFIGURATION.IMPORT, request);
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.CONFIGURATION.ROLLBACK, {
      version: 6,
      environment: "production",
      expected_version: 7,
      change_reason: "Rollback unsafe change",
    });
  });

  it("wraps ApiError failures with monitoring-specific status, code, and correlation evidence", async () => {
    vi.mocked(apiClient.get).mockRejectedValue(
      new ApiError("Policy denied", 403, undefined, "policy_denied", "corr-denied")
    );

    await expect(performanceMonitoringService.getHealth()).rejects.toMatchObject({
      name: "PerformanceMonitoringApiError",
      message: "Policy denied",
      status: 403,
      code: "policy_denied",
      correlationId: "corr-denied",
    } satisfies Partial<PerformanceMonitoringApiError>);
  });
});
