/* eslint-disable max-lines-per-function -- exact route surface matrix intentionally keeps labels, paths, and order together. */
import { describe, expect, it } from "vitest";
import { Activity, CalendarClock, Settings2, Workflow } from "lucide-react";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "../../routes";

describe("automation orchestration route registry", () => {
  const expectedRoutes = [
    [
      "automation-orchestration.definitions.list",
      "/automation-orchestration",
      "Orchestration definitions",
      "sidebar",
      "Definitions",
      60,
      undefined,
      Workflow,
      "modules/automation_orchestration/pages/DefinitionsListPage.tsx",
    ],
    [
      "automation-orchestration.configuration",
      "/automation-orchestration/configuration",
      "Orchestration configuration",
      "sidebar",
      "Configuration",
      63,
      undefined,
      Settings2,
      "modules/automation_orchestration/pages/ConfigurationPage.tsx",
    ],
    [
      "automation-orchestration.definitions.create",
      "/automation-orchestration/definitions/new",
      "Create orchestration definition",
      "contextual",
      undefined,
      undefined,
      "automation-orchestration.definitions.list",
      undefined,
      "modules/automation_orchestration/pages/DefinitionCreatePage.tsx",
    ],
    [
      "automation-orchestration.definitions.detail",
      "/automation-orchestration/definitions/:id",
      "Orchestration definition",
      "contextual",
      undefined,
      undefined,
      "automation-orchestration.definitions.list",
      undefined,
      "modules/automation_orchestration/pages/DefinitionDetailPage.tsx",
    ],
    [
      "automation-orchestration.definitions.edit",
      "/automation-orchestration/definitions/:id/edit",
      "Edit orchestration graph",
      "contextual",
      undefined,
      undefined,
      "automation-orchestration.definitions.list",
      undefined,
      "modules/automation_orchestration/pages/DefinitionEditPage.tsx",
    ],
    [
      "automation-orchestration.schedules.list",
      "/automation-orchestration/schedules",
      "Orchestration schedules",
      "sidebar",
      "Schedules",
      61,
      undefined,
      CalendarClock,
      "modules/automation_orchestration/pages/SchedulesListPage.tsx",
    ],
    [
      "automation-orchestration.schedules.create",
      "/automation-orchestration/schedules/new",
      "Create orchestration schedule",
      "contextual",
      undefined,
      undefined,
      "automation-orchestration.schedules.list",
      undefined,
      "modules/automation_orchestration/pages/ScheduleCreatePage.tsx",
    ],
    [
      "automation-orchestration.schedules.edit",
      "/automation-orchestration/schedules/:id/edit",
      "Edit orchestration schedule",
      "contextual",
      undefined,
      undefined,
      "automation-orchestration.schedules.list",
      undefined,
      "modules/automation_orchestration/pages/ScheduleEditPage.tsx",
    ],
    [
      "automation-orchestration.runs.list",
      "/automation-orchestration/runs",
      "Orchestration runs",
      "sidebar",
      "Runs",
      62,
      undefined,
      Activity,
      "modules/automation_orchestration/pages/RunsListPage.tsx",
    ],
    [
      "automation-orchestration.runs.detail",
      "/automation-orchestration/runs/:runId",
      "Orchestration run detail",
      "contextual",
      undefined,
      undefined,
      "automation-orchestration.runs.list",
      undefined,
      "modules/automation_orchestration/pages/RunDetailPage.tsx",
    ],
  ] as const;

  it("declares the configuration sidebar route and six contextual lazy routes", () => {
    expect(
      tenantRoutes.map((route) => [
        route.id,
        route.path,
        route.title,
        route.navigation.type,
        route.navigation.type === "sidebar" ? route.navigation.label : undefined,
        route.navigation.type === "sidebar" ? route.navigation.order : undefined,
        route.navigation.type === "contextual" ? route.navigation.parentRouteId : undefined,
        route.navigation.type === "sidebar" ? route.navigation.icon : undefined,
        route.sourceFile,
      ])
    ).toEqual(expectedRoutes);
    expect(tenantRoutes.filter((route) => route.navigation.type === "sidebar")).toHaveLength(4);
    expect(tenantRoutes.filter((route) => route.navigation.type === "contextual")).toHaveLength(6);
    expect(tenantRoutes.every((route) => typeof route.Page === "object")).toBe(true);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
  });

  it("uses unique ids and paths with valid same-module parents", () => {
    const ids = new Set(tenantRoutes.map((route) => route.id));
    const paths = new Set(tenantRoutes.map((route) => route.path));
    expect(ids.size).toBe(tenantRoutes.length);
    expect(paths.size).toBe(tenantRoutes.length);
    for (const route of tenantRoutes) {
      expect(route.module).toBe("automation_orchestration");
      expect(route.modes).toEqual(["development", "self-hosted", "saas"]);
      if (route.navigation.type === "contextual") {
        const parent = tenantRoutes.find(
          (candidate) => candidate.id === route.navigation.parentRouteId
        );
        expect(parent?.module).toBe(route.module);
        expect(parent?.navigation.type).toBe("sidebar");
      }
    }
  });
});
