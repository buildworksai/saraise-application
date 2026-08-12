/* eslint-disable max-lines-per-function -- component workflows are intentionally exercised end to end. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AssetLifecycleDialog } from "./AssetLifecycleDialog";
import { AssetForm, CategoryForm } from "./AssetForms";
import { ScheduleForm } from "./ScheduleForm";
import type { AssetCategory, FixedAsset, LifecyclePreview } from "../contracts";

const hoisted = vi.hoisted(() => {
  class TestFixedAssetsApiError extends Error {
    constructor(
      message: string,
      readonly status: number,
      readonly code: string,
      readonly correlationId: string | null,
      readonly fieldErrors: readonly { readonly field: string; readonly message: string }[] = []
    ) {
      super(message);
    }

    fieldError(field: string): string | undefined {
      return this.fieldErrors.find((item) => item.field === field)?.message;
    }
  }

  return {
    FixedAssetsApiError: TestFixedAssetsApiError,
    service: {
      previewCapitalize: vi.fn(),
      previewTransfer: vi.fn(),
      previewImpair: vi.fn(),
      previewDispose: vi.fn(),
      capitalize: vi.fn(),
      transfer: vi.fn(),
      impair: vi.fn(),
      dispose: vi.fn(),
    },
  };
});

vi.mock("../services/fixed-assets-service", () => ({
  FixedAssetsApiError: hoisted.FixedAssetsApiError,
  fixedAssetsService: hoisted.service,
}));

const { service, FixedAssetsApiError: TestFixedAssetsApiError } = hoisted;

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const activeCategory: AssetCategory = {
  id: "category-active",
  code: "EQUIP",
  name: "Equipment",
  description: "",
  default_depreciation_method: "straight_line",
  default_useful_life_months: 60,
  default_residual_value_percent: "0.00",
  default_declining_balance_rate: null,
  asset_account_id: "asset-account",
  accumulated_depreciation_account_id: "accum-dep-account",
  depreciation_expense_account_id: "dep-exp-account",
  impairment_loss_account_id: null,
  disposal_gain_account_id: null,
  disposal_loss_account_id: null,
  is_active: true,
  version: 1,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};

const inactiveCategory: AssetCategory = {
  ...activeCategory,
  id: "category-inactive",
  code: "OLD",
  name: "Inactive",
  is_active: false,
};

const asset: FixedAsset = {
  id: "asset-1",
  asset_code: "ASSET-1",
  asset_name: "Forklift",
  description: "Warehouse lift",
  category: { id: activeCategory.id, code: activeCategory.code, name: activeCategory.name },
  purchase_date: "2026-07-01",
  purchase_cost: "12000.00",
  currency: "USD",
  residual_value: "1000.00",
  capitalization_date: null,
  depreciation_start_date: null,
  depreciation_method: "straight_line",
  useful_life_months: 60,
  declining_balance_rate: null,
  expected_total_units: null,
  accumulated_depreciation: "0.00",
  accumulated_impairment: "0.00",
  net_book_value: "12000.00",
  location: "Dock A",
  cost_center: "OPS",
  status: "draft",
  disposal_date: null,
  disposal_proceeds: null,
  disposal_gain_loss: null,
  next_depreciation_date: null,
  as_of: "2026-07-28",
  version: 3,
  allowed_commands: ["edit", "delete", "capitalize"],
  denial_reasons: {},
  active_schedule: null,
  balance_reconciliation: {
    purchase_cost: "12000.00",
    accumulated_depreciation: "0.00",
    accumulated_impairment: "0.00",
    calculated_net_book_value: "12000.00",
    reconciled: true,
  },
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};

const preview: LifecyclePreview = {
  command: "transfer",
  asset_version: 3,
  as_of: "2026-08-01",
  opening_net_book_value: "12000.00",
  closing_net_book_value: "12000.00",
  currency: "USD",
  warnings: [{ code: "LOCATION_CHANGE", message: "Location will change." }],
  blockers: [],
  journal_effect: { status: "not_required", entries: [] },
  schedule_effect: { status: "unchanged", description: "No depreciation schedule changes." },
};

describe("AssetForm and CategoryForm", () => {
  beforeEach(() => vi.clearAllMocks());

  it("normalizes asset fields, shows method dependencies, and preserves optimistic version on edit", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    render(
      <AssetForm
        asset={asset}
        categories={[activeCategory, inactiveCategory]}
        pending={false}
        error={
          new TestFixedAssetsApiError("Invalid", 422, "VALIDATION_ERROR", "corr-form", [
            { field: "asset_name", message: "Name is already used." },
          ])
        }
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    expect(screen.getByText("Name is already used.")).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /OLD/u })).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("Asset code"));
    await user.type(screen.getByLabelText("Asset code"), "asset-2");
    await user.clear(screen.getByLabelText("Currency (ISO 4217)"));
    await user.type(screen.getByLabelText("Currency (ISO 4217)"), "eur");
    await user.selectOptions(screen.getByLabelText("Depreciation method"), "declining_balance");
    await user.type(screen.getByLabelText("Annual declining balance rate"), "20.00");
    await user.click(screen.getByRole("button", { name: "Save asset" }));

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_code: "ASSET-2",
        currency: "EUR",
        declining_balance_rate: "20.00",
        expected_version: 3,
      })
    );
  });

  it("requires explicit discard before cancelling dirty asset forms", async () => {
    const user = userEvent.setup();
    const cancel = vi.fn();
    render(
      <AssetForm
        categories={[activeCategory]}
        pending={false}
        error={null}
        onCancel={cancel}
        onSubmit={vi.fn()}
      />
    );

    await user.type(screen.getByLabelText("Asset code"), "asset-3");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(cancel).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("keeps category codes immutable on edit and clears blank account mappings to null", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    render(
      <CategoryForm
        category={activeCategory}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    expect(screen.getByLabelText("Category code")).toBeDisabled();
    await user.clear(screen.getByLabelText("Category name"));
    await user.type(screen.getByLabelText("Category name"), "Plant equipment");
    await user.selectOptions(screen.getByLabelText("Default method"), "declining_balance");
    await user.type(screen.getByLabelText("Default annual rate"), "25.00");
    await user.clear(screen.getByLabelText("asset account id"));
    await user.click(screen.getByRole("button", { name: "Save category" }));

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        code: "EQUIP",
        name: "Plant equipment",
        default_depreciation_method: "declining_balance",
        default_declining_balance_rate: "25.00",
        asset_account_id: null,
      })
    );
  });
});

describe("ScheduleForm", () => {
  beforeEach(() => vi.clearAllMocks());

  it("creates units-of-production draft assumptions and gates submit until an asset is selected", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    render(
      <ScheduleForm
        assets={[asset]}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    expect(screen.getByRole("button", { name: "Create draft schedule" })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Asset"), "asset-1");
    await user.selectOptions(screen.getByLabelText("Method"), "units_of_production");
    await user.type(screen.getByLabelText("Start date (optional override)"), "2026-08-01");
    await user.type(screen.getByLabelText("End date (optional override)"), "2026-12-31");
    await user.type(screen.getByLabelText("Residual value override"), "1000.00");
    await user.type(screen.getByLabelText("Expected total units"), "25000.0000");
    await user.click(screen.getByRole("button", { name: "Create draft schedule" }));

    expect(submit).toHaveBeenCalledWith({
      asset_id: "asset-1",
      method: "units_of_production",
      start_date: "2026-08-01",
      end_date: "2026-12-31",
      residual_value: "1000.00",
      declining_balance_rate: undefined,
      expected_total_units: "25000.0000",
    });
  });

  it("preserves immutable asset choice and optimistic version when editing schedule assumptions", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    render(
      <ScheduleForm
        schedule={{
          id: "schedule-1",
          asset_id: "asset-1",
          asset: { id: "asset-1", asset_code: "ASSET-1", asset_name: "Forklift", currency: "USD" },
          schedule_number: "DEP-2026-001",
          revision: 2,
          method: "declining_balance",
          frequency: "monthly",
          start_date: "2026-08-01",
          end_date: "2031-07-31",
          cost_basis: "12000.00",
          residual_value: "1000.00",
          depreciable_amount: "11000.00",
          declining_balance_rate: "20.00",
          expected_total_units: null,
          total_planned_depreciation: "11000.00",
          status: "draft",
          version: 5,
          calculated_at: null,
          activated_at: null,
          completed_at: null,
          superseded_by: null,
          reconciliation: { line_total: "0.00", difference: "11000.00", reconciled: false },
          allowed_commands: ["update"],
          denial_reasons: {},
          created_at: "2026-07-28T00:00:00Z",
          updated_at: "2026-07-28T01:00:00Z",
        }}
        assets={[asset]}
        pending={false}
        error={
          new TestFixedAssetsApiError("Invalid", 422, "VALIDATION_ERROR", "corr-schedule", [
            { field: "start_date", message: "Start date overlaps an active schedule." },
          ])
        }
        onCancel={vi.fn()}
        onSubmit={submit}
      />
    );

    expect(screen.getByText("Start date overlaps an active schedule.")).toBeInTheDocument();
    expect(screen.getByLabelText("Asset")).toBeDisabled();
    await user.clear(screen.getByLabelText("Annual declining rate"));
    await user.type(screen.getByLabelText("Annual declining rate"), "25.00");
    await user.click(screen.getByRole("button", { name: "Save assumptions" }));

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: "asset-1",
        method: "declining_balance",
        declining_balance_rate: "25.00",
        expected_version: 5,
      })
    );
  });

  it("requires explicit discard before leaving dirty schedule forms", async () => {
    const user = userEvent.setup();
    const cancel = vi.fn();
    render(
      <ScheduleForm
        assets={[asset]}
        defaultAssetId="asset-1"
        pending={false}
        error={null}
        onCancel={cancel}
        onSubmit={vi.fn()}
      />
    );

    await user.type(screen.getByLabelText("Residual value override"), "500.00");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(cancel).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(cancel).toHaveBeenCalledOnce();
  });
});

describe("AssetLifecycleDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    service.previewTransfer.mockResolvedValue(preview);
    service.transfer.mockResolvedValue({ ...asset, location: "Dock B", version: 4 });
    service.previewDispose.mockResolvedValue({
      ...preview,
      command: "dispose",
      blockers: [{ code: "OPEN_SCHEDULE", message: "Active schedule must be closed first." }],
    });
  });

  it("previews transfer financial effects before executing the server command", async () => {
    const user = userEvent.setup();
    const complete = vi.fn();
    const openChange = vi.fn();
    renderWithQuery(
      <AssetLifecycleDialog
        asset={asset}
        command="transfer"
        open
        onOpenChange={openChange}
        onComplete={complete}
      />
    );

    await user.type(screen.getByLabelText("Effective date"), "2026-08-01");
    await user.clear(screen.getByLabelText("New location"));
    await user.type(screen.getByLabelText("New location"), "Dock B");
    await user.clear(screen.getByLabelText("New cost center"));
    await user.type(screen.getByLabelText("New cost center"), "MFG");
    await user.click(screen.getByRole("button", { name: "Preview financial effect" }));

    await waitFor(() =>
      expect(service.previewTransfer).toHaveBeenCalledWith("asset-1", {
        effective_date: "2026-08-01",
        to_location: "Dock B",
        to_cost_center: "MFG",
      })
    );
    expect(await screen.findByText("No depreciation schedule changes.")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("LOCATION_CHANGE");

    await user.click(screen.getByRole("button", { name: "Confirm transfer" }));
    await waitFor(() =>
      expect(service.transfer).toHaveBeenCalledWith(
        "asset-1",
        { effective_date: "2026-08-01", to_location: "Dock B", to_cost_center: "MFG" },
        "transfer:asset-1:2026-08-01"
      )
    );
    expect(complete).toHaveBeenCalledWith(expect.objectContaining({ location: "Dock B" }));
    expect(openChange).toHaveBeenCalledWith(false);
  });

  it("keeps destructive lifecycle commands disabled when preview blockers exist", async () => {
    const user = userEvent.setup();
    renderWithQuery(
      <AssetLifecycleDialog
        asset={asset}
        command="dispose"
        open
        onOpenChange={vi.fn()}
        onComplete={vi.fn()}
      />
    );

    await user.type(screen.getByLabelText("Effective date"), "2026-08-01");
    await user.type(screen.getByLabelText("Disposal proceeds"), "500.00");
    await user.type(screen.getByLabelText("Reason"), "Replacement");
    await user.click(screen.getByRole("button", { name: "Preview financial effect" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("OPEN_SCHEDULE");
    await user.type(
      screen.getByLabelText("Type ASSET-1 to confirm irreversible disposal"),
      "ASSET-1"
    );
    expect(screen.getByRole("button", { name: "Confirm dispose" })).toBeDisabled();
    expect(service.dispose).not.toHaveBeenCalled();
  });
});
