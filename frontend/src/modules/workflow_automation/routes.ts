import { lazy } from "react";
import { CheckSquare, FilePlus2, History, ListChecks, Pencil, Settings, Workflow } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";
import { ROUTES } from "./contracts";

const modes = ["development", "self-hosted", "saas"] as const;
const order = {
  workflows: 0,
  create: 0.1,
  detail: 0.2,
  edit: 0.3,
  instances: 1,
  instanceDetail: 1.1,
  tasks: 2,
  taskDetail: 2.1,
  configuration: 3,
} as const;

export const tenantRoutes = [
  { id: "workflow-automation.workflows.list", module: "workflow_automation", path: ROUTES.WORKFLOWS, title: "Workflows", sourceFile: "modules/workflow_automation/pages/WorkflowListPage.tsx", Page: lazy(() => import("./pages/WorkflowListPage").then(({ WorkflowListPage }) => ({ default: WorkflowListPage }))), modes, requiredPermission: "workflow_automation.workflow:read", navigation: { type: "sidebar", label: "Workflows", icon: Workflow, order: order.workflows } },
  { id: "workflow-automation.workflows.create", module: "workflow_automation", path: ROUTES.WORKFLOW_CREATE, title: "Create workflow", sourceFile: "modules/workflow_automation/pages/WorkflowCreatePage.tsx", Page: lazy(() => import("./pages/WorkflowCreatePage").then(({ WorkflowCreatePage }) => ({ default: WorkflowCreatePage }))), modes, requiredPermission: "workflow_automation.workflow:create", navigation: { type: "contextual", parentRouteId: "workflow-automation.workflows.list", label: "Create workflow", icon: FilePlus2, order: order.create } },
  { id: "workflow-automation.workflows.detail", module: "workflow_automation", path: ROUTES.WORKFLOW_DETAIL(":id"), title: "Workflow detail", sourceFile: "modules/workflow_automation/pages/WorkflowDetailPage.tsx", Page: lazy(() => import("./pages/WorkflowDetailPage").then(({ WorkflowDetailPage }) => ({ default: WorkflowDetailPage }))), modes, requiredPermission: "workflow_automation.workflow:read", navigation: { type: "contextual", parentRouteId: "workflow-automation.workflows.list", label: "Workflow detail", icon: Workflow, order: order.detail } },
  { id: "workflow-automation.workflows.edit", module: "workflow_automation", path: ROUTES.WORKFLOW_EDIT(":id"), title: "Edit workflow", sourceFile: "modules/workflow_automation/pages/WorkflowEditPage.tsx", Page: lazy(() => import("./pages/WorkflowEditPage").then(({ WorkflowEditPage }) => ({ default: WorkflowEditPage }))), modes, requiredPermission: "workflow_automation.workflow:update", navigation: { type: "contextual", parentRouteId: "workflow-automation.workflows.list", label: "Edit workflow", icon: Pencil, order: order.edit } },
  { id: "workflow-automation.instances.list", module: "workflow_automation", path: ROUTES.INSTANCES, title: "Workflow executions", sourceFile: "modules/workflow_automation/pages/WorkflowInstanceListPage.tsx", Page: lazy(() => import("./pages/WorkflowInstanceListPage").then(({ WorkflowInstanceListPage }) => ({ default: WorkflowInstanceListPage }))), modes, requiredPermission: "workflow_automation.instance:read", navigation: { type: "sidebar", label: "Executions", icon: ListChecks, order: order.instances } },
  { id: "workflow-automation.instances.detail", module: "workflow_automation", path: ROUTES.INSTANCE_DETAIL(":id"), title: "Workflow execution detail", sourceFile: "modules/workflow_automation/pages/WorkflowInstanceDetailPage.tsx", Page: lazy(() => import("./pages/WorkflowInstanceDetailPage").then(({ WorkflowInstanceDetailPage }) => ({ default: WorkflowInstanceDetailPage }))), modes, requiredPermission: "workflow_automation.instance:read", navigation: { type: "contextual", parentRouteId: "workflow-automation.instances.list", label: "Execution detail", icon: History, order: order.instanceDetail } },
  { id: "workflow-automation.tasks.list", module: "workflow_automation", path: ROUTES.TASKS, title: "Workflow tasks", sourceFile: "modules/workflow_automation/pages/TaskInboxPage.tsx", Page: lazy(() => import("./pages/TaskInboxPage").then(({ TaskInboxPage }) => ({ default: TaskInboxPage }))), modes, requiredPermission: "workflow_automation.task:read", navigation: { type: "sidebar", label: "My Tasks", icon: CheckSquare, order: order.tasks } },
  { id: "workflow-automation.tasks.detail", module: "workflow_automation", path: ROUTES.TASK_DETAIL(":id"), title: "Workflow task detail", sourceFile: "modules/workflow_automation/pages/WorkflowTaskDetailPage.tsx", Page: lazy(() => import("./pages/WorkflowTaskDetailPage").then(({ WorkflowTaskDetailPage }) => ({ default: WorkflowTaskDetailPage }))), modes, requiredPermission: "workflow_automation.task:read", navigation: { type: "contextual", parentRouteId: "workflow-automation.tasks.list", label: "Task detail", icon: CheckSquare, order: order.taskDetail } },
  { id: "workflow-automation.configuration", module: "workflow_automation", path: ROUTES.CONFIGURATION, title: "Workflow configuration", sourceFile: "modules/workflow_automation/pages/WorkflowConfigurationPage.tsx", Page: lazy(() => import("./pages/WorkflowConfigurationPage").then(({ WorkflowConfigurationPage }) => ({ default: WorkflowConfigurationPage }))), modes, requiredPermission: "workflow_automation.configuration:read", navigation: { type: "sidebar", label: "Configuration", icon: Settings, order: order.configuration } },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
