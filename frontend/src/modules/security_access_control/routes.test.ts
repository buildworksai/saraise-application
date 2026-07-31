/* eslint-disable max-lines-per-function, max-nested-callbacks -- exact route surface matrix intentionally keeps labels, paths, and order together. */
import { describe, expect, it, vi } from "vitest";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import type { TenantRoute } from "@/navigation/tenant-route-types";

async function loadTenantRoutes(): Promise<readonly TenantRoute[]> {
  vi.resetModules();
  return (await import("./routes")).tenantRoutes;
}

describe("security route discovery", () => {
  const expectedPaths = [
    "/security-access-control/roles",
    "/security-access-control/roles/create",
    "/security-access-control/roles/:id",
    "/security-access-control/roles/:id/edit",
    "/security-access-control/permissions",
    "/security-access-control/permissions/:id",
    "/security-access-control/assignments",
    "/security-access-control/assignments/create",
    "/security-access-control/assignments/:id",
    "/security-access-control/assignments/:id/edit",
    "/security-access-control/permission-sets",
    "/security-access-control/permission-sets/create",
    "/security-access-control/permission-sets/:id",
    "/security-access-control/permission-sets/:id/edit",
    "/security-access-control/assignments/permission-set-grants",
    "/security-access-control/assignments/permission-set-grants/create",
    "/security-access-control/assignments/permission-set-grants/:id",
    "/security-access-control/assignments/permission-set-grants/:id/edit",
    "/security-access-control/field-security",
    "/security-access-control/field-security/create",
    "/security-access-control/field-security/:id",
    "/security-access-control/field-security/:id/edit",
    "/security-access-control/row-security",
    "/security-access-control/row-security/create",
    "/security-access-control/row-security/:id",
    "/security-access-control/row-security/:id/edit",
    "/security-access-control/security-profiles",
    "/security-access-control/security-profiles/create",
    "/security-access-control/security-profiles/:id",
    "/security-access-control/security-profiles/:id/edit",
    "/security-access-control/assignments/profile-assignments",
    "/security-access-control/assignments/profile-assignments/create",
    "/security-access-control/assignments/profile-assignments/:id",
    "/security-access-control/assignments/profile-assignments/:id/edit",
    "/security-access-control/audit-logs",
    "/security-access-control/audit-logs/:id",
    "/security-access-control/access-simulator",
    "/security-access-control/configuration",
  ];

  it("publishes unique, structurally valid descriptors", async () => {
    const tenantRoutes = await loadTenantRoutes();
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
  });

  it("publishes the exact ordered route surface", async () => {
    const tenantRoutes = await loadTenantRoutes();
    expect(tenantRoutes.map((route) => route.path)).toEqual(expectedPaths);
  });

  it("publishes exact sidebar labels, paths, and display order", async () => {
    const tenantRoutes = await loadTenantRoutes();
    const sidebar = tenantRoutes.filter((route) => route.navigation.type === "sidebar");
    expect(sidebar.map((route) => route.path)).toEqual([
      "/security-access-control/roles",
      "/security-access-control/permissions",
      "/security-access-control/assignments",
      "/security-access-control/permission-sets",
      "/security-access-control/field-security",
      "/security-access-control/row-security",
      "/security-access-control/security-profiles",
      "/security-access-control/audit-logs",
      "/security-access-control/access-simulator",
      "/security-access-control/configuration",
    ]);
    expect(sidebar.map((route) => route.navigation.label)).toEqual([
      "Roles",
      "Permissions",
      "Assignments",
      "Permission sets",
      "Field security",
      "Row security",
      "Security profiles",
      "Audit logs",
      "Access simulator",
      "Configuration",
    ]);
    expect(sidebar.map((route) => route.navigation.order)).toEqual([
      120, 121, 122, 123, 124, 125, 126, 127, 128, 129,
    ]);
  });

  it("assigns exact page titles by route kind", async () => {
    const tenantRoutes = await loadTenantRoutes();
    const titleByPath = new Map(tenantRoutes.map((route) => [route.path, route.title]));
    expect(titleByPath.get("/security-access-control/roles")).toBe("Security administration");
    expect(titleByPath.get("/security-access-control/roles/create")).toBe("Create security policy");
    expect(titleByPath.get("/security-access-control/roles/:id")).toBe("Security policy detail");
    expect(titleByPath.get("/security-access-control/roles/:id/edit")).toBe("Edit security policy");
    expect(titleByPath.get("/security-access-control/access-simulator")).toBe("Access simulator");
    expect(titleByPath.get("/security-access-control/configuration")).toBe(
      "Security configuration"
    );
  });

  it("links every contextual route to an existing sidebar parent", async () => {
    const tenantRoutes = await loadTenantRoutes();
    const sidebarIds = new Set(
      tenantRoutes.filter((route) => route.navigation.type === "sidebar").map((route) => route.id)
    );
    for (const route of tenantRoutes)
      if (route.navigation.type === "contextual")
        expect(sidebarIds.has(route.navigation.parentRouteId)).toBe(true);
  });
  it("shows only audit and simulation in SaaS", async () => {
    const tenantRoutes = await loadTenantRoutes();
    const saas = tenantRoutes.filter((route) => route.modes?.some((mode) => mode === "saas"));
    expect(saas.map((route) => route.path)).toEqual(
      expect.arrayContaining([
        "/security-access-control/audit-logs",
        "/security-access-control/audit-logs/:id",
        "/security-access-control/access-simulator",
      ])
    );
    expect(saas.some((route) => route.path === "/security-access-control/roles")).toBe(false);
  });
  it("contains every required contextual family without broken links", async () => {
    const tenantRoutes = await loadTenantRoutes();
    const paths = tenantRoutes.map((route) => route.path);
    expect(paths).toEqual(expectedPaths);
    for (const family of [
      "roles",
      "assignments",
      "permission-sets",
      "field-security",
      "row-security",
      "security-profiles",
    ]) {
      expect(paths).toContain(`/security-access-control/${family}`);
      expect(paths).toContain(`/security-access-control/${family}/create`);
      expect(paths).toContain(`/security-access-control/${family}/:id`);
      expect(paths).toContain(`/security-access-control/${family}/:id/edit`);
    }
  });
});
