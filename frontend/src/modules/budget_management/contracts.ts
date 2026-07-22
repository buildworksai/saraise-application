/** Authoritative frontend contract for the governed Budget Management v2 API. */
export type UUID = string;
export type DecimalString = string;
export type ISODate = string;
export type ISODateTime = string;

export interface PaginationMeta {
  readonly page: number;
  readonly page_size: number;
  readonly count: number;
  readonly total_pages: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}

export interface ApiV2Meta {
  readonly correlation_id: string;
  readonly timestamp: ISODateTime;
  readonly pagination?: PaginationMeta;
}

export interface ApiV2Envelope<T> {
  readonly data: T;
  readonly meta: ApiV2Meta;
}

export interface ApiV2PaginatedEnvelope<T> extends ApiV2Envelope<readonly T[]> {
  readonly meta: ApiV2Meta & { readonly pagination: PaginationMeta };
}

export interface ApiV2Error {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly fields?: Readonly<Record<string, readonly string[]>>;
    readonly retryable?: boolean;
    readonly correlation_id?: string;
  };
  readonly meta?: { readonly correlation_id?: string; readonly timestamp?: ISODateTime };
}

export type BudgetStatus = 'draft' | 'pending_approval' | 'approved' | 'rejected' | 'revision' | 'closed';
export type BudgetType = 'operating' | 'capital' | 'project' | 'departmental';
export type PeriodType = 'annual' | 'monthly' | 'quarterly';
export type AlertType = 'over_budget' | 'approaching_limit' | 'underspend';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';
export type NotificationStatus = 'pending' | 'sent' | 'failed' | 'unavailable';

export interface BudgetListItem {
  readonly id: UUID;
  readonly budget_code: string;
  readonly budget_name: string;
  readonly fiscal_year: number;
  readonly start_date: ISODate;
  readonly end_date: ISODate;
  readonly budget_type: BudgetType;
  readonly department_id: UUID | null;
  readonly project_id: UUID | null;
  readonly status: BudgetStatus;
  readonly currency: string;
  readonly budget_ceiling: DecimalString | null;
  readonly total_budget: DecimalString;
  readonly variance?: DecimalString | null;
  readonly variance_percentage?: DecimalString | null;
  readonly updated_at: ISODateTime;
}

export interface BudgetLine {
  readonly id: UUID;
  readonly budget: UUID;
  readonly account_id: UUID | null;
  readonly account_code: string;
  readonly account_name: string;
  readonly period_type: PeriodType;
  readonly period_number: number;
  readonly budget_amount: DecimalString;
  readonly committed_amount: DecimalString;
  readonly actual_amount: DecimalString;
  readonly variance: DecimalString;
  readonly actuals_as_of: ISODateTime | null;
  readonly source: 'manual' | 'accounting_sync';
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
}

export interface BudgetApproval {
  readonly id: UUID;
  readonly budget: UUID;
  readonly budget_code?: string;
  readonly budget_name?: string;
  readonly budget_total?: DecimalString;
  readonly currency?: string;
  readonly submitted_by?: UUID | null;
  readonly submitted_at?: ISODateTime | null;
  readonly workflow_request_id: UUID | null;
  readonly approver_id: UUID;
  readonly approval_level: number;
  readonly status: ApprovalStatus;
  readonly decision_at: ISODateTime | null;
  readonly notes: string;
  readonly rejection_reason: string;
  readonly created_by: UUID;
  readonly created_at: ISODateTime;
  readonly self_approval_denied?: boolean;
}

export interface BudgetTransition {
  readonly id: UUID;
  readonly budget: UUID;
  readonly transition_key: string;
  readonly command: string;
  readonly from_state: BudgetStatus;
  readonly to_state: BudgetStatus;
  readonly actor_id: UUID;
  readonly notes: string;
  readonly metadata: Readonly<Record<string, string | number | boolean | null>>;
  readonly occurred_at: ISODateTime;
}

export interface VarianceLine {
  readonly budget_line_id: UUID;
  readonly account_code: string;
  readonly account_name?: string;
  readonly period_type: PeriodType;
  readonly period_number: number;
  readonly budgeted: DecimalString;
  readonly committed: DecimalString;
  readonly actual: DecimalString;
  readonly variance: DecimalString;
  readonly variance_percentage: DecimalString | null;
  readonly favorable: boolean;
  readonly threshold_exceeded: boolean;
}

export interface VarianceReport {
  readonly budget_id: UUID;
  readonly currency: string;
  readonly budgeted: DecimalString;
  readonly committed: DecimalString;
  readonly actual: DecimalString;
  readonly variance: DecimalString;
  readonly variance_percentage: DecimalString | null;
  readonly favorable: boolean;
  readonly lines: readonly VarianceLine[];
  readonly as_of: ISODateTime;
}

export interface VarianceAlert {
  readonly id: UUID;
  readonly budget: UUID;
  readonly budget_line: UUID;
  readonly alert_type: AlertType;
  readonly threshold_percentage: DecimalString;
  readonly variance_percentage: DecimalString | null;
  readonly budget_amount: DecimalString;
  readonly actual_amount: DecimalString;
  readonly committed_amount: DecimalString;
  readonly alert_date: ISODate;
  readonly notification_status: NotificationStatus;
  readonly notification_job_id: UUID | null;
  readonly acknowledged_at: ISODateTime | null;
  readonly acknowledged_by: UUID | null;
  readonly created_at: ISODateTime;
}

export interface BudgetDetail extends BudgetListItem {
  readonly submitted_at: ISODateTime | null;
  readonly submitted_by: UUID | null;
  readonly approved_at: ISODateTime | null;
  readonly approved_by: UUID | null;
  readonly rejected_at: ISODateTime | null;
  readonly rejected_by: UUID | null;
  readonly rejection_reason: string;
  readonly created_at: ISODateTime;
  readonly created_by: UUID;
  readonly updated_by: UUID;
  readonly lines: readonly BudgetLine[];
  readonly approvals: readonly BudgetApproval[];
  readonly transitions: readonly BudgetTransition[];
  readonly variance_alerts: readonly VarianceAlert[];
  readonly variance_summary: VarianceReport | null;
  readonly allowed_commands: readonly string[];
}

export interface BudgetCreateRequest {
  readonly budget_code: string;
  readonly budget_name: string;
  readonly fiscal_year: number;
  readonly start_date: ISODate;
  readonly end_date: ISODate;
  readonly budget_type: BudgetType;
  readonly currency: string;
  readonly budget_ceiling?: DecimalString | null;
  readonly department_id?: UUID | null;
  readonly project_id?: UUID | null;
}

export interface BudgetUpdateRequest {
  readonly expected_updated_at: ISODateTime;
  readonly budget_code?: string;
  readonly budget_name?: string;
  readonly fiscal_year?: number;
  readonly start_date?: ISODate;
  readonly end_date?: ISODate;
  readonly budget_type?: BudgetType;
  readonly currency?: string;
  readonly budget_ceiling?: DecimalString | null;
  readonly department_id?: UUID | null;
  readonly project_id?: UUID | null;
}

export interface BudgetLineCreateRequest {
  readonly budget: UUID;
  readonly account_code: string;
  readonly period_type: PeriodType;
  readonly period_number: number;
  readonly budget_amount: DecimalString;
}

export interface BudgetLineUpdateRequest {
  readonly expected_updated_at: ISODateTime;
  readonly account_code?: string;
  readonly period_type?: PeriodType;
  readonly period_number?: number;
  readonly budget_amount?: DecimalString;
}

export interface AllocationInput {
  readonly account_code: string;
  readonly period_type: PeriodType;
  readonly period_number: number;
  readonly budget_amount: DecimalString;
}

export interface AllocationReplaceRequest {
  readonly expected_updated_at: ISODateTime;
  readonly allocations: readonly AllocationInput[];
}

export interface TransitionRequest {
  readonly idempotency_key: string;
  readonly notes?: string;
}

export interface RejectRequest extends TransitionRequest { readonly reason: string }

export interface BudgetAvailabilityRequest {
  readonly account_code: string;
  readonly amount: DecimalString;
  readonly period: ISODate;
  readonly budget_id?: UUID;
}

export interface BudgetAvailabilityResult {
  readonly account_code: string;
  readonly budget_id: UUID | null;
  readonly currency?: string | null;
  readonly allocated: DecimalString;
  readonly committed: DecimalString;
  readonly actual: DecimalString;
  readonly available: DecimalString;
  readonly deficit: DecimalString;
  readonly sufficient: boolean;
  readonly unbudgeted: boolean;
}

export interface ActualsSyncRequest { readonly idempotency_key: string }
export interface AcceptedJob {
  readonly id: UUID;
  readonly job_type: string;
  readonly status: 'queued' | 'running' | 'succeeded' | 'failed' | 'timed_out' | 'cancelled';
  readonly created_at: ISODateTime;
}

export interface HealthResult {
  readonly status: 'healthy' | 'degraded' | 'unhealthy';
  readonly dependencies: Readonly<Record<string, 'healthy' | 'degraded' | 'unhealthy' | 'unavailable'>>;
  readonly checked_at: ISODateTime;
}

export interface PageFilters { readonly page?: number; readonly page_size?: number; readonly ordering?: string }
export interface BudgetListFilters extends PageFilters {
  readonly fiscal_year?: number;
  readonly budget_type?: BudgetType;
  readonly status?: BudgetStatus;
  readonly currency?: string;
  readonly department_id?: UUID;
  readonly project_id?: UUID;
  readonly start_date_from?: ISODate;
  readonly end_date_to?: ISODate;
  readonly search?: string;
}
export interface BudgetLineFilters extends PageFilters { readonly budget_id: UUID; readonly account_code?: string; readonly account_id?: UUID; readonly period_type?: PeriodType; readonly period_number?: number; readonly source?: 'manual' | 'accounting_sync' }
export interface ApprovalFilters extends PageFilters { readonly budget_id?: UUID; readonly approver_id?: UUID; readonly status?: ApprovalStatus; readonly approval_level?: number }
export interface VarianceAlertFilters extends PageFilters { readonly budget_id?: UUID; readonly budget_line_id?: UUID; readonly alert_type?: AlertType; readonly notification_status?: NotificationStatus; readonly acknowledged?: boolean; readonly date_from?: ISODate; readonly date_to?: ISODate }
export interface VarianceFilters { readonly period_type?: PeriodType; readonly period_number?: number; readonly account_code?: string; readonly threshold_percentage?: number }
export interface VarianceAlertGenerateRequest { readonly threshold_percentage: DecimalString; readonly alert_type: AlertType; readonly idempotency_key: string }
export interface VarianceAlertAcknowledgeRequest { readonly acknowledged: true }

export interface PaginatedResult<T> {
  readonly items: readonly T[];
  readonly pagination: PaginationMeta;
  readonly correlationId: string;
  readonly receivedAt: ISODateTime;
}

export const MODULE_API_PREFIX = '/api/v2/budget-management';
export const ENDPOINTS = {
  BUDGETS: {
    LIST: `${MODULE_API_PREFIX}/budgets/`, CREATE: `${MODULE_API_PREFIX}/budgets/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/` as const,
    ALLOCATIONS: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/allocations/` as const,
    SUBMIT: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/submit/` as const,
    APPROVE: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/approve/` as const,
    REJECT: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/reject/` as const,
    REVISE: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/revise/` as const,
    CLOSE: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/close/` as const,
    VARIANCE: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/variance/` as const,
    SYNC_ACTUALS: (id: UUID) => `${MODULE_API_PREFIX}/budgets/${id}/sync-actuals/` as const,
  },
  BUDGET_LINES: { LIST: `${MODULE_API_PREFIX}/budget-lines/`, CREATE: `${MODULE_API_PREFIX}/budget-lines/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/budget-lines/${id}/` as const, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/budget-lines/${id}/` as const, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/budget-lines/${id}/` as const },
  APPROVALS: { LIST: `${MODULE_API_PREFIX}/approvals/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/approvals/${id}/` as const },
  VARIANCE_ALERTS: { LIST: `${MODULE_API_PREFIX}/variance-alerts/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/variance-alerts/${id}/` as const, GENERATE: `${MODULE_API_PREFIX}/variance-alerts/generate/`, ACKNOWLEDGE: (id: UUID) => `${MODULE_API_PREFIX}/variance-alerts/${id}/acknowledge/` as const },
  AVAILABILITY: `${MODULE_API_PREFIX}/availability/`,
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTES = {
  BUDGETS: '/budget-management/budgets', CREATE: '/budget-management/budgets/new',
  DETAIL: (id: UUID) => `/budget-management/budgets/${id}` as const,
  EDIT: (id: UUID) => `/budget-management/budgets/${id}/edit` as const,
  ALLOCATIONS: (id: UUID) => `/budget-management/budgets/${id}/allocations` as const,
  APPROVALS: '/budget-management/approvals', VARIANCE: '/budget-management/variance', REPORT: '/budget-management/report',
} as const;

export const QUERY_KEYS = {
  root: ['budget-management'] as const,
  budgets: (filters: BudgetListFilters = {}) => ['budget-management', 'budgets', stableFilters(filters)] as const,
  budget: (id: UUID) => ['budget-management', 'budget', id] as const,
  lines: (filters: BudgetLineFilters) => ['budget-management', 'lines', stableFilters(filters)] as const,
  approvals: (filters: ApprovalFilters = {}) => ['budget-management', 'approvals', stableFilters(filters)] as const,
  variance: (id: UUID, filters: VarianceFilters = {}) => ['budget-management', 'variance', id, stableFilters(filters)] as const,
  alerts: (filters: VarianceAlertFilters = {}) => ['budget-management', 'alerts', stableFilters(filters)] as const,
};

type QueryValue = string | number | boolean | undefined;
function queryEntries(filters: object): readonly (readonly [string, QueryValue])[] {
  return Object.keys(filters).flatMap((key) => {
    const value: unknown = Object.getOwnPropertyDescriptor(filters, key)?.value;
    return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || value === undefined ? [[key, value] as const] : [];
  });
}
export function withQuery(path: string, filters: object): string {
  const params = new URLSearchParams();
  queryEntries(filters).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)); });
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}
function stableFilters(filters: object): string {
  return queryEntries(filters).filter(([, value]) => value !== undefined && value !== '').sort(([left], [right]) => left.localeCompare(right)).map(([key, value]) => `${key}:${String(value)}`).join('|');
}
