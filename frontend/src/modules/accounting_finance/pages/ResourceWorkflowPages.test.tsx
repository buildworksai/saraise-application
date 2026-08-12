/* eslint-disable max-lines-per-function -- accounting resource workflows require stateful form and lifecycle assertions. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type { Account, JournalEntry, Payment, PostingPeriod } from "../contracts";
import { AccountingApiError, accountingService } from "../services/accounting-service";
import {
  AccountListView,
  JournalEntryListView,
  PaymentListView,
  PostingPeriodListView,
} from "./ResourceListPages";
import { PaymentDetailView, PostingPeriodDetailView } from "./ResourceDetailPages";
import {
  AccountFormPage,
  JournalEntryFormPage,
  PaymentFormPage,
  PostingPeriodFormPage,
} from "./ResourceFormPages";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock("../services/accounting-service", () => ({
  AccountingApiError: class AccountingApiError extends Error {
    readonly kind: string;
    constructor(
      message: string,
      readonly status: number,
      readonly code: string,
      readonly correlationId: string | null,
      readonly detail: string | null,
      readonly fieldErrors: readonly { field: string; code: string; message: string }[] = []
    ) {
      super(message);
      this.name = "AccountingApiError";
      this.kind = status === 400 ? "validation" : "unknown";
    }
  },
  accountingService: {
    closePostingPeriod: vi.fn(),
    accountHierarchy: vi.fn(),
    createAccount: vi.fn(),
    createPostingPeriod: vi.fn(),
    createJournalEntry: vi.fn(),
    getPayment: vi.fn(),
    getPostingPeriod: vi.fn(),
    listAccounts: vi.fn(),
    listJournalEntries: vi.fn(),
    listPayments: vi.fn(),
    listPostingPeriods: vi.fn(),
    lockPostingPeriod: vi.fn(),
    reopenPostingPeriod: vi.fn(),
    updatePostingPeriod: vi.fn(),
    updatePayment: vi.fn(),
    voidPayment: vi.fn(),
  },
  createIdempotencyKey: vi.fn((scope: string) => `${scope}:test-key`),
}));

const service = vi.mocked(accountingService);

const pagination = {
  page: 1,
  page_size: 20,
  total_pages: 2,
  count: 21,
  has_next: true,
  has_previous: false,
};

const period: PostingPeriod = {
  id: "period-1",
  tenant_id: "tenant-1",
  version: 4,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-02T00:00:00Z",
  period_name: "FY2026-07",
  start_date: "2026-07-01",
  end_date: "2026-07-31",
  fiscal_year: 2026,
  status: "open",
  closed_at: null,
  closed_by: null,
  locked_at: null,
  locked_by: null,
  transition_history: [
    {
      command: "open",
      from_status: "draft",
      to_status: "open",
      actor_id: "operator-1",
      occurred_at: "2026-07-01T00:00:00Z",
      reason: "Month opened",
    },
  ],
};

const account: Account = {
  id: "account-1",
  tenant_id: "tenant-1",
  version: 2,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-02T00:00:00Z",
  code: "1000",
  name: "Cash",
  account_type: "asset",
  normal_balance: "debit",
  parent: null,
  is_group: false,
  is_active: true,
  currency: "USD",
  allow_multi_currency: false,
  cash_flow_category: "operating",
  description: "Operating cash account",
  is_deleted: false,
  balance: "2500.00",
};

const journal: JournalEntry = {
  id: "journal-1",
  tenant_id: "tenant-1",
  version: 3,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-02T00:00:00Z",
  entry_number: "JE-2026-0001",
  posting_date: "2026-07-15",
  posting_period: period.id,
  reference: "REV-1",
  description: "Monthly revenue accrual",
  status: "draft",
  currency: "USD",
  debit_total: "1250.00",
  credit_total: "1250.00",
  posted_at: null,
  posted_by: null,
  reversed_at: null,
  reversed_by: null,
  reversed_entry: null,
  source_module: "manual",
  source_reference: "batch-1",
  transition_history: [],
  lines: [
    {
      id: "line-1",
      line_number: 1,
      account: "account-1",
      account_code: "4000",
      account_name: "Revenue",
      debit_amount: "0.00",
      credit_amount: "1250.00",
      currency: "USD",
      exchange_rate: "1.0000",
      base_debit_amount: "0.00",
      base_credit_amount: "1250.00",
      description: "Accrual",
      cost_center: "FIN",
      dimension_values: {},
    },
  ],
  is_deleted: false,
};

const payment: Payment = {
  id: "payment-1",
  tenant_id: "tenant-1",
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
  created_by: "operator-1",
  payment_date: "2026-07-20",
  amount: "500.00",
  payment_method: "wire_transfer",
  currency: "USD",
  reference_number: "PAY-500",
  ap_invoice: null,
  ar_invoice: "ar-1",
  description: "Customer receipt",
  status: "recorded",
  voided_at: null,
  voided_by: null,
  void_reason: "",
  journal_entry: "journal-1",
  reversal_journal_entry: null,
};

function page<T>(results: readonly T[]) {
  return {
    results,
    pagination,
    meta: { correlation_id: "corr-accounting", timestamp: "2026-07-23T00:00:00Z" },
  };
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{location.pathname}</output>;
}

function renderAccounting(initial: string, element: React.ReactNode, path = initial) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <LocationProbe />
        <Routes>
          <Route path={path} element={element} />
          <Route path="/accounting-finance/accounts/:id" element={<LocationProbe />} />
          <Route path="/accounting-finance/periods/:id" element={<LocationProbe />} />
          <Route path="/accounting-finance/periods" element={<LocationProbe />} />
          <Route path="/accounting-finance/payments/:id" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("accounting resource workflow pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: {
        id: "operator-1",
        email: "operator@saraise.com",
        username: "operator",
        is_staff: false,
        is_superuser: false,
        tenant_id: "tenant-1",
        platform_role: null,
        tenant_role: "tenant_admin",
      },
      isAuthenticated: true,
      isLoading: false,
    });
    service.listAccounts.mockResolvedValue(page([account]));
    service.accountHierarchy.mockResolvedValue([{ ...account, children: [] }]);
    service.createAccount.mockResolvedValue(account);
    service.createJournalEntry.mockResolvedValue(journal);
    service.listPostingPeriods.mockResolvedValue(page([period]));
    service.listJournalEntries.mockResolvedValue(page([journal]));
    service.listPayments.mockResolvedValue(page([payment]));
    service.getPostingPeriod.mockResolvedValue(period);
    service.closePostingPeriod.mockResolvedValue({ ...period, status: "closed" });
    service.reopenPostingPeriod.mockResolvedValue(period);
    service.lockPostingPeriod.mockResolvedValue({ ...period, status: "locked" });
    service.createPostingPeriod.mockResolvedValue(period);
    service.updatePostingPeriod.mockResolvedValue(period);
    service.updatePayment.mockResolvedValue(payment);
    service.getPayment.mockResolvedValue(payment);
    service.voidPayment.mockResolvedValue({
      ...payment,
      status: "voided",
      void_reason: "Duplicate receipt",
    });
  });

  it("searches and paginates posting periods, journal entries, and payments through their service queries", async () => {
    const user = userEvent.setup();
    const periods = renderAccounting("/accounting-finance/periods", <PostingPeriodListView />);
    expect(await screen.findByText("FY2026-07")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Search Posting periods"), "FY2026");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(service.listPostingPeriods).toHaveBeenLastCalledWith({
        page: 1,
        search: "FY2026",
        ordering: "-start_date",
      })
    );
    periods.unmount();

    const journals = renderAccounting(
      "/accounting-finance/journal-entries",
      <JournalEntryListView />
    );
    expect(await screen.findByText("JE-2026-0001")).toBeInTheDocument();
    expect(screen.getByText("Monthly revenue accrual")).toBeInTheDocument();
    expect(service.listJournalEntries).toHaveBeenCalledWith({
      page: 1,
      search: "",
      ordering: "-posting_date",
    });
    journals.unmount();

    renderAccounting("/accounting-finance/payments", <PaymentListView />);
    expect(await screen.findByText("PAY-500")).toBeInTheDocument();
    expect(screen.getByText("wire transfer")).toBeInTheDocument();
    expect(service.listPayments).toHaveBeenCalledWith({
      page: 1,
      search: "",
      ordering: "-payment_date",
    });
  });

  it("renders resource list empty and error states without fabricating accounting rows", async () => {
    service.listPostingPeriods.mockResolvedValueOnce(page([]));
    const emptyPeriods = renderAccounting("/accounting-finance/periods", <PostingPeriodListView />);
    expect(await screen.findByText("No posting periods found")).toBeInTheDocument();
    expect(
      screen.getByText("Create the first new period when you have permission.")
    ).toBeInTheDocument();
    emptyPeriods.unmount();

    service.listPayments.mockRejectedValueOnce(
      new AccountingApiError("Ledger unavailable", 503, "DEPENDENCY_DOWN", "corr-ledger", null)
    );
    renderAccounting("/accounting-finance/payments", <PaymentListView />);
    expect(await screen.findByText("Ledger unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-ledger/iu)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("switches account resources from table to governed hierarchy view", async () => {
    const user = userEvent.setup();
    renderAccounting("/accounting-finance/accounts", <AccountListView />);

    expect(await screen.findByText("Cash")).toBeInTheDocument();
    expect(service.listAccounts).toHaveBeenCalledWith({ page: 1, search: "", ordering: "code" });
    await user.click(screen.getByRole("button", { name: "Tree view" }));

    expect(await screen.findByRole("tree", { name: "Account hierarchy" })).toBeInTheDocument();
    expect(screen.getByRole("treeitem", { name: /1000 · Cash/iu })).toHaveAttribute(
      "aria-level",
      "1"
    );
    expect(service.accountHierarchy).toHaveBeenCalledWith(true);
  });

  it("closes an open posting period only after a reasoned action dialog confirmation", async () => {
    const user = userEvent.setup();
    renderAccounting(
      "/accounting-finance/periods/period-1",
      <PostingPeriodDetailView />,
      "/accounting-finance/periods/:id"
    );

    expect(await screen.findByRole("heading", { name: "FY2026-07" })).toBeInTheDocument();
    expect(screen.getByText("Month opened")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close period" }));
    await user.type(screen.getByLabelText("Reason"), "All journals reconciled");
    await user.click(screen.getByRole("button", { name: "Close period" }));

    await waitFor(() =>
      expect(service.closePostingPeriod).toHaveBeenCalledWith("period-1", {
        transition_key: "period.close:test-key",
        version: 4,
        reason: "All journals reconciled",
      })
    );
  });

  it("validates posting-period forms and maps server field errors without saving invalid input", async () => {
    const user = userEvent.setup();
    service.createPostingPeriod.mockRejectedValueOnce(
      new AccountingApiError(
        "Validation failed",
        400,
        "VALIDATION_ERROR",
        "corr-validation",
        null,
        [{ field: "period_name", code: "unique", message: "Period already exists." }]
      )
    );
    renderAccounting(
      "/accounting-finance/periods/new",
      <PostingPeriodFormPage />,
      "/accounting-finance/periods/new"
    );

    await user.type(screen.getByLabelText("Period name"), "FY2026-07");
    fireEvent.change(screen.getByLabelText("Fiscal year"), { target: { value: "2026" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-07-31" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-07-01" } });
    await user.click(screen.getByRole("button", { name: "Create period" }));
    expect(service.createPostingPeriod).not.toHaveBeenCalled();
    expect(await screen.findByText("End date must be on or after start date.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-07-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-07-31" } });
    await user.click(screen.getByRole("button", { name: "Create period" }));

    await waitFor(() =>
      expect(service.createPostingPeriod).toHaveBeenCalledWith(
        {
          period_name: "FY2026-07",
          fiscal_year: 2026,
          start_date: "2026-07-01",
          end_date: "2026-07-31",
        },
        "period.create:test-key"
      )
    );
    expect(await screen.findByText("Period already exists.")).toBeInTheDocument();
  });

  it("validates account and journal resource forms before governed create calls", async () => {
    const user = userEvent.setup();
    const accountForm = renderAccounting(
      "/accounting-finance/accounts/new",
      <AccountFormPage />,
      "/accounting-finance/accounts/new"
    );

    await screen.findByRole("button", { name: "Create account" });
    const accountCode = screen.getByLabelText("Account code");
    const accountFormElement = accountCode.closest("form");
    if (!accountFormElement) throw new Error("Account form was not rendered.");
    fireEvent.submit(accountFormElement);
    expect(await screen.findAllByText("String must contain at least 1 character(s)")).toHaveLength(
      2
    );
    expect(service.createAccount).not.toHaveBeenCalled();
    await user.type(accountCode, "6100");
    await user.type(screen.getByLabelText("Account name"), "Implementation expense");
    await user.selectOptions(screen.getByLabelText("Account type"), "expense");
    await user.selectOptions(screen.getByLabelText("Normal balance"), "debit");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() =>
      expect(service.createAccount).toHaveBeenCalledWith(
        expect.objectContaining({
          code: "6100",
          name: "Implementation expense",
          account_type: "expense",
          normal_balance: "debit",
          currency: "USD",
        }),
        "account.create:test-key"
      )
    );
    accountForm.unmount();

    renderAccounting(
      "/accounting-finance/journal-entries/new",
      <JournalEntryFormPage />,
      "/accounting-finance/journal-entries/new"
    );
    await user.type(await screen.findByLabelText("Entry number"), "JE-2026-0002");
    fireEvent.change(screen.getByLabelText("Posting date"), { target: { value: "2026-07-25" } });
    await user.type(
      screen.getByLabelText("Posting period UUID"),
      "00000000-0000-4000-8000-000000000001"
    );
    await user.type(
      screen.getByLabelText("Line 1 account"),
      "00000000-0000-4000-8000-000000000002"
    );
    await user.clear(screen.getByLabelText("Line 1 debit"));
    await user.type(screen.getByLabelText("Line 1 debit"), "100.00");
    await user.type(
      screen.getByLabelText("Line 2 account"),
      "00000000-0000-4000-8000-000000000003"
    );
    await user.clear(screen.getByLabelText("Line 2 credit"));
    await user.type(screen.getByLabelText("Line 2 credit"), "90.00");
    await user.click(screen.getByRole("button", { name: "Create draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Debits and credits must balance exactly."
    );
    expect(service.createJournalEntry).not.toHaveBeenCalled();
  });

  it("edits only mutable payment reference fields from the payment form page", async () => {
    const user = userEvent.setup();
    renderAccounting(
      "/accounting-finance/payments/payment-1/edit",
      <PaymentFormPage edit />,
      "/accounting-finance/payments/:id/edit"
    );

    const reference = await screen.findByLabelText("Reference number");
    await user.clear(reference);
    await user.type(reference, "PAY-501");
    await user.clear(screen.getByLabelText("Description"));
    await user.type(screen.getByLabelText("Description"), "Corrected bank trace");
    await user.click(screen.getByRole("button", { name: "Save reference" }));

    await waitFor(() =>
      expect(service.updatePayment).toHaveBeenCalledWith("payment-1", {
        reference_number: "PAY-501",
        description: "Corrected bank trace",
      })
    );
  });

  it("voids a posted payment with an audited reason and keeps reversal evidence visible", async () => {
    const user = userEvent.setup();
    renderAccounting(
      "/accounting-finance/payments/payment-1",
      <PaymentDetailView />,
      "/accounting-finance/payments/:id"
    );

    expect(await screen.findByRole("heading", { name: "Payment PAY-500" })).toBeInTheDocument();
    expect(screen.getByText("journal-1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Void payment" }));
    await user.type(screen.getByLabelText("Reason"), "Duplicate receipt");
    await user.click(screen.getByRole("button", { name: "Void and reverse" }));

    await waitFor(() =>
      expect(service.voidPayment).toHaveBeenCalledWith("payment-1", {
        transition_key: "payment.void:test-key",
        reason: "Duplicate receipt",
      })
    );
  });
});
