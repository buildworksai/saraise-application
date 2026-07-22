import { describe, expect, it } from "vitest";
import { buildTenantSidebarTree, getTenantRouteValidationIssues, getTenantRoutesForMode } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "./routes";

describe("metadata modeling route contract", () => {
  it("publishes unique governed routes with titles and valid contextual parents", () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    expect(tenantRoutes.every((route) => route.title?.endsWith("· SARAISE"))).toBe(true);
  });

  it("resolves the required sidebar leaves", () => {
    const branch = buildTenantSidebarTree(tenantRoutes).find((item) => item.module === "metadata_modeling");
    expect(branch?.children.map((item) => item.label)).toEqual(["Metadata Models", "Dynamic Records", "Metadata Settings"]);
  });

  it.each(["development", "self-hosted", "saas"] as const)("is available in %s mode", (mode) => {
    expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(9);
  });
});
