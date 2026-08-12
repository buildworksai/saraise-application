/* eslint-disable max-lines-per-function -- component state coverage keeps fixtures and assertions local. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type { MonitoringConfigurationDocument } from "../contracts";
import {
  EmptyTelemetry,
  MonitoringPage,
  OperationalError,
  StateBanner,
  StatusPill,
  formatNumber,
  formatTime,
  isStale,
  useLogLevelClass,
  useMonitoringConfiguration,
} from "./MonitoringPage";

const mocks = vi.hoisted(() => ({
  getConfiguration: vi.fn(),
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
  performanceMonitoringService: {
    getConfiguration: mocks.getConfiguration,
  },
}));

const monitoringDocument: MonitoringConfigurationDocument = {
  schema_version: "1.0",
  allowlists: {
    source_types: ["otlp"],
    metric_types: ["gauge"],
    alert_conditions: ["above_threshold"],
    severities: ["warning"],
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
    slo: {
      window_days: 30,
      expected_interval_seconds: 60,
      error_budget_minutes: 43,
    },
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
  rules: { fail_closed: true },
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

const configuration = {
  id: "00000000-0000-4000-8000-000000000001",
  tenant_id: "00000000-0000-4000-8000-000000000002",
  environment: "default",
  version: 3,
  document: monitoringDocument,
  updated_by: "00000000-0000-4000-8000-000000000003",
  correlation_id: "corr-monitoring-config",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
};

function queryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderWithProviders(node: React.ReactNode, initial = "/performance-monitoring/metrics") {
  return render(
    <QueryClientProvider client={queryClient()}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="*" element={node} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function ConfigurationProbe() {
  const config = useMonitoringConfiguration();
  const warnClass = useLogLevelClass("warn");
  const fatalClass = useLogLevelClass("fatal");
  return (
    <>
      <output aria-label="Configured max page size">{config.pagination.max_page_size}</output>
      <output aria-label="Warning class">{warnClass}</output>
      <output aria-label="Fatal class">{fatalClass}</output>
      <StateBanner state="stale">Last point was older than the tenant limit.</StateBanner>
      <StateBanner state="degraded">Redis dependency failed its probe.</StateBanner>
      <StatusPill status="critical" />
      <StatusPill status="resolved" />
    </>
  );
}

describe("MonitoringPage governed shell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    globalThis.document.title = "SARAISE";
    mocks.getConfiguration.mockResolvedValue(configuration);
  });

  it("loads tenant configuration before rendering children and navigation", async () => {
    renderWithProviders(
      <MonitoringPage title="Metric explorer" description="Inspect governed metric evidence.">
        <ConfigurationProbe />
      </MonitoringPage>
    );

    expect(screen.getByRole("status", { name: "Loading monitoring data" })).toHaveTextContent(
      "Loading monitoring data"
    );
    expect(await screen.findByRole("heading", { name: "Metric explorer" })).toBeInTheDocument();
    expect(screen.getByLabelText("Configured max page size")).toHaveTextContent("100");
    expect(screen.getByLabelText("Warning class")).toHaveTextContent("text-foreground");
    expect(screen.getByLabelText("Fatal class")).toHaveTextContent("text-destructive font-bold");
    expect(screen.getByText("Telemetry is stale.")).toBeInTheDocument();
    expect(screen.getByText("Partial data.")).toBeInTheDocument();
    expect(screen.getByText("critical")).toHaveClass("text-destructive");
    expect(screen.getByText("resolved")).toHaveClass("text-primary");
    expect(
      screen.getByRole("navigation", { name: "Performance monitoring sections" })
    ).toBeInTheDocument();
    await waitFor(() => expect(globalThis.document.title).toBe("Metric explorer | SARAISE"));
  });

  it("fails closed when configuration is unavailable and retries without rendering children", async () => {
    mocks.getConfiguration
      .mockRejectedValueOnce(new Error("configuration offline"))
      .mockResolvedValueOnce(configuration);
    renderWithProviders(
      <MonitoringPage title="Alerts" description="Review alert state.">
        <ConfigurationProbe />
      </MonitoringPage>
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Monitoring configuration unavailable"
    );
    expect(screen.queryByLabelText("Configured max page size")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("Configured max page size")).toHaveTextContent("100");
    expect(mocks.getConfiguration).toHaveBeenCalledTimes(2);
  });

  it("requires configuration context for semantic components", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<StatusPill status="ok" />)).toThrow(
      "Monitoring configuration context is unavailable."
    );
    vi.mocked(console.error).mockRestore();
  });
});

describe("monitoring utility states", () => {
  it("renders operational errors by status without replacing evidence", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <OperationalError
        error={new ApiError("Denied", 403, undefined, "permission_denied", "corr-denied")}
        onRetry={onRetry}
      />
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Permission required");
    rerender(<OperationalError error={new Error("offline")} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Monitoring data is unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders empty telemetry actions and stable formatting helpers", () => {
    render(<EmptyTelemetry title="No traces" description="No trace evidence matched." />);
    expect(screen.getByRole("heading", { name: "No traces" })).toBeInTheDocument();
    expect(formatNumber(undefined)).toBe("Unavailable");
    expect(formatNumber(1250)).toMatch(/1,250|1.250/u);
    expect(formatTime(null)).toBe("Never");
    expect(formatTime("not-a-date")).toBe("Unknown");

    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-22T10:00:00Z"));
    expect(isStale("2026-07-22T09:40:00Z", 10)).toBe(true);
    expect(isStale("2026-07-22T09:55:00Z", 10)).toBe(false);
    expect(isStale(undefined, 10)).toBe(true);
    vi.useRealTimers();
  });
});
