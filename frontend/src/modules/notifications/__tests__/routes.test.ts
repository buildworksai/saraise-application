import { describe, expect, it } from "vitest";
import { tenantRoutes } from "../routes";

describe("notification route registry", () => {
  it("registers all pages with titles and unique paths", () => {
    expect(tenantRoutes).toHaveLength(16);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(16);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(16);
    expect(tenantRoutes.every((route) => Boolean(route.title?.trim()))).toBe(true);
  });

  it("publishes six sidebar destinations and real contextual parents", () => {
    const sidebar = tenantRoutes.filter((route) => route.navigation.type === "sidebar");
    expect(sidebar.map((route) => route.id)).toEqual([
      "notifications.inbox", "notifications.templates", "notifications.deliveries",
      "notifications.endpoints", "notifications.configuration", "notifications.health",
    ]);
    const ids = new Set(sidebar.map((route) => route.id));
    tenantRoutes.filter((route) => route.navigation.type === "contextual").forEach((route) => {
      if (route.navigation.type === "contextual") expect(ids.has(route.navigation.parentRouteId)).toBe(true);
    });
  });

  it("declares an explicit policy capability for every sidebar destination", () => {
    expect(tenantRoutes.filter((route) => route.navigation.type === "sidebar").every((route) => route.requiredPermission?.startsWith("notifications."))).toBe(true);
  });
});
