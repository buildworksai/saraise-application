/* eslint-disable max-lines-per-function -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
/* eslint-disable @typescript-eslint/unbound-method -- assertions intentionally reference Vitest mocks. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiEnvelope,
  type Metric,
  type MonitoringConfigurationDocument,
} from "../contracts";
import { performanceMonitoringService as service } from "../services/performance-monitoring-service";

vi.mock("@/services/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public details?: unknown,
      public code?: string,
      public correlationId?: string
    ) {
      super(message);
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const meta = {
  correlation_id: "corr-performance-1",
  timestamp: "2026-07-22T00:00:00Z",
  pagination: {
    page: 1,
    page_size: 25,
    count: 1,
    total_pages: 1,
    has_next: false,
    has_previous: false,
  },
};

const metric: Metric = {
  id: "00000000-0000-4000-8000-000000000001",
  tenant_id: "00000000-0000-4000-8000-000000000002",
  metric_name: "api.response_time",
  display_name: "API response time",
  namespace: "api",
  description: "",
  metric_type: "histogram",
  unit: "ms",
  source: null,
  service: null,
  environment: null,
  default_tags: {},
  expected_interval_seconds: 60,
  retention_days: 30,
  is_active: true,
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
};

describe("performanceMonitoringService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps governed paginated responses and preserves trace metadata", async () => {
    const envelope: ApiEnvelope<readonly Metric[]> = { data: [metric], meta };
    vi.mocked(apiClient.get).mockResolvedValue(envelope);
    await expect(service.listMetrics({ page: 1, search: "response" })).resolves.toMatchObject({
      items: [metric],
      correlationId: "corr-performance-1",
    });
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.METRICS.LIST}?page=1&search=response`);
  });

  it("rejects a list that omits pagination instead of fabricating counts", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [],
      meta: { correlation_id: "corr", timestamp: meta.timestamp },
    });
    await expect(service.listMetrics()).rejects.toThrow("without pagination metadata");
  });

  it("uses the governed batch shape and preserves partial failures", async () => {
    const result = {
      accepted: 1,
      rejected: 1,
      errors: [{ index: 1, code: "invalid_value", message: "Value is not finite" }],
    };
    vi.mocked(apiClient.post).mockResolvedValue({ data: result, meta });
    const points = [
      { metric_name: "api.requests", value: 1 },
      { metric_name: "api.requests", value: Number.NaN },
    ];
    await expect(service.ingestMetricBatch(points)).resolves.toEqual(result);
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.METRICS.BATCH, { data_points: points });
  });

  it("encodes the documented metric query contract", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { metric_name: "api.response_time", aggregation: "p95", interval: "5m", data: [] },
      meta,
    });
    await service.queryMetric({
      metric_name: "api.response_time",
      start: "2026-07-21T00:00:00Z",
      end: "2026-07-22T00:00:00Z",
      aggregation: "p95",
      interval: "5m",
      tags: { region: "in" },
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      expect.stringContaining(`${ENDPOINTS.METRICS.QUERY}?metric_name=api.response_time`)
    );
    expect(apiClient.get).toHaveBeenCalledWith(expect.stringContaining("tags=region%3Din"));
  });

  it("posts alert transitions and complete SLA report requests", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { id: metric.id, status: "accepted" },
      meta,
    });
    await service.acknowledgeAlert(metric.id, { note: "Investigating" });
    await service.resolveAlert(metric.id, { note: "Recovered" });
    await service.generateSLAReport({
      sla_id: metric.id,
      period: "calendar_month",
      format: "json",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.ALERTS.ACKNOWLEDGE(metric.id), {
      note: "Investigating",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.ALERTS.RESOLVE(metric.id), {
      note: "Recovered",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.SLA.REPORTS, {
      sla_id: metric.id,
      period: "calendar_month",
      format: "json",
    });
  });

  it("keeps single-rule and all-rule alert evaluation distinct", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { id: metric.id, status: "evaluated" },
      meta,
    });
    await service.evaluateAlertRule(metric.id);
    await service.evaluateAllAlertRules();
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.ALERT_RULES.EVALUATE(metric.id),
      {}
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.ALERTS.EVALUATE, {});
  });

  it("uses only the configuration endpoint registry for the complete lifecycle", async () => {
    const document = {} as MonitoringConfigurationDocument;
    const current = {
      id: metric.id,
      tenant_id: metric.tenant_id,
      environment: "default",
      version: 2,
      document,
      updated_by: metric.id,
      correlation_id: meta.correlation_id,
      created_at: meta.timestamp,
      updated_at: meta.timestamp,
    };
    vi.mocked(apiClient.get).mockResolvedValue({ data: current, meta });
    await service.getConfiguration();
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.CURRENT}?environment=default`
    );

    vi.mocked(apiClient.post).mockResolvedValue({
      data: { valid: true, current_version: 2, proposed_document: document, diff: [] },
      meta,
    });
    const request = {
      document,
      environment: "default",
      expected_version: 2,
      change_reason: "Audit correction",
    } as const;
    await service.previewConfiguration(request);
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.PREVIEW, request);

    vi.mocked(apiClient.patch).mockResolvedValue({ data: current, meta });
    await service.updateConfiguration(request);
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.CURRENT, request);
  });

  it("uses the implemented evidence and SLO evaluation endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta });
    await service.listMetricDataPoints({ metric_name: metric.metric_name });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.DATA_POINTS.LIST}?metric_name=api.response_time`
    );
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: metric.id }, meta });
    await service.evaluateSLO(metric.id);
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.SLOS.EVALUATE(metric.id), {});
  });

  it("normalizes ApiError failures without swallowing non-API exceptions", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(
      new ApiError("Rate limit exceeded", 429, undefined, "rate_limited", "corr-rate")
    );
    await expect(service.listMetrics()).rejects.toMatchObject({
      name: "PerformanceMonitoringApiError",
      message: "Rate limit exceeded",
      status: 429,
      code: "rate_limited",
      correlationId: "corr-rate",
    });

    const transportFailure = new TypeError("network unavailable");
    vi.mocked(apiClient.get).mockRejectedValueOnce(transportFailure);
    await expect(service.listMetrics()).rejects.toBe(transportFailure);
  });

  it("routes catalog, service, dashboard, and metric writes through their governed endpoints", async () => {
    const telemetrySource = { id: metric.id, name: "OpenTelemetry", is_active: true };
    const environment = { id: metric.id, name: "Production", slug: "production" };
    const monitoredService = { id: metric.id, name: "API", service_key: "api" }; // pragma: allowlist secret
    const dashboard = { id: metric.id, name: "Operations", layout: [] };
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: [telemetrySource], meta })
      .mockResolvedValueOnce({ data: [environment], meta })
      .mockResolvedValueOnce({ data: [monitoredService], meta })
      .mockResolvedValueOnce({ data: monitoredService, meta })
      .mockResolvedValueOnce({ data: [dashboard], meta })
      .mockResolvedValueOnce({ data: metric, meta })
      .mockResolvedValueOnce({ data: { summaries: [] }, meta });
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: telemetrySource, meta })
      .mockResolvedValueOnce({ data: environment, meta })
      .mockResolvedValueOnce({ data: dashboard, meta })
      .mockResolvedValueOnce({ data: metric, meta });

    await service.listTelemetrySources({ page: 2, ordering: "name" });
    await service.createTelemetrySource({
      name: "OpenTelemetry",
    } as Parameters<typeof service.createTelemetrySource>[0]);
    await service.listEnvironments({ search: "prod" });
    await service.createEnvironment({
      name: "Production",
      slug: "production",
    } as Parameters<typeof service.createEnvironment>[0]);
    await service.listServices({ page_size: 10 });
    await service.getService(metric.id);
    await service.listDashboards({ search: "ops" });
    await service.createDashboard({ name: "Operations" } as Parameters<
      typeof service.createDashboard
    >[0]);
    await service.getMetric(metric.id);
    await service.createMetric({ metric_name: metric.metric_name } as Parameters<
      typeof service.createMetric
    >[0]);
    await service.summarizeMetrics(["api.requests", "api.errors"]);

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.TELEMETRY_SOURCES.LIST}?page=2&ordering=name`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.TELEMETRY_SOURCES.LIST, {
      name: "OpenTelemetry",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(2, `${ENDPOINTS.ENVIRONMENTS.LIST}?search=prod`);
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.ENVIRONMENTS.LIST, {
      name: "Production",
      slug: "production",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(3, `${ENDPOINTS.SERVICES.LIST}?page_size=10`);
    expect(apiClient.get).toHaveBeenNthCalledWith(4, ENDPOINTS.SERVICES.DETAIL(metric.id));
    expect(apiClient.get).toHaveBeenNthCalledWith(5, `${ENDPOINTS.DASHBOARDS.LIST}?search=ops`);
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.DASHBOARDS.LIST, {
      name: "Operations",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(6, ENDPOINTS.METRICS.DETAIL(metric.id));
    expect(apiClient.post).toHaveBeenNthCalledWith(4, ENDPOINTS.METRICS.LIST, {
      metric_name: metric.metric_name,
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(
      7,
      `${ENDPOINTS.METRICS.SUMMARY}?metric_names=api.requests%2Capi.errors&period=1h`
    );
  });

  it("routes logs, traces, alert rules, SLAs, SLOs, health, and configuration history", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: [], meta })
      .mockResolvedValueOnce({ data: { id: "log-id" }, meta })
      .mockResolvedValueOnce({ data: [], meta })
      .mockResolvedValueOnce({ data: { id: "trace-id" }, meta })
      .mockResolvedValueOnce({ data: [], meta })
      .mockResolvedValueOnce({ data: [], meta })
      .mockResolvedValueOnce({ data: [], meta })
      .mockResolvedValueOnce({ data: { id: metric.id, status: "compliant" }, meta })
      .mockResolvedValueOnce({ data: [], meta })
      .mockResolvedValueOnce({ data: { id: metric.id, remaining_percent: 99 }, meta })
      .mockResolvedValueOnce({ data: [], meta })
      .mockResolvedValueOnce({ data: { status: "healthy" }, meta })
      .mockResolvedValueOnce({ data: [], meta })
      .mockResolvedValueOnce({ data: [], meta })
      .mockResolvedValueOnce({ data: { environment: "staging", document: {} }, meta });
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({ data: { id: metric.id }, meta })
      .mockResolvedValueOnce({ data: { id: metric.id }, meta })
      .mockResolvedValueOnce({ data: { id: metric.id }, meta })
      .mockResolvedValueOnce({ data: { environment: "staging", document: {} }, meta });

    await service.listLogs({
      level: "error",
      service_id: metric.id,
      environment_id: metric.tenant_id,
      trace_id: "trace-1",
    });
    await service.getLog("log-id");
    await service.listTraces({ status: "error", min_duration_ms: 250 });
    await service.getTrace("trace-id");
    await service.listTraceSpans("trace-id");
    await service.listAlertRules({ search: "latency" });
    await service.createAlertRule({
      name: "Latency breach",
      metric_name: metric.metric_name,
      condition: "above_threshold",
      threshold: 500,
      evaluation_window_minutes: 5,
      cooldown_minutes: 10,
      severity: "critical",
      action: { channel: "pager" },
      ignored_server_field: "must not cross boundary",
    } as unknown as Parameters<typeof service.createAlertRule>[0]);
    await service.listAlerts({ status: "firing", severity: "critical" });
    await service.listSLAs({ page: 2 });
    await service.createSLA({
      metric_name: "api.availability",
      service_name: "api",
      comparison: "gte",
      target: 99.9,
      window: "calendar_month",
    });
    await service.evaluateSLA(metric.id);
    await service.listSLOs({ search: "budget" });
    await service.createSLO({
      name: "API latency",
      service_id: metric.tenant_id,
      indicator_metric_id: metric.id,
      comparison: "lte",
      threshold: 250,
      objective_percentage: 99,
    });
    await service.getSLOBudget(metric.id);
    await service.listComplianceRecords({ ordering: "-period_end" });
    await service.getHealth();
    await service.listConfigurationHistory("staging");
    await service.listConfigurationAudit("staging");
    await service.rollbackConfiguration({
      environment: "staging",
      version: 1,
      expected_version: 2,
      change_reason: "Rollback failed rollout",
    });
    await service.importConfiguration({
      environment: "staging",
      document: {},
      expected_version: 2,
      change_reason: "Promote import",
    } as Parameters<typeof service.importConfiguration>[0]);
    await service.exportConfiguration("staging");

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.LOGS.LIST}?level=error&service_id=${metric.id}&environment_id=${metric.tenant_id}&trace_id=trace-1`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(2, ENDPOINTS.LOGS.DETAIL("log-id"));
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.TRACES.LIST}?status=error&min_duration_ms=250`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(4, ENDPOINTS.TRACES.DETAIL("trace-id"));
    expect(apiClient.get).toHaveBeenNthCalledWith(5, ENDPOINTS.SPANS.FOR_TRACE("trace-id"));
    expect(apiClient.get).toHaveBeenNthCalledWith(
      6,
      `${ENDPOINTS.ALERT_RULES.LIST}?search=latency`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.ALERT_RULES.LIST, {
      name: "Latency breach",
      metric_name: metric.metric_name,
      condition: "above_threshold",
      threshold: 500,
      evaluation_window_minutes: 5,
      cooldown_minutes: 10,
      severity: "critical",
      action: { channel: "pager" },
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(
      7,
      `${ENDPOINTS.ALERTS.LIST}?status=firing&severity=critical`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(8, `${ENDPOINTS.SLA.LIST}?page=2`);
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.SLA.LIST, {
      metric_name: "api.availability",
      service_name: "api",
      comparison: "gte",
      target: 99.9,
      window: "calendar_month",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(9, ENDPOINTS.SLA.COMPLIANCE(metric.id));
    expect(apiClient.get).toHaveBeenNthCalledWith(10, `${ENDPOINTS.SLOS.LIST}?search=budget`);
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.SLOS.LIST, {
      name: "API latency",
      service_id: metric.tenant_id,
      indicator_metric_id: metric.id,
      comparison: "lte",
      threshold: 250,
      objective_percentage: 99,
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(11, ENDPOINTS.SLOS.BUDGET(metric.id));
    expect(apiClient.get).toHaveBeenNthCalledWith(
      12,
      `${ENDPOINTS.COMPLIANCE_RECORDS.LIST}?ordering=-period_end`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(13, ENDPOINTS.HEALTH);
    expect(apiClient.get).toHaveBeenNthCalledWith(
      14,
      `${ENDPOINTS.CONFIGURATION.HISTORY}?environment=staging`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      15,
      `${ENDPOINTS.CONFIGURATION.AUDIT}?environment=staging`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(4, ENDPOINTS.CONFIGURATION.ROLLBACK, {
      environment: "staging",
      version: 1,
      expected_version: 2,
      change_reason: "Rollback failed rollout",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(5, ENDPOINTS.CONFIGURATION.IMPORT, {
      environment: "staging",
      document: {},
      expected_version: 2,
      change_reason: "Promote import",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(
      16,
      `${ENDPOINTS.CONFIGURATION.EXPORT}?environment=staging`
    );
  });
});
