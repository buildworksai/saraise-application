import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentDetailPage } from "./AgentDetailPage";
import { ApprovalDetailPage } from "./ApprovalDetailPage";
import { AuditTrailDetailPage } from "./AuditTrailDetailPage";
import { EditAgentPage } from "./EditAgentPage";
import { EvaluationPage } from "./EvaluationPage";
import { ExecutionDetailPage } from "./ExecutionDetailPage";
import { ScheduleDetailPage } from "./ScheduleDetailPage";
import { ToolDetailPage } from "./ToolDetailPage";
import { ToolEditPage } from "./ToolEditPage";
import { aiAgentService } from "../services/ai-agent-service";

vi.mock("../services/ai-agent-service", () => ({
  aiAgentService: {
    getAgent: vi.fn(),
    getExecution: vi.fn(),
    listToolInvocations: vi.fn(),
    listApprovals: vi.fn(),
    listEgressRequests: vi.fn(),
    listCostRecords: vi.fn(),
    listAuditEvents: vi.fn(),
    getSchedule: vi.fn(),
    getApproval: vi.fn(),
    getTool: vi.fn(),
    getAuditTrail: vi.fn(),
  },
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderRoute(element: React.ReactElement, pattern: string, path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AI agent route terminal states", () => {
  afterEach(() => vi.clearAllMocks());

  it.each([
    ["agent detail", <AgentDetailPage />, "/ai-agents/:id", "/ai-agents/not-a-uuid", "getAgent"],
    ["agent edit", <EditAgentPage />, "/ai-agents/:id/edit", "/ai-agents/not-a-uuid/edit", "getAgent"],
    [
      "agent evaluation",
      <EvaluationPage />,
      "/ai-agents/:id/evaluation",
      "/ai-agents/not-a-uuid/evaluation",
      "getAgent",
    ],
    [
      "execution detail",
      <ExecutionDetailPage />,
      "/ai-agents/executions/:id",
      "/ai-agents/executions/not-a-uuid",
      "getExecution",
    ],
    [
      "schedule detail",
      <ScheduleDetailPage />,
      "/ai-agents/schedules/:id",
      "/ai-agents/schedules/not-a-uuid",
      "getSchedule",
    ],
    [
      "approval detail",
      <ApprovalDetailPage />,
      "/ai-agents/approvals/:id",
      "/ai-agents/approvals/not-a-uuid",
      "getApproval",
    ],
    [
      "tool detail",
      <ToolDetailPage />,
      "/ai-agents/tools/:id",
      "/ai-agents/tools/not-a-uuid",
      "getTool",
    ],
    [
      "tool edit",
      <ToolEditPage />,
      "/ai-agents/tools/:id/edit",
      "/ai-agents/tools/not-a-uuid/edit",
      "getTool",
    ],
    [
      "audit trail detail",
      <AuditTrailDetailPage />,
      "/ai-agents/audit/:id",
      "/ai-agents/audit/not-a-uuid",
      "getAuditTrail",
    ],
  ] as const)("renders record not found for invalid %s route IDs", async (_name, page, pattern, path, method) => {
    renderRoute(page, pattern, path);

    expect(await screen.findByText("Record not found")).toBeInTheDocument();
    expect(aiAgentService[method]).not.toHaveBeenCalled();
  });
});
