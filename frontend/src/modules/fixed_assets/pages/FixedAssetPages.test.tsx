/* eslint-disable max-lines-per-function -- page tests cover routed workflows with service assertions. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DepreciationScheduleDetailPage } from "./DepreciationScheduleDetailPage";
import { DepreciationScheduleListPage } from "./DepreciationScheduleListPage";
import { AssetCategoryDetailPage } from "./AssetCategoryDetailPage";
import { AssetCategoryListPage } from "./AssetCategoryListPage";
import { AssetTransactionDetailPage } from "./AssetTransactionDetailPage";
import { DepreciationLineDetailPage } from "./DepreciationLineDetailPage";
import { FixedAssetDashboardPage } from "./FixedAssetDashboardPage";
import { FixedAssetDetailPage } from "./FixedAssetDetailPage";
import { FixedAssetListPage } from "./FixedAssetListPage";
import type {
  AssetCategory,
  AssetTransaction,
  DepreciationLine,
  DepreciationSchedule,
  FixedAsset,
  FixedAssetDashboard,
  JobStatusDto,
  ListResult,
  PaginationMeta,
} from "../contracts";

const service = vi.hoisted(() => ({
  listAssets: vi.fn(),
  getAsset: vi.fn(),
  listSchedules: vi.fn(),
  assetTransactions: vi.fn(),
  deleteAsset: vi.fn(),
  dashboard: vi.fn(),
  listCategories: vi.fn(),
  getCategory: vi.fn(),
  deactivateCategory: vi.fn(),
  getSchedule: vi.fn(),
  listLines: vi.fn(),
  getLine: vi.fn(),
  calculateSchedule: vi.fn(),
  activateSchedule: vi.fn(),
  supersedeSchedule: vi.fn(),
  postLine: vi.fn(),
  postDue: vi.fn(),
  getAllScheduleLines: vi.fn(),
  getTransaction: vi.fn(),
  getJob: vi.fn(),
}));

vi.mock("../services/fixed-assets-service", () => ({
  fixedAssetsService: service,
  shouldPollJob: (job: JobStatusDto | undefined) =>
    job?.status === "queued" || job?.status === "running",
  fixedAssetQueryKeys: {
    root: (tenantId: string | null) => ["fixed-assets", tenantId ?? "none"] as const,
    dashboard: (tenantId: string | null) =>
      ["fixed-assets", tenantId ?? "none", "dashboard"] as const,
    assets: (tenantId: string | null, filters = {}) =>
      ["fixed-assets", tenantId ?? "none", "assets", filters] as const,
    asset: (tenantId: string | null, id: string) =>
      ["fixed-assets", tenantId ?? "none", "asset", id] as const,
    categories: (tenantId: string | null, filters = {}) =>
      ["fixed-assets", tenantId ?? "none", "categories", filters] as const,
    category: (tenantId: string | null, id: string) =>
      ["fixed-assets", tenantId ?? "none", "category", id] as const,
    schedules: (tenantId: string | null, filters = {}) =>
      ["fixed-assets", tenantId ?? "none", "schedules", filters] as const,
    schedule: (tenantId: string | null, id: string) =>
      ["fixed-assets", tenantId ?? "none", "schedule", id] as const,
    lines: (tenantId: string | null, filters = {}) =>
      ["fixed-assets", tenantId ?? "none", "lines", filters] as const,
    line: (tenantId: string | null, id: string) =>
      ["fixed-assets", tenantId ?? "none", "line", id] as const,
    transaction: (tenantId: string | null, id: string) =>
      ["fixed-assets", tenantId ?? "none", "transaction", id] as const,
    job: (tenantId: string | null, id: string) =>
      ["fixed-assets", tenantId ?? "none", "job", id] as const,
  },
}));
vi.mock("@/stores/auth-store", () => ({
  useAuthStore: (selector: (state: { user: { tenant_id: string } }) => unknown) =>
    selector({ user: { tenant_id: "tenant-1" } }),
}));
vi.mock("../components/AssetLifecycleDialog", () => ({
  AssetLifecycleDialog: ({
    command,
    onOpenChange,
    onComplete,
  }: {
    command: string;
    onOpenChange: (open: boolean) => void;
    onComplete: () => void;
  }) => (
    <div role="dialog" aria-label={`${command} lifecycle dialog`}>
      <button
        type="button"
        onClick={() => {
          onComplete();
          onOpenChange(false);
        }}
      >
        Complete {command}
      </button>
    </div>
  ),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderRoute(ui: React.ReactElement, path: string, entry = path) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path={path} element={ui} />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function LocationProbe() {
  const location = useLocation();
  return (
    <p data-testid="location">
      {location.pathname}
      {location.search}
    </p>
  );
}

const pagination: PaginationMeta = {
  page: 1,
  page_size: 25,
  total_pages: 1,
  count: 1,
  has_next: false,
  has_previous: false,
};

function page<T>(items: readonly T[], meta: PaginationMeta = pagination): ListResult<T> {
  return { items, pagination: meta, correlationId: "corr-fixed-assets-test" };
}

const asset: FixedAsset = {
  id: "asset-1",
  asset_code: "ASSET-1",
  asset_name: "Forklift",
  description: "Warehouse lift",
  category: { id: "category-1", code: "EQUIP", name: "Equipment" },
  purchase_date: "2026-07-01",
  purchase_cost: "12000.00",
  currency: "USD",
  residual_value: "1000.00",
  capitalization_date: null,
  depreciation_start_date: "2026-08-01",
  depreciation_method: "straight_line",
  useful_life_months: 60,
  declining_balance_rate: null,
  expected_total_units: null,
  accumulated_depreciation: "200.00",
  accumulated_impairment: "0.00",
  net_book_value: "11800.00",
  location: "Dock A",
  cost_center: "OPS",
  status: "draft",
  disposal_date: null,
  disposal_proceeds: null,
  disposal_gain_loss: null,
  next_depreciation_date: null,
  as_of: "2026-07-28",
  version: 3,
  allowed_commands: ["edit", "delete", "capitalize", "transfer"],
  denial_reasons: { dispose: "Only active assets can be disposed." },
  active_schedule: null,
  balance_reconciliation: {
    purchase_cost: "12000.00",
    accumulated_depreciation: "200.00",
    accumulated_impairment: "0.00",
    calculated_net_book_value: "11800.00",
    reconciled: true,
  },
  created_by: "user-1",
  updated_by: "user-2",
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T01:00:00Z",
};

const category: AssetCategory = {
  id: "category-1",
  code: "EQUIP",
  name: "Equipment",
  description: "Tenant-governed equipment category",
  default_depreciation_method: "straight_line",
  default_useful_life_months: 60,
  default_residual_value_percent: "5.00",
  default_declining_balance_rate: null,
  asset_account_id: "acct-asset",
  accumulated_depreciation_account_id: "acct-accumulated",
  depreciation_expense_account_id: "acct-expense",
  impairment_loss_account_id: "acct-impairment",
  disposal_gain_account_id: "acct-gain",
  disposal_loss_account_id: "acct-loss",
  is_active: true,
  version: 3,
  allowed_commands: ["edit", "deactivate"],
  denial_reasons: {},
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T01:00:00Z",
};

const schedule: DepreciationSchedule = {
  id: "schedule-1",
  asset_id: "asset-1",
  asset: { id: "asset-1", asset_code: "ASSET-1", asset_name: "Forklift", currency: "USD" },
  schedule_number: "DEP-2026-001",
  revision: 2,
  method: "straight_line",
  frequency: "monthly",
  start_date: "2026-08-01",
  end_date: "2031-07-31",
  cost_basis: "12000.00",
  residual_value: "1000.00",
  depreciable_amount: "11000.00",
  declining_balance_rate: null,
  expected_total_units: null,
  total_planned_depreciation: "11000.00",
  status: "calculated",
  version: 5,
  calculated_at: "2026-07-28T00:00:00Z",
  activated_at: null,
  completed_at: null,
  superseded_by: null,
  reconciliation: { line_total: "11000.00", difference: "0.00", reconciled: true },
  allowed_commands: ["edit", "activate", "supersede", "calculate"],
  denial_reasons: {},
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T01:00:00Z",
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

const transaction: AssetTransaction = {
  id: "transaction-1",
  asset_id: "asset-1",
  asset: { id: "asset-1", asset_code: "ASSET-1", asset_name: "Forklift" },
  transaction_type: "capitalization",
  effective_date: "2026-08-01",
  amount: "12000.00",
  currency: "USD",
  opening_net_book_value: "0.00",
  closing_net_book_value: "12000.00",
  from_location: "",
  to_location: "Dock A",
  from_cost_center: "",
  to_cost_center: "OPS",
  journal_entry_id: "journal-1",
  source_type: "asset",
  source_id: "asset-1",
  actor_id: "user-1",
  correlation_id: "corr-transaction",
  metadata: {},
  created_at: "2026-08-01T00:00:00Z",
};

const job: JobStatusDto = {
  id: "job-1",
  status: "succeeded",
  operation: "post_line",
  progress_percent: 100,
  error_code: null,
  correlation_id: "corr-job",
  result: { posted_line_ids: ["line-1"] },
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:01:00Z",
};

const dashboard: FixedAssetDashboard = {
  asset_counts: { total: 3, draft: 1, active: 2, fully_depreciated: 0, disposed: 0 },
  book_value_by_currency: [{ currency: "USD", amount: "11800.00" }],
  current_period_depreciation_by_currency: [{ currency: "USD", amount: "183.33" }],
  pending_postings: 2,
  failed_postings: 1,
  impairments: 1,
  disposals: 0,
};

describe("Fixed asset detail pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    service.getAsset.mockResolvedValue(asset);
    service.listAssets.mockResolvedValue(
      page([asset], { ...pagination, total_pages: 2, has_next: true, count: 2 })
    );
    service.listSchedules.mockResolvedValue(page([schedule]));
    service.assetTransactions.mockResolvedValue(page([transaction]));
    service.deleteAsset.mockResolvedValue(undefined);
    service.dashboard.mockResolvedValue(dashboard);
    service.listCategories.mockResolvedValue(page([category]));
    service.getCategory.mockResolvedValue(category);
    service.deactivateCategory.mockResolvedValue(undefined);
    service.getSchedule.mockResolvedValue(schedule);
    service.listLines.mockResolvedValue(page([line]));
    service.getLine.mockResolvedValue(line);
    service.calculateSchedule.mockResolvedValue(schedule);
    service.activateSchedule.mockResolvedValue({ ...schedule, status: "active" });
    service.supersedeSchedule.mockResolvedValue({ ...schedule, status: "superseded" });
    service.postLine.mockResolvedValue(job);
    service.postDue.mockResolvedValue({ ...job, id: "job-post-due", operation: "post_due" });
    service.getAllScheduleLines.mockResolvedValue([line]);
    service.getTransaction.mockResolvedValue(transaction);
    service.getJob.mockResolvedValue(job);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:fixed-assets"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fixed-assets");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  });

  it("filters the asset register, navigates rows, and keeps URL-backed pagination stable", async () => {
    const user = userEvent.setup();
    renderRoute(<FixedAssetListPage />, "/fixed-assets/assets", "/fixed-assets/assets");

    expect(await screen.findByRole("button", { name: "ASSET-1" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search assets"), { target: { value: "fork" } });
    await screen.findByRole("button", { name: "ASSET-1" });
    await user.selectOptions(await screen.findByLabelText("Status filter"), "active");
    await screen.findByRole("button", { name: "ASSET-1" });
    await user.selectOptions(await screen.findByLabelText("Method filter"), "straight_line");
    await screen.findByRole("button", { name: "ASSET-1" });
    fireEvent.change(screen.getByLabelText("Currency filter"), { target: { value: "eur" } });
    await screen.findByRole("button", { name: "ASSET-1" });
    await user.selectOptions(await screen.findByLabelText("Sort assets"), "-net_book_value");
    await screen.findByRole("button", { name: "ASSET-1" });
    await user.click(await screen.findByRole("button", { name: "Next" }));

    await waitFor(() =>
      expect(service.listAssets).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page: 2,
          page_size: 25,
          search: "fork",
          status: "active",
          method: "straight_line",
          currency: "EUR",
          ordering: "-net_book_value",
        })
      )
    );

    await user.click(screen.getByRole("button", { name: "ASSET-1" }));
    expect(await screen.findByTestId("location")).toHaveTextContent("/fixed-assets/assets/asset-1");
  });

  it("filters depreciation schedules and queues due posting with deterministic idempotency", async () => {
    const user = userEvent.setup();
    renderRoute(
      <DepreciationScheduleListPage />,
      "/fixed-assets/depreciation-schedules",
      "/fixed-assets/depreciation-schedules"
    );

    expect(await screen.findByRole("button", { name: "DEP-2026-001" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Schedule status"), "active");
    await user.type(screen.getByLabelText("Start from"), "2026-08-01");
    await user.type(screen.getByLabelText("Post due through"), "2026-08-31");
    await user.click(screen.getByRole("button", { name: "Post due" }));

    await waitFor(() =>
      expect(service.listSchedules).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page: 1,
          page_size: 25,
          status: "active",
          start_from: "2026-08-01",
        })
      )
    );
    await waitFor(() =>
      expect(service.postDue).toHaveBeenCalledWith(
        { through_date: "2026-08-31" },
        "post-due:2026-08-31"
      )
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Job job-post-due");

    await user.click(screen.getByRole("button", { name: "DEP-2026-001" }));
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/fixed-assets/depreciation-schedules/schedule-1"
    );
  });

  it("loads asset evidence tabs and navigates from schedule and transaction rows", async () => {
    const user = userEvent.setup();
    const firstRender = renderRoute(
      <FixedAssetDetailPage />,
      "/fixed-assets/assets/:id",
      "/fixed-assets/assets/asset-1"
    );

    expect(await screen.findByRole("heading", { name: /ASSET-1/u })).toBeInTheDocument();
    expect(screen.getByLabelText("Balance summary")).toHaveTextContent("Purchase cost");
    expect(screen.getByText("Reconciled to the stored book value.")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Depreciation" }));
    expect(await screen.findByRole("button", { name: /DEP-2026-001/u })).toBeInTheDocument();
    expect(service.listSchedules).toHaveBeenCalledWith({ asset_id: "asset-1" });
    await user.click(screen.getByRole("button", { name: /DEP-2026-001/u }));
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/fixed-assets/depreciation-schedules/schedule-1"
    );
    firstRender.unmount();

    renderRoute(
      <FixedAssetDetailPage />,
      "/fixed-assets/assets/:id",
      "/fixed-assets/assets/asset-1"
    );
    await user.click(await screen.findByRole("tab", { name: "Transactions" }));
    expect(await screen.findByRole("button", { name: /Capitalization/u })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Capitalization/u }));
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/fixed-assets/transactions/transaction-1"
    );
  });

  it("requires typed confirmation before deleting draft assets", async () => {
    const user = userEvent.setup();
    renderRoute(
      <FixedAssetDetailPage />,
      "/fixed-assets/assets/:id",
      "/fixed-assets/assets/asset-1"
    );

    await user.click(await screen.findByRole("button", { name: "Delete draft" }));
    expect(screen.getByRole("button", { name: "Delete draft permanently" })).toBeDisabled();
    await user.type(screen.getByLabelText("Type ASSET-1 to confirm"), "ASSET-1");
    await user.click(screen.getByRole("button", { name: "Delete draft permanently" }));

    await waitFor(() => expect(service.deleteAsset).toHaveBeenCalledWith("asset-1"));
    expect(await screen.findByTestId("location")).toHaveTextContent("/fixed-assets/assets");
  });

  it("opens server-authoritative lifecycle dialog from allowed commands", async () => {
    const user = userEvent.setup();
    renderRoute(
      <FixedAssetDetailPage />,
      "/fixed-assets/assets/:id",
      "/fixed-assets/assets/asset-1"
    );

    await user.click(await screen.findByRole("button", { name: "Capitalize" }));
    expect(screen.getByRole("dialog", { name: "capitalize lifecycle dialog" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Complete capitalize" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("runs schedule calculate, activate, export, post, and supersede workflows", async () => {
    const user = userEvent.setup();
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderRoute(
      <DepreciationScheduleDetailPage />,
      "/fixed-assets/depreciation-schedules/:id",
      "/fixed-assets/depreciation-schedules/schedule-1"
    );

    expect(await screen.findByRole("heading", { name: "DEP-2026-001" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Calculate preview/u }));
    await user.type(screen.getByLabelText("Units by period (optional)"), "2026-08-01, 125.5000");
    await user.click(screen.getByRole("button", { name: "Calculate immutable preview" }));
    await waitFor(() =>
      expect(service.calculateSchedule).toHaveBeenCalledWith(
        "schedule-1",
        { units_by_period: [{ period_start: "2026-08-01", units_consumed: "125.5000" }] },
        "calculate-schedule:schedule-1:5"
      )
    );

    await user.click(screen.getByRole("button", { name: /Activate/u }));
    await waitFor(() =>
      expect(service.activateSchedule).toHaveBeenCalledWith(
        "schedule-1",
        {},
        "activate-schedule:schedule-1:5"
      )
    );

    await user.click(screen.getByRole("button", { name: /Export CSV/u }));
    await waitFor(() => expect(service.getAllScheduleLines).toHaveBeenCalledWith("schedule-1"));
    expect(clickSpy).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Post" }));
    await waitFor(() =>
      expect(service.postLine).toHaveBeenCalledWith("line-1", {}, "post-line:line-1")
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Posting job · Succeeded");

    await user.click(screen.getByRole("button", { name: "Supersede" }));
    await user.type(screen.getByLabelText("Reason"), "Replaced by corrected useful life");
    await user.click(screen.getByRole("button", { name: "Supersede schedule" }));
    await waitFor(() =>
      expect(service.supersedeSchedule).toHaveBeenCalledWith(
        "schedule-1",
        { reason: "Replaced by corrected useful life" },
        "supersede-schedule:schedule-1:5"
      )
    );
  });

  it("renders dashboard lifecycle totals and navigates primary actions", async () => {
    const user = userEvent.setup();
    const firstRender = renderRoute(<FixedAssetDashboardPage />, "/fixed-assets");

    expect(
      await screen.findByRole("heading", { name: "Fixed asset dashboard" })
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Lifecycle summary")).toHaveTextContent("Assets");
    expect(screen.getByText("$11,800.00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Register asset" }));
    expect(await screen.findByTestId("location")).toHaveTextContent("/fixed-assets/assets/new");
    firstRender.unmount();

    service.dashboard.mockResolvedValueOnce({
      ...dashboard,
      asset_counts: { total: 0, draft: 0, active: 0, fully_depreciated: 0, disposed: 0 },
    });
    renderRoute(<FixedAssetDashboardPage />, "/fixed-assets");
    expect(await screen.findByText("Your asset register is empty")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create category" }));
    expect(await screen.findByTestId("location")).toHaveTextContent("/fixed-assets/categories/new");
  });

  it("filters category list and deactivates only after typed confirmation", async () => {
    const user = userEvent.setup();
    const listRender = renderRoute(
      <AssetCategoryListPage />,
      "/fixed-assets/categories",
      "/fixed-assets/categories"
    );

    expect(await screen.findByRole("heading", { name: "Asset categories" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search categories"), { target: { value: "equip" } });
    await user.selectOptions(
      await screen.findByLabelText("Depreciation method filter"),
      "straight_line"
    );
    await waitFor(() =>
      expect(service.listCategories).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 25,
        search: "equip",
        method: "straight_line",
      })
    );
    await user.click(screen.getByRole("button", { name: "EQUIP" }));
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/fixed-assets/categories/category-1"
    );
    listRender.unmount();

    renderRoute(
      <AssetCategoryDetailPage />,
      "/fixed-assets/categories/:id",
      "/fixed-assets/categories/category-1"
    );
    expect(await screen.findByRole("heading", { name: "EQUIP · Equipment" })).toBeInTheDocument();
    expect(screen.getByText("acct-accumulated")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(screen.getByRole("button", { name: "Deactivate category" })).toBeDisabled();
    await user.type(screen.getByLabelText("Type EQUIP to confirm"), "EQUIP");
    await user.click(screen.getByRole("button", { name: "Deactivate category" }));
    await waitFor(() => expect(service.deactivateCategory).toHaveBeenCalledWith("category-1"));
  });

  it("loads depreciation line detail, posts with deterministic key, and returns to schedule", async () => {
    const user = userEvent.setup();
    renderRoute(
      <DepreciationLineDetailPage />,
      "/fixed-assets/depreciation-lines/:id",
      "/fixed-assets/depreciation-lines/line-1"
    );

    expect(
      await screen.findByRole("heading", { name: "Depreciation period 1" })
    ).toBeInTheDocument();
    expect(screen.getAllByText("$183.33").length).toBeGreaterThanOrEqual(1);
    await user.click(screen.getByRole("button", { name: "Post depreciation" }));
    await waitFor(() =>
      expect(service.postLine).toHaveBeenCalledWith("line-1", {}, "post-line:line-1")
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Correlation ID: corr-job");
    await user.click(screen.getByRole("button", { name: "Schedule" }));
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/fixed-assets/depreciation-schedules/schedule-1"
    );
  });

  it("renders append-only transaction detail and navigates back to asset history", async () => {
    const user = userEvent.setup();
    renderRoute(
      <AssetTransactionDetailPage />,
      "/fixed-assets/transactions/:id",
      "/fixed-assets/transactions/transaction-1"
    );

    expect(await screen.findByRole("heading", { name: "Capitalization" })).toBeInTheDocument();
    expect(screen.getByText("ASSET-1 · Forklift")).toBeInTheDocument();
    expect(screen.getByText("corr-transaction")).toBeInTheDocument();
    expect(screen.getByText(/append-only/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Asset history" }));
    expect(await screen.findByTestId("location")).toHaveTextContent("/fixed-assets/assets/asset-1");
  });
});
