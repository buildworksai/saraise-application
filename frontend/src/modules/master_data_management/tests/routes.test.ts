import { describe, expect, it } from "vitest";
import { buildTenantSidebarTree, getTenantRoutesForMode, getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "../routes";

describe("master data tenant routes", () => {
  it("registers all 26 required pages with unique identities and titles", () => {
    expect(tenantRoutes).toHaveLength(26);
    expect(new Set(tenantRoutes.map((route) => route.id))).toHaveLength(26);
    expect(new Set(tenantRoutes.map((route) => route.path))).toHaveLength(26);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(tenantRoutes.every((route) => route.id.startsWith("master-data-management.") && route.sourceFile.endsWith(".tsx") && Boolean(route.title))).toBe(true);
  });

  it.each(["development", "self-hosted", "saas"] as const)("is visible in %s mode", (mode) => {
    expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(26);
  });

  it("gives every page a discoverable sidebar NavItem", () => {
    const tree = buildTenantSidebarTree(tenantRoutes);
    expect(tree).toHaveLength(1);
    expect(tree[0]?.children[0]?.path).toBe("/master-data");
    expect(tree[0]?.children).toHaveLength(26);
    expect(tenantRoutes.every((route) => route.navigation.type === "sidebar")).toBe(true);
  });
});
