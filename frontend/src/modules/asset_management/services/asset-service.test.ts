/* eslint-disable @typescript-eslint/unbound-method */
/* eslint-disable max-lines-per-function -- HTTP-boundary coverage is clearer as cohesive endpoint matrix tests. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type Asset,
  type AssetConfiguration,
  type AssetConfigurationDocument,
  type AssetConfigurationExport,
  type AssetConfigurationPreview,
  type AssetConfigurationVersion,
  type DepreciationEntry,
} from "../contracts";
import { AssetManagementApiError, assetQueryKeys, assetService } from "./asset-service";

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

const asset: Asset = {
  id: "00000000-0000-4000-8000-000000000001",
  asset_code: "LAP-001",
  asset_name: "Design laptop",
  category: "fixed",
  purchase_date: "2026-01-01",
  purchase_cost: "1200.00",
  residual_value: "120.00",
  current_value: "1110.00",
  depreciation_method: "straight_line",
  useful_life_years: 3,
  declining_balance_rate: null,
  location: "Studio",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-02-01T00:00:00Z",
};

const entry: DepreciationEntry = {
  id: "00000000-0000-4000-8000-000000000002",
  asset: asset.id,
  asset_code: asset.asset_code,
  asset_name: asset.asset_name,
  entry_date: "2026-02-01",
  depreciation_amount: "30.00",
  accumulated_depreciation: "90.00",
  book_value: "1110.00",
  created_at: "2026-02-01T00:00:00Z",
};

const configurationDocument: AssetConfigurationDocument = {
  environment: "default",
  enabled: true,
  rollout_roles: [],
  rollout_cohorts: [],
  asset_code_max_length: 50,
  asset_name_max_length: 255,
  location_max_length: 255,
  monetary_max_digits: 15,
  monetary_decimal_places: 2,
  minimum_purchase_cost: "0.01",
  default_residual_value: "0.00",
  default_current_value: "0.00",
  new_asset_active_default: true,
  allowed_categories: ["fixed", "intangible", "current"],
  default_category: "fixed",
  allowed_depreciation_methods: ["straight_line", "declining_balance", "none"],
  default_depreciation_method: "straight_line",
  non_depreciable_categories: ["current"],
  useful_life_min_years: 1,
  useful_life_max_years: 100,
  default_useful_life_years: 5,
  declining_rate_min: "0.0001",
  declining_rate_max: "100.0000",
  percentage_divisor: "100",
  double_declining_factor: "2",
  annual_cap: "1",
  accounting_periods_per_year: 12,
  posting_frequency: "monthly",
  require_chronological_depreciation: true,
  require_useful_life_for_depreciation: true,
  declining_rate_requires_declining_method: true,
  inactive_assets_depreciable: false,
  allow_depreciation_before_purchase: false,
  lock_financial_fields_after_history: true,
  archive_sets_inactive: true,
  archive_confirmation: "asset_code",
  asset_list_page_size: 25,
  asset_list_max_page_size: 100,
  asset_list_default_ordering: "asset_code",
  asset_detail_history_page_size: 12,
  asset_search_fields: ["asset_code", "asset_name", "location"],
  asset_ordering_fields: ["asset_code", "asset_name"],
  tenant_throttle_rate: "240/minute",
  health_interval_seconds: 60,
};

const configuration: AssetConfiguration = {
  id: "00000000-0000-4000-8000-000000000003",
  version: 1,
  document: configurationDocument,
  limits: {},
  updated_at: "2026-02-01T00:00:00Z",
};

const configurationVersion: AssetConfigurationVersion = {
  id: "00000000-0000-4000-8000-000000000004",
  version: 1,
  document: configurationDocument,
  source: "operator",
  correlation_id: "corr-config",
  created_at: "2026-02-01T00:00:00Z",
};

const configurationExport: AssetConfigurationExport = {
  schema_version: "1.0",
  module: "asset_management",
  version: 1,
  document: configurationDocument,
};

const configurationPreview: AssetConfigurationPreview = {
  valid: true,
  current_version: 1,
  changes: { enabled: { from: true, to: false } },
  document: { ...configurationDocument, enabled: false },
};

describe("asset management service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("retains pagination and safely encodes collection filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [asset],
    });

    await expect(
      assetService.listAssets({ search: "plant & studio", is_active: false, page: 2 })
    ).resolves.toEqual({ items: [asset], count: 1, next: null, previous: null });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.ASSETS.LIST}?search=plant+%26+studio&is_active=false&page=2`
    );
  });

  it("rejects malformed records instead of fabricating an empty success", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [{}],
    });
    await expect(assetService.listAssets()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
    });
  });

  it("maps governed field errors and correlation evidence", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(
      new ApiError(
        "Validation failed",
        400,
        { error: { field_errors: { asset_code: ["This code is already in use."] } } },
        "VALIDATION_ERROR",
        "corr-asset-1"
      )
    );

    await expect(assetService.createAsset({} as never)).rejects.toEqual(
      expect.objectContaining({
        status: 400,
        code: "VALIDATION_ERROR",
        correlationId: "corr-asset-1",
        fieldErrors: { asset_code: "This code is already in use." },
      })
    );
  });

  it("uses the command endpoint and validates depreciation results", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(entry);
    await expect(
      assetService.calculateDepreciation(asset.id, { entry_date: entry.entry_date })
    ).resolves.toEqual(entry);
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.ASSETS.CALCULATE_DEPRECIATION(asset.id), {
      entry_date: entry.entry_date,
    });
  });

  it("uses idempotency keys on mutating asset create, update, and archive calls", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000099");
    vi.mocked(apiClient.post).mockResolvedValue(asset);
    vi.mocked(apiClient.patch).mockResolvedValue({ data: asset });
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await assetService.createAsset({
      asset_code: asset.asset_code,
      asset_name: asset.asset_name,
      category: asset.category,
      purchase_date: asset.purchase_date,
      purchase_cost: asset.purchase_cost,
      residual_value: asset.residual_value,
      depreciation_method: asset.depreciation_method,
      useful_life_years: asset.useful_life_years,
      declining_balance_rate: asset.declining_balance_rate,
      location: asset.location,
    });
    await assetService.updateAsset(asset.id, { asset_name: "Updated laptop" });
    await assetService.deleteAsset(asset.id);

    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.ASSETS.CREATE,
      expect.objectContaining({ asset_code: asset.asset_code }),
      { headers: { "Idempotency-Key": "asset-create-00000000-0000-4000-8000-000000000099" } }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.ASSETS.UPDATE(asset.id),
      { asset_name: "Updated laptop" },
      {
        headers: {
          "Idempotency-Key": `asset-update-${asset.id}-00000000-0000-4000-8000-000000000099`,
        },
      }
    );
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.ASSETS.DELETE(asset.id), {
      headers: {
        "Idempotency-Key": `asset-delete-${asset.id}-00000000-0000-4000-8000-000000000099`,
      },
    });
  });

  it("round-trips governed configuration endpoints and validates audit evidence", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: configuration })
      .mockResolvedValueOnce({
        results: [configurationVersion],
        count: 1,
        next: null,
        previous: null,
      })
      .mockResolvedValueOnce(configurationExport);
    vi.mocked(apiClient.patch).mockResolvedValue({ data: configuration });
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(configurationPreview)
      .mockResolvedValueOnce(configuration)
      .mockResolvedValueOnce(configuration)
      .mockResolvedValueOnce(configuration);

    await expect(assetService.getConfiguration()).resolves.toEqual(configuration);
    await expect(assetService.listConfigurationHistory()).resolves.toEqual({
      items: [configurationVersion],
      count: 1,
      next: null,
      previous: null,
    });
    await expect(assetService.exportConfiguration()).resolves.toEqual(configurationExport);
    await expect(assetService.updateConfiguration(configurationDocument)).resolves.toEqual(
      configuration
    );
    await expect(assetService.previewConfiguration(configurationPreview.document)).resolves.toEqual(
      configurationPreview
    );
    await expect(assetService.rollbackConfiguration(1)).resolves.toEqual(configuration);
    await expect(assetService.importConfiguration(configurationExport)).resolves.toEqual(
      configuration
    );

    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.UPDATE, {
      document: configurationDocument,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.CONFIGURATION.PREVIEW, {
      document: configurationPreview.document,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.CONFIGURATION.ROLLBACK, {
      version: 1,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.CONFIGURATION.IMPORT, {
      configuration: configurationExport,
    });
  });

  it("rejects malformed configuration and depreciation payloads at the HTTP boundary", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { ...configuration, document: {} } });
    await expect(assetService.getConfiguration()).rejects.toMatchObject({
      code: "MALFORMED_RESPONSE",
      status: 502,
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [{ ...entry, depreciation_amount: 30 }],
    });
    await expect(assetService.listDepreciationEntries()).rejects.toMatchObject({
      code: "MALFORMED_RESPONSE",
      status: 502,
    });
  });

  it("keeps every cache key tenant-qualified", () => {
    expect(assetQueryKeys.assets("tenant-a")).not.toEqual(assetQueryKeys.assets("tenant-b"));
    expect(assetQueryKeys.asset("tenant-a", asset.id)).not.toEqual(
      assetQueryKeys.asset("tenant-b", asset.id)
    );
    expect(new AssetManagementApiError("Unavailable", 503, "UNAVAILABLE", null)).toMatchObject({
      status: 503,
      code: "UNAVAILABLE",
    });
  });
});
