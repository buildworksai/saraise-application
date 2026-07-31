/* eslint-disable max-lines-per-function -- exact route surface matrix intentionally keeps labels, paths, permissions, and order together. */
import { describe, expect, it } from "vitest";
import {
  CheckSquare,
  FilePlus2,
  History,
  ListChecks,
  Pencil,
  Settings,
  Workflow,
} from "lucide-react";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "../../routes";

describe("workflow automation route registry", () => {
  const expectedRoutes = [
    [
      "workflow-automation.workflows.list",
      "/workflow-automation/workflows",
      "Workflows",
      "sidebar",
      "Workflows",
      0,
      undefined,
      "workflow_automation.workflow:read",
      Workflow,
      "modules/workflow_automation/pages/WorkflowListPage.tsx",
    ],
    [
      "workflow-automation.workflows.create",
      "/workflow-automation/workflows/new",
      "Create workflow",
      "contextual",
      "Create workflow",
      0.1,
      "workflow-automation.workflows.list",
      "workflow_automation.workflow:create",
      FilePlus2,
      "modules/workflow_automation/pages/WorkflowCreatePage.tsx",
    ],
    [
      "workflow-automation.workflows.detail",
      "/workflow-automation/workflows/:id",
      "Workflow detail",
      "contextual",
      "Workflow detail",
      0.2,
      "workflow-automation.workflows.list",
      "workflow_automation.workflow:read",
      Workflow,
      "modules/workflow_automation/pages/WorkflowDetailPage.tsx",
    ],
    [
      "workflow-automation.workflows.edit",
      "/workflow-automation/workflows/:id/edit",
      "Edit workflow",
      "contextual",
      "Edit workflow",
      0.3,
      "workflow-automation.workflows.list",
      "workflow_automation.workflow:update",
      Pencil,
      "modules/workflow_automation/pages/WorkflowEditPage.tsx",
    ],
    [
      "workflow-automation.instances.list",
      "/workflow-automation/instances",
      "Workflow executions",
      "sidebar",
      "Executions",
      1,
      undefined,
      "workflow_automation.instance:read",
      ListChecks,
      "modules/workflow_automation/pages/WorkflowInstanceListPage.tsx",
    ],
    [
      "workflow-automation.instances.detail",
      "/workflow-automation/instances/:id",
      "Workflow execution detail",
      "contextual",
      "Execution detail",
      1.1,
      "workflow-automation.instances.list",
      "workflow_automation.instance:read",
      History,
      "modules/workflow_automation/pages/WorkflowInstanceDetailPage.tsx",
    ],
    [
      "workflow-automation.tasks.list",
      "/workflow-automation/tasks",
      "Workflow tasks",
      "sidebar",
      "My Tasks",
      2,
      undefined,
      "workflow_automation.task:read",
      CheckSquare,
      "modules/workflow_automation/pages/TaskInboxPage.tsx",
    ],
    [
      "workflow-automation.tasks.detail",
      "/workflow-automation/tasks/:id",
      "Workflow task detail",
      "contextual",
      "Task detail",
      2.1,
      "workflow-automation.tasks.list",
      "workflow_automation.task:read",
      CheckSquare,
      "modules/workflow_automation/pages/WorkflowTaskDetailPage.tsx",
    ],
    [
      "workflow-automation.configuration",
      "/workflow-automation/configuration",
      "Workflow configuration",
      "sidebar",
      "Configuration",
      3,
      undefined,
      "workflow_automation.configuration:read",
      Settings,
      "modules/workflow_automation/pages/WorkflowConfigurationPage.tsx",
    ],
  ] as const;

  it("discovers every required page with four sidebar parents", () => {
    expect(
      tenantRoutes.map((route) => [
        route.id,
        route.path,
        route.title,
        route.navigation.type,
        route.navigation.label,
        route.navigation.order,
        route.navigation.type === "contextual" ? route.navigation.parentRouteId : undefined,
        route.requiredPermission,
        route.navigation.icon,
        route.sourceFile,
      ])
    ).toEqual(expectedRoutes);
    expect(tenantRoutes.filter((route) => route.navigation.type === "sidebar")).toHaveLength(4);
  });

  it("has unique paths and same-module contextual parents in every runtime mode", () => {
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    for (const route of tenantRoutes) {
      expect(route.module).toBe("workflow_automation");
      expect(route.Page).toBeDefined();
      expect(route.modes).toEqual(["development", "self-hosted", "saas"]);
      if (route.navigation.type === "sidebar") expect(route.path).not.toContain(":");
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
