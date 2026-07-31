/* eslint-disable max-lines, max-lines-per-function, @typescript-eslint/unbound-method -- Bank reconciliation has a wide governed UI surface; these tests keep each workflow state explicit. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type * as ReactRouter from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AcceptedImport,
  BankAccount,
  BankStatement,
  BankTransaction,
  MatchingRule,
  ReconciliationMatch,
  ReconciliationSummary,
  ReconciliationSession,
  ScoreFactors,
  StatementImport,
} from "../contracts";
import { bankReconciliationService } from "../services/bank-reconciliation-service";
import * as BankAccountDetailEntry from "./BankAccountDetailPage";
import * as BankAccountListEntry from "./BankAccountListPage";
import * as CreateBankAccountEntry from "./CreateBankAccountPage";
import * as CreateManualStatementEntry from "./CreateManualStatementPage";
import * as CreateMatchingRuleEntry from "./CreateMatchingRulePage";
import * as CreateReconciliationEntry from "./CreateReconciliationPage";
import * as EditBankAccountEntry from "./EditBankAccountPage";
import * as EditMatchingRuleEntry from "./EditMatchingRulePage";
import * as EditTransactionEntry from "./EditTransactionPage";
import * as ImportJobDetailEntry from "./ImportJobDetailPage";
import * as ImportJobListEntry from "./ImportJobListPage";
import * as ImportStatementEntry from "./ImportStatementPage";
import * as MatchingRuleDetailEntry from "./MatchingRuleDetailPage";
import * as MatchingRuleListEntry from "./MatchingRuleListPage";
import * as ReconciliationDetailEntry from "./ReconciliationDetailPage";
import * as ReconciliationListEntry from "./ReconciliationListPage";
import * as ReconciliationWorkspaceEntry from "./ReconciliationWorkspacePage";
import * as StatementDetailEntry from "./StatementDetailPage";
import * as StatementListEntry from "./StatementListPage";
import * as TransactionDetailEntry from "./TransactionDetailPage";
import {
  BankAccountDetailPage,
  BankAccountListPage,
  CreateMatchingRulePage,
  CreateReconciliationPage,
  EditBankAccountPage,
  EditMatchingRulePage,
  EditTransactionPage,
  CreateBankAccountPage,
  CreateManualStatementPage,
  ImportJobDetailPage,
  ImportJobListPage,
  ImportStatementPage,
  MatchingRuleDetailPage,
  MatchingRuleListPage,
  ReconciliationDetailPage,
  ReconciliationListPage,
  ReconciliationWorkspacePage,
  StatementDetailPage,
  StatementListPage,
  TransactionDetailPage,
} from "./_implementations";

const navigateSpy = vi.hoisted(() => vi.fn());
const toastSuccess = vi.hoisted(() => vi.fn());
const toastError = vi.hoisted(() => vi.fn());

vi.mock("react-router-dom", async (importOriginal) => {
  const actual: typeof ReactRouter = await importOriginal();
  return {
    ...actual,
    useNavigate: () => navigateSpy,
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: toastSuccess,
    error: toastError,
  },
}));

vi.mock("../services/bank-reconciliation-service", () => ({
  bankReconciliationService: {
    listBankAccounts: vi.fn(),
    getBankAccount: vi.fn(),
    createBankAccount: vi.fn(),
    updateBankAccount: vi.fn(),
    archiveBankAccount: vi.fn(),
    listStatements: vi.fn(),
    getStatement: vi.fn(),
    createManualStatement: vi.fn(),
    voidStatement: vi.fn(),
    listStatementTransactions: vi.fn(),
    listTransactions: vi.fn(),
    getTransaction: vi.fn(),
    updateManualTransaction: vi.fn(),
    excludeTransaction: vi.fn(),
    restoreTransaction: vi.fn(),
    requestImport: vi.fn(),
    listImports: vi.fn(),
    getImport: vi.fn(),
    retryImport: vi.fn(),
    cancelImport: vi.fn(),
    pollImport: vi.fn(),
    listRules: vi.fn(),
    getRule: vi.fn(),
    createRule: vi.fn(),
    updateRule: vi.fn(),
    deleteRule: vi.fn(),
    activateRule: vi.fn(),
    deactivateRule: vi.fn(),
    listReconciliations: vi.fn(),
    getReconciliation: vi.fn(),
    createReconciliation: vi.fn(),
    startReconciliation: vi.fn(),
    generateCandidates: vi.fn(),
    createManualMatch: vi.fn(),
    submitReview: vi.fn(),
    finalizeReconciliation: vi.fn(),
    voidReconciliation: vi.fn(),
    getMatch: vi.fn(),
    confirmMatch: vi.fn(),
    rejectMatch: vi.fn(),
    reverseMatch: vi.fn(),
    downloadReport: vi.fn(),
    health: vi.fn(),
  },
}));

const service = vi.mocked(bankReconciliationService);

const summary: ReconciliationSummary = {
  statement_balance: "125.0000",
  ledger_balance: "125.0000",
  matched_amount: "25.0000",
  unmatched_amount: "0.0000",
  difference: "0.0000",
  tolerance: "0.0000",
  proposed_count: 1,
  unmatched_count: 0,
  excluded_count: 0,
  guard_failures: [],
};

const scoreFactors: ScoreFactors = {
  amount: "1.0",
  reference: "1.0",
  date: "1.0",
  counterparty: "1.0",
};

const reconciliationMatch: ReconciliationMatch = {
  id: "match-1",
  reconciliation: "recon-1",
  match_type: "manual",
  status: "proposed",
  score: "0.9000",
  rule: null,
  explanation: scoreFactors,
  matched_at: null,
  lines: [
    {
      id: "line-1",
      side: "bank",
      bank_transaction: "tx-1",
      ledger_entry_id: null,
      ledger_entry_type: "other",
      allocated_amount: "25.0000",
      currency: "USD",
    },
  ],
  reversal_reason: "",
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
};

function collection<T>(items: T[], overrides = {}) {
  return {
    items,
    correlationId: "corr-bank",
    pagination: {
      page: 1,
      page_size: 25,
      total_pages: 1,
      count: items.length,
      has_next: false,
      has_previous: false,
    },
    ...overrides,
  };
}

const account: BankAccount = {
  id: "account-1",
  masked_account_number: "",
  account_number_last4: "4387",
  bank_name: "Civic Bank",
  account_name: "Operating cash",
  account_type: "checking",
  currency: "USD",
  bank_identifier: "CIVICUS33",
  ledger_account_id: "ledger-account-1",
  opening_balance: "100.0000",
  opening_balance_date: "2026-01-01",
  is_active: true,
  archived_at: null,
  last_statement_date: "2026-07-01",
  statement_count: 3,
  reconciliation_count: 1,
  unreconciled_count: 4,
  active_session_count: 0,
  allowed_actions: ["read", "archive"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

const statement: BankStatement = {
  id: "statement-1",
  bank_account: "account-1",
  account,
  statement_import: {
    id: "import-1",
    status: "succeeded",
    file_format: "csv",
    source_filename: "july.csv",
    rows_received: 2,
    rows_imported: 2,
    rows_rejected: 0,
  },
  statement_reference: "JULY-2026",
  period_start: "2026-07-01",
  period_end: "2026-07-31",
  statement_date: "2026-07-31",
  opening_balance: "100.0000",
  closing_balance: "125.0000",
  transaction_total: "25.0000",
  calculated_closing_balance: "125.0000",
  balance_variance: "0.0000",
  status: "imported",
  is_reconciled: false,
  reconciled_at: null,
  transaction_count: 1,
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
};

const transaction: BankTransaction = {
  id: "tx-1",
  bank_statement: "statement-1",
  sequence_number: 1,
  external_id: "ext-1",
  transaction_date: "2026-07-15",
  value_date: null,
  description: "Customer payment",
  amount: "25.0000",
  transaction_type: "credit",
  running_balance: "125.0000",
  reference_number: "REF-25",
  counterparty_name: "Customer LLC",
  counterparty_account_masked: "****9281",
  match_status: "unmatched",
  is_reconciled: false,
  matched_payment_id: null,
  source_data: { raw_reference: "REF-25", nullable: null },
  source: "manual",
  match_history: [
    {
      id: "history-1",
      status: "proposed",
      match_type: "manual",
      allocated_amount: "25.0000",
      created_at: "2026-07-15T00:00:00Z",
    },
  ],
  created_at: "2026-07-15T00:00:00Z",
  updated_at: "2026-07-15T00:00:00Z",
};

const reconciliation: ReconciliationSession = {
  id: "recon-1",
  bank_account: "account-1",
  bank_statement: "statement-1",
  reconciliation_date: "2026-07-31",
  ledger_balance: "125.0000",
  statement_balance: "125.0000",
  matched_amount: "25.0000",
  unmatched_amount: "0.0000",
  difference: "0.0000",
  tolerance: "0.0000",
  status: "in_progress",
  notes: "Month end",
  reviewed_by_id: null,
  finalized_at: null,
  finalized_by_id: null,
  reviewed_at: null,
  match_count: 1,
  allowed_actions: ["read", "review", "finalize", "export"],
  summary,
  matches: [reconciliationMatch],
  transition_history: [
    {
      command: "start",
      from: "draft",
      to: "in_progress",
      reason: "",
      actor_id: "user-1",
      occurred_at: "2026-07-31T00:00:00Z",
    },
  ],
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
};

const rule: MatchingRule = {
  id: "rule-1",
  name: "Exact reference",
  description: "Reference and amount must agree",
  rule_type: "exact",
  priority: 10,
  configuration: { "reference.require_reference": true },
  auto_confirm: true,
  minimum_score: "1.0000",
  extension_key: "",
  is_active: true,
  usage_count: 0,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

const importJob: StatementImport = {
  id: "import-1",
  bank_account: "account-1",
  source: "file",
  file_format: "csv",
  source_document_id: null,
  source_filename: "july.csv",
  content_sha256: "hash",
  mapping: { date: "date" },
  status: "failed",
  idempotency_key: "idem-import",
  rows_received: 10,
  rows_imported: 7,
  rows_rejected: 3,
  error_code: "BAD_DATE",
  error_detail: { row: "3" },
  async_job: {
    id: "job-1",
    status: "failed",
    task_name: "parse",
    attempts: 1,
    created_at: "2026-07-31T00:00:00Z",
    updated_at: "2026-07-31T00:00:00Z",
  },
  statement_id: null,
  correlation_id: "corr-import",
  started_at: "2026-07-31T00:00:00Z",
  completed_at: "2026-07-31T00:01:00Z",
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:01:00Z",
};

function renderPage(path: string, element: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route
              path={path.includes(":") ? path : path.replace(/\/[^/]+$/u, "/:id")}
              element={element}
            />
            <Route path="*" element={element} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    ),
  };
}

function renderAt(routePattern: string, entry: string, element: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path={routePattern} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("bank reconciliation governed pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      "confirm",
      vi.fn(() => true)
    );
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "idem-test") });
    service.health.mockResolvedValue({
      status: "degraded",
      components: { ledger_gateway: "unavailable", import_worker: "available" },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    navigateSpy.mockClear();
  });

  it("keeps route-facing page entrypoints wired to their governed implementations", () => {
    expect(BankAccountDetailEntry.BankAccountDetailPage).toBe(BankAccountDetailPage);
    expect(BankAccountListEntry.BankAccountListPage).toBe(BankAccountListPage);
    expect(CreateBankAccountEntry.CreateBankAccountPage).toBe(CreateBankAccountPage);
    expect(CreateManualStatementEntry.CreateManualStatementPage).toBe(CreateManualStatementPage);
    expect(CreateMatchingRuleEntry.CreateMatchingRulePage).toBe(CreateMatchingRulePage);
    expect(CreateReconciliationEntry.CreateReconciliationPage).toBe(CreateReconciliationPage);
    expect(EditBankAccountEntry.EditBankAccountPage).toBe(EditBankAccountPage);
    expect(EditMatchingRuleEntry.EditMatchingRulePage).toBe(EditMatchingRulePage);
    expect(EditTransactionEntry.EditTransactionPage).toBe(EditTransactionPage);
    expect(ImportJobDetailEntry.ImportJobDetailPage).toBe(ImportJobDetailPage);
    expect(ImportJobListEntry.ImportJobListPage).toBe(ImportJobListPage);
    expect(ImportStatementEntry.ImportStatementPage).toBe(ImportStatementPage);
    expect(MatchingRuleDetailEntry.MatchingRuleDetailPage).toBe(MatchingRuleDetailPage);
    expect(MatchingRuleListEntry.MatchingRuleListPage).toBe(MatchingRuleListPage);
    expect(ReconciliationDetailEntry.ReconciliationDetailPage).toBe(ReconciliationDetailPage);
    expect(ReconciliationListEntry.ReconciliationListPage).toBe(ReconciliationListPage);
    expect(ReconciliationWorkspaceEntry.ReconciliationWorkspacePage).toBe(
      ReconciliationWorkspacePage
    );
    expect(StatementDetailEntry.StatementDetailPage).toBe(StatementDetailPage);
    expect(StatementListEntry.StatementListPage).toBe(StatementListPage);
    expect(TransactionDetailEntry.TransactionDetailPage).toBe(TransactionDetailPage);
  });

  it("renders account search/filter/pagination and archives through the governed service", async () => {
    service.listBankAccounts.mockResolvedValue(
      collection([account], {
        pagination: {
          page: 1,
          page_size: 25,
          total_pages: 2,
          count: 26,
          has_next: true,
          has_previous: false,
        },
      })
    );
    service.archiveBankAccount.mockResolvedValue(undefined);

    renderPage("/bank-reconciliation/accounts", <BankAccountListPage />);

    expect(await screen.findByText("Operating cash")).toBeInTheDocument();
    expect(screen.getByText(/4387/u)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search bank, account, or last four"), {
      target: { value: "cash" },
    });
    expect(await screen.findByText("Operating cash")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Account type"), "checking");
    expect(await screen.findByText("Operating cash")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Account status"), "true");
    expect(await screen.findByText("Operating cash")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /next/i }));
    fireEvent.click(await screen.findByRole("button", { name: /archive/i }));

    await waitFor(() => expect(service.archiveBankAccount).toHaveBeenCalledWith("account-1"));
    expect(service.listBankAccounts).toHaveBeenLastCalledWith(
      expect.objectContaining({ search: "cash", account_type: "checking", is_active: true })
    );
  });

  it("validates bank account creation before submitting and shows disconnected ledger fallback", async () => {
    service.createBankAccount.mockResolvedValue(account);
    renderPage("/bank-reconciliation/accounts/new", <CreateBankAccountPage />);

    expect(await screen.findByText("Accounting integration disconnected")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Currency"));
    await userEvent.type(screen.getByLabelText("Currency"), "usd");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findAllByRole("alert")).toHaveLength(3);
    expect(service.createBankAccount).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("Account number"), "000-111");
    await userEvent.type(screen.getByLabelText("Account display name"), "Payroll");
    await userEvent.type(screen.getByLabelText("Bank name"), "Civic Bank");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(service.createBankAccount).toHaveBeenCalledWith(
        expect.objectContaining({ account_number: "000-111", currency: "USD" })
      )
    );
    expect(navigateSpy).toHaveBeenCalledWith("/bank-reconciliation/accounts/account-1");
  });

  it("renders statement filters, balance proof, import diagnostics, and void guard", async () => {
    service.listStatements.mockResolvedValue(
      collection([{ ...statement, balance_variance: "5.0000" }])
    );
    service.getStatement.mockResolvedValue({ ...statement, balance_variance: "5.0000" });
    service.listStatementTransactions.mockResolvedValue(collection([transaction]));
    service.voidStatement.mockResolvedValue({ ...statement, status: "void" });

    renderPage("/bank-reconciliation/statements", <StatementListPage />);
    expect(await screen.findByText("JULY-2026")).toBeInTheDocument();
    expect(screen.getByText("Variance 5.0000")).toHaveClass("text-destructive");
    await userEvent.selectOptions(screen.getByLabelText("Statement status"), "imported");
    fireEvent.click(screen.getByLabelText("Has variance"));
    expect(service.listStatements).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "imported", has_variance: true })
    );

    renderAt("/statements/:id", "/statements/statement-1", <StatementDetailPage />);
    expect(await screen.findByText("Balance proof failed.")).toBeInTheDocument();
    expect(screen.getByText("Customer payment")).toBeInTheDocument();
    expect(screen.getByText("july.csv")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Void statement" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Void reason"), "Duplicate file");
    await userEvent.click(screen.getByRole("button", { name: "Void statement" }));
    await waitFor(() =>
      expect(service.voidStatement).toHaveBeenCalledWith("statement-1", {
        reason: "Duplicate file",
        idempotency_key: "idem-test",
      })
    );
  });

  it("calculates manual statement variance and submits transaction rows atomically", async () => {
    service.createManualStatement.mockResolvedValue(statement);
    renderPage("/bank-reconciliation/statements/manual", <CreateManualStatementPage />);

    await userEvent.type(screen.getByLabelText("Bank account ID"), "account-1");
    await userEvent.type(screen.getByLabelText("Statement reference"), "MAN-1");
    await userEvent.type(screen.getByLabelText("Period start"), "2026-07-01");
    await userEvent.type(screen.getByLabelText("Period end"), "2026-07-31");
    await userEvent.clear(screen.getByLabelText("Opening balance"));
    await userEvent.type(screen.getByLabelText("Opening balance"), "100.0000");
    await userEvent.clear(screen.getByLabelText("Closing balance"));
    await userEvent.type(screen.getByLabelText("Closing balance"), "125.0000");
    await userEvent.type(screen.getByLabelText("Transaction 1 date"), "2026-07-15");
    await userEvent.type(screen.getByLabelText("Transaction 1 description"), "Customer payment");
    await userEvent.clear(screen.getByLabelText("Transaction 1 amount"));
    await userEvent.type(screen.getByLabelText("Transaction 1 amount"), "25.0000");

    expect(screen.getByText("Calculated close").closest("div")).toHaveTextContent("125.0000");
    expect(screen.getByText("Variance").closest("div")).toHaveTextContent("0.0000");
    await userEvent.click(screen.getByRole("button", { name: "Create statement" }));

    await waitFor(() =>
      expect(service.createManualStatement).toHaveBeenCalledWith(
        expect.objectContaining({
          bank_account: "account-1",
          statement_reference: "MAN-1",
          transactions: [expect.objectContaining({ amount: "25.0000" })],
        })
      )
    );
  });

  it("detects upload format, maps CSV columns, and sends multipart import request metadata", async () => {
    const accepted: AcceptedImport = {
      import: { ...importJob, id: "import-accepted", status: "pending", error_code: "" },
      job: {
        id: "job-accepted",
        status: "queued",
        task_name: "parse",
        attempts: 0,
        created_at: "2026-07-31T00:00:00Z",
        updated_at: "2026-07-31T00:00:00Z",
      },
    };
    service.requestImport.mockResolvedValue(accepted);
    renderPage("/bank-reconciliation/statements/import", <ImportStatementPage />);

    await userEvent.type(screen.getByLabelText("Bank account ID"), "account-1");
    const fileInput = document.querySelector<HTMLInputElement>("#statement-file");
    expect(fileInput).not.toBeNull();
    await userEvent.upload(
      fileInput!,
      new File(["date,amount"], "july.ofx", { type: "application/ofx" })
    );
    expect(screen.getByLabelText("Detected format")).toHaveValue("ofx");
    await userEvent.selectOptions(screen.getByLabelText("Detected format"), "csv");
    await userEvent.clear(screen.getByLabelText("Date"));
    await userEvent.type(screen.getByLabelText("Date"), "posted_on");
    await userEvent.click(screen.getByRole("button", { name: "Request import" }));

    await waitFor(() => expect(service.requestImport).toHaveBeenCalledTimes(1));
    expect(service.requestImport.mock.calls[0]?.[0]).toMatchObject({
      bank_account: "account-1",
      file_format: "csv",
      idempotency_key: "idem-test",
    });
    expect(service.requestImport.mock.calls[0]?.[0].mapping).toMatchObject({ date: "posted_on" });
    expect(navigateSpy).toHaveBeenCalledWith("/bank-reconciliation/imports/import-accepted");
  });

  it("handles transaction exclusion and restore without allowing blank audit reasons", async () => {
    service.getTransaction.mockResolvedValue(transaction);
    service.excludeTransaction.mockResolvedValue({ ...transaction, match_status: "excluded" });
    renderAt("/transactions/:id", "/transactions/tx-1", <TransactionDetailPage />);

    expect(await screen.findByText("Normalized source fields")).toBeInTheDocument();
    expect(screen.queryByText("No proposals or confirmed matches.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exclude transaction" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Exclusion reason"), "Out of scope");
    await userEvent.click(screen.getByRole("button", { name: "Exclude transaction" }));
    await waitFor(() =>
      expect(service.excludeTransaction).toHaveBeenCalledWith("tx-1", { reason: "Out of scope" })
    );

    service.getTransaction.mockResolvedValue({ ...transaction, match_status: "excluded" });
    service.restoreTransaction.mockResolvedValue(transaction);
    renderAt("/transactions/:id", "/transactions/tx-1", <TransactionDetailPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Restore to unmatched" }));
    await waitFor(() => expect(service.restoreTransaction).toHaveBeenCalledWith("tx-1"));
  });

  it("groups reconciliation transactions and blocks certification when guards fail", async () => {
    service.getReconciliation.mockResolvedValue({
      ...reconciliation,
      summary: { ...summary, guard_failures: ["Unmatched transactions remain"] },
      matches: [
        {
          ...reconciliationMatch,
          explanation: { ...scoreFactors, date: "0.8" },
        },
      ],
    });
    service.getBankAccount.mockResolvedValue(account);
    service.listStatementTransactions.mockResolvedValue(
      collection([
        transaction,
        {
          ...transaction,
          id: "tx-2",
          description: "Fee",
          amount: "-5.0000",
          match_status: "unmatched",
        },
      ])
    );
    service.createManualMatch.mockResolvedValue(reconciliationMatch);

    renderAt(
      "/reconciliations/:id/workspace",
      "/reconciliations/recon-1/workspace",
      <ReconciliationWorkspacePage />
    );

    expect(await screen.findByText("Certification blocked")).toBeInTheDocument();
    expect(screen.getByText("Unmatched transactions remain")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit review" })).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/Customer payment/u));
    await userEvent.click(screen.getByLabelText(/Fee/u));
    await userEvent.type(screen.getByLabelText(/Ledger entry UUID/u), "ledger-entry-1");
    expect(screen.getByLabelText(/Bank total/u)).toHaveValue("20.0000");
    await userEvent.click(screen.getByRole("button", { name: "Create allocation" }));

    await waitFor(() => expect(service.createManualMatch).toHaveBeenCalledTimes(1));
    expect(service.createManualMatch.mock.calls[0]?.[0]).toBe("recon-1");
    expect(service.createManualMatch.mock.calls[0]?.[1].match_type).toBe("many_to_one");
    expect(service.createManualMatch.mock.calls[0]?.[1].lines).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ side: "ledger", allocated_amount: "20.0000" }),
      ])
    );
  });

  it("renders reconciliation evidence and exports certified CSV without mutating history", async () => {
    const createObjectURL = vi.fn(() => "blob:reconciliation");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    service.getReconciliation.mockResolvedValue({ ...reconciliation, status: "finalized" });
    service.downloadReport.mockResolvedValue(new Blob(["csv"]));
    renderAt("/reconciliations/:id", "/reconciliations/recon-1", <ReconciliationDetailPage />);

    expect(await screen.findByText("Transition history")).toBeInTheDocument();
    expect(screen.getByText(/start: draft/u)).toBeInTheDocument();
    expect(screen.getByText(/1 allocation lines/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(service.downloadReport).toHaveBeenCalledWith("recon-1", "csv"));
    expect(createObjectURL).toHaveBeenCalled();
    expect(anchorClick).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:reconciliation");
  });

  it("renders list pages for reconciliations, matching rules, and import jobs with governed actions", async () => {
    service.listReconciliations.mockResolvedValue(collection([reconciliation]));
    service.listRules.mockResolvedValue(collection([rule]));
    service.deactivateRule.mockResolvedValue({ ...rule, is_active: false });
    service.listImports.mockResolvedValue(collection([importJob]));

    renderPage("/bank-reconciliation/reconciliations", <ReconciliationListPage />);
    expect(await screen.findByText("2026-07-31")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Reconciliation status"), "in_progress");
    fireEvent.click(screen.getByLabelText("Non-zero difference"));
    expect(service.listReconciliations).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "in_progress", has_difference: true })
    );

    renderPage("/bank-reconciliation/rules", <MatchingRuleListPage />);
    expect(await screen.findByText("Exact reference")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(service.deactivateRule).toHaveBeenCalledWith("rule-1"));

    renderPage("/bank-reconciliation/imports", <ImportJobListPage />);
    expect(await screen.findByText("july.csv")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Import status"), "failed");
    await userEvent.selectOptions(screen.getByLabelText("File format"), "csv");
    expect(service.listImports).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "failed", file_format: "csv" })
    );
  });

  it("renders matching rule details and import retry/cancel/success diagnostics", async () => {
    service.getRule.mockResolvedValue(rule);
    service.deleteRule.mockResolvedValue(undefined);
    service.getImport.mockResolvedValue(importJob);
    service.retryImport.mockResolvedValue({
      import: { ...importJob, id: "retry-1", status: "pending", error_code: "" },
      job: {
        id: "job-retry",
        status: "queued",
        task_name: "parse",
        attempts: 0,
        created_at: "2026-07-31T00:00:00Z",
        updated_at: "2026-07-31T00:00:00Z",
      },
    });

    renderAt("/rules/:id", "/rules/rule-1", <MatchingRuleDetailPage />);
    expect(await screen.findByText("Reference and amount must agree")).toBeInTheDocument();
    expect(screen.getByText(/require_reference/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete unused rule" }));
    await waitFor(() => expect(service.deleteRule).toHaveBeenCalledWith("rule-1"));

    renderAt("/imports/:id", "/imports/import-1", <ImportJobDetailPage />);
    expect(await screen.findByText("Sanitized diagnostics")).toBeInTheDocument();
    expect(screen.getByText("BAD_DATE")).toBeInTheDocument();
    expect(screen.getByText("Correlation ID: corr-import")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(service.retryImport).toHaveBeenCalledWith("import-1", {
        idempotency_key: "idem-test",
      })
    );
  });

  it("renders accessible empty and permission states instead of silent blanks", async () => {
    service.listBankAccounts.mockResolvedValue(collection([]));
    renderPage("/bank-reconciliation/accounts", <BankAccountListPage />);
    expect(await screen.findByText("No bank accounts found")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create bank account" }));
    expect(navigateSpy).toHaveBeenCalledWith("/bank-reconciliation/accounts/new");

    service.listBankAccounts.mockRejectedValue(
      Object.assign(new Error("Denied"), { status: 403, correlationId: "corr-denied" })
    );
    renderPage("/bank-reconciliation/accounts", <BankAccountListPage />);
    expect(await screen.findByText("This information could not be loaded.")).toBeInTheDocument();
  });
});
