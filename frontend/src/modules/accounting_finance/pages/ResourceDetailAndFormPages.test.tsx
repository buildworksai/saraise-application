/* eslint-disable max-lines-per-function -- focused page coverage exercises stateful detail actions and form mutations. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type { APInvoice, ARInvoice, Account, JournalEntry, Payment } from "../contracts";
import { AccountingApiError, accountingService } from "../services/accounting-service";
import {
  APInvoiceDetailView,
  AccountDetailView,
  ARInvoiceDetailView,
  JournalEntryDetailView,
} from "./ResourceDetailPages";
import { AccountFormPage, InvoiceFormPage, PaymentFormPage } from "./ResourceFormPages";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock("../services/accounting-service", () => ({
  AccountingApiError: class AccountingApiError extends Error {
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
    }

    get kind() {
      if (this.status === 400 || this.code === "VALIDATION_ERROR") return "validation";
      if (this.status === 409) return "conflict";
      if (this.status === 404) return "not-found";
      return "unknown";
    }
  },
  accountingService: {
    approveAPInvoice: vi.fn(),
    cancelAPInvoice: vi.fn(),
    cancelARInvoice: vi.fn(),
    createAPInvoice: vi.fn(),
    createARInvoice: vi.fn(),
    createAccount: vi.fn(),
    createPayment: vi.fn(),
    deleteAPInvoice: vi.fn(),
    deleteARInvoice: vi.fn(),
    deleteAccount: vi.fn(),
    deleteJournalEntry: vi.fn(),
    getAPInvoice: vi.fn(),
    getARInvoice: vi.fn(),
    getAccount: vi.fn(),
    getJournalEntry: vi.fn(),
    getPayment: vi.fn(),
    postAPInvoice: vi.fn(),
    postARInvoice: vi.fn(),
    postJournalEntry: vi.fn(),
    rejectAPInvoice: vi.fn(),
    reverseJournalEntry: vi.fn(),
    submitAPInvoice: vi.fn(),
    updateAPInvoice: vi.fn(),
    updateARInvoice: vi.fn(),
    updateAccount: vi.fn(),
    updatePayment: vi.fn(),
  },
  createIdempotencyKey: vi.fn((scope: string) => `${scope}:test-key`),
}));

const service = vi.mocked(accountingService);

const ACCOUNT_ID = "11111111-1111-4111-8111-111111111111";
const ACCOUNT_2_ID = "22222222-2222-4222-8222-222222222222";
const PERIOD_ID = "33333333-3333-4333-8333-333333333333";
const JOURNAL_ID = "44444444-4444-4444-8444-444444444444";
const AP_INVOICE_ID = "55555555-5555-4555-8555-555555555555";
const AR_INVOICE_ID = "66666666-6666-4666-8666-666666666666";
const PAYMENT_ID = "77777777-7777-4777-8777-777777777777";
const SUPPLIER_ID = "88888888-8888-4888-8888-888888888888";
const CUSTOMER_ID = "99999999-9999-4999-8999-999999999999";

const account: Account = {
  id: ACCOUNT_ID,
  tenant_id: "tenant-1",
  version: 7,
  created_by: "operator-1",
  updated_by: "operator-2",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-02T00:00:00Z",
  code: "1000",
  name: "Operating Cash",
  account_type: "asset",
  normal_balance: "debit",
  parent: null,
  is_group: false,
  is_active: true,
  currency: "USD",
  allow_multi_currency: false,
  cash_flow_category: "operating",
  description: "Primary bank ledger",
  is_deleted: false,
  balance: "1500.25",
};

const journal: JournalEntry = {
  id: JOURNAL_ID,
  tenant_id: "tenant-1",
  version: 5,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-05T00:00:00Z",
  updated_at: "2026-07-06T00:00:00Z",
  entry_number: "JE-2026-0005",
  posting_date: "2026-07-15",
  posting_period: PERIOD_ID,
  reference: "REV-5",
  description: "Accrual reversal candidate",
  status: "posted",
  currency: "USD",
  debit_total: "500.00",
  credit_total: "500.00",
  posted_at: "2026-07-15T12:00:00Z",
  posted_by: "operator-1",
  reversed_at: null,
  reversed_by: null,
  reversed_entry: null,
  source_module: "manual",
  source_reference: "batch-5",
  transition_history: [],
  lines: [
    {
      id: "line-1",
      line_number: 1,
      account: ACCOUNT_ID,
      account_code: "1000",
      account_name: "Operating Cash",
      debit_amount: "500.00",
      credit_amount: "0.00",
      currency: "USD",
      exchange_rate: "1.00000000",
      base_debit_amount: "500.00",
      base_credit_amount: "0.00",
      description: "Cash",
      cost_center: "FIN",
      dimension_values: {},
    },
    {
      id: "line-2",
      line_number: 2,
      account: ACCOUNT_2_ID,
      account_code: "4000",
      account_name: "Revenue",
      debit_amount: "0.00",
      credit_amount: "500.00",
      currency: "USD",
      exchange_rate: "1.00000000",
      base_debit_amount: "0.00",
      base_credit_amount: "500.00",
      description: "Revenue",
      cost_center: "FIN",
      dimension_values: {},
    },
  ],
  is_deleted: false,
};

const invoiceLine = {
  id: "invoice-line-1",
  line_number: 1,
  description: "Implementation services",
  account: ACCOUNT_2_ID,
  account_code: "4000",
  quantity: "2.0000",
  unit_price: "125.00",
  tax_amount: "25.00",
  line_total: "275.00",
  cost_center: "FIN",
  dimension_values: {},
};

const apInvoice: APInvoice = {
  id: AP_INVOICE_ID,
  tenant_id: "tenant-1",
  version: 9,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-10T00:00:00Z",
  updated_at: "2026-07-11T00:00:00Z",
  invoice_number: "AP-2026-0009",
  supplier_id: SUPPLIER_ID,
  invoice_date: "2026-07-10",
  due_date: "2026-08-09",
  amount: "250.00",
  tax_amount: "25.00",
  total_amount: "275.00",
  paid_amount: "0.00",
  currency: "USD",
  exchange_rate: "1.00000000",
  description: "Supplier implementation",
  journal_entry: null,
  legacy_without_lines: false,
  transition_history: [],
  lines: [invoiceLine],
  is_deleted: false,
  status: "submitted",
  approved_at: null,
  approved_by: null,
  posted_at: null,
  posted_by: null,
  cancelled_at: null,
  cancelled_by: null,
};

const arInvoice: ARInvoice = {
  id: AR_INVOICE_ID,
  tenant_id: "tenant-1",
  version: 4,
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-12T00:00:00Z",
  updated_at: "2026-07-12T00:00:00Z",
  invoice_number: "AR-2026-0004",
  customer_id: CUSTOMER_ID,
  invoice_date: "2026-07-12",
  due_date: "2026-08-11",
  amount: "250.00",
  tax_amount: "25.00",
  total_amount: "275.00",
  paid_amount: "0.00",
  currency: "USD",
  exchange_rate: "1.00000000",
  description: "Customer implementation",
  journal_entry: JOURNAL_ID,
  legacy_without_lines: false,
  transition_history: [],
  lines: [invoiceLine],
  is_deleted: false,
  status: "draft",
  posted_at: null,
  posted_by: null,
  cancelled_at: null,
  cancelled_by: null,
};

const payment: Payment = {
  id: PAYMENT_ID,
  tenant_id: "tenant-1",
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
  created_by: "operator-1",
  payment_date: "2026-07-20",
  amount: "275.00",
  payment_method: "ach",
  currency: "USD",
  reference_number: "PAY-275",
  ap_invoice: null,
  ar_invoice: AR_INVOICE_ID,
  description: "Customer receipt",
  status: "recorded",
  voided_at: null,
  voided_by: null,
  void_reason: "",
  journal_entry: JOURNAL_ID,
  reversal_journal_entry: null,
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>;
}

function renderAccounting(route: string, element: ReactElement, path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={element} />
          <Route path="/accounting-finance/accounts" element={<LocationProbe />} />
          <Route path="/accounting-finance/accounts/:id" element={<LocationProbe />} />
          <Route path="/accounting-finance/ap-invoices/:id" element={<LocationProbe />} />
          <Route path="/accounting-finance/ar-invoices/:id" element={<LocationProbe />} />
          <Route path="/accounting-finance/payments/:id" element={<LocationProbe />} />
          <Route path="/accounting-finance/reports/general-ledger" element={<LocationProbe />} />
          <Route path="/accounting-finance/journal-entries" element={<LocationProbe />} />
          <Route path="/accounting-finance/journal-entries/:id" element={<LocationProbe />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function fillValidInvoice(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Invoice number"), "INV-NEW");
  await user.type(screen.getByLabelText("Supplier UUID"), SUPPLIER_ID);
  fireEvent.change(screen.getByLabelText("Invoice date"), { target: { value: "2026-07-01" } });
  fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-07-31" } });
  await user.clear(screen.getByLabelText("Line 1 description"));
  await user.type(screen.getByLabelText("Line 1 description"), "Implementation services");
  await user.clear(screen.getByLabelText("Line 1 account"));
  await user.type(screen.getByLabelText("Line 1 account"), ACCOUNT_2_ID);
  await user.clear(screen.getByLabelText("Line 1 unit price"));
  await user.type(screen.getByLabelText("Line 1 unit price"), "125.00");
  await user.clear(screen.getByLabelText("Line 1 tax"));
  await user.type(screen.getByLabelText("Line 1 tax"), "25.00");
}

describe("accounting resource detail pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.setSystemTime(new Date("2026-07-25T08:30:00Z"));
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
    service.getAccount.mockResolvedValue(account);
    service.deleteAccount.mockResolvedValue(undefined);
    service.getJournalEntry.mockResolvedValue(journal);
    service.reverseJournalEntry.mockResolvedValue({ ...journal, id: "reversal-journal" });
    service.deleteJournalEntry.mockResolvedValue(undefined);
    service.getAPInvoice.mockResolvedValue(apInvoice);
    service.approveAPInvoice.mockResolvedValue({ ...apInvoice, status: "approved" });
    service.getARInvoice.mockResolvedValue(arInvoice);
    service.postARInvoice.mockResolvedValue({ ...arInvoice, status: "posted" });
  });

  it("opens account ledger navigation and deletes only through the confirmation dialog", async () => {
    const user = userEvent.setup();
    const ledgerView = renderAccounting(
      `/accounting-finance/accounts/${ACCOUNT_ID}`,
      <AccountDetailView />,
      "/accounting-finance/accounts/:id"
    );

    expect(await screen.findByRole("heading", { name: "1000 · Operating Cash" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "View ledger" }));
    expect(screen.getAllByLabelText("Current route").at(-1)).toHaveTextContent(
      `/accounting-finance/reports/general-ledger?account_id=${ACCOUNT_ID}`
    );
    ledgerView.unmount();

    renderAccounting(
      `/accounting-finance/accounts/${ACCOUNT_ID}`,
      <AccountDetailView />,
      "/accounting-finance/accounts/:id"
    );
    expect(await screen.findByRole("heading", { name: "1000 · Operating Cash" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(service.deleteAccount).not.toHaveBeenCalled();
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(service.deleteAccount).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete account" }));
    await waitFor(() => expect(service.deleteAccount).toHaveBeenCalledWith(ACCOUNT_ID));
    expect(screen.getAllByLabelText("Current route").at(-1)).toHaveTextContent(
      "/accounting-finance/accounts"
    );
  });

  it("reverses posted journals with versioned idempotent payloads and today's posting date", async () => {
    const user = userEvent.setup();
    renderAccounting(
      `/accounting-finance/journal-entries/${JOURNAL_ID}`,
      <JournalEntryDetailView />,
      "/accounting-finance/journal-entries/:id"
    );

    expect(await screen.findByRole("heading", { name: "Journal JE-2026-0005" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reverse" }));
    await user.type(screen.getByLabelText("Reason"), "Accrual no longer valid");
    await user.click(screen.getByRole("button", { name: "Post reversal" }));

    await waitFor(() =>
      expect(service.reverseJournalEntry).toHaveBeenCalledWith(JOURNAL_ID, {
        transition_key: "journal.reverse:test-key",
        version: 5,
        reason: "Accrual no longer valid",
        posting_date: "2026-07-25",
      })
    );
    expect(screen.getAllByLabelText("Current route").at(-1)).toHaveTextContent(
      "/accounting-finance/journal-entries/reversal-journal"
    );
  });

  it("deletes only draft journals and returns to the journal list", async () => {
    const user = userEvent.setup();
    service.getJournalEntry.mockResolvedValueOnce({ ...journal, status: "draft" });
    renderAccounting(
      `/accounting-finance/journal-entries/${JOURNAL_ID}`,
      <JournalEntryDetailView />,
      "/accounting-finance/journal-entries/:id"
    );

    expect(await screen.findByRole("button", { name: "Delete draft" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Delete draft" }));
    await user.click(screen.getByRole("button", { name: "Delete draft" }));

    await waitFor(() => expect(service.deleteJournalEntry).toHaveBeenCalledWith(JOURNAL_ID));
    expect(service.postJournalEntry).not.toHaveBeenCalled();
    expect(screen.getAllByLabelText("Current route").at(-1)).toHaveTextContent(
      "/accounting-finance/journal-entries"
    );
  });

  it("approves submitted AP invoices with approval comments mirrored from the reason", async () => {
    const user = userEvent.setup();
    renderAccounting(
      `/accounting-finance/ap-invoices/${AP_INVOICE_ID}`,
      <APInvoiceDetailView />,
      "/accounting-finance/ap-invoices/:id"
    );

    expect(await screen.findByRole("heading", { name: "AP invoice AP-2026-0009" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Approve invoice" }));

    await waitFor(() =>
      expect(service.approveAPInvoice).toHaveBeenCalledWith(AP_INVOICE_ID, {
        transition_key: "ap.approve:test-key",
        version: 9,
        reason: "",
        comments: "",
      })
    );
  });

  it("posts draft AR invoices and blocks cancel without the required reason", async () => {
    const user = userEvent.setup();
    renderAccounting(
      `/accounting-finance/ar-invoices/${AR_INVOICE_ID}`,
      <ARInvoiceDetailView />,
      "/accounting-finance/ar-invoices/:id"
    );

    expect(await screen.findByRole("heading", { name: "AR invoice AR-2026-0004" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Cancel invoice" }));
    expect(service.cancelARInvoice).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("Reason"), "Customer order cancelled");
    await user.click(screen.getByRole("button", { name: "Cancel invoice" }));

    await waitFor(() =>
      expect(service.cancelARInvoice).toHaveBeenCalledWith(AR_INVOICE_ID, {
        transition_key: "ar.cancel:test-key",
        version: 4,
        reason: "Customer order cancelled",
      })
    );
  });
});

describe("accounting resource form pages", () => {
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
    service.getAccount.mockResolvedValue(account);
    service.updateAccount.mockResolvedValue(account);
    service.createAccount.mockResolvedValue({ ...account, id: ACCOUNT_2_ID, code: "1100" });
    service.getAPInvoice.mockResolvedValue(apInvoice);
    service.updateAPInvoice.mockResolvedValue(apInvoice);
    service.createAPInvoice.mockResolvedValue(apInvoice);
    service.getPayment.mockResolvedValue(payment);
    service.updatePayment.mockResolvedValue(payment);
    service.createPayment.mockResolvedValue(payment);
  });

  it("validates account input locally and sends update payloads with the fetched version", async () => {
    const user = userEvent.setup();
    renderAccounting(
      `/accounting-finance/accounts/${ACCOUNT_ID}/edit`,
      <AccountFormPage edit />,
      "/accounting-finance/accounts/:id/edit"
    );

    expect(await screen.findByDisplayValue("Operating Cash")).toBeVisible();
    await user.clear(screen.getByLabelText("Parent group UUID (optional)"));
    await user.type(screen.getByLabelText("Parent group UUID (optional)"), "not-a-uuid");
    await user.click(screen.getByRole("button", { name: "Save account" }));
    expect(service.updateAccount).not.toHaveBeenCalled();
    expect(await screen.findByText("Invalid uuid")).toBeVisible();

    await user.clear(screen.getByLabelText("Parent group UUID (optional)"));
    await user.type(screen.getByLabelText("Parent group UUID (optional)"), ACCOUNT_2_ID);
    await user.clear(screen.getByLabelText("Account name"));
    await user.type(screen.getByLabelText("Account name"), "Operating Bank");
    await user.click(screen.getByRole("button", { name: "Save account" }));

    await waitFor(() =>
      expect(service.updateAccount).toHaveBeenCalledWith(
        ACCOUNT_ID,
        expect.objectContaining({
          code: "1000",
          name: "Operating Bank",
          parent: ACCOUNT_2_ID,
          version: 7,
        })
      )
    );
  });

  it("maps server field errors on account creation without rendering a generic failure", async () => {
    const user = userEvent.setup();
    service.createAccount.mockRejectedValueOnce(
      new AccountingApiError("Validation failed", 400, "VALIDATION_ERROR", "corr-account", null, [
        { field: "code", code: "unique", message: "Account code already exists." },
      ])
    );
    renderAccounting(
      "/accounting-finance/accounts/new",
      <AccountFormPage />,
      "/accounting-finance/accounts/new"
    );

    await user.type(screen.getByLabelText("Account code"), "1000");
    await user.type(screen.getByLabelText("Account name"), "Duplicate Cash");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() =>
      expect(service.createAccount).toHaveBeenCalledWith(
        expect.objectContaining({ code: "1000", name: "Duplicate Cash" }),
        "account.create:test-key"
      )
    );
    expect(await screen.findByText("Account code already exists.")).toBeVisible();
    expect(screen.queryByText("Check the highlighted information")).not.toBeInTheDocument();
  });

  it("validates AP invoice dates and creates invoices with parsed line payloads", async () => {
    const user = userEvent.setup();
    renderAccounting(
      "/accounting-finance/ap-invoices/new",
      <InvoiceFormPage kind="ap" />,
      "/accounting-finance/ap-invoices/new"
    );

    await fillValidInvoice(user);
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-06-30" } });
    await user.click(screen.getByRole("button", { name: "Create invoice" }));
    expect(service.createAPInvoice).not.toHaveBeenCalled();
    expect(await screen.findByText("Due date must be on or after invoice date.")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-07-31" } });
    await user.click(screen.getByRole("button", { name: "Create invoice" }));
    await waitFor(() =>
      expect(service.createAPInvoice).toHaveBeenCalledWith(
        {
          invoice_number: "INV-NEW",
          supplier_id: SUPPLIER_ID,
          invoice_date: "2026-07-01",
          due_date: "2026-07-31",
          currency: "USD",
          exchange_rate: "1.00000000",
          description: "",
          lines: [
            {
              line_number: 1,
              description: "Implementation services",
              account: ACCOUNT_2_ID,
              quantity: "1.0000",
              unit_price: "125.00",
              tax_amount: "25.00",
              cost_center: "",
              dimension_values: {},
            },
          ],
          tax_provenance: undefined,
        },
        "ap-invoice.create:test-key"
      )
    );
  });

  it("updates AP invoices from fetched details with immutable version in the mutation body", async () => {
    const user = userEvent.setup();
    renderAccounting(
      `/accounting-finance/ap-invoices/${AP_INVOICE_ID}/edit`,
      <InvoiceFormPage kind="ap" edit />,
      "/accounting-finance/ap-invoices/:id/edit"
    );

    expect(await screen.findByDisplayValue("AP-2026-0009")).toBeVisible();
    await user.clear(screen.getByLabelText("Invoice number"));
    await user.type(screen.getByLabelText("Invoice number"), "AP-2026-0010");
    await user.click(screen.getByRole("button", { name: "Save invoice" }));

    await waitFor(() =>
      expect(service.updateAPInvoice).toHaveBeenCalledWith(
        AP_INVOICE_ID,
        expect.objectContaining({
          invoice_number: "AP-2026-0010",
          supplier_id: SUPPLIER_ID,
          version: 9,
          lines: [
            expect.objectContaining({
              line_number: 1,
              account: ACCOUNT_2_ID,
              description: "Implementation services",
            }),
          ],
        })
      )
    );
  });

  it("validates payment invoice selection and records a payment with one invoice target", async () => {
    const user = userEvent.setup();
    renderAccounting(
      "/accounting-finance/payments/new",
      <PaymentFormPage />,
      "/accounting-finance/payments/new"
    );

    await user.clear(screen.getByLabelText("Amount"));
    await user.type(screen.getByLabelText("Amount"), "275.00");
    await user.click(screen.getByRole("button", { name: "Record payment" }));
    expect(service.createPayment).not.toHaveBeenCalled();
    expect(await screen.findByText("Choose exactly one AP or AR invoice.")).toBeVisible();

    await user.type(screen.getByLabelText("AR invoice UUID"), AR_INVOICE_ID);
    await user.type(screen.getByLabelText("Reference number"), "PAY-NEW");
    await user.click(screen.getByRole("button", { name: "Record payment" }));

    await waitFor(() =>
      expect(service.createPayment).toHaveBeenCalledWith(
        expect.objectContaining({
          amount: "275.00",
          payment_method: "ach",
          currency: "USD",
          reference_number: "PAY-NEW",
          ap_invoice: null,
          ar_invoice: AR_INVOICE_ID,
        }),
        "payment.record:test-key"
      )
    );
  });

  it("updates only editable payment reference fields on correction pages", async () => {
    const user = userEvent.setup();
    renderAccounting(
      `/accounting-finance/payments/${PAYMENT_ID}/edit`,
      <PaymentFormPage edit />,
      "/accounting-finance/payments/:id/edit"
    );

    expect(await screen.findByDisplayValue("PAY-275")).toBeVisible();
    await user.clear(screen.getByLabelText("Reference number"));
    await user.type(screen.getByLabelText("Reference number"), "PAY-CORRECTED");
    await user.clear(screen.getByLabelText("Description"));
    await user.type(screen.getByLabelText("Description"), "Corrected remittance reference");
    await user.click(screen.getByRole("button", { name: "Save reference" }));

    await waitFor(() =>
      expect(service.updatePayment).toHaveBeenCalledWith(PAYMENT_ID, {
        reference_number: "PAY-CORRECTED",
        description: "Corrected remittance reference",
      })
    );
  });
});
