import { lazy } from "react";
import { Activity, Bot, FileCheck2, Gauge, ScrollText, Settings2, ShieldCheck } from "lucide-react";
import type { TenantRoute } from "@/navigation/tenant-route-types";
import { ROUTES } from "./contracts";

const MODULE = "ai_agent_management";
const modes = ["development", "self-hosted", "saas"] as const;
const contextual = (parentRouteId: string) => ({ type: "contextual" as const, parentRouteId });

const routeDefinitions = [
  { id: "ai-agent-management.agents.list", module: MODULE, path: ROUTES.AGENTS, sourceFile: "modules/ai_agent_management/pages/AgentListPage.tsx", Page: lazy(() => import("./pages/AgentListPage").then(({ AgentListPage }) => ({ default: AgentListPage }))), modes, navigation: { type: "sidebar", label: "Agents", icon: Bot, order: 0 } },
  { id: "ai-agent-management.agents.create", module: MODULE, path: ROUTES.AGENT_CREATE, sourceFile: "modules/ai_agent_management/pages/CreateAgentPage.tsx", Page: lazy(() => import("./pages/CreateAgentPage").then(({ CreateAgentPage }) => ({ default: CreateAgentPage }))), modes, navigation: contextual("ai-agent-management.agents.list") },
  { id: "ai-agent-management.agents.detail", module: MODULE, path: ROUTES.AGENT_DETAIL(":id"), sourceFile: "modules/ai_agent_management/pages/AgentDetailPage.tsx", Page: lazy(() => import("./pages/AgentDetailPage").then(({ AgentDetailPage }) => ({ default: AgentDetailPage }))), modes, navigation: contextual("ai-agent-management.agents.list") },
  { id: "ai-agent-management.agents.edit", module: MODULE, path: ROUTES.AGENT_EDIT(":id"), sourceFile: "modules/ai_agent_management/pages/EditAgentPage.tsx", Page: lazy(() => import("./pages/EditAgentPage").then(({ EditAgentPage }) => ({ default: EditAgentPage }))), modes, navigation: contextual("ai-agent-management.agents.list") },
  { id: "ai-agent-management.agents.evaluation", module: MODULE, path: ROUTES.EVALUATION(":id"), sourceFile: "modules/ai_agent_management/pages/EvaluationPage.tsx", Page: lazy(() => import("./pages/EvaluationPage").then(({ EvaluationPage }) => ({ default: EvaluationPage }))), modes, navigation: contextual("ai-agent-management.agents.list") },

  { id: "ai-agent-management.executions.list", module: MODULE, path: ROUTES.EXECUTIONS, sourceFile: "modules/ai_agent_management/pages/ExecutionListPage.tsx", Page: lazy(() => import("./pages/ExecutionListPage").then(({ ExecutionListPage }) => ({ default: ExecutionListPage }))), modes, navigation: { type: "sidebar", label: "Executions", icon: Activity, order: 0 } },
  { id: "ai-agent-management.executions.detail", module: MODULE, path: ROUTES.EXECUTION_DETAIL(":id"), sourceFile: "modules/ai_agent_management/pages/ExecutionDetailPage.tsx", Page: lazy(() => import("./pages/ExecutionDetailPage").then(({ ExecutionDetailPage }) => ({ default: ExecutionDetailPage }))), modes, navigation: contextual("ai-agent-management.executions.list") },
  { id: "ai-agent-management.schedules.list", module: MODULE, path: ROUTES.SCHEDULES, sourceFile: "modules/ai_agent_management/pages/ScheduleListPage.tsx", Page: lazy(() => import("./pages/ScheduleListPage").then(({ ScheduleListPage }) => ({ default: ScheduleListPage }))), modes, navigation: contextual("ai-agent-management.executions.list") },
  { id: "ai-agent-management.schedules.create", module: MODULE, path: ROUTES.SCHEDULE_CREATE, sourceFile: "modules/ai_agent_management/pages/ScheduleCreatePage.tsx", Page: lazy(() => import("./pages/ScheduleCreatePage").then(({ ScheduleCreatePage }) => ({ default: ScheduleCreatePage }))), modes, navigation: contextual("ai-agent-management.executions.list") },
  { id: "ai-agent-management.schedules.detail", module: MODULE, path: ROUTES.SCHEDULE_DETAIL(":id"), sourceFile: "modules/ai_agent_management/pages/ScheduleDetailPage.tsx", Page: lazy(() => import("./pages/ScheduleDetailPage").then(({ ScheduleDetailPage }) => ({ default: ScheduleDetailPage }))), modes, navigation: contextual("ai-agent-management.executions.list") },

  { id: "ai-agent-management.approvals.list", module: MODULE, path: ROUTES.APPROVALS, sourceFile: "modules/ai_agent_management/pages/ApprovalQueuePage.tsx", Page: lazy(() => import("./pages/ApprovalQueuePage").then(({ ApprovalQueuePage }) => ({ default: ApprovalQueuePage }))), modes, navigation: { type: "sidebar", label: "Approvals", icon: FileCheck2, order: 0 } },
  { id: "ai-agent-management.approvals.detail", module: MODULE, path: ROUTES.APPROVAL_DETAIL(":id"), sourceFile: "modules/ai_agent_management/pages/ApprovalDetailPage.tsx", Page: lazy(() => import("./pages/ApprovalDetailPage").then(({ ApprovalDetailPage }) => ({ default: ApprovalDetailPage }))), modes, navigation: contextual("ai-agent-management.approvals.list") },

  { id: "ai-agent-management.configuration", module: MODULE, path: ROUTES.CONFIGURATION, sourceFile: "modules/ai_agent_management/pages/ConfigurationPage.tsx", Page: lazy(() => import("./pages/ConfigurationPage").then(({ ConfigurationPage }) => ({ default: ConfigurationPage }))), modes, navigation: { type: "sidebar", label: "Configuration", icon: Settings2, order: 0 } },
  { id: "ai-agent-management.governance", module: MODULE, path: ROUTES.GOVERNANCE, sourceFile: "modules/ai_agent_management/pages/GovernancePage.tsx", Page: lazy(() => import("./pages/GovernancePage").then(({ GovernancePage }) => ({ default: GovernancePage }))), modes, navigation: { type: "sidebar", label: "Governance", icon: ShieldCheck, order: 0 } },
  { id: "ai-agent-management.tools.list", module: MODULE, path: ROUTES.TOOLS, sourceFile: "modules/ai_agent_management/pages/ToolListPage.tsx", Page: lazy(() => import("./pages/ToolListPage").then(({ ToolListPage }) => ({ default: ToolListPage }))), modes, navigation: contextual("ai-agent-management.governance") },
  { id: "ai-agent-management.tools.create", module: MODULE, path: ROUTES.TOOL_CREATE, sourceFile: "modules/ai_agent_management/pages/ToolCreatePage.tsx", Page: lazy(() => import("./pages/ToolCreatePage").then(({ ToolCreatePage }) => ({ default: ToolCreatePage }))), modes, navigation: contextual("ai-agent-management.governance") },
  { id: "ai-agent-management.tools.detail", module: MODULE, path: ROUTES.TOOL_DETAIL(":id"), sourceFile: "modules/ai_agent_management/pages/ToolDetailPage.tsx", Page: lazy(() => import("./pages/ToolDetailPage").then(({ ToolDetailPage }) => ({ default: ToolDetailPage }))), modes, navigation: contextual("ai-agent-management.governance") },
  { id: "ai-agent-management.tools.edit", module: MODULE, path: ROUTES.TOOL_EDIT(":id"), sourceFile: "modules/ai_agent_management/pages/ToolEditPage.tsx", Page: lazy(() => import("./pages/ToolEditPage").then(({ ToolEditPage }) => ({ default: ToolEditPage }))), modes, navigation: contextual("ai-agent-management.governance") },

  { id: "ai-agent-management.usage", module: MODULE, path: ROUTES.USAGE, sourceFile: "modules/ai_agent_management/pages/UsagePage.tsx", Page: lazy(() => import("./pages/UsagePage").then(({ UsagePage }) => ({ default: UsagePage }))), modes, navigation: { type: "sidebar", label: "Usage", icon: Gauge, order: 0 } },
  { id: "ai-agent-management.audit.list", module: MODULE, path: ROUTES.AUDIT, sourceFile: "modules/ai_agent_management/pages/AuditExplorerPage.tsx", Page: lazy(() => import("./pages/AuditExplorerPage").then(({ AuditExplorerPage }) => ({ default: AuditExplorerPage }))), modes, navigation: { type: "sidebar", label: "Audit", icon: ScrollText, order: 0 } },
  { id: "ai-agent-management.audit.detail", module: MODULE, path: ROUTES.AUDIT_TRAIL_DETAIL(":id"), sourceFile: "modules/ai_agent_management/pages/AuditTrailDetailPage.tsx", Page: lazy(() => import("./pages/AuditTrailDetailPage").then(({ AuditTrailDetailPage }) => ({ default: AuditTrailDetailPage }))), modes, navigation: contextual("ai-agent-management.audit.list") },
] satisfies readonly TenantRoute[];

function routeTitle(route: TenantRoute): string {
  const file = route.sourceFile.split("/").at(-1)?.replace(/Page\.tsx$/u, "") ?? "AI agent management";
  return file.replace(/([a-z])([A-Z])/gu, "$1 $2");
}

export const tenantRoutes = routeDefinitions.map((route) => ({
  ...route,
  title: routeTitle(route),
})) satisfies readonly TenantRoute[];

export default tenantRoutes;
