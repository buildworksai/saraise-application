import {
  buildTenantSidebarTree,
  getTenantRoutesForMode,
  validateTenantRoutes,
} from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "./routes";

describe("fixed-assets tenant routes", () => {
  it("publishes every required page with unique ids, paths, and valid parents", () => {
    expect(tenantRoutes).toHaveLength(15);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(15);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(15);
    expect(() => validateTenantRoutes(tenantRoutes)).not.toThrow();
  });

  it.each(["development", "self-hosted", "saas"] as const)("is visible in %s mode", (mode) => {
    expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(15);
  });

  it("resolves the four required sidebar leaves", () => {
    const tree = buildTenantSidebarTree(tenantRoutes);
    expect(tree).toHaveLength(1);
    expect(tree[0]?.children.map((leaf) => leaf.path)).toEqual([
      "/fixed-assets/dashboard",
      "/fixed-assets/assets",
      "/fixed-assets/categories",
      "/fixed-assets/depreciation-schedules",
    ]);
  });

  it("sets a human-readable browser title for every routed page", () => {
    expect(tenantRoutes.map((route) => [route.id, route.title])).toEqual([
      ["fixed_assets.dashboard", "Fixed assets dashboard"],
      ["fixed_assets.assets.list", "Fixed assets"],
      ["fixed_assets.assets.create", "Create fixed asset"],
      ["fixed_assets.assets.detail", "Fixed asset details"],
      ["fixed_assets.assets.edit", "Edit fixed asset"],
      ["fixed_assets.categories.list", "Asset categories"],
      ["fixed_assets.categories.create", "Create asset category"],
      ["fixed_assets.categories.detail", "Asset category details"],
      ["fixed_assets.categories.edit", "Edit asset category"],
      ["fixed_assets.schedules.list", "Depreciation schedules"],
      ["fixed_assets.schedules.create", "Create depreciation schedule"],
      ["fixed_assets.schedules.detail", "Depreciation schedule details"],
      ["fixed_assets.schedules.edit", "Edit depreciation schedule"],
      ["fixed_assets.lines.detail", "Depreciation line details"],
      ["fixed_assets.transactions.detail", "Asset transaction details"],
    ]);
  });
});
