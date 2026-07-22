/** Typed public contract for the governed bank-reconciliation v2 API. */

export type UUID = string;
export type DecimalString = string;
export type ISODate = string;
export type ISODateTime = string;

export type AccountType = "checking" | "savings" | "credit" | "cash" | "other";
export type ImportSource = "file" | "manual" | "bank_feed";
export type ParserFormat = "csv" | "ofx" | "qif" | "bai2" | "mt940" | "camt053" | "manual";
export type ImportStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";
export type AsyncJobStatus =
  "queued" | "running" | "succeeded" | "failed" | "cancelled" | "timed_out" | "retrying";
export type StatementStatus = "imported" | "reconciling" | "reconciled" | "void";
export type TransactionType = "debit" | "credit";
export type MatchStatus = "unmatched" | "proposed" | "matched" | "excluded";
export type RuleType =
  "exact" | "date_window" | "reference" | "amount_tolerance" | "counterparty" | "extension";
export type ReconciliationStatus = "draft" | "in_progress" | "review" | "finalized" | "void";
export type ReconciliationMatchType =
  "auto" | "manual" | "one_to_many" | "many_to_one" | "adjustment";
export type ReconciliationMatchStatus = "proposed" | "confirmed" | "rejected" | "reversed";
export type MatchLineSide = "bank" | "ledger";
export type LedgerEntryType = "payment" | "journal_line" | "deposit" | "other";

export interface PaginationMeta {
  page: number;
  page_size: number;
  total_pages: number;
  count: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface ApiMeta {
  correlation_id: string;
  timestamp: ISODateTime;
}

export interface ApiV2Response<T> {
  data: T;
  meta: ApiMeta;
}

export interface ApiV2Collection<T> {
  data: T[];
  meta: ApiMeta & { pagination: PaginationMeta };
}

export interface ApiV2ErrorDetail {
  [field: string]: string | string[] | ApiV2ErrorDetail;
}
export interface ApiV2Error {
  error: { code: string; message: string; detail: ApiV2ErrorDetail; correlation_id: string };
}

export type AllowedAction =
  | "read"
  | "create"
  | "update"
  | "archive"
  | "void"
  | "retry"
  | "cancel"
  | "review"
  | "finalize"
  | "export"
  | "confirm"
  | "reverse";

export interface BankAccount {
  id: UUID;
  masked_account_number: string;
  account_number_last4: string;
  bank_name: string;
  account_name: string;
  account_type: AccountType;
  currency: string;
  bank_identifier: string;
  ledger_account_id: UUID | null;
  opening_balance: DecimalString;
  opening_balance_date: ISODate | null;
  is_active: boolean;
  archived_at: ISODateTime | null;
  last_statement_date: ISODate | null;
  statement_count: number;
  reconciliation_count: number;
  unreconciled_count: number;
  active_session_count: number;
  allowed_actions?: AllowedAction[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface BankAccountCreate {
  account_number: string;
  bank_name: string;
  account_name: string;
  account_type: AccountType;
  currency: string;
  bank_identifier?: string;
  ledger_account_id?: UUID | null;
  opening_balance?: DecimalString;
  opening_balance_date?: ISODate | null;
}
export type BankAccountUpdate = Pick<BankAccountCreate, "bank_name" | "account_name"> &
  Partial<Pick<BankAccountCreate, "account_type" | "bank_identifier" | "ledger_account_id">>;
export interface BankAccountFilters extends PageFilters {
  search?: string;
  is_active?: boolean;
  account_type?: AccountType;
  currency?: string;
  ordering?:
    "bank_name" | "-bank_name" | "account_name" | "-account_name" | "created_at" | "-created_at";
}

export interface StatementImportSummary {
  id: UUID;
  status: ImportStatus;
  file_format: ParserFormat;
  source_filename: string;
  rows_received: number;
  rows_imported: number;
  rows_rejected: number;
}
export interface BankStatement {
  id: UUID;
  bank_account: UUID;
  account?: BankAccount;
  statement_import: StatementImportSummary | null;
  statement_reference: string;
  period_start: ISODate;
  period_end: ISODate;
  statement_date: ISODate;
  opening_balance: DecimalString;
  closing_balance: DecimalString;
  transaction_total: DecimalString;
  calculated_closing_balance: DecimalString;
  balance_variance: DecimalString;
  status: StatementStatus;
  is_reconciled: boolean;
  reconciled_at: ISODateTime | null;
  transaction_count: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
export interface ManualTransactionInput {
  transaction_date: ISODate;
  value_date?: ISODate | null;
  description: string;
  amount: DecimalString;
  reference_number?: string;
  counterparty_name?: string;
}
export interface ManualStatementCreate {
  bank_account: UUID;
  statement_reference: string;
  period_start: ISODate;
  period_end: ISODate;
  opening_balance: DecimalString;
  closing_balance: DecimalString;
  transactions: ManualTransactionInput[];
}
export interface StatementFilters extends PageFilters {
  bank_account?: UUID;
  status?: StatementStatus;
  period_start_after?: ISODate;
  period_end_before?: ISODate;
  has_variance?: boolean;
  ordering?: "period_end" | "-period_end" | "created_at" | "-created_at";
}

export interface MatchHistoryEntry {
  id: UUID;
  status: ReconciliationMatchStatus;
  match_type: ReconciliationMatchType;
  allocated_amount: DecimalString;
  created_at: ISODateTime;
}
export interface BankTransaction {
  id: UUID;
  bank_statement: UUID;
  sequence_number: number;
  external_id: string;
  transaction_date: ISODate;
  value_date: ISODate | null;
  description: string;
  amount: DecimalString;
  transaction_type: TransactionType;
  running_balance: DecimalString | null;
  reference_number: string;
  counterparty_name: string;
  counterparty_account_masked: string;
  match_status: MatchStatus;
  is_reconciled: boolean;
  matched_payment_id: UUID | null;
  source_data: Record<string, string | number | boolean | null>;
  source: ImportSource;
  match_history?: MatchHistoryEntry[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
export type ManualTransactionUpdate = ManualTransactionInput;
export interface TransactionFilters extends PageFilters {
  bank_statement?: UUID;
  bank_account?: UUID;
  match_status?: MatchStatus;
  transaction_type?: TransactionType;
  date_after?: ISODate;
  date_before?: ISODate;
  search?: string;
  ordering?: "transaction_date" | "-transaction_date" | "amount" | "-amount";
}
export interface ReasonAction {
  reason: string;
}
export interface IdempotentAction {
  idempotency_key: string;
}
export interface IdempotentReasonAction extends ReasonAction, IdempotentAction {}

export interface AsyncJobSummary {
  id: UUID;
  status: AsyncJobStatus;
  task_name: string;
  attempts: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
export interface StatementImport {
  id: UUID;
  bank_account: UUID;
  source: ImportSource;
  file_format: ParserFormat;
  source_document_id: UUID | null;
  source_filename: string;
  content_sha256: string;
  mapping: Record<string, string>;
  status: ImportStatus;
  idempotency_key: string;
  async_job: AsyncJobSummary | null;
  rows_received: number;
  rows_imported: number;
  rows_rejected: number;
  error_code: string;
  error_detail: ApiV2ErrorDetail;
  started_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  statement_id: UUID | null;
  correlation_id?: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
export interface StatementImportCreate {
  bank_account: UUID;
  file: File;
  file_format: Exclude<ParserFormat, "manual">;
  mapping?: Record<string, string>;
  idempotency_key: string;
}
export interface AcceptedImport {
  import: StatementImport;
  job: AsyncJobSummary;
}
export interface ImportFilters extends PageFilters {
  bank_account?: UUID;
  file_format?: ParserFormat;
  status?: ImportStatus;
  created_after?: ISODate;
  created_before?: ISODate;
}

export interface RuleConfiguration {
  date_window_days?: number;
  amount_tolerance?: DecimalString;
  reference_normalization?: string;
  counterparty_pattern?: string;
  [namespacedKey: `${string}.${string}`]: string | number | boolean | undefined;
}
export interface MatchingRule {
  id: UUID;
  name: string;
  description: string;
  rule_type: RuleType;
  priority: number;
  configuration: RuleConfiguration;
  auto_confirm: boolean;
  minimum_score: DecimalString;
  extension_key: string;
  is_active: boolean;
  usage_count: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
export type MatchingRuleCreate = Pick<
  MatchingRule,
  | "name"
  | "description"
  | "rule_type"
  | "priority"
  | "configuration"
  | "auto_confirm"
  | "minimum_score"
  | "extension_key"
>;
export type MatchingRuleUpdate = Partial<MatchingRuleCreate>;
export interface RuleFilters extends PageFilters {
  is_active?: boolean;
  rule_type?: RuleType;
  search?: string;
}

export interface TransitionEvidence {
  command: string;
  from: ReconciliationStatus;
  to: ReconciliationStatus;
  actor_id: UUID;
  occurred_at: ISODateTime;
  reason?: string;
}
export interface ReconciliationSession {
  id: UUID;
  bank_account: UUID;
  bank_statement: UUID;
  reconciliation_date: ISODate;
  status: ReconciliationStatus;
  statement_balance: DecimalString;
  ledger_balance: DecimalString;
  matched_amount: DecimalString;
  unmatched_amount: DecimalString;
  difference: DecimalString;
  tolerance: DecimalString;
  notes: string;
  reviewed_by_id: UUID | null;
  finalized_by_id: UUID | null;
  reviewed_at: ISODateTime | null;
  finalized_at: ISODateTime | null;
  transition_history: TransitionEvidence[];
  match_count: number;
  allowed_actions?: AllowedAction[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
  summary?: ReconciliationSummary;
  matches?: ReconciliationMatch[];
}
export interface ReconciliationCreate {
  bank_account: UUID;
  bank_statement: UUID;
  reconciliation_date: ISODate;
  ledger_balance: DecimalString;
  tolerance: DecimalString;
  notes?: string;
  idempotency_key: string;
}
export interface ReconciliationFilters extends PageFilters {
  bank_account?: UUID;
  bank_statement?: UUID;
  status?: ReconciliationStatus;
  date_after?: ISODate;
  date_before?: ISODate;
  has_difference?: boolean;
  finalized?: boolean;
}
export interface ReconciliationSummary {
  statement_balance: DecimalString;
  ledger_balance: DecimalString;
  matched_amount: DecimalString;
  unmatched_amount: DecimalString;
  difference: DecimalString;
  tolerance: DecimalString;
  proposed_count: number;
  unmatched_count: number;
  excluded_count: number;
  guard_failures: string[];
}
export interface ScoreFactors {
  amount: DecimalString;
  reference: DecimalString;
  date: DecimalString;
  counterparty: DecimalString;
}
export interface ReconciliationMatchLine {
  id: UUID;
  side: MatchLineSide;
  bank_transaction: UUID | null;
  ledger_entry_id: UUID | null;
  ledger_entry_type: LedgerEntryType;
  allocated_amount: DecimalString;
  currency: string;
  ledger_document_number?: string;
  ledger_description?: string;
  ledger_date?: ISODate;
}
export interface ReconciliationMatch {
  id: UUID;
  reconciliation: UUID;
  match_type: ReconciliationMatchType;
  status: ReconciliationMatchStatus;
  score: DecimalString | null;
  rule: UUID | null;
  explanation: ScoreFactors;
  matched_at: ISODateTime | null;
  reversal_reason: string;
  lines: ReconciliationMatchLine[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
export interface MatchLineCreate {
  side: MatchLineSide;
  bank_transaction?: UUID;
  ledger_entry_id?: UUID;
  ledger_entry_type?: LedgerEntryType;
  allocated_amount: DecimalString;
  currency: string;
}
export interface ManualMatchCreate {
  match_type: Exclude<ReconciliationMatchType, "auto">;
  lines: MatchLineCreate[];
}
export interface CandidateResult {
  generated: number;
  auto_confirmed: number;
  matches: ReconciliationMatch[];
}

export interface PageFilters {
  page?: number;
  page_size?: number;
}
export interface HealthStatus {
  status: "healthy" | "degraded" | "unavailable";
  components: Record<string, "available" | "degraded" | "not_configured" | "unavailable">;
}

export const BANK_RECONCILIATION_PERMISSIONS = {
  ACCOUNT_READ: "bank_reconciliation.account:read",
  ACCOUNT_CREATE: "bank_reconciliation.account:create",
  ACCOUNT_UPDATE: "bank_reconciliation.account:update",
  ACCOUNT_ARCHIVE: "bank_reconciliation.account:archive",
  STATEMENT_READ: "bank_reconciliation.statement:read",
  STATEMENT_CREATE: "bank_reconciliation.statement:create",
  TRANSACTION_READ: "bank_reconciliation.transaction:read",
  IMPORT_CREATE: "bank_reconciliation.import:create",
  RULE_READ: "bank_reconciliation.rule:read",
  RECONCILIATION_READ: "bank_reconciliation.reconciliation:read",
} as const;

export const MODULE_API_PREFIX = "/api/v2/bank-reconciliation" as const;
const collection = (resource: string) => `${MODULE_API_PREFIX}/${resource}/` as const;
const detail = (resource: string, id: UUID) => `${MODULE_API_PREFIX}/${resource}/${id}/` as const;
export const ENDPOINTS = {
  ACCOUNTS: {
    LIST: collection("accounts"),
    CREATE: collection("accounts"),
    DETAIL: (id: UUID) => detail("accounts", id),
    UPDATE: (id: UUID) => detail("accounts", id),
    ARCHIVE: (id: UUID) => detail("accounts", id),
  },
  STATEMENTS: {
    LIST: collection("statements"),
    CREATE: collection("statements"),
    DETAIL: (id: UUID) => detail("statements", id),
    VOID: (id: UUID) => `${detail("statements", id)}void/` as const,
    TRANSACTIONS: (id: UUID) => `${detail("statements", id)}transactions/` as const,
  },
  TRANSACTIONS: {
    LIST: collection("transactions"),
    DETAIL: (id: UUID) => detail("transactions", id),
    UPDATE: (id: UUID) => detail("transactions", id),
    EXCLUDE: (id: UUID) => `${detail("transactions", id)}exclude/` as const,
    RESTORE: (id: UUID) => `${detail("transactions", id)}restore/` as const,
  },
  IMPORTS: {
    LIST: collection("imports"),
    CREATE: collection("imports"),
    DETAIL: (id: UUID) => detail("imports", id),
    RETRY: (id: UUID) => `${detail("imports", id)}retry/` as const,
    CANCEL: (id: UUID) => `${detail("imports", id)}cancel/` as const,
  },
  RULES: {
    LIST: collection("rules"),
    CREATE: collection("rules"),
    DETAIL: (id: UUID) => detail("rules", id),
    UPDATE: (id: UUID) => detail("rules", id),
    DELETE: (id: UUID) => detail("rules", id),
    ACTIVATE: (id: UUID) => `${detail("rules", id)}activate/` as const,
    DEACTIVATE: (id: UUID) => `${detail("rules", id)}deactivate/` as const,
  },
  RECONCILIATIONS: {
    LIST: collection("reconciliations"),
    CREATE: collection("reconciliations"),
    DETAIL: (id: UUID) => detail("reconciliations", id),
    START: (id: UUID) => `${detail("reconciliations", id)}start/` as const,
    GENERATE_CANDIDATES: (id: UUID) =>
      `${detail("reconciliations", id)}generate-candidates/` as const,
    MATCHES: (id: UUID) => `${detail("reconciliations", id)}matches/` as const,
    SUBMIT_REVIEW: (id: UUID) => `${detail("reconciliations", id)}submit-review/` as const,
    RETURN_TO_WORK: (id: UUID) => `${detail("reconciliations", id)}return-to-work/` as const,
    FINALIZE: (id: UUID) => `${detail("reconciliations", id)}finalize/` as const,
    VOID: (id: UUID) => `${detail("reconciliations", id)}void/` as const,
    REPORT: (id: UUID, format: "csv" | "pdf" = "csv") =>
      `${detail("reconciliations", id)}report/?format=${format}` as const,
  },
  MATCHES: {
    DETAIL: (id: UUID) => detail("matches", id),
    CONFIRM: (id: UUID) => `${detail("matches", id)}confirm/` as const,
    REJECT: (id: UUID) => `${detail("matches", id)}reject/` as const,
    REVERSE: (id: UUID) => `${detail("matches", id)}reverse/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/` as const,
} as const;

export const ROUTES = {
  ACCOUNTS: "/bank-reconciliation/accounts",
  ACCOUNT_CREATE: "/bank-reconciliation/accounts/new",
  ACCOUNT_DETAIL: (id: UUID) => `/bank-reconciliation/accounts/${id}`,
  ACCOUNT_EDIT: (id: UUID) => `/bank-reconciliation/accounts/${id}/edit`,
  STATEMENTS: "/bank-reconciliation/statements",
  STATEMENT_IMPORT: "/bank-reconciliation/statements/import",
  STATEMENT_CREATE: "/bank-reconciliation/statements/new",
  STATEMENT_DETAIL: (id: UUID) => `/bank-reconciliation/statements/${id}`,
  TRANSACTION_DETAIL: (id: UUID) => `/bank-reconciliation/transactions/${id}`,
  TRANSACTION_EDIT: (id: UUID) => `/bank-reconciliation/transactions/${id}/edit`,
  RECONCILIATIONS: "/bank-reconciliation/reconciliations",
  RECONCILIATION_CREATE: "/bank-reconciliation/reconciliations/new",
  RECONCILIATION_DETAIL: (id: UUID) => `/bank-reconciliation/reconciliations/${id}`,
  RECONCILIATION_WORKSPACE: (id: UUID) => `/bank-reconciliation/reconciliations/${id}/workspace`,
  RULES: "/bank-reconciliation/rules",
  RULE_CREATE: "/bank-reconciliation/rules/new",
  RULE_DETAIL: (id: UUID) => `/bank-reconciliation/rules/${id}`,
  RULE_EDIT: (id: UUID) => `/bank-reconciliation/rules/${id}/edit`,
  IMPORTS: "/bank-reconciliation/imports",
  IMPORT_DETAIL: (id: UUID) => `/bank-reconciliation/imports/${id}`,
} as const;

const sorted = (filters?: object): string =>
  JSON.stringify(filters ?? {}, Object.keys(filters ?? {}).sort()) ?? "{}";
export const QUERY_KEYS = {
  accounts: {
    all: ["bank-reconciliation", "accounts"] as const,
    list: (filters?: BankAccountFilters) =>
      ["bank-reconciliation", "accounts", "list", sorted(filters)] as const,
    detail: (id: UUID) => ["bank-reconciliation", "accounts", id] as const,
  },
  statements: {
    all: ["bank-reconciliation", "statements"] as const,
    list: (filters?: StatementFilters) =>
      ["bank-reconciliation", "statements", "list", sorted(filters)] as const,
    detail: (id: UUID) => ["bank-reconciliation", "statements", id] as const,
  },
  transactions: {
    all: ["bank-reconciliation", "transactions"] as const,
    list: (filters?: TransactionFilters) =>
      ["bank-reconciliation", "transactions", "list", sorted(filters)] as const,
    detail: (id: UUID) => ["bank-reconciliation", "transactions", id] as const,
  },
  imports: {
    all: ["bank-reconciliation", "imports"] as const,
    list: (filters?: ImportFilters) =>
      ["bank-reconciliation", "imports", "list", sorted(filters)] as const,
    detail: (id: UUID) => ["bank-reconciliation", "imports", id] as const,
  },
  rules: {
    all: ["bank-reconciliation", "rules"] as const,
    list: (filters?: RuleFilters) =>
      ["bank-reconciliation", "rules", "list", sorted(filters)] as const,
    detail: (id: UUID) => ["bank-reconciliation", "rules", id] as const,
  },
  reconciliations: {
    all: ["bank-reconciliation", "reconciliations"] as const,
    list: (filters?: ReconciliationFilters) =>
      ["bank-reconciliation", "reconciliations", "list", sorted(filters)] as const,
    detail: (id: UUID) => ["bank-reconciliation", "reconciliations", id] as const,
  },
  matches: { detail: (id: UUID) => ["bank-reconciliation", "matches", id] as const },
} as const;
