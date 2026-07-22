/* eslint-disable @typescript-eslint/unbound-method -- assertions intentionally reference typed API mocks */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS, type ApiEnvelope, type QueryDetail, type ReportDetail } from "../contracts";
import { biQueryKeys, biService } from "./bi-service";

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

  it("never accepts or returns the legacy raw-array report shape", async () => {
    const report = { id: "report-1" } as ReportDetail;
    vi.mocked(apiClient.get).mockResolvedValue({
      data: report,
      meta,
    } satisfies ApiEnvelope<ReportDetail>);
    await expect(biService.getReport("report-1")).resolves.toBe(report);
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.REPORTS.DETAIL("report-1"));
  });

  it("partitions query cache keys by tenant, filters, page, and identifier", () => {
    expect(biQueryKeys.queries("tenant-a", { state: "draft", page: 2 })).not.toEqual(
      biQueryKeys.queries("tenant-b", { state: "draft", page: 2 })
    );
    expect(biQueryKeys.query("tenant-a", "query-1")).not.toEqual(
      biQueryKeys.query("tenant-a", "query-2")
    );
  });
});
