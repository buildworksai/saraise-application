import { describe, expect, it } from "vitest";
import { tenantRoutes } from "../../routes";

describe("automation orchestration route registry", () => {
  it("declares three sidebar and six contextual lazy routes", () => {
    expect(tenantRoutes).toHaveLength(9);
    expect(tenantRoutes.filter((route) => route.navigation.type === "sidebar")).toHaveLength(3);
    expect(tenantRoutes.filter((route) => route.navigation.type === "contextual")).toHaveLength(6);
    expect(tenantRoutes.every((route) => typeof route.Page === "object")).toBe(true);
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
