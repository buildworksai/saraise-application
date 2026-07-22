import { lazy } from "react";
import { Boxes, ClipboardCheck, Gauge, PackageCheck, ReceiptText, Settings2, Warehouse, Waypoints } from "lucide-react";
import type { TenantApplicationMode, TenantRoute } from "@/navigation/tenant-route-types";
import { ROUTES } from "./contracts";

const modes = ["development", "self-hosted", "saas"] as const satisfies readonly TenantApplicationMode[];
const pages = () => import("./pages/InventoryPages");
const page = (name: keyof Awaited<ReturnType<typeof pages>>) => lazy(() => pages().then((module) => ({ default: module[name] })));
const sidebar = (id: string, path: string, title: string, Page: ReturnType<typeof page>, icon: typeof Gauge, order: number): TenantRoute => ({ id, module: "inventory_management", path, title: `${title} | SARAISE`, sourceFile: "inventory_management/routes.ts", Page, modes, navigation: { type: "sidebar", label: title, icon, order } });
const contextual = (id: string, path: string, title: string, Page: ReturnType<typeof page>, parentRouteId: string): TenantRoute => ({ id, module: "inventory_management", path, title: `${title} | SARAISE`, sourceFile: "inventory_management/routes.ts", Page, modes, navigation: { type: "contextual", parentRouteId } });

export const tenantRoutes = [
  sidebar("inventory.dashboard", ROUTES.DASHBOARD, "Inventory dashboard", page("InventoryDashboardPage"), Gauge, 400),
  sidebar("inventory.warehouses", ROUTES.WAREHOUSES, "Warehouses", page("WarehouseListPage"), Warehouse, 410),
  sidebar("inventory.items", ROUTES.ITEMS, "Items", page("ItemListPage"), Boxes, 420),
  sidebar("inventory.stock-entries", ROUTES.STOCK_ENTRIES, "Stock entries", page("StockEntryListPage"), ReceiptText, 430),
  sidebar("inventory.stock-balances", ROUTES.STOCK_BALANCES, "Stock balances", page("StockBalanceListPage"), PackageCheck, 440),
  sidebar("inventory.reservations", ROUTES.RESERVATIONS, "Reservations", page("ReservationListPage"), Waypoints, 450),
  sidebar("inventory.cycle-counts", ROUTES.CYCLE_COUNTS, "Cycle counts", page("CycleCountListPage"), ClipboardCheck, 460),
  sidebar("inventory.settings", ROUTES.SETTINGS, "Inventory settings", page("ConfigurationListPage"), Settings2, 470),

  contextual("inventory.warehouse-new", ROUTES.WAREHOUSE_NEW, "Create warehouse", page("WarehouseCreatePage"), "inventory.warehouses"),
  contextual("inventory.warehouse-detail", ROUTES.WAREHOUSE_DETAIL, "Warehouse", page("WarehouseDetailPage"), "inventory.warehouses"),
  contextual("inventory.warehouse-edit", ROUTES.WAREHOUSE_EDIT, "Edit warehouse", page("WarehouseEditPage"), "inventory.warehouses"),
  contextual("inventory.locations", ROUTES.LOCATIONS, "Locations", page("LocationListPage"), "inventory.warehouses"),
  contextual("inventory.location-new", ROUTES.LOCATION_NEW, "Create location", page("LocationCreatePage"), "inventory.warehouses"),
  contextual("inventory.location-detail", ROUTES.LOCATION_DETAIL, "Location", page("LocationDetailPage"), "inventory.warehouses"),
  contextual("inventory.location-edit", ROUTES.LOCATION_EDIT, "Edit location", page("LocationEditPage"), "inventory.warehouses"),
  contextual("inventory.item-new", ROUTES.ITEM_NEW, "Create item", page("ItemCreatePage"), "inventory.items"),
  contextual("inventory.item-detail", ROUTES.ITEM_DETAIL, "Item", page("ItemDetailPage"), "inventory.items"),
  contextual("inventory.item-edit", ROUTES.ITEM_EDIT, "Edit item", page("ItemEditPage"), "inventory.items"),
  contextual("inventory.batches", ROUTES.BATCHES, "Batches", page("BatchListPage"), "inventory.items"),
  contextual("inventory.batch-new", ROUTES.BATCH_NEW, "Register batch", page("BatchCreatePage"), "inventory.items"),
  contextual("inventory.batch-detail", ROUTES.BATCH_DETAIL, "Batch", page("BatchDetailPage"), "inventory.items"),
  contextual("inventory.batch-edit", ROUTES.BATCH_EDIT, "Edit batch", page("BatchEditPage"), "inventory.items"),
  contextual("inventory.batch-trace", ROUTES.BATCH_TRACE, "Batch trace", page("BatchTracePage"), "inventory.items"),
  contextual("inventory.serials", ROUTES.SERIALS, "Serial numbers", page("SerialListPage"), "inventory.items"),
  contextual("inventory.serial-new", ROUTES.SERIAL_NEW, "Register serial number", page("SerialCreatePage"), "inventory.items"),
  contextual("inventory.serial-detail", ROUTES.SERIAL_DETAIL, "Serial number", page("SerialDetailPage"), "inventory.items"),
  contextual("inventory.serial-edit", ROUTES.SERIAL_EDIT, "Edit serial number", page("SerialEditPage"), "inventory.items"),
  contextual("inventory.serial-trace", ROUTES.SERIAL_TRACE, "Serial trace", page("SerialTracePage"), "inventory.items"),
  contextual("inventory.stock-entry-new", ROUTES.STOCK_ENTRY_NEW, "Create stock entry", page("StockEntryCreatePage"), "inventory.stock-entries"),
  contextual("inventory.stock-entry-detail", ROUTES.STOCK_ENTRY_DETAIL, "Stock entry", page("StockEntryDetailPage"), "inventory.stock-entries"),
  contextual("inventory.stock-entry-edit", ROUTES.STOCK_ENTRY_EDIT, "Edit stock entry", page("StockEntryEditPage"), "inventory.stock-entries"),
  contextual("inventory.stock-balance-detail", ROUTES.STOCK_BALANCE_DETAIL, "Stock balance", page("StockBalanceDetailPage"), "inventory.stock-balances"),
  contextual("inventory.stock-ledger", ROUTES.STOCK_LEDGER, "Stock ledger", page("StockLedgerListPage"), "inventory.stock-balances"),
  contextual("inventory.stock-ledger-detail", ROUTES.STOCK_LEDGER_DETAIL, "Ledger movement", page("StockLedgerDetailPage"), "inventory.stock-balances"),
  contextual("inventory.reservation-new", ROUTES.RESERVATION_NEW, "Create reservation", page("ReservationCreatePage"), "inventory.reservations"),
  contextual("inventory.reservation-detail", ROUTES.RESERVATION_DETAIL, "Reservation", page("ReservationDetailPage"), "inventory.reservations"),
  contextual("inventory.reservation-edit", ROUTES.RESERVATION_EDIT, "Edit reservation", page("ReservationEditPage"), "inventory.reservations"),
  contextual("inventory.cycle-count-new", ROUTES.CYCLE_COUNT_NEW, "Schedule cycle count", page("CycleCountCreatePage"), "inventory.cycle-counts"),
  contextual("inventory.cycle-count-detail", ROUTES.CYCLE_COUNT_DETAIL, "Cycle count", page("CycleCountDetailPage"), "inventory.cycle-counts"),
  contextual("inventory.cycle-count-edit", ROUTES.CYCLE_COUNT_EDIT, "Edit cycle count", page("CycleCountEditPage"), "inventory.cycle-counts"),
  contextual("inventory.bulk-import", ROUTES.IMPORT, "Import inventory data", page("BulkImportPage"), "inventory.items"),
  contextual("inventory.configuration-detail", ROUTES.CONFIGURATION_DETAIL, "Inventory configuration", page("ConfigurationDetailPage"), "inventory.settings"),
  contextual("inventory.configuration-edit", ROUTES.CONFIGURATION_EDIT, "Edit inventory configuration", page("ConfigurationEditPage"), "inventory.settings"),
  contextual("inventory.configuration-history", ROUTES.CONFIGURATION_HISTORY, "Configuration history", page("ConfigurationHistoryPage"), "inventory.settings"),
  contextual("inventory.configuration-preview", ROUTES.CONFIGURATION_PREVIEW, "Configuration preview", page("ConfigurationPreviewPage"), "inventory.settings"),
  contextual("inventory.configuration-import", ROUTES.CONFIGURATION_IMPORT, "Import configuration", page("ConfigurationImportPage"), "inventory.settings"),
  contextual("inventory.configuration-export", ROUTES.CONFIGURATION_EXPORT, "Export configuration", page("ConfigurationExportPage"), "inventory.settings"),
  contextual("inventory.configuration-rollback", ROUTES.CONFIGURATION_ROLLBACK, "Rollback configuration", page("ConfigurationRollbackPage"), "inventory.settings"),
] satisfies readonly TenantRoute[];

export default tenantRoutes;
