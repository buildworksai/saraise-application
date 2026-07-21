import { lazy } from "react";
import { Activity, CalendarClock, Workflow } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";

const modes = ["development", "self-hosted", "saas"] as const;

export const tenantRoutes = [
  {
    id: "automation-orchestration.definitions.list",
    module: "automation_orchestration",
    path: "/automation-orchestration",
    sourceFile: "modules/automation_orchestration/pages/DefinitionsListPage.tsx",
    Page: lazy(() => import("./pages/DefinitionsListPage").then(({ DefinitionsListPage }) => ({ default: DefinitionsListPage }))),
    modes,
    navigation: { type: "sidebar", label: "Definitions", icon: Workflow, order: 60 },
  },
  {
    id: "automation-orchestration.definitions.create",
    module: "automation_orchestration",
    path: "/automation-orchestration/definitions/new",
    sourceFile: "modules/automation_orchestration/pages/DefinitionCreatePage.tsx",
    Page: lazy(() => import("./pages/DefinitionCreatePage").then(({ DefinitionCreatePage }) => ({ default: DefinitionCreatePage }))),
    modes,
    navigation: { type: "contextual", parentRouteId: "automation-orchestration.definitions.list" },
  },
  {
    id: "automation-orchestration.definitions.detail",
    module: "automation_orchestration",
    path: "/automation-orchestration/definitions/:id",
    sourceFile: "modules/automation_orchestration/pages/DefinitionDetailPage.tsx",
    Page: lazy(() => import("./pages/DefinitionDetailPage").then(({ DefinitionDetailPage }) => ({ default: DefinitionDetailPage }))),
    modes,
    navigation: { type: "contextual", parentRouteId: "automation-orchestration.definitions.list" },
  },
  {
    id: "automation-orchestration.definitions.edit",
    module: "automation_orchestration",
    path: "/automation-orchestration/definitions/:id/edit",
    sourceFile: "modules/automation_orchestration/pages/DefinitionEditPage.tsx",
    Page: lazy(() => import("./pages/DefinitionEditPage").then(({ DefinitionEditPage }) => ({ default: DefinitionEditPage }))),
    modes,
    navigation: { type: "contextual", parentRouteId: "automation-orchestration.definitions.list" },
  },
  {
    id: "automation-orchestration.schedules.list",
    module: "automation_orchestration",
    path: "/automation-orchestration/schedules",
    sourceFile: "modules/automation_orchestration/pages/SchedulesListPage.tsx",
    Page: lazy(() => import("./pages/SchedulesListPage").then(({ SchedulesListPage }) => ({ default: SchedulesListPage }))),
    modes,
    navigation: { type: "sidebar", label: "Schedules", icon: CalendarClock, order: 61 },
  },
  {
    id: "automation-orchestration.schedules.create",
    module: "automation_orchestration",
    path: "/automation-orchestration/schedules/new",
    sourceFile: "modules/automation_orchestration/pages/ScheduleCreatePage.tsx",
    Page: lazy(() => import("./pages/ScheduleCreatePage").then(({ ScheduleCreatePage }) => ({ default: ScheduleCreatePage }))),
    modes,
    navigation: { type: "contextual", parentRouteId: "automation-orchestration.schedules.list" },
  },
  {
    id: "automation-orchestration.schedules.edit",
    module: "automation_orchestration",
    path: "/automation-orchestration/schedules/:id/edit",
    sourceFile: "modules/automation_orchestration/pages/ScheduleEditPage.tsx",
    Page: lazy(() => import("./pages/ScheduleEditPage").then(({ ScheduleEditPage }) => ({ default: ScheduleEditPage }))),
    modes,
    navigation: { type: "contextual", parentRouteId: "automation-orchestration.schedules.list" },
  },
  {
    id: "automation-orchestration.runs.list",
    module: "automation_orchestration",
    path: "/automation-orchestration/runs",
    sourceFile: "modules/automation_orchestration/pages/RunsListPage.tsx",
    Page: lazy(() => import("./pages/RunsListPage").then(({ RunsListPage }) => ({ default: RunsListPage }))),
    modes,
    navigation: { type: "sidebar", label: "Runs", icon: Activity, order: 62 },
  },
  {
    id: "automation-orchestration.runs.detail",
    module: "automation_orchestration",
    path: "/automation-orchestration/runs/:runId",
    sourceFile: "modules/automation_orchestration/pages/RunDetailPage.tsx",
    Page: lazy(() => import("./pages/RunDetailPage").then(({ RunDetailPage }) => ({ default: RunDetailPage }))),
    modes,
    navigation: { type: "contextual", parentRouteId: "automation-orchestration.runs.list" },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
