/* eslint-disable max-lines-per-function -- route descriptor parity intentionally snapshots the governed route table. */
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { createElement, Suspense } from "react";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { ROUTES } from "./contracts";

vi.mock("./pages/InventoryPages", () => ({
  InventoryDashboardPage: () => "inventory.dashboard.page",
  WarehouseListPage: () => "inventory.warehouses.page",
  ItemListPage: () => "inventory.items.page",
  StockEntryListPage: () => "inventory.stock-entries.page",
  StockBalanceListPage: () => "inventory.stock-balances.page",
  ReservationListPage: () => "inventory.reservations.page",
  CycleCountListPage: () => "inventory.cycle-counts.page",
  ConfigurationListPage: () => "inventory.settings.page",
  WarehouseCreatePage: () => "inventory.warehouse-new.page",
  WarehouseDetailPage: () => "inventory.warehouse-detail.page",
  WarehouseEditPage: () => "inventory.warehouse-edit.page",
  LocationListPage: () => "inventory.locations.page",
  LocationCreatePage: () => "inventory.location-new.page",
  LocationDetailPage: () => "inventory.location-detail.page",
  LocationEditPage: () => "inventory.location-edit.page",
  ItemCreatePage: () => "inventory.item-new.page",
  ItemDetailPage: () => "inventory.item-detail.page",
  ItemEditPage: () => "inventory.item-edit.page",
  BatchListPage: () => "inventory.batches.page",
  BatchCreatePage: () => "inventory.batch-new.page",
  BatchDetailPage: () => "inventory.batch-detail.page",
  BatchEditPage: () => "inventory.batch-edit.page",
  BatchTracePage: () => "inventory.batch-trace.page",
  SerialListPage: () => "inventory.serials.page",
  SerialCreatePage: () => "inventory.serial-new.page",
  SerialDetailPage: () => "inventory.serial-detail.page",
  SerialEditPage: () => "inventory.serial-edit.page",
  SerialTracePage: () => "inventory.serial-trace.page",
  StockEntryCreatePage: () => "inventory.stock-entry-new.page",
  StockEntryDetailPage: () => "inventory.stock-entry-detail.page",
  StockEntryEditPage: () => "inventory.stock-entry-edit.page",
  StockBalanceDetailPage: () => "inventory.stock-balance-detail.page",
  StockLedgerListPage: () => "inventory.stock-ledger.page",
  StockLedgerDetailPage: () => "inventory.stock-ledger-detail.page",
  ReservationCreatePage: () => "inventory.reservation-new.page",
  ReservationDetailPage: () => "inventory.reservation-detail.page",
  ReservationEditPage: () => "inventory.reservation-edit.page",
  CycleCountCreatePage: () => "inventory.cycle-count-new.page",
  CycleCountDetailPage: () => "inventory.cycle-count-detail.page",
  CycleCountEditPage: () => "inventory.cycle-count-edit.page",
  BulkImportPage: () => "inventory.bulk-import.page",
  ConfigurationDetailPage: () => "inventory.configuration-detail.page",
  ConfigurationEditPage: () => "inventory.configuration-edit.page",
  ConfigurationHistoryPage: () => "inventory.configuration-history.page",
  ConfigurationPreviewPage: () => "inventory.configuration-preview.page",
  ConfigurationImportPage: () => "inventory.configuration-import.page",
  ConfigurationExportPage: () => "inventory.configuration-export.page",
  ConfigurationRollbackPage: () => "inventory.configuration-rollback.page",
}));

const moduleSources = import.meta.glob<string>(["./**/*.ts", "./**/*.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
});
const getTenantRoutes = async () => {
  vi.resetModules();
  const { tenantRoutes } = await import("./routes");
  return tenantRoutes;
};

describe("inventory tenant routes", () => {
  afterEach(() => {
    cleanup();
  });

  it("publishes a unique, valid registry with eight sidebar destinations", async () => {
    const routes = await getTenantRoutes();
    expect(getTenantRouteValidationIssues(routes)).toEqual([]);
    expect(new Set(routes.map((route) => route.id)).size).toBe(routes.length);
    expect(new Set(routes.map((route) => route.path)).size).toBe(routes.length);
    expect(routes.map((route) => route.module)).toEqual(
      Array.from({ length: routes.length }, () => "inventory_management")
    );
    expect(routes.map((route) => route.sourceFile)).toEqual(
      Array.from({ length: routes.length }, () => "inventory_management/routes.ts")
    );
    expect(routes.filter((route) => route.navigation.type === "sidebar")).toHaveLength(8);
  });

  it("resolves every contextual route to an inventory sidebar parent", async () => {
    const routes = await getTenantRoutes();
    const byId = new Map(routes.map((route) => [route.id, route]));
    for (const route of routes) {
      if (route.navigation.type !== "contextual") continue;
      const parent = byId.get(route.navigation.parentRouteId);
      expect(parent?.module).toBe("inventory_management");
      expect(parent?.navigation.type).toBe("sidebar");
    }
  });

  it("keeps sidebar and route contract parity", async () => {
    const routes = await getTenantRoutes();
    const sidebarPaths = routes
      .filter((route) => route.navigation.type === "sidebar")
      .map((route) => route.path);
    expect(sidebarPaths).toEqual([
      ROUTES.DASHBOARD,
      ROUTES.WAREHOUSES,
      ROUTES.ITEMS,
      ROUTES.STOCK_ENTRIES,
      ROUTES.STOCK_BALANCES,
      ROUTES.RESERVATIONS,
      ROUTES.CYCLE_COUNTS,
      ROUTES.SETTINGS,
    ]);
    expect(
      routes
        .filter((route) => route.navigation.type === "sidebar")
        .map((route) => (route.navigation.type === "sidebar" ? route.navigation.label : ""))
    ).toEqual([
      "Inventory dashboard",
      "Warehouses",
      "Items",
      "Stock entries",
      "Stock balances",
      "Reservations",
      "Cycle counts",
      "Inventory settings",
    ]);
  });

  it("keeps inventory dashboard and stock route descriptors stable", async () => {
    const routes = await getTenantRoutes();
    expect(
      routes.slice(0, 34).map((route) => ({
        id: route.id,
        path: route.path,
        title: route.title,
        navigation:
          route.navigation.type === "sidebar"
            ? { type: "sidebar", order: route.navigation.order }
            : { type: "contextual", parentRouteId: route.navigation.parentRouteId },
      }))
    ).toEqual([
      {
        id: "inventory.dashboard",
        path: ROUTES.DASHBOARD,
        title: "Inventory dashboard",
        navigation: { type: "sidebar", order: 400 },
      },
      {
        id: "inventory.warehouses",
        path: ROUTES.WAREHOUSES,
        title: "Warehouses",
        navigation: { type: "sidebar", order: 410 },
      },
      {
        id: "inventory.items",
        path: ROUTES.ITEMS,
        title: "Items",
        navigation: { type: "sidebar", order: 420 },
      },
      {
        id: "inventory.stock-entries",
        path: ROUTES.STOCK_ENTRIES,
        title: "Stock entries",
        navigation: { type: "sidebar", order: 430 },
      },
      {
        id: "inventory.stock-balances",
        path: ROUTES.STOCK_BALANCES,
        title: "Stock balances",
        navigation: { type: "sidebar", order: 440 },
      },
      {
        id: "inventory.reservations",
        path: ROUTES.RESERVATIONS,
        title: "Reservations",
        navigation: { type: "sidebar", order: 450 },
      },
      {
        id: "inventory.cycle-counts",
        path: ROUTES.CYCLE_COUNTS,
        title: "Cycle counts",
        navigation: { type: "sidebar", order: 460 },
      },
      {
        id: "inventory.settings",
        path: ROUTES.SETTINGS,
        title: "Inventory settings",
        navigation: { type: "sidebar", order: 470 },
      },
      {
        id: "inventory.warehouse-new",
        path: ROUTES.WAREHOUSE_NEW,
        title: "Create warehouse",
        navigation: { type: "contextual", parentRouteId: "inventory.warehouses" },
      },
      {
        id: "inventory.warehouse-detail",
        path: ROUTES.WAREHOUSE_DETAIL,
        title: "Warehouse",
        navigation: { type: "contextual", parentRouteId: "inventory.warehouses" },
      },
      {
        id: "inventory.warehouse-edit",
        path: ROUTES.WAREHOUSE_EDIT,
        title: "Edit warehouse",
        navigation: { type: "contextual", parentRouteId: "inventory.warehouses" },
      },
      {
        id: "inventory.locations",
        path: ROUTES.LOCATIONS,
        title: "Locations",
        navigation: { type: "contextual", parentRouteId: "inventory.warehouses" },
      },
      {
        id: "inventory.location-new",
        path: ROUTES.LOCATION_NEW,
        title: "Create location",
        navigation: { type: "contextual", parentRouteId: "inventory.warehouses" },
      },
      {
        id: "inventory.location-detail",
        path: ROUTES.LOCATION_DETAIL,
        title: "Location",
        navigation: { type: "contextual", parentRouteId: "inventory.warehouses" },
      },
      {
        id: "inventory.location-edit",
        path: ROUTES.LOCATION_EDIT,
        title: "Edit location",
        navigation: { type: "contextual", parentRouteId: "inventory.warehouses" },
      },
      {
        id: "inventory.item-new",
        path: ROUTES.ITEM_NEW,
        title: "Create item",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.item-detail",
        path: ROUTES.ITEM_DETAIL,
        title: "Item",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.item-edit",
        path: ROUTES.ITEM_EDIT,
        title: "Edit item",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.batches",
        path: ROUTES.BATCHES,
        title: "Batches",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.batch-new",
        path: ROUTES.BATCH_NEW,
        title: "Register batch",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.batch-detail",
        path: ROUTES.BATCH_DETAIL,
        title: "Batch",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.batch-edit",
        path: ROUTES.BATCH_EDIT,
        title: "Edit batch",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.batch-trace",
        path: ROUTES.BATCH_TRACE,
        title: "Batch trace",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.serials",
        path: ROUTES.SERIALS,
        title: "Serial numbers",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.serial-new",
        path: ROUTES.SERIAL_NEW,
        title: "Register serial number",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.serial-detail",
        path: ROUTES.SERIAL_DETAIL,
        title: "Serial number",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.serial-edit",
        path: ROUTES.SERIAL_EDIT,
        title: "Edit serial number",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.serial-trace",
        path: ROUTES.SERIAL_TRACE,
        title: "Serial trace",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.stock-entry-new",
        path: ROUTES.STOCK_ENTRY_NEW,
        title: "Create stock entry",
        navigation: { type: "contextual", parentRouteId: "inventory.stock-entries" },
      },
      {
        id: "inventory.stock-entry-detail",
        path: ROUTES.STOCK_ENTRY_DETAIL,
        title: "Stock entry",
        navigation: { type: "contextual", parentRouteId: "inventory.stock-entries" },
      },
      {
        id: "inventory.stock-entry-edit",
        path: ROUTES.STOCK_ENTRY_EDIT,
        title: "Edit stock entry",
        navigation: { type: "contextual", parentRouteId: "inventory.stock-entries" },
      },
      {
        id: "inventory.stock-balance-detail",
        path: ROUTES.STOCK_BALANCE_DETAIL,
        title: "Stock balance",
        navigation: { type: "contextual", parentRouteId: "inventory.stock-balances" },
      },
      {
        id: "inventory.stock-ledger",
        path: ROUTES.STOCK_LEDGER,
        title: "Stock ledger",
        navigation: { type: "contextual", parentRouteId: "inventory.stock-balances" },
      },
      {
        id: "inventory.stock-ledger-detail",
        path: ROUTES.STOCK_LEDGER_DETAIL,
        title: "Ledger movement",
        navigation: { type: "contextual", parentRouteId: "inventory.stock-balances" },
      },
    ]);
  });

  it("keeps inventory count and configuration route descriptors stable", async () => {
    const routes = await getTenantRoutes();
    expect(
      routes.slice(34).map((route) => ({
        id: route.id,
        path: route.path,
        title: route.title,
        navigation:
          route.navigation.type === "sidebar"
            ? { type: "sidebar", order: route.navigation.order }
            : { type: "contextual", parentRouteId: route.navigation.parentRouteId },
      }))
    ).toEqual([
      {
        id: "inventory.reservation-new",
        path: ROUTES.RESERVATION_NEW,
        title: "Create reservation",
        navigation: { type: "contextual", parentRouteId: "inventory.reservations" },
      },
      {
        id: "inventory.reservation-detail",
        path: ROUTES.RESERVATION_DETAIL,
        title: "Reservation",
        navigation: { type: "contextual", parentRouteId: "inventory.reservations" },
      },
      {
        id: "inventory.reservation-edit",
        path: ROUTES.RESERVATION_EDIT,
        title: "Edit reservation",
        navigation: { type: "contextual", parentRouteId: "inventory.reservations" },
      },
      {
        id: "inventory.cycle-count-new",
        path: ROUTES.CYCLE_COUNT_NEW,
        title: "Schedule cycle count",
        navigation: { type: "contextual", parentRouteId: "inventory.cycle-counts" },
      },
      {
        id: "inventory.cycle-count-detail",
        path: ROUTES.CYCLE_COUNT_DETAIL,
        title: "Cycle count",
        navigation: { type: "contextual", parentRouteId: "inventory.cycle-counts" },
      },
      {
        id: "inventory.cycle-count-edit",
        path: ROUTES.CYCLE_COUNT_EDIT,
        title: "Edit cycle count",
        navigation: { type: "contextual", parentRouteId: "inventory.cycle-counts" },
      },
      {
        id: "inventory.bulk-import",
        path: ROUTES.IMPORT,
        title: "Import inventory data",
        navigation: { type: "contextual", parentRouteId: "inventory.items" },
      },
      {
        id: "inventory.configuration-detail",
        path: ROUTES.CONFIGURATION_DETAIL,
        title: "Inventory configuration",
        navigation: { type: "contextual", parentRouteId: "inventory.settings" },
      },
      {
        id: "inventory.configuration-edit",
        path: ROUTES.CONFIGURATION_EDIT,
        title: "Edit inventory configuration",
        navigation: { type: "contextual", parentRouteId: "inventory.settings" },
      },
      {
        id: "inventory.configuration-history",
        path: ROUTES.CONFIGURATION_HISTORY,
        title: "Configuration history",
        navigation: { type: "contextual", parentRouteId: "inventory.settings" },
      },
      {
        id: "inventory.configuration-preview",
        path: ROUTES.CONFIGURATION_PREVIEW,
        title: "Configuration preview",
        navigation: { type: "contextual", parentRouteId: "inventory.settings" },
      },
      {
        id: "inventory.configuration-import",
        path: ROUTES.CONFIGURATION_IMPORT,
        title: "Import configuration",
        navigation: { type: "contextual", parentRouteId: "inventory.settings" },
      },
      {
        id: "inventory.configuration-export",
        path: ROUTES.CONFIGURATION_EXPORT,
        title: "Export configuration",
        navigation: { type: "contextual", parentRouteId: "inventory.settings" },
      },
      {
        id: "inventory.configuration-rollback",
        path: ROUTES.CONFIGURATION_ROLLBACK,
        title: "Rollback configuration",
        navigation: { type: "contextual", parentRouteId: "inventory.settings" },
      },
    ]);
  });

  it("sets a specific title and all supported runtime modes on every route", async () => {
    for (const route of await getTenantRoutes()) {
      expect(route.title).toBeTruthy();
      expect(route.title).not.toMatch(/SARAISE/u);
      expect(route.modes).toEqual(["development", "self-hosted", "saas"]);
    }
  });

  it("loads the exact registered lazy page for every inventory route", async () => {
    for (const route of await getTenantRoutes()) {
      cleanup();
      const Page = route.Page;

      render(createElement(Suspense, { fallback: "loading route" }, createElement(Page)));

      await waitFor(() => expect(screen.getByText(`${route.id}.page`)).toBeInTheDocument());
    }
  });

  it("centralizes API URLs in contracts.ts", () => {
    for (const [path, source] of Object.entries(moduleSources)) {
      if (path.endsWith("contracts.ts") || path.endsWith(".test.ts") || path.endsWith(".test.tsx"))
        continue;
      expect(source, path).not.toMatch(/\/api\/v[0-9]+\/inventory/u);
    }
  });
});
