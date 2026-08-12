/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- Page-flow tests assert service calls and keep typed fixtures local to this module. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import { ApiProblem, Pagination, StatusPill } from "../components/ModuleShell";
import {
  deterministicKey,
  formatDate,
  formatDuration,
  useCanManageProcessMining,
} from "../components/utils";
import type {
  DiscoveryCreateRequest,
  DiscoveryJob,
  EventExport,
  EventExportCreateRequest,
  BottleneckAnalysis,
  BottleneckCreateRequest,
  BottleneckFinding,
  ConformanceCheck,
  ConformanceCreateRequest,
  ConformanceDeviation,
  CaseFitness,
  ModuleHealth,
  PaginatedResult,
  ProcessEvent,
  ProcessMiningConfiguration,
  ProcessMiningConfigurationDocument,
  ProcessModel,
  ProcessModelVersion,
  ProcessOverview,
  TransitionActionRequest,
} from "../contracts";
import { ProcessMiningApiError, processMiningService } from "../services/process_mining-service";
import { CreateDiscoveryPage } from "./CreateDiscoveryPage";
import { CreateExportPage } from "./CreateExportPage";
import { CreateProcessModelPage } from "./CreateProcessModelPage";
import { CreateConformancePage } from "./CreateConformancePage";
import { CreateBottleneckAnalysisPage } from "./CreateBottleneckAnalysisPage";
import { ConformanceDetailPage } from "./ConformanceDetailPage";
import { ConformanceListPage } from "./ConformanceListPage";
import { BottleneckDetailPage } from "./BottleneckDetailPage";
import { BottleneckListPage } from "./BottleneckListPage";
import { DiscoveryDetailPage } from "./DiscoveryDetailPage";
import { DiscoveryListPage } from "./DiscoveryListPage";
import { EditProcessModelPage } from "./EditProcessModelPage";
import { EventDetailPage } from "./EventDetailPage";
import { EventExplorerPage } from "./EventExplorerPage";
import { ExportListPage } from "./ExportListPage";
import { IngestEventsPage } from "./IngestEventsPage";
import { ProcessDetailPage } from "./ProcessDetailPage";
import { ProcessMapPage } from "./ProcessMapPage";
import { ProcessOverviewPage } from "./ProcessOverviewPage";

const documentValue: ProcessMiningConfigurationDocument = {
  environment: "development",
  max_batch_events: 1000,
  max_export_events: 1000,
  max_export_bytes: 100000,
  max_conformance_events: 1000,
  text_max_length: 255,
  attributes_max_bytes: 4096,
  forbidden_attribute_keys: ["password", "token"],
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
  inductive_default_threshold: 0.2,
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
  visual_zoom_step: 0.25,
  visual_edge_width_min: 1,
  visual_edge_width_max: 8,
  visual_frequency_divisor: 10,
  visual_duration_divisor: 60,
  visual_canvas_width: 1200,
  visual_canvas_height: 800,
  visual_node_width: 160,
  visual_node_height: 80,
  visual_layout_columns: 2,
  visual_horizontal_gap: 220,
  visual_vertical_gap: 120,
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
  version: 7,
  document: documentValue,
  limits: {},
  updated_at: "2026-07-21T00:00:00Z",
};

const health: ModuleHealth = {
  status: "healthy",
  live: true,
  ready: true,
  checked_at: "2026-07-21T00:00:00Z",
  dependencies: [],
};

const processOverview: ProcessOverview = {
  process_name: "Order to Cash",
  event_count: 42,
  case_count: 6,
  last_activity: "2026-07-21T10:00:00Z",
  has_reference: true,
  model_id: "model-1",
  last_discovery: "2026-07-21T11:00:00Z",
};

const eventOne: ProcessEvent = {
  id: "event-1",
  process_name: "Order to Cash",
  source_module: "sales",
  source_event_id: "SO-1",
  case_id: "case-1",
  activity: "Create order",
  occurred_at: "2026-07-21T10:00:00Z",
  resource: "Ava",
  attributes: { customer: "redacted", amount: 100 },
  ingested_at: "2026-07-21T10:01:00Z",
  created_at: "2026-07-21T10:01:00Z",
};

const eventTwo: ProcessEvent = {
  ...eventOne,
  id: "event-2",
  activity: "Approve order",
  occurred_at: "2026-07-21T10:05:00Z",
  resource: null,
};

const discovery: DiscoveryJob = {
  id: "discovery-1",
  process_name: "Order to Cash",
  algorithm: "heuristic_miner",
  parameters: { dependency_threshold: 0.8 },
  status: "completed",
  event_count: 42,
  case_count: 6,
  activity_count: 4,
  started_at: "2026-07-21T10:00:00Z",
  completed_at: "2026-07-21T10:02:00Z",
  error_code: "",
  transition_history: [
    {
      transition_key: "job-key",
      command: "complete",
      from_state: "running",
      to_state: "completed",
      occurred_at: "2026-07-21T10:02:00Z",
      metadata: { actor_id: "system", reason: "finished", correlation_id: "corr-transition" },
    },
  ],
  async_job_id: "async-1",
  created_at: "2026-07-21T09:59:00Z",
  updated_at: "2026-07-21T10:02:00Z",
};

const model: ProcessModel = {
  id: "model-1",
  name: "Order model",
  process_name: "Order to Cash",
  description: "Discovered model",
  source_kind: "discovered",
  current_version_number: 2,
  reference_version_number: 1,
  created_at: "2026-07-21T10:00:00Z",
  updated_at: "2026-07-21T11:00:00Z",
};

const modelVersion: ProcessModelVersion = {
  id: "version-1",
  process_model: "model-1",
  version: 2,
  algorithm: "heuristic_miner",
  parameters: {},
  model_data: {
    schema_version: "1.0",
    algorithm: "heuristic_miner",
    nodes: [
      { id: "start", label: "Start", type: "start", frequency: 42 },
      { id: "approve", label: "Approve", type: "activity", frequency: 39 },
      { id: "end", label: "End", type: "end", frequency: 38 },
    ],
    edges: [
      { id: "edge-1", source: "start", target: "approve", frequency: 30, duration_seconds: 45 },
      { id: "edge-2", source: "approve", target: "end", frequency: 12, duration_seconds: 7200 },
    ],
  },
  event_count: 42,
  case_count: 6,
  activity_count: 4,
  avg_case_duration_seconds: "3600",
  is_reference: false,
  published_at: "2026-07-21T11:00:00Z",
  created_at: "2026-07-21T11:00:00Z",
};

const exportItem: EventExport = {
  id: "export-1",
  process_name: "Order to Cash",
  format: "csv",
  status: "completed",
  event_filter: { process_name: "Order to Cash" },
  row_count: 42,
  byte_size: 4096,
  sha256: "abc123",
  expires_at: "2026-07-28T11:00:00Z",
  completed_at: "2026-07-21T11:00:00Z",
  error_code: "",
  transition_history: [],
  async_job_id: "async-export-1",
  created_at: "2026-07-21T10:55:00Z",
  updated_at: "2026-07-21T11:00:00Z",
};
const conformanceCheck: ConformanceCheck = {
  id: "conformance-1",
  process_model_version: "version-1",
  event_filter: { start: "2026-07-01T00:00:00.000Z", end: "2026-07-31T00:00:00.000Z" },
  status: "completed",
  fitness: "0.94",
  precision: "0.88",
  generalization: "0.91",
  total_cases: 6,
  conformant_cases: 5,
  deviating_cases: 1,
  started_at: "2026-07-21T10:00:00Z",
  completed_at: "2026-07-21T10:03:00Z",
  error_code: "",
  transition_history: [],
  created_at: "2026-07-21T09:59:00Z",
  updated_at: "2026-07-21T10:03:00Z",
};
const conformanceFitness: CaseFitness = {
  id: "fitness-1",
  conformance_check: "conformance-1",
  case_id: "case-1",
  fitness: "0.99",
  is_conformant: true,
  deviation_count: 0,
  trace_length: 3,
  created_at: "2026-07-21T10:04:00Z",
};
const conformanceDeviation: ConformanceDeviation = {
  id: "deviation-1",
  conformance_check: "conformance-1",
  case_id: "case-2",
  deviation_type: "unexpected_activity",
  expected: "Approve order",
  actual: "Skip approval",
  position: 2,
  description: "Case bypassed required approval.",
  created_at: "2026-07-21T10:04:00Z",
};
const bottleneck: BottleneckAnalysis = {
  id: "bottleneck-1",
  process_name: "Order to Cash",
  time_range_start: "2026-07-01T00:00:00Z",
  time_range_end: "2026-07-31T00:00:00Z",
  status: "completed",
  total_cases: 6,
  total_variants: 2,
  avg_case_duration_seconds: "7200",
  started_at: "2026-07-21T10:00:00Z",
  completed_at: "2026-07-21T10:05:00Z",
  error_code: "",
  transition_history: [],
  created_at: "2026-07-21T09:59:00Z",
  updated_at: "2026-07-21T10:05:00Z",
};
const bottleneckFinding: BottleneckFinding = {
  id: "finding-1",
  analysis: "bottleneck-1",
  from_activity: "Approve order",
  to_activity: "Ship order",
  avg_duration_seconds: "3600",
  median_duration_seconds: "1800",
  p95_duration_seconds: "7200",
  case_count: 4,
  severity: "critical",
  resource_bottleneck: "Ava",
  rank: 1,
  created_at: "2026-07-21T10:05:00Z",
};

function page<T>(
  items: readonly T[],
  pagination: Partial<PaginatedResult<T>["pagination"]> = {}
): PaginatedResult<T> {
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
      ...pagination,
    },
  };
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>;
}

function renderRoute(ui: ReactElement, path: string, route = path) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route
            path={path}
            element={
              <>
                <LocationProbe />
                {ui}
              </>
            }
          />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderNode(ui: ReactElement) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
        })
      }
    >
      {ui}
    </QueryClientProvider>
  );
}

function setUser(role: string | null, isSuperuser = false) {
  act(() => {
    useAuthStore.setState({
      isAuthenticated: true,
      isLoading: false,
      user: {
        id: "user-1",
        email: "user@example.com",
        username: "user",
        is_staff: false,
        is_superuser: isSuperuser,
        tenant_id: "tenant-1",
        platform_role: null,
        tenant_role: role,
      },
    });
  });
}

function installDefaultServiceSpies() {
  vi.spyOn(processMiningService, "getConfiguration").mockResolvedValue(configuration);
  vi.spyOn(processMiningService, "health").mockResolvedValue(health);
  vi.spyOn(processMiningService, "listProcesses").mockResolvedValue(page([processOverview]));
  vi.spyOn(processMiningService, "getProcess").mockResolvedValue(processOverview);
  vi.spyOn(processMiningService, "listEvents").mockResolvedValue(page([eventOne, eventTwo]));
  vi.spyOn(processMiningService, "getEvent").mockResolvedValue(eventOne);
  vi.spyOn(processMiningService, "listDiscoveries").mockResolvedValue(
    page([
      discovery,
      { ...discovery, id: "discovery-running", status: "running", process_name: "Invoice" },
    ])
  );
  vi.spyOn(processMiningService, "getDiscovery").mockResolvedValue(discovery);
  vi.spyOn(processMiningService, "getDiscoveredModel").mockResolvedValue(modelVersion);
  vi.spyOn(processMiningService, "createDiscovery").mockResolvedValue(discovery);
  vi.spyOn(processMiningService, "deleteDiscovery").mockResolvedValue(undefined);
  vi.spyOn(processMiningService, "cancelDiscovery").mockResolvedValue({
    ...discovery,
    status: "cancelled",
  });
  vi.spyOn(processMiningService, "retryDiscovery").mockResolvedValue({
    ...discovery,
    status: "queued",
  });
  vi.spyOn(processMiningService, "getModel").mockResolvedValue(model);
  vi.spyOn(processMiningService, "createModel").mockResolvedValue(model);
  vi.spyOn(processMiningService, "listModels").mockResolvedValue(page([model]));
  vi.spyOn(processMiningService, "updateModel").mockResolvedValue({
    ...model,
    name: "Updated order model",
  });
  vi.spyOn(processMiningService, "listModelVersions").mockResolvedValue(page([modelVersion]));
  vi.spyOn(processMiningService, "getModelVersion").mockResolvedValue(modelVersion);
  vi.spyOn(processMiningService, "setReference").mockResolvedValue({
    ...modelVersion,
    is_reference: true,
  });
  vi.spyOn(processMiningService, "listExports").mockResolvedValue(page([exportItem]));
  vi.spyOn(processMiningService, "createExport").mockResolvedValue({
    ...exportItem,
    id: "export-2",
    status: "queued",
  });
  vi.spyOn(processMiningService, "deleteExport").mockResolvedValue(undefined);
  vi.spyOn(processMiningService, "downloadExport").mockResolvedValue(new Blob(["csv-body"]));
  vi.spyOn(processMiningService, "ingestEvents").mockResolvedValue({
    accepted: 1,
    duplicates: 1,
    rejected: 1,
    rows: [
      { index: 0, status: "accepted", event_id: "event-1", code: "", message: "accepted" },
      { index: 1, status: "duplicate", event_id: "event-1", code: "DUPLICATE", message: "seen" },
      { index: 2, status: "rejected", event_id: null, code: "FORBIDDEN_KEY", message: "token" },
    ],
  });
  vi.spyOn(processMiningService, "listConformance").mockResolvedValue(
    page([conformanceCheck, { ...conformanceCheck, id: "conformance-running", status: "running" }])
  );
  vi.spyOn(processMiningService, "getConformance").mockResolvedValue(conformanceCheck);
  vi.spyOn(processMiningService, "createConformance").mockResolvedValue(conformanceCheck);
  vi.spyOn(processMiningService, "deleteConformance").mockResolvedValue(undefined);
  vi.spyOn(processMiningService, "getFitness").mockResolvedValue(page([conformanceFitness]));
  vi.spyOn(processMiningService, "listDeviations").mockResolvedValue(page([conformanceDeviation]));
  vi.spyOn(processMiningService, "listBottlenecks").mockResolvedValue(
    page([bottleneck, { ...bottleneck, id: "bottleneck-running", status: "running" }])
  );
  vi.spyOn(processMiningService, "getBottleneck").mockResolvedValue(bottleneck);
  vi.spyOn(processMiningService, "createBottleneck").mockResolvedValue(bottleneck);
  vi.spyOn(processMiningService, "deleteBottleneck").mockResolvedValue(undefined);
  vi.spyOn(processMiningService, "listFindings").mockResolvedValue(page([bottleneckFinding]));
  vi.spyOn(processMiningService, "listVariants").mockResolvedValue(
    page([
      {
        id: "variant-1",
        analysis: "bottleneck-1",
        variant_key: "happy",
        activities: ["Create order", "Approve order", "Ship order"],
        case_count: 5,
        percentage: "83.3",
        avg_duration_seconds: "5400",
        is_happy_path: true,
        is_grouped_other: false,
        created_at: "2026-07-21T10:05:00Z",
      },
    ])
  );
}

describe("process mining shared components and utilities", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    act(() => {
      useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
    });
    localStorage.clear();
  });

  it("formats deterministic evidence values and evaluates management access", () => {
    function AccessProbe() {
      return <span>{useCanManageProcessMining() ? "can-manage" : "read-only"}</span>;
    }

    expect(deterministicKey(" Retry ", "Order to Cash", "V2")).toBe(
      "process-mining:retry:order%20to%20cash:v2"
    );
    expect(formatDate(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
    expect(formatDuration(30)).toBe("30.0 s");
    expect(formatDuration(180)).toBe("3.0 min");
    expect(formatDuration(7200)).toBe("2.0 h");

    act(() => {
      useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
    });
    const { rerender } = renderNode(<AccessProbe />);
    expect(screen.getByText("read-only")).toBeInTheDocument();
    setUser("tenant_admin");
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <AccessProbe />
      </QueryClientProvider>
    );
    expect(screen.getByText("can-manage")).toBeInTheDocument();
  });

  it("renders fail-closed API problem variants, status pills, and guarded pagination", async () => {
    const retry = vi.fn();
    const onPage = vi.fn();
    renderNode(
      <>
        <ApiProblem
          error={new ProcessMiningApiError("Denied by policy", 403, "DENIED", "corr-denied", {})}
          onRetry={retry}
        />
        <StatusPill status="running" />
        <StatusPill status="failed" />
        <Pagination
          value={{
            count: 75,
            page: 2,
            page_size: 25,
            total_pages: 3,
            has_next: true,
            has_previous: true,
          }}
          onPage={onPage}
        />
      </>
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Access unavailable");
    expect(screen.getByText("Correlation ID: corr-denied")).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onPage).toHaveBeenNthCalledWith(1, 1);
    expect(onPage).toHaveBeenNthCalledWith(2, 3);
    expect(retry).toHaveBeenCalledOnce();
  });
});

describe("process mining pages", () => {
  beforeEach(() => {
    installDefaultServiceSpies();
    setUser("tenant_admin");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    act(() => {
      useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
    });
    localStorage.clear();
  });

  it("filters the process landscape and navigates to process, evidence, and export routes", async () => {
    renderRoute(<ProcessOverviewPage />, "/process-mining/processes");

    expect(await screen.findByRole("heading", { name: "Process landscape" })).toBeInTheDocument();
    expect(screen.getAllByText("42")).toHaveLength(2);
    await userEvent.clear(screen.getByLabelText("Search processes"));
    await userEvent.type(screen.getByLabelText("Search processes"), "cash");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(processMiningService.listProcesses).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "cash", page_size: 25 })
      )
    );

    await userEvent.click(screen.getByRole("button", { name: "Order to Cash" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/processes/Order%20to%20Cash"
    );
  });

  it("keeps process landscape write actions hidden from read-only users", async () => {
    setUser("viewer");
    renderRoute(<ProcessOverviewPage />, "/process-mining/processes");

    expect(await screen.findByRole("heading", { name: "Process landscape" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ingest events" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Discover process" })).not.toBeInTheDocument();
  });

  it("renders process landscape API errors with correlation evidence and retry", async () => {
    const getConfiguration = vi
      .spyOn(processMiningService, "getConfiguration")
      .mockRejectedValueOnce(
        new ProcessMiningApiError("Storage unavailable", 503, "STORE_DOWN", "corr-store", {})
      )
      .mockResolvedValue(configuration);

    renderRoute(<ProcessOverviewPage />, "/process-mining/processes");

    expect(await screen.findByRole("alert")).toHaveTextContent("Capability unavailable");
    expect(screen.getByText("Correlation ID: corr-store")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(getConfiguration).toHaveBeenCalledTimes(2));
  });

  it("filters events, opens the trace drawer, closes it, and follows event navigation", async () => {
    renderRoute(
      <EventExplorerPage />,
      "/process-mining/events",
      "/process-mining/events?process_name=Order%20to%20Cash"
    );

    expect(await screen.findByRole("heading", { name: "Event explorer" })).toBeInTheDocument();
    await waitFor(() =>
      expect(processMiningService.listEvents).toHaveBeenCalledWith(
        expect.objectContaining({
          process_name: "Order to Cash",
          page_size: 25,
          ordering: "occurred_at",
        })
      )
    );
    fireEvent.change(screen.getByLabelText("Activity facet"), { target: { value: "Approve" } });
    await waitFor(() =>
      expect(processMiningService.listEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ activity: "Approve", page: 1 })
      )
    );

    await userEvent.click(screen.getAllByRole("button", { name: "case-1" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Case trace case-1" });
    expect(within(dialog).getByText(/1. Create order/u)).toBeInTheDocument();
    expect(within(dialog).getByText(/2. Approve order/u)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Close trace" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Approve order" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/events/event-2"
    );
  });

  it("shows the event explorer empty prompt before a process is selected", async () => {
    renderRoute(<EventExplorerPage />, "/process-mining/events");

    expect(await screen.findByText("Choose a process")).toBeInTheDocument();
    expect(processMiningService.listEvents).not.toHaveBeenCalled();
  });

  it("renders immutable event detail attributes and fail-closed not-found retry", async () => {
    renderRoute(
      <EventDetailPage />,
      "/process-mining/events/:id",
      "/process-mining/events/event-1"
    );

    expect(await screen.findByRole("heading", { name: "Create order" })).toBeInTheDocument();
    expect(screen.getByText("Append-only")).toBeInTheDocument();
    expect(screen.getByText(/"amount": 100/u)).toBeInTheDocument();

    vi.restoreAllMocks();
    const getEvent = vi
      .spyOn(processMiningService, "getEvent")
      .mockRejectedValueOnce(
        new ProcessMiningApiError("Event missing", 404, "NOT_FOUND", "corr-missing", {})
      )
      .mockResolvedValue(eventOne);
    renderRoute(
      <EventDetailPage />,
      "/process-mining/events/:id",
      "/process-mining/events/missing"
    );
    expect(await screen.findByText("Evidence not found")).toBeInTheDocument();
    expect(screen.getByText("Correlation ID: corr-missing")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(getEvent).toHaveBeenCalledTimes(2));
  });

  it("queues discovery only after configured evidence and threshold validation pass", async () => {
    renderRoute(
      <CreateDiscoveryPage />,
      "/process-mining/discoveries/new",
      "/process-mining/discoveries/new?process_name=Order%20to%20Cash"
    );

    expect(await screen.findByText(/configured minimum met/u)).toBeInTheDocument();
    const threshold = screen.getByLabelText("Configured algorithm threshold");
    await userEvent.clear(threshold);
    await userEvent.type(threshold, "1.5");
    expect(screen.getByRole("button", { name: "Queue discovery" })).toBeDisabled();
    await userEvent.clear(threshold);
    await userEvent.type(threshold, "0.9");
    await userEvent.click(screen.getByRole("button", { name: "Queue discovery" }));

    await waitFor(() => expect(processMiningService.createDiscovery).toHaveBeenCalled());
    const createDiscoveryCalls = vi.mocked(processMiningService.createDiscovery).mock
      .calls as readonly [DiscoveryCreateRequest][];
    const createDiscoveryRequest = createDiscoveryCalls.at(-1)?.[0];
    if (!createDiscoveryRequest) throw new Error("Expected discovery creation request");
    expect(createDiscoveryRequest.process_name).toBe("Order to Cash");
    expect(createDiscoveryRequest.algorithm).toBe("heuristic_miner");
    expect(createDiscoveryRequest.parameters).toEqual({ dependency_threshold: 0.9 });
    expect(createDiscoveryRequest.idempotency_key).toContain(
      "process-mining:discovery:order%20to%20cash"
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/discoveries/discovery-1"
    );
  });

  it("deletes only terminal discovery jobs and uses configured pagination", async () => {
    renderRoute(<DiscoveryListPage />, "/process-mining/discoveries");

    expect(await screen.findByRole("heading", { name: "Process discovery" })).toBeInTheDocument();
    await waitFor(() =>
      expect(processMiningService.listDiscoveries).toHaveBeenCalledWith(
        expect.objectContaining({ page_size: 25, ordering: "-created_at" })
      )
    );
    const deleteButtons = screen.getAllByRole("button", { name: /Delete/u });
    const terminalDeleteButton = deleteButtons[0];
    if (!terminalDeleteButton) throw new Error("Expected terminal discovery delete button");
    expect(terminalDeleteButton).toBeEnabled();
    expect(deleteButtons[1]).toBeDisabled();
    await userEvent.click(terminalDeleteButton);
    await waitFor(() =>
      expect(processMiningService.deleteDiscovery).toHaveBeenCalledWith("discovery-1")
    );
  });

  it("cancels, retries, and opens discovered maps from discovery details", async () => {
    const getDiscovery = vi
      .spyOn(processMiningService, "getDiscovery")
      .mockResolvedValueOnce({ ...discovery, status: "running" })
      .mockResolvedValueOnce({ ...discovery, status: "failed", error_code: "ADAPTER_TIMEOUT" })
      .mockResolvedValue(discovery);

    renderRoute(
      <DiscoveryDetailPage />,
      "/process-mining/discoveries/:id",
      "/process-mining/discoveries/discovery-1"
    );

    expect(await screen.findByRole("heading", { name: "Order to Cash" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(processMiningService.cancelDiscovery).toHaveBeenCalledWith(
        "discovery-1",
        expect.objectContaining({
          transition_key: "process-mining:cancel:discovery-1:2026-07-21t10%3A02%3A00z",
        })
      )
    );
    await waitFor(() => expect(getDiscovery).toHaveBeenCalledTimes(2));
    expect(await screen.findAllByText("ADAPTER_TIMEOUT")).toHaveLength(2);
    expect(
      screen.getByText("No model version was fabricated.", { exact: false })
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(processMiningService.retryDiscovery).toHaveBeenCalled());
    const retryDiscoveryCalls = vi.mocked(processMiningService.retryDiscovery).mock
      .calls as readonly [string, TransitionActionRequest][];
    const retryCall = retryDiscoveryCalls.at(-1);
    if (!retryCall) throw new Error("Expected discovery retry request");
    expect(retryCall[0]).toBe("discovery-1");
    expect(retryCall[1].transition_key).toBe(
      "process-mining:retry:discovery-1:2026-07-21t10%3A02%3A00z"
    );
    expect(retryCall[1].idempotency_key).toContain("process-mining:retry-job:discovery-1");

    await waitFor(() => expect(getDiscovery).toHaveBeenCalledTimes(3));
    expect(await screen.findByText("corr-transition")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open process map" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/models/model-1/map"
    );
  });

  it("navigates from process detail through evidence, discovery, bottleneck, export, and map actions", async () => {
    const firstRender = renderRoute(
      <ProcessDetailPage />,
      "/process-mining/processes/:processName",
      "/process-mining/processes/Order%20to%20Cash"
    );

    expect(await screen.findByRole("heading", { name: "Order to Cash" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Explore events" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/events?process_name=Order%20to%20Cash"
    );
    firstRender.unmount();

    renderRoute(
      <ProcessDetailPage />,
      "/process-mining/processes/:processName",
      "/process-mining/processes/Order%20to%20Cash"
    );
    await screen.findByRole("heading", { name: "Order to Cash" });
    await userEvent.click(screen.getByRole("button", { name: "Open map" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/models/model-1/map"
    );
  });

  it("creates bounded exports only after process sizing is eligible", async () => {
    renderRoute(
      <CreateExportPage />,
      "/process-mining/exports/new",
      "/process-mining/exports/new?process_name=Order%20to%20Cash"
    );

    expect(
      await screen.findByRole("heading", { name: "Create evidence export" })
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(processMiningService.listProcesses).toHaveBeenCalledWith({
        process_name: "Order to Cash",
        page_size: 1,
      })
    );
    fireEvent.change(screen.getByLabelText("Format"), { target: { value: "json" } });
    await userEvent.click(screen.getByRole("button", { name: "Queue verified export" }));

    await waitFor(() => expect(processMiningService.createExport).toHaveBeenCalled());
    const createExportCalls = vi.mocked(processMiningService.createExport).mock.calls as readonly [
      EventExportCreateRequest,
    ][];
    const createExportRequest = createExportCalls.at(-1)?.[0];
    if (!createExportRequest) throw new Error("Expected export creation request");
    expect(createExportRequest.format).toBe("json");
    expect(createExportRequest.process_name).toBe("Order to Cash");
    expect(createExportRequest.idempotency_key).toContain(
      "process-mining:export:order%20to%20cash:json"
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/process-mining/exports");

    vi.mocked(processMiningService.listProcesses).mockResolvedValueOnce(
      page([{ ...processOverview, event_count: documentValue.max_export_events + 1 }])
    );
    renderRoute(
      <CreateExportPage />,
      "/process-mining/exports/new",
      "/process-mining/exports/new?process_name=Order%20to%20Cash"
    );
    expect(await screen.findByRole("button", { name: "Queue verified export" })).toBeDisabled();
  });

  it("downloads completed exports and deletes only terminal export artifacts", async () => {
    const createObjectURL = vi.fn().mockReturnValue("blob:export");
    const revokeObjectURL = vi.fn();
    const linkClick = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });

    const completedExports = renderRoute(<ExportListPage />, "/process-mining/exports");

    expect(await screen.findByRole("heading", { name: "Evidence exports" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Download/u }));
    await waitFor(() =>
      expect(processMiningService.downloadExport).toHaveBeenCalledWith("export-1")
    );
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:export");
    await userEvent.click(screen.getByRole("button", { name: /Delete/u }));
    await waitFor(() => expect(processMiningService.deleteExport).toHaveBeenCalledWith("export-1"));
    completedExports.unmount();

    vi.mocked(processMiningService.listExports).mockResolvedValueOnce(
      page([{ ...exportItem, id: "export-running", status: "running" }])
    );
    renderRoute(<ExportListPage />, "/process-mining/exports");
    expect(await screen.findByRole("button", { name: /Delete/u })).toBeDisabled();
    linkClick.mockRestore();
  });

  it("previews event ingestion quality and submits only structurally valid rows", async () => {
    renderRoute(<IngestEventsPage />, "/process-mining/events/ingest");

    expect(
      await screen.findByRole("heading", { name: "Ingest canonical events" })
    ).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Process name"));
    await userEvent.type(screen.getByLabelText("Process name"), "Order to Cash");
    fireEvent.change(screen.getByLabelText("Event batch JSON"), {
      target: {
        value:
          '[{"case_id":"case-1","activity":"Create order","occurred_at":"2026-07-21T10:00:00Z"},{"case_id":"case-2"}]',
      },
    });
    expect(screen.getByText(/1 row\(s\) are missing/u)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Submit/u })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Event batch JSON"), {
      target: {
        value:
          '[{"case_id":"case-1","activity":"Create order","occurred_at":"2026-07-21T10:00:00Z","attributes":{"amount":100}}]',
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Submit 1 events" }));

    await waitFor(() => expect(processMiningService.ingestEvents).toHaveBeenCalledTimes(1));
    expect(processMiningService.ingestEvents).toHaveBeenCalledWith({
      process_name: "Order to Cash",
      source_module: "canonical",
      events: [
        {
          case_id: "case-1",
          activity: "Create order",
          occurred_at: "2026-07-21T10:00:00Z",
          attributes: { amount: 100 },
        },
      ],
    });
    expect(screen.getByText("1 accepted · 1 duplicates · 1 rejected")).toBeInTheDocument();
    expect(screen.getByText("FORBIDDEN_KEY")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Explore evidence" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/events?process_name=Order%20to%20Cash"
    );
  });

  it("validates imported model graphs and edits mutable model metadata only", async () => {
    const graph = {
      schema_version: "1.0",
      nodes: [{ id: "start", label: "Start", type: "start", frequency: 1 }],
      edges: [],
    };
    renderRoute(
      <CreateProcessModelPage />,
      "/process-mining/models/new",
      "/process-mining/models/new?process_name=Order%20to%20Cash"
    );

    expect(
      await screen.findByRole("heading", { name: "Create process model" })
    ).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Model name"), "Imported order model");
    const createModelCallsBeforeInvalid = vi.mocked(processMiningService.createModel).mock.calls
      .length;
    fireEvent.change(screen.getByLabelText("Canonical graph JSON"), { target: { value: "[]" } });
    await userEvent.click(screen.getByRole("button", { name: "Publish immutable version" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Process mining unavailable");
    expect(processMiningService.createModel).toHaveBeenCalledTimes(createModelCallsBeforeInvalid);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    fireEvent.change(screen.getByLabelText("Canonical graph JSON"), {
      target: { value: JSON.stringify(graph) },
    });
    await userEvent.click(screen.getByRole("button", { name: "Publish immutable version" }));
    await waitFor(() => expect(processMiningService.createModel).toHaveBeenCalledTimes(1));
    expect(processMiningService.createModel).toHaveBeenCalledWith({
      name: "Imported order model",
      process_name: "Order to Cash",
      description: "",
      model_data: graph,
    });
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/models/model-1/map"
    );

    renderRoute(
      <EditProcessModelPage />,
      "/process-mining/models/:id/edit",
      "/process-mining/models/model-1/edit"
    );
    expect(await screen.findByRole("heading", { name: "Edit model metadata" })).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Model name"));
    await userEvent.type(screen.getByLabelText("Model name"), "Updated order model");
    await userEvent.clear(screen.getByLabelText("Description"));
    await userEvent.type(screen.getByLabelText("Description"), "Curated model");
    await userEvent.click(screen.getByRole("button", { name: "Save metadata" }));
    await waitFor(() =>
      expect(processMiningService.updateModel).toHaveBeenCalledWith("model-1", {
        name: "Updated order model",
        description: "Curated model",
      })
    );
  });

  it("renders a configuration-driven process map and sets the reference version idempotently", async () => {
    renderRoute(
      <ProcessMapPage />,
      "/process-mining/models/:id/map",
      "/process-mining/models/model-1/map"
    );

    expect(await screen.findByRole("heading", { name: "Order model" })).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("viewBox", "0 0 1200 800");
    expect(screen.getByText("45.0 s")).toBeInTheDocument();
    expect(screen.getByText("2.0 h")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "frequency" }));
    expect(screen.getByRole("button", { name: "duration" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "+" }));
    expect(screen.getByText("125%")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Set reference" }));
    await waitFor(() =>
      expect(processMiningService.setReference).toHaveBeenCalledWith("model-1", {
        version_id: "version-1",
        transition_key: "process-mining:reference:model-1:version-1",
      })
    );
    await userEvent.click(screen.getByRole("button", { name: "Edit metadata" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/models/model-1/edit"
    );
  });

  it("creates conformance checks from reference-ready model versions and renders completed evidence", async () => {
    renderRoute(
      <CreateConformancePage />,
      "/process-mining/conformance/new",
      "/process-mining/conformance/new"
    );

    expect(
      await screen.findByRole("heading", { name: "Create conformance check" })
    ).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Reference-ready model"), "model-1");
    await waitFor(() =>
      expect(processMiningService.listModelVersions).toHaveBeenCalledWith("model-1")
    );
    await userEvent.selectOptions(await screen.findByLabelText("Immutable version"), "version-1");
    fireEvent.change(screen.getByLabelText("Event window start"), {
      target: { value: "2026-07-01T00:00" },
    });
    fireEvent.change(screen.getByLabelText("Event window end"), {
      target: { value: "2026-07-31T00:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Queue conformance check" }));

    await waitFor(() => expect(processMiningService.createConformance).toHaveBeenCalled());
    const calls = vi.mocked(processMiningService.createConformance).mock.calls as readonly [
      ConformanceCreateRequest,
    ][];
    const payload = calls.at(-1)?.[0];
    if (!payload) throw new Error("Expected conformance payload");
    expect(payload.process_model_version_id).toBe("version-1");
    expect(payload.event_filter).toEqual({
      start: "2026-06-30T18:30:00.000Z",
      end: "2026-07-30T18:30:00.000Z",
    });
    expect(payload.idempotency_key).toContain("process-mining:conformance:version-1");
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/conformance/conformance-1"
    );

    renderRoute(
      <ConformanceDetailPage />,
      "/process-mining/conformance/:id",
      "/process-mining/conformance/conformance-1"
    );
    expect(
      await screen.findByRole("heading", { name: "Conformance evidence" })
    ).toBeInTheDocument();
    expect(screen.getByText("0.94")).toBeInTheDocument();
    expect(screen.getByText("Case fitness distribution")).toBeInTheDocument();
    expect(screen.getByText("case-1")).toBeInTheDocument();
    expect(screen.getByText("Skip approval")).toBeInTheDocument();
    expect(processMiningService.listDeviations).toHaveBeenCalledWith("conformance-1", {
      page_size: 50,
    });
  });

  it("lists conformance and bottleneck artifacts with terminal-only deletes", async () => {
    const conformanceList = renderRoute(
      <ConformanceListPage />,
      "/process-mining/conformance",
      "/process-mining/conformance?page=2"
    );

    expect(await screen.findByRole("heading", { name: "Conformance checks" })).toBeInTheDocument();
    await waitFor(() =>
      expect(processMiningService.listConformance).toHaveBeenCalledWith({
        page: 2,
        page_size: 25,
        ordering: "-created_at",
      })
    );
    const conformanceDeletes = screen.getAllByRole("button", { name: /Delete/u });
    expect(conformanceDeletes[0]).toBeEnabled();
    expect(conformanceDeletes[1]).toBeDisabled();
    await userEvent.click(conformanceDeletes[0]!);
    await waitFor(() =>
      expect(processMiningService.deleteConformance).toHaveBeenCalledWith("conformance-1")
    );
    conformanceList.unmount();

    renderRoute(
      <BottleneckListPage />,
      "/process-mining/bottlenecks",
      "/process-mining/bottlenecks"
    );
    expect(await screen.findByRole("heading", { name: "Bottleneck analyses" })).toBeInTheDocument();
    await waitFor(() =>
      expect(processMiningService.listBottlenecks).toHaveBeenCalledWith({
        page: 1,
        page_size: 25,
        ordering: "-created_at",
      })
    );
    const bottleneckDeletes = screen.getAllByRole("button", { name: /Delete/u });
    expect(bottleneckDeletes[0]).toBeEnabled();
    expect(bottleneckDeletes[1]).toBeDisabled();
    await userEvent.click(bottleneckDeletes[0]!);
    await waitFor(() =>
      expect(processMiningService.deleteBottleneck).toHaveBeenCalledWith("bottleneck-1")
    );
  });

  it("creates bottleneck analyses from eligible process windows and renders findings", async () => {
    renderRoute(
      <CreateBottleneckAnalysisPage />,
      "/process-mining/bottlenecks/new",
      "/process-mining/bottlenecks/new?process_name=Order%20to%20Cash"
    );

    expect(
      await screen.findByRole("heading", { name: "Create bottleneck analysis" })
    ).toBeInTheDocument();
    expect(await screen.findByText("6 cases · configured minimum 5")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Window start"), {
      target: { value: "2026-07-01T00:00" },
    });
    fireEvent.change(screen.getByLabelText("Window end"), {
      target: { value: "2026-07-31T00:00" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Queue analysis" }));

    await waitFor(() => expect(processMiningService.createBottleneck).toHaveBeenCalled());
    const calls = vi.mocked(processMiningService.createBottleneck).mock.calls as readonly [
      BottleneckCreateRequest,
    ][];
    const payload = calls.at(-1)?.[0];
    if (!payload) throw new Error("Expected bottleneck payload");
    expect(payload).toMatchObject({
      process_name: "Order to Cash",
      time_range_start: "2026-06-30T18:30:00.000Z",
      time_range_end: "2026-07-30T18:30:00.000Z",
    });
    expect(payload.idempotency_key).toContain("process-mining:bottleneck:order%20to%20cash");
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/process-mining/bottlenecks/bottleneck-1"
    );

    renderRoute(
      <BottleneckDetailPage />,
      "/process-mining/bottlenecks/:id",
      "/process-mining/bottlenecks/bottleneck-1"
    );
    expect(
      await screen.findByRole("heading", { name: "Order to Cash bottlenecks" })
    ).toBeInTheDocument();
    expect(screen.getByText("Approve order → Ship order")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("Create order → Approve order → Ship order")).toBeInTheDocument();
    expect(processMiningService.listFindings).toHaveBeenCalledWith("bottleneck-1", {
      page_size: 50,
    });
    expect(processMiningService.listVariants).toHaveBeenCalledWith("bottleneck-1", {
      page_size: 50,
      ordering: "-case_count",
    });
  });
});
