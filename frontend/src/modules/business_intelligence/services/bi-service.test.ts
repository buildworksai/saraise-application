/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method -- mutation-focused service boundary tests intentionally keep endpoint matrices local. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiEnvelope,
  type DashboardDetail,
  type DashboardShare,
  type DashboardWidget,
  type DatasetDescriptor,
  type DatasetSummary,
  type ExecutionDetail,
  type HealthResponse,
  type QueryDetail,
  type ReportDetail,
} from "../contracts";
import { biQueryKeys, biService, createIdempotencyKey } from "./bi-service";

vi.mock("@/services/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
const meta = { correlation_id: "corr-1", timestamp: "2026-07-23T00:00:00Z" };
const query: QueryDetail = {
  id: "query-1",
  query_code: "SALES",
  name: "Sales",
  description: "",
  dataset_key: "core.sales",
  dataset_version: "1.0.0",
  dataset_schema_fingerprint: "schema-fingerprint",
  state: "draft",
  version: 1,
  updated_at: meta.timestamp,
  created_at: meta.timestamp,
  created_by_id: "user-1",
  updated_by_id: "user-1",
  dimensions: ["region"],
  measures: [{ key: "revenue" }],
  filters: [],
  grouping: [],
  ordering: [],
  parameters_schema: {},
  row_limit: 500,
  cache_ttl_seconds: 300,
  transition_history: [],
};
const datasetSummary = {
  key: "core.sales",
  module: "sales",
  label: "Sales",
  description: "Sales facts",
  version: "1.0.0",
  freshness: "live",
  entitlement: { state: "available" },
  dimension_count: 1,
  measure_count: 1,
} satisfies DatasetSummary;
const datasetDescriptor = {
  ...datasetSummary,
  dimensions: [],
  measures: [],
  supported_grouping: [],
  supported_ordering: [],
  required_permission: "business_intelligence.dataset:read",
  maximum_row_limit: 1000,
} satisfies DatasetDescriptor;
const dashboard = { id: "dashboard-1", dashboard_name: "Revenue" } as DashboardDetail;
const widget = { id: "widget-1", title: "Revenue" } as DashboardWidget;
const share = { id: "share-1", subject_type: "role", access_level: "view" } as DashboardShare;
const execution = { id: "execution-1", status: "queued" } as ExecutionDetail;
const health = { status: "healthy", ready: true, dependencies: {} } satisfies HealthResponse;

const pageEnvelope = <T>(data: T[]): ApiEnvelope<T[]> => ({
  data,
  meta: {
    ...meta,
    pagination: {
      count: data.length,
      page: 1,
      page_size: 25,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
  },
});
const envelope = <T>(data: T): ApiEnvelope<T> => ({ data, meta });
const pageResult = <T>(data: T[]) => ({
  items: data,
  meta: {
    count: data.length,
    page: 1,
    page_size: 25,
    total_pages: 1,
    has_next: false,
    has_previous: false,
  },
  correlationId: "corr-1",
});

describe("business intelligence v2 service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps governed collection data and pagination evidence", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [query],
      meta: {
        ...meta,
        pagination: {
          count: 1,
          page: 1,
          page_size: 25,
          total_pages: 1,
          has_next: false,
          has_previous: false,
        },
      },
    } satisfies ApiEnvelope<QueryDetail[]>);
    const result = await biService.listQueries({ state: "draft", page: 1 });
    expect(result.items).toEqual([query]);
    expect(result.correlationId).toBe("corr-1");
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.QUERIES.LIST}?state=draft&page=1`);
  });

  it("normalizes filters and preserves fallback pagination for legacy-compatible pages", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [query],
      meta,
    } satisfies ApiEnvelope<QueryDetail[]>);

    const result = await biService.listQueries({
      state: "draft",
      page: 0,
      archived: false,
      empty: "",
      missing: null,
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.QUERIES.LIST}?state=draft&page=0&archived=false`
    );
    expect(result).toStrictEqual({
      items: [query],
      correlationId: "corr-1",
      meta: {
        count: 1,
        page: 1,
        page_size: 1,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
    });
  });

  it("does not append query delimiters when collection filters are empty or omitted", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [],
      meta,
    } satisfies ApiEnvelope<QueryDetail[]>);

    await biService.listQueries();
    await biService.listQueries({ state: undefined, search: "", missing: null });

    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.QUERIES.LIST);
    expect(apiClient.get).toHaveBeenNthCalledWith(2, ENDPOINTS.QUERIES.LIST);
  });

  it("serializes execution-result filters with encoded values and without empty entries", async () => {
    const result = {
      columns: ["region"],
      rows: [{ region: "North East" }],
      row_count: 1,
      truncated: false,
    };
    vi.mocked(apiClient.get).mockResolvedValue({
      data: result,
      meta,
    } satisfies ApiEnvelope<typeof result>);

    await expect(
      biService.getExecutionResult("execution-1", {
        search: "North East",
        include_totals: true,
        page: 2,
        empty: "",
        missing: null,
      })
    ).resolves.toBe(result);

    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.EXECUTIONS.RESULT("execution-1")}?search=North+East&include_totals=true&page=2`
    );
  });

  it("sends idempotency evidence on mutations", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: query,
      meta,
    } satisfies ApiEnvelope<QueryDetail>);
    await biService.createQuery(
      {
        query_code: "SALES",
        name: "Sales",
        dataset_key: "core.sales",
        dimensions: ["region"],
        measures: [{ key: "revenue" }],
      },
      "operation-1"
    );
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.QUERIES.CREATE, expect.any(Object), {
      headers: { "Idempotency-Key": "operation-1" },
    });
  });

  it("sends idempotency evidence for updates, deletes, transitions, and execution requests", async () => {
    const dashboard = { id: "dashboard-1" } as DashboardDetail;
    vi.mocked(apiClient.patch).mockResolvedValue({
      data: dashboard,
      meta,
    } satisfies ApiEnvelope<DashboardDetail>);
    vi.mocked(apiClient.post).mockResolvedValue({
      data: dashboard,
      meta,
    } satisfies ApiEnvelope<DashboardDetail>);
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await biService.updateDashboard(
      "dashboard-1",
      { dashboard_name: "Revenue", version: 3 },
      "update-key"
    );
    await biService.transitionDashboard(
      "dashboard-1",
      "publish",
      { reason: "approved", version: 4 },
      "transition-key"
    );
    await biService.deleteDashboard("dashboard-1", "delete-key");
    await biService.executeQuery("query-1", { parameters: { region: "west" } }, "execute-key");

    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.DASHBOARDS.UPDATE("dashboard-1"),
      { dashboard_name: "Revenue", version: 3 },
      { headers: { "Idempotency-Key": "update-key" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.DASHBOARDS.PUBLISH("dashboard-1"),
      { reason: "approved", version: 4 },
      { headers: { "Idempotency-Key": "transition-key" } }
    );
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.DASHBOARDS.DELETE("dashboard-1"), {
      headers: { "Idempotency-Key": "delete-key" },
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.QUERIES.EXECUTE("query-1"),
      { parameters: { region: "west" } },
      { headers: { "Idempotency-Key": "execute-key" } }
    );
  });

  it("posts validation requests without mutation idempotency headers", async () => {
    const validation = {
      valid: true,
      errors: [],
      warnings: [],
      estimated_cost: { rows: 10 },
    };
    vi.mocked(apiClient.post).mockResolvedValue({
      data: validation,
      meta,
    } satisfies ApiEnvelope<typeof validation>);

    await expect(biService.validateQuery("query-1")).resolves.toBe(validation);
    await biService.validateQuery("query-1", { parameters: { region: "west" } });

    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.QUERIES.VALIDATE("query-1"), {});
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.QUERIES.VALIDATE("query-1"), {
      parameters: { region: "west" },
    });
  });

  it("rejects unsupported transition commands before issuing an API request", () => {
    expect(() =>
      biService.transitionQuery(
        "query-1",
        "escalate" as Parameters<typeof biService.transitionQuery>[1],
        { reason: "invalid", version: 1 },
        "transition-key"
      )
    ).toThrow(TypeError);
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("serializes widget reorders and execution cancellations through explicit request bodies", async () => {
    const widgets = [
      { id: "widget-1", x: 0, y: 1, width: 6, height: 4, display_order: 2, version: 3 },
      { id: "widget-2", x: 6, y: 0, width: 6, height: 4, display_order: 1, version: 5 },
    ];
    const reordered = widgets.map((widget) => ({ id: widget.id }));
    const execution = { id: "execution-1", status: "cancelled" };
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({
        data: reordered,
        meta,
      } satisfies ApiEnvelope<typeof reordered>)
      .mockResolvedValueOnce({
        data: execution,
        meta,
      } satisfies ApiEnvelope<typeof execution>);

    await expect(biService.reorderWidgets("dashboard-1", 7, widgets, "reorder-key")).resolves.toBe(
      reordered
    );
    await expect(biService.cancelExecution("execution-1", "cancel-key")).resolves.toBe(execution);

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.DASHBOARDS.WIDGET_REORDER("dashboard-1"),
      { version: 7, widgets },
      { headers: { "Idempotency-Key": "reorder-key" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.EXECUTIONS.CANCEL("execution-1"),
      {},
      { headers: { "Idempotency-Key": "cancel-key" } }
    );
  });

  it("uses crypto idempotency keys when available and falls back to entropy plus timestamp", () => {
    const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, "crypto");
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: { randomUUID: vi.fn(() => "uuid-key") },
    });
    expect(createIdempotencyKey()).toBe("uuid-key");
    expect(globalThis.crypto.randomUUID).toHaveBeenCalledTimes(1);

    const dateNow = vi.spyOn(Date, "now").mockReturnValue(123456);
    const random = vi.spyOn(Math, "random").mockReturnValue(0.5);
    Object.defineProperty(globalThis, "crypto", { configurable: true, value: {} });
    expect(createIdempotencyKey()).toBe("123456-i");

    Object.defineProperty(globalThis, "crypto", { configurable: true, value: undefined });
    expect(createIdempotencyKey()).toBe("123456-i");

    if (cryptoDescriptor) Object.defineProperty(globalThis, "crypto", cryptoDescriptor);
    else delete (globalThis as Partial<typeof globalThis>).crypto;
    dateNow.mockRestore();
    random.mockRestore();
  });

  it("never accepts or returns the legacy raw-array report shape", async () => {
    const report = { id: "report-1" } as ReportDetail;
    vi.mocked(apiClient.get).mockResolvedValue({
      data: report,
      meta,
    } satisfies ApiEnvelope<ReportDetail>);
    await expect(biService.getReport("report-1")).resolves.toBe(report);
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.REPORTS.DETAIL("report-1"));
  });

  it("covers every read endpoint family with unwrapped governed responses", async () => {
    const readCases = [
      {
        call: () => biService.listDatasets({ page: 2 }),
        response: pageEnvelope([datasetSummary]),
        expected: pageResult([datasetSummary]),
        request: `${ENDPOINTS.DATASETS.LIST}?page=2`,
      },
      {
        call: () => biService.getDataset("core.sales"),
        response: envelope(datasetDescriptor),
        expected: datasetDescriptor,
        request: ENDPOINTS.DATASETS.DETAIL("core.sales"),
      },
      {
        call: () => biService.getQuery("query-1"),
        response: envelope(query),
        expected: query,
        request: ENDPOINTS.QUERIES.DETAIL("query-1"),
      },
      {
        call: () => biService.listReports({ state: "published" }),
        response: pageEnvelope([{ id: "report-1" } as ReportDetail]),
        expected: pageResult([{ id: "report-1" } as ReportDetail]),
        request: `${ENDPOINTS.REPORTS.LIST}?state=published`,
      },
      {
        call: () => biService.listDashboards({ search: "margin" }),
        response: pageEnvelope([dashboard]),
        expected: pageResult([dashboard]),
        request: `${ENDPOINTS.DASHBOARDS.LIST}?search=margin`,
      },
      {
        call: () => biService.getDashboard("dashboard-1"),
        response: envelope(dashboard),
        expected: dashboard,
        request: ENDPOINTS.DASHBOARDS.DETAIL("dashboard-1"),
      },
      {
        call: () => biService.listWidgets("dashboard-1", { page: 1 }),
        response: pageEnvelope([widget]),
        expected: pageResult([widget]),
        request: `${ENDPOINTS.DASHBOARDS.WIDGETS("dashboard-1")}?page=1`,
      },
      {
        call: () => biService.getWidget("dashboard-1", "widget-1"),
        response: envelope(widget),
        expected: widget,
        request: ENDPOINTS.DASHBOARDS.WIDGET_DETAIL("dashboard-1", "widget-1"),
      },
      {
        call: () => biService.listShares("dashboard-1"),
        response: pageEnvelope([share]),
        expected: pageResult([share]),
        request: ENDPOINTS.DASHBOARDS.SHARES("dashboard-1"),
      },
      {
        call: () => biService.listExecutions({ status: "queued" }),
        response: pageEnvelope([execution]),
        expected: pageResult([execution]),
        request: `${ENDPOINTS.EXECUTIONS.LIST}?status=queued`,
      },
      {
        call: () => biService.getExecution("execution-1"),
        response: envelope(execution),
        expected: execution,
        request: ENDPOINTS.EXECUTIONS.DETAIL("execution-1"),
      },
      {
        call: () => biService.health(),
        response: envelope(health),
        expected: health,
        request: ENDPOINTS.HEALTH,
      },
    ];

    for (const item of readCases) {
      vi.mocked(apiClient.get).mockResolvedValueOnce(item.response);
      await expect(item.call()).resolves.toStrictEqual(item.expected);
      expect(apiClient.get).toHaveBeenLastCalledWith(item.request);
    }
  });

  it("covers every mutation endpoint family with idempotency evidence", async () => {
    const enqueue = { execution_id: "execution-1", status: "queued" };
    const mutationCases = [
      {
        call: () => biService.updateQuery("query-1", { name: "Sales v2", version: 2 }, "key-1"),
        method: apiClient.patch,
        response: envelope(query),
        expected: query,
        request: [
          ENDPOINTS.QUERIES.UPDATE("query-1"),
          { name: "Sales v2", version: 2 },
          { headers: { "Idempotency-Key": "key-1" } },
        ],
      },
      {
        call: () => biService.transitionReport("report-1", "archive", { version: 3 }, "key-2"),
        method: apiClient.post,
        response: envelope({ id: "report-1" } as ReportDetail),
        expected: { id: "report-1" },
        request: [
          ENDPOINTS.REPORTS.ARCHIVE("report-1"),
          { version: 3 },
          { headers: { "Idempotency-Key": "key-2" } },
        ],
      },
      {
        call: () =>
          biService.executeReport("report-1", { parameters: { region: "east" } }, "key-3"),
        method: apiClient.post,
        response: envelope(enqueue),
        expected: enqueue,
        request: [
          ENDPOINTS.REPORTS.EXECUTE("report-1"),
          { parameters: { region: "east" } },
          { headers: { "Idempotency-Key": "key-3" } },
        ],
      },
      {
        call: () =>
          biService.createReport(
            {
              report_code: "REV",
              report_name: "Revenue",
              report_type: "table",
              query_definition_id: "query-1",
            },
            "key-10"
          ),
        method: apiClient.post,
        response: envelope({ id: "report-1" } as ReportDetail),
        expected: { id: "report-1" },
        request: [
          ENDPOINTS.REPORTS.CREATE,
          {
            report_code: "REV",
            report_name: "Revenue",
            report_type: "table",
            query_definition_id: "query-1",
          },
          { headers: { "Idempotency-Key": "key-10" } },
        ],
      },
      {
        call: () =>
          biService.updateReport("report-1", { report_name: "Revenue v2", version: 2 }, "key-11"),
        method: apiClient.patch,
        response: envelope({ id: "report-1", report_name: "Revenue v2" } as ReportDetail),
        expected: { id: "report-1", report_name: "Revenue v2" },
        request: [
          ENDPOINTS.REPORTS.UPDATE("report-1"),
          { report_name: "Revenue v2", version: 2 },
          { headers: { "Idempotency-Key": "key-11" } },
        ],
      },
      {
        call: () =>
          biService.createDashboard({ dashboard_code: "REV", dashboard_name: "Revenue" }, "key-4"),
        method: apiClient.post,
        response: envelope(dashboard),
        expected: dashboard,
        request: [
          ENDPOINTS.DASHBOARDS.CREATE,
          { dashboard_code: "REV", dashboard_name: "Revenue" },
          { headers: { "Idempotency-Key": "key-4" } },
        ],
      },
      {
        call: () =>
          biService.executeDashboard("dashboard-1", { parameters: { region: "central" } }, "key-5"),
        method: apiClient.post,
        response: envelope(enqueue),
        expected: enqueue,
        request: [
          ENDPOINTS.DASHBOARDS.EXECUTE("dashboard-1"),
          { parameters: { region: "central" } },
          { headers: { "Idempotency-Key": "key-5" } },
        ],
      },
      {
        call: () =>
          biService.addWidget(
            "dashboard-1",
            {
              title: "Revenue",
              widget_type: "kpi",
              x: 0,
              y: 0,
              width: 4,
              height: 2,
              display_order: 1,
            },
            "key-6"
          ),
        method: apiClient.post,
        response: envelope(widget),
        expected: widget,
        request: [
          ENDPOINTS.DASHBOARDS.WIDGETS("dashboard-1"),
          {
            title: "Revenue",
            widget_type: "kpi",
            x: 0,
            y: 0,
            width: 4,
            height: 2,
            display_order: 1,
          },
          { headers: { "Idempotency-Key": "key-6" } },
        ],
      },
      {
        call: () =>
          biService.updateWidget(
            "dashboard-1",
            "widget-1",
            { title: "Margin", version: 2 },
            "key-7"
          ),
        method: apiClient.patch,
        response: envelope(widget),
        expected: widget,
        request: [
          ENDPOINTS.DASHBOARDS.WIDGET_DETAIL("dashboard-1", "widget-1"),
          { title: "Margin", version: 2 },
          { headers: { "Idempotency-Key": "key-7" } },
        ],
      },
      {
        call: () =>
          biService.createShare(
            "dashboard-1",
            { subject_type: "role", subject_id: "finance", access_level: "view" },
            "key-8"
          ),
        method: apiClient.post,
        response: envelope(share),
        expected: share,
        request: [
          ENDPOINTS.DASHBOARDS.SHARES("dashboard-1"),
          { subject_type: "role", subject_id: "finance", access_level: "view" },
          { headers: { "Idempotency-Key": "key-8" } },
        ],
      },
      {
        call: () =>
          biService.updateShare("dashboard-1", "share-1", { access_level: "edit" }, "key-9"),
        method: apiClient.patch,
        response: envelope(share),
        expected: share,
        request: [
          ENDPOINTS.DASHBOARDS.SHARE_DETAIL("dashboard-1", "share-1"),
          { access_level: "edit" },
          { headers: { "Idempotency-Key": "key-9" } },
        ],
      },
    ];

    for (const item of mutationCases) {
      vi.mocked(item.method).mockClear();
      vi.mocked(item.method).mockResolvedValueOnce(item.response);
      await expect(item.call()).resolves.toStrictEqual(item.expected);
      expect(item.method).toHaveBeenCalledTimes(1);
      expect(item.method).toHaveBeenCalledWith(...item.request);
    }
  });

  it("covers destructive service calls without returning fake payloads", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await expect(biService.deleteQuery("query-1", "delete-query")).resolves.toBeUndefined();
    await expect(biService.deleteReport("report-1", "delete-report")).resolves.toBeUndefined();
    await expect(
      biService.removeWidget("dashboard-1", "widget-1", "remove-widget")
    ).resolves.toBeUndefined();
    await expect(
      biService.revokeShare("dashboard-1", "share-1", "revoke-share")
    ).resolves.toBeUndefined();

    expect(apiClient.delete).toHaveBeenNthCalledWith(1, ENDPOINTS.QUERIES.DELETE("query-1"), {
      headers: { "Idempotency-Key": "delete-query" },
    });
    expect(apiClient.delete).toHaveBeenNthCalledWith(2, ENDPOINTS.REPORTS.DELETE("report-1"), {
      headers: { "Idempotency-Key": "delete-report" },
    });
    expect(apiClient.delete).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.DASHBOARDS.WIDGET_DETAIL("dashboard-1", "widget-1"),
      { headers: { "Idempotency-Key": "remove-widget" } }
    );
    expect(apiClient.delete).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.DASHBOARDS.SHARE_DETAIL("dashboard-1", "share-1"),
      { headers: { "Idempotency-Key": "revoke-share" } }
    );
  });

  it("partitions every query cache key by tenant, resource, filters, and identifiers", () => {
    expect(biQueryKeys.datasets("tenant-a", { page: 1 })).toEqual([
      "business-intelligence",
      "tenant-a",
      "datasets",
      { page: 1 },
    ]);
    expect(biQueryKeys.dataset("tenant-a", "core.sales")).toEqual([
      "business-intelligence",
      "tenant-a",
      "dataset",
      "core.sales",
    ]);
    expect(biQueryKeys.queries("tenant-a", { state: "draft", page: 2 })).toEqual([
      "business-intelligence",
      "tenant-a",
      "queries",
      { state: "draft", page: 2 },
    ]);
    expect(biQueryKeys.query("tenant-a", "query-1")).toEqual([
      "business-intelligence",
      "tenant-a",
      "query",
      "query-1",
    ]);
    expect(biQueryKeys.reports("tenant-a", { state: "published" })).toEqual([
      "business-intelligence",
      "tenant-a",
      "reports",
      { state: "published" },
    ]);
    expect(biQueryKeys.report("tenant-a", "report-1")).toEqual([
      "business-intelligence",
      "tenant-a",
      "report",
      "report-1",
    ]);
    expect(biQueryKeys.dashboards("tenant-a", { search: "rev" })).toEqual([
      "business-intelligence",
      "tenant-a",
      "dashboards",
      { search: "rev" },
    ]);
    expect(biQueryKeys.dashboard("tenant-a", "dashboard-1")).toEqual([
      "business-intelligence",
      "tenant-a",
      "dashboard",
      "dashboard-1",
    ]);
    expect(biQueryKeys.widgets("tenant-a", "dashboard-1", { page: 3 })).toEqual([
      "business-intelligence",
      "tenant-a",
      "dashboard",
      "dashboard-1",
      "widgets",
      { page: 3 },
    ]);
    expect(biQueryKeys.shares("tenant-a", "dashboard-1", { access: "view" })).toEqual([
      "business-intelligence",
      "tenant-a",
      "dashboard",
      "dashboard-1",
      "shares",
      { access: "view" },
    ]);
    expect(biQueryKeys.executions("tenant-a", { status: "queued" })).toEqual([
      "business-intelligence",
      "tenant-a",
      "executions",
      { status: "queued" },
    ]);
    expect(biQueryKeys.execution("tenant-a", "execution-1")).toEqual([
      "business-intelligence",
      "tenant-a",
      "execution",
      "execution-1",
    ]);
    expect(biQueryKeys.result("tenant-a", "execution-1", { page: 4 })).toEqual([
      "business-intelligence",
      "tenant-a",
      "execution",
      "execution-1",
      "result",
      { page: 4 },
    ]);
    expect(biQueryKeys.query("tenant-a", "query-1")).not.toEqual(
      biQueryKeys.query("tenant-a", "query-2")
    );
  });
});
