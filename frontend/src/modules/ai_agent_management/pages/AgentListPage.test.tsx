/* eslint-disable max-lines-per-function -- focused page behavior tests intentionally keep the shared render setup and mutation assertions together. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AgentListItem, PageResult } from "../contracts";
import { aiAgentService } from "../services/ai-agent-service";
import { AgentListPage } from "./AgentListPage";

vi.mock("../services/ai-agent-service");

const pagination = {
  count: 0,
  page: 1,
  page_size: 25,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};
const page = (
  items: readonly AgentListItem[],
  overrides: Partial<PageResult<AgentListItem>["pagination"]> = {}
): PageResult<AgentListItem> => ({
  items,
  pagination: { ...pagination, ...overrides, count: overrides.count ?? items.length },
  correlationId: "correlation-1",
  receivedAt: "2026-07-23T00:00:00Z",
});
const agent: AgentListItem = {
  id: "agent-1",
  name: "Close books",
  description: "Reconciles ledgers",
  identity_type: "system_bound" as const,
  runner_key: "finance_runner",
  provider_config_id: null,
  status: "draft" as const,
  updated_at: "2026-07-23T00:00:00Z",
  created_at: "2026-07-23T00:00:00Z",
};
const agentWithoutDescription: AgentListItem = {
  ...agent,
  id: "agent-2",
  name: "Post accruals",
  description: "",
  provider_config_id: "provider-1",
  status: "active",
  identity_type: "user_bound",
  runner_key: "close_runner",
};
const configuration = {
  id: "configuration-1",
  environment: "production",
  version: 1,
  document: {
    ui: {
      agent_page_size: 25,
      status_tokens: {
        success: "status-success",
        info: "status-info",
        warning: "status-warning",
        danger: "status-danger",
        neutral: "status-neutral",
      },
      status_token_by_state: { draft: "neutral" },
    },
  },
  created_at: "2026-07-23T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
} as unknown as Awaited<ReturnType<typeof aiAgentService.getConfiguration>>;

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="current-path">{location.pathname}</span>;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AgentListPage />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { client, ...view };
}

describe("AgentListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiAgentService.getConfiguration).mockResolvedValue(configuration);
  });

  it("renders a skeleton while loading", () => {
    vi.mocked(aiAgentService.listAgents).mockImplementation(() => new Promise(() => undefined));
    renderPage();
    expect(screen.getByLabelText("Loading AI agent data")).toHaveAttribute("aria-busy", "true");
  });

  it("renders governed agent rows and sends server-side filters", async () => {
    vi.mocked(aiAgentService.listAgents).mockResolvedValue(page([agent]));
    const { client } = renderPage();
    expect(await screen.findByText("Close books")).toBeInTheDocument();
    expect(screen.getByText("Not required")).toBeInTheDocument();
    expect(
      client
        .getQueryCache()
        .getAll()
        .some((query) => query.queryKey[0] === "ai-agents")
    ).toBe(true);
    expect(aiAgentService.listAgents).toHaveBeenLastCalledWith(
      expect.objectContaining({ ordering: "-updated_at", page: 1, page_size: 25 })
    );
    await userEvent.type(screen.getByLabelText("Search agents"), "ledger");
    await waitFor(() =>
      expect(aiAgentService.listAgents).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "ledger", page: 1, page_size: 25 })
      )
    );
  });

  it("applies every governed filter and sort control to the server request", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.listAgents).mockResolvedValue(page([]));
    renderPage();
    await screen.findByText("Create your first governed agent");

    expect(
      Array.from(screen.getByLabelText("Filter status").querySelectorAll("option")).map(
        (option) => option.value
      )
    ).toEqual(["", "draft", "active", "disabled", "retired"]);

    await user.selectOptions(screen.getByLabelText("Filter status"), "active");
    await user.selectOptions(screen.getByLabelText("Filter identity"), "user_bound");
    await user.type(screen.getByLabelText("Filter runner"), "close_runner");
    await user.selectOptions(screen.getByLabelText("Sort agents"), "name");

    await waitFor(() =>
      expect(aiAgentService.listAgents).toHaveBeenLastCalledWith(
        expect.objectContaining({
          identity_type: "user_bound",
          ordering: "name",
          page: 1,
          runner_key: "close_runner",
          status: "active",
        })
      )
    );
  });

  it("renders filtered empty state and clears filter parameters", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.listAgents).mockResolvedValue(page([]));
    renderPage();

    await user.type(await screen.findByLabelText("Search agents"), "ledger");
    expect(await screen.findByText("No agents match")).toBeInTheDocument();
    expect(
      screen.getByText("Clear or adjust filters to inspect the tenant catalog.")
    ).toBeInTheDocument();

    const clearFilters = screen.getByRole("button", { name: "Clear filters" });
    expect(clearFilters).toHaveClass("border");
    await user.click(clearFilters);

    await waitFor(() =>
      expect(aiAgentService.listAgents).toHaveBeenLastCalledWith(
        expect.objectContaining({
          identity_type: undefined,
          runner_key: undefined,
          search: undefined,
          status: undefined,
        })
      )
    );
  });

  it("renders onboarding when the catalog is empty", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.listAgents).mockResolvedValue(page([]));
    renderPage();
    expect(await screen.findByText("Create your first governed agent")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Define an identity, runner, provider, tools, approvals, and budget before the first execution."
      )
    ).toBeInTheDocument();
    const createButtons = screen.getAllByRole("button", { name: "Create agent" });
    expect(createButtons).toHaveLength(2);
    const onboardingCreateButton = createButtons[1];
    if (!onboardingCreateButton) throw new Error("Expected onboarding create button.");
    expect(onboardingCreateButton).toHaveClass("bg-primary");
    const headerCreateButton = createButtons[0];
    if (!headerCreateButton) throw new Error("Expected header create button.");

    await user.click(headerCreateButton);
    expect(screen.getByTestId("current-path")).toHaveTextContent("/ai-agents/create");
  });

  it("renders provider, fallback description, identity text, row selection, and pagination", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.listAgents).mockResolvedValue(
      page([agentWithoutDescription], {
        count: 26,
        has_next: true,
        page: 1,
        total_pages: 2,
      })
    );
    renderPage();

    expect(await screen.findByText("Post accruals")).toBeInTheDocument();
    expect(screen.getByText("No description")).toBeInTheDocument();
    expect(screen.getByText("Configured")).toBeInTheDocument();
    expect(screen.getByText("user bound")).toBeInTheDocument();
    expect(screen.getByLabelText("Select Post accruals")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2 · 26 records")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(aiAgentService.listAgents).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 })
      )
    );
  });

  it("renders a retryable error", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.listAgents).mockRejectedValue(new Error("dependency failed"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("dependency failed");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(aiAgentService.listAgents).toHaveBeenCalledTimes(2));
  });

  it("renders a retryable configuration error", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.getConfiguration).mockRejectedValue(new Error("configuration failed"));
    vi.mocked(aiAgentService.listAgents).mockResolvedValue(page([agent]));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("configuration failed");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(aiAgentService.getConfiguration).toHaveBeenCalledTimes(2));
  });

  it("fails closed when the agent query returns no governed response", async () => {
    const user = userEvent.setup();
    vi.mocked(aiAgentService.listAgents).mockResolvedValue(undefined as never);
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No governed agent response was received."
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(aiAgentService.listAgents).toHaveBeenCalledTimes(2));
  });
});
