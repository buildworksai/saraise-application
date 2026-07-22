/** CRM v2 API contract. This file is the only owner of CRM DTOs and URLs. */

export type JsonPrimitive = string | number | boolean | null;
export type MetadataValue = JsonPrimitive | readonly MetadataValue[] | { readonly [key: string]: MetadataValue };
/** Extension fields must be namespaced (`industry.<module>.<field>`). */
export type CrmMetadata = Readonly<Record<string, MetadataValue>>;

export type LeadStatus = 'new' | 'contacted' | 'qualified' | 'converted' | 'lost';
export type LeadGrade = 'A' | 'B' | 'C' | 'D';
export type ScoreSource = 'rules' | 'provider';
export type LeadCommand = 'contact' | 'qualify' | 'disqualify';
export type AccountType = 'prospect' | 'customer' | 'partner';
export type OpportunityStage = 'prospecting' | 'qualification' | 'needs_analysis' | 'proposal' | 'negotiation' | 'closed_won' | 'closed_lost';
export type OpportunityOpenStage = Exclude<OpportunityStage, 'closed_won' | 'closed_lost'>;
export type OpportunityStatus = 'open' | 'won' | 'lost';
export type OpportunityTransitionCommand = 'advance_to_qualification' | 'advance_to_needs_analysis' | 'advance_to_proposal' | 'advance_to_negotiation' | 'reopen_to_prospecting' | 'reopen_to_qualification' | 'reopen_to_needs_analysis' | 'reopen_to_proposal';
export type ActivityType = 'call' | 'email' | 'meeting' | 'task' | 'note';
export type RelatedEntityType = 'Lead' | 'Contact' | 'Account' | 'Opportunity';
export type SortDirection = '' | '-';
export type AsyncJobStatus = 'pending' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface TransitionRecord {
  readonly transition_key: string;
  readonly command: string;
  readonly from_state: string;
  readonly to_state: string;
  readonly occurred_at: string;
  readonly metadata: { readonly actor_id?: string; readonly correlation_id?: string; readonly reason_supplied?: boolean };
  /** Derived UI compatibility keys; not serialized in command requests. */
  readonly key?: string;
  readonly reason?: string | null;
}

export interface MutableEntityRead {
  readonly id: string;
  readonly tenant_id: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly created_by: string | null;
  readonly updated_by: string | null;
  readonly version: number;
  readonly is_deleted: boolean;
  readonly deleted_at: string | null;
  readonly metadata: CrmMetadata;
}

export interface Lead extends MutableEntityRead {
  readonly first_name: string;
  readonly last_name: string;
  readonly email: string | null;
  readonly phone: string;
  readonly company: string;
  readonly title: string;
  readonly score: number;
  readonly grade: LeadGrade;
  readonly score_source: ScoreSource;
  readonly score_explanation: CrmMetadata;
  readonly source: string;
  readonly campaign_id: string | null;
  readonly owner_id: string | null;
  readonly status: LeadStatus;
  readonly converted_at: string | null;
  readonly converted_to_opportunity_id: string | null;
  readonly transition_history: readonly TransitionRecord[];
}

export interface LeadCreate {
  first_name?: string;
  last_name: string;
  email?: string | null;
  phone?: string;
  company?: string;
  title?: string;
  source?: string;
  campaign_id?: string | null;
  owner_id?: string | null;
  metadata?: CrmMetadata;
}
export type LeadUpdate = Partial<LeadCreate> & { version: number };

export interface Account extends MutableEntityRead {
  readonly name: string;
  readonly website: string;
  readonly industry: string;
  readonly employees: number | null;
  readonly annual_revenue: string | null;
  readonly parent_account_id: string | null;
  readonly billing_street: string;
  readonly billing_city: string;
  readonly billing_state: string;
  readonly billing_postal_code: string;
  readonly billing_country: string;
  readonly owner_id: string | null;
  readonly account_type: AccountType;
}
export interface AccountCreate {
  name: string;
  website?: string;
  industry?: string;
  employees?: number | null;
  annual_revenue?: string | null;
  parent_account_id?: string | null;
  billing_street?: string;
  billing_city?: string;
  billing_state?: string;
  billing_postal_code?: string;
  billing_country?: string;
  owner_id?: string | null;
  account_type?: AccountType;
  metadata?: CrmMetadata;
}
export type AccountUpdate = Partial<AccountCreate> & { version: number };

export interface AccountHierarchyNode {
  readonly id: string;
  readonly name: string;
  readonly account_type: AccountType;
  readonly children: readonly AccountHierarchyNode[];
}
export interface DuplicateAccountResult {
  readonly local_matches: readonly Account[];
  readonly external_matches: readonly { readonly id: string; readonly name: string; readonly website?: string }[];
  readonly enrichment_status: 'available' | 'unavailable';
}

export interface Contact extends MutableEntityRead {
  readonly account_id: string;
  readonly first_name: string;
  readonly last_name: string;
  readonly email: string | null;
  readonly phone: string;
  readonly mobile: string;
  readonly title: string;
  readonly department: string;
  readonly linkedin: string;
  readonly twitter: string;
  readonly last_contacted_at: string | null;
  readonly engagement_score: number;
  readonly owner_id: string | null;
}
export interface ContactCreate {
  account_id: string;
  first_name?: string;
  last_name: string;
  email?: string | null;
  phone?: string;
  mobile?: string;
  title?: string;
  department?: string;
  linkedin?: string;
  twitter?: string;
  owner_id?: string | null;
  metadata?: CrmMetadata;
  domain_override_reason?: string;
}
export type ContactUpdate = Partial<Omit<ContactCreate, 'account_id'>> & { version: number };

export interface Opportunity extends MutableEntityRead {
  readonly account_id: string;
  readonly primary_contact_id: string | null;
  readonly name: string;
  readonly description: string;
  readonly amount: string;
  readonly currency: string;
  readonly probability: number;
  readonly stage: OpportunityStage;
  readonly close_date: string;
  readonly product_ids: readonly string[];
  readonly competitors: readonly string[];
  readonly owner_id: string | null;
  readonly status: OpportunityStatus;
  readonly closed_at: string | null;
  readonly loss_reason: string;
  readonly converted_to_order_id: string | null;
  readonly last_activity_at: string | null;
  readonly transition_history: readonly TransitionRecord[];
}
export interface OpportunityCreate {
  account_id: string;
  primary_contact_id?: string | null;
  name: string;
  description?: string;
  amount: string;
  currency?: string;
  probability?: number;
  close_date: string;
  product_ids?: readonly string[];
  competitors?: readonly string[];
  owner_id?: string | null;
  metadata?: CrmMetadata;
}
export type OpportunityUpdate = Partial<Omit<OpportunityCreate, 'account_id'>> & { version: number };

export interface Activity extends MutableEntityRead {
  readonly activity_type: ActivityType;
  readonly related_to_type: RelatedEntityType;
  readonly related_to_id: string;
  readonly subject: string;
  readonly description: string;
  readonly outcome: string;
  readonly due_date: string | null;
  readonly completed: boolean;
  readonly completed_at: string | null;
  readonly owner_id: string | null;
  readonly external_id: string;
}
export interface ActivityCreate {
  activity_type: ActivityType;
  related_to_type: RelatedEntityType;
  related_to_id: string;
  subject: string;
  description?: string;
  outcome?: string;
  due_date?: string | null;
  owner_id?: string | null;
  external_id?: string;
  metadata?: CrmMetadata;
}
export type ActivityUpdate = Partial<Omit<ActivityCreate, 'related_to_type' | 'related_to_id'>> & { version: number };

export interface LeadTransitionRequest { command: LeadCommand; transition_key: string; expected_version: number; reason?: string; }
export interface OpportunityTransitionRequest { command: OpportunityTransitionCommand; transition_key: string; expected_version: number; reason?: string; }
export interface LeadConversionRequest {
  amount: string;
  currency: string;
  close_date: string;
  name?: string;
  account_id?: string;
  create_new_account?: boolean;
  transition_key: string;
  expected_version: number;
}
export type OpportunityCreateFromLead = LeadConversionRequest;
export interface CloseWonRequest { expected_version: number; transition_key: string; confirmed: true; }
export interface CloseLostRequest { expected_version: number; transition_key: string; loss_reason: string; }
export interface CompleteActivityRequest { expected_version: number; transition_key: string; }
export type LeadScoringResponse = Lead;
export interface ConversionResult { lead: Lead; account: Account; contact: Contact | null; opportunity: Opportunity; }

export interface CurrencyAmount { readonly currency: string; readonly amount: string; }
export interface CurrencyForecast { readonly currency: string; readonly total_pipeline_value: string; readonly weighted_pipeline_value: string; readonly opportunity_count: number; }
export interface Forecast {
  readonly currencies: readonly CurrencyForecast[];
  readonly period_days: number;
}
export interface WinRate { readonly win_rate: string | null; readonly won_count: number; readonly lost_count: number; readonly total_closed: number; readonly period_days: number; }
export interface StageForecast { readonly stage: OpportunityStage; readonly currency: string; readonly total_value: string; readonly weighted_value: string; readonly opportunity_count: number; }
export interface Prediction { readonly amount: string; readonly currency: string; readonly confidence: string | null; readonly factors: CrmMetadata; readonly provider: string; readonly model: string; readonly as_of: string; readonly period_days: number; }
/** Backwards-compatible name, with no fabricated default values. */
export type AIPrediction = Prediction;

export interface AsyncJob { readonly id: string; readonly command: string; readonly status: AsyncJobStatus; readonly progress: number | null; readonly result: MetadataValue | null; readonly error: ApiError | null; readonly created_at: string; readonly updated_at: string; readonly correlation_id: string; }
export interface AsyncOperation { readonly job_id: string; readonly status: AsyncJobStatus; readonly command: string; readonly created_at: string; readonly correlation_id: string; }
export interface ConflictResponse<T> { readonly current: T; readonly submitted_version: number; readonly current_version: number; readonly changed_fields: readonly string[]; }
export interface ApiError { readonly code: string; readonly message: string; readonly detail: MetadataValue | null; readonly correlation_id: string; }
export interface PaginationMeta { readonly count: number; readonly page: number; readonly page_size: number; readonly total_pages: number; readonly has_next: boolean; readonly has_previous: boolean; }
export interface ResponseMeta { readonly correlation_id: string; readonly timestamp: string; }
export interface V2Envelope<T> { readonly data: T; readonly meta: ResponseMeta; }
export interface V2PageEnvelope<T> { readonly data: readonly T[]; readonly meta: ResponseMeta & { readonly pagination: PaginationMeta }; }

export interface PageFilters { page?: number; page_size?: number; ordering?: string; }
export interface LeadFilters extends PageFilters { status?: LeadStatus; owner_id?: string; score_min?: number; score_max?: number; source?: string; search?: string; }
export interface AccountFilters extends PageFilters { account_type?: AccountType; owner_id?: string; parent_account_id?: string; industry?: string; search?: string; }
export interface ContactFilters extends PageFilters { account_id?: string; owner_id?: string; engagement_min?: number; search?: string; }
export interface OpportunityFilters extends PageFilters { status?: OpportunityStatus; stage?: OpportunityStage; owner_id?: string; account_id?: string; close_date_from?: string; close_date_to?: string; search?: string; }
export interface ActivityFilters extends PageFilters { related_to_type?: RelatedEntityType; related_to_id?: string; activity_type?: ActivityType; owner_id?: string; completed?: boolean; due_from?: string; due_to?: string; }
export interface ForecastFilters { owner_id?: string; period?: number; }
export interface PredictionRequest { period?: number; }

export const MODULE_API_PREFIX = '/api/v2/crm';
export const ENDPOINTS = {
  LEADS: { LIST: `${MODULE_API_PREFIX}/leads/`, CREATE: `${MODULE_API_PREFIX}/leads/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/` as const, TRANSITION: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/transition/` as const, CONVERT: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/convert/` as const, SCORE: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/score/` as const },
  ACCOUNTS: { LIST: `${MODULE_API_PREFIX}/accounts/`, CREATE: `${MODULE_API_PREFIX}/accounts/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const, HIERARCHY: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/hierarchy/` as const, DUPLICATES: `${MODULE_API_PREFIX}/accounts/duplicates/` },
  CONTACTS: { LIST: `${MODULE_API_PREFIX}/contacts/`, CREATE: `${MODULE_API_PREFIX}/contacts/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/contacts/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/contacts/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/contacts/${id}/` as const },
  OPPORTUNITIES: { LIST: `${MODULE_API_PREFIX}/opportunities/`, CREATE: `${MODULE_API_PREFIX}/opportunities/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/` as const, TRANSITION: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/transition/` as const, CLOSE_WON: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/close-won/` as const, CLOSE_LOST: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/close-lost/` as const },
  ACTIVITIES: { LIST: `${MODULE_API_PREFIX}/activities/`, CREATE: `${MODULE_API_PREFIX}/activities/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/activities/${id}/` as const, UPDATE: (id: string) => `${MODULE_API_PREFIX}/activities/${id}/` as const, DELETE: (id: string) => `${MODULE_API_PREFIX}/activities/${id}/` as const, COMPLETE: (id: string) => `${MODULE_API_PREFIX}/activities/${id}/complete/` as const },
  FORECASTING: { PIPELINE: `${MODULE_API_PREFIX}/forecasting/pipeline/`, WIN_RATE: `${MODULE_API_PREFIX}/forecasting/win-rate/`, BY_STAGE: `${MODULE_API_PREFIX}/forecasting/by-stage/`, PREDICT: `${MODULE_API_PREFIX}/forecasting/predict/` },
  JOBS: { DETAIL: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/` as const },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function entity(value: unknown): value is MutableEntityRead { return object(value) && typeof value.id === 'string' && typeof value.version === 'number' && typeof value.created_at === 'string'; }
export function isV2Envelope(value: unknown): value is V2Envelope<unknown> { return object(value) && 'data' in value && object(value.meta) && typeof value.meta.correlation_id === 'string' && typeof value.meta.timestamp === 'string'; }
export function isV2PageEnvelope(value: unknown): value is V2PageEnvelope<unknown> { if (!isV2Envelope(value) || !Array.isArray(value.data)) return false; const meta: unknown = value.meta; return object(meta) && object(meta.pagination) && typeof meta.pagination.count === 'number'; }
export function isLead(value: unknown): value is Lead { return entity(value) && typeof (value as Lead).last_name === 'string' && typeof (value as Lead).score === 'number'; }
export function isAccount(value: unknown): value is Account { return entity(value) && typeof (value as Account).name === 'string' && typeof (value as Account).account_type === 'string'; }
export function isContact(value: unknown): value is Contact { return entity(value) && typeof (value as Contact).account_id === 'string' && typeof (value as Contact).last_name === 'string'; }
export function isOpportunity(value: unknown): value is Opportunity { return entity(value) && typeof (value as Opportunity).account_id === 'string' && typeof (value as Opportunity).stage === 'string'; }
export function isActivity(value: unknown): value is Activity { return entity(value) && typeof (value as Activity).subject === 'string' && typeof (value as Activity).related_to_id === 'string'; }
