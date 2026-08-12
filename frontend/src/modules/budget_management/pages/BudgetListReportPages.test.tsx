/* eslint-disable max-lines-per-function, @typescript-eslint/no-unsafe-assignment -- page tests intentionally assert governed query and export payloads end-to-end. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BudgetListItem, PaginatedResult, VarianceReport } from "../contracts";
import { BudgetManagementApiError } from "../services/budget-service";
import { BudgetListPage } from "./BudgetListPage";
import { BudgetReportPage } from "./BudgetReportPage";

const service = vi.hoisted(() => ({
  listBudgets: vi.fn(),
  getVariance: vi.fn(),
}));

vi.mock("../services/budget-service", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  budgetService: service,
}));

const pagination = {
  page: 1,
  page_size: 25,
  count: 1,
  total_pages: 2,
  has_next: true,
  has_previous: false,
};

const budget: BudgetListItem = {
  id: "budget-1",
  budget_code: "FY27-OPS",
  budget_name: "Operations",
  fiscal_year: 2027,
  start_date: "2027-01-01",
  end_date: "2027-12-31",
  budget_type: "operating",
  department_id: null,
  project_id: null,
  status: "approved",
  currency: "USD",
  budget_ceiling: "1000.00",
  total_budget: "1000.00",
  variance: "-250.00",
  variance_percentage: "-25.00",
  updated_at: "2026-07-28T00:00:00Z",
};

const report: VarianceReport = {
  budget_id: "budget-1",
  currency: "USD",
  budgeted: "1000.00",
  committed: "150.00",
  actual: "1250.00",
  variance: "-250.00",
  variance_percentage: "-25.00",
  favorable: false,
  as_of: "2026-07-28T00:00:00Z",
  lines: [
    {
      budget_line_id: "line-1",
      account_code: "6100",
      account_name: "Cloud hosting",
      period_type: "monthly",
      period_number: 7,
      budgeted: "1000.00",
      committed: "150.00",
      actual: "1250.00",
      variance: "-250.00",
      variance_percentage: "-25.00",
      favorable: false,
      threshold_exceeded: true,
    },
  ],
};

function page<T>(
  items: readonly T[],
  overrides: Partial<typeof pagination> = {}
): PaginatedResult<T> {
  return {
    items,
    pagination: { ...pagination, count: items.length, ...overrides },
    correlationId: "corr-budget-page",
    receivedAt: "2026-07-28T00:00:00Z",
  };
}

function renderRoute(ui: React.ReactElement, path: string, entry = path) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path={path} element={ui} />
          <Route path="/budget-management/budgets/new" element={<LocationProbe />} />
          <Route path="/budget-management/budgets/:id" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

describe("Budget list and report pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    service.listBudgets.mockResolvedValue(page([budget]));
    service.getVariance.mockResolvedValue(report);
  });

  it("applies filters, pagination, ordering, and detail navigation through governed list queries", async () => {
    const user = userEvent.setup();
    renderRoute(<BudgetListPage />, "/budget-management/budgets");

    expect(await screen.findByRole("heading", { name: "Budgets" })).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Search budgets"));
    await user.type(screen.getByLabelText("Search budgets"), "ops");
    await user.click(screen.getByRole("button", { name: "Apply search" }));
    await user.type(screen.getByLabelText("Fiscal year"), "2027");
    await user.selectOptions(screen.getByLabelText("Budget type"), "operating");
    await user.selectOptions(screen.getByLabelText("Budget status"), "approved");
    await user.click(screen.getByRole("button", { name: "Toggle updated ordering" }));
    await user.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() =>
      expect(service.listBudgets).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page: 2,
          page_size: 25,
          search: "ops",
          fiscal_year: 2027,
          budget_type: "operating",
          status: "approved",
          ordering: "-updated_at",
        }),
        expect.any(AbortSignal)
      )
    );

    await user.click(screen.getByRole("button", { name: "FY27-OPS" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/budget-management/budgets/budget-1");
  });

  it("fails closed with correlation evidence and offers a create action for empty lists", async () => {
    const user = userEvent.setup();
    service.listBudgets
      .mockRejectedValueOnce(
        new BudgetManagementApiError("Budget service down", 503, "unavailable", "corr-budget-503")
      )
      .mockResolvedValueOnce(page([], { total_pages: 0, has_next: false }));
    renderRoute(<BudgetListPage />, "/budget-management/budgets");

    expect(await screen.findByRole("alert")).toHaveTextContent("Capability unavailable");
    expect(screen.getByText(/corr-budget-503/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "No budgets match" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create first budget" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/budget-management/budgets/new");
  });

  it("selects reportable budgets and exports the authorized variance rows as escaped CSV", async () => {
    const user = userEvent.setup();
    const createObjectUrl = vi.fn(() => "blob:budget");
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });
    const click = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(click);
    renderRoute(<BudgetReportPage />, "/budget-management/report");

    expect(
      await screen.findByRole("heading", { name: "Budget versus actual report" })
    ).toBeInTheDocument();
    expect(await screen.findByText(/Cloud hosting/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(createObjectUrl).toHaveBeenCalledWith(expect.any(Blob));
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:budget");
    await waitFor(() =>
      expect(service.getVariance).toHaveBeenCalledWith("budget-1", {}, expect.any(AbortSignal))
    );
  });

  it("renders report empty and variance failure states without fabricating rows", async () => {
    service.getVariance.mockRejectedValueOnce(
      new BudgetManagementApiError("Variance unavailable", 503, "unavailable", "corr-variance")
    );
    renderRoute(<BudgetReportPage />, "/budget-management/report");

    expect(await screen.findByRole("alert")).toHaveTextContent("Capability unavailable");
    expect(screen.getByText(/corr-variance/u)).toBeInTheDocument();

    service.listBudgets.mockResolvedValueOnce(page([], { total_pages: 0, has_next: false }));
    service.getVariance.mockResolvedValueOnce({ ...report, lines: [] });
    renderRoute(<BudgetReportPage />, "/budget-management/report");
    expect(
      await screen.findByRole("heading", { name: "No reportable budgets" })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create budget" })).toHaveAttribute(
      "href",
      "/budget-management/budgets/new"
    );
  });
});
