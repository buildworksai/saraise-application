/* eslint-disable max-lines-per-function -- route registry tests intentionally pin every governed route entry. */
import { Suspense, createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";

vi.mock("./pages/AgentListPage", () => ({
  AgentListPage: () => createElement("div", undefined, "AgentListPage resolved"),
}));
vi.mock("./pages/CreateAgentPage", () => ({
  CreateAgentPage: () => createElement("div", undefined, "CreateAgentPage resolved"),
}));
vi.mock("./pages/AgentDetailPage", () => ({
  AgentDetailPage: () => createElement("div", undefined, "AgentDetailPage resolved"),
}));
vi.mock("./pages/EditAgentPage", () => ({
  EditAgentPage: () => createElement("div", undefined, "EditAgentPage resolved"),
}));
vi.mock("./pages/EvaluationPage", () => ({
  EvaluationPage: () => createElement("div", undefined, "EvaluationPage resolved"),
}));
vi.mock("./pages/ExecutionListPage", () => ({
  ExecutionListPage: () => createElement("div", undefined, "ExecutionListPage resolved"),
}));
vi.mock("./pages/ExecutionDetailPage", () => ({
  ExecutionDetailPage: () => createElement("div", undefined, "ExecutionDetailPage resolved"),
}));
vi.mock("./pages/ScheduleListPage", () => ({
  ScheduleListPage: () => createElement("div", undefined, "ScheduleListPage resolved"),
}));
vi.mock("./pages/ScheduleCreatePage", () => ({
  ScheduleCreatePage: () => createElement("div", undefined, "ScheduleCreatePage resolved"),
}));
vi.mock("./pages/ScheduleDetailPage", () => ({
  ScheduleDetailPage: () => createElement("div", undefined, "ScheduleDetailPage resolved"),
}));
vi.mock("./pages/ApprovalQueuePage", () => ({
  ApprovalQueuePage: () => createElement("div", undefined, "ApprovalQueuePage resolved"),
}));
vi.mock("./pages/ApprovalDetailPage", () => ({
  ApprovalDetailPage: () => createElement("div", undefined, "ApprovalDetailPage resolved"),
}));
vi.mock("./pages/ConfigurationPage", () => ({
  ConfigurationPage: () => createElement("div", undefined, "ConfigurationPage resolved"),
}));
vi.mock("./pages/GovernancePage", () => ({
  GovernancePage: () => createElement("div", undefined, "GovernancePage resolved"),
}));
vi.mock("./pages/ToolListPage", () => ({
  ToolListPage: () => createElement("div", undefined, "ToolListPage resolved"),
}));
vi.mock("./pages/ToolCreatePage", () => ({
  ToolCreatePage: () => createElement("div", undefined, "ToolCreatePage resolved"),
}));
vi.mock("./pages/ToolDetailPage", () => ({
  ToolDetailPage: () => createElement("div", undefined, "ToolDetailPage resolved"),
}));
vi.mock("./pages/ToolEditPage", () => ({
  ToolEditPage: () => createElement("div", undefined, "ToolEditPage resolved"),
}));
vi.mock("./pages/UsagePage", () => ({
  UsagePage: () => createElement("div", undefined, "UsagePage resolved"),
}));
vi.mock("./pages/AuditExplorerPage", () => ({
  AuditExplorerPage: () => createElement("div", undefined, "AuditExplorerPage resolved"),
}));
vi.mock("./pages/AuditTrailDetailPage", () => ({
  AuditTrailDetailPage: () => createElement("div", undefined, "AuditTrailDetailPage resolved"),
}));

const expectedPaths = [
  "/ai-agents",
  "/ai-agents/create",
  "/ai-agents/:id",
  "/ai-agents/:id/edit",
  "/ai-agents/:id/evaluation",
  "/ai-agents/executions",
  "/ai-agents/executions/:id",
  "/ai-agents/schedules",
  "/ai-agents/schedules/create",
  "/ai-agents/schedules/:id",
  "/ai-agents/approvals",
  "/ai-agents/approvals/:id",
  "/ai-agents/configuration",
  "/ai-agents/governance",
  "/ai-agents/tools",
  "/ai-agents/tools/create",
  "/ai-agents/tools/:id",
  "/ai-agents/tools/:id/edit",
  "/ai-agents/usage",
  "/ai-agents/audit",
  "/ai-agents/audit/:id",
] as const;

const expectedTitles = [
  "Agent List",
  "Create Agent",
  "Agent Detail",
  "Edit Agent",
  "Evaluation",
  "Execution List",
  "Execution Detail",
  "Schedule List",
  "Schedule Create",
  "Schedule Detail",
  "Approval Queue",
  "Approval Detail",
  "Configuration",
  "Governance",
  "Tool List",
  "Tool Create",
  "Tool Detail",
  "Tool Edit",
  "Usage",
  "Audit Explorer",
  "Audit Trail Detail",
] as const;

const expectedRouteSurface = [
  ["ai-agent-management.agents.list", "Agents", "AgentList", "sidebar", undefined],
  [
    "ai-agent-management.agents.create",
    undefined,
    "CreateAgent",
    "contextual",
    "ai-agent-management.agents.list",
  ],
  [
    "ai-agent-management.agents.detail",
    undefined,
    "AgentDetail",
    "contextual",
    "ai-agent-management.agents.list",
  ],
  [
    "ai-agent-management.agents.edit",
    undefined,
    "EditAgent",
    "contextual",
    "ai-agent-management.agents.list",
  ],
  [
    "ai-agent-management.agents.evaluation",
    undefined,
    "Evaluation",
    "contextual",
    "ai-agent-management.agents.list",
  ],
  ["ai-agent-management.executions.list", "Executions", "ExecutionList", "sidebar", undefined],
  [
    "ai-agent-management.executions.detail",
    undefined,
    "ExecutionDetail",
    "contextual",
    "ai-agent-management.executions.list",
  ],
  [
    "ai-agent-management.schedules.list",
    undefined,
    "ScheduleList",
    "contextual",
    "ai-agent-management.executions.list",
  ],
  [
    "ai-agent-management.schedules.create",
    undefined,
    "ScheduleCreate",
    "contextual",
    "ai-agent-management.executions.list",
  ],
  [
    "ai-agent-management.schedules.detail",
    undefined,
    "ScheduleDetail",
    "contextual",
    "ai-agent-management.executions.list",
  ],
  ["ai-agent-management.approvals.list", "Approvals", "ApprovalQueue", "sidebar", undefined],
  [
    "ai-agent-management.approvals.detail",
    undefined,
    "ApprovalDetail",
    "contextual",
    "ai-agent-management.approvals.list",
  ],
  ["ai-agent-management.configuration", "Configuration", "Configuration", "sidebar", undefined],
  ["ai-agent-management.governance", "Governance", "Governance", "sidebar", undefined],
  [
    "ai-agent-management.tools.list",
    undefined,
    "ToolList",
    "contextual",
    "ai-agent-management.governance",
  ],
  [
    "ai-agent-management.tools.create",
    undefined,
    "ToolCreate",
    "contextual",
    "ai-agent-management.governance",
  ],
  [
    "ai-agent-management.tools.detail",
    undefined,
    "ToolDetail",
    "contextual",
    "ai-agent-management.governance",
  ],
  [
    "ai-agent-management.tools.edit",
    undefined,
    "ToolEdit",
    "contextual",
    "ai-agent-management.governance",
  ],
  ["ai-agent-management.usage", "Usage", "Usage", "sidebar", undefined],
  ["ai-agent-management.audit.list", "Audit", "AuditExplorer", "sidebar", undefined],
  [
    "ai-agent-management.audit.detail",
    undefined,
    "AuditTrailDetail",
    "contextual",
    "ai-agent-management.audit.list",
  ],
] as const;

async function loadRoutes() {
  return import("./routes");
}

describe("ai agent module routes", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    cleanup();
  });

  it("publishes exactly the required discoverable areas", async () => {
    const { tenantRoutes } = await loadRoutes();
    const labels = tenantRoutes.flatMap((route) =>
      route.navigation.type === "sidebar" ? [route.navigation.label] : []
    );

    expect(labels).toEqual([
      "Agents",
      "Executions",
      "Approvals",
      "Configuration",
      "Governance",
      "Usage",
      "Audit",
    ]);
    expect(tenantRoutes.every((route) => route.module === "ai_agent_management")).toBe(true);
  });

  it("publishes the exact ordered route surface", async () => {
    const { tenantRoutes } = await loadRoutes();

    expect(tenantRoutes.map((route) => route.path)).toEqual(expectedPaths);
    expect(tenantRoutes.map((route) => route.id)).toEqual(expectedRouteSurface.map(([id]) => id));
    expect(tenantRoutes.map((route) => route.title)).toEqual(expectedTitles);
  });

  it("derives route titles only from valid page source files", async () => {
    const { routeTitle } = await loadRoutes();

    expect(routeTitle({ sourceFile: "modules/ai_agent_management/pages/AgentListPage.tsx" })).toBe(
      "Agent List"
    );
    expect(routeTitle({ sourceFile: "modules/ai_agent_management/pages/APIKeyPage.tsx" })).toBe(
      "APIKey"
    );
    expect(() => routeTitle({ sourceFile: "" })).toThrow("AI agent route has invalid source file");
    expect(() => routeTitle({ sourceFile: "modules/ai_agent_management/pages/" })).toThrow(
      "AI agent route has invalid source file"
    );
  });

  it("publishes exact sidebar labels, paths, and display order", async () => {
    const { tenantRoutes } = await loadRoutes();
    const sidebar = tenantRoutes.filter((route) => route.navigation.type === "sidebar");

    expect(sidebar.map((route) => route.path)).toEqual([
      "/ai-agents",
      "/ai-agents/executions",
      "/ai-agents/approvals",
      "/ai-agents/configuration",
      "/ai-agents/governance",
      "/ai-agents/usage",
      "/ai-agents/audit",
    ]);
    expect(
      sidebar.flatMap((route) =>
        route.navigation.type === "sidebar" ? [route.navigation.label] : []
      )
    ).toEqual([
      "Agents",
      "Executions",
      "Approvals",
      "Configuration",
      "Governance",
      "Usage",
      "Audit",
    ]);
    expect(
      sidebar.flatMap((route) =>
        route.navigation.type === "sidebar" ? [route.navigation.order] : []
      )
    ).toEqual([0, 0, 0, 0, 0, 0, 0]);
  });

  it("has unique paths and valid contextual parents", async () => {
    const { tenantRoutes } = await loadRoutes();

    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
  });

  it("registers all required contextual workflows", async () => {
    const { tenantRoutes } = await loadRoutes();

    expect(
      tenantRoutes.map((route) =>
        route.navigation.type === "contextual" ? route.navigation.parentRouteId : undefined
      )
    ).toEqual(expectedRouteSurface.map(([, , , , parentRouteId]) => parentRouteId));
  });

  it("resolves every lazy page module to the declared page component", async () => {
    const { tenantRoutes } = await loadRoutes();

    for (const route of tenantRoutes) {
      render(
        createElement(
          Suspense,
          { fallback: createElement("div", undefined, "Loading page") },
          createElement(route.Page)
        )
      );
      const expectedTitle = route.title.replaceAll(" ", "");
      expect(await screen.findByText(`${expectedTitle}Page resolved`)).toBeInTheDocument();
      cleanup();
    }
  });
});
