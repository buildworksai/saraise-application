/* eslint-disable max-lines, max-lines-per-function -- page coverage needs cohesive fixtures and assertions. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Alert,
  AlertRule,
  LogEntry,
  Metric,
  MonitoringConfiguration,
  MonitoringDashboard,
  MonitoringEnvironment,
  MonitoredService,
  PageResult,
  SLAComplianceRecord,
  SLADefinition,
  Span,
  TelemetrySource,
  Trace,
} from "../contracts";
import { ActiveAlertsPage } from "./ActiveAlertsPage";
import { AlertRulesPage } from "./AlertRulesPage";
import { InstrumentationSetupPage } from "./InstrumentationSetupPage";
import { LogExplorerPage } from "./LogExplorerPage";
import { MetricExplorerPage } from "./MetricExplorerPage";
import { MetricsDashboardPage } from "./MetricsDashboardPage";
import { MonitoringCatalogPage } from "./MonitoringCatalogPage";
import { PerformanceDashboardPage } from "./PerformanceDashboardPage";
import { PerformanceMonitoringIndexPage } from "./PerformanceMonitoringIndexPage";
import { SLAManagementPage } from "./SLAManagementPage";
import { SLOMonitoringPage } from "./SLOMonitoringPage";
import { TraceExplorerPage } from "./TraceExplorerPage";

const mocks = vi.hoisted(() => ({
  createAlertRule: vi.fn(),
  createDashboard: vi.fn(),
  createEnvironment: vi.fn(),
  createMetric: vi.fn(),
  createSLA: vi.fn(),
  createTelemetrySource: vi.fn(),
  acknowledgeAlert: vi.fn(),
  evaluateAlertRule: vi.fn(),
  evaluateSLA: vi.fn(),
  generateSLAReport: vi.fn(),
  getConfiguration: vi.fn(),
  listAlertRules: vi.fn(),
  listAlerts: vi.fn(),
  listComplianceRecords: vi.fn(),
  listDashboards: vi.fn(),
  listEnvironments: vi.fn(),
  listLogs: vi.fn(),
  listMetrics: vi.fn(),
  listServices: vi.fn(),
  listSLAs: vi.fn(),
  listTraceSpans: vi.fn(),
  listTraces: vi.fn(),
  listTelemetrySources: vi.fn(),
  queryMetric: vi.fn(),
  resolveAlert: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("recharts", () => ({
  Line: () => null,
  LineChart: ({ children }: { readonly children?: ReactNode }) => (
    <div data-testid="metric-line-chart">{children}</div>
  ),
  ResponsiveContainer: ({ children }: { readonly children?: ReactNode }) => (
    <div data-testid="responsive-chart">{children}</div>
  ),
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));
vi.mock("../services/performance-monitoring-service", () => ({
  PerformanceMonitoringApiError: class PerformanceMonitoringApiError extends Error {
    constructor(
      message: string,
      readonly status: number,
      readonly code: string,
      readonly correlationId: string | null
    ) {
      super(message);
      this.name = "PerformanceMonitoringApiError";
    }
  },
  performanceMonitoringService: mocks,
}));

const pagination = {
  count: 0,
  page: 1,
  page_size: 100,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

function page<T>(items: readonly T[]): PageResult<T> {
  return {
    items,
    pagination: { ...pagination, count: items.length },
    correlationId: "corr-page",
    receivedAt: "2026-07-28T00:00:00Z",
  };
}

const configuration: MonitoringConfiguration = {
  id: "config-1",
  tenant_id: "tenant-1",
  environment: "default",
  version: 7,
  updated_by: "operator-1",
  correlation_id: "corr-config",
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
  document: {
    schema_version: "1.0",
    allowlists: {
      source_types: ["otlp", "prometheus"],
      metric_types: ["gauge", "counter"],
      alert_conditions: ["above_threshold", "absence"],
      severities: ["warning", "critical"],
      sla_comparisons: ["gte", "lte"],
      report_periods: ["calendar_month", "rolling_24h"],
    },
    defaults: {
      telemetry_source: {
        sampling_rate: 0.5,
        retention_days: 30,
        daily_event_quota: 5000,
        redaction_fields: ["authorization", "cookie"],
      },
      environment: { kind: "production" },
      service: { namespace: "core" },
      metric: {
        namespace: "api",
        unit: "ms",
        expected_interval_seconds: 60,
        retention_days: 30,
      },
      dashboard: { refresh_interval_seconds: 45, service_list_limit: 2, alert_list_limit: 1 },
      alert_rule: {
        threshold: 500,
        aggregation: "avg",
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
      daily_event_quota_max: 10000,
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
      evaluation_window_max_minutes: 60,
      cooldown_max_minutes: 1440,
      sla_cadence_min_seconds: 60,
      sla_cadence_max_seconds: 3600,
    },
    rules: { fail_closed: true },
    query: {
      interval_seconds: { "1m": 60, "5m": 300 },
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
  },
};

const environment: MonitoringEnvironment = {
  id: "env-1",
  tenant_id: "tenant-1",
  name: "Production",
  slug: "production",
  description: "Primary environment",
  kind: "production",
  is_active: true,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};
const dashboard: MonitoringDashboard = {
  id: "dash-1",
  tenant_id: "tenant-1",
  name: "Tenant operations",
  description: "Primary dashboard",
  is_default: true,
  layout: {},
  widgets: [],
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};
const metric: Metric = {
  id: "metric-1",
  tenant_id: "tenant-1",
  metric_name: "api.latency",
  display_name: "API latency",
  namespace: "api",
  description: "Request latency",
  metric_type: "gauge",
  unit: "ms",
  source: null,
  service: null,
  environment: null,
  default_tags: {},
  expected_interval_seconds: 60,
  retention_days: 30,
  is_active: true,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};
const source: TelemetrySource = {
  id: "source-1",
  tenant_id: "tenant-1",
  name: "OTLP collector",
  source_type: "otlp",
  description: "Collector",
  status: "healthy",
  sampling_rate: 0.5,
  retention_days: 30,
  daily_event_quota: 5000,
  redaction_fields: ["authorization"],
  last_seen_at: "2026-07-28T11:59:00Z",
  is_active: true,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};
const service: MonitoredService = {
  id: "service-1",
  tenant_id: "tenant-1",
  name: "Runtime API",
  slug: "runtime-api",
  environment: "env-1",
  source: "source-1",
  namespace: "core",
  version: "2026.7",
  owner: "platform",
  language: "python",
  status: "healthy",
  last_seen_at: "2026-07-28T11:59:00Z",
  attributes: {},
  is_active: true,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};
const staleService: MonitoredService = {
  ...service,
  id: "service-stale",
  name: "Worker",
  slug: "worker",
  status: "stale",
  last_seen_at: "2026-07-28T11:00:00Z",
};
const trace: Trace = {
  id: "trace-1",
  tenant_id: "tenant-1",
  trace_id: "4bf92f3577b34da6a3ce929d0e0e4736",
  source: "source-1",
  service: service.id,
  environment: environment.id,
  name: "POST /api/orders",
  started_at: "2026-07-28T11:58:00Z",
  ended_at: "2026-07-28T11:58:02Z",
  duration_ms: 1250.25,
  status: "error",
  span_count: 2,
  error_span_count: 1,
  sampled: true,
};
const span: Span = {
  id: "span-1",
  span_id: "span-runtime",
  parent_span_id: null,
  trace: trace.id,
  service: service.id,
  name: "database.query",
  kind: "client",
  started_at: "2026-07-28T11:58:01Z",
  ended_at: "2026-07-28T11:58:02Z",
  duration_ms: 950.5,
  status: "error",
  attributes: { table: "orders" },
};
const alertRule: AlertRule = {
  id: "rule-1",
  tenant_id: "tenant-1",
  name: "High latency",
  description: "",
  metric: null,
  metric_name: "api.latency",
  condition: "above_threshold",
  threshold: 500,
  evaluation_window_minutes: 5,
  evaluation_interval_seconds: 60,
  cooldown_minutes: 15,
  severity: "critical",
  action: { channels: ["in_app"] },
  is_active: true,
  last_evaluated_at: "2026-07-28T11:55:00Z",
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};
const alert: Alert = {
  id: "alert-1",
  tenant_id: "tenant-1",
  alert_rule: "rule-1",
  metric_name: "api.latency",
  status: "firing",
  severity: "critical",
  title: "Latency breached",
  description: "p95 exceeded threshold",
  triggered_value: 800,
  threshold: 500,
  triggered_at: "2026-07-28T11:50:00Z",
  last_observed_at: "2026-07-28T11:59:00Z",
  occurrence_count: 2,
  acknowledged_at: null,
  acknowledged_by: null,
  resolved_at: null,
  resolution_note: "",
  context: {},
};
const logEntry: LogEntry = {
  id: "log-1",
  tenant_id: "tenant-1",
  timestamp: "2026-07-28T11:59:00Z",
  source: source.id,
  service: service.id,
  environment: environment.id,
  observed_at: "2026-07-28T11:59:01Z",
  level: "error",
  message: "Request failed closed",
  trace_id: trace.trace_id,
  span_id: span.span_id,
  correlation_id: "corr-runtime",
  attributes: { route: "/api/orders", status_code: 503 },
};
const sla: SLADefinition = {
  id: "sla-1",
  tenant_id: "tenant-1",
  name: "Runtime availability",
  description: "Availability objective",
  metric: null,
  metric_name: "api.availability",
  service: null,
  service_name: "runtime-api",
  comparison: "gte",
  target: 99.9,
  window: "calendar_month",
  expected_interval_seconds: 60,
  version: 2,
  effective_from: "2026-07-28T00:00:00Z",
  effective_until: null,
  is_active: true,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};
const compliance: SLAComplianceRecord = {
  id: "compliance-1",
  sla: "sla-1",
  period_start: "2026-07-01T00:00:00Z",
  period_end: "2026-07-31T23:59:59Z",
  expected_samples: 100,
  observed_samples: 95,
  compliant_samples: 94,
  missing_samples: 5,
  actual_value: 99.95,
  target_value: 99.9,
  is_compliant: true,
  compliance_percentage: 98.9,
  breach_duration_minutes: 0,
  status: "compliant",
  created_at: "2026-07-28T00:00:00Z",
};

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="path">{location.pathname}</span>;
}

function renderPage(node: React.ReactElement, path = "/performance-monitoring") {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="*"
            element={
              <>
                {node}
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  mocks.getConfiguration.mockResolvedValue(configuration);
  mocks.listEnvironments.mockResolvedValue(page([environment]));
  mocks.listDashboards.mockResolvedValue(page([dashboard]));
  mocks.listMetrics.mockResolvedValue(page([metric]));
  mocks.queryMetric.mockResolvedValue({
    metric_name: "api.latency",
    aggregation: "avg",
    interval: "1m",
    data: [
      { timestamp: "2026-07-28T11:58:00Z", value: 120 },
      { timestamp: "2026-07-28T11:59:00Z", value: 180 },
    ],
  });
  mocks.listTelemetrySources.mockResolvedValue(page([source]));
  mocks.listServices.mockResolvedValue(page([service]));
  mocks.listTraces.mockResolvedValue(page([trace]));
  mocks.listTraceSpans.mockResolvedValue([span]);
  mocks.listAlertRules.mockResolvedValue(page([alertRule]));
  mocks.evaluateAlertRule.mockResolvedValue(alertRule);
  mocks.listAlerts.mockResolvedValue(page([alert]));
  mocks.acknowledgeAlert.mockResolvedValue({ ...alert, status: "acknowledged" });
  mocks.resolveAlert.mockResolvedValue({ ...alert, status: "resolved" });
  mocks.listLogs.mockResolvedValue(page([logEntry]));
  mocks.listSLAs.mockResolvedValue(page([sla]));
  mocks.listComplianceRecords.mockResolvedValue(page([compliance]));
  mocks.evaluateSLA.mockResolvedValue(compliance);
  mocks.generateSLAReport.mockResolvedValue({ id: "job-1" });
  mocks.createEnvironment.mockResolvedValue(environment);
  mocks.createDashboard.mockResolvedValue(dashboard);
  mocks.createMetric.mockResolvedValue(metric);
  mocks.createTelemetrySource.mockResolvedValue(source);
  mocks.createAlertRule.mockResolvedValue(alertRule);
  mocks.createSLA.mockResolvedValue(sla);
});

describe("performance monitoring page coverage", () => {
  it("creates catalog environments and dashboards from governed defaults", async () => {
    const user = userEvent.setup();
    renderPage(<MonitoringCatalogPage />);

    expect(await screen.findByText("Production")).toBeInTheDocument();
    expect(screen.getByText("Tenant operations")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Environment/u }));
    const environmentInputs = screen.getAllByRole("textbox");
    await user.type(environmentInputs[0]!, "Staging");
    await user.type(environmentInputs[1]!, "STAGING");
    await user.clear(environmentInputs[2]!);
    await user.type(environmentInputs[2]!, "staging");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(mocks.createEnvironment).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "staging", name: "Staging", slug: "staging" })
    );

    await user.click(screen.getByRole("button", { name: /Dashboard/u }));
    await user.type(screen.getByLabelText("Name"), "Operations");
    expect(screen.getByLabelText("Refresh interval (seconds)")).toHaveValue(45);
    await user.click(screen.getByLabelText("Default dashboard"));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(mocks.createDashboard).toHaveBeenCalledWith(
      expect.objectContaining({
        is_default: true,
        name: "Operations",
        refresh_interval_seconds: 45,
      })
    );
  });

  it("queries metrics, renders statistics, and validates metric creation", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-07-28T12:00:00Z"));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage(<MetricExplorerPage />);

    expect(await screen.findByText("API latency")).toBeInTheDocument();
    await waitFor(() =>
      expect(mocks.queryMetric).toHaveBeenCalledWith(
        expect.objectContaining({ aggregation: "avg", interval: "1m", metric_name: "api.latency" })
      )
    );
    expect(screen.getByText("Latest")).toBeInTheDocument();
    expect(screen.getAllByText(/180 ms/u).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Define metric" }));
    const create = screen.getByRole("button", { name: "Create metric" });
    expect(create).toBeDisabled();
    await user.type(screen.getByLabelText(/Metric name/u), "API.NewMetric");
    await user.clear(screen.getByLabelText("Unit"));
    await user.type(screen.getByLabelText("Unit"), "count");
    await user.click(create);
    expect(mocks.createMetric).toHaveBeenCalledWith(
      expect.objectContaining({ metric_name: "api.newmetric", metric_type: "gauge", unit: "count" })
    );
  });

  it("registers telemetry sources and copies the OpenTelemetry quick start", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    renderPage(<InstrumentationSetupPage />);

    expect(await screen.findByText("OTLP collector")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy OpenTelemetry configuration" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("production"));

    await user.click(screen.getByRole("button", { name: "Register source" }));
    await user.type(screen.getByLabelText("Source name"), "Browser telemetry");
    const redactionLabel = screen.getByText("Redacted attributes").closest("label");
    if (!redactionLabel) throw new Error("Expected redaction label.");
    const redactionInput = within(redactionLabel).getByRole("textbox");
    fireEvent.change(redactionInput, { target: { value: "authorization, x-api-key" } });
    await user.click(screen.getAllByRole("button", { name: "Register source" })[1]!);
    expect(mocks.createTelemetrySource).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Browser telemetry",
        redaction_fields: ["authorization", "x-api-key"],
        sampling_rate: 0.5,
      })
    );
  });

  it("evaluates alert rules and creates absence rules without thresholds", async () => {
    const user = userEvent.setup();
    renderPage(<AlertRulesPage />);

    expect(await screen.findByText("High latency")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Evaluate" }));
    expect(mocks.evaluateAlertRule).toHaveBeenCalledWith("rule-1");
    await user.click(screen.getByRole("button", { name: "Alert center" }));
    expect(screen.getByTestId("path")).toHaveTextContent("/performance-monitoring/alerts");

    await user.click(screen.getByRole("button", { name: "New rule" }));
    await user.type(screen.getByLabelText("Name"), "Missing heartbeat");
    await user.type(screen.getByLabelText("Metric name"), "heartbeat.present");
    await user.selectOptions(screen.getByLabelText("Condition"), "absence");
    expect(screen.queryByLabelText("Threshold")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create rule" }));
    expect(mocks.createAlertRule).toHaveBeenCalledWith(
      expect.objectContaining({
        condition: "absence",
        metric_name: "heartbeat.present",
        name: "Missing heartbeat",
        threshold: null,
      })
    );
  });

  it("renders SLA compliance evidence, evaluates, reports, and validates SLA cadence", async () => {
    const user = userEvent.setup();
    renderPage(<SLAManagementPage />);

    expect(await screen.findByText("Runtime availability")).toBeInTheDocument();
    expect(screen.getByText(/98.9/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Evaluate now" }));
    await user.click(screen.getByRole("button", { name: "Generate report" }));
    expect(mocks.evaluateSLA).toHaveBeenCalledWith("sla-1");
    expect(mocks.generateSLAReport).toHaveBeenCalledWith({
      format: "json",
      period: "calendar_month",
      sla_id: "sla-1",
    });

    await user.click(screen.getByRole("button", { name: "Define SLA" }));
    await user.type(screen.getByLabelText("Service name"), "runtime-api");
    await user.type(screen.getByLabelText("Metric name"), "api.availability");
    await user.clear(screen.getByLabelText("Expected sample cadence (seconds)"));
    await user.type(screen.getByLabelText("Expected sample cadence (seconds)"), "9999");
    expect(screen.getByRole("button", { name: "Create SLA" })).toBeDisabled();
    await user.clear(screen.getByLabelText("Expected sample cadence (seconds)"));
    await user.type(screen.getByLabelText("Expected sample cadence (seconds)"), "120");
    await user.click(screen.getByRole("button", { name: "Create SLA" }));
    expect(mocks.createSLA).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_interval_seconds: 120,
        metric_name: "api.availability",
        service_name: "runtime-api",
      })
    );
  });

  it("renders dashboard summaries, stale/degraded banners, and setup navigation", async () => {
    mocks.listMetrics.mockRejectedValue(new Error("metric catalog offline"));
    renderPage(<PerformanceDashboardPage />);

    expect(await screen.findByText(/data source is unavailable/u)).toBeInTheDocument();
    expect(screen.getByText(/No connected source has reported/u)).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(screen.getByText("Latency breached")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Connect telemetry" }));
    expect(screen.getByTestId("path")).toHaveTextContent("/performance-monitoring/setup");
  });

  it("renders trace service maps with stale evidence and indexes selected spans", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date("2026-07-28T12:00:00Z"));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mocks.listServices.mockResolvedValue(page([service, staleService]));
    renderPage(<TraceExplorerPage />);

    expect(await screen.findByText("Runtime API")).toBeInTheDocument();
    expect(screen.getByText("Worker")).toBeInTheDocument();
    expect(screen.getByText(/stopped reporting/u)).toBeInTheDocument();
    expect(screen.getByText(/1 traces indexed/u)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Traces/u }));
    await user.click(await screen.findByText(trace.name));
    expect(await screen.findByText("Trace details")).toBeInTheDocument();
    expect(screen.getByText(span.name)).toBeInTheDocument();
    expect(screen.getByText(/Runtime API · client/u)).toBeInTheDocument();
    expect(mocks.listTraceSpans).toHaveBeenCalledWith(trace.id);
  });

  it("shows degraded Trace Explorer evidence when only one APM source fails", async () => {
    mocks.listTraces.mockRejectedValue(new Error("trace index offline"));
    renderPage(<TraceExplorerPage />);

    expect(await screen.findByText(/One APM data source is unavailable/u)).toBeInTheDocument();
    expect(screen.getByText("Trace count unavailable")).toBeInTheDocument();
    expect(screen.getByText("Runtime API")).toBeInTheDocument();
  });

  it("keeps Trace Explorer fail-closed when spans cannot load", async () => {
    const user = userEvent.setup();
    mocks.listTraceSpans.mockRejectedValue(new Error("span store unavailable"));
    renderPage(<TraceExplorerPage />);

    await user.click(await screen.findByRole("button", { name: /Traces/u }));
    const traceRow = (await screen.findByText(trace.name)).closest("tr");
    if (!traceRow) throw new Error("Expected trace row.");
    fireEvent.click(traceRow);

    expect(await screen.findByText("Trace details")).toBeInTheDocument();
    expect(await screen.findByText("Monitoring data is unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("triages active alerts and filters by persisted status", async () => {
    const user = userEvent.setup();
    renderPage(<ActiveAlertsPage />);

    expect(await screen.findByText(alert.title)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Acknowledge" }));
    await waitFor(() =>
      expect(mocks.acknowledgeAlert).toHaveBeenCalledWith(alert.id, {
        note: "Acknowledged from alert center",
      })
    );

    await user.selectOptions(screen.getByLabelText("Filter alert status"), "resolved");
    await waitFor(() =>
      expect(mocks.listAlerts).toHaveBeenLastCalledWith(
        expect.objectContaining({ ordering: "-triggered_at", page_size: 100, status: "resolved" })
      )
    );

    await user.click(screen.getByRole("button", { name: "Alert rules" }));
    expect(screen.getByTestId("path")).toHaveTextContent("/performance-monitoring/alerts/rules");
  });

  it("searches logs, expands attributes, and clears empty filtered evidence", async () => {
    const user = userEvent.setup();
    renderPage(<LogExplorerPage />);

    expect(await screen.findByText(logEntry.message)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Attributes" }));
    expect(screen.getByText(/status_code/u)).toBeInTheDocument();

    await user.type(
      screen.getByPlaceholderText("Search messages, correlation IDs or attributes"),
      "timeout"
    );
    await user.selectOptions(screen.getByLabelText("Filter by log level"), "error");
    await waitFor(() =>
      expect(mocks.listLogs).toHaveBeenLastCalledWith(
        expect.objectContaining({ level: "error", ordering: "-timestamp", page_size: 100 })
      )
    );

    mocks.listLogs.mockResolvedValue(page([]));
    await user.clear(screen.getByPlaceholderText("Search messages, correlation IDs or attributes"));
    await waitFor(() => expect(screen.getByText("No matching log events")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(
      screen.getByPlaceholderText("Search messages, correlation IDs or attributes")
    ).toHaveValue("");
  });

  it("keeps redirect and alias pages wired to the governed implementations", async () => {
    const { rerender } = renderPage(<PerformanceMonitoringIndexPage />);
    expect(await screen.findByTestId("path")).toHaveTextContent("/performance-monitoring");
    await waitFor(() => expect(document.title).toBe("Performance monitoring | SARAISE"));

    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter initialEntries={["/performance-monitoring/metrics"]}>
          <MetricsDashboardPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(await screen.findByText("Performance overview")).toBeInTheDocument();

    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter initialEntries={["/performance-monitoring/slo"]}>
          <SLOMonitoringPage />
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(await screen.findByText("Runtime availability")).toBeInTheDocument();
  });
});
