import { describe, expect, it } from "vitest";
import { tenantRoutes } from "./routes";

describe("bank reconciliation tenant routes", () => {
  it("has unique route IDs and paths", () => {
    expect(new Set(tenantRoutes.map(({ id }) => id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map(({ path }) => path)).size).toBe(tenantRoutes.length);
  });

  it("resolves every contextual parent to a sidebar route", () => {
    const byId = new Map(tenantRoutes.map((route) => [route.id, route]));
    for (const route of tenantRoutes) {
      if (route.navigation.type === "contextual") {
        expect(byId.get(route.navigation.parentRouteId)?.navigation.type).toBe("sidebar");
      }
    }
  });

  it("publishes the five ordered sidebar leaves", () => {
    const sidebar = tenantRoutes.filter((route) => route.navigation.type === "sidebar");
    expect(sidebar.map((route) => route.path)).toEqual([
      "/bank-reconciliation/accounts",
      "/bank-reconciliation/statements",
      "/bank-reconciliation/reconciliations",
      "/bank-reconciliation/rules",
      "/bank-reconciliation/imports",
    ]);
    expect(
      sidebar.map((route) => (route.navigation.type === "sidebar" ? route.navigation.order : 0))
    ).toEqual([600, 610, 620, 630, 640]);
  });
});
