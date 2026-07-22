import { describe, expect, it } from "vitest";
import { tenantRoutes } from "../routes";

describe("backup recovery route registry", () => {
  it("registers all required sidebar and contextual pages", () => {
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

  it("gives every contextual route a valid module-owned parent", () => {
    const ids = new Set(tenantRoutes.map((route) => route.id));
    for (const route of tenantRoutes) {
      expect(route.module).toBe("backup_recovery");
      if (route.navigation.type === "contextual")
        expect(ids.has(route.navigation.parentRouteId)).toBe(true);
    }
  });
});
