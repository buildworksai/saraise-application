/* eslint-disable @typescript-eslint/unbound-method -- Vitest spies intentionally reference service methods. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ConfigurationAuditDTO,
  ConfigurationPreviewDTO,
  ConfigurationVersionDTO,
  OrchestrationConfigurationDTO,
  OrchestrationConfigurationDocument,
  PageResult,
} from "../../contracts";
import { automationOrchestrationService as service } from "../../services/automation-orchestration-service";
import { ConfigurationPage } from "../ConfigurationPage";

const documentValue: OrchestrationConfigurationDocument = {
  limits: {
    json_bytes: 4096,
    json_depth: 8,
    parallel_tasks_min: 1,
    parallel_tasks_max: 10,
    timeout_seconds_min: 5,
    timeout_seconds_max: 3600,
    attempts_min: 1,
    attempts_max: 5,
    retry_multiplier_min: 1,
    retry_multiplier_max: 3,
    page_size_default: 25,
    page_size_max: 100,
    idempotency_key_length: 36,
    event_metadata_bytes: 2048,
    schedule_scan_batch: 50,
    definition_name_min: 3,
    definition_name_max: 120,
    description_max: 500,
    schedule_name_min: 3,
    schedule_name_max: 120,
  },
  defaults: {
    max_parallel_tasks: 4,
    timeout_seconds: 120,
    max_attempts: 3,
    retry_initial_delay_seconds: 5,
    retry_backoff_multiplier: 2,
    retry_max_delay_seconds: 300,
    retry_jitter_ratio: 0.2,
    edge_condition: "on_success",
    edge_priority: 1,
    timezone: "UTC",
    schedule_status: "active",
    misfire_policy: "skip",
    concurrency_policy: "forbid",
    cron_expression: "0 * * * *",
    input_schema: {},
    output_schema: {},
  },
  workflow: {},
  integrations: {},
  scheduler: {
    cron_fields: 5,
    search_horizon_days: 30,
    active_status: "active",
    enqueue_misfire_policies: ["run_once"],
    forbid_overlap_policy: "forbid",
  },
  health: {
    scanner_heartbeat_ttl_seconds: 120,
    pending_outbox_freshness_seconds: 300,
    scanner_freshness_seconds: 300,
    registry_staleness_seconds: 600,
  },
  ui: {
    definition_detail_page_size: 25,
    definition_page_size: 25,
    schedule_page_size: 25,
    task_run_page_size: 25,
    published_definition_page_size: 25,
    run_poll_interval_ms: 5000,
    run_detail_poll_interval_ms: 5000,
    event_poll_interval_ms: 5000,
    cron_preview_count: 5,
    skeleton_rows: 5,
    duration_seconds_threshold_ms: 1000,
    zoom_default: 1,
    zoom_min: 0.5,
    zoom_max: 2,
    zoom_step: 0.1,
  },
};

const configuration: OrchestrationConfigurationDTO = {
  id: "config-1",
  environment: "development",
  cohort: "all",
  version: 3,
  enabled: true,
  rollout_percentage: 100,
  allowed_roles: ["automation-admin"],
  document: documentValue,
  updated_by: "user-1",
  updated_at: "2026-07-21T00:00:00Z",
};

function page<T>(items: readonly T[]): PageResult<T> {
  return {
    items,
    correlationId: "corr-page",
    receivedAt: "2026-07-21T00:00:00Z",
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

const olderVersion: ConfigurationVersionDTO = {
  id: "version-2",
  version: 2,
  document: documentValue,
  enabled: true,
  rollout_percentage: 80,
  allowed_roles: [],
  actor_id: "user-2",
  correlation_id: "corr-v2",
  parent_version_id: null,
  rollback_of_id: null,
  created_at: "2026-07-20T00:00:00Z",
};

const audit: ConfigurationAuditDTO = {
  id: "audit-1",
  action: "update",
  version: 3,
  actor_id: "user-1",
  correlation_id: "corr-audit",
  changed_at: "2026-07-21T00:00:00Z",
  before: null,
  after: configuration,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ConfigurationPage />
    </QueryClientProvider>
  );
}

describe("automation orchestration ConfigurationPage", () => {
  beforeEach(() => {
    vi.spyOn(service, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(service, "listConfigurationVersions").mockResolvedValue(page([olderVersion]));
    vi.spyOn(service, "listConfigurationAudits").mockResolvedValue(page([audit]));
    vi.spyOn(service, "updateConfiguration").mockResolvedValue(configuration);
    vi.spyOn(service, "previewConfiguration").mockResolvedValue({
      valid: true,
      changed_sections: ["defaults"],
      before: documentValue,
      after: { ...documentValue, defaults: { ...documentValue.defaults, max_parallel_tasks: 5 } },
    } satisfies ConfigurationPreviewDTO);
    vi.spyOn(service, "rollbackConfiguration").mockResolvedValue(configuration);
    vi.spyOn(service, "importConfiguration").mockResolvedValue(configuration);
    vi.spyOn(service, "exportConfiguration").mockResolvedValue(configuration);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:test"),
    });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    Object.defineProperty(File.prototype, "text", {
      configurable: true,
      value: vi.fn(() => Promise.resolve("not-json")),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  it("blocks preview and save when guided safe limits are invalid", async () => {
    renderPage();
    await userEvent.clear(await screen.findByLabelText("Parallel minimum"));
    await userEvent.type(screen.getByLabelText("Parallel minimum"), "11");

    expect(screen.getByText("Parallel minimum exceeds maximum.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Preview/u })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Apply version/u })).toBeDisabled();
  });

  it("sends trimmed roles through preview and renders the dry-run diff", async () => {
    renderPage();
    const roles = await screen.findByLabelText("Allowed roles");
    await userEvent.clear(roles);
    await userEvent.type(roles, "ops, automation-admin, ");
    await userEvent.click(screen.getByRole("button", { name: /Preview/u }));

    await waitFor(() => expect(service.previewConfiguration).toHaveBeenCalled());
    expect(service.previewConfiguration).toHaveBeenCalledWith(
      expect.objectContaining({ allowed_roles: ["ops", "automation-admin"] })
    );
    expect(await screen.findByText("Changed sections: defaults")).toBeInTheDocument();
  });

  it("rolls back, exports, and rejects malformed imports without calling import", async () => {
    const view = renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /Rollback/u }));
    await waitFor(() =>
      expect(service.rollbackConfiguration).toHaveBeenCalledWith("development", "all", 2)
    );

    await userEvent.click(screen.getByRole("button", { name: /Export JSON/u }));
    await waitFor(() =>
      expect(service.exportConfiguration).toHaveBeenCalledWith("development", "all")
    );
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();

    const input = view.container.querySelector<HTMLInputElement>("input[type='file']");
    expect(input).not.toBeNull();
    await userEvent.upload(
      input!,
      new File(["not-json"], "bad.json", { type: "application/json" })
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/Unexpected token/u);
    expect(service.importConfiguration).not.toHaveBeenCalled();
  });
});
