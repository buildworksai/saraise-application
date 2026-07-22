/** Canonical v2 browser contract for the tenant-scoped accounting core. */
import { z } from 'zod';

export type AccountType = 'asset' | 'liability' | 'equity' | 'revenue' | 'expense';
export type NormalBalance = 'debit' | 'credit';
export type CashFlowCategory = 'operating' | 'investing' | 'financing';
export type PostingPeriodStatus = 'open' | 'closed' | 'locked';
export type JournalEntryStatus = 'draft' | 'posted' | 'reversed';
export type APInvoiceStatus = 'draft' | 'submitted' | 'approved' | 'posted' | 'partially_paid' | 'paid' | 'cancelled';
export type ARInvoiceStatus = 'draft' | 'posted' | 'partially_paid' | 'paid' | 'overdue' | 'cancelled';
export type PaymentStatus = 'recorded' | 'voided';
export type PaymentMethod = 'cash' | 'check' | 'wire_transfer' | 'ach' | 'credit_card' | 'other';
export type JobStatus = 'queued' | 'running' | 'retrying' | 'succeeded' | 'failed' | 'cancelled';

export interface PaginationMeta {
  readonly page: number;
  readonly page_size: number;
  readonly total_pages: number;
  readonly count: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}
export interface ApiMeta { readonly correlation_id: string; readonly timestamp: string; readonly pagination?: PaginationMeta }
export interface ApiEnvelope<T> { readonly data: T; readonly meta: ApiMeta }
export interface ApiListEnvelope<T> { readonly data: readonly T[]; readonly meta: ApiMeta & { readonly pagination: PaginationMeta } }
export interface FieldError { readonly field: string; readonly code: string; readonly message: string }
export interface ApiError {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly detail?: string;
    readonly correlation_id?: string;
    readonly field_errors?: readonly FieldError[];
  };
}
export interface ListResult<T> { readonly items: readonly T[]; readonly pagination: PaginationMeta; readonly meta: ApiMeta }

export interface TransitionHistoryItem {
  readonly command: string;
  readonly from_status: string;
  readonly to_status: string;
  readonly actor_id: string;
  readonly occurred_at: string;
  readonly reason?: string;
  readonly correlation_id?: string;
}
export interface MutableRecord {
  readonly id: string;
  readonly tenant_id: string;
  readonly version: number;
  readonly created_by: string;
  readonly updated_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface Account extends MutableRecord {
  readonly code: string;
  readonly name: string;
  readonly account_type: AccountType;
  readonly normal_balance: NormalBalance;
  readonly parent: string | null;
  readonly parent_account_id?: string | null;
  readonly is_group: boolean;
  readonly is_active: boolean;
  readonly currency: string;
  readonly allow_multi_currency: boolean;
  readonly cash_flow_category: CashFlowCategory | null;
  readonly description: string;
  readonly is_deleted: boolean;
  readonly balance?: string;
}
export interface AccountCreateRequest {
  code: string; name: string; account_type: AccountType; normal_balance: NormalBalance;
  parent?: string | null; is_group?: boolean; is_active?: boolean; currency?: string;
  allow_multi_currency?: boolean; cash_flow_category?: CashFlowCategory | null; description?: string;
}
export type AccountUpdateRequest = Partial<AccountCreateRequest> & { version: number };
export interface AccountNode extends Account { readonly children: readonly AccountNode[] }

export interface PostingPeriod extends MutableRecord {
  readonly period_name: string; readonly start_date: string; readonly end_date: string;
  readonly fiscal_year: number; readonly status: PostingPeriodStatus;
  readonly closed_at: string | null; readonly closed_by: string | null;
  readonly locked_at: string | null; readonly locked_by: string | null;
  readonly transition_history: readonly TransitionHistoryItem[];
}
export interface PostingPeriodCreateRequest { period_name: string; start_date: string; end_date: string; fiscal_year: number }
export type PostingPeriodUpdateRequest = Partial<PostingPeriodCreateRequest> & { version: number };

export interface JournalLine {
  readonly id: string; readonly line_number: number; readonly account: string;
  readonly account_code?: string; readonly account_name?: string;
  readonly debit_amount: string; readonly credit_amount: string; readonly currency: string;
  readonly exchange_rate: string; readonly base_debit_amount: string; readonly base_credit_amount: string;
  readonly description: string; readonly cost_center: string; readonly dimension_values: Readonly<Record<string, string>>;
}
export interface JournalLineWriteRequest {
  line_number: number; account: string; debit_amount: string; credit_amount: string;
  currency: string; exchange_rate?: string; description?: string; cost_center?: string;
  dimension_values?: Readonly<Record<string, string>>;
}
export interface JournalEntry extends MutableRecord {
  readonly entry_number: string; readonly posting_date: string; readonly posting_period: string;
  readonly reference: string; readonly description: string; readonly status: JournalEntryStatus;
  readonly currency: string; readonly debit_total: string; readonly credit_total: string;
  readonly posted_at: string | null; readonly posted_by: string | null;
  readonly reversed_at: string | null; readonly reversed_by: string | null;
  readonly reversed_entry: string | null; readonly source_module: string; readonly source_reference: string;
  readonly transition_history: readonly TransitionHistoryItem[]; readonly lines: readonly JournalLine[];
  readonly is_deleted: boolean;
}
export interface JournalEntryCreateRequest {
  entry_number: string; posting_date: string; posting_period: string; reference?: string;
  description?: string; currency?: string; lines: readonly JournalLineWriteRequest[];
}
export type JournalEntryUpdateRequest = Partial<Omit<JournalEntryCreateRequest, 'lines'>> & { version: number; lines?: readonly JournalLineWriteRequest[] };

export interface InvoiceLine {
  readonly id: string; readonly line_number: number; readonly description: string; readonly account: string;
  readonly account_code?: string; readonly quantity: string; readonly unit_price: string;
  readonly tax_amount: string; readonly line_total: string; readonly cost_center: string;
  readonly dimension_values: Readonly<Record<string, string>>;
}
export interface InvoiceLineWriteRequest {
  line_number: number; description: string; account: string; quantity: string; unit_price: string;
  tax_amount?: string; cost_center?: string; dimension_values?: Readonly<Record<string, string>>;
}
export interface InvoiceBase extends MutableRecord {
  readonly invoice_number: string; readonly invoice_date: string; readonly due_date: string;
  readonly amount: string; readonly tax_amount: string; readonly total_amount: string; readonly paid_amount: string;
  readonly currency: string; readonly exchange_rate: string; readonly description: string;
  readonly journal_entry: string | null; readonly legacy_without_lines: boolean;
  readonly transition_history: readonly TransitionHistoryItem[]; readonly lines: readonly InvoiceLine[];
  readonly is_deleted: boolean;
}
export interface APInvoice extends InvoiceBase {
  readonly supplier_id: string; readonly status: APInvoiceStatus;
  readonly approved_at: string | null; readonly approved_by: string | null;
  readonly posted_at: string | null; readonly posted_by: string | null;
  readonly cancelled_at: string | null; readonly cancelled_by: string | null;
}
export interface ARInvoice extends InvoiceBase {
  readonly customer_id: string; readonly status: ARInvoiceStatus;
  readonly posted_at: string | null; readonly posted_by: string | null;
  readonly cancelled_at: string | null; readonly cancelled_by: string | null;
}
export interface APInvoiceCreateRequest {
  invoice_number: string; supplier_id: string; invoice_date: string; due_date: string;
  currency?: string; exchange_rate?: string; description?: string; tax_provenance?: Readonly<Record<string, string>>;
  lines: readonly InvoiceLineWriteRequest[];
}
export type APInvoiceUpdateRequest = Partial<Omit<APInvoiceCreateRequest, 'lines'>> & { version: number; lines?: readonly InvoiceLineWriteRequest[] };
export interface ARInvoiceCreateRequest {
  invoice_number: string; customer_id: string; invoice_date: string; due_date: string;
  currency?: string; exchange_rate?: string; description?: string; tax_provenance?: Readonly<Record<string, string>>;
  lines: readonly InvoiceLineWriteRequest[];
}
export type ARInvoiceUpdateRequest = Partial<Omit<ARInvoiceCreateRequest, 'lines'>> & { version: number; lines?: readonly InvoiceLineWriteRequest[] };

export interface Payment {
  readonly id: string; readonly tenant_id: string; readonly created_at: string; readonly updated_at: string;
  readonly created_by: string; readonly payment_date: string; readonly amount: string; readonly payment_method: PaymentMethod;
  readonly currency: string; readonly reference_number: string; readonly ap_invoice: string | null; readonly ar_invoice: string | null;
  readonly description: string; readonly status: PaymentStatus; readonly voided_at: string | null;
  readonly voided_by: string | null; readonly void_reason: string; readonly journal_entry: string | null;
  readonly reversal_journal_entry: string | null;
}
export interface PaymentCreateRequest {
  payment_date: string; amount: string; payment_method: PaymentMethod; currency?: string;
  reference_number?: string; ap_invoice?: string | null; ar_invoice?: string | null; description?: string;
}
export interface PaymentUpdateRequest { reference_number?: string; description?: string }

export interface TransitionCommand { transition_key: string; version: number; reason?: string }
export interface ApprovalCommand extends TransitionCommand { comments?: string }
export interface ReversalCommand extends TransitionCommand { posting_date: string; reason: string }
export interface BatchImportCommand { file_reference: string }
export interface ReportGenerationCommand { report_type: ReportType; parameters: Readonly<Record<string, string>> }

export interface ReportMeta { readonly period: { readonly start_date?: string; readonly end_date: string }; readonly currency: string; readonly generated_at: string; readonly correlation_id: string }
export interface ReportAmountRow { readonly label: string; readonly account_ids: readonly string[]; readonly amount: string; readonly comparison_amount?: string }
export interface TrialBalanceRow { readonly account_id: string; readonly account_code: string; readonly account_name: string; readonly debit: string; readonly credit: string; readonly balance: string; readonly journal_entry_ids: readonly string[] }
export interface TrialBalance { readonly meta: ReportMeta; readonly rows: readonly TrialBalanceRow[]; readonly debit_total: string; readonly credit_total: string; readonly balanced: boolean }
export interface LedgerRow { readonly journal_entry_id: string; readonly journal_line_id: string; readonly posting_date: string; readonly entry_number: string; readonly description: string; readonly debit: string; readonly credit: string; readonly running_balance: string; readonly source_module: string; readonly source_reference: string }
export interface GeneralLedger { readonly meta: ReportMeta; readonly account: Pick<Account, 'id' | 'code' | 'name' | 'currency'>; readonly opening_balance: string; readonly rows: readonly LedgerRow[]; readonly closing_balance: string }
export interface FinancialStatement { readonly meta: ReportMeta; readonly sections: readonly { readonly name: string; readonly rows: readonly ReportAmountRow[]; readonly total: string }[]; readonly total: string }
export interface CashFlowStatement extends FinancialStatement { readonly net_change: string; readonly unclassified_account_ids: readonly string[] }
export interface AgingBucket { readonly key: 'current' | '1_30' | '31_60' | '61_90' | 'over_90'; readonly label: string; readonly amount: string; readonly invoice_ids: readonly string[] }
export interface AgingReport { readonly as_of_date: string; readonly currency: string; readonly generated_at: string; readonly buckets: readonly AgingBucket[]; readonly total_outstanding: string; readonly correlation_id: string }
export type ReportType = 'trial-balance' | 'general-ledger' | 'balance-sheet' | 'income-statement' | 'cash-flow';
export interface AsOfDateQuery { as_of_date: string }
export interface DateRangeQuery { start_date: string; end_date: string }
export interface GeneralLedgerQuery extends DateRangeQuery { account_id: string; page?: number; page_size?: number }

export interface AccountingJob { readonly id: string; readonly operation: string; readonly status: JobStatus; readonly progress_percent: number | null; readonly result: Readonly<Record<string, unknown>> | null; readonly error_code: string | null; readonly correlation_id: string; readonly created_at: string; readonly updated_at: string }
export interface AccountingHealthCheck { readonly name: string; readonly status: 'healthy' | 'degraded' | 'unhealthy'; readonly code?: string; readonly latency_ms?: number }
export interface AccountingHealth { readonly status: 'healthy' | 'degraded' | 'unhealthy'; readonly module_version: string; readonly checks: readonly AccountingHealthCheck[] }

export interface CommonListQuery { page?: number; page_size?: number; search?: string; ordering?: string }
export interface AccountListQuery extends CommonListQuery { account_type?: AccountType; parent?: string; is_group?: boolean; is_active?: boolean }
export interface PostingPeriodListQuery extends CommonListQuery { status?: PostingPeriodStatus; fiscal_year?: number; date?: string }
export interface JournalEntryListQuery extends CommonListQuery { status?: JournalEntryStatus; posting_period?: string; start_date?: string; end_date?: string; source_module?: string }
export interface APInvoiceListQuery extends CommonListQuery { status?: APInvoiceStatus; supplier_id?: string; start_date?: string; end_date?: string; due_from?: string; due_to?: string; currency?: string }
export interface ARInvoiceListQuery extends CommonListQuery { status?: ARInvoiceStatus; customer_id?: string; start_date?: string; end_date?: string; due_from?: string; due_to?: string; currency?: string }
export interface PaymentListQuery extends CommonListQuery { status?: PaymentStatus; ap_invoice?: string; ar_invoice?: string; start_date?: string; end_date?: string; payment_method?: PaymentMethod }

const decimal = z.string().regex(/^\d+(\.\d{1,8})?$/, 'Enter a non-negative decimal amount.');
const money = z.string().regex(/^\d+(\.\d{1,2})?$/, 'Enter an amount with no more than two decimal places.');
const currency = z.string().regex(/^[A-Z]{3}$/, 'Use a three-letter uppercase ISO currency code.');
const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Use YYYY-MM-DD.');
const uuid = z.string().uuid();
const version = z.number().int().positive();
const dimensions = z.record(z.string());

export const accountCreateSchema = z.object({ code: z.string().trim().min(1).max(50), name: z.string().trim().min(1).max(255), account_type: z.enum(['asset', 'liability', 'equity', 'revenue', 'expense']), normal_balance: z.enum(['debit', 'credit']), parent: uuid.nullable().optional(), is_group: z.boolean().optional(), is_active: z.boolean().optional(), currency: currency.optional(), allow_multi_currency: z.boolean().optional(), cash_flow_category: z.enum(['operating', 'investing', 'financing']).nullable().optional(), description: z.string().max(5000).optional() });
export const accountUpdateSchema = accountCreateSchema.partial().extend({ version });
export const postingPeriodCreateSchema = z.object({ period_name: z.string().trim().min(1).max(50), start_date: date, end_date: date, fiscal_year: z.number().int().min(1900).max(9999) }).refine((value) => value.start_date <= value.end_date, { path: ['end_date'], message: 'End date must be on or after start date.' });
export const postingPeriodUpdateSchema = z.object({ period_name: z.string().trim().min(1).max(50).optional(), start_date: date.optional(), end_date: date.optional(), fiscal_year: z.number().int().min(1900).max(9999).optional(), version });
export const journalLineWriteSchema = z.object({ line_number: z.number().int().positive(), account: uuid, debit_amount: money, credit_amount: money, currency, exchange_rate: decimal.optional(), description: z.string().max(500).optional(), cost_center: z.string().max(100).optional(), dimension_values: dimensions.optional() }).refine((line) => (Number(line.debit_amount) > 0) !== (Number(line.credit_amount) > 0), { message: 'Exactly one of debit or credit must be greater than zero.' });
export const journalEntryCreateSchema = z.object({ entry_number: z.string().trim().min(1).max(50), posting_date: date, posting_period: uuid, reference: z.string().max(255).optional(), description: z.string().max(5000).optional(), currency: currency.optional(), lines: z.array(journalLineWriteSchema).min(2) });
export const journalEntryUpdateSchema = journalEntryCreateSchema.partial().extend({ version });
export const invoiceLineWriteSchema = z.object({ line_number: z.number().int().positive(), description: z.string().trim().min(1).max(500), account: uuid, quantity: decimal.refine((value) => Number(value) > 0, 'Quantity must be greater than zero.'), unit_price: money, tax_amount: money.optional(), cost_center: z.string().max(100).optional(), dimension_values: dimensions.optional() });
const invoiceBaseSchema = z.object({ invoice_number: z.string().trim().min(1).max(100), invoice_date: date, due_date: date, currency: currency.optional(), exchange_rate: decimal.optional(), description: z.string().max(5000).optional(), tax_provenance: dimensions.optional(), lines: z.array(invoiceLineWriteSchema).min(1) }).refine((value) => value.invoice_date <= value.due_date, { path: ['due_date'], message: 'Due date must be on or after invoice date.' });
export const apInvoiceCreateSchema = invoiceBaseSchema.and(z.object({ supplier_id: uuid }));
export const arInvoiceCreateSchema = invoiceBaseSchema.and(z.object({ customer_id: uuid }));
export const apInvoiceUpdateSchema = z.object({ invoice_number: z.string().trim().min(1).max(100).optional(), supplier_id: uuid.optional(), invoice_date: date.optional(), due_date: date.optional(), currency: currency.optional(), exchange_rate: decimal.optional(), description: z.string().max(5000).optional(), tax_provenance: dimensions.optional(), lines: z.array(invoiceLineWriteSchema).min(1).optional(), version });
export const arInvoiceUpdateSchema = z.object({ invoice_number: z.string().trim().min(1).max(100).optional(), customer_id: uuid.optional(), invoice_date: date.optional(), due_date: date.optional(), currency: currency.optional(), exchange_rate: decimal.optional(), description: z.string().max(5000).optional(), tax_provenance: dimensions.optional(), lines: z.array(invoiceLineWriteSchema).min(1).optional(), version });
export const paymentCreateSchema = z.object({ payment_date: date, amount: money.refine((value) => Number(value) > 0, 'Amount must be greater than zero.'), payment_method: z.enum(['cash', 'check', 'wire_transfer', 'ach', 'credit_card', 'other']), currency: currency.optional(), reference_number: z.string().max(100).optional(), ap_invoice: uuid.nullable().optional(), ar_invoice: uuid.nullable().optional(), description: z.string().max(5000).optional() }).refine((value) => Boolean(value.ap_invoice) !== Boolean(value.ar_invoice), { message: 'Choose exactly one AP or AR invoice.' });
export const paymentUpdateSchema = z.object({ reference_number: z.string().max(100).optional(), description: z.string().max(5000).optional() }).refine((value) => value.reference_number !== undefined || value.description !== undefined, 'Provide a reference or description change.');
export const transitionCommandSchema = z.object({ transition_key: z.string().min(8), version, reason: z.string().min(1).max(2000).optional() });
export const approvalCommandSchema = transitionCommandSchema.extend({ comments: z.string().max(2000).optional() });
export const reversalCommandSchema = transitionCommandSchema.extend({ posting_date: date, reason: z.string().min(1).max(2000) });
export const batchImportCommandSchema = z.object({ file_reference: z.string().trim().min(1).max(2048) });
export const reportGenerationCommandSchema = z.object({ report_type: z.enum(['trial-balance', 'general-ledger', 'balance-sheet', 'income-statement', 'cash-flow']), parameters: z.record(z.string()) });
export const asOfDateQuerySchema = z.object({ as_of_date: date });
export const dateRangeQuerySchema = z.object({ start_date: date, end_date: date }).refine((value) => value.start_date <= value.end_date, { path: ['end_date'], message: 'End date must be on or after start date.' });
export const generalLedgerQuerySchema = dateRangeQuerySchema.and(z.object({ account_id: uuid, page: z.number().int().positive().optional(), page_size: z.number().int().min(1).max(100).optional() }));

export const MODULE_API_PREFIX = '/api/v2/accounting-finance';
export const ENDPOINTS = {
  ACCOUNTS: { LIST: `${MODULE_API_PREFIX}/accounts/`, CREATE: `${MODULE_API_PREFIX}/accounts/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const, HIERARCHY: `${MODULE_API_PREFIX}/accounts/hierarchy/` },
  POSTING_PERIODS: { LIST: `${MODULE_API_PREFIX}/posting-periods/`, CREATE: `${MODULE_API_PREFIX}/posting-periods/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/posting-periods/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/posting-periods/${id}/` as const, CLOSE: (id: string) => `${MODULE_API_PREFIX}/posting-periods/${id}/close/` as const, REOPEN: (id: string) => `${MODULE_API_PREFIX}/posting-periods/${id}/reopen/` as const, LOCK: (id: string) => `${MODULE_API_PREFIX}/posting-periods/${id}/lock/` as const },
  JOURNAL_ENTRIES: { LIST: `${MODULE_API_PREFIX}/journal-entries/`, CREATE: `${MODULE_API_PREFIX}/journal-entries/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/journal-entries/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/journal-entries/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/journal-entries/${id}/` as const, POST: (id: string) => `${MODULE_API_PREFIX}/journal-entries/${id}/post/` as const, REVERSE: (id: string) => `${MODULE_API_PREFIX}/journal-entries/${id}/reverse/` as const, BATCH_IMPORT: `${MODULE_API_PREFIX}/journal-entries/batch-import/` },
  AP_INVOICES: { LIST: `${MODULE_API_PREFIX}/ap-invoices/`, CREATE: `${MODULE_API_PREFIX}/ap-invoices/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/` as const, SUBMIT: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/submit/` as const, APPROVE: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/approve/` as const, REJECT: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/reject/` as const, POST: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/post/` as const, CANCEL: (id: string) => `${MODULE_API_PREFIX}/ap-invoices/${id}/cancel/` as const, AGING: `${MODULE_API_PREFIX}/ap-invoices/aging/` },
  AR_INVOICES: { LIST: `${MODULE_API_PREFIX}/ar-invoices/`, CREATE: `${MODULE_API_PREFIX}/ar-invoices/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/ar-invoices/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/ar-invoices/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/ar-invoices/${id}/` as const, POST: (id: string) => `${MODULE_API_PREFIX}/ar-invoices/${id}/post/` as const, CANCEL: (id: string) => `${MODULE_API_PREFIX}/ar-invoices/${id}/cancel/` as const, AGING: `${MODULE_API_PREFIX}/ar-invoices/aging/` },
  PAYMENTS: { LIST: `${MODULE_API_PREFIX}/payments/`, CREATE: `${MODULE_API_PREFIX}/payments/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/payments/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/payments/${id}/` as const, VOID: (id: string) => `${MODULE_API_PREFIX}/payments/${id}/void/` as const },
  REPORTS: { TRIAL_BALANCE: `${MODULE_API_PREFIX}/reports/trial-balance/`, GENERAL_LEDGER: `${MODULE_API_PREFIX}/reports/general-ledger/`, BALANCE_SHEET: `${MODULE_API_PREFIX}/reports/balance-sheet/`, INCOME_STATEMENT: `${MODULE_API_PREFIX}/reports/income-statement/`, CASH_FLOW: `${MODULE_API_PREFIX}/reports/cash-flow/`, GENERATE: `${MODULE_API_PREFIX}/reports/generate/` },
  JOBS: { DETAIL: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/` as const },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const accountingQueryKeys = {
  root: ['accounting-finance'] as const,
  accounts: (query: AccountListQuery = {}) => [...accountingQueryKeys.root, 'accounts', query] as const,
  account: (id: string) => [...accountingQueryKeys.root, 'account', id] as const,
  hierarchy: () => [...accountingQueryKeys.root, 'hierarchy'] as const,
  periods: (query: PostingPeriodListQuery = {}) => [...accountingQueryKeys.root, 'periods', query] as const,
  period: (id: string) => [...accountingQueryKeys.root, 'period', id] as const,
  journals: (query: JournalEntryListQuery = {}) => [...accountingQueryKeys.root, 'journals', query] as const,
  journal: (id: string) => [...accountingQueryKeys.root, 'journal', id] as const,
  apInvoices: (query: APInvoiceListQuery = {}) => [...accountingQueryKeys.root, 'ap-invoices', query] as const,
  apInvoice: (id: string) => [...accountingQueryKeys.root, 'ap-invoice', id] as const,
  arInvoices: (query: ARInvoiceListQuery = {}) => [...accountingQueryKeys.root, 'ar-invoices', query] as const,
  arInvoice: (id: string) => [...accountingQueryKeys.root, 'ar-invoice', id] as const,
  payments: (query: PaymentListQuery = {}) => [...accountingQueryKeys.root, 'payments', query] as const,
  payment: (id: string) => [...accountingQueryKeys.root, 'payment', id] as const,
  report: (type: ReportType, query: object) => [...accountingQueryKeys.root, 'report', type, query] as const,
  aging: (kind: 'ap' | 'ar', asOfDate: string) => [...accountingQueryKeys.root, `${kind}-aging`, asOfDate] as const,
  job: (id: string) => [...accountingQueryKeys.root, 'job', id] as const,
  health: () => [...accountingQueryKeys.root, 'health'] as const,
};
