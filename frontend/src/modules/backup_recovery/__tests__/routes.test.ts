import { describe, expect, it } from "vitest";

async function loadTenantRoutes() {
  const { tenantRoutes } = await import("../routes");
  return tenantRoutes;
}

describe("backup recovery route registry", () => {
  it("registers all required sidebar and contextual pages", async () => {
    const tenantRoutes = await loadTenantRoutes();
    const paths = tenantRoutes.map((route) => route.path);
    expect(paths).toEqual(
      expect.arrayContaining([
        "/backup-recovery",
        "/backup-recovery/jobs",
        "/backup-recovery/jobs/new",
        "/backup-recovery/jobs/:id",
        "/backup-recovery/jobs/:id/edit",
        "/backup-recovery/schedules",
        "/backup-recovery/schedules/new",
        "/backup-recovery/schedules/:id/edit",
        "/backup-recovery/retention-policies",
        "/backup-recovery/retention-policies/new",
        "/backup-recovery/storage-targets",
        "/backup-recovery/storage-targets/new",
        "/backup-recovery/archives",
        "/backup-recovery/archives/:id",
        "/backup-recovery/verifications",
        "/backup-recovery/verifications/:id",
      ])
    );
    expect(tenantRoutes.filter((route) => route.navigation.type === "sidebar")).toHaveLength(7);
  });

  it("gives every contextual route a valid module-owned parent", async () => {
    const tenantRoutes = await loadTenantRoutes();
    const ids = new Set(tenantRoutes.map((route) => route.id));
    for (const route of tenantRoutes) {
      expect(route.module).toBe("backup_recovery");
      expect(route.title?.trim()).toBeTruthy();
      if (route.navigation.type === "contextual")
        expect(ids.has(route.navigation.parentRouteId)).toBe(true);
    }
  });

  it("publishes exact browser titles for every backup recovery route", async () => {
    const tenantRoutes = await loadTenantRoutes();
    expect(Object.fromEntries(tenantRoutes.map((route) => [route.path, route.title]))).toEqual({
      "/backup-recovery": "Backup protection posture",
      "/backup-recovery/jobs": "Backup jobs",
      "/backup-recovery/jobs/new": "Request backup",
      "/backup-recovery/jobs/:id": "Backup job detail",
      "/backup-recovery/jobs/:id/edit": "Edit backup request",
      "/backup-recovery/schedules": "Backup schedules",
      "/backup-recovery/schedules/new": "Create backup schedule",
      "/backup-recovery/schedules/:id": "Backup schedule detail",
      "/backup-recovery/schedules/:id/edit": "Edit backup schedule",
      "/backup-recovery/retention-policies": "Retention policies",
      "/backup-recovery/retention-policies/new": "Create retention policy",
      "/backup-recovery/retention-policies/:id": "Retention policy detail",
      "/backup-recovery/retention-policies/:id/edit": "Edit retention policy",
      "/backup-recovery/storage-targets": "Storage targets",
      "/backup-recovery/storage-targets/new": "Add storage target",
      "/backup-recovery/storage-targets/:id": "Storage target detail",
      "/backup-recovery/storage-targets/:id/edit": "Edit storage target",
      "/backup-recovery/archives": "Backup artifacts",
      "/backup-recovery/archives/:id": "Backup artifact detail",
      "/backup-recovery/verifications": "Integrity verifications",
      "/backup-recovery/verifications/:id": "Integrity verification detail",
    });
  });
});
