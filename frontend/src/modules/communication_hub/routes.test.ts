import { describe, expect, it } from "vitest";
import {
  buildTenantSidebarTree,
  getTenantRouteValidationIssues,
  getTenantRoutesForMode,
} from "@/navigation/tenant-route-registry";
import { ROUTES } from "./contracts";
import { tenantRoutes } from "./routes";

describe("communication hub route registry", () => {
  it("registers the UAT-covered module routes", () => {
    expect(tenantRoutes.map((route) => route.path)).toEqual([
      ROUTES.CHANNELS,
      ROUTES.MESSAGES,
      ROUTES.TEMPLATES,
      ROUTES.CONFIGURATION,
    ]);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
  });

  it("publishes concrete sidebar destinations for every route", () => {
    expect(tenantRoutes.every((route) => route.navigation.type === "sidebar")).toBe(true);
    expect(tenantRoutes.map((route) => route.requiredPermission)).toEqual([
      "communication.channel:read",
      "communication.message:read",
      "communication.message:read",
      "communication.channel:read",
    ]);
    expect(buildTenantSidebarTree(tenantRoutes)[0]?.children.map((leaf) => leaf.path)).toEqual([
      ROUTES.CHANNELS,
      ROUTES.MESSAGES,
      ROUTES.TEMPLATES,
      ROUTES.CONFIGURATION,
    ]);
  });

  it("is available in every runtime mode", () => {
    for (const mode of ["development", "self-hosted", "saas"] as const) {
      expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(tenantRoutes.length);
    }
  });
});
