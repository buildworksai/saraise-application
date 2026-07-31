/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- table-driven service contract tests cover the accounting API surface. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import { ENDPOINTS, type ApiEnvelope, type ApiListEnvelope } from "../contracts";
import {
  AccountingApiError,
  accountingService,
  createIdempotencyKey,
  shouldPollJob,
} from "./accounting-service";

vi.mock("@/services/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      readonly status: number,
      readonly details?: unknown,
      readonly code?: string,
      readonly correlationId?: string
    ) {
      super(message);
      this.name = "ApiError";
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const pagination = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};
const meta = { correlation_id: "corr-accounting-1", timestamp: "2026-07-31T00:00:00Z" };
const record = {
  id: "record-1",
  tenant_id: "tenant-1",
  version: 7,
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
};
const envelope = <T>(data: T): ApiEnvelope<T> => ({ data, meta });
const listEnvelope = <T>(data: readonly T[]): ApiListEnvelope<T> => ({
  data,
  meta: { ...meta, pagination },
});
const account = {
  ...record,
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
  description: "Operating cash",
  is_deleted: false,
};
const period = {
  ...record,
  period_name: "FY26-07",
  start_date: "2026-07-01",
  end_date: "2026-07-31",
  fiscal_year: 2026,
  status: "open",
  closed_at: null,
  closed_by: null,
  locked_at: null,
  locked_by: null,
  transition_history: [],
};
const journal = {
  ...record,
  entry_number: "JE-1",
  posting_date: "2026-07-31",
  posting_period: "period-1",
  reference: "REF",
  description: "Accrual",
  status: "draft",
  currency: "USD",
  debit_total: "10.00",
  credit_total: "10.00",
  posted_at: null,
  posted_by: null,
  reversed_at: null,
  reversed_by: null,
  reversed_entry: null,
  source_module: "manual",
  source_reference: "manual-1",
  transition_history: [],
  lines: [],
  is_deleted: false,
};
const invoice = {
  ...record,
  invoice_number: "INV-1",
  vendor_id: "vendor-1",
  vendor_name: "Vendor",
  customer_id: "customer-1",
  customer_name: "Customer",
  invoice_date: "2026-07-31",
  due_date: "2026-08-31",
  posting_period: "period-1",
  currency: "USD",
  subtotal: "10.00",
  tax_total: "0.00",
  total_amount: "10.00",
  paid_amount: "0.00",
  balance_due: "10.00",
  status: "draft",
  lines: [],
  transition_history: [],
  is_deleted: false,
};
const payment = {
  ...record,
  payment_number: "PAY-1",
  payment_date: "2026-07-31",
  payment_method: "ach",
  amount: "10.00",
  currency: "USD",
  status: "recorded",
  party_id: "party-1",
  party_name: "Party",
  reference: "REF",
  transition_history: [],
};
const job = {
  id: "job-1",
  job_type: "trial_balance",
  status: "queued",
  progress: 0,
  requested_by: "user-1",
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
};
const command = { transition_key: "transition-1", version: 7, reason: "Governed action" };

describe("accounting service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("classifies governed API failures and exposes field errors", () => {
    expect(new AccountingApiError("Missing", 404, "NOT_FOUND", null, null).kind).toBe("not-found");
    expect(new AccountingApiError("Unauthenticated", 401, "AUTH_REQUIRED", null, null).kind).toBe(
      "permission"
    );
    expect(new AccountingApiError("Denied", 403, "DENIED", null, null).kind).toBe("permission");
    expect(new AccountingApiError("Conflict", 409, "ANY", null, null).kind).toBe("conflict");
    expect(new AccountingApiError("Closed", 400, "PERIOD_CLOSED", null, null).kind).toBe(
      "conflict"
    );
    expect(new AccountingApiError("Stale", 422, "STALE_VERSION", null, null).kind).toBe("conflict");
    expect(new AccountingApiError("Idempotent", 422, "IDEMPOTENCY_CONFLICT", null, null).kind).toBe(
      "conflict"
    );
    expect(new AccountingApiError("Transition", 422, "ILLEGAL_TRANSITION", null, null).kind).toBe(
      "conflict"
    );
    expect(new AccountingApiError("SOD", 422, "SOD_DENIED", null, null).kind).toBe("conflict");
    expect(
      new AccountingApiError("Capability", 422, "CAPABILITY_UNAVAILABLE", null, null).kind
    ).toBe("dependency");
    expect(new AccountingApiError("Down", 503, "ANY", null, null).kind).toBe("dependency");
    expect(new AccountingApiError("Network", 0, "ANY", null, null).kind).toBe("network");
    expect(new AccountingApiError("Invalid", 422, "VALIDATION_ERROR", null, null).kind).toBe(
      "validation"
    );
    expect(new AccountingApiError("Unknown", 422, "UNKNOWN", null, null).kind).toBe("unknown");
    const defaultError = new AccountingApiError("Default", 500, "ERR", null, null);
    expect(defaultError.name).toBe("AccountingApiError");
    expect(defaultError.fieldErrors).toEqual([]);
    const validation = new AccountingApiError("Invalid", 400, "VALIDATION_ERROR", "corr-1", null, [
      { field: "code", code: "duplicate", message: "Already used" },
    ]);
    expect(validation.kind).toBe("validation");
    expect(validation.fieldError("code")).toBe("Already used");
    expect(validation.fieldError("name")).toBeUndefined();
  });

  it("unwraps list envelopes and serializes only meaningful filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(listEnvelope([account]));

    await expect(
      accountingService.listAccounts({
        search: "cash & bank",
        account_type: "asset",
        parent: "",
        is_active: false,
        page: 2,
      })
    ).resolves.toEqual({
      results: [account],
      pagination,
      meta: { ...meta, pagination },
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.ACCOUNTS.LIST}?search=cash+%26+bank&account_type=asset&is_active=false&page=2`
    );
  });

  it("preserves false and zero filter values while omitting empty optional values", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(listEnvelope([account]));

    await accountingService.listAccounts({
      search: "",
      parent: null,
      page: 0,
      is_active: false,
    } as never);
    await accountingService.accountHierarchy();
    await accountingService.generalLedger({
      start_date: "2026-07-01",
      end_date: "2026-07-31",
      account_id: undefined,
      include_zero_activity: false,
    } as never);

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.ACCOUNTS.LIST}?page=0&is_active=false`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.ACCOUNTS.HIERARCHY}?active_only=true`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.REPORTS.GENERAL_LEDGER}?start_date=2026-07-01&end_date=2026-07-31&include_zero_activity=false`
    );
  });

  it("uses account endpoints, idempotency keys, and optimistic version headers", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope(account));
    vi.mocked(apiClient.post).mockResolvedValue(envelope(account));
    vi.mocked(apiClient.patch).mockResolvedValue(envelope(account));
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await expect(accountingService.getAccount("account-1")).resolves.toEqual(account);
    await expect(
      accountingService.createAccount({ code: "1000" } as never, "account-key")
    ).resolves.toEqual(account);
    await expect(
      accountingService.updateAccount("account-1", { version: 7 } as never)
    ).resolves.toEqual(account);
    await expect(accountingService.deleteAccount("account-1")).resolves.toBeUndefined();
    await expect(accountingService.accountHierarchy(false)).resolves.toEqual(account);

    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.ACCOUNTS.DETAIL("account-1"));
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.ACCOUNTS.CREATE,
      { code: "1000" },
      { headers: { "Idempotency-Key": "account-key" } }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.ACCOUNTS.UPDATE("account-1"),
      { version: 7 },
      { headers: { "If-Match": '"7"' } }
    );
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.ACCOUNTS.DELETE("account-1"));
    expect(apiClient.get).toHaveBeenLastCalledWith(
      `${ENDPOINTS.ACCOUNTS.HIERARCHY}?active_only=false`
    );
  });

  it("uses governed posting period transition endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(listEnvelope([period]));
    vi.mocked(apiClient.post).mockResolvedValue(envelope(period));
    vi.mocked(apiClient.patch).mockResolvedValue(envelope(period));

    await expect(accountingService.listPostingPeriods({ status: "open" })).resolves.toMatchObject({
      results: [period],
    });
    await expect(accountingService.getPostingPeriod("period-1")).resolves.toBeDefined();
    await expect(
      accountingService.createPostingPeriod({ period_name: "FY26-07" } as never, "period-key")
    ).resolves.toBe(period);
    await expect(
      accountingService.updatePostingPeriod("period-1", { version: 7 } as never)
    ).resolves.toBe(period);
    await expect(accountingService.closePostingPeriod("period-1", command)).resolves.toBe(period);
    await expect(accountingService.reopenPostingPeriod("period-1", command)).resolves.toBe(period);
    await expect(accountingService.lockPostingPeriod("period-1", command)).resolves.toBe(period);

    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.POSTING_PERIODS.LIST}?status=open`);
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.POSTING_PERIODS.CREATE,
      { period_name: "FY26-07" },
      { headers: { "Idempotency-Key": "period-key" } }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.POSTING_PERIODS.UPDATE("period-1"),
      { version: 7 },
      { headers: { "If-Match": '"7"' } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.POSTING_PERIODS.CLOSE("period-1"),
      command,
      { headers: { "Idempotency-Key": "transition-1", "If-Match": '"7"' } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.POSTING_PERIODS.REOPEN("period-1"),
      command,
      { headers: { "Idempotency-Key": "transition-1", "If-Match": '"7"' } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.POSTING_PERIODS.LOCK("period-1"),
      command,
      { headers: { "Idempotency-Key": "transition-1", "If-Match": '"7"' } }
    );
  });

  it("uses journal entry command endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(listEnvelope([journal]));
    vi.mocked(apiClient.post).mockResolvedValue(envelope(journal));
    vi.mocked(apiClient.patch).mockResolvedValue(envelope(journal));
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await expect(accountingService.listJournalEntries({ status: "draft" })).resolves.toMatchObject({
      results: [journal],
    });
    await expect(accountingService.getJournalEntry("journal-1")).resolves.toBeDefined();
    await expect(
      accountingService.createJournalEntry(
        { entry_number: "JE-1", lines: [] } as never,
        "journal-key"
      )
    ).resolves.toBe(journal);
    await expect(
      accountingService.updateJournalEntry("journal-1", { version: 7 } as never)
    ).resolves.toBe(journal);
    await expect(accountingService.deleteJournalEntry("journal-1")).resolves.toBeUndefined();
    await expect(accountingService.postJournalEntry("journal-1", command)).resolves.toBe(journal);
    await expect(
      accountingService.reverseJournalEntry("journal-1", {
        ...command,
        reversal_date: "2026-08-01",
      } as never)
    ).resolves.toBe(journal);
    await expect(
      accountingService.importJournalEntries({ file_id: "file-1" } as never, "import-key")
    ).resolves.toBeDefined();

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.JOURNAL_ENTRIES.LIST}?status=draft`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(2, ENDPOINTS.JOURNAL_ENTRIES.DETAIL("journal-1"));
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.JOURNAL_ENTRIES.CREATE,
      { entry_number: "JE-1", lines: [] },
      { headers: { "Idempotency-Key": "journal-key" } }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.JOURNAL_ENTRIES.UPDATE("journal-1"),
      { version: 7 },
      { headers: { "If-Match": '"7"' } }
    );
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.JOURNAL_ENTRIES.DELETE("journal-1"));
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.JOURNAL_ENTRIES.POST("journal-1"),
      command,
      { headers: { "Idempotency-Key": "transition-1", "If-Match": '"7"' } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.JOURNAL_ENTRIES.REVERSE("journal-1"),
      { ...command, reversal_date: "2026-08-01" },
      { headers: { "Idempotency-Key": "transition-1", "If-Match": '"7"' } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.JOURNAL_ENTRIES.BATCH_IMPORT,
      { file_id: "file-1" },
      { headers: { "Idempotency-Key": "import-key" } }
    );
  });

  it("uses AP and AR invoice lifecycle endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(listEnvelope([invoice]));
    vi.mocked(apiClient.post).mockResolvedValue(envelope(invoice));
    vi.mocked(apiClient.patch).mockResolvedValue(envelope(invoice));
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await expect(accountingService.listAPInvoices({ status: "draft" })).resolves.toMatchObject({
      results: [invoice],
    });
    await expect(accountingService.getAPInvoice("ap-1")).resolves.toBeDefined();
    await expect(
      accountingService.createAPInvoice({ invoice_number: "AP-1" } as never, "ap-key")
    ).resolves.toBe(invoice);
    await expect(accountingService.updateAPInvoice("ap-1", { version: 7 } as never)).resolves.toBe(
      invoice
    );
    await expect(accountingService.deleteAPInvoice("ap-1")).resolves.toBeUndefined();
    await expect(accountingService.submitAPInvoice("ap-1", command)).resolves.toBe(invoice);
    await expect(
      accountingService.approveAPInvoice("ap-1", { ...command, approved: true } as never)
    ).resolves.toBe(invoice);
    await expect(accountingService.rejectAPInvoice("ap-1", command)).resolves.toBe(invoice);
    await expect(accountingService.postAPInvoice("ap-1", command)).resolves.toBe(invoice);
    await expect(accountingService.cancelAPInvoice("ap-1", command)).resolves.toBe(invoice);
    await expect(accountingService.apAging({ as_of_date: "2026-07-31" })).resolves.toBeDefined();
    await expect(accountingService.listARInvoices({ status: "posted" })).resolves.toMatchObject({
      results: [invoice],
    });
    await expect(accountingService.getARInvoice("ar-1")).resolves.toBeDefined();
    await expect(
      accountingService.createARInvoice({ invoice_number: "AR-1" } as never, "ar-key")
    ).resolves.toBe(invoice);
    await expect(accountingService.updateARInvoice("ar-1", { version: 7 } as never)).resolves.toBe(
      invoice
    );
    await expect(accountingService.deleteARInvoice("ar-1")).resolves.toBeUndefined();
    await expect(accountingService.postARInvoice("ar-1", command)).resolves.toBe(invoice);
    await expect(accountingService.cancelARInvoice("ar-1", command)).resolves.toBe(invoice);
    await expect(accountingService.arAging({ as_of_date: "2026-07-31" })).resolves.toBeDefined();

    expect(apiClient.get).toHaveBeenNthCalledWith(1, `${ENDPOINTS.AP_INVOICES.LIST}?status=draft`);
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.AP_INVOICES.CREATE,
      { invoice_number: "AP-1" },
      { headers: { "Idempotency-Key": "ap-key" } }
    );
    expect(apiClient.patch).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.AP_INVOICES.UPDATE("ap-1"),
      { version: 7 },
      { headers: { "If-Match": '"7"' } }
    );
    expect(apiClient.delete).toHaveBeenNthCalledWith(1, ENDPOINTS.AP_INVOICES.DELETE("ap-1"));
    expect(apiClient.get).toHaveBeenNthCalledWith(2, ENDPOINTS.AP_INVOICES.DETAIL("ap-1"));
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.AP_INVOICES.AGING}?as_of_date=2026-07-31`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(4, `${ENDPOINTS.AR_INVOICES.LIST}?status=posted`);
    expect(apiClient.get).toHaveBeenNthCalledWith(5, ENDPOINTS.AR_INVOICES.DETAIL("ar-1"));
    expect(apiClient.post).toHaveBeenNthCalledWith(
      7,
      ENDPOINTS.AR_INVOICES.CREATE,
      { invoice_number: "AR-1" },
      { headers: { "Idempotency-Key": "ar-key" } }
    );
    expect(apiClient.patch).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.AR_INVOICES.UPDATE("ar-1"),
      { version: 7 },
      { headers: { "If-Match": '"7"' } }
    );
    expect(apiClient.delete).toHaveBeenNthCalledWith(2, ENDPOINTS.AR_INVOICES.DELETE("ar-1"));
    expect(apiClient.get).toHaveBeenNthCalledWith(
      6,
      `${ENDPOINTS.AR_INVOICES.AGING}?as_of_date=2026-07-31`
    );
  });

  it("uses payment, report, job, and health endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(listEnvelope([payment]));
    vi.mocked(apiClient.post).mockResolvedValue(envelope(job));
    vi.mocked(apiClient.patch).mockResolvedValue(envelope(payment));

    await expect(accountingService.listPayments({ status: "recorded" })).resolves.toMatchObject({
      results: [payment],
    });
    await expect(accountingService.getPayment("payment-1")).resolves.toBeDefined();
    await expect(
      accountingService.createPayment({ payment_number: "PAY-1" } as never, "payment-key")
    ).resolves.toBeDefined();
    await expect(
      accountingService.updatePayment("payment-1", { version: 7 } as never)
    ).resolves.toBe(payment);
    await expect(
      accountingService.voidPayment("payment-1", {
        transition_key: "void-key",
        reason: "duplicate",
      } as never)
    ).resolves.toBeDefined();
    await expect(
      accountingService.trialBalance({ as_of_date: "2026-07-31" })
    ).resolves.toBeDefined();
    await expect(
      accountingService.generalLedger({
        start_date: "2026-07-01",
        end_date: "2026-07-31",
        account_id: "account-1",
      })
    ).resolves.toBeDefined();
    await expect(
      accountingService.balanceSheet({ as_of_date: "2026-07-31" })
    ).resolves.toBeDefined();
    await expect(
      accountingService.incomeStatement({ start_date: "2026-07-01", end_date: "2026-07-31" })
    ).resolves.toBeDefined();
    await expect(
      accountingService.cashFlow({ start_date: "2026-07-01", end_date: "2026-07-31" })
    ).resolves.toBeDefined();
    await expect(
      accountingService.generateReport({ report_type: "trial_balance" } as never, "report-key")
    ).resolves.toBe(job);
    await expect(accountingService.getJob("job-1")).resolves.toBeDefined();
    await expect(accountingService.health()).resolves.toBeDefined();

    expect(apiClient.get).toHaveBeenNthCalledWith(1, `${ENDPOINTS.PAYMENTS.LIST}?status=recorded`);
    expect(apiClient.get).toHaveBeenNthCalledWith(2, ENDPOINTS.PAYMENTS.DETAIL("payment-1"));
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.PAYMENTS.CREATE,
      { payment_number: "PAY-1" },
      { headers: { "Idempotency-Key": "payment-key" } }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.PAYMENTS.UPDATE("payment-1"), {
      version: 7,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.PAYMENTS.VOID("payment-1"),
      { transition_key: "void-key", reason: "duplicate" },
      { headers: { "Idempotency-Key": "void-key" } }
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.REPORTS.TRIAL_BALANCE}?as_of_date=2026-07-31`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      4,
      `${ENDPOINTS.REPORTS.GENERAL_LEDGER}?start_date=2026-07-01&end_date=2026-07-31&account_id=account-1`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      5,
      `${ENDPOINTS.REPORTS.BALANCE_SHEET}?as_of_date=2026-07-31`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      6,
      `${ENDPOINTS.REPORTS.INCOME_STATEMENT}?start_date=2026-07-01&end_date=2026-07-31`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      7,
      `${ENDPOINTS.REPORTS.CASH_FLOW}?start_date=2026-07-01&end_date=2026-07-31`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.REPORTS.GENERATE,
      { report_type: "trial_balance" },
      { headers: { "Idempotency-Key": "report-key" } }
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(8, ENDPOINTS.JOBS.DETAIL("job-1"));
    expect(apiClient.get).toHaveBeenNthCalledWith(9, ENDPOINTS.HEALTH);
  });

  it("routes every AP and AR transition to a distinct governed endpoint with versioned headers", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(envelope(invoice));

    await accountingService.submitAPInvoice("ap-1", command);
    await accountingService.approveAPInvoice("ap-1", { ...command, approved: true } as never);
    await accountingService.rejectAPInvoice("ap-1", command);
    await accountingService.postAPInvoice("ap-1", command);
    await accountingService.cancelAPInvoice("ap-1", command);
    await accountingService.postARInvoice("ar-1", command);
    await accountingService.cancelARInvoice("ar-1", command);

    const headers = { headers: { "Idempotency-Key": "transition-1", "If-Match": '"7"' } };
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.AP_INVOICES.SUBMIT("ap-1"),
      command,
      headers
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.AP_INVOICES.APPROVE("ap-1"),
      { ...command, approved: true },
      headers
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.AP_INVOICES.REJECT("ap-1"),
      command,
      headers
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.AP_INVOICES.POST("ap-1"),
      command,
      headers
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      5,
      ENDPOINTS.AP_INVOICES.CANCEL("ap-1"),
      command,
      headers
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      6,
      ENDPOINTS.AR_INVOICES.POST("ar-1"),
      command,
      headers
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      7,
      ENDPOINTS.AR_INVOICES.CANCEL("ar-1"),
      command,
      headers
    );
  });

  it("sends create, update, and command options only when the adapter contract requires them", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(envelope(payment));
    vi.mocked(apiClient.patch).mockResolvedValue(envelope(payment));

    await accountingService.createPayment({ payment_number: "PAY-2" } as never, "payment-key-2");
    await accountingService.updatePayment("payment-2", { version: 8 } as never);
    await accountingService.voidPayment("payment-2", {
      transition_key: "void-key-2",
      reason: "duplicate",
    } as never);

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.PAYMENTS.CREATE,
      { payment_number: "PAY-2" },
      { headers: { "Idempotency-Key": "payment-key-2" } }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.PAYMENTS.UPDATE("payment-2"), {
      version: 8,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.PAYMENTS.VOID("payment-2"),
      { transition_key: "void-key-2", reason: "duplicate" },
      { headers: { "Idempotency-Key": "void-key-2" } }
    );
  });

  it("rejects malformed envelopes and translates governed errors", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: account });
    await expect(accountingService.getAccount("account-1")).rejects.toMatchObject({
      code: "MALFORMED_RESPONSE",
      status: 502,
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: account, meta });
    await expect(accountingService.listAccounts()).rejects.toMatchObject({
      code: "MALFORMED_RESPONSE",
      status: 502,
      correlationId: "corr-accounting-1",
    });

    vi.mocked(apiClient.get).mockRejectedValueOnce(
      new ApiError(
        "Rejected",
        400,
        {
          error: {
            code: "VALIDATION_ERROR",
            message: "Validation failed",
            detail: "Correct highlighted fields.",
            correlation_id: "corr-error-1",
            field_errors: [{ field: "code", code: "duplicate", message: "Code exists" }],
          },
        },
        "REQUEST_FAILED",
        "fallback-corr"
      )
    );
    await expect(accountingService.getAccount("account-1")).rejects.toMatchObject({
      message: "Validation failed",
      status: 400,
      code: "VALIDATION_ERROR",
      correlationId: "corr-error-1",
      detail: "Correct highlighted fields.",
      fieldErrors: [{ field: "code", code: "duplicate", message: "Code exists" }],
    });

    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error("offline"));
    await expect(accountingService.getAccount("account-1")).rejects.toMatchObject({
      message: "The accounting service could not be reached.",
      status: 0,
      code: "NETWORK_ERROR",
    });

    vi.mocked(apiClient.get).mockRejectedValueOnce(
      new ApiError("Fallback", 500, { error: null }, undefined, "fallback-corr")
    );
    await expect(accountingService.getAccount("account-1")).rejects.toMatchObject({
      message: "Fallback",
      status: 500,
      code: "REQUEST_FAILED",
      correlationId: "fallback-corr",
      fieldErrors: [],
    });

    vi.mocked(apiClient.get).mockRejectedValueOnce(
      new ApiError(
        "Fallback string code",
        502,
        { error: { code: 42, message: "ignored" } },
        "UPSTREAM_BAD_GATEWAY",
        "fallback-corr-2"
      )
    );
    await expect(accountingService.getAccount("account-1")).rejects.toMatchObject({
      message: "Fallback string code",
      status: 502,
      code: "UPSTREAM_BAD_GATEWAY",
      correlationId: "fallback-corr-2",
    });

    vi.mocked(apiClient.get).mockRejectedValueOnce(
      new AccountingApiError("Already translated", 409, "STALE_VERSION", null, null)
    );
    await expect(accountingService.getAccount("account-1")).rejects.toMatchObject({
      message: "Already translated",
      code: "STALE_VERSION",
    });
  });

  it("creates deterministic command keys and identifies pollable job states", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "uuid-1" });

    expect(createIdempotencyKey("journal.post")).toBe("journal.post:uuid-1");
    expect(shouldPollJob(undefined)).toBe(false);
    expect(shouldPollJob({ ...job, status: "queued" } as never)).toBe(true);
    expect(shouldPollJob({ ...job, status: "running" } as never)).toBe(true);
    expect(shouldPollJob({ ...job, status: "retrying" } as never)).toBe(true);
    expect(shouldPollJob({ ...job, status: "succeeded" } as never)).toBe(false);
    expect(shouldPollJob({ ...job, status: "failed" } as never)).toBe(false);
  });
});
