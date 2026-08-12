/* eslint-disable max-lines-per-function -- configuration lifecycle tests exercise stateful page workflows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  MonitoringConfiguration,
  MonitoringConfigurationAudit,
  MonitoringConfigurationDocument,
  MonitoringConfigurationRollbackRequest,
  MonitoringConfigurationVersion,
  MonitoringConfigurationWriteRequest,
} from "../contracts";
import { performanceMonitoringService } from "../services/performance-monitoring-service";
import { MonitoringConfigurationPage } from "../pages/MonitoringConfigurationPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn() },
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
    exportConfiguration: vi.fn(),
    getConfiguration: vi.fn(),
    importConfiguration: vi.fn(),
    listConfigurationAudit: vi.fn(),
    listConfigurationHistory: vi.fn(),
    previewConfiguration: vi.fn(),
    rollbackConfiguration: vi.fn(),
    updateConfiguration: vi.fn(),
  },
}));

const service = vi.mocked(performanceMonitoringService);

const documentFixture: MonitoringConfigurationDocument = {
  schema_version: "1.0",
  allowlists: {
    source_types: ["otlp", "prometheus"],
    metric_types: ["gauge", "counter"],
    alert_conditions: ["above_threshold"],
    severities: ["warning", "critical"],
    sla_comparisons: ["gte"],
    report_periods: ["rolling_24h"],
  },
  defaults: {
    telemetry_source: {
      sampling_rate: 0.5,
      retention_days: 30,
      daily_event_quota: 100000,
      redaction_fields: ["password"],
    },
    environment: { kind: "production" },
    service: { namespace: "saraise" },
    metric: {
      namespace: "application",
      unit: "ms",
      expected_interval_seconds: 60,
      retention_days: 30,
    },
    dashboard: { refresh_interval_seconds: 60, service_list_limit: 10, alert_list_limit: 10 },
    alert_rule: {
      threshold: 95,
      aggregation: "p95",
      evaluation_window_minutes: 5,
      evaluation_interval_seconds: 60,
      cooldown_minutes: 10,
      severity: "warning",
      notification_channels: ["email"],
    },
    alert: { initial_occurrence_count: 1 },
    sla: {
      target_percentage: 99.9,
      window: "rolling_24h",
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
    daily_event_quota_max: 1000000,
    metric_name_max_length: 128,
    metric_name_pattern: "^[a-z_]+$",
    max_tags_per_data_point: 20,
    max_batch_data_points: 1000,
    metric_query_max_range_days: 30,
    max_alert_rules: 100,
    alert_evaluation_timeout_seconds: 10,
    compliance_max_range_days: 90,
    log_message_max_length: 2000,
    max_spans_per_trace: 500,
    evaluation_window_max_minutes: 1440,
    cooldown_max_minutes: 1440,
    sla_cadence_min_seconds: 10,
    sla_cadence_max_seconds: 3600,
  },
  rules: { require_correlation_id: true },
  query: {
    interval_seconds: { one_minute: 60 },
    summary_period_seconds: { hour: 3600 },
    automatic_buckets: [{ max_range_seconds: 3600, bucket_seconds: 60 }],
    summary_percentiles: [50, 95, 99],
    explorer_time_ranges_minutes: [15, 60],
    metric_stale_interval_multiplier: 3,
    global_stale_threshold_minutes: 15,
  },
  delivery: {
    timeout_seconds: 10,
    max_attempts: 3,
    initial_backoff_seconds: 1,
    max_backoff_seconds: 60,
    jitter_ratio: 0.2,
    circuit_failure_threshold: 5,
    circuit_recovery_seconds: 30,
  },
  health: { cache_probe_timeout_seconds: 2, critical_dependencies: ["postgres"] },
  evidence: { retention_days: 365, archival_enabled: true, archive_provider: "s3" },
  pagination: { default_page_size: 25, max_page_size: 100 },
  rollout: { enabled: true, percentage: 25, roles: ["ops"], cohorts: ["beta"] },
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

const configuration: MonitoringConfiguration = {
  id: "config-1",
  tenant_id: "tenant-1",
  environment: "default",
  version: 7,
  document: documentFixture,
  updated_by: "operator-1",
  correlation_id: "corr-config",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
};

const history: readonly MonitoringConfigurationVersion[] = [
  {
    id: "version-6",
    environment: "default",
    version: 6,
    document: { ...documentFixture, rollout: { ...documentFixture.rollout, percentage: 10 } },
    actor_id: "operator-2",
    correlation_id: "corr-v6",
    change_reason: "Reduce rollout",
    created_at: "2026-07-21T00:00:00Z",
  },
];

const audit: readonly MonitoringConfigurationAudit[] = [
  {
    id: "audit-1",
    environment: "default",
    action: "update",
    from_version: 6,
    to_version: 7,
    before: history[0]?.document ?? documentFixture,
    after: documentFixture,
    actor_id: "operator-1",
    correlation_id: "corr-audit",
    change_reason: "Increase rollout",
    created_at: "2026-07-23T00:00:00Z",
  },
];

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MonitoringConfigurationPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("MonitoringConfigurationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    service.getConfiguration.mockResolvedValue(configuration);
    service.listConfigurationHistory.mockResolvedValue(history);
    service.listConfigurationAudit.mockResolvedValue(audit);
    service.previewConfiguration.mockImplementation((request) =>
      Promise.resolve({
        valid: true,
        current_version: 7,
        proposed_document: request.document,
        diff: [{ path: "defaults.telemetry_source.sampling_rate", before: 0.5, after: 0.75 }],
      })
    );
    service.updateConfiguration.mockResolvedValue(configuration);
    service.rollbackConfiguration.mockResolvedValue(configuration);
    service.importConfiguration.mockResolvedValue(configuration);
    service.exportConfiguration.mockResolvedValue({
      schema_version: "1.0",
      environment: "default",
      exported_version: 7,
      document: documentFixture,
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:monitoring"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  it("previews before save and sends the governed versioned payload", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("Version 7")).toBeInTheDocument();
    const samplingInput = screen.getAllByRole("spinbutton")[0];
    if (!samplingInput) throw new Error("Sampling input was not rendered.");
    fireEvent.change(samplingInput, { target: { value: "0.75" } });
    await user.type(screen.getByLabelText("Change reason"), "Raise ingestion sampling after QA");
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(service.previewConfiguration.mock.calls.length).toBeGreaterThan(0));
    const previewRequest: MonitoringConfigurationWriteRequest | undefined =
      service.previewConfiguration.mock.calls.at(-1)?.[0];
    expect(previewRequest?.expected_version).toBe(7);
    expect(previewRequest?.change_reason).toBe("Raise ingestion sampling after QA");
    expect(previewRequest?.document.defaults.telemetry_source.sampling_rate).toBe(0.75);
    expect(await screen.findByText(/1 change\(s\)/u)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save version" }));
    await waitFor(() => expect(service.updateConfiguration.mock.calls.length).toBeGreaterThan(0));
    const updateRequest: MonitoringConfigurationWriteRequest | undefined =
      service.updateConfiguration.mock.calls.at(-1)?.[0];
    expect(updateRequest?.expected_version).toBe(7);
    expect(updateRequest?.change_reason).toBe("Raise ingestion sampling after QA");
  });

  it("blocks malformed JSON, imports portable documents, exports, and rolls back with a reason", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByLabelText("Complete configuration JSON")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Complete configuration JSON"), {
      target: { value: "{{" },
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/Expected property name/u);
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();

    await user.clear(screen.getByLabelText("Change reason"));
    await user.type(screen.getByLabelText("Change reason"), "Restore audited settings");
    fireEvent.change(screen.getByLabelText("Imported configuration JSON"), {
      target: {
        value: JSON.stringify({
          schema_version: "1.0",
          environment: "default",
          exported_version: 6,
          document: documentFixture,
        }),
      },
    });
    await user.click(screen.getByRole("button", { name: "Validate and import" }));
    await waitFor(() => expect(service.importConfiguration.mock.calls.length).toBeGreaterThan(0));
    const importRequest: MonitoringConfigurationWriteRequest | undefined =
      service.importConfiguration.mock.calls.at(-1)?.[0];
    expect(importRequest?.expected_version).toBe(7);
    expect(importRequest?.change_reason).toBe("Restore audited settings");
    expect(importRequest?.document).toEqual(documentFixture);

    await user.click(screen.getByRole("button", { name: "Export" }));
    expect(service.exportConfiguration.mock.calls.at(-1)).toEqual(["default"]);

    await user.clear(screen.getByLabelText("Change reason"));
    await user.type(screen.getByLabelText("Change reason"), "Restore audited settings");
    await user.click(screen.getByRole("button", { name: "Rollback" }));
    await waitFor(() => expect(service.rollbackConfiguration.mock.calls.length).toBeGreaterThan(0));
    const rollbackRequest: MonitoringConfigurationRollbackRequest | undefined =
      service.rollbackConfiguration.mock.calls.at(-1)?.[0];
    expect(rollbackRequest?.version).toBe(6);
    expect(rollbackRequest?.expected_version).toBe(7);
    expect(rollbackRequest?.change_reason).toBe("Restore audited settings");
  });
});
