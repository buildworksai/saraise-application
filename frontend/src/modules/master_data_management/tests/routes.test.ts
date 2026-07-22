import { describe, expect, it } from "vitest";
import { buildTenantSidebarTree, getTenantRoutesForMode, getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "../routes";

describe("master data tenant routes", () => {
  it("registers all 25 required pages with unique identities", () => {
    expect(tenantRoutes).toHaveLength(25);
    expect(new Set(tenantRoutes.map((route) => route.id))).toHaveLength(25);
    expect(new Set(tenantRoutes.map((route) => route.path))).toHaveLength(25);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(tenantRoutes.every((route) => route.id.startsWith("master-data-management.") && route.sourceFile.endsWith(".tsx"))).toBe(true);
  });

  it.each(["development", "self-hosted", "saas"] as const)("is visible in %s mode", (mode) => {
    expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(25);
  });

  it("derives a single sidebar entry and keeps contextual pages parented", () => {
    const tree = buildTenantSidebarTree(tenantRoutes);
    expect(tree).toHaveLength(1);
    expect(tree[0]?.children[0]?.path).toBe("/master-data");
    expect(tenantRoutes.slice(1).every((route) => route.navigation.type === "contextual" && route.navigation.parentRouteId === "master-data-management.dashboard")).toBe(true);
  });
});
