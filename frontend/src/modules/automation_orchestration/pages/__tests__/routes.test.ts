import { describe, expect, it } from "vitest";
import { tenantRoutes } from "../../routes";

describe("automation orchestration route registry", () => {
  it("declares the configuration sidebar route and six contextual lazy routes", () => {
    expect(tenantRoutes).toHaveLength(10);
    expect(tenantRoutes.filter((route) => route.navigation.type === "sidebar")).toHaveLength(4);
    expect(tenantRoutes.filter((route) => route.navigation.type === "contextual")).toHaveLength(6);
    expect(tenantRoutes.every((route) => typeof route.Page === "object")).toBe(true);
    expect(tenantRoutes.every((route) => route.title.length > 0)).toBe(true);
    expect(tenantRoutes.some((route) => route.path === "/automation-orchestration/configuration")).toBe(true);
  });

  it("uses unique ids and paths with valid same-module parents", () => {
    const ids = new Set(tenantRoutes.map((route) => route.id));
    const paths = new Set(tenantRoutes.map((route) => route.path));
    expect(ids.size).toBe(tenantRoutes.length);
    expect(paths.size).toBe(tenantRoutes.length);
    for (const route of tenantRoutes) {
      expect(route.modes).toEqual(["development", "self-hosted", "saas"]);
      if (route.navigation.type === "contextual") {
        const parent = tenantRoutes.find((candidate) => candidate.id === route.navigation.parentRouteId);
        expect(parent?.module).toBe(route.module);
        expect(parent?.navigation.type).toBe("sidebar");
      }
    }
  });
});
