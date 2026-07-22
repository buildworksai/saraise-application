/** Governed, tenant-safe contract for the fixed-asset financial lifecycle. */

export interface PaginationMeta {
  readonly page: number;
  readonly page_size: number;
  readonly total_pages: number;
  readonly count: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}

export interface ApiMeta {
  readonly correlation_id: string;
  readonly timestamp: string;
  readonly pagination?: PaginationMeta;
}

export interface ApiEnvelope<T> { readonly data: T; readonly meta: ApiMeta }
export interface PaginatedEnvelope<T> {
  readonly data: readonly T[];
  readonly meta: ApiMeta & { readonly pagination: PaginationMeta };
}

export type DepreciationMethod = 'straight_line' | 'declining_balance' | 'units_of_production';
export type AssetStatus = 'draft' | 'active' | 'fully_depreciated' | 'disposed';
export type ScheduleStatus = 'draft' | 'calculated' | 'active' | 'completed' | 'superseded';
export type DepreciationLineStatus = 'planned' | 'posting' | 'posted' | 'failed' | 'void';
export type TransactionType = 'capitalization' | 'depreciation' | 'transfer' | 'impairment' | 'disposal';
export type AllowedCommand = 'edit' | 'delete' | 'deactivate' | 'capitalize' | 'transfer' | 'impair' | 'dispose' | 'calculate' | 'activate' | 'supersede' | 'post' | 'retry';
export type ServerAllowedCommand = AllowedCommand | 'update';
export type JobStatus = 'queued' | 'running' | 'retrying' | 'succeeded' | 'failed' | 'timed_out' | 'cancelled';

export interface CommandAffordance {
  readonly command: AllowedCommand;
  readonly allowed: boolean;
  readonly denial_code?: string;
  readonly explanation?: string;
}
export interface CommandDenialReasons { readonly update?: string; readonly edit?: string; readonly delete?: string; readonly deactivate?: string; readonly capitalize?: string; readonly transfer?: string; readonly impair?: string; readonly dispose?: string; readonly calculate?: string; readonly activate?: string; readonly supersede?: string; readonly post?: string; readonly retry?: string }

export interface CategorySummary { readonly id: string; readonly code: string; readonly name: string }

export interface AssetCategory {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly default_depreciation_method: DepreciationMethod;
  readonly default_useful_life_months: number;
  readonly default_residual_value_percent: string;
  readonly default_declining_balance_rate: string | null;
  readonly asset_account_id: string | null;
  readonly accumulated_depreciation_account_id: string | null;
  readonly depreciation_expense_account_id: string | null;
  readonly impairment_loss_account_id: string | null;
  readonly disposal_gain_account_id: string | null;
  readonly disposal_loss_account_id: string | null;
  readonly is_active: boolean;
  readonly version: number;
  readonly allowed_commands?: readonly ServerAllowedCommand[];
  readonly denial_reasons?: CommandDenialReasons;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface FixedAsset {
  readonly id: string;
  readonly asset_code: string;
  readonly asset_name: string;
  readonly description: string;
  readonly category: CategorySummary;
  readonly purchase_date: string;
  readonly purchase_cost: string;
  readonly currency: string;
  readonly residual_value: string;
  readonly capitalization_date: string | null;
  readonly depreciation_start_date: string | null;
  readonly depreciation_method: DepreciationMethod;
  readonly useful_life_months: number;
  readonly declining_balance_rate: string | null;
  readonly expected_total_units: string | null;
  readonly accumulated_depreciation: string;
  readonly accumulated_impairment: string;
  readonly net_book_value: string;
  readonly location: string;
  readonly cost_center: string;
  readonly status: AssetStatus;
  readonly disposal_date: string | null;
  readonly disposal_proceeds: string | null;
  readonly disposal_gain_loss: string | null;
  readonly next_depreciation_date: string | null;
  readonly as_of: string;
  readonly version: number;
  readonly allowed_commands: readonly ServerAllowedCommand[];
  readonly denial_reasons: CommandDenialReasons;
  readonly active_schedule: ScheduleSummary | null;
  readonly balance_reconciliation: BalanceReconciliation;
  readonly created_by: string;
  readonly updated_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ScheduleSummary { readonly id: string; readonly schedule_number: string; readonly revision: number; readonly status: ScheduleStatus }
export interface BalanceReconciliation { readonly purchase_cost: string; readonly accumulated_depreciation: string; readonly accumulated_impairment: string; readonly calculated_net_book_value: string; readonly reconciled: boolean }

export interface DepreciationSchedule {
  readonly id: string;
  readonly asset_id: string;
  readonly asset: { readonly id: string; readonly asset_code: string; readonly asset_name: string; readonly currency?: string };
  readonly schedule_number: string;
  readonly revision: number;
  readonly method: DepreciationMethod;
  readonly frequency: 'monthly';
  readonly start_date: string;
  readonly end_date: string;
  readonly cost_basis: string;
  readonly residual_value: string;
  readonly depreciable_amount: string;
  readonly declining_balance_rate: string | null;
  readonly expected_total_units: string | null;
  readonly total_planned_depreciation: string;
  readonly status: ScheduleStatus;
  readonly version: number;
  readonly calculated_at: string | null;
  readonly activated_at: string | null;
  readonly completed_at: string | null;
  readonly superseded_by: string | null;
  readonly lines_url?: string;
  readonly reconciliation: { readonly line_total: string; readonly difference: string; readonly reconciled: boolean };
  readonly allowed_commands?: readonly ServerAllowedCommand[];
  readonly denial_reasons?: CommandDenialReasons;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface DepreciationLine {
  readonly id: string;
  readonly schedule_id: string;
  readonly asset_id: string;
  readonly currency?: string;
  readonly sequence: number;
  readonly period_start: string;
  readonly period_end: string;
  readonly opening_net_book_value: string;
  readonly units_consumed: string | null;
  readonly depreciation_amount: string;
  readonly accumulated_depreciation: string;
  readonly closing_net_book_value: string;
  readonly status: DepreciationLineStatus;
  readonly journal_entry_id: string | null;
  readonly posting_job_id: string | null;
  readonly posted_at: string | null;
  readonly posting_error_code: string;
  readonly allowed_commands?: readonly ServerAllowedCommand[];
  readonly denial_reasons?: CommandDenialReasons;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface TransactionMetadata {
  readonly reason?: string;
  readonly gain_loss?: string;
  readonly book_code?: string;
  readonly schedule_id?: string;
  readonly depreciation_line_id?: string;
  readonly prior_asset_version?: number;
  readonly resulting_asset_version?: number;
}
export interface AssetTransaction {
  readonly id: string;
  readonly asset_id: string;
  readonly asset: { readonly id: string; readonly asset_code: string; readonly asset_name: string };
  readonly transaction_type: TransactionType;
  readonly effective_date: string;
  readonly amount: string;
  readonly currency: string;
  readonly opening_net_book_value: string;
  readonly closing_net_book_value: string;
  readonly from_location: string;
  readonly to_location: string;
  readonly from_cost_center: string;
  readonly to_cost_center: string;
  readonly journal_entry_id: string | null;
  readonly source_type: string;
  readonly source_id: string | null;
  readonly actor_id: string;
  readonly correlation_id: string;
  readonly metadata: TransactionMetadata;
  readonly created_at: string;
}

export interface AssetCategoryCreateRequest {
  code: string; name: string; description?: string; default_depreciation_method: DepreciationMethod;
  default_useful_life_months: number; default_residual_value_percent: string; default_declining_balance_rate?: string | null;
  asset_account_id?: string | null; accumulated_depreciation_account_id?: string | null; depreciation_expense_account_id?: string | null;
  impairment_loss_account_id?: string | null; disposal_gain_account_id?: string | null; disposal_loss_account_id?: string | null; is_active?: boolean;
}
export type AssetCategoryUpdateRequest = Partial<AssetCategoryCreateRequest> & { expected_version: number };
export interface FixedAssetCreateRequest { asset_code: string; asset_name: string; description?: string; category_id: string; purchase_date: string; purchase_cost: string; currency: string; residual_value?: string; depreciation_method: DepreciationMethod; useful_life_months: number; declining_balance_rate?: string | null; expected_total_units?: string | null; location?: string; cost_center?: string }
export type FixedAssetUpdateRequest = Partial<FixedAssetCreateRequest> & { expected_version: number };
export interface CapitalizeRequest { effective_date: string; depreciation_start_date?: string; expected_version: number }
export interface TransferRequest { effective_date: string; to_location: string; to_cost_center: string }
export interface ImpairmentRequest { effective_date: string; recoverable_amount: string; reason: string }
export interface DisposalRequest { effective_date: string; proceeds: string; reason: string }
export interface ScheduleCreateRequest { asset_id: string; method?: DepreciationMethod; start_date?: string; end_date?: string; residual_value?: string; declining_balance_rate?: string | null; expected_total_units?: string | null }
export type ScheduleUpdateRequest = Partial<ScheduleCreateRequest> & { expected_version: number };
export interface ScheduleCalculateRequest { units_by_period?: readonly { period_start: string; units_consumed: string }[] }
export interface ScheduleTransitionRequest { reason?: string }
export interface LinePostingRequest { expected_asset_version?: number }
export interface DuePostingRequest { through_date: string }

export interface FinancialEffectEntry { readonly account_id: string | null; readonly direction: 'debit' | 'credit'; readonly amount: string; readonly currency: string; readonly description?: string }
export interface LifecyclePreview {
  readonly command: 'capitalize' | 'transfer' | 'impair' | 'dispose';
  readonly asset_version: number;
  readonly as_of: string;
  readonly opening_net_book_value: string;
  readonly closing_net_book_value: string;
  readonly currency: string;
  readonly warnings: readonly { readonly code: string; readonly message: string }[];
  readonly blockers: readonly { readonly code: string; readonly message: string }[];
  readonly journal_effect: { readonly status: 'ready' | 'not_required' | 'unavailable'; readonly entries: readonly FinancialEffectEntry[] };
  readonly schedule_effect: { readonly status: 'unchanged' | 'created' | 'superseded' | 'completed' | 'voided'; readonly description: string };
}

/** Versioned paid-strategy boundary; core never assumes extension parameters. */
export interface StrategyParameterDescriptor { readonly key: string; readonly label: string; readonly input_type: 'decimal' | 'integer' | 'date' | 'select' | 'text'; readonly required: boolean; readonly help_text: string; readonly options?: readonly { readonly value: string; readonly label: string }[] }
export interface DepreciationStrategyDescriptor { readonly id: string; readonly namespace: string; readonly schema_version: string; readonly label: string; readonly description: string; readonly parameters: readonly StrategyParameterDescriptor[]; readonly entitlement_code: string | null }
export interface StrategyParameterValue { readonly key: string; readonly value: string }
export interface AssetDetailContributionDescriptor { readonly id: string; readonly schema_version: string; readonly label: string; readonly route: string; readonly entitlement_code: string | null }
export interface FixedAssetReportDescriptor { readonly id: string; readonly schema_version: string; readonly label: string; readonly route: string; readonly entitlement_code: string | null }
export interface FixedAssetActionDescriptor { readonly id: string; readonly schema_version: string; readonly label: string; readonly preview_route: string; readonly command_route: string; readonly entitlement_code: string | null }
export interface FixedAssetFrontendExtension { readonly namespace: string; readonly schema_version: string; readonly strategies: readonly DepreciationStrategyDescriptor[]; readonly asset_detail_contributions: readonly AssetDetailContributionDescriptor[]; readonly reports: readonly FixedAssetReportDescriptor[]; readonly actions: readonly FixedAssetActionDescriptor[] }

export interface DashboardCurrencyTotal { readonly currency: string; readonly amount: string }
export interface FixedAssetDashboard {
  readonly asset_counts: { readonly draft: number; readonly active: number; readonly fully_depreciated: number; readonly disposed: number; readonly total: number };
  readonly book_value_by_currency: readonly DashboardCurrencyTotal[];
  readonly current_period_depreciation_by_currency: readonly DashboardCurrencyTotal[];
  readonly pending_postings: number; readonly failed_postings: number; readonly impairments: number; readonly disposals: number;
}
export interface HealthStatus { readonly status: 'healthy' | 'degraded' | 'unhealthy'; readonly checks: readonly { readonly name: string; readonly status: 'healthy' | 'degraded' | 'unhealthy'; readonly code?: string }[] }
export interface JobResult { readonly posted_line_ids?: readonly string[]; readonly failed_line_ids?: readonly string[]; readonly progress_percent?: number }
export interface JobStatusDto { readonly id: string; readonly status: JobStatus; readonly operation: string; readonly progress_percent: number | null; readonly error_code: string | null; readonly correlation_id: string; readonly result: JobResult | null; readonly created_at: string; readonly updated_at: string }

export interface ValidationError { readonly field: string; readonly code: string; readonly message: string }
export interface GovernedErrorBody { readonly error: { readonly code: string; readonly message: string; readonly correlation_id?: string; readonly field_errors?: readonly ValidationError[] } }
export interface ListResult<T> { readonly items: readonly T[]; readonly pagination: PaginationMeta; readonly correlationId: string }

export interface CommonFilters { page?: number; page_size?: number; search?: string; ordering?: string }
export interface AssetFilters extends CommonFilters { status?: AssetStatus; category_id?: string; method?: DepreciationMethod; currency?: string; location?: string; cost_center?: string; capitalized_from?: string; capitalized_to?: string }
export interface CategoryFilters extends CommonFilters { is_active?: boolean; method?: DepreciationMethod }
export interface ScheduleFilters extends CommonFilters { asset_id?: string; status?: ScheduleStatus; method?: DepreciationMethod; start_from?: string; start_to?: string }
export interface LineFilters extends CommonFilters { asset_id?: string; schedule_id?: string; status?: DepreciationLineStatus; period_from?: string; period_to?: string }

export const MODULE_API_PREFIX = '/api/v2/fixed-assets';
export const ENDPOINTS = {
  CATEGORIES: { LIST: `${MODULE_API_PREFIX}/categories/`, CREATE: `${MODULE_API_PREFIX}/categories/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/categories/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/categories/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/categories/${id}/` as const },
  ASSETS: { LIST: `${MODULE_API_PREFIX}/assets/`, CREATE: `${MODULE_API_PREFIX}/assets/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/` as const, CAPITALIZE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/capitalize/` as const, TRANSFER: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/transfer/` as const, IMPAIR: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/impair/` as const, DISPOSE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/dispose/` as const, PREVIEW_CAPITALIZE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/preview-capitalize/` as const, PREVIEW_TRANSFER: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/preview-transfer/` as const, PREVIEW_IMPAIR: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/preview-impair/` as const, PREVIEW_DISPOSE: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/preview-dispose/` as const, TRANSACTIONS: (id: string) => `${MODULE_API_PREFIX}/assets/${id}/transactions/` as const },
  SCHEDULES: { LIST: `${MODULE_API_PREFIX}/depreciation-schedules/`, CREATE: `${MODULE_API_PREFIX}/depreciation-schedules/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/depreciation-schedules/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/depreciation-schedules/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/depreciation-schedules/${id}/` as const, CALCULATE: (id: string) => `${MODULE_API_PREFIX}/depreciation-schedules/${id}/calculate/` as const, ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/depreciation-schedules/${id}/activate/` as const, SUPERSEDE: (id: string) => `${MODULE_API_PREFIX}/depreciation-schedules/${id}/supersede/` as const },
  LINES: { LIST: `${MODULE_API_PREFIX}/depreciation-lines/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/depreciation-lines/${id}/` as const, POST: (id: string) => `${MODULE_API_PREFIX}/depreciation-lines/${id}/post/` as const, POST_DUE: `${MODULE_API_PREFIX}/depreciation-lines/post-due/` },
  TRANSACTIONS: { DETAIL: (id: string) => `${MODULE_API_PREFIX}/transactions/${id}/` as const }, JOBS: { DETAIL: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/` as const },
  STRATEGIES: { LIST: `${MODULE_API_PREFIX}/depreciation-strategies/` },
  DASHBOARD: `${MODULE_API_PREFIX}/dashboard/`, HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
