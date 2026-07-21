import { describe, expect, it } from "vitest";
import { buildTenantSidebarTree, getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "../routes";

describe("customization framework route registration", () => {
  it("registers four discoverable sidebar leaves and every contextual parent", () => {
    expect(tenantRoutes.filter(route => route.navigation.type === "sidebar").map(route => route.navigation.type === "sidebar" ? route.navigation.label : "")).toEqual(["Fields", "Forms", "Rules", "Executions"]);
    expect(tenantRoutes.filter(route => route.navigation.type === "contextual")).toHaveLength(15);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
  });

  it("derives sidebar entries and makes all routes available in every mode", () => {
    const tree = buildTenantSidebarTree(tenantRoutes);
    expect(tree).toHaveLength(1);
    expect(tree[0]?.children).toHaveLength(4);
    expect(tenantRoutes.every(route => route.modes?.join(",") === "development,self-hosted,saas")).toBe(true);
    expect(new Set(tenantRoutes.map(route => route.path)).size).toBe(tenantRoutes.length);
  });
});
