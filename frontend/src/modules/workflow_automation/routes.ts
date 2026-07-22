import { lazy } from "react";
import { CheckSquare, ListChecks, Workflow } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";
import { ROUTES } from "./contracts";

const modes = ["development", "self-hosted", "saas"] as const;
export const tenantRoutes = [
  { id: "workflow-automation.workflows.list", module: "workflow_automation", path: ROUTES.WORKFLOWS, sourceFile: "modules/workflow_automation/pages/WorkflowListPage.tsx", Page: lazy(() => import("./pages/WorkflowListPage").then(({ WorkflowListPage }) => ({ default: WorkflowListPage }))), modes, navigation: { type: "sidebar", label: "Workflows", icon: Workflow, order: 80 } },
  { id: "workflow-automation.workflows.create", module: "workflow_automation", path: ROUTES.WORKFLOW_CREATE, sourceFile: "modules/workflow_automation/pages/WorkflowCreatePage.tsx", Page: lazy(() => import("./pages/WorkflowCreatePage").then(({ WorkflowCreatePage }) => ({ default: WorkflowCreatePage }))), modes, navigation: { type: "contextual", parentRouteId: "workflow-automation.workflows.list" } },
  { id: "workflow-automation.workflows.detail", module: "workflow_automation", path: ROUTES.WORKFLOW_DETAIL(":id"), sourceFile: "modules/workflow_automation/pages/WorkflowDetailPage.tsx", Page: lazy(() => import("./pages/WorkflowDetailPage").then(({ WorkflowDetailPage }) => ({ default: WorkflowDetailPage }))), modes, navigation: { type: "contextual", parentRouteId: "workflow-automation.workflows.list" } },
  { id: "workflow-automation.workflows.edit", module: "workflow_automation", path: ROUTES.WORKFLOW_EDIT(":id"), sourceFile: "modules/workflow_automation/pages/WorkflowEditPage.tsx", Page: lazy(() => import("./pages/WorkflowEditPage").then(({ WorkflowEditPage }) => ({ default: WorkflowEditPage }))), modes, navigation: { type: "contextual", parentRouteId: "workflow-automation.workflows.list" } },
  { id: "workflow-automation.instances.list", module: "workflow_automation", path: ROUTES.INSTANCES, sourceFile: "modules/workflow_automation/pages/WorkflowInstanceListPage.tsx", Page: lazy(() => import("./pages/WorkflowInstanceListPage").then(({ WorkflowInstanceListPage }) => ({ default: WorkflowInstanceListPage }))), modes, navigation: { type: "sidebar", label: "Executions", icon: ListChecks, order: 81 } },
  { id: "workflow-automation.instances.detail", module: "workflow_automation", path: ROUTES.INSTANCE_DETAIL(":id"), sourceFile: "modules/workflow_automation/pages/WorkflowInstanceDetailPage.tsx", Page: lazy(() => import("./pages/WorkflowInstanceDetailPage").then(({ WorkflowInstanceDetailPage }) => ({ default: WorkflowInstanceDetailPage }))), modes, navigation: { type: "contextual", parentRouteId: "workflow-automation.instances.list" } },
  { id: "workflow-automation.tasks.list", module: "workflow_automation", path: ROUTES.TASKS, sourceFile: "modules/workflow_automation/pages/TaskInboxPage.tsx", Page: lazy(() => import("./pages/TaskInboxPage").then(({ TaskInboxPage }) => ({ default: TaskInboxPage }))), modes, navigation: { type: "sidebar", label: "My Tasks", icon: CheckSquare, order: 82 } },
  { id: "workflow-automation.tasks.detail", module: "workflow_automation", path: ROUTES.TASK_DETAIL(":id"), sourceFile: "modules/workflow_automation/pages/WorkflowTaskDetailPage.tsx", Page: lazy(() => import("./pages/WorkflowTaskDetailPage").then(({ WorkflowTaskDetailPage }) => ({ default: WorkflowTaskDetailPage }))), modes, navigation: { type: "contextual", parentRouteId: "workflow-automation.tasks.list" } },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
