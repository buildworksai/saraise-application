/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- service request coverage uses a dense fixture harness. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import type { AssetCategory, DepreciationLine, PaginatedEnvelope } from "../contracts";
import { ENDPOINTS } from "../contracts";
import {
  createIdempotencyKey,
  fixedAssetQueryKeys,
  fixedAssetsService,
  shouldPollJob,
} from "./fixed-assets-service";

vi.mock("@/services/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      readonly status: number,
      readonly details?: unknown,
      readonly code?: string,
      readonly correlationId?: string
    ) {
      super(message);
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const pagination = {
  page: 1,
  page_size: 25,
  total_pages: 1,
  count: 1,
  has_next: false,
  has_previous: false,
} as const;
const category: AssetCategory = {
  id: "category-1",
  code: "EQUIPMENT",
  name: "Equipment",
  description: "",
  default_depreciation_method: "straight_line",
  default_useful_life_months: 60,
  default_residual_value_percent: "0.00",
  default_declining_balance_rate: null,
  asset_account_id: null,
  accumulated_depreciation_account_id: null,
  depreciation_expense_account_id: null,
  impairment_loss_account_id: null,
  disposal_gain_account_id: null,
  disposal_loss_account_id: null,
  is_active: true,
  version: 1,
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
};
const envelope: PaginatedEnvelope<AssetCategory> = {
  data: [category],
  meta: { correlation_id: "corr-list", timestamp: "2026-07-22T00:00:00Z", pagination },
};
const line: DepreciationLine = {
  id: "line-1",
  schedule_id: "schedule-1",
  asset_id: "asset-1",
  currency: "USD",
  sequence: 1,
  period_start: "2026-08-01",
  period_end: "2026-08-31",
  opening_net_book_value: "12000.00",
  units_consumed: null,
  depreciation_amount: "183.33",
  accumulated_depreciation: "183.33",
  closing_net_book_value: "11816.67",
  status: "planned",
  journal_entry_id: null,
  posting_job_id: null,
  posted_at: null,
  posting_error_code: "",
  allowed_commands: ["post"],
  denial_reasons: {},
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};

describe("fixed assets service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps the governed collection once and retains pagination", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope);
    await expect(
      fixedAssetsService.listCategories({ search: "plant & machinery", page: 1 })
    ).resolves.toEqual({ items: [category], pagination, correlationId: "corr-list" });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CATEGORIES.LIST}?search=plant+%26+machinery&page=1`
    );
  });

  it("rejects malformed list responses rather than fabricating an empty list", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [],
      meta: { correlation_id: "corr-bad", timestamp: "2026-07-22T00:00:00Z" },
    });
    await expect(fixedAssetsService.listCategories()).rejects.toMatchObject({
      code: "MALFORMED_RESPONSE",
      correlationId: "corr-bad",
    });
  });

  it("propagates stable governed field and domain errors", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(
      new ApiError("Invalid category", 422, {
        error: {
          code: "VALIDATION_ERROR",
          message: "Invalid category",
          correlation_id: "corr-error",
          field_errors: [{ field: "code", code: "duplicate", message: "Code is in use" }],
        },
      })
    );
    await expect(
      fixedAssetsService.createCategory(
        {
          code: "EQUIPMENT",
          name: "Equipment",
          default_depreciation_method: "straight_line",
          default_useful_life_months: 60,
          default_residual_value_percent: "0.00",
        },
        "category-key"
      )
    ).rejects.toMatchObject({
      status: 422,
      code: "VALIDATION_ERROR",
      correlationId: "corr-error",
      fieldErrors: [{ field: "code", code: "duplicate" }],
    });
  });

  it("sends idempotency keys on lifecycle commands", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { id: "asset-1" },
      meta: { correlation_id: "corr-action", timestamp: "2026-07-22T00:00:00Z" },
    });
    await fixedAssetsService.capitalize(
      "asset-1",
      { effective_date: "2026-07-22", expected_version: 2 },
      "capitalize-key"
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.ASSETS.CAPITALIZE("asset-1"),
      { effective_date: "2026-07-22", expected_version: 2 },
      { headers: { "Idempotency-Key": "capitalize-key" } }
    );
  });

  it("routes asset CRUD and lifecycle previews through exact request boundaries", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { id: "asset-1" },
      meta: { correlation_id: "corr-asset", timestamp: "2026-07-22T00:00:00Z" },
    });
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { command: "transfer" },
      meta: { correlation_id: "corr-preview", timestamp: "2026-07-22T00:00:00Z" },
    });
    vi.mocked(apiClient.patch).mockResolvedValue({
      data: { id: "asset-1" },
      meta: { correlation_id: "corr-patch", timestamp: "2026-07-22T00:00:00Z" },
    });
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await fixedAssetsService.dashboard();
    await fixedAssetsService.health();
    await fixedAssetsService.createAsset(
      {
        asset_code: "FA-001",
        asset_name: "Press",
        category_id: "category-1",
        purchase_date: "2026-07-01",
        purchase_cost: "10000.00",
        currency: "USD",
        depreciation_method: "straight_line",
        useful_life_months: 60,
      },
      "asset-create-key"
    );
    await fixedAssetsService.updateAsset("asset-1", { location: "Plant 2", expected_version: 3 });
    await fixedAssetsService.previewTransfer("asset-1", {
      effective_date: "2026-08-01",
      to_location: "Plant 2",
      to_cost_center: "OPS",
    });
    await fixedAssetsService.previewImpair("asset-1", {
      effective_date: "2026-08-01",
      recoverable_amount: "9000.00",
      reason: "Market value decline",
    });
    await fixedAssetsService.previewDispose("asset-1", {
      effective_date: "2026-08-01",
      proceeds: "8500.00",
      reason: "Sold",
    });
    await fixedAssetsService.deleteAsset("asset-1");

    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.DASHBOARD);
    expect(apiClient.get).toHaveBeenNthCalledWith(2, ENDPOINTS.HEALTH);
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.ASSETS.CREATE,
      expect.objectContaining({ asset_code: "FA-001" }),
      { headers: { "Idempotency-Key": "asset-create-key" } }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.ASSETS.UPDATE("asset-1"), {
      location: "Plant 2",
      expected_version: 3,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.ASSETS.PREVIEW_TRANSFER("asset-1"),
      { effective_date: "2026-08-01", to_location: "Plant 2", to_cost_center: "OPS" }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.ASSETS.PREVIEW_IMPAIR("asset-1"), {
      effective_date: "2026-08-01",
      recoverable_amount: "9000.00",
      reason: "Market value decline",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(4, ENDPOINTS.ASSETS.PREVIEW_DISPOSE("asset-1"), {
      effective_date: "2026-08-01",
      proceeds: "8500.00",
      reason: "Sold",
    });
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.ASSETS.DELETE("asset-1"));
  });

  it("adds transition keys to schedule state changes while preserving idempotency headers", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { id: "schedule-1" },
      meta: { correlation_id: "corr-schedule", timestamp: "2026-07-22T00:00:00Z" },
    });

    await fixedAssetsService.activateSchedule("schedule-1", {}, "activate-key");
    await fixedAssetsService.supersedeSchedule(
      "schedule-1",
      { reason: "Replaced useful life" },
      "supersede-key"
    );
    await fixedAssetsService.postDue({ through_date: "2026-08-31" }, "post-due-key");

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.SCHEDULES.ACTIVATE("schedule-1"),
      { transition_key: "activate-key" },
      { headers: { "Idempotency-Key": "activate-key" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.SCHEDULES.SUPERSEDE("schedule-1"),
      { reason: "Replaced useful life", transition_key: "supersede-key" },
      { headers: { "Idempotency-Key": "supersede-key" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.LINES.POST_DUE,
      { through_date: "2026-08-31" },
      { headers: { "Idempotency-Key": "post-due-key" } }
    );
  });

  it("walks every depreciation-line page when exporting a full schedule", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({
        data: [line],
        meta: {
          correlation_id: "corr-lines-1",
          timestamp: "2026-07-22T00:00:00Z",
          pagination: { ...pagination, total_pages: 2, has_next: true },
        },
      })
      .mockResolvedValueOnce({
        data: [{ ...line, id: "line-2", sequence: 2 }],
        meta: {
          correlation_id: "corr-lines-2",
          timestamp: "2026-07-22T00:00:00Z",
          pagination: { ...pagination, page: 2, total_pages: 2, has_previous: true },
        },
      });

    await expect(fixedAssetsService.getAllScheduleLines("schedule-1")).resolves.toEqual([
      line,
      { ...line, id: "line-2", sequence: 2 },
    ]);
    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.LINES.LIST}?schedule_id=schedule-1&page=1&page_size=100`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.LINES.LIST}?schedule_id=schedule-1&page=2&page_size=100`
    );
  });

  it("preserves category, schedule, line, transaction, and strategy endpoint contracts", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope);
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { id: "job-1" },
      meta: { correlation_id: "corr-command", timestamp: "2026-07-22T00:00:00Z" },
    });
    vi.mocked(apiClient.patch).mockResolvedValue({ data: category, meta: envelope.meta });
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await fixedAssetsService.getCategory("category-1");
    await fixedAssetsService.updateCategory("category-1", {
      name: "Machinery",
      expected_version: 2,
    });
    await fixedAssetsService.deactivateCategory("category-1");
    await fixedAssetsService.createSchedule(
      { asset_id: "asset-1", start_date: "2026-08-01" },
      "schedule-key"
    );
    await fixedAssetsService.updateSchedule("schedule-1", {
      end_date: "2031-07-31",
      expected_version: 2,
    });
    await fixedAssetsService.deleteSchedule("schedule-1");
    await fixedAssetsService.calculateSchedule(
      "schedule-1",
      { units_by_period: [{ period_start: "2026-08-01", units_consumed: "42" }] },
      "calculate-key"
    );
    await fixedAssetsService.listLines({ schedule_id: "schedule-1", status: "planned" });
    await fixedAssetsService.getLine("line-1");
    await fixedAssetsService.postLine("line-1", { expected_asset_version: 4 }, "post-line-key");
    await fixedAssetsService.assetTransactions("asset-1", 2);
    await fixedAssetsService.getTransaction("transaction-1");
    await fixedAssetsService.getJob("job-1");
    await fixedAssetsService.listStrategies();

    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.CATEGORIES.DETAIL("category-1"));
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.CATEGORIES.UPDATE("category-1"), {
      name: "Machinery",
      expected_version: 2,
    });
    expect(apiClient.delete).toHaveBeenNthCalledWith(1, ENDPOINTS.CATEGORIES.DELETE("category-1"));
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.SCHEDULES.CREATE,
      { asset_id: "asset-1", start_date: "2026-08-01" },
      { headers: { "Idempotency-Key": "schedule-key" } }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.SCHEDULES.UPDATE("schedule-1"), {
      end_date: "2031-07-31",
      expected_version: 2,
    });
    expect(apiClient.delete).toHaveBeenNthCalledWith(2, ENDPOINTS.SCHEDULES.DELETE("schedule-1"));
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.SCHEDULES.CALCULATE("schedule-1"),
      { units_by_period: [{ period_start: "2026-08-01", units_consumed: "42" }] },
      { headers: { "Idempotency-Key": "calculate-key" } }
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.LINES.LIST}?schedule_id=schedule-1&status=planned`
    );
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.LINES.DETAIL("line-1"));
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.LINES.POST("line-1"),
      { expected_asset_version: 4 },
      { headers: { "Idempotency-Key": "post-line-key" } }
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.ASSETS.TRANSACTIONS("asset-1")}?page=2`
    );
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.TRANSACTIONS.DETAIL("transaction-1"));
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.JOBS.DETAIL("job-1"));
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.STRATEGIES.LIST);
  });

  it("falls back to transport error evidence when governed error details are malformed", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(
      new ApiError(
        "Backend failed",
        500,
        { error: { message: "missing code" } },
        "UPSTREAM",
        "corr-transport"
      )
    );

    await expect(fixedAssetsService.getAsset("asset-1")).rejects.toMatchObject({
      message: "Backend failed",
      status: 500,
      code: "UPSTREAM",
      correlationId: "corr-transport",
      fieldErrors: [],
    });
  });

  it("keeps cache keys tenant-qualified and polls only intermediate jobs", () => {
    expect(fixedAssetQueryKeys.asset("tenant-a", "asset-1")).not.toEqual(
      fixedAssetQueryKeys.asset("tenant-b", "asset-1")
    );
    expect(shouldPollJob({ status: "queued" } as never)).toBe(true);
    expect(shouldPollJob({ status: "running" } as never)).toBe(true);
    expect(shouldPollJob({ status: "retrying" } as never)).toBe(false);
    expect(shouldPollJob({ status: "failed" } as never)).toBe(false);
    expect(createIdempotencyKey("transfer")).toMatch(/^transfer:/u);
  });
});
