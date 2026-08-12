/* eslint-disable max-lines-per-function, @typescript-eslint/no-unsafe-assignment -- page integration cases keep React Query, routing, and service expectations together; asymmetric matcher payloads are intentionally inspected. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovalQueuePage } from "./ApprovalQueuePage";
import { BudgetDetailPage } from "./BudgetDetailPage";
import { EditBudgetPage } from "./EditBudgetPage";
import { AllocationEditPage } from "./AllocationEditPage";
import { VarianceDashboardPage } from "./VarianceDashboardPage";
import type {
  BudgetApproval,
  BudgetDetail,
  BudgetLine,
  BudgetListItem,
  PaginatedResult,
  VarianceAlert,
  VarianceReport,
} from "../contracts";

const service = vi.hoisted(() => ({
  getBudget: vi.fn(),
  deleteBudget: vi.fn(),
  rejectBudget: vi.fn(),
  listApprovals: vi.fn(),
  submitBudget: vi.fn(),
  approveBudget: vi.fn(),
  reviseBudget: vi.fn(),
  closeBudget: vi.fn(),
  updateBudget: vi.fn(),
  requestActualsSync: vi.fn(),
  checkAvailability: vi.fn(),
  replaceAllocations: vi.fn(),
  listBudgets: vi.fn(),
  getVariance: vi.fn(),
  listAlerts: vi.fn(),
  acknowledgeAlert: vi.fn(),
}));

vi.mock("../services/budget-service", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  budgetService: service,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderRoute(ui: React.ReactElement, path: string, entry = path) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path={path} element={ui} />
          <Route path="/budget-management/budgets" element={<LocationProbe />} />
          <Route path="/budget-management/budgets/:id" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname}</p>;
}

const pagination = {
  page: 1,
  page_size: 25,
  count: 1,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

function page<T>(items: readonly T[]): PaginatedResult<T> {
  return {
    items,
    pagination: { ...pagination, count: items.length },
    correlationId: "corr-budget-test",
    receivedAt: "2026-07-28T00:00:00Z",
  };
}

function line(overrides: Partial<BudgetLine> = {}): BudgetLine {
  return {
    id: "line-1",
    budget: "budget-1",
    account_id: null,
    account_code: "6100",
    account_name: "Cloud hosting",
    period_type: "annual",
    period_number: 1,
    budget_amount: "1000.00",
    committed_amount: "150.00",
    actual_amount: "300.00",
    variance: "550.00",
    actuals_as_of: "2026-07-28T00:00:00Z",
    source: "manual",
    created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z",
    ...overrides,
  };
}

function budget(overrides: Partial<BudgetDetail> = {}): BudgetDetail {
  return {
    id: "budget-1",
    budget_code: "FY27-OPS",
    budget_name: "Operations",
    fiscal_year: 2027,
    start_date: "2027-01-01",
    end_date: "2027-12-31",
    budget_type: "operating",
    department_id: null,
    project_id: null,
    status: "draft",
    currency: "USD",
    budget_ceiling: "1000.00",
    total_budget: "1000.00",
    updated_at: "2026-07-28T00:00:00Z",
    submitted_at: null,
    submitted_by: null,
    approved_at: null,
    approved_by: null,
    rejected_at: null,
    rejected_by: null,
    rejection_reason: "",
    created_at: "2026-07-28T00:00:00Z",
    created_by: "user-1",
    updated_by: "user-1",
    lines: [line()],
    approvals: [],
    transitions: [],
    variance_alerts: [],
    variance_summary: {
      budget_id: "budget-1",
      currency: "USD",
      budgeted: "1000.00",
      committed: "150.00",
      actual: "300.00",
      variance: "550.00",
      variance_percentage: "55.00",
      favorable: true,
      lines: [],
      as_of: "2026-07-28T00:00:00Z",
    },
    allowed_commands: ["update", "replace_allocations", "submit", "approve", "sync_actuals"],
    ...overrides,
  };
}

const listItem: BudgetListItem = {
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
  updated_at: "2026-07-28T00:00:00Z",
};

const variance: VarianceReport = {
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

const alert: VarianceAlert = {
  id: "alert-1",
  budget: "budget-1",
  budget_line: "line-1",
  alert_type: "over_budget",
  threshold_percentage: "90.00",
  variance_percentage: "-25.00",
  budget_amount: "1000.00",
  actual_amount: "1250.00",
  committed_amount: "150.00",
  alert_date: "2026-07-28",
  notification_status: "sent",
  notification_job_id: null,
  acknowledged_at: null,
  acknowledged_by: null,
  created_at: "2026-07-28T00:00:00Z",
};

const approval: BudgetApproval = {
  id: "approval-1",
  budget: "budget-1",
  approval_level: 1,
  approver_id: "approver-1",
  status: "pending",
  notes: "",
  rejection_reason: "",
  decision_at: null,
  workflow_request_id: null,
  created_at: "2026-07-28T00:00:00Z",
  created_by: "submitter-1",
  budget_code: "FY27-OPS",
  budget_name: "Operations",
  budget_total: "1000.00",
  currency: "USD",
  submitted_at: "2026-07-28T00:00:00Z",
  submitted_by: "submitter-1",
  self_approval_denied: false,
};

describe("Budget Management pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    service.getBudget.mockResolvedValue(budget());
    service.approveBudget.mockResolvedValue(budget({ status: "approved" }));
    service.checkAvailability.mockResolvedValue({
      account_code: "6100",
      budget_id: "budget-1",
      currency: "USD",
      allocated: "1000.00",
      committed: "150.00",
      actual: "300.00",
      available: "550.00",
      deficit: "0.00",
      sufficient: true,
      unbudgeted: false,
    });
    service.replaceAllocations.mockResolvedValue(budget());
    service.listBudgets.mockResolvedValue(page([listItem]));
    service.getVariance.mockResolvedValue(variance);
    service.listAlerts.mockResolvedValue(page([alert]));
    service.acknowledgeAlert.mockResolvedValue({
      ...alert,
      acknowledged_at: "2026-07-28T01:00:00Z",
    });
    service.listApprovals.mockResolvedValue(page([approval]));
    service.updateBudget.mockResolvedValue(budget({ budget_name: "Operations revised" }));
  });

  it("renders governed detail evidence, runs allowed lifecycle commands, and checks availability", async () => {
    const user = userEvent.setup();
    renderRoute(
      <BudgetDetailPage />,
      "/budget-management/budgets/:id",
      "/budget-management/budgets/budget-1"
    );

    expect(await screen.findByRole("heading", { name: /FY27-OPS/u })).toBeInTheDocument();
    expect(screen.getByText(/Cloud hosting/u)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(service.approveBudget).toHaveBeenCalledWith(
        "budget-1",
        expect.objectContaining({ idempotency_key: expect.stringMatching(/^approve:/u) })
      )
    );

    await user.clear(screen.getByLabelText("Account code"));
    await user.type(screen.getByLabelText("Account code"), "6100");
    await user.clear(screen.getByLabelText("Purchase amount"));
    await user.type(screen.getByLabelText("Purchase amount"), "125.50");
    fireEvent.change(screen.getByLabelText("Purchase period"), { target: { value: "2027-07-01" } });
    await user.click(screen.getByRole("button", { name: /Check/u }));

    await waitFor(() =>
      expect(service.checkAvailability).toHaveBeenCalledWith({
        account_code: "6100",
        amount: "125.50",
        period: "2027-07-01",
        budget_id: "budget-1",
      })
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Sufficient");
    expect(screen.getByRole("status")).toHaveTextContent("550.00");
  });

  it("executes remaining lifecycle commands, fail-closes rejection, and renders empty evidence", async () => {
    const user = userEvent.setup();
    const prompt = vi.spyOn(window, "prompt");
    prompt.mockReturnValueOnce("").mockReturnValueOnce("Funding no longer authorized");
    service.getBudget.mockResolvedValue(
      budget({
        allowed_commands: ["reject", "revise", "close", "sync_actuals"],
        budget_ceiling: null,
        lines: [],
        approvals: [],
        transitions: [],
        variance_alerts: [],
        variance_summary: null,
        submitted_at: "2026-07-28T02:00:00Z",
        approved_at: "2026-07-28T03:00:00Z",
      })
    );
    service.rejectBudget.mockResolvedValue(budget({ status: "rejected" }));
    service.reviseBudget.mockResolvedValue(budget({ status: "revision" }));
    service.closeBudget.mockResolvedValue(budget({ status: "closed" }));
    service.requestActualsSync.mockResolvedValue(budget());
    service.checkAvailability.mockResolvedValueOnce({
      account_code: "6100",
      budget_id: "budget-1",
      currency: "USD",
      allocated: "1000.00",
      committed: "900.00",
      actual: "200.00",
      available: "-100.00",
      deficit: "100.00",
      sufficient: false,
      unbudgeted: false,
    });
    renderRoute(
      <BudgetDetailPage />,
      "/budget-management/budgets/:id",
      "/budget-management/budgets/budget-1"
    );

    expect(await screen.findByText("No ceiling")).toBeInTheDocument();
    expect(screen.getByText("Not synchronized")).toBeInTheDocument();
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText("No allocations yet.")).toBeInTheDocument();
    expect(screen.getByText("No approval assignments have been created.")).toBeInTheDocument();
    expect(screen.getByText("No lifecycle transitions yet.")).toBeInTheDocument();
    expect(screen.getByText("No variance alerts for this budget.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(
      await screen.findByText("Rejection cancelled: a reason is required.")
    ).toBeInTheDocument();
    expect(service.rejectBudget).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() =>
      expect(service.rejectBudget).toHaveBeenCalledWith(
        "budget-1",
        expect.objectContaining({
          idempotency_key: expect.stringMatching(/^reject:/u),
          reason: "Funding no longer authorized",
        })
      )
    );
    await user.click(screen.getByRole("button", { name: "Revise" }));
    await waitFor(() =>
      expect(service.reviseBudget).toHaveBeenCalledWith(
        "budget-1",
        expect.objectContaining({ idempotency_key: expect.stringMatching(/^revise:/u) })
      )
    );
    await user.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() =>
      expect(service.closeBudget).toHaveBeenCalledWith(
        "budget-1",
        expect.objectContaining({ idempotency_key: expect.stringMatching(/^close:/u) })
      )
    );
    await user.click(screen.getByRole("button", { name: /Sync actuals/u }));
    await waitFor(() =>
      expect(service.requestActualsSync).toHaveBeenCalledWith(
        "budget-1",
        expect.objectContaining({ idempotency_key: expect.stringMatching(/^sync:/u) })
      )
    );

    await user.type(screen.getByLabelText("Account code"), "6100");
    await user.type(screen.getByLabelText("Purchase amount"), "1200");
    await user.click(screen.getByRole("button", { name: /Check/u }));
    expect(await screen.findByRole("status")).toHaveTextContent("Insufficient");
    expect(screen.getByRole("status")).toHaveTextContent("Deficit");
  });

  it("soft-deletes draft budgets and surfaces availability service failures", async () => {
    const user = userEvent.setup();
    service.getBudget.mockResolvedValue(
      budget({ allowed_commands: ["delete"], variance_summary: null })
    );
    service.checkAvailability.mockRejectedValueOnce(new Error("availability service down"));
    service.deleteBudget.mockResolvedValue(undefined);
    renderRoute(
      <BudgetDetailPage />,
      "/budget-management/budgets/:id",
      "/budget-management/budgets/budget-1"
    );

    expect(await screen.findByRole("heading", { name: /FY27-OPS/u })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Account code"), "6100");
    await user.type(screen.getByLabelText("Purchase amount"), "125");
    await user.click(screen.getByRole("button", { name: /Check/u }));
    await waitFor(() => expect(service.checkAvailability).toHaveBeenCalled());
    expect(await screen.findByText(/availability service down/u)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(service.deleteBudget).toHaveBeenCalledWith("budget-1", "2026-07-28T00:00:00Z")
    );
    expect(await screen.findByTestId("location")).toHaveTextContent("/budget-management/budgets");
  });

  it("blocks invalid allocation saves and sends reconciled matrix replacements", async () => {
    const user = userEvent.setup();
    service.getBudget.mockResolvedValueOnce(
      budget({ lines: [], budget_ceiling: "100.00", total_budget: "0.00" })
    );
    renderRoute(
      <AllocationEditPage />,
      "/budget-management/budgets/:id/allocations",
      "/budget-management/budgets/budget-1/allocations"
    );

    expect(await screen.findByRole("heading", { name: /Allocate FY27-OPS/u })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Account code row 1"), "ops");
    await user.type(screen.getByLabelText("OPS Annual"), "99.99");
    await user.click(screen.getByRole("button", { name: /Save allocations/u }));
    expect(service.replaceAllocations).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("OPS Annual"));
    await user.type(screen.getByLabelText("OPS Annual"), "100");
    await user.click(screen.getByRole("button", { name: /Save allocations/u }));

    await waitFor(() =>
      expect(service.replaceAllocations).toHaveBeenCalledWith("budget-1", {
        expected_updated_at: "2026-07-28T00:00:00Z",
        allocations: [
          {
            account_code: "OPS",
            period_type: "annual",
            period_number: 1,
            budget_amount: "100.00",
          },
        ],
      })
    );
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/budget-management/budgets/budget-1"
    );
  });

  it("honors read-only allocation states", async () => {
    service.getBudget.mockResolvedValueOnce(budget({ status: "approved", allowed_commands: [] }));
    renderRoute(
      <AllocationEditPage />,
      "/budget-management/budgets/:id/allocations",
      "/budget-management/budgets/budget-1/allocations"
    );

    expect(
      await screen.findByRole("heading", { name: "Allocations are read-only" })
    ).toBeInTheDocument();
    expect(
      screen.getByText("Only draft and revision budgets can replace planning allocations.")
    ).toBeInTheDocument();
  });

  it("protects allocation matrix scheme switches, paste imports, duplicate accounts, and save errors", async () => {
    const user = userEvent.setup();
    service.getBudget.mockResolvedValueOnce(
      budget({
        lines: [line({ account_code: "6100", period_type: "monthly", period_number: 1 })],
        budget_ceiling: "100.00",
        total_budget: "1000.00",
      })
    );
    service.replaceAllocations.mockRejectedValueOnce(new Error("allocation write rejected"));
    const confirm = vi.spyOn(window, "confirm");
    confirm.mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderRoute(
      <AllocationEditPage />,
      "/budget-management/budgets/:id/allocations",
      "/budget-management/budgets/budget-1/allocations"
    );

    expect(await screen.findByRole("heading", { name: /Allocate FY27-OPS/u })).toBeInTheDocument();
    expect(screen.getByLabelText("6100 M1")).toHaveValue("1000.00");
    fireEvent.change(screen.getByLabelText("Account code row 1"), {
      target: { value: "ops" },
    });
    await user.selectOptions(screen.getByLabelText("Period scheme"), "quarterly");
    expect(screen.getByLabelText("OPS M1")).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledWith(
      "Changing the period scheme clears unsaved matrix values. Continue?"
    );

    await user.selectOptions(screen.getByLabelText("Period scheme"), "annual");
    expect(screen.getByLabelText("Account code row 1")).toHaveValue("");
    await user.type(screen.getByLabelText("Account code row 1"), "ops");
    await user.type(screen.getByLabelText("OPS Annual"), "100");
    await user.click(screen.getByRole("button", { name: "Add account" }));
    await user.type(screen.getByLabelText("Account code row 2"), "ops");
    await user.type(screen.getAllByLabelText("OPS Annual")[1]!, "100");
    await user.click(screen.getByRole("button", { name: /Save allocations/u }));
    expect(service.replaceAllocations).not.toHaveBeenCalled();

    await user.click(screen.getAllByRole("button", { name: "Remove OPS" })[1]!);
    await user.click(screen.getByRole("button", { name: /Save allocations/u }));
    expect(await screen.findByText("allocation write rejected")).toBeInTheDocument();

    fireEvent.paste(screen.getByRole("main"), {
      clipboardData: { getData: () => "7000\t125.5\n7100\t74.5" },
    } as unknown as React.ClipboardEvent<HTMLElement>);
    expect(screen.getByLabelText("7000 Annual")).toHaveValue("125.50");
    expect(screen.getByLabelText("7100 Annual")).toHaveValue("74.50");
  });

  it("applies variance filters, switches to visual mode, and acknowledges alerts", async () => {
    const user = userEvent.setup();
    renderRoute(
      <VarianceDashboardPage />,
      "/budget-management/variance",
      "/budget-management/variance"
    );

    expect(await screen.findByRole("heading", { name: "Variance dashboard" })).toBeInTheDocument();
    expect(await screen.findByText(/Cloud hosting/u)).toBeInTheDocument();
    expect(screen.getByText(/threshold exceeded/u)).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Account code"));
    await user.type(screen.getByLabelText("Account code"), "6100");
    await user.selectOptions(screen.getByLabelText("Period type"), "monthly");
    await user.type(screen.getByLabelText("Period number"), "7");
    await user.selectOptions(screen.getByLabelText("Alert type"), "over_budget");

    await waitFor(() =>
      expect(service.getVariance).toHaveBeenLastCalledWith(
        "budget-1",
        { account_code: "6100", period_type: "monthly", period_number: 7 },
        expect.any(AbortSignal)
      )
    );
    await waitFor(() =>
      expect(service.listAlerts).toHaveBeenLastCalledWith(
        { budget_id: "budget-1", alert_type: "over_budget", page_size: 100 },
        expect.any(AbortSignal)
      )
    );

    await user.click(screen.getByRole("button", { name: /Visual/u }));
    expect(screen.getByRole("img", { name: /Budget versus actual/u })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Acknowledge" }));
    await waitFor(() => expect(service.acknowledgeAlert).toHaveBeenCalledWith("alert-1"));
  });

  it("keeps approval decisions fail-closed until prompts and confirmations are complete", async () => {
    const user = userEvent.setup();
    const prompt = vi.spyOn(window, "prompt");
    const confirm = vi.spyOn(window, "confirm");
    prompt.mockReturnValueOnce("LGTM").mockReturnValueOnce("").mockReturnValueOnce("Over ceiling");
    confirm.mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderRoute(<ApprovalQueuePage />, "/budget-management/approvals");

    expect(await screen.findByText(/FY27-OPS/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(service.approveBudget).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent("Approval cancelled.");

    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(service.rejectBudget).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Rejection cancelled: a reason is required."
    );

    await user.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() =>
      expect(service.rejectBudget).toHaveBeenCalledWith(
        "budget-1",
        expect.objectContaining({
          idempotency_key: expect.stringMatching(/^reject:/u),
          reason: "Over ceiling",
        })
      )
    );
  });

  it("disables self-approval actions and treats approved budgets as read-only in edit", async () => {
    service.listApprovals.mockResolvedValueOnce(
      page([{ ...approval, self_approval_denied: true }])
    );
    const first = renderRoute(<ApprovalQueuePage />, "/budget-management/approvals");

    expect(await screen.findByText(/cannot approve it/u)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    first.unmount();

    service.getBudget.mockResolvedValueOnce(budget({ status: "approved" }));
    const user = userEvent.setup();
    renderRoute(
      <EditBudgetPage />,
      "/budget-management/budgets/:id/edit",
      "/budget-management/budgets/budget-1/edit"
    );

    expect(await screen.findByRole("heading", { name: "Budget is read-only" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to budget" }));
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/budget-management/budgets/budget-1"
    );
  });
});
