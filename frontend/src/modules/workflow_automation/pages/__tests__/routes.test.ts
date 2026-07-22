import { describe, expect, it } from "vitest";
import { tenantRoutes } from "../../routes";

describe("workflow automation route registry", () => {
  it("discovers every required page with three sidebar parents", () => {
    expect(tenantRoutes).toHaveLength(8);
    expect(tenantRoutes.filter((route) => route.navigation.type === "sidebar").map((route) => [route.path, route.navigation.type === "sidebar" ? route.navigation.order : -1])).toEqual([
      ["/workflow-automation/workflows", 80],
      ["/workflow-automation/instances", 81],
      ["/workflow-automation/tasks", 82],
    ]);
  });

  it("has unique paths and same-module contextual parents in every runtime mode", () => {
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    for (const route of tenantRoutes) {
      expect(route.modes).toEqual(["development", "self-hosted", "saas"]);
      if (route.navigation.type === "sidebar") expect(route.path).not.toContain(":");
      if (route.navigation.type === "contextual") {
        const parent = tenantRoutes.find((candidate) => candidate.id === route.navigation.parentRouteId);
        expect(parent?.module).toBe(route.module);
        expect(parent?.navigation.type).toBe("sidebar");
      }
    }
  });
});
