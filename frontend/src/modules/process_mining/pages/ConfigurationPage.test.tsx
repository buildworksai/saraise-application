/* eslint-disable @typescript-eslint/unbound-method -- Vitest spies intentionally reference service methods. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ModuleHealth,
  PaginatedResult,
  ProcessMiningConfiguration,
  ProcessMiningConfigurationDocument,
  ProcessMiningConfigurationVersion,
} from "../contracts";
import { processMiningService } from "../services/process_mining-service";
import { ConfigurationPage } from "./ConfigurationPage";

const documentValue: ProcessMiningConfigurationDocument = {
  environment: "development",
  max_batch_events: 1000,
  max_export_events: 1000,
  max_export_bytes: 100000,
  max_conformance_events: 1000,
  text_max_length: 255,
  attributes_max_bytes: 4096,
  forbidden_attribute_keys: ["password"],
  source_module_max_length: 64,
  max_event_age_days: 365,
  future_clock_skew_seconds: 60,
  bulk_insert_batch_size: 100,
  event_query_max_days: 90,
  retention_days: 30,
  retention_min_days: 7,
  export_projection_bytes_per_event: 128,
  export_iterator_chunk_size: 500,
  checksum_chunk_bytes: 1024,
  export_expiry_days: 7,
  discovery_min_events: 10,
  discovery_min_cases: 2,
  alpha_max_activities: 50,
  heuristic_default_threshold: 0.8,
  inductive_default_threshold: 0.8,
  default_discovery_algorithm: "heuristic_miner",
  algorithm_threshold_step: 0.05,
  algorithm_threshold_min: 0.1,
  algorithm_threshold_max: 1,
  low_fitness_threshold: 0.6,
  bottleneck_reuse_minutes: 30,
  bottleneck_min_cases: 5,
  bottleneck_critical_ratio: 0.9,
  bottleneck_high_ratio: 0.7,
  bottleneck_medium_ratio: 0.5,
  tail_duration_percentile: 0.95,
  resource_concentration_threshold: 0.6,
  variant_grouping_percentage: 0.05,
  outbox_freshness_seconds: 60,
  analysis_transitions: { queued: ["running"], running: ["completed", "failed"] },
  analysis_terminal_states: ["completed", "failed", "cancelled", "timed_out"],
  export_transitions: { queued: ["running"], running: ["completed", "failed"] },
  export_terminal_states: ["completed", "failed", "cancelled", "timed_out", "expired"],
  default_time_window_days: 30,
  list_page_size: 25,
  detail_page_size: 50,
  polling_interval_ms: 5000,
  visual_zoom_min: 0.5,
  visual_zoom_max: 2,
  visual_zoom_step: 0.1,
  visual_edge_width_min: 1,
  visual_edge_width_max: 8,
  visual_frequency_divisor: 10,
  visual_duration_divisor: 60,
  visual_canvas_width: 1200,
  visual_canvas_height: 800,
  visual_node_width: 160,
  visual_node_height: 80,
  visual_layout_columns: 4,
  visual_horizontal_gap: 120,
  visual_vertical_gap: 90,
  visual_layout_padding: 40,
  download_timeout_ms: 1000,
  download_retry_attempts: 2,
  download_retry_base_ms: 100,
  download_circuit_failure_threshold: 3,
  download_circuit_reset_ms: 60000,
  enabled: true,
  rollout_roles: ["process-admin"],
  rollout_cohorts: ["all"],
};

const configuration: ProcessMiningConfiguration = {
  id: "config-1",
  version: 4,
  document: documentValue,
  limits: {},
  updated_at: "2026-07-21T00:00:00Z",
};

const health: ModuleHealth = {
  status: "healthy",
  live: true,
  ready: true,
  checked_at: "2026-07-21T00:00:00Z",
  dependencies: [
    {
      name: "event-store",
      status: "healthy",
      code: "READY",
      checked_at: "2026-07-21T00:00:00Z",
    },
  ],
};

function page<T>(items: readonly T[]): PaginatedResult<T> {
  return {
    items: [...items],
    correlationId: "corr-page",
    pagination: {
      count: items.length,
      page: 1,
      page_size: 25,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ConfigurationPage />
    </QueryClientProvider>
  );
}

describe("process mining ConfigurationPage", () => {
  beforeEach(() => {
    vi.spyOn(processMiningService, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(processMiningService, "configurationHistory").mockResolvedValue(
      page<ProcessMiningConfigurationVersion>([
        {
          id: "version-3",
          version: 3,
          document: documentValue,
          source: "update",
          correlation_id: "corr-version",
          created_at: "2026-07-20T00:00:00Z",
        },
      ])
    );
    vi.spyOn(processMiningService, "health").mockResolvedValue(health);
    vi.spyOn(processMiningService, "previewConfiguration").mockResolvedValue({
      valid: true,
      current_version: 4,
      changes: { retention_days: { from: 30, to: 45 } },
      document: { ...documentValue, retention_days: 45 },
    });
    vi.spyOn(processMiningService, "updateConfiguration").mockResolvedValue(configuration);
    vi.spyOn(processMiningService, "rollbackConfiguration").mockResolvedValue(configuration);
    vi.spyOn(processMiningService, "importConfiguration").mockResolvedValue(configuration);
    vi.spyOn(processMiningService, "exportConfiguration").mockResolvedValue({
      schema_version: "1.0",
      module: "process_mining",
      version: 4,
      document: documentValue,
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:process"),
    });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  it("prevents preview and save when dependent limits are invalid", async () => {
    renderPage();

    await userEvent.clear(await screen.findByLabelText("retention days"));
    await userEvent.type(screen.getByLabelText("retention days"), "1");

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Retention days must be at least the configured minimum."
    );
    expect(screen.getByRole("button", { name: /Preview changes/u })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Save version/u })).toBeDisabled();
  });

  it("previews, saves, imports, exports, and rolls back through governed service methods", async () => {
    renderPage();

    await userEvent.clear(await screen.findByLabelText("retention days"));
    await userEvent.type(screen.getByLabelText("retention days"), "45");
    await userEvent.click(screen.getByRole("button", { name: /Preview changes/u }));
    expect(await screen.findByText(/retention_days/u)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Save version/u }));
    await waitFor(() =>
      expect(processMiningService.updateConfiguration).toHaveBeenCalledWith(
        expect.objectContaining({ retention_days: 45 })
      )
    );

    await userEvent.click(screen.getByRole("button", { name: /Export/u }));
    await waitFor(() => expect(processMiningService.exportConfiguration).toHaveBeenCalled());
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Import process mining configuration JSON"), {
      target: {
        value: JSON.stringify({
          schema_version: "1.0",
          module: "process_mining",
          version: 4,
          document: { ...documentValue, retention_days: 60 },
        }),
      },
    });
    await userEvent.click(screen.getByRole("button", { name: /Import as new version/u }));
    await waitFor(() =>
      expect(processMiningService.importConfiguration).toHaveBeenCalledWith(
        expect.objectContaining({ version: 4 })
      )
    );

    await userEvent.click(screen.getByRole("button", { name: /Rollback/u }));
    await waitFor(() => expect(processMiningService.rollbackConfiguration).toHaveBeenCalledWith(3));
  });
});
