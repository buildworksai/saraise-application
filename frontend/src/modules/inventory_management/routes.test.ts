import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { ROUTES } from "./contracts";
import { tenantRoutes } from "./routes";

const moduleSources = import.meta.glob<string>(["./**/*.ts", "./**/*.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
});

describe("inventory tenant routes", () => {
  it("publishes a unique, valid registry with eight sidebar destinations", () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    expect(tenantRoutes.filter((route) => route.navigation.type === "sidebar")).toHaveLength(8);
  });

  it("resolves every contextual route to an inventory sidebar parent", () => {
    const byId = new Map(tenantRoutes.map((route) => [route.id, route]));
    for (const route of tenantRoutes) {
      if (route.navigation.type !== "contextual") continue;
      const parent = byId.get(route.navigation.parentRouteId);
      expect(parent?.module).toBe("inventory_management");
      expect(parent?.navigation.type).toBe("sidebar");
    }
  });

  it("keeps sidebar and route contract parity", () => {
    const sidebarPaths = tenantRoutes.filter((route) => route.navigation.type === "sidebar").map((route) => route.path);
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
  });

  it("sets a specific title and all supported runtime modes on every route", () => {
    for (const route of tenantRoutes) {
      expect(route.title).toMatch(/\| SARAISE$/u);
      expect(route.modes).toEqual(["development", "self-hosted", "saas"]);
    }
  });

  it("centralizes API URLs in contracts.ts", () => {
    for (const [path, source] of Object.entries(moduleSources)) {
      if (path.endsWith("contracts.ts") || path.endsWith(".test.ts") || path.endsWith(".test.tsx")) continue;
      expect(source, path).not.toMatch(/\/api\/v[0-9]+\/inventory/u);
    }
  });
});
