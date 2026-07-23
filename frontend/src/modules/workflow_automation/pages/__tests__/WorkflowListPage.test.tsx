/* eslint-disable @typescript-eslint/unbound-method -- Vitest spies intentionally reference service methods. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PaginatedResult, WorkflowListDTO } from "../../contracts";
import { WorkflowApiError, workflowService } from "../../services/workflow-service";
import { WorkflowListPage } from "../WorkflowListPage";

const workflow: WorkflowListDTO = { id: "workflow-1", key: "purchase_approval", version: 2, name: "Purchase approval", description: "Govern purchasing", workflow_type: "approval", trigger_type: "manual", trigger_config: {}, status: "published", step_count: 2, created_by_name: "Asha", published_at: "2026-07-22T00:00:00Z", created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-22T00:00:00Z", allowed_actions: ["view", "clone", "start"] };
function result(items: readonly WorkflowListDTO[]): PaginatedResult<WorkflowListDTO> { return { items, correlationId: "corr-list", receivedAt: "2026-07-22T00:00:00Z", pagination: { count: items.length, page: 1, page_size: 20, total_pages: items.length ? 1 : 0, has_next: false, has_previous: false } }; }
function renderPage() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter><WorkflowListPage/></MemoryRouter></QueryClientProvider>); }

describe("WorkflowListPage states", () => {
  afterEach(() => vi.restoreAllMocks());
  it("renders the accessible loading skeleton", () => { vi.spyOn(workflowService.workflows, "list").mockReturnValue(new Promise(() => undefined)); renderPage(); expect(screen.getByLabelText("Loading workflow definitions")).toHaveAttribute("aria-busy", "true"); });
  it("renders first-use and filtered-empty actions", async () => { vi.spyOn(workflowService.workflows, "list").mockResolvedValue(result([])); renderPage(); expect(await screen.findByText("Create your first governed workflow")).toBeInTheDocument(); await userEvent.type(screen.getByLabelText("Search workflows"), "missing"); expect(await screen.findByText("No workflows match these filters")).toBeInTheDocument(); });
  it("renders a governed correlation ID and retry", async () => { vi.spyOn(workflowService.workflows, "list").mockRejectedValue(new WorkflowApiError("Unavailable", 503, "handler_unavailable", "corr-handler", [], true)); renderPage(); expect(await screen.findByText(/corr-handler/u)).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument(); });
  it("renders successful rows and hides unauthorized lifecycle actions", async () => { vi.spyOn(workflowService.workflows, "list").mockResolvedValue(result([workflow])); renderPage(); expect(await screen.findByRole("button", { name: "Purchase approval" })).toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Edit Purchase approval" })).not.toBeInTheDocument(); expect(screen.getByRole("button", { name: "Clone Purchase approval" })).toBeInTheDocument(); });
});
