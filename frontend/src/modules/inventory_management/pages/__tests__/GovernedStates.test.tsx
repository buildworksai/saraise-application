/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method -- inventory page coverage matrix intentionally keeps fixture-heavy scenarios together and asserts Vitest spies on service methods. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type React from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import { useAuthStore } from "@/stores/auth-store";
import {
  InventoryEmpty,
  InventoryErrorState,
  InventorySkeleton,
} from "../../components/GovernedStates";
import type { InventoryConfiguration } from "../../contracts";
import {
  BatchCreatePage,
  BatchDetailPage,
  BatchEditPage,
  BatchListPage,
  BatchTracePage,
  BulkImportPage,
  ConfigurationDetailPage,
  ConfigurationEditPage,
  ConfigurationExportPage,
  ConfigurationHistoryPage,
  ConfigurationImportPage,
  ConfigurationListPage,
  ConfigurationPreviewPage,
  ConfigurationRollbackPage,
  CycleCountCreatePage,
  CycleCountDetailPage,
  CycleCountEditPage,
  CycleCountListPage,
  InventoryDashboardPage,
  ItemDetailPage,
  ItemEditPage,
  ItemCreatePage,
  ItemListPage,
  LocationCreatePage,
  LocationDetailPage,
  LocationEditPage,
  LocationListPage,
  SerialCreatePage,
  SerialDetailPage,
  SerialEditPage,
  SerialListPage,
  SerialTracePage,
  StockBalanceDetailPage,
  StockBalanceListPage,
  StockEntryDetailPage,
  StockEntryEditPage,
  StockEntryListPage,
  ReservationCreatePage,
  ReservationDetailPage,
  ReservationEditPage,
  ReservationListPage,
  StockEntryCreatePage,
  StockLedgerDetailPage,
  StockLedgerListPage,
  WarehouseCreatePage,
  WarehouseDetailPage,
  WarehouseEditPage,
  WarehouseListPage,
} from "../InventoryPages";
import { inventoryService } from "../../services/inventory-service";

function renderInventoryPage(children: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderInventoryRoute(route: string, initial: string, children: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path={route} element={children} />
          <Route path="*" element={<div data-testid="navigated" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const configuration: InventoryConfiguration = {
  id: "config-1",
  version: 4,
  created_at: "2026-07-23T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
  allowed_commands: [],
  denial_reasons: [],
  environment: "development",
  status: "draft",
  default_valuation_method: "fifo",
  allow_negative_stock: false,
  require_stock_entry_approval: true,
  enforce_creator_approver_separation: true,
  max_lines_per_entry: 100,
  reservation_ttl_minutes: 60,
  expiry_warning_days: 30,
  auto_expire_batches: true,
  enabled_capabilities: {
    barcode_scanning: true,
    bulk_import: true,
    batch_tracking: true,
    serial_tracking: true,
    cycle_counting: true,
  },
  rollout_rules: {
    enabled: true,
    percentage: 100,
    tenant_cohort: "all",
    allowed_role_ids: [],
  },
  active_revision: 4,
};

const page = <T,>(data: T[], overrides = {}) => ({
  data,
  correlationId: "corr-page",
  timestamp: "2026-07-23T00:00:00Z",
  pagination: {
    page: 1,
    page_size: 25,
    total_count: data.length,
    total_pages: data.length ? 1 : 0,
    next: null,
    previous: null,
    ...overrides,
  },
});

const result = <T,>(data: T) => ({
  data,
  correlationId: "corr-detail",
  timestamp: "2026-07-23T00:00:00Z",
});

const warehouse = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "warehouse-1",
    version: 3,
    allowed_commands: [
      {
        name: "set_default",
        label: "Set default",
        destructive: false,
        requires_confirmation: true,
      },
      { name: "archive", label: "Archive", destructive: true, requires_confirmation: true },
    ],
    warehouse_code: "WH-MUM",
    warehouse_name: "Mumbai DC",
    warehouse_type: "distribution_center",
    country_code: "IN",
    timezone: "Asia/Kolkata",
    is_default: false,
    is_active: true,
    city: "Mumbai",
    ...overrides,
  }) as never;

const item = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "item-1",
    version: 2,
    allowed_commands: [
      { name: "archive", label: "Archive", destructive: true, requires_confirmation: true },
    ],
    item_code: "SKU-001",
    item_name: "Tracked component",
    base_uom: "EA",
    tracking_mode: "batch",
    valuation_method: "fifo",
    category: "components",
    reorder_point: "10.000000",
    is_active: true,
    ...overrides,
  }) as never;

const reservation = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "reservation-1",
    version: 9,
    allowed_commands: [
      { name: "release", label: "Release", destructive: false, requires_confirmation: false },
    ],
    reservation_number: "RES-001",
    item: { id: "item-1", code: "SKU-001", name: "Tracked component" },
    warehouse: { id: "warehouse-1", code: "WH-MUM", name: "Mumbai DC" },
    location: { id: "location-1", code: "BIN-01", name: "Pick face" },
    status: "active",
    quantity: "5.000000",
    expires_at: "2026-08-03T00:00:00Z",
    reference_module: "sales",
    reference_type: "order",
    ...overrides,
  }) as never;

const summary = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "summary-1",
    code: "REF-1",
    name: "Reference one",
    ...overrides,
  }) as never;

const location = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "location-1",
    version: 5,
    allowed_commands: [
      { name: "archive", label: "Archive", destructive: true, requires_confirmation: true },
    ],
    warehouse: summary({ id: "warehouse-1", code: "WH-MUM", name: "Mumbai DC" }),
    parent: null,
    location_code: "BIN-01",
    location_name: "Pick face",
    zone_type: "picking",
    location_type: "bin",
    barcode: "BIN-01",
    pick_sequence: 12,
    capacity_units: null,
    capacity_weight_kg: null,
    capacity_volume_cbm: null,
    temperature_controlled: false,
    hazmat_approved: false,
    is_default: false,
    is_active: true,
    archived_at: null,
    ...overrides,
  }) as never;

const batch = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "batch-1",
    version: 6,
    allowed_commands: [
      { name: "quarantine", label: "Quarantine", destructive: true, requires_confirmation: true },
    ],
    item: summary({ id: "item-1", code: "SKU-001", name: "Tracked component" }),
    batch_number: "BATCH-1",
    supplier_batch_number: "SUP-1",
    manufactured_on: "2026-07-01",
    expires_on: "2027-07-01",
    status: "active",
    transition_history: [],
    ...overrides,
  }) as never;

const serial = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "serial-1",
    version: 7,
    allowed_commands: [],
    item: summary({ id: "item-1", code: "SKU-001", name: "Tracked component" }),
    serial_number: "SER-1",
    status: "in_stock",
    current_warehouse: summary({ id: "warehouse-1", code: "WH-MUM", name: "Mumbai DC" }),
    current_location: summary({ id: "location-1", code: "BIN-01", name: "Pick face" }),
    manufacturer: "BuildWorks",
    model_number: "M-1",
    warranty_starts_on: "2026-07-01",
    warranty_ends_on: "2027-07-01",
    transition_history: [],
    ...overrides,
  }) as never;

const stockEntry = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "entry-1",
    version: 8,
    allowed_commands: [
      { name: "submit", label: "Submit", destructive: false, requires_confirmation: false },
    ],
    entry_number: "STK-1",
    entry_type: "receipt",
    posting_at: "2026-08-03T10:00",
    source_warehouse: null,
    destination_warehouse: summary({ id: "warehouse-1", code: "WH-MUM", name: "Mumbai DC" }),
    reference_module: "purchase",
    reference_type: "receipt",
    reference_id: "po-1",
    reason: "Initial receipt",
    status: "draft",
    created_by_id: "user-1",
    approved_by_id: null,
    posted_by_id: null,
    approved_at: null,
    posted_at: null,
    reversed_at: null,
    reversal_of_id: null,
    lines: [
      {
        id: "line-1",
        line_number: 1,
        item: summary({ id: "item-1", code: "SKU-001", name: "Tracked component" }),
        source_location: null,
        destination_location: summary({ id: "location-1", code: "BIN-01", name: "Pick face" }),
        batch: null,
        serial_number: null,
        quantity: "3.000000",
        uom: "EA",
        unit_cost: "11.00",
        line_value: "33.00",
        notes: "",
      },
    ],
    transition_history: [],
    ...overrides,
  }) as never;

const ledgerEntry = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "ledger-1",
    sequence: 42,
    stock_entry_id: "entry-1",
    stock_entry_line_id: "line-1",
    item: summary({ id: "item-1", code: "SKU-001", name: "Tracked component" }),
    warehouse: summary({ id: "warehouse-1", code: "WH-MUM", name: "Mumbai DC" }),
    location: summary({ id: "location-1", code: "BIN-01", name: "Pick face" }),
    batch: null,
    serial_number: null,
    quantity_delta: "3.000000",
    quantity_after: "3.000000",
    unit_cost: "11.00",
    value_delta: "33.00",
    value_after: "33.00",
    posted_at: "2026-08-03T10:00:00Z",
    correlation_id: "corr-ledger",
    created_at: "2026-08-03T10:00:00Z",
    ...overrides,
  }) as never;

const cycleCount = (overrides: Record<string, unknown> = {}) =>
  ({
    id: "count-1",
    version: 10,
    allowed_commands: [
      { name: "start", label: "Start", destructive: false, requires_confirmation: false },
    ],
    count_number: "COUNT-1",
    warehouse: summary({ id: "warehouse-1", code: "WH-MUM", name: "Mumbai DC" }),
    location: summary({ id: "location-1", code: "BIN-01", name: "Pick face" }),
    count_type: "full",
    scheduled_for: "2026-08-10",
    assigned_to_id: null,
    status: "scheduled",
    started_at: null,
    submitted_at: null,
    approved_at: null,
    posted_at: null,
    lines: [],
    transition_history: [],
    ...overrides,
  }) as never;

beforeEach(() => {
  globalThis.localStorage?.clear();
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
});

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.localStorage?.clear();
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
});

describe("inventory governed states", () => {
  it("renders an accessible skeleton", () => {
    render(<InventorySkeleton label="Loading balances" />);
    expect(screen.getByRole("status", { name: "Loading balances" })).toBeInTheDocument();
  });

  it("fails closed for 403 and surfaces correlation evidence without retry", () => {
    render(
      <InventoryErrorState
        error={new ApiError("denied", 403, undefined, "forbidden", "corr-denied")}
        onRetry={vi.fn()}
      />
    );
    expect(screen.getByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText(/corr-denied/u)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("does not disclose whether a 404 belongs to another tenant", () => {
    render(<InventoryErrorState error={new ApiError("secret object detail", 404)} />);
    expect(screen.getByText("Inventory record unavailable")).toBeInTheDocument();
    expect(screen.queryByText("secret object detail")).not.toBeInTheDocument();
  });

  it("offers retry only for retryable failures", () => {
    const retry = vi.fn();
    render(
      <InventoryErrorState
        error={new ApiError("temporarily unavailable", 503, undefined, "unavailable", "corr-retry")}
        onRetry={retry}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("gives empty states a valid next action", () => {
    const action = vi.fn();
    render(
      <InventoryEmpty
        title="No warehouses"
        detail="Create one."
        action={{ label: "Create warehouse", onClick: action }}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Create warehouse" }));
    expect(action).toHaveBeenCalledOnce();
  });

  it("marks inventory create pages with native required constraints", () => {
    const { container, unmount } = renderInventoryPage(<WarehouseCreatePage />);

    expect(container.querySelector("form")?.noValidate).toBe(false);
    expect(screen.getByLabelText(/^Warehouse code/u)).toBeRequired();
    expect(screen.getByLabelText(/^Warehouse name/u)).toBeRequired();
    expect(screen.getByLabelText(/^Warehouse type/u)).toBeRequired();
    expect(screen.getByLabelText(/^Country code/u)).toBeRequired();
    expect(screen.getByLabelText(/^Timezone/u)).toBeRequired();

    unmount();
    const item = renderInventoryPage(<ItemCreatePage />);

    expect(item.container.querySelector("form")?.noValidate).toBe(false);
    expect(screen.getByLabelText(/^Item code/u)).toBeRequired();
    expect(screen.getByLabelText(/^Item code/u)).not.toHaveAttribute("min");
    expect(screen.getByLabelText(/^Item name/u)).toBeRequired();
    expect(screen.getByLabelText(/^Base unit of measure/u)).toBeRequired();
    expect(screen.getByLabelText(/^Tracking mode/u)).toBeRequired();
    expect(screen.getByLabelText(/^Valuation method/u)).toBeRequired();

    item.unmount();
    const stockEntry = renderInventoryPage(<StockEntryCreatePage />);

    expect(screen.getByLabelText(/^Quantity/u)).toBeRequired();
    expect(screen.getByLabelText(/^Quantity/u)).toHaveAttribute("min", "0.000001");
    expect(screen.getByLabelText(/^Entry number/u)).not.toHaveAttribute("min");
    expect(screen.getByLabelText(/^Unit cost/u)).not.toHaveAttribute("min");

    stockEntry.unmount();
    const reservation = renderInventoryPage(<ReservationCreatePage />);

    expect(reservation.container.querySelector("form")?.noValidate).toBe(false);
    expect(screen.getByLabelText(/^Quantity/u)).toBeRequired();
    expect(screen.getByLabelText(/^Quantity/u)).toHaveAttribute("min", "0.000001");
  });

  it("does not retry configuration preview dry-runs automatically", async () => {
    vi.spyOn(inventoryService, "getConfiguration").mockResolvedValue({
      data: configuration,
      correlationId: "corr-config",
      timestamp: "2026-07-23T00:00:00Z",
    });
    const previewConfiguration = vi
      .spyOn(inventoryService, "previewConfiguration")
      .mockRejectedValue(
        new ApiError("preview failed", 503, undefined, "unavailable", "corr-preview")
      );

    renderInventoryRoute(
      "/inventory-management/configurations/:environment/preview",
      "/inventory-management/configurations/development/preview",
      <ConfigurationPreviewPage />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("preview failed");
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await waitFor(() => expect(previewConfiguration).toHaveBeenCalledTimes(1));
  });

  it("filters, saves, exports, and paginates warehouse lists with tenant-scoped evidence", async () => {
    const user = userEvent.setup();
    const createObjectUrl = vi.fn(() => "blob:inventory-export");
    const revokeObjectUrl = vi.fn();
    const anchor = document.createElement("a");
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    const createElement = vi.spyOn(document, "createElement").mockImplementation((tag) => {
      if (tag === "a") return anchor;
      return Document.prototype.createElement.call(document, tag);
    });
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: createObjectUrl,
      revokeObjectURL: revokeObjectUrl,
    });
    const listWarehouses = vi.spyOn(inventoryService, "listWarehouses").mockResolvedValue(
      page([warehouse(), warehouse({ id: "warehouse-2", warehouse_code: "WH-DEL" })], {
        total_count: 50,
        total_pages: 2,
        next: "2",
      })
    );

    renderInventoryRoute(
      "/inventory-management/warehouses",
      "/inventory-management/warehouses?search=old",
      <WarehouseListPage />
    );

    expect(await screen.findByText("WH-MUM")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search Warehouses"), { target: { value: "tracked" } });
    await waitFor(() =>
      expect(listWarehouses).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 25,
        search: "tracked",
        ordering: "code",
      })
    );

    await user.selectOptions(await screen.findByLabelText("Order results"), "-created_at");
    await waitFor(() =>
      expect(listWarehouses).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 25,
        search: "tracked",
        ordering: "-created_at",
      })
    );

    await user.click(screen.getByLabelText("Select WH-MUM"));
    await user.click(screen.getByRole("button", { name: /Export CSV/u }));
    expect(createObjectUrl).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(anchor.download).toBe("warehouse-inventory.csv");
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:inventory-export");

    await user.click(screen.getByRole("button", { name: "Save filter" }));
    const savedFilter =
      localStorage.getItem("inventory-filter:unscoped:warehouse") ??
      localStorage.getItem("inventory-filter:tenant-1:warehouse");
    expect(savedFilter ?? "").toContain("search=tracked");

    await user.click(screen.getByRole("button", { name: /Next/u }));
    await waitFor(() =>
      expect(listWarehouses).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    );
    createElement.mockRestore();
  });

  it("renders empty read-only ledger lists with operational navigation", async () => {
    vi.spyOn(inventoryService, "listLedger").mockResolvedValue(page([]));

    renderInventoryRoute(
      "/inventory-management/stock-ledger",
      "/inventory-management/stock-ledger",
      <StockLedgerListPage />
    );

    expect(
      await screen.findByRole("heading", { name: "No stock ledger found" })
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create a stock entry" }));
    expect(
      screen.queryByRole("heading", { name: "No stock ledger found" })
    ).not.toBeInTheDocument();
  });

  it("runs server-governed detail commands only after destructive confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal("crypto", { randomUUID: () => "command-key" });
    vi.spyOn(inventoryService, "getWarehouse").mockResolvedValue(result(warehouse()));
    const setDefaultWarehouse = vi
      .spyOn(inventoryService, "setDefaultWarehouse")
      .mockResolvedValue(result(warehouse({ is_default: true })));

    renderInventoryRoute(
      "/inventory-management/warehouses/:id",
      "/inventory-management/warehouses/warehouse-1",
      <WarehouseDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "Mumbai DC" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Set default" }));

    await waitFor(() =>
      expect(setDefaultWarehouse).toHaveBeenCalledWith(
        "warehouse-1",
        "inventory:warehouse:set_default:warehouse-1:command-key"
      )
    );
  });

  it("edits optimistic resources and sends descriptor-owned transition keys", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "unsupported-key" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(inventoryService, "getWarehouse").mockResolvedValue(result(warehouse()));
    const updateWarehouse = vi
      .spyOn(inventoryService, "updateWarehouse")
      .mockResolvedValue(result(warehouse({ warehouse_name: "Mumbai DC audited" })));

    const edit = renderInventoryRoute(
      "/inventory-management/warehouses/:id/edit",
      "/inventory-management/warehouses/warehouse-1/edit",
      <WarehouseEditPage />
    );

    const name = await screen.findByLabelText(/^Warehouse name/u);
    await user.type(screen.getByLabelText(/^Warehouse code/u), "WH-MUM");
    await user.clear(name);
    await user.type(name, "Mumbai DC audited");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(updateWarehouse).toHaveBeenCalledWith(
        "warehouse-1",
        expect.objectContaining({ warehouse_name: "Mumbai DC audited" }),
        3
      )
    );
    edit.unmount();

    vi.spyOn(inventoryService, "getBatch").mockResolvedValue(
      result(
        batch({
          allowed_commands: [
            {
              name: "unsupported",
              label: "Unsupported transition",
              destructive: false,
              requires_confirmation: false,
            },
          ],
        })
      )
    );
    const commandBatch = vi
      .spyOn(inventoryService, "commandBatch")
      .mockResolvedValue(result(batch()));

    renderInventoryRoute(
      "/inventory-management/batches/:id",
      "/inventory-management/batches/batch-1",
      <BatchDetailPage />
    );

    await user.click(await screen.findByRole("button", { name: "Unsupported transition" }));
    expect(commandBatch).toHaveBeenCalledWith(
      "batch-1",
      "unsupported",
      {
        expected_version: 6,
        transition_key: "inventory:batch:unsupported:batch-1:unsupported-key",
      },
      "inventory:batch:unsupported:batch-1:unsupported-key"
    );
  });

  it("creates item payloads with defaults, optional values, and generated idempotency keys", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "create-key" });
    const createItem = vi
      .spyOn(inventoryService, "createItem")
      .mockResolvedValue(result(item({ id: "created-item" })));

    renderInventoryRoute(
      "/inventory-management/items/new",
      "/inventory-management/items/new",
      <ItemCreatePage />
    );

    await user.type(screen.getByLabelText(/^Item code/u), "SKU-NEW");
    await user.type(screen.getByLabelText(/^Item name/u), "New component");
    await user.clear(screen.getByLabelText(/^Base unit of measure/u));
    await user.type(screen.getByLabelText(/^Base unit of measure/u), "KG");
    await user.clear(screen.getByLabelText(/^Tracking mode/u));
    await user.type(screen.getByLabelText(/^Tracking mode/u), "serial");
    await user.clear(screen.getByLabelText(/^Valuation method/u));
    await user.type(screen.getByLabelText(/^Valuation method/u), "standard_cost");
    await user.type(screen.getByLabelText(/^Barcode/u), "BAR-1");
    await user.click(screen.getByRole("button", { name: "Create item" }));

    await waitFor(() =>
      expect(createItem).toHaveBeenCalledWith(
        {
          item_code: "SKU-NEW",
          item_name: "New component",
          base_uom: "KG",
          tracking_mode: "serial",
          valuation_method: "standard_cost",
          barcode: "BAR-1",
        },
        "inventory:item:create:create-key"
      )
    );
  });

  it("hydrates detail and edit pages for item and reservation resource descriptors", async () => {
    vi.spyOn(inventoryService, "getItem").mockResolvedValue(result(item()));
    vi.spyOn(inventoryService, "getReservation").mockResolvedValue(result(reservation()));

    const itemDetail = renderInventoryRoute(
      "/inventory-management/items/:id",
      "/inventory-management/items/item-1",
      <ItemDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "Tracked component" })).toBeInTheDocument();
    expect(screen.getByText("SKU-001")).toBeInTheDocument();
    itemDetail.unmount();

    renderInventoryRoute(
      "/inventory-management/reservations/:id",
      "/inventory-management/reservations/reservation-1",
      <ReservationDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "RES-001" })).toBeInTheDocument();
    expect(screen.getByText("sales / order")).toBeInTheDocument();
  });

  it("hydrates remaining inventory descriptor wrappers and preserves edit payload boundaries", async () => {
    const user = userEvent.setup();
    vi.spyOn(inventoryService, "listReservations").mockResolvedValue(page([reservation()]));
    vi.spyOn(inventoryService, "listCycleCounts").mockResolvedValue(page([cycleCount()]));
    vi.spyOn(inventoryService, "getItem").mockResolvedValue(result(item()));
    vi.spyOn(inventoryService, "getLocation").mockResolvedValue(result(location()));
    vi.spyOn(inventoryService, "getSerial").mockResolvedValue(result(serial()));
    vi.spyOn(inventoryService, "getStockEntry").mockResolvedValue(result(stockEntry()));
    vi.spyOn(inventoryService, "getReservation").mockResolvedValue(result(reservation()));
    vi.spyOn(inventoryService, "getBalance").mockResolvedValue(
      result({
        id: "balance-1",
        item: summary({ id: "item-1", code: "SKU-001", name: "Tracked component" }),
        warehouse: summary({ id: "warehouse-1", code: "WH-MUM", name: "Mumbai DC" }),
        location: summary({ id: "location-1", code: "BIN-01", name: "Pick face" }),
        batch: null,
        serial_number: null,
        quantity_on_hand: "10.000000",
        quantity_allocated: "2.000000",
        quantity_available: "8.000000",
        stock_value: "110.00",
        valuation_rate: "11.00",
        last_ledger_entry_id: "ledger-1",
        created_at: "2026-08-03T10:00:00Z",
        updated_at: "2026-08-03T10:00:00Z",
      } as never)
    );
    vi.spyOn(inventoryService, "getLedgerEntry").mockResolvedValue(result(ledgerEntry()));
    vi.spyOn(inventoryService, "getCycleCount").mockResolvedValue(result(cycleCount()));
    const updateItem = vi.spyOn(inventoryService, "updateItem").mockResolvedValue(result(item()));
    const updateLocation = vi
      .spyOn(inventoryService, "updateLocation")
      .mockResolvedValue(result(location()));
    const updateBatch = vi
      .spyOn(inventoryService, "updateBatch")
      .mockResolvedValue(result(batch()));
    const updateSerial = vi
      .spyOn(inventoryService, "updateSerial")
      .mockResolvedValue(result(serial()));
    const updateStockEntry = vi.spyOn(inventoryService, "updateStockEntry");
    const updateReservation = vi.spyOn(inventoryService, "updateReservation");
    const updateCycleCount = vi
      .spyOn(inventoryService, "updateCycleCount")
      .mockResolvedValue(result(cycleCount()));

    const reservationList = renderInventoryRoute(
      "/inventory-management/reservations",
      "/inventory-management/reservations?search=RES",
      <ReservationListPage />
    );
    expect(await screen.findByText("RES-001")).toBeInTheDocument();
    reservationList.unmount();

    const cycleList = renderInventoryRoute(
      "/inventory-management/cycle-counts",
      "/inventory-management/cycle-counts",
      <CycleCountListPage />
    );
    expect(await screen.findByText("COUNT-1")).toBeInTheDocument();
    cycleList.unmount();

    const locationDetail = renderInventoryRoute(
      "/inventory-management/locations/:id",
      "/inventory-management/locations/location-1",
      <LocationDetailPage />
    );
    expect(await screen.findByRole("heading", { name: "Pick face" })).toBeInTheDocument();
    locationDetail.unmount();

    const serialDetail = renderInventoryRoute(
      "/inventory-management/serials/:id",
      "/inventory-management/serials/serial-1",
      <SerialDetailPage />
    );
    expect(await screen.findByRole("heading", { name: "SER-1" })).toBeInTheDocument();
    serialDetail.unmount();

    const stockEntryDetail = renderInventoryRoute(
      "/inventory-management/stock-entries/:id",
      "/inventory-management/stock-entries/entry-1",
      <StockEntryDetailPage />
    );
    expect(await screen.findByRole("heading", { name: "STK-1" })).toBeInTheDocument();
    stockEntryDetail.unmount();

    const balanceDetail = renderInventoryRoute(
      "/inventory-management/stock-balances/:id",
      "/inventory-management/stock-balances/balance-1",
      <StockBalanceDetailPage />
    );
    expect(await screen.findByRole("heading", { name: "Tracked component" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    balanceDetail.unmount();

    const ledgerDetail = renderInventoryRoute(
      "/inventory-management/stock-ledger/:id",
      "/inventory-management/stock-ledger/ledger-1",
      <StockLedgerDetailPage />
    );
    expect(await screen.findByRole("heading", { name: "Ledger movement #42" })).toBeInTheDocument();
    ledgerDetail.unmount();

    const cycleDetail = renderInventoryRoute(
      "/inventory-management/cycle-counts/:id",
      "/inventory-management/cycle-counts/count-1",
      <CycleCountDetailPage />
    );
    expect(await screen.findByRole("heading", { name: "COUNT-1" })).toBeInTheDocument();
    cycleDetail.unmount();

    vi.spyOn(inventoryService, "getBatch").mockResolvedValue(result(batch()));
    const itemEdit = renderInventoryRoute(
      "/inventory-management/items/:id/edit",
      "/inventory-management/items/item-1/edit",
      <ItemEditPage />
    );
    await user.clear(await screen.findByLabelText(/^Item name/u));
    await user.type(screen.getByLabelText(/^Item name/u), "Tracked component v2");
    await user.type(screen.getByLabelText(/^Item code/u), "SKU-001");
    await user.clear(screen.getByLabelText(/^Base unit of measure/u));
    await user.type(screen.getByLabelText(/^Base unit of measure/u), "EA");
    await user.clear(screen.getByLabelText(/^Tracking mode/u));
    await user.type(screen.getByLabelText(/^Tracking mode/u), "batch");
    await user.clear(screen.getByLabelText(/^Valuation method/u));
    await user.type(screen.getByLabelText(/^Valuation method/u), "fifo");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(updateItem).toHaveBeenCalledWith(
        "item-1",
        expect.objectContaining({ item_name: "Tracked component v2" }),
        2
      )
    );
    itemEdit.unmount();

    const locationEdit = renderInventoryRoute(
      "/inventory-management/locations/:id/edit",
      "/inventory-management/locations/location-1/edit",
      <LocationEditPage />
    );
    await user.type(await screen.findByLabelText(/^Warehouse ID/u), "warehouse-1");
    await user.type(screen.getByLabelText(/^Location code/u), "BIN-02");
    await user.type(screen.getByLabelText(/^Location name/u), "Overflow bin");
    await user.clear(screen.getByLabelText(/^Zone/u));
    await user.type(screen.getByLabelText(/^Zone/u), "bulk");
    await user.clear(screen.getByLabelText(/^Location type/u));
    await user.type(screen.getByLabelText(/^Location type/u), "rack");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(updateLocation).toHaveBeenCalledWith(
        "location-1",
        expect.objectContaining({ location_code: "BIN-02", location_type: "rack" }),
        5
      )
    );
    locationEdit.unmount();

    const batchEdit = renderInventoryRoute(
      "/inventory-management/batches/:id/edit",
      "/inventory-management/batches/batch-1/edit",
      <BatchEditPage />
    );
    await user.type(await screen.findByLabelText(/^Batch-tracked item ID/u), "item-1");
    await user.type(screen.getByLabelText(/^Batch number/u), "BATCH-2");
    await user.type(screen.getByLabelText(/^Manufactured on/u), "2026-08-01");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(updateBatch).toHaveBeenCalledWith(
        "batch-1",
        expect.objectContaining({ batch_number: "BATCH-2", manufactured_on: "2026-08-01" }),
        6
      )
    );
    batchEdit.unmount();

    const serialEdit = renderInventoryRoute(
      "/inventory-management/serials/:id/edit",
      "/inventory-management/serials/serial-1/edit",
      <SerialEditPage />
    );
    await user.type(await screen.findByLabelText(/^Serial-tracked item ID/u), "item-1");
    await user.type(screen.getByLabelText(/^Serial number/u), "SER-2");
    await user.type(screen.getByLabelText(/^Manufacturer/u), "BuildWorks");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(updateSerial).toHaveBeenCalledWith(
        "serial-1",
        expect.objectContaining({ serial_number: "SER-2", manufacturer: "BuildWorks" }),
        7
      )
    );
    serialEdit.unmount();

    const stockEntryEdit = renderInventoryRoute(
      "/inventory-management/stock-entries/:id/edit",
      "/inventory-management/stock-entries/entry-1/edit",
      <StockEntryEditPage />
    );
    await user.type(await screen.findByLabelText(/^Entry number/u), "STK-2");
    await user.clear(screen.getByLabelText(/^Entry type/u));
    await user.type(screen.getByLabelText(/^Entry type/u), "adjustment");
    await user.type(screen.getByLabelText(/^Posting time/u), "2026-08-03T11:00");
    await user.type(screen.getByLabelText(/^Line item ID/u), "item-1");
    const stockEntryQuantity = screen.getByLabelText(/^Quantity/u);
    await user.clear(stockEntryQuantity);
    await user.type(stockEntryQuantity, "0");
    await user.type(screen.getByLabelText(/^UOM/u), "EA");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(stockEntryQuantity).toBeInvalid();
    expect(updateStockEntry).not.toHaveBeenCalled();
    stockEntryEdit.unmount();

    const reservationEdit = renderInventoryRoute(
      "/inventory-management/reservations/:id/edit",
      "/inventory-management/reservations/reservation-1/edit",
      <ReservationEditPage />
    );
    await user.type(await screen.findByLabelText(/^Reservation number/u), "RES-002");
    await user.type(screen.getByLabelText(/^Reference module/u), "sales");
    await user.type(screen.getByLabelText(/^Reference type/u), "order");
    await user.type(screen.getByLabelText(/^Reference ID/u), "order-1");
    await user.type(screen.getByLabelText(/^Item ID/u), "item-1");
    await user.type(screen.getByLabelText(/^Warehouse ID/u), "warehouse-1");
    const reservationQuantity = screen.getByLabelText(/^Quantity/u);
    await user.clear(reservationQuantity);
    await user.type(reservationQuantity, "0");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(reservationQuantity).toBeInvalid();
    expect(updateReservation).not.toHaveBeenCalled();
    reservationEdit.unmount();

    const cycleEdit = renderInventoryRoute(
      "/inventory-management/cycle-counts/:id/edit",
      "/inventory-management/cycle-counts/count-1/edit",
      <CycleCountEditPage />
    );
    await user.type(await screen.findByLabelText(/^Count number/u), "COUNT-2");
    await user.type(screen.getByLabelText(/^Warehouse ID/u), "warehouse-1");
    await user.clear(screen.getByLabelText(/^Count type/u));
    await user.type(screen.getByLabelText(/^Count type/u), "cycle");
    await user.type(screen.getByLabelText(/^Scheduled for/u), "2026-08-11");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(updateCycleCount).toHaveBeenCalledWith(
        "count-1",
        { location_id: null, scheduled_for: "2026-08-11", count_type: "cycle" },
        10
      )
    );
    cycleEdit.unmount();
  });

  it("renders item list fallback values when service records omit optional metadata", async () => {
    vi.spyOn(inventoryService, "listItems").mockResolvedValue(
      page([item({ category: "", reorder_point: null, is_active: false })])
    );

    renderInventoryRoute(
      "/inventory-management/items",
      "/inventory-management/items",
      <ItemListPage />
    );

    expect(await screen.findByText("SKU-001")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.getByText("batch · fifo")).toBeInTheDocument();
  });

  it("maps location, batch, serial, stock entry, balance, and cycle count list rows", async () => {
    vi.spyOn(inventoryService, "listLocations").mockResolvedValue(page([location()]));
    vi.spyOn(inventoryService, "listBatches").mockResolvedValue(page([batch()]));
    vi.spyOn(inventoryService, "listSerials").mockResolvedValue(page([serial()]));
    vi.spyOn(inventoryService, "listStockEntries").mockResolvedValue(page([stockEntry()]));
    vi.spyOn(inventoryService, "listBalances").mockResolvedValue(
      page([
        {
          id: "balance-1",
          item: summary({ id: "item-1", code: "SKU-001", name: "Tracked component" }),
          warehouse: summary({ id: "warehouse-1", code: "WH-MUM", name: "Mumbai DC" }),
          location: summary({ id: "location-1", code: "BIN-01", name: "Pick face" }),
          batch: null,
          serial_number: null,
          quantity_on_hand: "10.000000",
          quantity_allocated: "2.000000",
          quantity_available: "8.000000",
          stock_value: "110.00",
          valuation_rate: "11.00",
          last_ledger_entry_id: "ledger-1",
          created_at: "2026-08-03T10:00:00Z",
          updated_at: "2026-08-03T10:00:00Z",
        } as never,
      ])
    );
    vi.spyOn(inventoryService, "listCycleCounts").mockResolvedValue(page([cycleCount()]));

    const locationList = renderInventoryRoute(
      "/inventory-management/locations",
      "/inventory-management/locations",
      <LocationListPage />
    );
    expect(await screen.findByText("BIN-01")).toBeInTheDocument();
    locationList.unmount();

    const batchList = renderInventoryRoute(
      "/inventory-management/batches",
      "/inventory-management/batches",
      <BatchListPage />
    );
    expect(await screen.findByText("BATCH-1")).toBeInTheDocument();
    batchList.unmount();

    const serialList = renderInventoryRoute(
      "/inventory-management/serials",
      "/inventory-management/serials",
      <SerialListPage />
    );
    expect(await screen.findByText("SER-1")).toBeInTheDocument();
    serialList.unmount();

    const stockEntryList = renderInventoryRoute(
      "/inventory-management/stock-entries",
      "/inventory-management/stock-entries",
      <StockEntryListPage />
    );
    expect(await screen.findByText("STK-1")).toBeInTheDocument();
    stockEntryList.unmount();

    renderInventoryRoute(
      "/inventory-management/stock-balances",
      "/inventory-management/stock-balances",
      <StockBalanceListPage />
    );
    expect(await screen.findByText("Available 8.000000")).toBeInTheDocument();
  });

  it("creates and edits additional inventory resources through descriptor-owned service calls", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "resource-key" });
    vi.spyOn(inventoryService, "createLocation").mockResolvedValue(result(location()));
    vi.spyOn(inventoryService, "createBatch").mockResolvedValue(result(batch()));
    vi.spyOn(inventoryService, "createSerial").mockResolvedValue(result(serial()));
    vi.spyOn(inventoryService, "createCycleCount").mockResolvedValue(result(cycleCount()));

    const locationCreate = renderInventoryRoute(
      "/inventory-management/locations/new",
      "/inventory-management/locations/new",
      <LocationCreatePage />
    );
    await user.type(screen.getByLabelText(/^Warehouse ID/u), "warehouse-1");
    await user.type(screen.getByLabelText(/^Location code/u), "BIN-01");
    await user.type(screen.getByLabelText(/^Location name/u), "Pick face");
    await user.click(screen.getByRole("button", { name: "Create location" }));
    await waitFor(() =>
      expect(inventoryService.createLocation).toHaveBeenCalledWith(
        expect.objectContaining({ warehouse_id: "warehouse-1", barcode: "" }),
        "inventory:location:create:resource-key"
      )
    );
    locationCreate.unmount();

    const batchCreate = renderInventoryRoute(
      "/inventory-management/batches/new",
      "/inventory-management/batches/new",
      <BatchCreatePage />
    );
    await user.type(screen.getByLabelText(/^Batch-tracked item ID/u), "item-1");
    await user.type(screen.getByLabelText(/^Batch number/u), "BATCH-1");
    await user.click(screen.getByRole("button", { name: "Create batch" }));
    await waitFor(() =>
      expect(inventoryService.createBatch).toHaveBeenCalledWith(
        expect.objectContaining({ manufactured_on: null, expires_on: null }),
        "inventory:batch:create:resource-key"
      )
    );
    batchCreate.unmount();

    const serialCreate = renderInventoryRoute(
      "/inventory-management/serials/new",
      "/inventory-management/serials/new",
      <SerialCreatePage />
    );
    await user.type(screen.getByLabelText(/^Serial-tracked item ID/u), "item-1");
    await user.type(screen.getByLabelText(/^Serial number/u), "SER-1");
    await user.click(screen.getByRole("button", { name: "Create serial number" }));
    await waitFor(() =>
      expect(inventoryService.createSerial).toHaveBeenCalledWith(
        expect.objectContaining({ warranty_starts_on: null, warranty_ends_on: null }),
        "inventory:serial:create:resource-key"
      )
    );
    serialCreate.unmount();

    renderInventoryRoute(
      "/inventory-management/cycle-counts/new",
      "/inventory-management/cycle-counts/new",
      <CycleCountCreatePage />
    );
    await user.type(screen.getByLabelText(/^Count number/u), "COUNT-1");
    await user.type(screen.getByLabelText(/^Warehouse ID/u), "warehouse-1");
    await user.type(screen.getByLabelText(/^Scheduled for/u), "2026-08-10");
    await user.click(screen.getByRole("button", { name: "Create cycle count" }));
    await waitFor(() =>
      expect(inventoryService.createCycleCount).toHaveBeenCalledWith(
        expect.objectContaining({ location_id: null, count_type: "full" }),
        "inventory:cycleCount:create:resource-key"
      )
    );
  });

  it("creates governed stock entries with normalized line payload boundaries", async () => {
    vi.stubGlobal("crypto", { randomUUID: () => "stock-entry-key" });
    vi.spyOn(inventoryService, "createStockEntry").mockResolvedValue(result(stockEntry()));

    renderInventoryRoute(
      "/inventory-management/stock-entries/new",
      "/inventory-management/stock-entries/new",
      <StockEntryCreatePage />
    );

    fireEvent.change(screen.getByLabelText(/^Entry number/u), { target: { value: "STK-NEW" } });
    fireEvent.change(screen.getByLabelText(/^Entry type/u), { target: { value: "transfer" } });
    fireEvent.change(screen.getByLabelText(/^Posting time/u), {
      target: { value: "2026-08-03T10:30" },
    });
    fireEvent.change(screen.getByLabelText(/^Source warehouse ID/u), {
      target: { value: "warehouse-source" },
    });
    fireEvent.change(screen.getByLabelText(/^Destination warehouse ID/u), {
      target: { value: "warehouse-dest" },
    });
    fireEvent.change(screen.getByLabelText(/^Line item ID/u), { target: { value: "item-1" } });
    fireEvent.change(screen.getByLabelText(/^Destination location ID/u), {
      target: { value: "location-dest" },
    });
    fireEvent.change(screen.getByLabelText(/^Quantity/u), { target: { value: "7.500000" } });
    fireEvent.change(screen.getByLabelText(/^UOM/u), { target: { value: "KG" } });
    fireEvent.submit(screen.getByRole("button", { name: "Create stock entry" }).closest("form")!);

    await waitFor(() =>
      expect(inventoryService.createStockEntry).toHaveBeenCalledWith(
        {
          entry_number: "STK-NEW",
          entry_type: "transfer",
          posting_at: "2026-08-03T10:30",
          source_warehouse_id: "warehouse-source",
          destination_warehouse_id: "warehouse-dest",
          lines: [
            {
              line_number: 1,
              item_id: "item-1",
              source_location_id: null,
              destination_location_id: "location-dest",
              quantity: "7.500000",
              uom: "KG",
              unit_cost: null,
            },
          ],
        },
        "inventory:stockEntry:create:stock-entry-key"
      )
    );
  });

  it("renders dashboard, configuration list/detail/history/export/import/rollback workflows", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "config-key" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(inventoryService, "dashboard").mockResolvedValue(
      result({
        metrics: [{ label: "Available SKUs", value: "12", trend: "up" }],
        alerts: [
          {
            id: "alert-1",
            severity: "warning",
            title: "Low stock",
            detail: "SKU-001 below reorder",
            resource_url: "/inventory-management/items/item-1",
          },
        ],
        recent_entries: [],
        low_stock_items: [],
        onboarding: {
          warehouse_created: true,
          item_created: true,
          first_receipt_posted: true,
          first_issue_posted: false,
        },
      } as never)
    );
    vi.spyOn(inventoryService, "listConfigurations").mockResolvedValue(
      page([configuration, { ...configuration, environment: "production", status: "active" }])
    );
    vi.spyOn(inventoryService, "getConfiguration").mockResolvedValue(
      result({
        ...configuration,
        allowed_commands: [
          { name: "activate", label: "Activate", destructive: false, requires_confirmation: true },
        ],
      })
    );
    vi.spyOn(inventoryService, "activateConfiguration").mockResolvedValue(
      result({ ...configuration, status: "active" })
    );
    vi.spyOn(inventoryService, "configurationHistory").mockResolvedValue(
      page([
        {
          id: "rev-4",
          revision: 4,
          snapshot: { ...configuration, change_reason: "initial" },
          change_reason: "initial",
          changed_by_id: "user-1",
          correlation_id: "corr-history",
          created_at: "2026-08-03T10:00:00Z",
        } as never,
      ])
    );
    vi.spyOn(inventoryService, "exportConfiguration").mockResolvedValue(
      result({
        schema_version: "1.0",
        environment: "development",
        exported_at: "2026-08-03T10:00:00Z",
        checksum: "sha256:abc",
        configuration: { ...configuration, change_reason: "exported" },
      } as never)
    );
    vi.spyOn(inventoryService, "importConfiguration").mockResolvedValue(result(configuration));
    vi.spyOn(inventoryService, "rollbackConfiguration").mockResolvedValue(result(configuration));

    const dashboard = renderInventoryRoute("/", "/", <InventoryDashboardPage />);
    expect(await screen.findByText("Available SKUs")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Low stock/u }));
    dashboard.unmount();

    const list = renderInventoryRoute(
      "/inventory-management/configurations",
      "/inventory-management/configurations",
      <ConfigurationListPage />
    );
    expect(await screen.findByText("draft · revision 4")).toBeInTheDocument();
    list.unmount();

    const detail = renderInventoryRoute(
      "/inventory-management/configurations/:environment",
      "/inventory-management/configurations/development",
      <ConfigurationDetailPage />
    );
    await user.click(await screen.findByRole("button", { name: "Activate" }));
    await waitFor(() =>
      expect(inventoryService.activateConfiguration).toHaveBeenCalledWith(
        "development",
        { revision: 4, change_reason: "Activated from inventory settings" },
        "inventory:configuration-activate:development:config-key"
      )
    );
    detail.unmount();

    const history = renderInventoryRoute(
      "/inventory-management/configurations/:environment/history",
      "/inventory-management/configurations/development/history",
      <ConfigurationHistoryPage />
    );
    expect(await screen.findByText("corr-history")).toBeInTheDocument();
    history.unmount();

    const anchor = document.createElement("a");
    vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    const createElement = vi.spyOn(document, "createElement").mockImplementation((tag) => {
      if (tag === "a") return anchor;
      return Document.prototype.createElement.call(document, tag);
    });
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:config"),
      revokeObjectURL: vi.fn(),
    });
    renderInventoryRoute(
      "/inventory-management/configurations/:environment/export",
      "/inventory-management/configurations/development/export",
      <ConfigurationExportPage />
    );
    await user.click(await screen.findByRole("button", { name: /Download JSON/u }));
    expect(createElement).toHaveBeenCalledWith("a");
    createElement.mockRestore();
  });

  it("validates configuration edit, import, rollback, bulk import, and trace paths", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "flow-key" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(inventoryService, "getConfiguration").mockResolvedValue(result(configuration));
    vi.spyOn(inventoryService, "createConfigurationRevision").mockResolvedValue(
      result({ ...configuration, active_revision: 5 })
    );
    vi.spyOn(inventoryService, "importConfiguration").mockResolvedValue(result(configuration));
    vi.spyOn(inventoryService, "rollbackConfiguration").mockResolvedValue(result(configuration));
    vi.spyOn(inventoryService, "enqueueImport").mockResolvedValue(
      result({
        id: "job-1",
        status: "queued",
        resource_type: "items",
        idempotency_key: "flow-key",
        created_at: "2026-08-03T10:00:00Z",
        completed_at: null,
        problem: null,
      } as never)
    );
    vi.spyOn(inventoryService, "traceBatch").mockResolvedValue(result([ledgerEntry()]));
    vi.spyOn(inventoryService, "traceSerial").mockResolvedValue(result([]));

    const edit = renderInventoryRoute(
      "/inventory-management/configurations/:environment/edit",
      "/inventory-management/configurations/development/edit",
      <ConfigurationEditPage />
    );
    await user.clear(await screen.findByLabelText("Change reason *"));
    await user.type(screen.getByLabelText("Change reason *"), "Tune limits");
    await user.click(screen.getByRole("button", { name: "Create revision and preview" }));
    await waitFor(() =>
      expect(inventoryService.createConfigurationRevision).toHaveBeenCalledWith(
        "development",
        expect.objectContaining({ change_reason: "Tune limits" }),
        4
      )
    );
    edit.unmount();

    const importPage = renderInventoryRoute(
      "/inventory-management/configurations/:environment/import",
      "/inventory-management/configurations/development/import",
      <ConfigurationImportPage />
    );
    fireEvent.change(screen.getByLabelText("Configuration JSON"), {
      target: {
        value: JSON.stringify({
          schema_version: "1.0",
          environment: "development",
          exported_at: "2026-08-03T10:00:00Z",
          checksum: "sha256:def",
          configuration: { ...configuration, change_reason: "imported" },
        }),
      },
    });
    await user.type(screen.getByLabelText("Change reason"), "Promote tested settings");
    await user.click(screen.getByRole("button", { name: "Validate and import" }));
    await waitFor(() =>
      expect(inventoryService.importConfiguration).toHaveBeenCalledWith(
        "development",
        expect.objectContaining({ change_reason: "Promote tested settings" }),
        "inventory:configuration-import:development:flow-key"
      )
    );
    importPage.unmount();

    const rollback = renderInventoryRoute(
      "/inventory-management/configurations/:environment/rollback",
      "/inventory-management/configurations/development/rollback?revision=3",
      <ConfigurationRollbackPage />
    );
    await user.type(screen.getByLabelText("Rollback reason"), "Undo unsafe change");
    await user.click(screen.getByRole("button", { name: "Create rollback revision" }));
    await waitFor(() =>
      expect(inventoryService.rollbackConfiguration).toHaveBeenCalledWith(
        "development",
        { revision: 3, change_reason: "Undo unsafe change" },
        "inventory:configuration-rollback:development:3:flow-key"
      )
    );
    rollback.unmount();

    const bulk = renderInventoryRoute(
      "/inventory-management/import",
      "/inventory-management/import",
      <BulkImportPage />
    );
    await user.type(screen.getByLabelText("Validated row count"), "3");
    await user.type(screen.getByLabelText("Uploaded document reference"), "doc://inventory.csv");
    await user.click(screen.getByRole("button", { name: "Queue validated import" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Job job-1");
    bulk.unmount();

    const trace = renderInventoryRoute(
      "/inventory-management/batches/:id/trace",
      "/inventory-management/batches/batch-1/trace",
      <BatchTracePage />
    );
    expect(await screen.findByText("#42")).toBeInTheDocument();
    trace.unmount();

    renderInventoryRoute(
      "/inventory-management/serials/:id/trace",
      "/inventory-management/serials/serial-1/trace",
      <SerialTracePage />
    );
    expect(await screen.findByText("No posted movements")).toBeInTheDocument();
  });

  it("blocks destructive inventory detail commands when confirmation is denied", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "blocked-command-key" });
    vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.spyOn(inventoryService, "getWarehouse").mockResolvedValue(result(warehouse()));
    const archiveWarehouse = vi.spyOn(inventoryService, "archiveWarehouse");

    renderInventoryRoute(
      "/inventory-management/warehouses/:id",
      "/inventory-management/warehouses/warehouse-1",
      <WarehouseDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "Mumbai DC" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Archive" }));

    expect(window.confirm).toHaveBeenCalledWith(
      "Archive Mumbai DC? This action may be irreversible and will be audited."
    );
    expect(archiveWarehouse).not.toHaveBeenCalled();
  });

  it("refuses unsafe configuration revisions before creating server-side policy drafts", async () => {
    const user = userEvent.setup();
    vi.spyOn(inventoryService, "getConfiguration").mockResolvedValue(result(configuration));
    const createConfigurationRevision = vi.spyOn(inventoryService, "createConfigurationRevision");

    renderInventoryRoute(
      "/inventory-management/configurations/:environment/edit",
      "/inventory-management/configurations/development/edit",
      <ConfigurationEditPage />
    );

    const maxLines = await screen.findByLabelText("Maximum lines per stock entry");
    await user.clear(maxLines);
    await user.type(maxLines, "0");
    await user.clear(screen.getByLabelText("Change reason *"));
    await user.type(screen.getByLabelText("Change reason *"), "Unsafe lower bound");
    await user.click(screen.getByRole("button", { name: "Create revision and preview" }));

    expect(maxLines).toBeInvalid();
    expect(createConfigurationRevision).not.toHaveBeenCalled();
  });

  it("bounds bulk import queueing and sends the selected resource payload exactly once", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "bulk-key" });
    const enqueueImport = vi.spyOn(inventoryService, "enqueueImport").mockResolvedValue(
      result({
        id: "job-bulk",
        status: "queued",
        resource_type: "warehouses",
        idempotency_key: "bulk-key",
        created_at: "2026-08-03T10:00:00Z",
        completed_at: null,
        problem: null,
      } as never)
    );

    renderInventoryRoute(
      "/inventory-management/import",
      "/inventory-management/import",
      <BulkImportPage />
    );

    expect(screen.getByRole("button", { name: "Queue validated import" })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Resource type"), "warehouses");
    await user.type(screen.getByLabelText("Validated row count"), "0");
    await user.type(screen.getByLabelText("Uploaded document reference"), "doc://warehouse.csv");
    expect(screen.getByRole("button", { name: "Queue validated import" })).toBeDisabled();

    await user.clear(screen.getByLabelText("Validated row count"));
    await user.type(screen.getByLabelText("Validated row count"), "12");
    await user.click(screen.getByRole("button", { name: "Queue validated import" }));

    await waitFor(() =>
      expect(enqueueImport).toHaveBeenCalledWith(
        {
          resource_type: "warehouses",
          document_ref: "doc://warehouse.csv",
          row_count: 12,
        },
        "inventory:bulk-import:bulk-key"
      )
    );
    expect(enqueueImport).toHaveBeenCalledOnce();
  });

  it("surfaces retryable list failures and recovers through the governed retry action", async () => {
    const listLocations = vi
      .spyOn(inventoryService, "listLocations")
      .mockRejectedValueOnce(
        new ApiError("location index unavailable", 503, {}, "unavailable", "corr-location-list")
      )
      .mockResolvedValueOnce(page([location()]));

    renderInventoryRoute(
      "/inventory-management/locations",
      "/inventory-management/locations",
      <LocationListPage />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("location index unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("BIN-01")).toBeInTheDocument();
    expect(listLocations).toHaveBeenCalledTimes(2);
  });

  it("fails closed when detail payloads are unavailable or unsupported commands error", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "detail-error-key" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(inventoryService, "getItem").mockResolvedValue(result(null as never));

    const missing = renderInventoryRoute(
      "/inventory-management/items/:id",
      "/inventory-management/items/item-missing",
      <ItemDetailPage />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Inventory could not be loaded");
    missing.unmount();

    vi.spyOn(inventoryService, "getWarehouse").mockResolvedValue(result(warehouse()));
    vi.spyOn(inventoryService, "archiveWarehouse").mockRejectedValue(
      new ApiError("archive denied by policy", 409, {}, "conflict", "corr-archive")
    );

    renderInventoryRoute(
      "/inventory-management/warehouses/:id",
      "/inventory-management/warehouses/warehouse-1",
      <WarehouseDetailPage />
    );

    await user.click(await screen.findByRole("button", { name: "Archive" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("archive denied by policy");
  });

  it("guards dirty create forms before navigating away", async () => {
    const user = userEvent.setup();
    const confirm = vi
      .spyOn(window, "confirm")
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);

    renderInventoryRoute(
      "/inventory-management/warehouses/new",
      "/inventory-management/warehouses/new",
      <WarehouseCreatePage />
    );

    await user.type(screen.getByLabelText(/^Warehouse code/u), "WH-DIRTY");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalledWith("Discard unsaved changes?");
    expect(screen.getByRole("heading", { name: "Create warehouse" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByTestId("navigated")).toBeInTheDocument();
  });

  it("renders dashboard and configuration empty states without leaking stale actions", async () => {
    vi.spyOn(inventoryService, "dashboard").mockResolvedValue(
      result({
        metrics: [{ label: "Open reservations", value: "0", trend: null }],
        alerts: [],
        recent_entries: [],
        low_stock_items: [],
        onboarding: {
          warehouse_created: false,
          item_created: false,
          first_receipt_posted: false,
          first_issue_posted: false,
        },
      } as never)
    );
    vi.spyOn(inventoryService, "listConfigurations").mockResolvedValue(page([]));

    const dashboard = renderInventoryRoute("/", "/", <InventoryDashboardPage />);
    expect(await screen.findByText("Open reservations")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View stock balances" }));
    expect(screen.getByTestId("navigated")).toBeInTheDocument();
    dashboard.unmount();

    renderInventoryRoute(
      "/inventory-management/configurations",
      "/inventory-management/configurations",
      <ConfigurationListPage />
    );

    expect(
      await screen.findByRole("heading", { name: "No inventory configuration" })
    ).toBeInTheDocument();
  });

  it("keeps configuration activation, import, rollback, and bulk import failures visible", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "failure-key" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(inventoryService, "getConfiguration").mockResolvedValue(
      result({
        ...configuration,
        allowed_commands: [
          { name: "activate", label: "Activate", destructive: false, requires_confirmation: true },
        ],
      })
    );
    vi.spyOn(inventoryService, "activateConfiguration").mockRejectedValue(
      new ApiError("activation blocked", 409, {}, "conflict", "corr-activate")
    );
    vi.spyOn(inventoryService, "importConfiguration").mockRejectedValue(
      new ApiError("checksum mismatch", 422, {}, "invalid", "corr-import")
    );
    vi.spyOn(inventoryService, "rollbackConfiguration").mockRejectedValue(
      new ApiError("revision locked", 409, {}, "conflict", "corr-rollback")
    );
    vi.spyOn(inventoryService, "enqueueImport").mockRejectedValue(
      new ApiError("document missing", 404, {}, "not_found", "corr-bulk")
    );

    const detail = renderInventoryRoute(
      "/inventory-management/configurations/:environment",
      "/inventory-management/configurations/production",
      <ConfigurationDetailPage />
    );
    await user.click(await screen.findByRole("button", { name: "Activate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("activation blocked");
    detail.unmount();

    const importPage = renderInventoryRoute(
      "/inventory-management/configurations/:environment/import",
      "/inventory-management/configurations/production/import",
      <ConfigurationImportPage />
    );
    fireEvent.change(screen.getByLabelText("Configuration JSON"), {
      target: { value: JSON.stringify({ schema_version: "1.0", configuration }) },
    });
    await user.type(screen.getByLabelText("Change reason"), "Reject invalid checksum");
    await user.click(screen.getByRole("button", { name: "Validate and import" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("checksum mismatch");
    importPage.unmount();

    const rollback = renderInventoryRoute(
      "/inventory-management/configurations/:environment/rollback",
      "/inventory-management/configurations/production/rollback?revision=2",
      <ConfigurationRollbackPage />
    );
    await user.type(screen.getByLabelText("Rollback reason"), "Restore prior settings");
    await user.click(screen.getByRole("button", { name: "Create rollback revision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("revision locked");
    rollback.unmount();

    renderInventoryRoute(
      "/inventory-management/import",
      "/inventory-management/import",
      <BulkImportPage />
    );
    await user.type(screen.getByLabelText("Validated row count"), "2");
    await user.type(screen.getByLabelText("Uploaded document reference"), "doc://missing.csv");
    await user.click(screen.getByRole("button", { name: "Queue validated import" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Inventory record unavailable");
  });

  it("validates configuration bounds and malformed import documents before persistence", async () => {
    const user = userEvent.setup();
    vi.spyOn(inventoryService, "getConfiguration").mockResolvedValue(result(configuration));
    const createConfigurationRevision = vi.spyOn(inventoryService, "createConfigurationRevision");
    const importConfiguration = vi.spyOn(inventoryService, "importConfiguration");

    const edit = renderInventoryRoute(
      "/inventory-management/configurations/:environment/edit",
      "/inventory-management/configurations/development/edit",
      <ConfigurationEditPage />
    );
    await user.clear(await screen.findByLabelText("Default reservation TTL (minutes)"));
    await user.type(screen.getByLabelText("Default reservation TTL (minutes)"), "10081");
    fireEvent.submit(
      screen.getByRole("button", { name: "Create revision and preview" }).closest("form")!
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Inventory could not be loaded");
    expect(createConfigurationRevision).not.toHaveBeenCalled();
    edit.unmount();

    renderInventoryRoute(
      "/inventory-management/configurations/:environment/import",
      "/inventory-management/configurations/development/import",
      <ConfigurationImportPage />
    );
    fireEvent.change(screen.getByLabelText("Configuration JSON"), {
      target: { value: "{bad json" },
    });
    await user.type(screen.getByLabelText("Change reason"), "Malformed import test");
    await user.click(screen.getByRole("button", { name: "Validate and import" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Inventory could not be loaded");
    expect(importConfiguration).not.toHaveBeenCalled();
  });

  it("renders trace and configuration-history failures through retryable governed errors", async () => {
    vi.spyOn(inventoryService, "traceBatch").mockRejectedValue(
      new ApiError("trace service down", 503, {}, "unavailable", "corr-trace")
    );
    vi.spyOn(inventoryService, "configurationHistory").mockRejectedValue(
      new ApiError("history unavailable", 503, {}, "unavailable", "corr-history-error")
    );

    const trace = renderInventoryRoute(
      "/inventory-management/batches/:id/trace",
      "/inventory-management/batches/batch-1/trace",
      <BatchTracePage />
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("trace service down");
    trace.unmount();

    renderInventoryRoute(
      "/inventory-management/configurations/:environment/history",
      "/inventory-management/configurations/staging/history",
      <ConfigurationHistoryPage />
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("history unavailable");
  });
});
