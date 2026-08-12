/* eslint-disable max-lines-per-function, @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-return, @typescript-eslint/unbound-method -- focused RTL tests assert mutation payloads and mocked service methods. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type {
  DashboardDetail,
  DatasetDescriptor,
  DatasetSummary,
  ExecutionDetail,
  ExecutionResult,
  ReportCreate,
  QueryCreate,
  QueryDetail,
  QueryListItem,
  ReportDetail,
} from "../contracts";
import type * as BiServiceModule from "../services/bi-service";
import { DatasetCatalogPage } from "./DatasetCatalogPage";
import { CreateDashboardPage } from "./CreateDashboardPage";
import { CreateQueryPage } from "./CreateQueryPage";
import { DashboardDetailPage } from "./DashboardDetailPage";
import { DashboardListPage } from "./DashboardListPage";
import { EditDashboardPage } from "./EditDashboardPage";
import { EditQueryPage } from "./EditQueryPage";
import { ExecutionDetailPage } from "./ExecutionDetailPage";
import { ExecutionListPage } from "./ExecutionListPage";
import { QueryForm } from "./QueryForm";
import { QueryDetailPage } from "./QueryDetailPage";
import { QueryListPage } from "./QueryListPage";
import { ReportDetailPage } from "./ReportDetailPage";
import { ReportForm } from "./ReportForm";
import { ReportListPage } from "./ReportListPage";
import { biService } from "../services/bi-service";

vi.mock("../services/bi-service", async (importOriginal) => {
  const actual = await importOriginal<typeof BiServiceModule>();
  return {
    ...actual,
    createIdempotencyKey: vi.fn(() => "idem-bi-test"),
    biService: {
      getDashboard: vi.fn(),
      listDashboards: vi.fn(),
      listQueries: vi.fn(),
      listReports: vi.fn(),
      listExecutions: vi.fn(),
      listDatasets: vi.fn(),
      getDataset: vi.fn(),
      getQuery: vi.fn(),
      getReport: vi.fn(),
      getExecution: vi.fn(),
      getExecutionResult: vi.fn(),
      createDashboard: vi.fn(),
      createQuery: vi.fn(),
      updateQuery: vi.fn(),
      addWidget: vi.fn(),
      removeWidget: vi.fn(),
      reorderWidgets: vi.fn(),
      createShare: vi.fn(),
      executeDashboard: vi.fn(),
      executeQuery: vi.fn(),
      executeReport: vi.fn(),
      transitionQuery: vi.fn(),
      transitionReport: vi.fn(),
      cancelExecution: vi.fn(),
    },
  };
});

const stamp = "2026-01-01T00:00:00Z";
const query: QueryListItem = {
  id: "query-1",
  query_code: "SALES_SUMMARY",
  name: "Sales summary",
  description: "Published governed query",
  dataset_key: "sales",
  state: "published",
  version: 3,
  updated_at: stamp,
  created_by_id: "user-1",
};
const queryDetail: QueryDetail = {
  ...query,
  dataset_version: "2026.8",
  dataset_schema_fingerprint: "schema-bi",
  dimensions: ["region"],
  measures: [{ key: "amount", alias: "pipeline_amount" }],
  filters: [],
  grouping: [{ dimension: "region" }],
  ordering: [{ field: "amount", direction: "desc" }],
  parameters_schema: {},
  row_limit: 1000,
  cache_ttl_seconds: 120,
  transition_history: [
    {
      command: "publish",
      from_state: "draft",
      to_state: "published",
      actor_id: "user-1",
      correlation_id: "corr-transition",
      timestamp: stamp,
    },
  ],
  created_at: stamp,
  updated_by_id: "user-2",
};
const reportDetail: ReportDetail = {
  id: "report-1",
  report_code: "PIPELINE",
  report_name: "Pipeline report",
  description: "Pipeline details",
  report_type: "table",
  state: "published",
  version: 4,
  updated_at: stamp,
  query_definition: {
    id: "query-1",
    query_code: "SALES_SUMMARY",
    name: "Sales summary",
    dataset_key: "sales",
    state: "published",
    version: 3,
  },
  last_execution: {
    id: "execution-latest",
    status: "succeeded",
    dataset_key: "sales",
    dataset_version: "2026.8",
    dataset_schema_fingerprint: "schema-bi",
    definition_version: 4,
    row_count: 3,
    truncated: false,
    cache_hit: false,
    duration_ms: 80,
    created_at: stamp,
    started_at: stamp,
    completed_at: stamp,
  },
  visualization: { type: "table" },
  default_parameters: {},
  transition_history: [
    {
      command: "publish",
      from_state: "draft",
      to_state: "published",
      timestamp: stamp,
    },
  ],
  created_at: stamp,
  created_by_id: "user-1",
  updated_by_id: "user-2",
};
const runningExecution: ExecutionDetail = {
  id: "execution-1",
  job_id: "job-1",
  status: "running",
  query_definition_id: "query-1",
  report_id: null,
  dashboard_id: null,
  dataset_key: "sales",
  dataset_version: "2026.8",
  dataset_schema_fingerprint: "schema-bi",
  definition_version: 3,
  actor_id: "user-1",
  row_count: null,
  truncated: false,
  cache_hit: false,
  duration_ms: null,
  created_at: stamp,
  started_at: stamp,
  completed_at: null,
  parameters: {},
  transition_history: [
    { command: "enqueue", to_state: "queued", timestamp: stamp },
    { command: "start", to_state: "running", timestamp: stamp },
  ],
  result_columns: [],
  error_code: "",
  error_message: "",
  effective_query_fingerprint: "fingerprint-bi",
  freshness_token: "fresh-bi",
  data_as_of: null,
  result_purged_at: null,
};
const succeededExecution: ExecutionDetail = {
  ...runningExecution,
  status: "succeeded",
  row_count: 2,
  cache_hit: true,
  duration_ms: 52,
  completed_at: stamp,
  transition_history: [
    ...runningExecution.transition_history,
    { command: "succeed", to_state: "succeeded", timestamp: stamp },
  ],
};
const failedExecution: ExecutionDetail = {
  ...runningExecution,
  id: "execution-failed",
  status: "failed",
  error_code: "SOURCE_TIMEOUT",
  error_message: "Warehouse request timed out after the configured limit.",
};
const executionResult: ExecutionResult = {
  execution_id: "execution-1",
  columns: [
    { key: "region", label: "Region", type: "string" },
    { key: "amount", label: "Amount", type: "number" },
    { key: "active", label: "Active", type: "boolean" },
  ],
  rows: [
    { region: "East", amount: 125000, active: true },
    { region: "West", amount: 85000, active: false },
  ],
  row_count: 2,
  truncated: true,
  cache_hit: true,
  definition_version: 3,
  dataset_key: "sales",
  dataset_version: "2026.8",
  dataset_schema_fingerprint: "schema-bi",
  effective_query_fingerprint: "fingerprint-bi",
  freshness_token: "fresh-bi",
  data_as_of: stamp,
};
const dashboard: DashboardDetail = {
  id: "dashboard-1",
  dashboard_code: "EXEC",
  dashboard_name: "Executive dashboard",
  description: "Executive metrics",
  state: "draft",
  version: 7,
  effective_access: "edit",
  widget_count: 2,
  last_refresh: null,
  updated_at: stamp,
  created_at: stamp,
  created_by_id: "user-1",
  updated_by_id: "user-2",
  global_filters: [],
  refresh_interval_seconds: null,
  shares: [],
  transition_history: [],
  widgets: [
    {
      id: "widget-1",
      title: "Pipeline value",
      description: "Pipeline",
      widget_type: "table",
      x: 0,
      y: 0,
      width: 6,
      height: 3,
      visualization: {},
      filters: [],
      refresh_interval_seconds: null,
      display_order: 0,
      version: 2,
      updated_at: stamp,
    },
    {
      id: "widget-2",
      title: "Win rate",
      description: "Win",
      widget_type: "kpi",
      x: 0,
      y: 3,
      width: 4,
      height: 2,
      visualization: {},
      filters: [],
      refresh_interval_seconds: null,
      display_order: 1,
      version: 5,
      updated_at: stamp,
    },
  ],
};
const dataset: DatasetDescriptor = {
  key: "sales",
  module: "sales",
  label: "Sales dataset",
  description: "Sales analytics",
  version: "1",
  freshness: "realtime",
  entitlement: { state: "available" },
  dimensions: [
    {
      key: "region",
      label: "Region",
      type: "string",
      filter_operators: ["eq"],
      sensitivity: "internal",
    },
  ],
  measures: [
    {
      key: "amount",
      label: "Amount",
      result_type: "number",
      aggregation: "sum",
    },
  ],
  supported_grouping: ["region"],
  supported_ordering: ["amount"],
  required_permission: "bi.view",
  maximum_row_limit: 2500,
};
const datasetSummaries: DatasetSummary[] = [
  {
    key: "sales",
    module: "sales",
    label: "Sales dataset",
    description: "Sales analytics",
    version: "1",
    freshness: "realtime",
    entitlement: { state: "available" },
    dimension_count: 1,
    measure_count: 1,
  },
  {
    key: "finance",
    module: "finance",
    label: "Finance dataset",
    description: "Restricted finance analytics",
    version: "2",
    freshness: "hourly",
    entitlement: {
      state: "locked",
      required_entitlement: "bi.finance",
      upgrade_url: "https://billing.example.test/upgrade",
    },
    dimension_count: 2,
    measure_count: 4,
  },
];
const emptyQuery: QueryCreate = {
  query_code: "",
  name: "",
  description: "",
  dataset_key: "",
  dimensions: [],
  measures: [],
  filters: [],
  grouping: [],
  ordering: [],
  parameters_schema: {},
  row_limit: 500,
  cache_ttl_seconds: 300,
};
const emptyReport: ReportCreate = {
  report_code: "",
  report_name: "",
  description: "",
  report_type: "table",
  query_definition_id: "",
  visualization: {},
  default_parameters: {},
};

function renderWithQueryClient(
  element: ReactElement,
  initialEntries = ["/dashboards/dashboard-1"]
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/dashboards/:id" element={element} />
          <Route path="/dashboards/:id/edit" element={element} />
          <Route path="/dashboards/new" element={element} />
          <Route path="/dashboards" element={element} />
          <Route path="/queries/new" element={element} />
          <Route path="/queries/:id" element={element} />
          <Route path="/queries" element={element} />
          <Route path="/reports/:id" element={element} />
          <Route path="/reports" element={element} />
          <Route path="/executions/:id" element={element} />
          <Route path="/executions" element={element} />
          <Route path="/datasets" element={element} />
          <Route path="/" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("business intelligence low coverage pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(biService.getDashboard).mockResolvedValue(dashboard);
    vi.mocked(biService.listDashboards).mockResolvedValue({
      items: [dashboard],
      correlationId: "corr-dashboards",
      meta: {
        count: 1,
        page: 1,
        page_size: 20,
        total_pages: 2,
        has_next: true,
        has_previous: false,
      },
    });
    vi.mocked(biService.listQueries).mockResolvedValue({
      items: [query],
      correlationId: "corr-bi",
      meta: {
        count: 1,
        page: 1,
        page_size: 100,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
    });
    vi.mocked(biService.listReports).mockResolvedValue({
      items: [reportDetail],
      correlationId: "corr-reports",
      meta: {
        count: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
    });
    vi.mocked(biService.listExecutions).mockResolvedValue({
      items: [succeededExecution],
      correlationId: "corr-executions",
      meta: {
        count: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
    });
    vi.mocked(biService.listDatasets).mockResolvedValue({
      items: datasetSummaries,
      correlationId: "corr-datasets",
      meta: {
        count: 2,
        page: 1,
        page_size: 20,
        total_pages: 2,
        has_next: true,
        has_previous: false,
      },
    });
    vi.mocked(biService.getDataset).mockResolvedValue(dataset);
    vi.mocked(biService.getQuery).mockResolvedValue(queryDetail);
    vi.mocked(biService.getReport).mockResolvedValue(reportDetail);
    vi.mocked(biService.getExecution).mockResolvedValue(succeededExecution);
    vi.mocked(biService.getExecutionResult).mockResolvedValue(executionResult);
    vi.mocked(biService.addWidget).mockResolvedValue(dashboard.widgets[0]!);
    vi.mocked(biService.reorderWidgets).mockResolvedValue(dashboard.widgets);
    vi.mocked(biService.removeWidget).mockResolvedValue(undefined);
    vi.mocked(biService.createShare).mockResolvedValue({
      id: "share-1",
      dashboard_id: "dashboard-1",
      subject_type: "role",
      subject_id: "finance-admin",
      access_level: "edit",
      shared_by_id: "user-1",
      expires_at: null,
      revoked_at: null,
      created_at: stamp,
      updated_at: stamp,
    });
    vi.mocked(biService.executeQuery).mockResolvedValue({
      execution_id: "execution-queued",
      status: "queued",
    });
    vi.mocked(biService.executeReport).mockResolvedValue({
      execution_ids: ["execution-report"],
      status: "queued",
    });
    vi.mocked(biService.transitionQuery).mockResolvedValue(queryDetail);
    vi.mocked(biService.transitionReport).mockResolvedValue(reportDetail);
    vi.mocked(biService.cancelExecution).mockResolvedValue({
      ...runningExecution,
      status: "cancelled",
    });
    vi.mocked(biService.createDashboard).mockResolvedValue(dashboard);
    vi.mocked(biService.createQuery).mockResolvedValue(queryDetail);
    vi.mocked(biService.executeDashboard).mockResolvedValue({
      execution_ids: ["execution-dashboard"],
      status: "queued",
    });
    vi.mocked(biService.updateQuery).mockResolvedValue(queryDetail);
  });

  it("renders dashboard detail widgets and refreshes only published dashboards", async () => {
    const user = userEvent.setup();
    vi.mocked(biService.getDashboard).mockResolvedValueOnce({
      ...dashboard,
      state: "published",
      last_refresh: stamp,
    });
    renderWithQueryClient(<DashboardDetailPage />, ["/dashboards/dashboard-1"]);

    expect(await screen.findByRole("heading", { name: "Executive dashboard" })).toBeVisible();
    expect(screen.getByText("Access: edit")).toBeVisible();
    expect(screen.getByText("Pipeline value")).toBeVisible();
    expect(screen.getByText("Win rate")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() =>
      expect(biService.executeDashboard).toHaveBeenCalledWith("dashboard-1", {}, "idem-bi-test")
    );
  });

  it("creates semantic queries from the dataset-backed wrapper page", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CreateQueryPage />, ["/queries/new?dataset=sales"]);

    expect(await screen.findByRole("heading", { name: "Create semantic query" })).toBeVisible();
    expect(screen.getByLabelText("Dataset")).toHaveValue("sales");
    await user.type(screen.getByLabelText("Code"), "sales summary!");
    await user.type(screen.getByLabelText("Name"), "Sales summary");
    const semanticSelections = screen.getAllByRole("checkbox");
    await user.click(semanticSelections[0]!);
    await user.click(semanticSelections[1]!);
    fireEvent.change(screen.getByLabelText("Row limit"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("Cache lifetime (seconds)"), {
      target: { value: "120" },
    });

    await user.click(screen.getByRole("button", { name: "Create draft query" }));
    await waitFor(() =>
      expect(biService.createQuery).toHaveBeenCalledWith(
        expect.objectContaining({
          query_code: "SALESSUMMARY",
          name: "Sales summary",
          dataset_key: "sales",
          dimensions: ["region"],
          measures: [{ key: "amount" }],
          row_limit: 1000,
          cache_ttl_seconds: 120,
        }),
        "idem-bi-test"
      )
    );
  });

  it("filters dashboard, query, report, and execution list pages with routed navigation", async () => {
    const user = userEvent.setup();
    const dashboards = renderWithQueryClient(<DashboardListPage />, ["/dashboards"]);

    expect(await screen.findByRole("heading", { name: "Dashboards" })).toBeVisible();
    fireEvent.change(screen.getByPlaceholderText("Search dashboards"), {
      target: { value: "exec" },
    });
    await user.selectOptions(await screen.findByLabelText("Access"), "shared");
    await waitFor(() =>
      expect(biService.listDashboards).toHaveBeenLastCalledWith({
        search: "exec",
        access: "shared",
        page: 1,
        ordering: "-updated_at",
      })
    );
    await user.click(screen.getByText("Executive dashboard"));
    dashboards.unmount();

    renderWithQueryClient(<QueryListPage />, ["/queries"]);
    expect(await screen.findByRole("heading", { name: "Semantic queries" })).toBeVisible();
    fireEvent.change(screen.getByPlaceholderText("Search code or name"), {
      target: { value: "sales" },
    });
    await user.selectOptions(await screen.findByLabelText("Filter by state"), "published");
    await waitFor(() =>
      expect(biService.listQueries).toHaveBeenLastCalledWith({
        search: "sales",
        state: "published",
        page: 1,
        ordering: "-updated_at",
      })
    );
    await user.click(screen.getByRole("button", { name: "Sales summary" }));
    cleanup();

    renderWithQueryClient(<ReportListPage />, ["/reports"]);
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeVisible();
    fireEvent.change(screen.getByPlaceholderText("Search reports"), {
      target: { value: "pipeline" },
    });
    await user.selectOptions(await screen.findByLabelText("Report type"), "table");
    await user.selectOptions(await screen.findByLabelText("State"), "published");
    await waitFor(() =>
      expect(biService.listReports).toHaveBeenLastCalledWith({
        search: "pipeline",
        report_type: "table",
        state: "published",
        page: 1,
        ordering: "-updated_at",
      })
    );
    await user.click(screen.getByRole("button", { name: "Pipeline report" }));
    cleanup();

    renderWithQueryClient(<ExecutionListPage />, ["/executions"]);
    expect(await screen.findByRole("heading", { name: "Execution history" })).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Status"), "succeeded");
    fireEvent.change(await screen.findByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.change(await screen.findByLabelText("To"), { target: { value: "2026-01-31" } });
    await waitFor(() =>
      expect(biService.listExecutions).toHaveBeenLastCalledWith({
        status: "succeeded",
        created_after: "2026-01-01",
        created_before: "2026-01-31",
        page: 1,
        ordering: "-created_at",
      })
    );
    await user.click(screen.getByRole("row", { name: /sales Query v3 succeeded/u }));
  });

  it("creates dashboards and edits queries through routed wrappers with idempotent payloads", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CreateDashboardPage />, ["/dashboards/new"]);

    expect(await screen.findByRole("heading", { name: "Create dashboard" })).toBeVisible();
    await user.type(screen.getByLabelText("Code"), "exec dashboard!");
    await user.type(screen.getByLabelText("Name"), "Executive dashboard");
    await user.type(screen.getByLabelText("Description"), "Board-visible governed metrics");
    fireEvent.change(screen.getByLabelText("Automatic refresh (seconds)"), {
      target: { value: "300" },
    });
    await user.click(screen.getByRole("button", { name: "Continue to dashboard builder" }));

    await waitFor(() =>
      expect(biService.createDashboard).toHaveBeenCalledWith(
        {
          dashboard_code: "EXECDASHBOARD",
          dashboard_name: "Executive dashboard",
          description: "Board-visible governed metrics",
          global_filters: [],
          refresh_interval_seconds: 300,
        },
        "idem-bi-test"
      )
    );
    cleanup();

    renderWithQueryClient(<EditQueryPage />, ["/queries/query-1"]);
    expect(await screen.findByRole("heading", { name: "Edit Sales summary" })).toBeVisible();
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Sales summary governed");
    await user.click(screen.getByRole("button", { name: "Save query" }));

    await waitFor(() =>
      expect(biService.updateQuery).toHaveBeenCalledWith(
        "query-1",
        expect.objectContaining({
          name: "Sales summary governed",
          version: 3,
          dataset_key: "sales",
          dimensions: ["region"],
          measures: [{ key: "amount", alias: "pipeline_amount" }],
        }),
        "idem-bi-test"
      )
    );
  });

  it("validates report form and submits selected published query metadata", async () => {
    const submit = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(
      <ReportForm
        initial={emptyReport}
        queries={[query]}
        onSubmit={submit}
        pending={false}
        error={undefined}
        submitLabel="Save report"
        storageKey="bi-report-form-test"
      />,
      ["/"]
    );

    expect(screen.getByRole("button", { name: "Save report" })).toBeDisabled();
    await user.type(screen.getByLabelText("Code"), "pipeline report!");
    await user.type(screen.getByLabelText("Name"), "Pipeline report");
    await user.type(screen.getByLabelText("Description"), "Pipeline by region");
    await user.selectOptions(screen.getByLabelText("Published query"), "query-1");
    await user.selectOptions(screen.getByLabelText("Report type"), "chart");
    await user.click(screen.getByRole("button", { name: "Save report" }));

    expect(submit).toHaveBeenCalledWith({
      report_code: "PIPELINEREPORT",
      report_name: "Pipeline report",
      description: "Pipeline by region",
      report_type: "chart",
      query_definition_id: "query-1",
      visualization: {},
      default_parameters: {},
    });
  });

  it("adds, reorders, removes, and shares dashboard widgets with governed payloads", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<EditDashboardPage />);

    expect(await screen.findByRole("heading", { name: "Build Executive dashboard" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Add widget" }));
    const addDialog = await screen.findByRole("dialog", { name: "Add widget" });
    await user.type(within(addDialog).getByLabelText("Title"), "Regional sales");
    await user.selectOptions(within(addDialog).getByLabelText("Published query"), "query-1");
    fireEvent.change(within(addDialog).getByLabelText("Width (1–12)"), { target: { value: "8" } });
    fireEvent.change(within(addDialog).getByLabelText("Height (1–24)"), { target: { value: "5" } });
    await user.click(within(addDialog).getByRole("button", { name: "Add widget" }));

    await waitFor(() =>
      expect(biService.addWidget).toHaveBeenCalledWith(
        "dashboard-1",
        expect.objectContaining({
          query_definition_id: "query-1",
          title: "Regional sales",
          width: 8,
          height: 5,
          display_order: 2,
          y: 5,
        }),
        "idem-bi-test"
      )
    );

    await user.click(screen.getByRole("button", { name: "Move Win rate up" }));
    await waitFor(() =>
      expect(biService.reorderWidgets).toHaveBeenCalledWith(
        "dashboard-1",
        7,
        [
          expect.objectContaining({ id: "widget-2", display_order: 0, y: 0, version: 5 }),
          expect.objectContaining({ id: "widget-1", display_order: 1, y: 2, version: 2 }),
        ],
        "idem-bi-test"
      )
    );

    await user.click(screen.getByRole("button", { name: "Remove Pipeline value" }));
    await waitFor(() =>
      expect(biService.removeWidget).toHaveBeenCalledWith("dashboard-1", "widget-1", "idem-bi-test")
    );

    await user.click(screen.getByRole("button", { name: "Share" }));
    const shareDialog = await screen.findByRole("dialog", { name: "Share dashboard" });
    await user.selectOptions(within(shareDialog).getByLabelText("Subject type"), "role");
    await user.type(within(shareDialog).getByLabelText("User or role ID"), "finance-admin");
    await user.selectOptions(within(shareDialog).getByLabelText("Access"), "edit");
    await user.click(within(shareDialog).getByRole("button", { name: "Share" }));

    await waitFor(() =>
      expect(biService.createShare).toHaveBeenCalledWith(
        "dashboard-1",
        { subject_type: "role", subject_id: "finance-admin", access_level: "edit" },
        "idem-bi-test"
      )
    );
  });

  it("surfaces dashboard load failures with retry-visible request state", async () => {
    vi.mocked(biService.getDashboard).mockRejectedValue(
      new ApiError("Dashboard unavailable", 503, undefined, "BI_DOWN", "corr-bi-down")
    );
    renderWithQueryClient(<EditDashboardPage />);

    expect(await screen.findByText("Service temporarily unavailable")).toBeVisible();
    expect(screen.getByText("Dashboard unavailable")).toBeVisible();
  });

  it("runs and archives published query details with versioned idempotent payloads", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<QueryDetailPage />, ["/queries/query-1"]);

    expect(await screen.findByRole("heading", { name: "Sales summary" })).toBeVisible();
    expect(screen.getByText("SALES_SUMMARY · sales")).toBeVisible();
    expect(screen.getByText("amount as pipeline_amount")).toBeVisible();
    expect(screen.getByText("publish")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() =>
      expect(biService.transitionQuery).toHaveBeenCalledWith(
        "query-1",
        "archive",
        { version: 3 },
        "idem-bi-test"
      )
    );

    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() =>
      expect(biService.executeQuery).toHaveBeenCalledWith("query-1", {}, "idem-bi-test")
    );
  });

  it("publishes draft query details while disabling execution until published", async () => {
    vi.mocked(biService.getQuery).mockResolvedValue({ ...queryDetail, state: "draft", version: 9 });
    const user = userEvent.setup();
    renderWithQueryClient(<QueryDetailPage />, ["/queries/query-1"]);

    expect(await screen.findByRole("button", { name: "Run" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() =>
      expect(biService.transitionQuery).toHaveBeenCalledWith(
        "query-1",
        "publish",
        { version: 9 },
        "idem-bi-test"
      )
    );
    expect(biService.executeQuery).not.toHaveBeenCalled();
  });

  it("runs report details and navigates from report/query evidence links", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ReportDetailPage />, ["/reports/report-1"]);

    expect(await screen.findByRole("heading", { name: "Pipeline report" })).toBeVisible();
    expect(screen.getByText("PIPELINE · table")).toBeVisible();
    expect(screen.getByText("Sales summary")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() =>
      expect(biService.transitionReport).toHaveBeenCalledWith(
        "report-1",
        "archive",
        { version: 4 },
        "idem-bi-test"
      )
    );

    await user.click(screen.getByRole("button", { name: "Run report" }));
    await waitFor(() =>
      expect(biService.executeReport).toHaveBeenCalledWith("report-1", {}, "idem-bi-test")
    );
  });

  it("cancels active executions and renders stored result evidence for succeeded executions", async () => {
    const user = userEvent.setup();
    vi.mocked(biService.getExecution).mockResolvedValueOnce(runningExecution);
    renderWithQueryClient(<ExecutionDetailPage />, ["/executions/execution-1"]);

    expect(await screen.findByRole("heading", { name: "Execution details" })).toBeVisible();
    expect(screen.getAllByText("running").length).toBeGreaterThanOrEqual(1);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(biService.cancelExecution).toHaveBeenCalledWith("execution-1", "idem-bi-test")
    );

    vi.mocked(biService.getExecution).mockResolvedValue(succeededExecution);
    cleanup();
    renderWithQueryClient(<ExecutionDetailPage />, ["/executions/execution-1"]);
    expect(await screen.findByText("Results (truncated)")).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "Region" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "East" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "125000" })).toBeVisible();
    expect(biService.getExecutionResult).toHaveBeenCalledWith("execution-1", {
      page: 1,
      page_size: 100,
    });
  });

  it("renders sanitized execution failure evidence without requesting stored rows", async () => {
    vi.mocked(biService.getExecution).mockResolvedValue(failedExecution);
    renderWithQueryClient(<ExecutionDetailPage />, ["/executions/execution-failed"]);

    expect(await screen.findByText("Sanitized failure evidence")).toBeVisible();
    expect(screen.getByText("SOURCE_TIMEOUT")).toBeVisible();
    expect(
      screen.getByText("Warehouse request timed out after the configured limit.")
    ).toBeVisible();
    expect(biService.getExecutionResult).not.toHaveBeenCalled();
  });

  it("filters dataset catalog, protects locked datasets, and starts queries only from entitled datasets", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DatasetCatalogPage />, ["/datasets"]);

    expect(await screen.findByRole("heading", { name: "Dataset catalog" })).toBeVisible();
    expect(screen.getByText("Sales dataset")).toBeVisible();
    expect(screen.getByText("Finance dataset")).toBeVisible();
    expect(screen.getByLabelText("Locked")).toBeVisible();
    expect(screen.getByText("Requires bi.finance")).toBeVisible();

    fireEvent.change(screen.getByPlaceholderText("Search datasets"), {
      target: { value: "pipeline" },
    });
    await waitFor(() =>
      expect(biService.listDatasets).toHaveBeenLastCalledWith({
        search: "pipeline",
        module: "",
        page: 1,
        include_locked: true,
      })
    );
    fireEvent.change(screen.getByLabelText("Filter by owning module"), {
      target: { value: "sales" },
    });
    await waitFor(() =>
      expect(biService.listDatasets).toHaveBeenLastCalledWith({
        search: "pipeline",
        module: "sales",
        page: 1,
        include_locked: true,
      })
    );

    expect(screen.getByRole("navigation", { name: "Pagination" })).toHaveTextContent(
      "Page 1 of 2 · 2 items"
    );
    await user.click(screen.getByRole("button", { name: "Start query" }));
  });

  it("validates QueryForm before submit and sends selected semantic fields", async () => {
    const submit = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(
      <QueryForm
        initial={emptyQuery}
        datasets={[dataset]}
        dataset={dataset}
        onDatasetChange={vi.fn()}
        onSubmit={submit}
        error={undefined}
        pending={false}
        storageKey="bi-query-form-test"
        submitLabel="Save query"
      />,
      ["/"]
    );

    expect(screen.getByRole("button", { name: "Save query" })).toBeDisabled();
    await user.type(screen.getByLabelText("Code"), "sales summary!");
    await user.type(screen.getByLabelText("Name"), "Sales summary");
    await user.selectOptions(screen.getByLabelText("Dataset"), "sales");
    const semanticSelections = screen.getAllByRole("checkbox");
    await user.click(semanticSelections[0]!);
    await user.click(semanticSelections[1]!);
    fireEvent.change(screen.getByLabelText("Row limit"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("Cache lifetime (seconds)"), {
      target: { value: "120" },
    });

    expect(screen.getByText("Ready for server schema validation.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save query" }));
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        query_code: "SALESSUMMARY",
        name: "Sales summary",
        dataset_key: "sales",
        dimensions: ["region"],
        measures: [{ key: "amount" }],
        row_limit: 1000,
        cache_ttl_seconds: 120,
      })
    );
  });

  it("restores QueryForm local draft and displays mutation field errors", () => {
    localStorage.setItem(
      "bi-query-form-test",
      JSON.stringify({ ...emptyQuery, query_code: "SAVED", name: "Saved draft" })
    );
    renderWithQueryClient(
      <QueryForm
        initial={emptyQuery}
        datasets={[dataset]}
        onDatasetChange={vi.fn()}
        onSubmit={vi.fn()}
        error={
          new ApiError(
            "Validation failed",
            400,
            { error: { field_errors: { query_code: ["Already exists"] } } },
            "invalid",
            "corr-invalid"
          )
        }
        pending={false}
        storageKey="bi-query-form-test"
        submitLabel="Save query"
      />,
      ["/"]
    );

    expect(screen.getByLabelText("Code")).toHaveValue("SAVED");
    expect(screen.getByLabelText("Name")).toHaveValue("Saved draft");
    expect(screen.getByRole("alert")).toHaveTextContent("query_code: Already exists");
    expect(
      screen.getByText("Choose a dataset and at least one dimension or measure.")
    ).toBeVisible();
  });
});
