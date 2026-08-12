/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- endpoint contract tests intentionally keep service workflows together. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import { bankReconciliationService } from "./bank-reconciliation-service";

vi.mock("@/services/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public details?: object,
      public code?: string,
      public correlationId?: string
    ) {
      super(message);
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const mockedClient = vi.mocked(apiClient);

describe("bank reconciliation service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.cookie = "saraise_csrftoken=csrf-bank";
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("unwraps only the governed collection envelope and preserves metadata", async () => {
    vi.mocked(mockedClient.get).mockResolvedValue({
      data: [],
      meta: {
        correlation_id: "req-1",
        timestamp: "2026-07-23T00:00:00Z",
        pagination: {
          page: 2,
          page_size: 25,
          total_pages: 3,
          count: 55,
          has_next: true,
          has_previous: true,
        },
      },
    });
    const result = await bankReconciliationService.listBankAccounts({
      page: 2,
      search: "operating",
    });
    expect(mockedClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.ACCOUNTS.LIST}?page=2&search=operating`
    );
    expect(result.items).toEqual([]);
    expect(result.correlationId).toBe("req-1");
    expect(result.pagination.page).toBe(2);
    expect(result.pagination.count).toBe(55);
  });

  it("uses archive DELETE semantics rather than physical-delete language or PUT", async () => {
    vi.mocked(mockedClient.delete).mockResolvedValue(undefined);
    await bankReconciliationService.archiveBankAccount("account-1");
    expect(mockedClient.delete).toHaveBeenCalledWith(ENDPOINTS.ACCOUNTS.ARCHIVE("account-1"));
  });

  it("routes all synchronous resource mutations through exact governed endpoints", async () => {
    vi.mocked(mockedClient.get).mockResolvedValue({ data: { id: "resource-1" }, meta: {} });
    vi.mocked(mockedClient.post).mockResolvedValue({ data: { id: "resource-1" }, meta: {} });
    vi.mocked(mockedClient.patch).mockResolvedValue({ data: { id: "resource-1" }, meta: {} });
    vi.mocked(mockedClient.delete).mockResolvedValue(undefined);

    await bankReconciliationService.createBankAccount({ account_name: "Operating" } as never);
    await bankReconciliationService.updateBankAccount("account-1", { currency: "USD" } as never);
    await bankReconciliationService.listStatements({ bank_account: "account-1", page_size: 10 });
    await bankReconciliationService.createManualStatement({ bank_account: "account-1" } as never);
    await bankReconciliationService.voidStatement("statement-1", {
      reason: "duplicate",
      idempotency_key: "void-once",
    });
    await bankReconciliationService.listStatementTransactions("statement-1", {
      reconciled: false,
    } as never);
    await bankReconciliationService.addManualTransaction("statement-1", {
      amount: "10.0000",
    } as never);
    await bankReconciliationService.updateManualTransaction("transaction-1", {
      amount: "9.0000",
    } as never);
    await bankReconciliationService.excludeTransaction("transaction-1", { reason: "fee" });
    await bankReconciliationService.restoreTransaction("transaction-1");
    await bankReconciliationService.retryImport("import-1", { idempotency_key: "retry-once" });
    await bankReconciliationService.cancelImport("import-1");
    await bankReconciliationService.createRule({ name: "Exact" } as never);
    await bankReconciliationService.updateRule("rule-1", { minimum_score: "0.9500" });
    await bankReconciliationService.deleteRule("rule-1");
    await bankReconciliationService.activateRule("rule-1");
    await bankReconciliationService.deactivateRule("rule-1");
    await bankReconciliationService.startReconciliation("recon-1", {
      idempotency_key: "start-once",
    });
    await bankReconciliationService.generateCandidates("recon-1", {
      idempotency_key: "generate-once",
    });
    await bankReconciliationService.createManualMatch("recon-1", {
      match_type: "manual",
      lines: [],
    });
    await bankReconciliationService.returnToWork("recon-1", {
      reason: "needs evidence",
      idempotency_key: "return-once",
    });
    await bankReconciliationService.finalizeReconciliation("recon-1", {
      idempotency_key: "finalize-once",
    });
    await bankReconciliationService.voidReconciliation("recon-1", {
      reason: "wrong statement",
      idempotency_key: "void-recon-once",
    });
    await bankReconciliationService.confirmMatch("match-1", { idempotency_key: "confirm-once" });
    await bankReconciliationService.rejectMatch("match-1", { reason: "wrong amount" });
    await bankReconciliationService.reverseMatch("match-1", {
      reason: "posting error",
      idempotency_key: "reverse-once",
    });

    expect(mockedClient.post).toHaveBeenCalledWith(ENDPOINTS.ACCOUNTS.CREATE, {
      account_name: "Operating",
    });
    expect(mockedClient.patch).toHaveBeenCalledWith(ENDPOINTS.ACCOUNTS.UPDATE("account-1"), {
      currency: "USD",
    });
    expect(mockedClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.STATEMENTS.LIST}?bank_account=account-1&page_size=10`
    );
    expect(mockedClient.post).toHaveBeenCalledWith(ENDPOINTS.STATEMENTS.VOID("statement-1"), {
      reason: "duplicate",
      idempotency_key: "void-once",
    });
    expect(mockedClient.post).toHaveBeenCalledWith(
      `${ENDPOINTS.STATEMENTS.TRANSACTIONS("statement-1")}`,
      { amount: "10.0000" }
    );
    expect(mockedClient.post).toHaveBeenCalledWith(
      ENDPOINTS.TRANSACTIONS.EXCLUDE("transaction-1"),
      {
        reason: "fee",
      }
    );
    expect(mockedClient.post).toHaveBeenCalledWith(ENDPOINTS.IMPORTS.RETRY("import-1"), {
      idempotency_key: "retry-once",
    });
    expect(mockedClient.delete).toHaveBeenCalledWith(ENDPOINTS.RULES.DELETE("rule-1"));
    expect(mockedClient.post).toHaveBeenCalledWith(ENDPOINTS.RULES.ACTIVATE("rule-1"), undefined);
    expect(mockedClient.post).toHaveBeenCalledWith(ENDPOINTS.RECONCILIATIONS.START("recon-1"), {
      idempotency_key: "start-once",
    });
    expect(mockedClient.post).toHaveBeenCalledWith(ENDPOINTS.RECONCILIATIONS.MATCHES("recon-1"), {
      match_type: "manual",
      lines: [],
    });
    expect(mockedClient.post).toHaveBeenCalledWith(ENDPOINTS.MATCHES.REVERSE("match-1"), {
      reason: "posting error",
      idempotency_key: "reverse-once",
    });
  });

  it("uploads statement imports with CSRF evidence and normalizes governed failures", async () => {
    const file = new File(["date,amount"], "statement.csv", { type: "text/csv" });
    const okFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: { accepted: true, import_id: "import-1" }, meta: {} }),
    });
    vi.stubGlobal("fetch", okFetch);

    await expect(
      bankReconciliationService.requestImport({
        bank_account: "account-1",
        file,
        file_format: "csv",
        mapping: { date: "Date", amount: "Amount" },
        idempotency_key: "import-once",
      })
    ).resolves.toEqual({ accepted: true, import_id: "import-1" });

    const request = okFetch.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(okFetch).toHaveBeenCalledWith(ENDPOINTS.IMPORTS.CREATE, expect.any(Object));
    expect(request?.headers).toEqual({ "X-CSRFToken": "csrf-bank" });
    expect(request?.credentials).toBe("include");
    expect(request?.body).toBeInstanceOf(FormData);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: () =>
          Promise.resolve({
            error: {
              message: "Mapping invalid",
              code: "invalid_mapping",
              correlation_id: "corr-import",
            },
          }),
      })
    );
    const failure = await bankReconciliationService
      .requestImport({
        bank_account: "account-1",
        file,
        file_format: "csv",
        idempotency_key: "import-fail",
      })
      .catch((error: unknown) => error);
    expect(failure).toMatchObject({
      message: "Mapping invalid",
      status: 422,
      code: "invalid_mapping",
      correlationId: "corr-import",
    });
  });

  it("polls imports with bounded timing, terminal status, abort, and timeout behavior", async () => {
    vi.mocked(mockedClient.get).mockResolvedValueOnce({
      data: { id: "import-1", status: "succeeded" },
      meta: {},
    });
    await expect(bankReconciliationService.pollImport("import-1")).resolves.toMatchObject({
      status: "succeeded",
    });
    expect(mockedClient.get).toHaveBeenCalledTimes(1);

    const controller = new AbortController();
    controller.abort();
    await expect(
      bankReconciliationService.pollImport("import-1", { signal: controller.signal })
    ).rejects.toMatchObject({ name: "AbortError" });

    vi.mocked(mockedClient.get).mockResolvedValue({
      data: { id: "import-2", status: "processing" },
      meta: {},
    });
    const timedOut = bankReconciliationService.pollImport("import-2", {
      intervalMs: 1,
      maxAttempts: 1,
    });
    await expect(timedOut).rejects.toMatchObject({
      message: "Import status polling timed out.",
      status: 408,
      code: "POLL_TIMEOUT",
    });
  });

  it("downloads reconciliation evidence and preserves export failure correlation", async () => {
    const blob = new Blob(["id,total"], { type: "text/csv" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(blob),
      })
    );
    await expect(bankReconciliationService.downloadReport("recon-1", "pdf")).resolves.toBe(blob);
    expect(fetch).toHaveBeenCalledWith(ENDPOINTS.RECONCILIATIONS.REPORT("recon-1", "pdf"), {
      credentials: "include",
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        headers: new Headers({ "X-Correlation-ID": "corr-report" }),
      })
    );
    await expect(bankReconciliationService.downloadReport("recon-1")).rejects.toMatchObject({
      message: "Unable to export reconciliation evidence.",
      status: 503,
      code: "REPORT_EXPORT_FAILED",
      correlationId: "corr-report",
    });
  });
});
