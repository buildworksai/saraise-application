import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type AcceptedImport,
  type ApiV2Collection,
  type ApiV2Error,
  type ApiV2Response,
  type BankAccount,
  type BankAccountCreate,
  type BankAccountFilters,
  type BankAccountUpdate,
  type BankStatement,
  type BankTransaction,
  type CandidateResult,
  type HealthStatus,
  type IdempotentAction,
  type IdempotentReasonAction,
  type ImportFilters,
  type ManualMatchCreate,
  type ManualStatementCreate,
  type ManualTransactionInput,
  type ManualTransactionUpdate,
  type MatchingRule,
  type MatchingRuleCreate,
  type MatchingRuleUpdate,
  type PaginationMeta,
  type ReasonAction,
  type ReconciliationCreate,
  type ReconciliationFilters,
  type ReconciliationMatch,
  type ReconciliationSession,
  type RuleFilters,
  type StatementFilters,
  type StatementImport,
  type StatementImportCreate,
  type TransactionFilters,
  type UUID,
} from "../contracts";

export interface CollectionResult<T> {
  items: T[];
  pagination: PaginationMeta;
  correlationId: string;
}

const unwrap = <T>(response: ApiV2Response<T>): T => response.data;
const unwrapCollection = <T>(response: ApiV2Collection<T>): CollectionResult<T> => ({
  items: response.data,
  pagination: response.meta.pagination,
  correlationId: response.meta.correlation_id,
});

const withQuery = (path: string, filters?: object): string => {
  if (!filters) return path;
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const query = params.toString();
  return query ? `${path}?${query}` : path;
};

const csrfToken = (): string | undefined =>
  document.cookie
    .split("; ")
    .find((part) => part.startsWith("saraise_csrftoken="))
    ?.split("=")[1];

async function uploadImport(payload: StatementImportCreate): Promise<AcceptedImport> {
  const form = new FormData();
  form.append("bank_account", payload.bank_account);
  form.append("file", payload.file);
  form.append("file_format", payload.file_format);
  form.append("idempotency_key", payload.idempotency_key);
  if (payload.mapping) form.append("mapping", JSON.stringify(payload.mapping));
  const token = csrfToken();
  const response = await fetch(ENDPOINTS.IMPORTS.CREATE, {
    method: "POST",
    body: form,
    credentials: "include",
    headers: token ? { "X-CSRFToken": token } : {},
  });
  if (!response.ok) {
    const failure = (await response.json()) as ApiV2Error;
    throw new ApiError(
      failure.error.message,
      response.status,
      failure,
      failure.error.code,
      failure.error.correlation_id
    );
  }
  return unwrap((await response.json()) as ApiV2Response<AcceptedImport>);
}

const get = async <T>(path: string): Promise<T> =>
  unwrap(await apiClient.get<ApiV2Response<T>>(path));
const post = async <T>(path: string, body?: object): Promise<T> =>
  unwrap(await apiClient.post<ApiV2Response<T>>(path, body));
const patch = async <T>(path: string, body: object): Promise<T> =>
  unwrap(await apiClient.patch<ApiV2Response<T>>(path, body));
const list = async <T>(path: string, filters?: object): Promise<CollectionResult<T>> =>
  unwrapCollection(await apiClient.get<ApiV2Collection<T>>(withQuery(path, filters)));

const terminalImportStatuses = new Set<StatementImport["status"]>([
  "succeeded",
  "failed",
  "cancelled",
]);

export const bankReconciliationService = {
  listBankAccounts: (filters?: BankAccountFilters) =>
    list<BankAccount>(ENDPOINTS.ACCOUNTS.LIST, filters),
  getBankAccount: (id: UUID) => get<BankAccount>(ENDPOINTS.ACCOUNTS.DETAIL(id)),
  createBankAccount: (data: BankAccountCreate) =>
    post<BankAccount>(ENDPOINTS.ACCOUNTS.CREATE, data),
  updateBankAccount: (id: UUID, data: BankAccountUpdate) =>
    patch<BankAccount>(ENDPOINTS.ACCOUNTS.UPDATE(id), data),
  archiveBankAccount: (id: UUID) => apiClient.delete<void>(ENDPOINTS.ACCOUNTS.ARCHIVE(id)),

  listStatements: (filters?: StatementFilters) =>
    list<BankStatement>(ENDPOINTS.STATEMENTS.LIST, filters),
  getStatement: (id: UUID) => get<BankStatement>(ENDPOINTS.STATEMENTS.DETAIL(id)),
  createManualStatement: (data: ManualStatementCreate) =>
    post<BankStatement>(ENDPOINTS.STATEMENTS.CREATE, data),
  voidStatement: (id: UUID, data: IdempotentReasonAction) =>
    post<BankStatement>(ENDPOINTS.STATEMENTS.VOID(id), data),
  listStatementTransactions: (id: UUID, filters?: TransactionFilters) =>
    list<BankTransaction>(ENDPOINTS.STATEMENTS.TRANSACTIONS(id), filters),
  addManualTransaction: (id: UUID, data: ManualTransactionInput) =>
    post<BankTransaction>(ENDPOINTS.STATEMENTS.TRANSACTIONS(id), data),

  listTransactions: (filters?: TransactionFilters) =>
    list<BankTransaction>(ENDPOINTS.TRANSACTIONS.LIST, filters),
  getTransaction: (id: UUID) => get<BankTransaction>(ENDPOINTS.TRANSACTIONS.DETAIL(id)),
  updateManualTransaction: (id: UUID, data: ManualTransactionUpdate) =>
    patch<BankTransaction>(ENDPOINTS.TRANSACTIONS.UPDATE(id), data),
  excludeTransaction: (id: UUID, data: ReasonAction) =>
    post<BankTransaction>(ENDPOINTS.TRANSACTIONS.EXCLUDE(id), data),
  restoreTransaction: (id: UUID) => post<BankTransaction>(ENDPOINTS.TRANSACTIONS.RESTORE(id)),

  requestImport: uploadImport,
  listImports: (filters?: ImportFilters) => list<StatementImport>(ENDPOINTS.IMPORTS.LIST, filters),
  getImport: (id: UUID) => get<StatementImport>(ENDPOINTS.IMPORTS.DETAIL(id)),
  retryImport: (id: UUID, data: IdempotentAction) =>
    post<AcceptedImport>(ENDPOINTS.IMPORTS.RETRY(id), data),
  cancelImport: (id: UUID) => post<StatementImport>(ENDPOINTS.IMPORTS.CANCEL(id)),
  pollImport: async (
    id: UUID,
    options: { intervalMs?: number; maxAttempts?: number; signal?: AbortSignal } = {}
  ) => {
    const intervalMs = Math.min(30_000, Math.max(1_000, options.intervalMs ?? 2_000));
    const maxAttempts = Math.min(300, Math.max(1, options.maxAttempts ?? 150));
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      if (options.signal?.aborted) throw new DOMException("Import polling cancelled", "AbortError");
      const current = await get<StatementImport>(ENDPOINTS.IMPORTS.DETAIL(id));
      if (terminalImportStatuses.has(current.status)) return current;
      await new Promise<void>((resolve, reject) => {
        const timer = window.setTimeout(resolve, intervalMs);
        options.signal?.addEventListener(
          "abort",
          () => {
            window.clearTimeout(timer);
            reject(new DOMException("Import polling cancelled", "AbortError"));
          },
          { once: true }
        );
      });
    }
    throw new ApiError("Import status polling timed out.", 408, undefined, "POLL_TIMEOUT");
  },

  listRules: (filters?: RuleFilters) => list<MatchingRule>(ENDPOINTS.RULES.LIST, filters),
  getRule: (id: UUID) => get<MatchingRule>(ENDPOINTS.RULES.DETAIL(id)),
  createRule: (data: MatchingRuleCreate) => post<MatchingRule>(ENDPOINTS.RULES.CREATE, data),
  updateRule: (id: UUID, data: MatchingRuleUpdate) =>
    patch<MatchingRule>(ENDPOINTS.RULES.UPDATE(id), data),
  deleteRule: (id: UUID) => apiClient.delete<void>(ENDPOINTS.RULES.DELETE(id)),
  activateRule: (id: UUID) => post<MatchingRule>(ENDPOINTS.RULES.ACTIVATE(id)),
  deactivateRule: (id: UUID) => post<MatchingRule>(ENDPOINTS.RULES.DEACTIVATE(id)),

  listReconciliations: (filters?: ReconciliationFilters) =>
    list<ReconciliationSession>(ENDPOINTS.RECONCILIATIONS.LIST, filters),
  getReconciliation: (id: UUID) => get<ReconciliationSession>(ENDPOINTS.RECONCILIATIONS.DETAIL(id)),
  createReconciliation: (data: ReconciliationCreate) =>
    post<ReconciliationSession>(ENDPOINTS.RECONCILIATIONS.CREATE, data),
  startReconciliation: (id: UUID, data: IdempotentAction) =>
    post<ReconciliationSession>(ENDPOINTS.RECONCILIATIONS.START(id), data),
  generateCandidates: (id: UUID, data: IdempotentAction) =>
    post<CandidateResult>(ENDPOINTS.RECONCILIATIONS.GENERATE_CANDIDATES(id), data),
  createManualMatch: (id: UUID, data: ManualMatchCreate) =>
    post<ReconciliationMatch>(ENDPOINTS.RECONCILIATIONS.MATCHES(id), data),
  submitReview: (id: UUID, data: IdempotentAction) =>
    post<ReconciliationSession>(ENDPOINTS.RECONCILIATIONS.SUBMIT_REVIEW(id), data),
  returnToWork: (id: UUID, data: IdempotentReasonAction) =>
    post<ReconciliationSession>(ENDPOINTS.RECONCILIATIONS.RETURN_TO_WORK(id), data),
  finalizeReconciliation: (id: UUID, data: IdempotentAction) =>
    post<ReconciliationSession>(ENDPOINTS.RECONCILIATIONS.FINALIZE(id), data),
  voidReconciliation: (id: UUID, data: IdempotentReasonAction) =>
    post<ReconciliationSession>(ENDPOINTS.RECONCILIATIONS.VOID(id), data),

  getMatch: (id: UUID) => get<ReconciliationMatch>(ENDPOINTS.MATCHES.DETAIL(id)),
  confirmMatch: (id: UUID, data: IdempotentAction) =>
    post<ReconciliationMatch>(ENDPOINTS.MATCHES.CONFIRM(id), data),
  rejectMatch: (id: UUID, data: ReasonAction) =>
    post<ReconciliationMatch>(ENDPOINTS.MATCHES.REJECT(id), data),
  reverseMatch: (id: UUID, data: IdempotentReasonAction) =>
    post<ReconciliationMatch>(ENDPOINTS.MATCHES.REVERSE(id), data),

  downloadReport: async (id: UUID, format: "csv" | "pdf" = "csv"): Promise<Blob> => {
    const response = await fetch(ENDPOINTS.RECONCILIATIONS.REPORT(id, format), {
      credentials: "include",
    });
    if (!response.ok)
      throw new ApiError(
        "Unable to export reconciliation evidence.",
        response.status,
        undefined,
        "REPORT_EXPORT_FAILED",
        response.headers.get("X-Correlation-ID") ?? undefined
      );
    return response.blob();
  },
  health: () => get<HealthStatus>(ENDPOINTS.HEALTH),
};
