/* eslint-disable @typescript-eslint/unbound-method -- Vitest spies intentionally reference service methods. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type { DefinitionListDTO, PageResult } from "../../contracts";
import { automationOrchestrationService as service } from "../../services/automation-orchestration-service";
import { DefinitionsListPage } from "../DefinitionsListPage";

const definition: DefinitionListDTO = {
  id: "00000000-0000-4000-8000-000000000001",
  tenant_id: "00000000-0000-4000-8000-000000000002",
  key: "daily-close",
  version: 2,
  name: "Daily close",
  description: "Close ledgers",
  status: "published",
  is_current: true,
  graph_revision: 4,
  node_count: 5,
  schedule_count: 2,
  last_run_at: "2026-07-21T00:00:00Z",
  success_rate: 0.98,
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

function page(items: readonly DefinitionListDTO[]): PageResult<DefinitionListDTO> {
  return {
    items,
    correlationId: "corr-test",
    receivedAt: "2026-07-21T00:00:00Z",
    pagination: {
      count: items.length,
      page: 1,
      page_size: 25,
      total_pages: items.length ? 1 : 0,
      has_next: false,
      has_previous: false,
    },
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><DefinitionsListPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DefinitionsListPage states", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders an accessible skeleton while loading", () => {
    vi.spyOn(service, "listDefinitions").mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByLabelText("Loading orchestration data")).toHaveAttribute("aria-busy", "true");
  });

  it("renders the true empty state with a creation action", async () => {
    vi.spyOn(service, "listDefinitions").mockResolvedValue(page([]));
    renderPage();
    expect(await screen.findByText("Build your first reliable automation")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create orchestration" })).toHaveLength(2);
  });

  it("distinguishes a filtered empty result", async () => {
    vi.spyOn(service, "listDefinitions").mockResolvedValue(page([]));
    renderPage();
    await userEvent.type(await screen.findByLabelText("Search definitions"), "missing");
    expect(await screen.findByText("No definitions match")).toBeInTheDocument();
  });

  it("renders permission denial without exposing actions", async () => {
    vi.spyOn(service, "listDefinitions").mockRejectedValue(new ApiError("Denied", 403));
    renderPage();
    expect(await screen.findByText("Permission required")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create orchestration" })).not.toBeInTheDocument();
  });

  it("renders operational summary data on success", async () => {
    vi.spyOn(service, "listDefinitions").mockResolvedValue(page([definition]));
    renderPage();
    expect(await screen.findByRole("link", { name: "Daily close" })).toBeInTheDocument();
    expect(screen.getByText("98%")).toBeInTheDocument();
    expect(screen.getByText("current")).toBeInTheDocument();
  });
});
