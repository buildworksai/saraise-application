import {
  buildTenantSidebarTree,
  getTenantRouteValidationIssues,
  tenantRoutes,
  tenantSidebarTree,
  validateTenantSidebarTree,
  validateTenantRoutes,
} from "./tenant-route-registry";

describe("tenant route registry parity", () => {
  it("discovers the CRM and sales-management module descriptors", () => {
    expect(new Set(tenantRoutes.map((route) => route.module))).toEqual(
      new Set(["crm", "sales_management"]),
    );
  });

  it("contains unique route ids and normalized paths", () => {
    const ids = tenantRoutes.map((route) => route.id);
    const paths = tenantRoutes.map((route) => route.path.replace(/\/+$/, ""));

    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(paths).size).toBe(paths.length);
    expect(() => validateTenantRoutes(tenantRoutes)).not.toThrow();
  });

  it("resolves every sidebar leaf to its registered route", () => {
    const routesById = new Map(tenantRoutes.map((route) => [route.id, route]));
    const leaves = tenantSidebarTree.flatMap((branch) => branch.children);

    expect(leaves.length).toBeGreaterThan(0);
    expect(() => validateTenantSidebarTree(tenantRoutes, tenantSidebarTree)).not.toThrow();
    for (const leaf of leaves) {
      const route = routesById.get(leaf.routeId);
      expect(route).toBeDefined();
      expect(route?.path).toBe(leaf.path);
      expect(route?.module).toBe(leaf.module);
      expect(route?.navigation.type).toBe("sidebar");
    }
  });

  it("gives every contextual route a real sidebar parent", () => {
    const routesById = new Map(tenantRoutes.map((route) => [route.id, route]));
    const contextualRoutes = tenantRoutes.filter(
      (route) => route.navigation.type === "contextual",
    );

    expect(contextualRoutes.length).toBeGreaterThan(0);
    for (const route of contextualRoutes) {
      if (route.navigation.type !== "contextual") continue;
      const parent = routesById.get(route.navigation.parentRouteId);
      expect(parent).toBeDefined();
      expect(parent?.module).toBe(route.module);
      expect(parent?.navigation.type).toBe("sidebar");
    }
  });

  it("keeps route parameters out of sidebar paths", () => {
    const leaves = tenantSidebarTree.flatMap((branch) => branch.children);

    for (const leaf of leaves) {
      expect(leaf.path.split("/").some((segment) => segment.startsWith(":"))).toBe(false);
    }
  });

  it("supports an empty registry as a migration no-op", () => {
    expect(buildTenantSidebarTree([])).toEqual([]);
    expect(getTenantRouteValidationIssues([])).toEqual([]);
  });

  it("reports duplicate paths and broken contextual parents together", () => {
    const sidebarRoute = tenantRoutes.find(
      (route) => route.navigation.type === "sidebar",
    );
    const contextualRoute = tenantRoutes.find(
      (route) => route.navigation.type === "contextual",
    );
    expect(sidebarRoute).toBeDefined();
    expect(contextualRoute).toBeDefined();
    if (!sidebarRoute || !contextualRoute) return;

    const issues = getTenantRouteValidationIssues([
      sidebarRoute,
      {
        ...contextualRoute,
        id: "test.broken-contextual-route",
        path: `${sidebarRoute.path}/`,
        navigation: { type: "contextual", parentRouteId: "missing.parent" },
      },
    ]);

    expect(issues.map((issue) => issue.message)).toEqual(
      expect.arrayContaining([
        expect.stringContaining("duplicate path"),
        expect.stringContaining("does not exist"),
      ]),
    );
  });
});
