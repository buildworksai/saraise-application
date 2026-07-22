/** Typed, governed CRM v2 client. */
import { ApiError as ClientApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  isAccount,
  isActivity,
  isContact,
  isLead,
  isOpportunity,
  isV2Envelope,
  isV2PageEnvelope,
} from '../contracts';
import type {
  Account, AccountCreate, AccountFilters, AccountHierarchyNode, AccountUpdate, Activity,
  ActivityCreate, ActivityFilters, ActivityUpdate, AsyncJob, CloseLostRequest, CloseWonRequest,
  CompleteActivityRequest, Contact, ContactCreate, ContactFilters, ContactUpdate, ConversionResult,
  DuplicateAccountResult, Forecast, ForecastFilters, Lead, LeadConversionRequest, LeadCreate,
  LeadFilters, LeadScoringResponse, LeadTransitionRequest, LeadUpdate, Opportunity,
  OpportunityCreate, OpportunityFilters, OpportunityTransitionRequest, OpportunityUpdate,
  OpportunityOpenStage, OpportunityTransitionCommand, PaginationMeta, Prediction, PredictionRequest, StageForecast, WinRate,
} from '../contracts';

export type CrmErrorKind = 'authentication' | 'permission' | 'not_found' | 'conflict' | 'validation' | 'rate_limit' | 'unavailable' | 'network' | 'invalid_response' | 'unexpected';

export class CrmApiError extends Error {
  constructor(
    message: string,
    readonly kind: CrmErrorKind,
    readonly status: number | null,
    readonly code: string,
    readonly correlationId: string | null,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = 'CrmApiError';
  }
}

export interface PageResult<T> {
  readonly items: readonly T[];
  readonly pagination: PaginationMeta & { readonly total_count: number };
  readonly correlationId: string;
}

type Guard<T> = (value: unknown) => value is T;

function kindForStatus(status: number): CrmErrorKind {
  if (status === 401) return 'authentication';
  if (status === 403) return 'permission';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 400 || status === 422) return 'validation';
  if (status === 429) return 'rate_limit';
  if (status === 503) return 'unavailable';
  return 'unexpected';
}

async function governed<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (error instanceof CrmApiError) throw error;
    if (error instanceof ClientApiError) {
      throw new CrmApiError(error.message, kindForStatus(error.status), error.status, error.code ?? 'request_failed', error.correlationId ?? null, error.details);
    }
    if (error instanceof TypeError) {
      throw new CrmApiError('CRM could not be reached. Check your connection and retry.', 'network', null, 'network_error', null);
    }
    throw new CrmApiError(error instanceof Error ? error.message : 'Unexpected CRM failure.', 'unexpected', null, 'unexpected_error', null);
  }
}

function decode<T>(value: unknown, guard: Guard<T>, label: string): T {
  if (!isV2Envelope(value) || !guard(value.data)) {
    throw new CrmApiError(`CRM returned an invalid ${label} response.`, 'invalid_response', null, 'invalid_response', isV2Envelope(value) ? value.meta.correlation_id : null, value);
  }
  return value.data;
}

function decodePage<T>(value: unknown, guard: Guard<T>, label: string): PageResult<T> {
  if (!isV2PageEnvelope(value) || !value.data.every(guard)) {
    throw new CrmApiError(`CRM returned an invalid ${label} page.`, 'invalid_response', null, 'invalid_response', isV2Envelope(value) ? value.meta.correlation_id : null, value);
  }
  return { items: value.data, pagination: { ...value.meta.pagination, total_count: value.meta.pagination.count }, correlationId: value.meta.correlation_id };
}

const isObject = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const isJob: Guard<AsyncJob> = (value): value is AsyncJob => isObject(value) && typeof value.id === 'string' && typeof value.status === 'string';
const isForecast: Guard<Forecast> = (value): value is Forecast => isObject(value) && Array.isArray(value.currencies) && typeof value.period_days === 'number';
const isWinRate: Guard<WinRate> = (value): value is WinRate => isObject(value) && typeof value.total_closed === 'number';
const isPrediction: Guard<Prediction> = (value): value is Prediction => isObject(value) && typeof value.amount === 'string' && typeof value.currency === 'string' && typeof value.provider === 'string';
const isHierarchy: Guard<AccountHierarchyNode> = (value): value is AccountHierarchyNode => isObject(value) && typeof value.id === 'string' && Array.isArray(value.children);
const isDuplicates: Guard<DuplicateAccountResult> = (value): value is DuplicateAccountResult => isObject(value) && Array.isArray(value.local_matches) && Array.isArray(value.external_matches) && typeof value.enrichment_status === 'string';
const isConversion: Guard<ConversionResult> = (value): value is ConversionResult => isObject(value) && isLead(value.lead) && isAccount(value.account) && isOpportunity(value.opportunity);
const isScore: Guard<LeadScoringResponse> = isLead;
const isStageForecastArray: Guard<readonly StageForecast[]> = (value): value is readonly StageForecast[] => Array.isArray(value) && value.every((entry) => isObject(entry) && typeof entry.stage === 'string' && typeof entry.currency === 'string');

function query(endpoint: string, filters?: object): string {
  if (!filters) return endpoint;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const serialized = params.toString();
  return serialized ? `${endpoint}?${serialized}` : endpoint;
}

const ifMatch = (version: number): RequestInit => ({ headers: { 'If-Match': String(version) } });
const stageCommand = (stage: OpportunityOpenStage): OpportunityTransitionCommand => {
  const commands = { qualification: 'advance_to_qualification', needs_analysis: 'advance_to_needs_analysis', proposal: 'advance_to_proposal', negotiation: 'advance_to_negotiation', prospecting: 'reopen_to_prospecting' } as const;
  return commands[stage];
};

export const crmKeys = {
  all: ['crm'] as const,
  leads: (filters?: LeadFilters) => ['crm', 'leads', filters ?? {}] as const,
  lead: (id: string) => ['crm', 'lead', id] as const,
  accounts: (filters?: AccountFilters) => ['crm', 'accounts', filters ?? {}] as const,
  account: (id: string) => ['crm', 'account', id] as const,
  contacts: (filters?: ContactFilters) => ['crm', 'contacts', filters ?? {}] as const,
  contact: (id: string) => ['crm', 'contact', id] as const,
  opportunities: (filters?: OpportunityFilters) => ['crm', 'opportunities', filters ?? {}] as const,
  opportunity: (id: string) => ['crm', 'opportunity', id] as const,
  activities: (filters?: ActivityFilters) => ['crm', 'activities', filters ?? {}] as const,
  activity: (id: string) => ['crm', 'activity', id] as const,
  forecast: (kind: string, filters?: ForecastFilters) => ['crm', 'forecast', kind, filters ?? {}] as const,
};

export const crmService = {
  listLeads: (filters?: LeadFilters) => governed(async () => decodePage(await apiClient.get(query(ENDPOINTS.LEADS.LIST, filters)), isLead, 'lead')),
  getLead: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.LEADS.DETAIL(id)), isLead, 'lead')),
  createLead: (payload: LeadCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.LEADS.CREATE, payload), isLead, 'lead')),
  updateLead: (id: string, payload: LeadUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.LEADS.UPDATE(id), payload, ifMatch(payload.version)), isLead, 'lead')),
  deleteLead: (id: string, version: number) => governed(async () => { await apiClient.delete(ENDPOINTS.LEADS.DELETE(id), ifMatch(version)); }),
  transitionLead: (id: string, payload: LeadTransitionRequest) => governed(async () => decode(await apiClient.post(ENDPOINTS.LEADS.TRANSITION(id), payload, ifMatch(payload.expected_version)), isLead, 'lead')),
  convertLead: (id: string, payload: LeadConversionRequest | (Omit<LeadConversionRequest, 'name' | 'create_new_account'> & { opportunity_name?: string; create_account?: { name: string }; contact_decision?: string })) => governed(async () => { const name = 'opportunity_name' in payload ? payload.opportunity_name : ('name' in payload ? payload.name : undefined); const createNew = 'create_account' in payload ? !payload.account_id : ('create_new_account' in payload ? payload.create_new_account : undefined); const normalized: LeadConversionRequest = { amount: payload.amount, currency: payload.currency, close_date: payload.close_date, name, account_id: payload.account_id, create_new_account: createNew, transition_key: payload.transition_key, expected_version: payload.expected_version }; return decode(await apiClient.post(ENDPOINTS.LEADS.CONVERT(id), normalized, ifMatch(payload.expected_version)), isConversion, 'lead conversion'); }),
  scoreLead: (id: string, expectedVersion?: number) => governed(async () => { void expectedVersion; return decode(await apiClient.post(ENDPOINTS.LEADS.SCORE(id), {}), isScore, 'lead score'); }),

  listAccounts: (filters?: AccountFilters) => governed(async () => decodePage(await apiClient.get(query(ENDPOINTS.ACCOUNTS.LIST, filters)), isAccount, 'account')),
  getAccount: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.ACCOUNTS.DETAIL(id)), isAccount, 'account')),
  createAccount: (payload: AccountCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.ACCOUNTS.CREATE, payload), isAccount, 'account')),
  updateAccount: (id: string, payload: AccountUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.ACCOUNTS.UPDATE(id), payload, ifMatch(payload.version)), isAccount, 'account')),
  deleteAccount: (id: string, version: number) => governed(async () => { await apiClient.delete(ENDPOINTS.ACCOUNTS.DELETE(id), ifMatch(version)); }),
  getAccountHierarchy: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.ACCOUNTS.HIERARCHY(id)), isHierarchy, 'account hierarchy')),
  findAccountDuplicates: (name: string, website?: string) => governed(async () => decode(await apiClient.get(query(ENDPOINTS.ACCOUNTS.DUPLICATES, { name, website })), isDuplicates, 'account duplicate')),

  listContacts: (filters?: ContactFilters) => governed(async () => decodePage(await apiClient.get(query(ENDPOINTS.CONTACTS.LIST, filters)), isContact, 'contact')),
  getContact: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.CONTACTS.DETAIL(id)), isContact, 'contact')),
  createContact: (payload: ContactCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.CONTACTS.CREATE, payload), isContact, 'contact')),
  updateContact: (id: string, payload: ContactUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.CONTACTS.UPDATE(id), payload, ifMatch(payload.version)), isContact, 'contact')),
  deleteContact: (id: string, version: number) => governed(async () => { await apiClient.delete(ENDPOINTS.CONTACTS.DELETE(id), ifMatch(version)); }),

  listOpportunities: (filters?: OpportunityFilters) => governed(async () => decodePage(await apiClient.get(query(ENDPOINTS.OPPORTUNITIES.LIST, filters)), isOpportunity, 'opportunity')),
  getOpportunity: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.OPPORTUNITIES.DETAIL(id)), isOpportunity, 'opportunity')),
  createOpportunity: (payload: OpportunityCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.OPPORTUNITIES.CREATE, payload), isOpportunity, 'opportunity')),
  updateOpportunity: (id: string, payload: OpportunityUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.OPPORTUNITIES.UPDATE(id), payload, ifMatch(payload.version)), isOpportunity, 'opportunity')),
  deleteOpportunity: (id: string, version: number) => governed(async () => { await apiClient.delete(ENDPOINTS.OPPORTUNITIES.DELETE(id), ifMatch(version)); }),
  transitionOpportunity: (id: string, payload: OpportunityTransitionRequest | { target_stage: OpportunityOpenStage; transition_key: string; expected_version: number; reason?: string }) => governed(async () => { const normalized: OpportunityTransitionRequest = 'target_stage' in payload ? { command: stageCommand(payload.target_stage), transition_key: payload.transition_key, expected_version: payload.expected_version, reason: payload.reason } : payload; return decode(await apiClient.post(ENDPOINTS.OPPORTUNITIES.TRANSITION(id), normalized, ifMatch(payload.expected_version)), isOpportunity, 'opportunity'); }),
  closeOpportunityWon: (id: string, payload: CloseWonRequest | { expected_version: number; transition_key: string; confirmation: true }) => governed(async () => { const normalized: CloseWonRequest = { expected_version: payload.expected_version, transition_key: payload.transition_key, confirmed: 'confirmation' in payload ? payload.confirmation : payload.confirmed }; return decode(await apiClient.post(ENDPOINTS.OPPORTUNITIES.CLOSE_WON(id), normalized, ifMatch(payload.expected_version)), isOpportunity, 'opportunity'); }),
  closeOpportunityLost: (id: string, payload: CloseLostRequest) => governed(async () => decode(await apiClient.post(ENDPOINTS.OPPORTUNITIES.CLOSE_LOST(id), payload, ifMatch(payload.expected_version)), isOpportunity, 'opportunity')),

  listActivities: (filters?: ActivityFilters) => governed(async () => decodePage(await apiClient.get(query(ENDPOINTS.ACTIVITIES.LIST, filters)), isActivity, 'activity')),
  getActivity: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.ACTIVITIES.DETAIL(id)), isActivity, 'activity')),
  createActivity: (payload: ActivityCreate) => governed(async () => decode(await apiClient.post(ENDPOINTS.ACTIVITIES.CREATE, payload), isActivity, 'activity')),
  updateActivity: (id: string, payload: ActivityUpdate) => governed(async () => decode(await apiClient.patch(ENDPOINTS.ACTIVITIES.UPDATE(id), payload, ifMatch(payload.version)), isActivity, 'activity')),
  deleteActivity: (id: string, version: number) => governed(async () => { await apiClient.delete(ENDPOINTS.ACTIVITIES.DELETE(id), ifMatch(version)); }),
  completeActivity: (id: string, payload: CompleteActivityRequest | { expected_version: number; idempotency_key: string }) => governed(async () => { const normalized: CompleteActivityRequest = { expected_version: payload.expected_version, transition_key: 'idempotency_key' in payload ? payload.idempotency_key : payload.transition_key }; return decode(await apiClient.post(ENDPOINTS.ACTIVITIES.COMPLETE(id), normalized, ifMatch(payload.expected_version)), isActivity, 'activity'); }),

  getPipeline: (filters?: ForecastFilters) => governed(async () => decode(await apiClient.get(query(ENDPOINTS.FORECASTING.PIPELINE, filters)), isForecast, 'pipeline forecast')),
  getWinRate: (filters?: ForecastFilters) => governed(async () => decode(await apiClient.get(query(ENDPOINTS.FORECASTING.WIN_RATE, filters)), isWinRate, 'win-rate forecast')),
  getForecastByStage: (filters?: ForecastFilters) => governed(async () => decode(await apiClient.get(query(ENDPOINTS.FORECASTING.BY_STAGE, filters)), isStageForecastArray, 'stage forecast')),
  predictRevenue: (payload?: PredictionRequest) => governed(async () => decode(await apiClient.post(ENDPOINTS.FORECASTING.PREDICT, { period: payload?.period }), isPrediction, 'revenue prediction')),
  getAIPrediction: (filters?: ForecastFilters) => crmService.predictRevenue(filters),
  getJob: (id: string) => governed(async () => decode(await apiClient.get(ENDPOINTS.JOBS.DETAIL(id)), isJob, 'job')),
};

export type { Account, AccountCreate, AccountUpdate, Activity, ActivityCreate, ActivityUpdate, Contact, ContactCreate, ContactUpdate, Forecast, Lead, LeadCreate, LeadUpdate, Opportunity, OpportunityCreate, OpportunityUpdate, Prediction as AIPrediction, WinRate };
