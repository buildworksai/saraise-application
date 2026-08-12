/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- RTL workflow tests use service spies and full DTO fixtures. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  DefinitionDetailDTO,
  DefinitionListDTO,
  NodeDescriptorDTO,
  OrchestrationConfigurationDTO,
  OrchestrationEdgeDTO,
  OrchestrationEventDTO,
  OrchestrationNodeDTO,
  OrchestrationScheduleDetailDTO,
  OrchestrationScheduleListDTO,
  PageResult,
  RunDetailDTO,
  RunListDTO,
  TaskRunDetailDTO,
  TaskRunListDTO,
} from "../../contracts";
import { EdgeEditor } from "../../components/EdgeEditor";
import { ScheduleEditor } from "../../components/ScheduleEditor";
import { Topology } from "../../components/Topology";
import { automationOrchestrationService as service } from "../../services/automation-orchestration-service";
import { DefinitionCreatePage } from "../DefinitionCreatePage";
import { DefinitionEditPage } from "../DefinitionEditPage";
import { RunDetailPage } from "../RunDetailPage";
import { RunsListPage } from "../RunsListPage";
import { SchedulesListPage } from "../SchedulesListPage";

const tenantId = "00000000-0000-4000-8000-000000000001";
const definitionId = "00000000-0000-4000-8000-000000000101";
const scheduleId = "00000000-0000-4000-8000-000000000201";
const runId = "00000000-0000-4000-8000-000000000301";
const parentRunId = "00000000-0000-4000-8000-000000000302";
const nodeOneId = "00000000-0000-4000-8000-000000000401";
const nodeTwoId = "00000000-0000-4000-8000-000000000402";
const taskId = "00000000-0000-4000-8000-000000000501";
const edgeId = "00000000-0000-4000-8000-000000000601";
const uuid = "00000000-0000-4000-8000-000000000999";

const configuration: OrchestrationConfigurationDTO = {
  id: "config-automation",
  environment: "development",
  cohort: "all",
  version: 4,
  enabled: true,
  rollout_percentage: 100,
  allowed_roles: ["automation-admin"],
  document: {
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
      cron_preview_count: 3,
      skeleton_rows: 5,
      duration_seconds_threshold_ms: 1000,
      zoom_default: 100,
      zoom_min: 50,
      zoom_max: 200,
      zoom_step: 25,
    },
  },
};

const definitionListItem: DefinitionListDTO = {
  id: definitionId,
  tenant_id: tenantId,
  key: "daily-close",
  version: 2,
  name: "Daily close",
  description: "Close ledgers safely",
  status: "published",
  is_current: true,
  graph_revision: 5,
  node_count: 2,
  schedule_count: 1,
  last_run_at: "2026-07-21T00:00:00Z",
  success_rate: 0.96,
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const nodeOne: OrchestrationNodeDTO = {
  id: nodeOneId,
  tenant_id: tenantId,
  definition_id: definitionId,
  key: "extract",
  name: "Extract invoices",
  description: "Extract invoice facts",
  node_type: "internal",
  handler_key: "http-call",
  config: { endpoint: "/invoices" },
  input_mapping: {},
  timeout_seconds: 60,
  max_attempts: 2,
  retry_initial_delay_seconds: 5,
  retry_backoff_multiplier: "2",
  retry_max_delay_seconds: 300,
  priority: 1,
  is_deleted: false,
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const nodeTwo: OrchestrationNodeDTO = {
  ...nodeOne,
  id: nodeTwoId,
  key: "post-ledger",
  name: "Post ledger",
  handler_key: "ledger-post",
};

const edge: OrchestrationEdgeDTO = {
  id: edgeId,
  tenant_id: tenantId,
  definition_id: definitionId,
  upstream_node_id: nodeOneId,
  downstream_node_id: nodeTwoId,
  condition: "on_success",
  priority: 1,
  is_deleted: false,
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const definitionDetail: DefinitionDetailDTO = {
  ...definitionListItem,
  status: "draft",
  max_parallel_tasks: 4,
  default_timeout_seconds: 120,
  default_max_attempts: 3,
  input_schema: {},
  output_schema: {},
  output_mapping: {},
  labels: {},
  contract_snapshot: {},
  transition_history: [],
  is_deleted: false,
  created_by: "user-1",
  updated_by: "user-1",
  deleted_at: null,
  nodes: [nodeOne, nodeTwo],
  edges: [edge],
};

const scheduleListItem: OrchestrationScheduleListDTO = {
  id: scheduleId,
  tenant_id: tenantId,
  definition_id: definitionId,
  definition_name: "Daily close",
  definition_key: "daily-close",
  definition_version: 2,
  name: "Hourly close",
  cron_expression: "0 * * * *",
  timezone: "UTC",
  status: "active",
  misfire_policy: "skip",
  concurrency_policy: "forbid",
  next_run_at: "2026-07-21T01:00:00Z",
  last_enqueued_at: null,
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const scheduleDetail: OrchestrationScheduleDetailDTO = {
  ...scheduleListItem,
  input: {},
  transition_history: [],
  is_deleted: false,
  deleted_at: null,
  created_by: "user-1",
  updated_by: "user-1",
};

const runListItem: RunListDTO = {
  id: runId,
  tenant_id: tenantId,
  definition_id: definitionId,
  definition_name: "Daily close",
  definition_key: "daily-close",
  definition_version: 2,
  schedule_id: scheduleId,
  parent_run_id: parentRunId,
  trigger_type: "schedule",
  status: "running",
  idempotency_key: "idem-run",
  correlation_id: "corr-run",
  requested_by: "user-1",
  task_count: 2,
  completed_task_count: 1,
  failed_task_count: 1,
  started_at: "2026-07-21T00:00:00Z",
  completed_at: null,
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:10:00Z",
};

const runDetail: RunDetailDTO = {
  ...runListItem,
  input: { source: "manual-test" },
  output: null,
  error_code: "TASK_FAILED",
  error_message: "Ledger write failed",
  transition_history: [],
};

const taskRun: TaskRunListDTO = {
  id: taskId,
  tenant_id: tenantId,
  run_id: runId,
  node_id: nodeOneId,
  node_key: "extract",
  node_name: "Extract invoices",
  status: "failed",
  remaining_dependencies: 0,
  current_attempt: 2,
  max_attempts: 3,
  error_code: "HTTP_500",
  error_message: "Upstream failed",
  started_at: "2026-07-21T00:01:00Z",
  completed_at: "2026-07-21T00:02:00Z",
  created_at: "2026-07-21T00:01:00Z",
  updated_at: "2026-07-21T00:02:00Z",
};

const taskDetail: TaskRunDetailDTO = {
  ...taskRun,
  node: nodeOne,
  input: { invoice_id: "INV-1" },
  output: null,
  transition_history: [],
  attempts: [
    {
      id: "attempt-1",
      tenant_id: tenantId,
      task_run_id: taskId,
      attempt_number: 1,
      status: "failed",
      available_at: "2026-07-21T00:01:00Z",
      correlation_id: "corr-attempt",
      output: null,
      error_code: "HTTP_500",
      error_message: "Upstream failed",
      duration_ms: 1000,
      transition_history: [],
      started_at: "2026-07-21T00:01:00Z",
      completed_at: "2026-07-21T00:02:00Z",
      created_at: "2026-07-21T00:01:00Z",
      updated_at: "2026-07-21T00:02:00Z",
    },
  ],
};

const event: OrchestrationEventDTO = {
  id: "event-1",
  tenant_id: tenantId,
  aggregate_type: "run",
  aggregate_id: runId,
  event_type: "run.started",
  actor_id: "user-1",
  correlation_id: "corr-run",
  payload: {},
  occurred_at: "2026-07-21T00:00:00Z",
};

const descriptor: NodeDescriptorDTO = {
  key: "http-call",
  display_name: "HTTP call",
  category: "Integration",
  description: "Call a governed endpoint",
  configuration_schema: { type: "object" },
  input_schema: {},
  output_schema: {},
  icon_key: "link",
  capability: "http",
  source_module: "automation_orchestration",
  spi_version: "1.0.0",
  module_version: "1.0.0",
  executor_version: "1.0.0",
  availability: "available",
  retry_safety: "idempotent",
};

function page<T>(items: readonly T[], pageNumber = 1): PageResult<T> {
  return {
    items,
    correlationId: "corr-test",
    receivedAt: "2026-07-21T00:00:00Z",
    pagination: {
      count: items.length,
      page: pageNumber,
      page_size: 25,
      total_pages: 2,
      has_next: pageNumber === 1,
      has_previous: pageNumber > 1,
    },
  };
}

function renderWithProviders(element: React.ReactElement, initialPath = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/" element={element} />
          <Route path="/automation-orchestration" element={<div>Definitions route</div>} />
          <Route path="/automation-orchestration/runs/:runId" element={<div>Run route</div>} />
          <Route
            path="/automation-orchestration/definitions/:id/edit"
            element={<div>Builder route</div>}
          />
          <Route
            path="/automation-orchestration/definitions/:id"
            element={<div>Definition detail route</div>}
          />
          <Route path="/automation-orchestration/schedules" element={<div>Schedules route</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderRoute(element: React.ReactElement, path: string, pattern: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={element} />
          <Route path="/automation-orchestration" element={<div>Definitions route</div>} />
          <Route path="/automation-orchestration/schedules" element={<div>Schedules route</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("automation orchestration workflow coverage", () => {
  beforeEach(() => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue(uuid);
    vi.spyOn(service, "getConfiguration").mockResolvedValue(configuration);
  });

  afterEach(() => vi.restoreAllMocks());

  it("filters run history, preserves lineage navigation, and resets pagination filters", async () => {
    vi.spyOn(service, "listRuns").mockResolvedValue(page([runListItem]));
    vi.spyOn(service, "listDefinitions").mockResolvedValue(page([definitionListItem]));
    renderWithProviders(<RunsListPage />);

    fireEvent.change(await screen.findByLabelText("Correlation ID"), {
      target: { value: "corr-run" },
    });
    fireEvent.change(await screen.findByLabelText("Run status"), { target: { value: "failed" } });
    fireEvent.change(await screen.findByLabelText("Trigger type"), {
      target: { value: "schedule" },
    });
    fireEvent.change(await screen.findByLabelText("Definition"), {
      target: { value: definitionId },
    });
    await waitFor(() =>
      expect(service.listRuns).toHaveBeenLastCalledWith(
        expect.objectContaining({
          correlation_id: "corr-run",
          status: "failed",
          trigger_type: "schedule",
          definition_id: definitionId,
          page: 1,
          page_size: 25,
        })
      )
    );

    const runLink = screen
      .getAllByRole("link", { name: /00000000/u })
      .find((link) => link.getAttribute("href") === `/automation-orchestration/runs/${runId}`);
    expect(runLink).toHaveAttribute("href", `/automation-orchestration/runs/${runId}`);
    expect(screen.getByRole("link", { name: /retry of 00000000/u })).toHaveAttribute(
      "href",
      `/automation-orchestration/runs/${parentRunId}`
    );
    expect(screen.getByText("100% · 1/2")).toBeInTheDocument();
  });

  it("surfaces schedule lifecycle failures and clears filtered empty states", async () => {
    vi.spyOn(service, "listSchedules").mockImplementation((filters = {}) =>
      Promise.resolve(filters.search ? page([]) : page([scheduleListItem]))
    );
    vi.spyOn(service, "pauseSchedule").mockRejectedValue(new Error("transition denied"));
    renderWithProviders(<SchedulesListPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Pause Hourly close" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("transition denied");
    expect(service.pauseSchedule).toHaveBeenCalledWith(scheduleId, uuid);

    await userEvent.type(screen.getByLabelText("Search schedules"), "missing");
    expect(await screen.findByText("No schedules match")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() =>
      expect(service.listSchedules).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: undefined, status: undefined, page: 1 })
      )
    );
  });

  it("validates create-definition limits and navigates after a governed payload succeeds", async () => {
    vi.spyOn(service, "createDefinition").mockResolvedValue(definitionDetail);
    renderWithProviders(<DefinitionCreatePage />);

    await userEvent.type(await screen.findByLabelText("Name"), "No");
    await userEvent.click(screen.getByRole("button", { name: /Create and open builder/u }));
    expect(
      await screen.findByText("String must contain at least 3 character(s)")
    ).toBeInTheDocument();
    expect(service.createDefinition).not.toHaveBeenCalled();

    await userEvent.clear(screen.getByLabelText("Name"));
    await userEvent.type(screen.getByLabelText("Name"), "Nightly Close");
    await userEvent.clear(screen.getByLabelText("Stable key"));
    await userEvent.type(screen.getByLabelText("Stable key"), "nightly-close");
    await userEvent.clear(screen.getByLabelText("Maximum parallel tasks"));
    await userEvent.type(screen.getByLabelText("Maximum parallel tasks"), "5");
    await userEvent.click(screen.getByRole("button", { name: /Create and open builder/u }));

    await waitFor(() =>
      expect(service.createDefinition).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Nightly Close",
          key: "nightly-close",
          max_parallel_tasks: 5,
          default_timeout_seconds: 120,
          default_max_attempts: 3,
          input_schema: { type: "object", properties: {}, additionalProperties: false },
        })
      )
    );
    expect(await screen.findByText("Builder route")).toBeInTheDocument();
  });

  it("edits graph nodes, validates on the server, and reports invalid JSON fail-closed", async () => {
    vi.spyOn(service, "getDefinition").mockResolvedValue(definitionDetail);
    vi.spyOn(service, "listNodeTypes").mockResolvedValue(page([descriptor]));
    vi.spyOn(service, "updateNode").mockResolvedValue(nodeOne);
    vi.spyOn(service, "validateDefinition").mockResolvedValue({
      valid: false,
      validated_revision: 5,
      issues: [
        {
          code: "MISSING_EDGE",
          severity: "error",
          message: "Terminal task is unreachable.",
          entity_type: "node",
          entity_id: nodeTwoId,
          pointer: "/edges",
          remediation: "Connect the dependency.",
        },
      ],
    });
    renderRoute(
      <DefinitionEditPage />,
      `/automation-orchestration/definitions/${definitionId}/edit`,
      "/automation-orchestration/definitions/:id/edit"
    );

    const extractNode = await screen.findByText("Extract invoices");
    await userEvent.click(extractNode.closest("button")!);
    const json = screen.getByLabelText("Node configuration JSON");
    fireEvent.change(json, { target: { value: "{bad" } });
    await userEvent.click(screen.getByRole("button", { name: "Save node settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Expected property name or '}' in JSON"
    );
    expect(service.updateNode).not.toHaveBeenCalled();

    fireEvent.change(json, { target: { value: '{"endpoint":"/safe"}' } });
    await userEvent.click(screen.getByRole("button", { name: "Save node settings" }));
    await waitFor(() =>
      expect(service.updateNode).toHaveBeenCalledWith(
        nodeOneId,
        expect.objectContaining({
          timeout_seconds: 60,
          max_attempts: 2,
          config: { endpoint: "/safe" },
        })
      )
    );

    await userEvent.click(screen.getByRole("button", { name: "Server validate" }));
    expect(await screen.findByText("Graph needs attention")).toBeInTheDocument();
    expect(screen.getByText("Terminal task is unreachable.")).toBeInTheDocument();
  });

  it("creates and deletes dependency edges through selected topology controls", async () => {
    const onChanged = vi.fn();
    vi.spyOn(service, "createEdge").mockResolvedValue(edge);
    vi.spyOn(service, "deleteEdge").mockResolvedValue(undefined);
    renderWithProviders(
      <EdgeEditor
        definitionId={definitionId}
        selectedNodeId={nodeOneId}
        nodes={[nodeOne, nodeTwo]}
        edges={[edge]}
        onChanged={onChanged}
      />
    );

    await userEvent.selectOptions(await screen.findByLabelText("Downstream node"), nodeTwoId);
    await userEvent.selectOptions(screen.getByLabelText("Edge condition"), "always");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() =>
      expect(service.createEdge).toHaveBeenCalledWith(definitionId, {
        upstream_node_id: nodeOneId,
        downstream_node_id: nodeTwoId,
        condition: "always",
      })
    );

    await userEvent.click(screen.getByRole("button", { name: "Remove edge to Post ledger" }));
    await waitFor(() => expect(service.deleteEdge).toHaveBeenCalledWith(edgeId));
    expect(onChanged).toHaveBeenCalledTimes(2);
  });

  it("previews and saves schedules only when cron simulation proves an upcoming run", async () => {
    vi.spyOn(service, "listDefinitions").mockResolvedValue(page([definitionListItem]));
    vi.spyOn(service, "createSchedule").mockResolvedValue(scheduleDetail);
    renderWithProviders(<ScheduleEditor />);

    await userEvent.type(await screen.findByLabelText("Name"), "Hourly close");
    await userEvent.selectOptions(screen.getByLabelText("Published definition"), definitionId);
    await userEvent.clear(screen.getByLabelText("Cron expression"));
    await userEvent.type(screen.getByLabelText("Cron expression"), "bad cron");
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(await screen.findByText(/cannot produce a valid upcoming run/u)).toBeInTheDocument();
    expect(service.createSchedule).not.toHaveBeenCalled();

    await userEvent.clear(screen.getByLabelText("Cron expression"));
    await userEvent.type(screen.getByLabelText("Cron expression"), "*/15 * * * *");
    expect(screen.getByText("Upcoming scheduled times")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    await waitFor(() =>
      expect(service.createSchedule).toHaveBeenCalledWith({
        definition_id: definitionId,
        name: "Hourly close",
        cron_expression: "*/15 * * * *",
        timezone: "UTC",
        misfire_policy: "skip",
        concurrency_policy: "forbid",
        input: {},
      })
    );
    expect(await screen.findByText("Schedules route")).toBeInTheDocument();
  });

  it("loads existing schedules as immutable definition bindings and patches editable policy", async () => {
    vi.spyOn(service, "listDefinitions").mockResolvedValue(page([definitionListItem]));
    vi.spyOn(service, "getSchedule").mockResolvedValue(scheduleDetail);
    vi.spyOn(service, "updateSchedule").mockResolvedValue(scheduleDetail);
    renderRoute(
      <ScheduleEditor scheduleId={scheduleId} />,
      `/automation-orchestration/schedules/${scheduleId}/edit`,
      "/automation-orchestration/schedules/:id/edit"
    );

    expect(await screen.findByLabelText("Published definition")).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Name"));
    await userEvent.type(screen.getByLabelText("Name"), "Hourly close safe");
    await userEvent.selectOptions(screen.getByLabelText("Misfire policy"), "run_once");
    await userEvent.click(screen.getByRole("button", { name: "Save schedule" }));
    await waitFor(() =>
      expect(service.updateSchedule).toHaveBeenCalledWith(scheduleId, {
        name: "Hourly close safe",
        cron_expression: "0 * * * *",
        timezone: "UTC",
        misfire_policy: "run_once",
        concurrency_policy: "forbid",
        input: {},
      })
    );
  });

  it("renders topology dependency counts and selects task-backed evidence nodes", async () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <Topology
        nodes={[nodeOne, nodeTwo]}
        edges={[edge]}
        taskRuns={[taskRun]}
        selectedNodeId={nodeOneId}
        onSelect={onSelect}
      />
    );

    expect(screen.getByText("Root node")).toBeInTheDocument();
    expect(screen.getByText("1 dependency")).toBeInTheDocument();
    expect(screen.getByText("Minimap · 2 nodes · 1 edges")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Post ledger").closest("button")!);
    expect(onSelect).toHaveBeenCalledWith(nodeTwoId);
  });

  it("controls failed run and task retries while showing immutable evidence", async () => {
    vi.spyOn(service, "getRun").mockResolvedValue({ ...runDetail, status: "failed" });
    vi.spyOn(service, "getDefinition").mockResolvedValue(definitionDetail);
    vi.spyOn(service, "listTaskRuns").mockResolvedValue(page([taskRun]));
    vi.spyOn(service, "listEvents").mockResolvedValue(page([event]));
    vi.spyOn(service, "getTaskRun").mockResolvedValue(taskDetail);
    vi.spyOn(service, "retryRun").mockResolvedValue(runDetail);
    vi.spyOn(service, "retryTaskRun").mockResolvedValue(taskDetail);
    renderRoute(
      <RunDetailPage />,
      `/automation-orchestration/runs/${runId}`,
      "/automation-orchestration/runs/:runId"
    );

    await userEvent.click(await screen.findByRole("button", { name: "Retry run" }));
    await waitFor(() =>
      expect(service.retryRun).toHaveBeenCalledWith(runId, { idempotency_key: uuid })
    );

    const taskRow = await screen.findByRole("button", { name: "Inspect Extract invoices" });
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(service.retryTaskRun).toHaveBeenCalledWith(taskId, { idempotency_key: uuid })
    );

    await userEvent.click(taskRow);
    await waitFor(() => expect(service.getTaskRun).toHaveBeenCalledWith(taskId));
    expect(
      await screen.findByText((text) => text.includes('"invoice_id": "INV-1"'))
    ).toBeInTheDocument();
    expect(screen.getByText("run.started")).toBeInTheDocument();
    expect(screen.getByText("TASK_FAILED: Ledger write failed")).toBeInTheDocument();
  });
});
