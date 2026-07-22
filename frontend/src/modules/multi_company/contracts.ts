/** Governed frontend contract for the multi-company v2 API. */

export type UUID = string;
export type DecimalString = string;
export type IsoDate = string;
export type IsoDateTime = string;

export interface ApiMeta { correlation_id: string; timestamp: IsoDateTime }
export interface PaginationMeta { count: number; page: number; page_size: number; total_pages: number; has_next: boolean; has_previous: boolean }
export interface ApiEnvelope<T> { data: T; meta: ApiMeta }
export interface PaginatedEnvelope<T> { data: readonly T[]; meta: ApiMeta & { pagination: PaginationMeta } }
export interface GovernedFieldError { field: string; code: string; message: string }
export interface GovernedErrorBody { error: { code: string; message: string; correlation_id: string; details?: readonly GovernedFieldError[] } }

export type AllowedCommand =
  | 'update' | 'delete' | 'deactivate' | 'reactivate' | 'submit' | 'approve'
  | 'dispute' | 'resolve' | 'post' | 'retry_posting' | 'cancel' | 'reverse'
  | 'execute' | 'retry' | 'publish' | 'calculate' | 'activate' | 'rollback'
  | 'import' | 'export' | 'grant' | 'revoke';
export interface DenialReason { command: AllowedCommand; code: string; message: string; prerequisite?: string }
export interface AuditFields { id: UUID; created_at: IsoDateTime; correlation_id: string }
export interface MutableFields extends AuditFields { created_by: string; updated_by: string; updated_at: IsoDateTime; version: number; is_deleted: boolean; deleted_at: IsoDateTime | null }
export interface CommandAware { allowed_commands: readonly AllowedCommand[]; denial_reasons: Readonly<Record<string, string>> }

export interface Company extends MutableFields, CommandAware {
  company_code: string; company_name: string; legal_name: string; tax_id: string | null;
  currency: string; fiscal_year_start_month: number; parent_company: UUID | null;
  parent_company_name?: string | null; consolidation_group: string; ownership_percentage: DecimalString | null;
  address: string; is_active: boolean; is_holding: boolean;
}
export type CompanyRole = 'viewer' | 'operator' | 'approver' | 'controller' | 'tax_admin';
export interface CompanyAccessGrant extends MutableFields, CommandAware { company: UUID; company_name?: string; subject_id: string; role: CompanyRole; valid_from: IsoDateTime; valid_until: IsoDateTime | null; granted_by: string; revoked_by: string; revoked_at: IsoDateTime | null }
export interface CompanyHierarchyNode { id: UUID; company_code: string; company_name: string; is_active: boolean; depth: number; children: readonly CompanyHierarchyNode[] }
export type CompanyHierarchy = readonly CompanyHierarchyNode[];

export type TransactionType = 'sale' | 'purchase' | 'service' | 'loan' | 'transfer' | 'dividend' | 'cost_allocation';
export type TransactionStatus = 'draft' | 'pending_approval' | 'approved' | 'posting' | 'posted' | 'posting_failed' | 'disputed' | 'eliminated' | 'cancelled' | 'expired';
export type ApprovalSide = 'source' | 'target';
export interface TransitionEvidence { command: string; from_status: string; to_status: string; actor_id: string; correlation_id: string; occurred_at: IsoDateTime }
export interface IntercompanyApproval extends AuditFields { transaction: UUID; side: ApprovalSide; attempt: number; approver_id: string; decision: 'approved' | 'rejected'; reason: string; workflow_reference: string; decided_at: IsoDateTime }
export interface IntercompanyTransaction extends MutableFields, CommandAware {
  reference: string; source_company: UUID; source_company_name?: string; target_company: UUID; target_company_name?: string;
  transaction_type: TransactionType; product_category: string; original_amount: DecimalString; amount: DecimalString;
  currency: string; exchange_rate: DecimalString | null; target_amount: DecimalString | null; description: string;
  transaction_date: IsoDate; status: TransactionStatus; transfer_pricing_rule: UUID | null;
  transfer_pricing_snapshot: TransferPricingSnapshot | null; source_journal_id: UUID | null; target_journal_id: UUID | null;
  posted_date: IsoDate | null; cancellation_reason: string; dispute_reason: string; failure_code: string; failure_detail: string;
  job_id: UUID | null; transition_history: readonly TransitionEvidence[]; approvals: readonly IntercompanyApproval[];
}
export interface TransferPricingSnapshot { rule_id: UUID; rule_key: UUID; rule_version: number; method: PricingMethod; formula: string; calculated_amount: DecimalString; rounding: string }
export interface ReconciliationRow { transaction_id: UUID; reference: string; source_company_id: UUID; target_company_id: UUID; currency: string; source_amount: DecimalString; target_amount: DecimalString | null; variance: DecimalString; status: TransactionStatus }

export type ConsolidationStatus = 'draft' | 'queued' | 'running' | 'completed' | 'failed' | 'approved' | 'published' | 'cancelled';
export type TranslationMethod = 'current_rate' | 'temporal' | 'monetary_non_monetary';
export interface ConsolidationRun extends MutableFields, CommandAware { name: string; consolidation_group: string; period_start: IsoDate; period_end: IsoDate; reporting_currency: string; translation_method: TranslationMethod; status: ConsolidationStatus; total_companies: number; total_eliminations: number; elimination_total: DecimalString; minority_interest_total: DecimalString; job_id: UUID | null; started_at: IsoDateTime | null; completed_at: IsoDateTime | null; approved_at: IsoDateTime | null; published_at: IsoDateTime | null; approved_by: string; published_by: string; failure_code: string; failure_step: string; failure_detail: string; report_snapshot: ConsolidatedReport | null; transition_history: readonly TransitionEvidence[] }
export type EliminationType = 'intercompany_balance' | 'intercompany_revenue' | 'intercompany_expense' | 'intercompany_receivable' | 'intercompany_payable' | 'unrealized_profit' | 'intercompany_dividend' | 'equity_investment' | 'minority_interest';
export interface EliminationEntry extends AuditFields { created_by: string; consolidation_run: UUID; elimination_type: EliminationType; source_company: UUID; target_company: UUID; debit_account: string; credit_account: string; amount: DecimalString; currency: string; description: string; source_transaction: UUID | null; is_auto_generated: boolean; rule_key: string; sequence: number }
export interface ConsolidatedReport { schema_version: string; run_id: UUID; reporting_currency: string; period_start: IsoDate; period_end: IsoDate; companies: readonly UUID[]; trial_balance: readonly { company_id: UUID; account: string; debit: DecimalString; credit: DecimalString }[]; elimination_total: DecimalString; minority_interest_total: DecimalString }

export type PricingMethod = 'cost_plus' | 'resale_minus' | 'comparable_uncontrolled' | 'transactional_net_margin' | 'profit_split' | 'extension';
export interface PricingParameters { base_cost?: DecimalString; resale_price?: DecimalString; comparable_price?: DecimalString; operating_cost?: DecimalString; allocation_weight?: DecimalString }
export interface TransferPricingRule extends MutableFields, CommandAware { rule_key: UUID; rule_version: number; name: string; source_company: UUID; target_company: UUID; product_category: string; transaction_type: TransactionType; pricing_method: PricingMethod; extension_key: string; markup_percentage: DecimalString | null; margin_range_min: DecimalString | null; margin_range_max: DecimalString | null; parameters: PricingParameters; effective_from: IsoDate; effective_to: IsoDate | null; is_active: boolean; documentation: string; supersedes: UUID | null }
export interface TransferPriceScenario { method: PricingMethod; amount: DecimalString; parameters: PricingParameters; extension_key?: string }
export interface TransferPriceResult { rule_id: UUID | null; rule_version: number | null; pricing_method: PricingMethod; amount: DecimalString; formula: string; rounding_mode: string; precision: number; evidence: Readonly<Record<string, string | number | boolean | null>> }

export type RuntimeEnvironment = 'development' | 'staging' | 'production';
export type ConfigurationStatus = 'draft' | 'active' | 'superseded' | 'rolled_back';
export interface RolloutPolicy { enabled: boolean; tenant_cohorts: readonly string[]; roles: readonly string[]; percentage: number }
export interface MultiCompanySettings { draft_expiry_hours: number; minimum_consolidation_company_count: number; permitted_translation_methods: readonly TranslationMethod[]; permitted_transaction_types: readonly TransactionType[]; permitted_pricing_methods: readonly PricingMethod[]; maximum_transaction_amount_by_currency: Readonly<Record<string, DecimalString>>; approval_sides: readonly ApprovalSide[]; transfer_pricing_tolerance_min: DecimalString; transfer_pricing_tolerance_max: DecimalString; allow_consolidation_overlap: boolean; rounding_mode: 'ROUND_HALF_EVEN' | 'ROUND_HALF_UP'; money_precision: number; feature_flags: Readonly<Record<string, boolean>>; rollout: { roles: readonly string[]; cohorts: readonly string[] }; extension_enablement_keys: readonly string[]; notification_policy: { approval: boolean; dispute: boolean; failure: boolean; completion: boolean }; job_max_retries: number; job_timeout_seconds: number; default_currency: string; default_fiscal_year_start_month: number; ledger_accounts: { intercompany_receivable: string; intercompany_payable: string; intercompany_revenue: string; intercompany_expense: string }; elimination_accounts: { debit: string; credit: string } }
export interface ConfigurationVersion extends AuditFields, CommandAware { created_by: string; environment: RuntimeEnvironment; version: number; status: ConfigurationStatus; schema_version: string; settings: MultiCompanySettings; change_summary: string; supersedes: UUID | null; activated_by: string; activated_at: IsoDateTime | null }
export interface ConfigurationImpact { valid: boolean; changed_keys: readonly string[]; affected_companies: number; affected_draft_transactions: number; warnings: readonly string[] }
export interface SignedConfigurationExport { format: 'saraise.multi-company.configuration'; format_version: '1.0'; environment: RuntimeEnvironment; schema_version: string; source_version: number; settings: MultiCompanySettings; change_summary: string; signature: string }
export interface AsyncJob { id: UUID; command: string; status: 'queued' | 'running' | 'retrying' | 'succeeded' | 'failed' | 'cancelled' | 'timed_out'; attempts: number; result: unknown; error_message: string; correlation_id: string; started_at: IsoDateTime | null; completed_at: IsoDateTime | null; created_at: IsoDateTime; updated_at: IsoDateTime }
export interface HealthStatus { status: 'healthy' | 'degraded' | 'unhealthy'; checked_at: IsoDateTime; checks: Readonly<Record<string, string>> }
export interface ExtensionCatalogEntry { key: string; version: string; spi_version: string; installed: boolean; entitled: boolean; feature_enabled: boolean; access_allowed: boolean; compatible: boolean; healthy: boolean; available: boolean; locked: boolean; unavailable_reason: string }

export interface PageFilters { page?: number; page_size?: number; ordering?: string; search?: string }
export interface CompanyFilters extends PageFilters { company_code?: string; is_active?: boolean; parent_company_id?: UUID; consolidation_group?: string; currency?: string }
export interface AccessGrantFilters extends PageFilters { company_id?: UUID; subject_id?: string; role?: CompanyRole; active_at?: IsoDateTime }
export interface TransactionFilters extends PageFilters { source_company_id?: UUID; target_company_id?: UUID; transaction_type?: TransactionType; status?: TransactionStatus; currency?: string; date_from?: IsoDate; date_to?: IsoDate }
export interface ReconciliationFilters extends PageFilters { source_company_id?: UUID; target_company_id?: UUID; currency?: string; period_start?: IsoDate; period_end?: IsoDate; variance_status?: 'matched' | 'variance' }
export interface ConsolidationFilters extends PageFilters { consolidation_group?: string; status?: ConsolidationStatus; period_start?: IsoDate; period_end?: IsoDate; reporting_currency?: string }
export interface EliminationFilters extends PageFilters { elimination_type?: EliminationType; source_company_id?: UUID; target_company_id?: UUID; is_auto_generated?: boolean }
export interface TransferPricingFilters extends PageFilters { source_company_id?: UUID; target_company_id?: UUID; product_category?: string; transaction_type?: TransactionType; pricing_method?: PricingMethod; active_on?: IsoDate }
export interface ConfigurationFilters extends PageFilters { environment?: RuntimeEnvironment }

export interface CompanyCreateRequest { company_code: string; company_name: string; legal_name: string; tax_id?: string; currency: string; fiscal_year_start_month?: number; parent_company_id?: UUID | null; consolidation_group?: string; ownership_percentage?: DecimalString | null; address?: string; is_holding?: boolean; idempotency_key: string }
export type CompanyUpdateRequest = Partial<Omit<CompanyCreateRequest, 'idempotency_key'>> & { expected_version: number };
export interface TransitionRequest { expected_version: number; transition_key: string }
export interface ReasonTransitionRequest extends TransitionRequest { reason: string }
export interface AccessGrantCreateRequest { company_id: UUID; subject_id: string; role: CompanyRole; valid_from?: IsoDateTime; valid_until?: IsoDateTime | null }
export interface TransactionCreateRequest { reference: string; source_company_id: UUID; target_company_id: UUID; transaction_type: TransactionType; product_category?: string; amount: DecimalString; currency: string; exchange_rate?: DecimalString | null; description?: string; transaction_date: IsoDate; transfer_pricing_rule_id?: UUID | null; idempotency_key: string }
export type TransactionUpdateRequest = Partial<Omit<TransactionCreateRequest, 'idempotency_key'>> & { expected_version: number };
export interface ApprovalRequest extends TransitionRequest { side: ApprovalSide; decision: 'approved' | 'rejected'; reason?: string; workflow_reference?: string }
export interface ResolveDisputeRequest extends TransitionRequest { resolution: string }
export interface ApplyPricingRequest { expected_version: number; rule_id?: UUID | null }
export interface ConsolidationCreateRequest { name: string; consolidation_group: string; period_start: IsoDate; period_end: IsoDate; reporting_currency: string; translation_method: TranslationMethod; idempotency_key: string }
export type ConsolidationUpdateRequest = Partial<Omit<ConsolidationCreateRequest, 'idempotency_key'>> & { expected_version: number };
export interface EliminationCreateRequest { elimination_type: EliminationType; source_company_id: UUID; target_company_id: UUID; debit_account: string; credit_account: string; amount: DecimalString; currency: string; description?: string; source_transaction_id?: UUID | null; rule_key?: string; idempotency_key: string }
export interface TransferPricingRuleCreateRequest { name: string; source_company_id: UUID; target_company_id: UUID; product_category: string; transaction_type: TransactionType; pricing_method: PricingMethod; extension_key?: string; markup_percentage?: DecimalString | null; margin_range_min?: DecimalString | null; margin_range_max?: DecimalString | null; parameters: PricingParameters; effective_from: IsoDate; effective_to?: IsoDate | null; documentation?: string; idempotency_key: string }
export type TransferPricingRuleUpdateRequest = Partial<Omit<TransferPricingRuleCreateRequest, 'idempotency_key'>> & { expected_version: number };
export interface TransferPriceRequest { source_company_id: UUID; target_company_id: UUID; product_category: string; transaction_type: TransactionType; amount: DecimalString; currency: string; effective_date: IsoDate; rule_id?: UUID | null; scenarios?: readonly TransferPriceScenario[] }
export interface ConfigurationCreateRequest { environment: RuntimeEnvironment; schema_version: string; settings: MultiCompanySettings; change_summary: string }
export interface ConfigurationUpdateRequest { expected_version: number; settings?: MultiCompanySettings; change_summary?: string }
export interface ConfigurationRollbackRequest { transition_key: string; change_summary: string }

export const MODULE_API_PREFIX = '/api/v2/multi-company';
const resource = (name: string) => `${MODULE_API_PREFIX}/${name}/` as const;
const detail = (name: string, id: UUID) => `${MODULE_API_PREFIX}/${name}/${encodeURIComponent(id)}/` as const;
export const ENDPOINTS = {
  COMPANIES: { LIST: resource('companies'), CREATE: resource('companies'), DETAIL: (id: UUID) => detail('companies', id), UPDATE: (id: UUID) => detail('companies', id), DELETE: (id: UUID) => detail('companies', id), DEACTIVATE: (id: UUID) => `${detail('companies', id)}deactivate/` as const, REACTIVATE: (id: UUID) => `${detail('companies', id)}reactivate/` as const, HIERARCHY: `${resource('companies')}hierarchy/` as const, SUBSIDIARIES: (id: UUID) => `${detail('companies', id)}subsidiaries/` as const, CONSOLIDATION_GROUP: (group: string) => `${resource('companies')}consolidation-groups/${encodeURIComponent(group)}/` as const },
  COMPANY_ACCESS: { LIST: resource('company-access'), CREATE: resource('company-access'), DETAIL: (id: UUID) => detail('company-access', id), REVOKE: (id: UUID) => `${detail('company-access', id)}revoke/` as const },
  TRANSACTIONS: { LIST: resource('transactions'), CREATE: resource('transactions'), DETAIL: (id: UUID) => detail('transactions', id), UPDATE: (id: UUID) => detail('transactions', id), SUBMIT: (id: UUID) => `${detail('transactions', id)}submit/` as const, APPROVE: (id: UUID) => `${detail('transactions', id)}approve/` as const, DISPUTE: (id: UUID) => `${detail('transactions', id)}dispute/` as const, RESOLVE_DISPUTE: (id: UUID) => `${detail('transactions', id)}resolve-dispute/` as const, APPLY_TRANSFER_PRICING: (id: UUID) => `${detail('transactions', id)}apply-transfer-pricing/` as const, POST: (id: UUID) => `${detail('transactions', id)}post/` as const, RETRY_POSTING: (id: UUID) => `${detail('transactions', id)}retry-posting/` as const, CANCEL: (id: UUID) => `${detail('transactions', id)}cancel/` as const, REVERSE: (id: UUID) => `${detail('transactions', id)}reverse/` as const },
  RECONCILIATION: resource('reconciliation'),
  CONSOLIDATIONS: { LIST: resource('consolidation-runs'), CREATE: resource('consolidation-runs'), DETAIL: (id: UUID) => detail('consolidation-runs', id), UPDATE: (id: UUID) => detail('consolidation-runs', id), EXECUTE: (id: UUID) => `${detail('consolidation-runs', id)}execute/` as const, RETRY: (id: UUID) => `${detail('consolidation-runs', id)}retry/` as const, APPROVE: (id: UUID) => `${detail('consolidation-runs', id)}approve/` as const, PUBLISH: (id: UUID) => `${detail('consolidation-runs', id)}publish/` as const, CANCEL: (id: UUID) => `${detail('consolidation-runs', id)}cancel/` as const, ELIMINATIONS: (id: UUID) => `${detail('consolidation-runs', id)}eliminations/` as const, REPORT: (id: UUID) => `${detail('consolidation-runs', id)}report/` as const },
  ELIMINATIONS: { DETAIL: (id: UUID) => detail('eliminations', id) },
  TRANSFER_PRICING_RULES: { LIST: resource('transfer-pricing-rules'), CREATE: resource('transfer-pricing-rules'), DETAIL: (id: UUID) => detail('transfer-pricing-rules', id), UPDATE: (id: UUID) => detail('transfer-pricing-rules', id), DELETE: (id: UUID) => detail('transfer-pricing-rules', id) },
  TRANSFER_PRICING: { CALCULATE: `${resource('transfer-pricing')}calculate/` as const, PREVIEW: `${resource('transfer-pricing')}preview/` as const },
  CONFIGURATION: { LIST: `${resource('configuration')}versions/` as const, CREATE: `${resource('configuration')}versions/` as const, DETAIL: (id: UUID) => `${resource('configuration')}versions/${encodeURIComponent(id)}/` as const, UPDATE: (id: UUID) => `${resource('configuration')}versions/${encodeURIComponent(id)}/` as const, VALIDATE: (id: UUID) => `${resource('configuration')}versions/${encodeURIComponent(id)}/validate/` as const, PREVIEW: (id: UUID) => `${resource('configuration')}versions/${encodeURIComponent(id)}/preview/` as const, ACTIVATE: (id: UUID) => `${resource('configuration')}versions/${encodeURIComponent(id)}/activate/` as const, ROLLBACK: (id: UUID) => `${resource('configuration')}versions/${encodeURIComponent(id)}/rollback/` as const, EXPORT: `${resource('configuration')}export/` as const, IMPORT: `${resource('configuration')}import/` as const },
  EXTENSIONS: { CATALOG: `${resource('extensions')}catalog/` as const },
  JOBS: { DETAIL: (id: UUID) => detail('jobs', id) }, HEALTH: resource('health'),
} as const;
