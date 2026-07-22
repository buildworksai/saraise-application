import { ApiError as SharedApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type APInvoice,
  type APInvoiceCreateRequest,
  type APInvoiceListQuery,
  type APInvoiceUpdateRequest,
  type ARInvoice,
  type ARInvoiceCreateRequest,
  type ARInvoiceListQuery,
  type ARInvoiceUpdateRequest,
  type Account,
  type AccountCreateRequest,
  type AccountListQuery,
  type AccountNode,
  type AccountUpdateRequest,
  type AccountingHealth,
  type AccountingJob,
  type AgingReport,
  type ApiEnvelope,
  type ApiError,
  type ApiListEnvelope,
  type ApprovalCommand,
  type AsOfDateQuery,
  type BatchImportCommand,
  type CashFlowStatement,
  type DateRangeQuery,
  type FieldError,
  type FinancialStatement,
  type GeneralLedger,
  type GeneralLedgerQuery,
  type JournalEntry,
  type JournalEntryCreateRequest,
  type JournalEntryListQuery,
  type JournalEntryUpdateRequest,
  type ListResult,
  type Payment,
  type PaymentCreateRequest,
  type PaymentListQuery,
  type PaymentUpdateRequest,
  type PostingPeriod,
  type PostingPeriodCreateRequest,
  type PostingPeriodListQuery,
  type PostingPeriodUpdateRequest,
  type ReportGenerationCommand,
  type ReversalCommand,
  type TransitionCommand,
  type TrialBalance,
} from '../contracts';

export type AccountingFailureKind = 'not-found' | 'permission' | 'conflict' | 'dependency' | 'network' | 'validation' | 'unknown';

/** Stable UI error independent of fetch and the shared client's implementation details. */
export class AccountingApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
    readonly detail: string | null,
    readonly fieldErrors: readonly FieldError[] = [],
  ) {
    super(message);
    this.name = 'AccountingApiError';
  }

  get kind(): AccountingFailureKind {
    if (this.status === 404) return 'not-found';
    if (this.status === 401 || this.status === 403) return 'permission';
    if (this.status === 409 || ['STALE_VERSION', 'IDEMPOTENCY_CONFLICT', 'ILLEGAL_TRANSITION', 'PERIOD_CLOSED', 'SOD_DENIED'].includes(this.code)) return 'conflict';
    if (this.code === 'CAPABILITY_UNAVAILABLE' || this.status === 503) return 'dependency';
    if (this.status === 0) return 'network';
    if (this.status === 400 || this.code === 'VALIDATION_ERROR') return 'validation';
    return 'unknown';
  }

  fieldError(field: string): string | undefined {
    return this.fieldErrors.find((error) => error.field === field)?.message;
  }
}

function governedError(details: unknown): ApiError['error'] | undefined {
  if (!details || typeof details !== 'object' || !('error' in details)) return undefined;
  const error = details.error;
  if (!error || typeof error !== 'object' || !('code' in error) || !('message' in error)) return undefined;
  const candidate = error as Record<string, unknown>;
  if (typeof candidate.code !== 'string' || typeof candidate.message !== 'string') return undefined;
  return error as ApiError['error'];
}

async function translate<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (failure) {
    if (failure instanceof AccountingApiError) throw failure;
    if (failure instanceof SharedApiError) {
      const error = governedError(failure.details);
      throw new AccountingApiError(
        error?.message ?? failure.message,
        failure.status,
        error?.code ?? failure.code ?? 'REQUEST_FAILED',
        error?.correlation_id ?? failure.correlationId ?? null,
        error?.detail ?? null,
        error?.field_errors ?? [],
      );
    }
    throw new AccountingApiError('The accounting service could not be reached.', 0, 'NETWORK_ERROR', null, null);
  }
}

function query(path: string, values: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const serialized = params.toString();
  return serialized ? `${path}?${serialized}` : path;
}

function mutationHeaders(idempotencyKey?: string, version?: number): RequestInit {
  const headers: Record<string, string> = {};
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  if (version !== undefined) headers['If-Match'] = `"${version}"`;
  return { headers };
}

async function unwrap<T>(request: Promise<ApiEnvelope<T>>): Promise<T> {
  const envelope = await translate(request);
  if (!envelope.meta || !('correlation_id' in envelope.meta)) throw new AccountingApiError('The server returned an invalid response envelope.', 502, 'MALFORMED_RESPONSE', null, null);
  return envelope.data;
}

async function unwrapList<T>(request: Promise<ApiListEnvelope<T>>): Promise<ListResult<T>> {
  const envelope = await translate(request);
  if (!Array.isArray(envelope.data) || !envelope.meta?.pagination) throw new AccountingApiError('The server returned an invalid paginated response envelope.', 502, 'MALFORMED_RESPONSE', envelope.meta?.correlation_id ?? null, null);
  return { items: envelope.data, pagination: envelope.meta.pagination, meta: envelope.meta };
}

export function createIdempotencyKey(command: string): string {
  return `${command}:${crypto.randomUUID()}`;
}

export const accountingService = {
  listAccounts: (filters: AccountListQuery = {}) => unwrapList(apiClient.get<ApiListEnvelope<Account>>(query(ENDPOINTS.ACCOUNTS.LIST, filters))),
  getAccount: (id: string) => unwrap(apiClient.get<ApiEnvelope<Account>>(ENDPOINTS.ACCOUNTS.DETAIL(id))),
  createAccount: (data: AccountCreateRequest, key: string) => unwrap(apiClient.post<ApiEnvelope<Account>>(ENDPOINTS.ACCOUNTS.CREATE, data, mutationHeaders(key))),
  updateAccount: (id: string, data: AccountUpdateRequest) => unwrap(apiClient.patch<ApiEnvelope<Account>>(ENDPOINTS.ACCOUNTS.UPDATE(id), data, mutationHeaders(undefined, data.version))),
  deleteAccount: (id: string) => translate(apiClient.delete<void>(ENDPOINTS.ACCOUNTS.DELETE(id))),
  accountHierarchy: (activeOnly = true) => unwrap(apiClient.get<ApiEnvelope<readonly AccountNode[]>>(query(ENDPOINTS.ACCOUNTS.HIERARCHY, { active_only: activeOnly }))),

  listPostingPeriods: (filters: PostingPeriodListQuery = {}) => unwrapList(apiClient.get<ApiListEnvelope<PostingPeriod>>(query(ENDPOINTS.POSTING_PERIODS.LIST, filters))),
  getPostingPeriod: (id: string) => unwrap(apiClient.get<ApiEnvelope<PostingPeriod>>(ENDPOINTS.POSTING_PERIODS.DETAIL(id))),
  createPostingPeriod: (data: PostingPeriodCreateRequest, key: string) => unwrap(apiClient.post<ApiEnvelope<PostingPeriod>>(ENDPOINTS.POSTING_PERIODS.CREATE, data, mutationHeaders(key))),
  updatePostingPeriod: (id: string, data: PostingPeriodUpdateRequest) => unwrap(apiClient.patch<ApiEnvelope<PostingPeriod>>(ENDPOINTS.POSTING_PERIODS.UPDATE(id), data, mutationHeaders(undefined, data.version))),
  closePostingPeriod: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<PostingPeriod>>(ENDPOINTS.POSTING_PERIODS.CLOSE(id), command, mutationHeaders(command.transition_key, command.version))),
  reopenPostingPeriod: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<PostingPeriod>>(ENDPOINTS.POSTING_PERIODS.REOPEN(id), command, mutationHeaders(command.transition_key, command.version))),
  lockPostingPeriod: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<PostingPeriod>>(ENDPOINTS.POSTING_PERIODS.LOCK(id), command, mutationHeaders(command.transition_key, command.version))),

  listJournalEntries: (filters: JournalEntryListQuery = {}) => unwrapList(apiClient.get<ApiListEnvelope<JournalEntry>>(query(ENDPOINTS.JOURNAL_ENTRIES.LIST, filters))),
  getJournalEntry: (id: string) => unwrap(apiClient.get<ApiEnvelope<JournalEntry>>(ENDPOINTS.JOURNAL_ENTRIES.DETAIL(id))),
  createJournalEntry: (data: JournalEntryCreateRequest, key: string) => unwrap(apiClient.post<ApiEnvelope<JournalEntry>>(ENDPOINTS.JOURNAL_ENTRIES.CREATE, data, mutationHeaders(key))),
  updateJournalEntry: (id: string, data: JournalEntryUpdateRequest) => unwrap(apiClient.patch<ApiEnvelope<JournalEntry>>(ENDPOINTS.JOURNAL_ENTRIES.UPDATE(id), data, mutationHeaders(undefined, data.version))),
  deleteJournalEntry: (id: string) => translate(apiClient.delete<void>(ENDPOINTS.JOURNAL_ENTRIES.DELETE(id))),
  postJournalEntry: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<JournalEntry>>(ENDPOINTS.JOURNAL_ENTRIES.POST(id), command, mutationHeaders(command.transition_key, command.version))),
  reverseJournalEntry: (id: string, command: ReversalCommand) => unwrap(apiClient.post<ApiEnvelope<JournalEntry>>(ENDPOINTS.JOURNAL_ENTRIES.REVERSE(id), command, mutationHeaders(command.transition_key, command.version))),
  importJournalEntries: (command: BatchImportCommand, key: string) => unwrap(apiClient.post<ApiEnvelope<AccountingJob>>(ENDPOINTS.JOURNAL_ENTRIES.BATCH_IMPORT, command, mutationHeaders(key))),

  listAPInvoices: (filters: APInvoiceListQuery = {}) => unwrapList(apiClient.get<ApiListEnvelope<APInvoice>>(query(ENDPOINTS.AP_INVOICES.LIST, filters))),
  getAPInvoice: (id: string) => unwrap(apiClient.get<ApiEnvelope<APInvoice>>(ENDPOINTS.AP_INVOICES.DETAIL(id))),
  createAPInvoice: (data: APInvoiceCreateRequest, key: string) => unwrap(apiClient.post<ApiEnvelope<APInvoice>>(ENDPOINTS.AP_INVOICES.CREATE, data, mutationHeaders(key))),
  updateAPInvoice: (id: string, data: APInvoiceUpdateRequest) => unwrap(apiClient.patch<ApiEnvelope<APInvoice>>(ENDPOINTS.AP_INVOICES.UPDATE(id), data, mutationHeaders(undefined, data.version))),
  deleteAPInvoice: (id: string) => translate(apiClient.delete<void>(ENDPOINTS.AP_INVOICES.DELETE(id))),
  submitAPInvoice: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<APInvoice>>(ENDPOINTS.AP_INVOICES.SUBMIT(id), command, mutationHeaders(command.transition_key, command.version))),
  approveAPInvoice: (id: string, command: ApprovalCommand) => unwrap(apiClient.post<ApiEnvelope<APInvoice>>(ENDPOINTS.AP_INVOICES.APPROVE(id), command, mutationHeaders(command.transition_key, command.version))),
  rejectAPInvoice: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<APInvoice>>(ENDPOINTS.AP_INVOICES.REJECT(id), command, mutationHeaders(command.transition_key, command.version))),
  postAPInvoice: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<APInvoice>>(ENDPOINTS.AP_INVOICES.POST(id), command, mutationHeaders(command.transition_key, command.version))),
  cancelAPInvoice: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<APInvoice>>(ENDPOINTS.AP_INVOICES.CANCEL(id), command, mutationHeaders(command.transition_key, command.version))),
  apAging: (queryValues: AsOfDateQuery) => unwrap(apiClient.get<ApiEnvelope<AgingReport>>(query(ENDPOINTS.AP_INVOICES.AGING, queryValues))),

  listARInvoices: (filters: ARInvoiceListQuery = {}) => unwrapList(apiClient.get<ApiListEnvelope<ARInvoice>>(query(ENDPOINTS.AR_INVOICES.LIST, filters))),
  getARInvoice: (id: string) => unwrap(apiClient.get<ApiEnvelope<ARInvoice>>(ENDPOINTS.AR_INVOICES.DETAIL(id))),
  createARInvoice: (data: ARInvoiceCreateRequest, key: string) => unwrap(apiClient.post<ApiEnvelope<ARInvoice>>(ENDPOINTS.AR_INVOICES.CREATE, data, mutationHeaders(key))),
  updateARInvoice: (id: string, data: ARInvoiceUpdateRequest) => unwrap(apiClient.patch<ApiEnvelope<ARInvoice>>(ENDPOINTS.AR_INVOICES.UPDATE(id), data, mutationHeaders(undefined, data.version))),
  deleteARInvoice: (id: string) => translate(apiClient.delete<void>(ENDPOINTS.AR_INVOICES.DELETE(id))),
  postARInvoice: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<ARInvoice>>(ENDPOINTS.AR_INVOICES.POST(id), command, mutationHeaders(command.transition_key, command.version))),
  cancelARInvoice: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<ARInvoice>>(ENDPOINTS.AR_INVOICES.CANCEL(id), command, mutationHeaders(command.transition_key, command.version))),
  arAging: (queryValues: AsOfDateQuery) => unwrap(apiClient.get<ApiEnvelope<AgingReport>>(query(ENDPOINTS.AR_INVOICES.AGING, queryValues))),

  listPayments: (filters: PaymentListQuery = {}) => unwrapList(apiClient.get<ApiListEnvelope<Payment>>(query(ENDPOINTS.PAYMENTS.LIST, filters))),
  getPayment: (id: string) => unwrap(apiClient.get<ApiEnvelope<Payment>>(ENDPOINTS.PAYMENTS.DETAIL(id))),
  createPayment: (data: PaymentCreateRequest, key: string) => unwrap(apiClient.post<ApiEnvelope<Payment>>(ENDPOINTS.PAYMENTS.CREATE, data, mutationHeaders(key))),
  updatePayment: (id: string, data: PaymentUpdateRequest) => unwrap(apiClient.patch<ApiEnvelope<Payment>>(ENDPOINTS.PAYMENTS.UPDATE(id), data)),
  voidPayment: (id: string, command: TransitionCommand) => unwrap(apiClient.post<ApiEnvelope<Payment>>(ENDPOINTS.PAYMENTS.VOID(id), command, mutationHeaders(command.transition_key, command.version))),

  trialBalance: (queryValues: AsOfDateQuery) => unwrap(apiClient.get<ApiEnvelope<TrialBalance>>(query(ENDPOINTS.REPORTS.TRIAL_BALANCE, queryValues))),
  generalLedger: (queryValues: GeneralLedgerQuery) => unwrap(apiClient.get<ApiEnvelope<GeneralLedger>>(query(ENDPOINTS.REPORTS.GENERAL_LEDGER, queryValues))),
  balanceSheet: (queryValues: AsOfDateQuery) => unwrap(apiClient.get<ApiEnvelope<FinancialStatement>>(query(ENDPOINTS.REPORTS.BALANCE_SHEET, queryValues))),
  incomeStatement: (queryValues: DateRangeQuery) => unwrap(apiClient.get<ApiEnvelope<FinancialStatement>>(query(ENDPOINTS.REPORTS.INCOME_STATEMENT, queryValues))),
  cashFlow: (queryValues: DateRangeQuery) => unwrap(apiClient.get<ApiEnvelope<CashFlowStatement>>(query(ENDPOINTS.REPORTS.CASH_FLOW, queryValues))),
  generateReport: (command: ReportGenerationCommand, key: string) => unwrap(apiClient.post<ApiEnvelope<AccountingJob>>(ENDPOINTS.REPORTS.GENERATE, command, mutationHeaders(key))),
  getJob: (id: string) => unwrap(apiClient.get<ApiEnvelope<AccountingJob>>(ENDPOINTS.JOBS.DETAIL(id))),
  health: () => unwrap(apiClient.get<ApiEnvelope<AccountingHealth>>(ENDPOINTS.HEALTH)),
};

export function shouldPollJob(job: AccountingJob | undefined): boolean {
  return job?.status === 'queued' || job?.status === 'running' || job?.status === 'retrying';
}
