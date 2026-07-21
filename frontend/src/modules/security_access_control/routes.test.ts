import { describe, expect, it } from "vitest";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "./routes";

describe("security route discovery", () => {
  it("publishes unique, structurally valid descriptors", () => { expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]); expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length); });
  it("links every contextual route to an existing sidebar parent", () => { const sidebarIds = new Set(tenantRoutes.filter((route) => route.navigation.type === "sidebar").map((route) => route.id)); for (const route of tenantRoutes) if (route.navigation.type === "contextual") expect(sidebarIds.has(route.navigation.parentRouteId)).toBe(true); });
  it("shows only audit and simulation in SaaS", () => { const saas = tenantRoutes.filter((route) => route.modes?.some((mode) => mode === "saas")); expect(saas.map((route) => route.path)).toEqual(expect.arrayContaining(["/security-access-control/audit-logs", "/security-access-control/audit-logs/:id", "/security-access-control/access-simulator"])); expect(saas.some((route) => route.path === "/security-access-control/roles")).toBe(false); });
  it("contains every required contextual family without broken links", () => { const paths = tenantRoutes.map((route) => route.path); for (const family of ["roles", "assignments", "permission-sets", "field-security", "row-security", "security-profiles"]) { expect(paths).toContain(`/security-access-control/${family}`); expect(paths).toContain(`/security-access-control/${family}/create`); expect(paths).toContain(`/security-access-control/${family}/:id`); expect(paths).toContain(`/security-access-control/${family}/:id/edit`); } });
});
