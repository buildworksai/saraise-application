/* eslint-disable max-lines-per-function, max-nested-callbacks -- exact route surface matrix intentionally keeps labels, paths, and order together. */
import { describe, expect, it } from "vitest";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "./routes";

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
  const expectedContextualParentByPath = new Map([
    ["/security-access-control/roles/create", "security-access-control.roles.list"],
    ["/security-access-control/roles/:id", "security-access-control.roles.list"],
    ["/security-access-control/roles/:id/edit", "security-access-control.roles.list"],
    ["/security-access-control/permissions/:id", "security-access-control.permissions.list"],
    ["/security-access-control/assignments/create", "security-access-control.assignments.list"],
    ["/security-access-control/assignments/:id", "security-access-control.assignments.list"],
    ["/security-access-control/assignments/:id/edit", "security-access-control.assignments.list"],
    [
      "/security-access-control/permission-sets/create",
      "security-access-control.permission-sets.list",
    ],
    [
      "/security-access-control/permission-sets/:id",
      "security-access-control.permission-sets.list",
    ],
    [
      "/security-access-control/permission-sets/:id/edit",
      "security-access-control.permission-sets.list",
    ],
    [
      "/security-access-control/assignments/permission-set-grants",
      "security-access-control.assignments.list",
    ],
    [
      "/security-access-control/assignments/permission-set-grants/create",
      "security-access-control.assignments.list",
    ],
    [
      "/security-access-control/assignments/permission-set-grants/:id",
      "security-access-control.assignments.list",
    ],
    [
      "/security-access-control/assignments/permission-set-grants/:id/edit",
      "security-access-control.assignments.list",
    ],
    [
      "/security-access-control/field-security/create",
      "security-access-control.field-security.list",
    ],
    ["/security-access-control/field-security/:id", "security-access-control.field-security.list"],
    [
      "/security-access-control/field-security/:id/edit",
      "security-access-control.field-security.list",
    ],
    ["/security-access-control/row-security/create", "security-access-control.row-security.list"],
    ["/security-access-control/row-security/:id", "security-access-control.row-security.list"],
    ["/security-access-control/row-security/:id/edit", "security-access-control.row-security.list"],
    ["/security-access-control/security-profiles/create", "security-access-control.profiles.list"],
    ["/security-access-control/security-profiles/:id", "security-access-control.profiles.list"],
    [
      "/security-access-control/security-profiles/:id/edit",
      "security-access-control.profiles.list",
    ],
    [
      "/security-access-control/assignments/profile-assignments",
      "security-access-control.assignments.list",
    ],
    [
      "/security-access-control/assignments/profile-assignments/create",
      "security-access-control.assignments.list",
    ],
    [
      "/security-access-control/assignments/profile-assignments/:id",
      "security-access-control.assignments.list",
    ],
    [
      "/security-access-control/assignments/profile-assignments/:id/edit",
      "security-access-control.assignments.list",
    ],
    ["/security-access-control/audit-logs/:id", "security-access-control.audit.list"],
  ]);
  const expectedSaasPaths = [
    "/security-access-control/audit-logs",
    "/security-access-control/audit-logs/:id",
    "/security-access-control/access-simulator",
    "/security-access-control/configuration",
  ];

  it("publishes unique, structurally valid descriptors", () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(tenantRoutes).toHaveLength(expectedPaths.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
  });

  it("publishes the exact ordered route surface", () => {
    expect(tenantRoutes.map((route) => route.path)).toEqual(expectedPaths);
  });

  it("publishes exact sidebar labels, paths, and display order", () => {
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

  it("assigns exact page titles by route kind", () => {
    const titleByPath = new Map(tenantRoutes.map((route) => [route.path, route.title]));
    expect(titleByPath.get("/security-access-control/roles")).toBe("Security administration");
    expect(titleByPath.get("/security-access-control/permissions")).toBe("Permissions");
    expect(titleByPath.get("/security-access-control/assignments")).toBe("Assignments");
    expect(titleByPath.get("/security-access-control/permission-sets")).toBe("Permission sets");
    expect(titleByPath.get("/security-access-control/field-security")).toBe("Field security");
    expect(titleByPath.get("/security-access-control/row-security")).toBe("Row security");
    expect(titleByPath.get("/security-access-control/security-profiles")).toBe("Security profiles");
    expect(titleByPath.get("/security-access-control/assignments/profile-assignments")).toBe(
      "Profile assignments"
    );
    expect(titleByPath.get("/security-access-control/audit-logs")).toBe("Security audit trail");
    expect(titleByPath.get("/security-access-control/roles/create")).toBe("Create security policy");
    expect(titleByPath.get("/security-access-control/roles/:id")).toBe("Security policy detail");
    expect(titleByPath.get("/security-access-control/roles/:id/edit")).toBe("Edit security policy");
    expect(titleByPath.get("/security-access-control/access-simulator")).toBe("Access simulator");
    expect(titleByPath.get("/security-access-control/configuration")).toBe(
      "Security configuration"
    );
  });

  it("links every contextual route to an existing sidebar parent", () => {
    const sidebarIds = new Set(
      tenantRoutes.filter((route) => route.navigation.type === "sidebar").map((route) => route.id)
    );
    expect(tenantRoutes.filter((route) => route.navigation.type === "contextual")).toHaveLength(
      expectedContextualParentByPath.size
    );
    for (const route of tenantRoutes) {
      const expectedParent = expectedContextualParentByPath.get(route.path);
      if (expectedParent) {
        expect(route.navigation.type).toBe("contextual");
        if (route.navigation.type !== "contextual") continue;
        expect(route.navigation.parentRouteId).toBe(expectedParent);
        expect(sidebarIds.has(route.navigation.parentRouteId)).toBe(true);
      } else {
        expect(route.navigation.type).toBe("sidebar");
      }
    }
  });
  it("shows only audit and simulation in SaaS", () => {
    const saas = tenantRoutes.filter((route) => route.modes?.some((mode) => mode === "saas"));
    expect(saas.map((route) => route.path)).toEqual(expectedSaasPaths);
    expect(saas.some((route) => route.path === "/security-access-control/roles")).toBe(false);
  });
  it("contains every required contextual family without broken links", () => {
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
