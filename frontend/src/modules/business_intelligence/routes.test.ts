import { describe, expect, it } from "vitest";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "./routes";

describe("business intelligence route contract", () => {
  const expected = [
    ["/business-intelligence/datasets", "Dataset catalog"],
    ["/business-intelligence/dashboards", "Dashboards"],
    ["/business-intelligence/dashboards/new", "Create dashboard"],
    ["/business-intelligence/dashboards/:id", "Dashboard"],
    ["/business-intelligence/dashboards/:id/edit", "Dashboard builder"],
    ["/business-intelligence/reports", "Reports"],
    ["/business-intelligence/reports/new", "Create report"],
    ["/business-intelligence/reports/:id", "Report details"],
    ["/business-intelligence/reports/:id/edit", "Edit report"],
    ["/business-intelligence/queries", "Queries"],
    ["/business-intelligence/queries/new", "Create query"],
    ["/business-intelligence/queries/:id", "Query details"],
    ["/business-intelligence/queries/:id/edit", "Edit query"],
    ["/business-intelligence/executions", "Execution history"],
    ["/business-intelligence/executions/:id", "Execution details"],
  ] as const;

  it("publishes valid unique route descriptors with exact titles", () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(tenantRoutes.map(({ path, title }) => [path, title])).toEqual(expected);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
  });

  it("keeps contextual routes attached to existing sidebar parents", () => {
    const routeIds = new Set(tenantRoutes.map((route) => route.id));
    const contextualRoutes = tenantRoutes.filter((route) => route.navigation.type === "contextual");

    expect(contextualRoutes).toHaveLength(10);
    expect(
      contextualRoutes.map((route) => {
        const navigation = route.navigation;
        return navigation.type === "contextual" ? navigation.parentRouteId : "";
      })
    ).toEqual([
      "business_intelligence.dashboards.list",
      "business_intelligence.dashboards.list",
      "business_intelligence.dashboards.list",
      "business_intelligence.reports.list",
      "business_intelligence.reports.list",
      "business_intelligence.reports.list",
      "business_intelligence.queries.list",
      "business_intelligence.queries.list",
      "business_intelligence.queries.list",
      "business_intelligence.executions.list",
    ]);
    contextualRoutes.forEach((route) => {
      const navigation = route.navigation;
      if (navigation.type === "contextual") {
        expect(routeIds.has(navigation.parentRouteId)).toBe(true);
      }
    });
  });
});
