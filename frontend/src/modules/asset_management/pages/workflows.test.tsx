/* eslint-disable max-lines-per-function -- workflow coverage needs cohesive end-to-end fixtures and assertions. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type {
  Asset,
  AssetConfiguration,
  AssetConfigurationDocument,
  AssetConfigurationExport,
  AssetConfigurationPreview,
  AssetConfigurationVersion,
  DepreciationEntry,
} from "../contracts";
import { ROUTES } from "../contracts";
import { AssetForm } from "../components/AssetForm";
import { AssetManagementApiError, assetService } from "../services/asset-service";
import { AssetDetailPage } from "./AssetDetailPage";
import { AssetConfigurationPage } from "./AssetConfigurationPage";
import { EditAssetPage } from "./EditAssetPage";
import { AssetListPage } from "./AssetListPage";

const asset: Asset = {
  id: "00000000-0000-4000-8000-000000000001",
  asset_code: "LAP-001",
  asset_name: "Design laptop",
  category: "fixed",
  purchase_date: "2026-01-01",
  purchase_cost: "1200.00",
  residual_value: "120.00",
  current_value: "1170.00",
  depreciation_method: "straight_line",
  useful_life_years: 3,
  declining_balance_rate: null,
  location: "Studio",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-02-01T00:00:00Z",
};

const decliningAsset: Asset = {
  ...asset,
  id: "00000000-0000-4000-8000-000000000004",
  asset_code: "INT-001",
  asset_name: "Patent",
  category: "intangible",
  depreciation_method: "declining_balance",
  useful_life_years: 7,
  declining_balance_rate: "15.5",
};

const inconsistentStraightLineAsset: Asset = {
  ...asset,
  id: "00000000-0000-4000-8000-000000000005",
  depreciation_method: "straight_line",
  declining_balance_rate: "12.5",
};

const outOfRangeStraightLineAsset: Asset = {
  ...inconsistentStraightLineAsset,
  id: "00000000-0000-4000-8000-000000000009",
  declining_balance_rate: "150",
};

const inconsistentNoneAsset: Asset = {
  ...asset,
  id: "00000000-0000-4000-8000-000000000006",
  depreciation_method: "none",
  useful_life_years: 4,
  declining_balance_rate: "12.5",
};

const incompleteDecliningAsset: Asset = {
  ...asset,
  id: "00000000-0000-4000-8000-000000000007",
  depreciation_method: "declining_balance",
  useful_life_years: null,
  declining_balance_rate: null,
};

const unparseableCostAsset: Asset = {
  ...asset,
  id: "00000000-0000-4000-8000-000000000008",
  purchase_cost: "not-a-number",
};

const entry: DepreciationEntry = {
  id: "00000000-0000-4000-8000-000000000002",
  asset: asset.id,
  asset_code: asset.asset_code,
  asset_name: asset.asset_name,
  entry_date: "2026-02-01",
  depreciation_amount: "30.00",
  accumulated_depreciation: "30.00",
  book_value: "1170.00",
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
  asset_ordering_fields: [
    "asset_code",
    "asset_name",
    "purchase_date",
    "purchase_cost",
    "current_value",
    "created_at",
  ],
  tenant_throttle_rate: "240/minute",
  health_interval_seconds: 60,
};

const configuration: AssetConfiguration = {
  id: "00000000-0000-4000-8000-000000000003",
  version: 1,
  document: configurationDocument,
  limits: {},
  updated_at: "2026-01-01T00:00:00Z",
};

const configurationVersion: AssetConfigurationVersion = {
  id: "00000000-0000-4000-8000-000000000010",
  version: 1,
  document: configurationDocument,
  source: "operator",
  correlation_id: "corr-asset-config-1",
  created_at: "2026-01-02T00:00:00Z",
};

const configurationExport: AssetConfigurationExport = {
  schema_version: "1.0",
  module: "asset_management",
  version: 1,
  document: configurationDocument,
};

function renderRoute(element: React.ReactElement, path: string, pattern = path) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={element} />
          <Route path="*" element={<p>Navigated away</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("asset management workflows", () => {
  it("shows purposeful empty-register guidance", async () => {
    vi.spyOn(assetService, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(assetService, "listAssets").mockResolvedValue({
      items: [],
      count: 0,
      next: null,
      previous: null,
    });
    renderRoute(<AssetListPage />, ROUTES.ASSETS.LIST);

    expect(await screen.findByText("No assets yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create asset" })).toHaveLength(2);
  });

  it("applies list filters, pagination, and register navigation through query state", async () => {
    vi.spyOn(assetService, "getConfiguration").mockResolvedValue({
      ...configuration,
      document: { ...configurationDocument, asset_list_page_size: 10 },
    });
    const listAssets = vi.spyOn(assetService, "listAssets").mockResolvedValue({
      items: [asset],
      count: 2,
      next: "/api/next",
      previous: "/api/prev",
    });
    renderRoute(
      <AssetListPage />,
      `${ROUTES.ASSETS.LIST}?page=0&search=lap&category=fixed&is_active=false&purchase_date_after=2026-01-01&purchase_date_before=2026-12-31&ordering=-purchase_date`,
      ROUTES.ASSETS.LIST
    );

    expect(await screen.findByRole("button", { name: asset.asset_code })).toBeInTheDocument();
    await waitFor(() =>
      expect(listAssets).toHaveBeenLastCalledWith(
        expect.objectContaining({
          category: "fixed",
          is_active: false,
          ordering: "-purchase_date",
          page: 1,
          page_size: 10,
          purchase_date_after: "2026-01-01",
          purchase_date_before: "2026-12-31",
          search: "lap",
        })
      )
    );

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(listAssets).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    );

    fireEvent.change(screen.getByLabelText("Search assets"), { target: { value: "  Studio  " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(listAssets).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 1, search: "Studio" })
      )
    );

    fireEvent.click(screen.getByRole("button", { name: asset.asset_code }));
    expect(await screen.findByText("Navigated away")).toBeInTheDocument();
  });

  it("previews, saves, exports, imports, and rolls back versioned configuration", async () => {
    const preview: AssetConfigurationPreview = {
      valid: true,
      current_version: 1,
      changes: { asset_list_page_size: { from: 25, to: 30 } },
      document: { ...configurationDocument, asset_list_page_size: 30 },
    };
    vi.spyOn(assetService, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(assetService, "listConfigurationHistory").mockResolvedValue({
      items: [configurationVersion],
      count: 1,
      next: null,
      previous: null,
    });
    const previewConfiguration = vi
      .spyOn(assetService, "previewConfiguration")
      .mockResolvedValue(preview);
    const updateConfiguration = vi.spyOn(assetService, "updateConfiguration").mockResolvedValue({
      ...configuration,
      version: 2,
      document: preview.document,
    });
    const exportConfiguration = vi
      .spyOn(assetService, "exportConfiguration")
      .mockResolvedValue(configurationExport);
    const importConfiguration = vi
      .spyOn(assetService, "importConfiguration")
      .mockResolvedValue(configuration);
    const rollbackConfiguration = vi
      .spyOn(assetService, "rollbackConfiguration")
      .mockResolvedValue(configuration);
    renderRoute(<AssetConfigurationPage />, ROUTES.ASSETS.CONFIGURATION);

    const documentEditor = await screen.findByLabelText("Configuration document");
    fireEvent.change(documentEditor, {
      target: { value: JSON.stringify(preview.document, null, 2) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(previewConfiguration).toHaveBeenCalledWith(preview.document));
    expect(await screen.findByText("asset_list_page_size")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save version" }));
    await waitFor(() => expect(updateConfiguration).toHaveBeenCalledWith(preview.document));

    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(exportConfiguration).toHaveBeenCalled());
    const importEditor = screen.getByLabelText("Configuration import document");
    await waitFor(() =>
      expect(importEditor).toHaveValue(JSON.stringify(configurationExport, null, 2))
    );
    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() => expect(importConfiguration).toHaveBeenCalledWith(configurationExport));

    fireEvent.click(screen.getByRole("button", { name: "Roll back" }));
    await waitFor(() => expect(rollbackConfiguration).toHaveBeenCalledWith(1));
  });

  it("fails closed when configuration JSON is malformed", async () => {
    vi.spyOn(assetService, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(assetService, "listConfigurationHistory").mockResolvedValue({
      items: [],
      count: 0,
      next: null,
      previous: null,
    });
    const previewConfiguration = vi.spyOn(assetService, "previewConfiguration");
    renderRoute(<AssetConfigurationPage />, ROUTES.ASSETS.CONFIGURATION);

    fireEvent.change(await screen.findByLabelText("Configuration document"), {
      target: { value: "{ invalid" },
    });

    expect(screen.getByRole("alert")).toHaveTextContent(/JSON/u);
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
    expect(previewConfiguration).not.toHaveBeenCalled();
  });
});

describe("asset form edit governance", () => {
  it("projects required native constraints for asset create forms", () => {
    const { container } = render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    expect(container.querySelector("form")?.noValidate).toBe(false);
    expect(screen.getByLabelText("Asset code")).toBeRequired();
    expect(screen.getByLabelText("Asset name")).toBeRequired();
    expect(screen.getByLabelText("Category")).toBeRequired();
    expect(screen.getByLabelText("Purchase date")).toBeRequired();
    expect(screen.getByLabelText("Purchase cost")).toBeRequired();
    expect(screen.getByLabelText("Residual value")).toBeRequired();
    expect(screen.getByLabelText("Depreciation method")).toBeRequired();
    expect(screen.getByLabelText("Useful life (years)")).toBeRequired();
  });

  it("submits only changed fields when editing a financially locked asset", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={asset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    expect(screen.getByRole("button", { name: "No changes" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Asset name"), {
      target: { value: "Design laptop – team A" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(submit).toHaveBeenCalledWith({ asset_name: "Design laptop – team A" });
  });

  it("uppercases asset codes as the operator types", () => {
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "lap-009" } });

    expect(screen.getByLabelText("Asset code")).toHaveValue("LAP-009");
  });
});

describe("asset form edit dirty checks", () => {
  it("keeps decimal-equivalent financial edits as no-op updates", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={asset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "1200" } });

    expect(screen.getByRole("button", { name: "No changes" })).toBeDisabled();
    expect(submit).not.toHaveBeenCalled();
  });

  it("keeps residual and declining-rate decimal equivalents as no-op updates", () => {
    const submit = vi.fn();
    const { container } = render(
      <AssetForm
        asset={decliningAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Residual value"), { target: { value: "120" } });
    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "15.50" },
    });
    fireEvent.submit(container.querySelector("form")!);

    expect(screen.getByRole("button", { name: "No changes" })).toBeDisabled();
    expect(submit).not.toHaveBeenCalled();
  });

  it("does not submit an unchanged edit even when the form is submitted directly", () => {
    const submit = vi.fn();
    const { container } = render(
      <AssetForm
        asset={asset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.submit(container.querySelector("form")!);

    expect(submit).not.toHaveBeenCalled();
  });

  it("submits decimal fields when finite values are materially changed", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={asset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "1201.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(submit).toHaveBeenCalledWith({ purchase_cost: "1201.00" });
  });

  it("marks unparseable decimal edits as dirty before validation blocks submission", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={unparseableCostAsset}
        configuration={{ ...configurationDocument, minimum_purchase_cost: "not-a-number" }}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "also-invalid" } });

    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
    expect(submit).not.toHaveBeenCalled();
  });
});

describe("asset form legacy normalization", () => {
  it("normalizes legacy non-depreciating assets when saving unrelated edits", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={inconsistentNoneAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Archived laptop" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(submit).toHaveBeenCalledWith({
      asset_name: "Archived laptop",
      useful_life_years: null,
      declining_balance_rate: null,
    });
  });

  it("normalizes legacy straight-line assets with stray declining rates", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={inconsistentStraightLineAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Clean laptop" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(submit).toHaveBeenCalledWith({
      asset_name: "Clean laptop",
      declining_balance_rate: null,
    });
  });
});

describe("asset form default rendering", () => {
  it("renders create defaults from configuration and the current date", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-15T11:30:00Z"));

    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    expect(screen.getByLabelText("Asset code")).toHaveValue("");
    expect(screen.getByLabelText("Asset name")).toHaveValue("");
    expect(screen.getByLabelText("Category")).toHaveValue(configurationDocument.default_category);
    expect(screen.getByLabelText("Purchase date")).toHaveValue("2026-04-15");
    expect(screen.getByLabelText("Purchase cost")).toHaveValue("");
    expect(screen.getByLabelText("Residual value")).toHaveValue(
      configurationDocument.default_residual_value
    );
    expect(screen.getByLabelText("Depreciation method")).toHaveValue(
      configurationDocument.default_depreciation_method
    );
    expect(screen.getByLabelText("Useful life (years)")).toHaveValue(5);
    expect(screen.getByLabelText("Location")).toHaveValue("");
  });

  it("renders edit values from the asset instead of configuration defaults", () => {
    render(
      <AssetForm
        asset={decliningAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    expect(screen.getByLabelText("Asset code")).toHaveValue("INT-001");
    expect(screen.getByLabelText("Category")).toHaveValue("intangible");
    expect(screen.getByLabelText("Depreciation method")).toHaveValue("declining_balance");
    expect(screen.getByLabelText("Useful life (years)")).toHaveValue(7);
    expect(screen.getByLabelText("Annual declining balance rate (%)")).toHaveValue("15.5");
  });

  it("renders configured useful life and blank rate for incomplete declining-balance assets", () => {
    render(
      <AssetForm
        asset={incompleteDecliningAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    expect(screen.getByLabelText("Useful life (years)")).toHaveValue(
      configurationDocument.default_useful_life_years
    );
    expect(screen.getByLabelText("Annual declining balance rate (%)")).toHaveValue("");
  });

  it("enforces the non-depreciating current-asset rule in the form", () => {
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "current" } });

    expect(screen.getByLabelText("Depreciation method")).toBeDisabled();
    expect(screen.getByText(/Current assets are not depreciated/u)).toBeInTheDocument();
    expect(screen.queryByLabelText("Useful life (years)")).not.toBeInTheDocument();
  });

  it("preserves depreciation settings when moving between depreciable categories", () => {
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });
    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "12.5" },
    });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "intangible" } });

    expect(screen.getByLabelText("Category")).toHaveValue("intangible");
    expect(screen.getByLabelText("Depreciation method")).toHaveValue("declining_balance");
    expect(screen.getByLabelText("Annual declining balance rate (%)")).toHaveValue("12.5");
  });
});

describe("asset form validation governance", () => {
  it("normalizes create payloads and blocks invalid identity fields before submit", () => {
    const submit = vi.fn();
    const strictConfiguration = {
      ...configurationDocument,
      asset_code_max_length: 5,
      asset_name_max_length: 12,
      location_max_length: 4,
    };
    render(
      <AssetForm
        configuration={strictConfiguration}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "bad code!" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Purchase date"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "warehouse" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(screen.getByText("Asset code cannot exceed 5 characters.")).toBeInTheDocument();
    expect(screen.getByText("Asset name is required.")).toBeInTheDocument();
    expect(screen.getByText("Purchase date is required.")).toBeInTheDocument();
    expect(screen.getByText("Location cannot exceed 4 characters.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "lap-2" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "  Laptop  " } });
    fireEvent.change(screen.getByLabelText("Purchase date"), { target: { value: "2026-03-01" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100.00" } });
    fireEvent.change(screen.getByLabelText("Residual value"), { target: { value: "10.00" } });
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: " HQ " } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_code: "LAP-2",
        asset_name: "Laptop",
        location: "HQ",
      })
    );
  });

  it("checks asset code length after trimming before applying the character policy", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={{ ...configurationDocument, asset_code_max_length: 5 }}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: " lap-2 " } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Trimmed code" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(screen.queryByText("Asset code cannot exceed 5 characters.")).not.toBeInTheDocument();
    expect(
      screen.getByText("Use letters, numbers, periods, underscores, or hyphens.")
    ).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("accepts names that are exactly the configured trimmed length", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={{ ...configurationDocument, asset_name_max_length: 6 }}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "TRIM-1" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: " Laptop " } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_name: "Laptop",
      })
    );
    expect(screen.queryByText("Asset name cannot exceed 6 characters.")).not.toBeInTheDocument();
  });
});

describe("asset form field validation", () => {
  it("validates character policy, name limits, and negative residual values", () => {
    const submit = vi.fn();
    const strictConfiguration = {
      ...configurationDocument,
      asset_name_max_length: 6,
    };
    render(
      <AssetForm
        configuration={strictConfiguration}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "BAD CODE!" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Long name" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Residual value"), { target: { value: "-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(
      screen.getByText("Use letters, numbers, periods, underscores, or hyphens.")
    ).toBeInTheDocument();
    expect(screen.getByText("Asset name cannot exceed 6 characters.")).toBeInTheDocument();
    expect(screen.getByText("Enter a non-negative amount.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("rejects asset codes containing invalid prefixes even when they end with valid characters", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "BAD CODE" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Laptop" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(
      screen.getByText("Use letters, numbers, periods, underscores, or hyphens.")
    ).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("treats whitespace-only required values as blank", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "   " } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(screen.getByText("Asset code is required.")).toBeInTheDocument();
    expect(screen.getByText("Asset name is required.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });
});

describe("asset form money validation", () => {
  it("enforces money and declining-balance policy bounds", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "LAP-002" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Laptop" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Residual value"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });
    fireEvent.change(screen.getByLabelText("Useful life (years)"), { target: { value: "101" } });
    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "101" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(screen.getByText("Enter at least 0.01.")).toBeInTheDocument();
    expect(screen.getByText("Residual value cannot exceed purchase cost.")).toBeInTheDocument();
    expect(screen.getByText("Useful life must be 1-100 years.")).toBeInTheDocument();
    expect(screen.getByText("Enter an annual rate from 0.0001 to 100.0000.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });
});

describe("asset form depreciation validation", () => {
  it("rejects blank and below-minimum useful life values using configured lower bounds", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={{ ...configurationDocument, useful_life_min_years: 2 }}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "LIFE-1" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Life asset" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Useful life (years)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(screen.getByText("Useful life must be 2-100 years.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Useful life (years)"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(screen.getByText("Useful life must be 2-100 years.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("rejects non-numeric and below-minimum declining-balance rates", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "RATE-1" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Rate asset" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });
    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "not-a-rate" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(screen.getByText("Enter an annual rate from 0.0001 to 100.0000.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "0" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(screen.getByText("Enter an annual rate from 0.0001 to 100.0000.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });
});

describe("asset form legacy straight-line depreciation validation", () => {
  it("allows straight-line assets even when legacy data carries a stray declining rate", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={inconsistentStraightLineAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Straight asset" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(submit).toHaveBeenCalledWith({
      asset_name: "Straight asset",
      declining_balance_rate: null,
    });
    expect(
      screen.queryByText("Enter an annual rate from 0.0001 to 100.0000.")
    ).not.toBeInTheDocument();
  });

  it("does not validate legacy declining rates while the asset remains straight-line", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={outOfRangeStraightLineAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset name"), {
      target: { value: "Straight asset cleaned" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(
      screen.queryByText("Enter an annual rate from 0.0001 to 100.0000.")
    ).not.toBeInTheDocument();
    expect(submit).toHaveBeenCalledWith({
      asset_name: "Straight asset cleaned",
      declining_balance_rate: null,
    });
  });
});

describe("asset form money boundary acceptance", () => {
  it("accepts configured depreciation boundary values", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "BOUND-1" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Boundary asset" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });
    fireEvent.change(screen.getByLabelText("Useful life (years)"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "0.0001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(submit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        useful_life_years: 1,
        declining_balance_rate: "0.0001",
      })
    );

    fireEvent.change(screen.getByLabelText("Useful life (years)"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "100.0000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(submit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        useful_life_years: 100,
        declining_balance_rate: "100.0000",
      })
    );
  });

  it("accepts minimum purchase cost and residual equal to cost", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "MIN-1" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Minimum" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "0.01" } });
    fireEvent.change(screen.getByLabelText("Residual value"), { target: { value: "0.01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        purchase_cost: "0.01",
        residual_value: "0.01",
      })
    );
  });
});

describe("asset form depreciation payloads", () => {
  it("accepts declining-balance depreciation with a blank optional rate", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "DBL-1" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Declining blank" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        depreciation_method: "declining_balance",
        declining_balance_rate: null,
      })
    );
  });

  it("submits none and declining-balance depreciation payload boundaries", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "NONE-1" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "No depreciation" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Depreciation method"), { target: { value: "none" } });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(submit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        depreciation_method: "none",
        useful_life_years: null,
        declining_balance_rate: null,
      })
    );

    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });
    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "12.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(submit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        depreciation_method: "declining_balance",
        useful_life_years: configurationDocument.default_useful_life_years,
        declining_balance_rate: "12.5",
      })
    );
  });
});

describe("asset form depreciation transitions", () => {
  it("clears declining-balance rate when switching back to straight-line depreciation", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Asset code"), { target: { value: "DEP-1" } });
    fireEvent.change(screen.getByLabelText("Asset name"), { target: { value: "Depreciable" } });
    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });
    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "12.5" },
    });
    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "straight_line" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create asset" }));

    expect(screen.queryByLabelText("Annual declining balance rate (%)")).not.toBeInTheDocument();
    expect(submit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        depreciation_method: "straight_line",
        declining_balance_rate: null,
      })
    );
  });

  it("clears and restores depreciation controls across select transitions", () => {
    render(
      <AssetForm
        asset={decliningAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "straight_line" },
    });
    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });

    expect(screen.getByLabelText("Annual declining balance rate (%)")).toHaveValue("");

    fireEvent.change(screen.getByLabelText("Depreciation method"), { target: { value: "none" } });
    expect(screen.queryByLabelText("Useful life (years)")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });
    expect(screen.getByLabelText("Useful life (years)")).toHaveValue(
      configurationDocument.default_useful_life_years
    );
    expect(screen.getByLabelText("Annual declining balance rate (%)")).toHaveValue("");
  });

  it("treats a blank declining-balance rate and zero rate as materially different edits", () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={incompleteDecliningAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    fireEvent.change(screen.getByLabelText("Annual declining balance rate (%)"), {
      target: { value: "0" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(screen.getByText("Enter an annual rate from 0.0001 to 100.0000.")).toBeInTheDocument();
    expect(submit).not.toHaveBeenCalled();
  });

  it("retains legacy declining rates when explicitly switching to declining balance", () => {
    render(
      <AssetForm
        asset={inconsistentStraightLineAsset}
        configuration={configurationDocument}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    fireEvent.change(screen.getByLabelText("Depreciation method"), {
      target: { value: "declining_balance" },
    });

    expect(screen.getByLabelText("Annual declining balance rate (%)")).toHaveValue("12.5");
  });
});

describe("asset form server states", () => {
  it("surfaces mapped server field errors without replacing the form", () => {
    render(
      <AssetForm
        configuration={configurationDocument}
        pending={false}
        error={
          new AssetManagementApiError("Validation failed", 400, "VALIDATION_ERROR", "corr-asset", {
            asset_code: "This code is already in use.",
          })
        }
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    );

    expect(screen.getByText("This code is already in use.")).toBeInTheDocument();
    expect(screen.queryByText("We could not complete this request")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create asset" })).toBeEnabled();
  });

  it("shows unmapped server errors, pending state, cancel wiring, and decimal-equivalent no-op edits", () => {
    const cancel = vi.fn();
    const submit = vi.fn();
    render(
      <AssetForm
        asset={asset}
        configuration={configurationDocument}
        pending
        error={new AssetManagementApiError("Service unavailable", 503, "UPSTREAM_DOWN", "corr-503")}
        onCancel={cancel}
        onSubmit={submit}
      />
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Service unavailable");
    expect(screen.getByText("Correlation ID: corr-503")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(cancel).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText("Purchase cost"), { target: { value: "1200" } });
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(submit).not.toHaveBeenCalled();
  });
});

describe("asset detail workflows", () => {
  it("runs depreciation as an explicit persisted command", async () => {
    vi.spyOn(assetService, "getAsset").mockResolvedValue(asset);
    vi.spyOn(assetService, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(assetService, "listDepreciationEntries").mockResolvedValue({
      items: [],
      count: 0,
      next: null,
      previous: null,
    });
    const calculate = vi.spyOn(assetService, "calculateDepreciation").mockResolvedValue(entry);
    renderRoute(<AssetDetailPage />, ROUTES.ASSETS.DETAIL(asset.id), ROUTES.ASSETS.DETAIL_PATTERN);

    const calculateButtons = await screen.findAllByRole("button", {
      name: "Calculate depreciation",
    });
    const calculateButton = calculateButtons[0];
    if (!calculateButton) throw new Error("The depreciation command was not rendered.");
    fireEvent.click(calculateButton);
    const entryDate = screen.getByLabelText("Entry date");
    fireEvent.change(entryDate, { target: { value: entry.entry_date } });
    fireEvent.click(screen.getByRole("button", { name: "Calculate and record" }));

    await waitFor(() =>
      expect(calculate).toHaveBeenCalledWith(asset.id, { entry_date: entry.entry_date })
    );
  });

  it.each([
    [
      "detail",
      <AssetDetailPage />,
      ROUTES.ASSETS.DETAIL_PATTERN,
      "/asset-management/assets/not-a-uuid",
    ],
    [
      "edit",
      <EditAssetPage />,
      ROUTES.ASSETS.EDIT_PATTERN,
      "/asset-management/assets/not-a-uuid/edit",
    ],
  ] as const)(
    "renders asset not found for invalid %s route IDs",
    async (_name, page, pattern, path) => {
      const getAsset = vi.spyOn(assetService, "getAsset");
      vi.spyOn(assetService, "getConfiguration").mockResolvedValue(configuration);

      renderRoute(page, path, pattern);

      expect(await screen.findByText("Asset not found")).toBeInTheDocument();
      expect(getAsset).not.toHaveBeenCalled();
    }
  );

  it("requires the configured archive confirmation before deleting an asset", async () => {
    vi.spyOn(assetService, "getAsset").mockResolvedValue(asset);
    vi.spyOn(assetService, "getConfiguration").mockResolvedValue({
      ...configuration,
      document: { ...configurationDocument, archive_confirmation: "asset_name" },
    });
    vi.spyOn(assetService, "listDepreciationEntries").mockResolvedValue({
      items: [entry],
      count: 1,
      next: null,
      previous: null,
    });
    const deleteAsset = vi.spyOn(assetService, "deleteAsset").mockResolvedValue();
    renderRoute(<AssetDetailPage />, ROUTES.ASSETS.DETAIL(asset.id), ROUTES.ASSETS.DETAIL_PATTERN);

    fireEvent.click(await screen.findByRole("button", { name: "Archive" }));
    expect(screen.getByRole("button", { name: "Archive asset" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(`Type ${asset.asset_name} to confirm`), {
      target: { value: asset.asset_name },
    });
    fireEvent.click(screen.getByRole("button", { name: "Archive asset" }));

    await waitFor(() => expect(deleteAsset).toHaveBeenCalledWith(asset.id));
    expect(await screen.findByText("Navigated away")).toBeInTheDocument();
  });

  it("blocks depreciation when configuration marks the category non-depreciable", async () => {
    vi.spyOn(assetService, "getAsset").mockResolvedValue({ ...asset, category: "current" });
    vi.spyOn(assetService, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(assetService, "listDepreciationEntries").mockResolvedValue({
      items: [],
      count: 0,
      next: null,
      previous: null,
    });
    const calculate = vi.spyOn(assetService, "calculateDepreciation");
    renderRoute(<AssetDetailPage />, ROUTES.ASSETS.DETAIL(asset.id), ROUTES.ASSETS.DETAIL_PATTERN);

    const calculateButton = (
      await screen.findAllByRole("button", {
        name: "Calculate depreciation",
      })
    )[0];
    if (!calculateButton) throw new Error("Expected depreciation button.");
    expect(calculateButton).toBeDisabled();
    expect(screen.getAllByText("Current assets are configured as non-depreciable.")).toHaveLength(
      2
    );
    expect(calculate).not.toHaveBeenCalled();
  });
});
