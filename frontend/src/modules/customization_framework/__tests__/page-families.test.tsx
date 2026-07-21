import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import { GovernedError } from "../components/CustomizationUI";
import { FieldDefinitionListPage } from "../pages/FieldDefinitionListPage";
import { FormListPage } from "../pages/FormListPage";
import { RuleExecutionListPage } from "../pages/RuleExecutionListPage";
import { RuleListPage } from "../pages/RuleListPage";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

vi.mock("../services/customization-framework-service", () => ({ customizationFrameworkService: { listFields: vi.fn(), listForms: vi.fn(), listRules: vi.fn(), listExecutions: vi.fn() } }));
const meta = { correlation_id: "00000000-0000-4000-8000-000000000099", timestamp: "2026-07-22T00:00:00Z", pagination: { count: 0, page: 1, page_size: 25, total_pages: 0, has_next: false, has_previous: false } } as const;
function renderPage(page: React.ReactElement, initial = "/") { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[initial]}>{page}</MemoryRouter></QueryClientProvider>); }

describe("customization page families", () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(service.listFields).mockResolvedValue({ data: [], meta }); vi.mocked(service.listForms).mockResolvedValue({ data: [], meta }); vi.mocked(service.listRules).mockResolvedValue({ data: [], meta }); vi.mocked(service.listExecutions).mockResolvedValue({ data: [], meta }); });

  it.each([
    ["fields", <FieldDefinitionListPage />, "No fields yet"],
    ["forms", <FormListPage />, "No forms yet"],
    ["rules", <RuleListPage />, "No rules yet"],
    ["executions", <RuleExecutionListPage />, "No executions yet"],
  ])("renders distinct empty state for %s", async (_name, page, heading) => { renderPage(page); expect(await screen.findByText(heading)).toBeInTheDocument(); });

  it("renders a distinct zero-results state from URL-backed server filters", async () => { renderPage(<FieldDefinitionListPage />, "/?search=missing"); expect(await screen.findByText("No fields match")).toBeInTheDocument(); expect(service.listFields).toHaveBeenCalledWith(expect.objectContaining({ search: "missing" })); });

  it("shows safe denied and capability-unavailable states with correlation IDs", () => { const { rerender } = render(<GovernedError error={new ApiError("hidden", 403, undefined, "permission_denied", "corr-denied")}/>); expect(screen.getByText("Access denied")).toBeInTheDocument(); expect(screen.getByText(/corr-denied/u)).toBeInTheDocument(); rerender(<GovernedError error={new ApiError("offline", 503, undefined, "capability_unavailable", "corr-down")}/>); expect(screen.getByText("Capability unavailable")).toBeInTheDocument(); expect(screen.getByText(/corr-down/u)).toBeInTheDocument(); });
});
