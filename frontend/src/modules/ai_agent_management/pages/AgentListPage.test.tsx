import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { aiAgentService } from "../services/ai-agent-service";
import { AgentListPage } from "./AgentListPage";

vi.mock("../services/ai-agent-service");

const pagination = { count: 0, page: 1, page_size: 25, total_pages: 0, has_next: false, has_previous: false };
const page = (items: readonly [{ readonly id: string; readonly name: string; readonly description: string; readonly identity_type: "system_bound"; readonly runner_key: string; readonly provider_config_id: null; readonly status: "draft"; readonly updated_at: string; readonly created_at: string }] | readonly []) => ({ items, pagination: { ...pagination, count: items.length }, correlationId: "correlation-1", receivedAt: "2026-07-23T00:00:00Z" });
const agent = { id: "agent-1", name: "Close books", description: "Reconciles ledgers", identity_type: "system_bound" as const, runner_key: "finance_runner", provider_config_id: null, status: "draft" as const, updated_at: "2026-07-23T00:00:00Z", created_at: "2026-07-23T00:00:00Z" };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><AgentListPage/></MemoryRouter></QueryClientProvider>);
}

describe("AgentListPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a skeleton while loading", () => {
    vi.mocked(aiAgentService.listAgents).mockImplementation(() => new Promise(() => undefined));
    renderPage();
    expect(screen.getByLabelText("Loading AI agent data")).toHaveAttribute("aria-busy", "true");
  });

  it("renders governed agent rows and sends server-side filters", async () => {
    vi.mocked(aiAgentService.listAgents).mockResolvedValue(page([agent]));
    renderPage();
    expect(await screen.findByText("Close books")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search agents"), "ledger");
    await waitFor(() => expect(aiAgentService.listAgents).toHaveBeenLastCalledWith(expect.objectContaining({ search: "ledger", page: 1, page_size: 25 })));
  });

  it("renders onboarding when the catalog is empty", async () => {
    vi.mocked(aiAgentService.listAgents).mockResolvedValue(page([]));
    renderPage();
    expect(await screen.findByText("Create your first governed agent")).toBeInTheDocument();
  });

  it("renders a retryable error", async () => {
    vi.mocked(aiAgentService.listAgents).mockRejectedValue(new Error("dependency failed"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("dependency failed");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
