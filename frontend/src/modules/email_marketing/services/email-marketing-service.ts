/** Sole HTTP boundary for email marketing. Every successful body is validated. */
import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS, isApiV2Envelope, isApiV2Page, isAsyncJob, isCampaignAnalytics,
  isCampaignDetail, isCampaignSummary, isConsentDetail, isConsentSummary,
  isDeliveryDetail, isDeliverySummary, isHealth, isRecipientDetail,
  isRecipientSummary, isRenderedEmail, isSuppressionDetail, isSuppressionSummary,
  isTemplateDetail, isTemplateSummary,
  isEmailMarketingConfiguration,
  isEmailMarketingConfigurationPreview, isEmailMarketingConfigurationVersion,
  isPublicUnsubscribeResponse,
  type AsyncJobSummary, type CampaignAnalytics, type CampaignCreateInput,
  type CampaignFilters, type CampaignRecipientDetail, type CampaignRecipientSummary,
  type CampaignUpdateInput, type CloneTemplateInput, type ConsentCreateInput,
  type ConsentFilters, type ConsentRecordDetail, type ConsentRecordSummary,
  type ConsentRevokeInput, type DeliveryAttemptDetail, type DeliveryAttemptSummary,
  type DeliveryFilters, type EmailCampaignDetail, type EmailCampaignSummary,
  type EmailTemplateDetail, type EmailTemplateSummary, type GovernedResult,
  type IdempotentActionInput, type ModuleHealth, type PaginatedResult,
  type RecipientFilters, type RenderedEmail, type ScheduleCampaignInput,
  type SendCampaignInput, type PublicUnsubscribeInput, type PublicUnsubscribeResponse,
  type SuppressionCreateInput, type SuppressionDeactivateInput,
  type SuppressionEntryDetail, type SuppressionEntrySummary, type SuppressionFilters,
  type TemplateCreateInput, type TemplateFilters, type TemplatePreviewInput,
  type TemplateUpdateInput, type TransitionInput,
  type ConfigurationPreviewInput, type ConfigurationRollbackInput,
  type ConfigurationWriteInput, type EmailMarketingConfiguration,
  type EmailMarketingConfigurationDocument, type EmailMarketingConfigurationPreview,
  type EmailMarketingConfigurationVersion,
} from '../contracts';

type Guard<T> = (value: unknown) => value is T;
const malformed = (message: string, correlationId?: string) => new ApiError(message, 502, undefined, 'MALFORMED_RESPONSE', correlationId);

export function unwrapEnvelope<T>(value: unknown, guard: Guard<T>): GovernedResult<T> {
  if (!isApiV2Envelope(value)) throw malformed('Email marketing returned a malformed governed envelope.');
  if (!guard(value.data)) throw malformed('Email marketing returned data that violates its v2 contract.', value.meta.correlation_id);
  return { data: value.data, correlationId: value.meta.correlation_id, timestamp: value.meta.timestamp };
}

export function unwrapPage<T>(value: unknown, guard: Guard<T>): PaginatedResult<T> {
  if (!isApiV2Page(value)) throw malformed('Email marketing omitted valid pagination metadata.');
  if (!value.data.every(guard)) throw malformed('Email marketing returned malformed list data.', value.meta.correlation_id);
  return { items: value.data, pagination: value.meta.pagination, correlationId: value.meta.correlation_id, timestamp: value.meta.timestamp };
}

export function buildQuery(path: string, filters: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

const getOne = async <T>(path: string, guard: Guard<T>) => unwrapEnvelope(await apiClient.get<unknown>(path), guard);
const getPage = async <T>(path: string, filters: object, guard: Guard<T>) => unwrapPage(await apiClient.get<unknown>(buildQuery(path, filters)), guard);
const postOne = async <T>(path: string, input: unknown, guard: Guard<T>) => unwrapEnvelope(await apiClient.post<unknown>(path, input), guard);
const postIdempotentCreate = async <T>(path: string, input: unknown, guard: Guard<T>) => unwrapEnvelope(
  await apiClient.post<unknown>(path, input, { headers: { 'Idempotency-Key': crypto.randomUUID() } }),
  guard,
);
const putOne = async <T>(path: string, input: unknown, guard: Guard<T>) => unwrapEnvelope(await apiClient.put<unknown>(path, input), guard);
const patchOne = async <T>(path: string, input: unknown, guard: Guard<T>) => unwrapEnvelope(await apiClient.patch<unknown>(path, input), guard);

export const EMAIL_MARKETING_QUERY_KEYS = {
  all: ['email-marketing'] as const,
  campaigns: (filters: CampaignFilters = {}) => ['email-marketing', 'campaigns', filters] as const,
  campaign: (id: string) => ['email-marketing', 'campaign', id] as const,
  analytics: (id: string) => ['email-marketing', 'analytics', id] as const,
  templates: (filters: TemplateFilters = {}) => ['email-marketing', 'templates', filters] as const,
  template: (id: string) => ['email-marketing', 'template', id] as const,
  recipients: (filters: RecipientFilters = {}) => ['email-marketing', 'recipients', filters] as const,
  recipient: (id: string) => ['email-marketing', 'recipient', id] as const,
  deliveries: (filters: DeliveryFilters = {}) => ['email-marketing', 'deliveries', filters] as const,
  delivery: (id: string) => ['email-marketing', 'delivery', id] as const,
  suppressions: (filters: SuppressionFilters = {}) => ['email-marketing', 'suppressions', filters] as const,
  suppression: (id: string) => ['email-marketing', 'suppression', id] as const,
  consents: (filters: ConsentFilters = {}) => ['email-marketing', 'consents', filters] as const,
  consent: (id: string) => ['email-marketing', 'consent', id] as const,
  configuration: ['email-marketing', 'configuration'] as const,
  configurationHistory: ['email-marketing', 'configuration', 'history'] as const,
  health: ['email-marketing', 'health'] as const,
};

export const emailMarketingService = {
  campaigns: {
    list: (filters: CampaignFilters = {}): Promise<PaginatedResult<EmailCampaignSummary>> => getPage(ENDPOINTS.CAMPAIGNS.LIST, filters, isCampaignSummary),
    get: (id: string): Promise<GovernedResult<EmailCampaignDetail>> => getOne(ENDPOINTS.CAMPAIGNS.DETAIL(id), isCampaignDetail),
    create: (input: CampaignCreateInput): Promise<GovernedResult<EmailCampaignDetail>> => postIdempotentCreate(ENDPOINTS.CAMPAIGNS.CREATE, input, isCampaignDetail),
    update: (id: string, input: CampaignUpdateInput): Promise<GovernedResult<EmailCampaignDetail>> => patchOne(ENDPOINTS.CAMPAIGNS.UPDATE(id), input, isCampaignDetail),
    delete: (id: string): Promise<void> => apiClient.delete<void>(ENDPOINTS.CAMPAIGNS.DELETE(id)),
    resolveAudience: (id: string, input: IdempotentActionInput): Promise<GovernedResult<AsyncJobSummary>> => postOne(ENDPOINTS.CAMPAIGNS.RESOLVE_AUDIENCE(id), input, isAsyncJob),
    schedule: (id: string, input: ScheduleCampaignInput): Promise<GovernedResult<EmailCampaignDetail>> => postOne(ENDPOINTS.CAMPAIGNS.SCHEDULE(id), input, isCampaignDetail),
    unschedule: (id: string, input: IdempotentActionInput): Promise<GovernedResult<EmailCampaignDetail>> => postOne(ENDPOINTS.CAMPAIGNS.UNSCHEDULE(id), input, isCampaignDetail),
    send: (id: string, input: SendCampaignInput): Promise<GovernedResult<AsyncJobSummary>> => postOne(ENDPOINTS.CAMPAIGNS.SEND(id), input, isAsyncJob),
    pause: (id: string, input: TransitionInput): Promise<GovernedResult<EmailCampaignDetail>> => postOne(ENDPOINTS.CAMPAIGNS.PAUSE(id), input, isCampaignDetail),
    resume: (id: string, input: IdempotentActionInput): Promise<GovernedResult<AsyncJobSummary>> => postOne(ENDPOINTS.CAMPAIGNS.RESUME(id), input, isAsyncJob),
    cancel: (id: string, input: TransitionInput): Promise<GovernedResult<EmailCampaignDetail>> => postOne(ENDPOINTS.CAMPAIGNS.CANCEL(id), input, isCampaignDetail),
    analytics: (id: string): Promise<GovernedResult<CampaignAnalytics>> => getOne(ENDPOINTS.CAMPAIGNS.ANALYTICS(id), isCampaignAnalytics),
  },
  templates: {
    list: (filters: TemplateFilters = {}): Promise<PaginatedResult<EmailTemplateSummary>> => getPage(ENDPOINTS.TEMPLATES.LIST, filters, isTemplateSummary),
    get: (id: string): Promise<GovernedResult<EmailTemplateDetail>> => getOne(ENDPOINTS.TEMPLATES.DETAIL(id), isTemplateDetail),
    create: (input: TemplateCreateInput): Promise<GovernedResult<EmailTemplateDetail>> => postIdempotentCreate(ENDPOINTS.TEMPLATES.CREATE, input, isTemplateDetail),
    update: (id: string, input: TemplateUpdateInput): Promise<GovernedResult<EmailTemplateDetail>> => patchOne(ENDPOINTS.TEMPLATES.UPDATE(id), input, isTemplateDetail),
    delete: (id: string): Promise<void> => apiClient.delete<void>(ENDPOINTS.TEMPLATES.DELETE(id)),
    activate: (id: string, input: IdempotentActionInput): Promise<GovernedResult<EmailTemplateDetail>> => postOne(ENDPOINTS.TEMPLATES.ACTIVATE(id), input, isTemplateDetail),
    archive: (id: string, input: IdempotentActionInput): Promise<GovernedResult<EmailTemplateDetail>> => postOne(ENDPOINTS.TEMPLATES.ARCHIVE(id), input, isTemplateDetail),
    clone: (id: string, input: CloneTemplateInput): Promise<GovernedResult<EmailTemplateDetail>> => postOne(ENDPOINTS.TEMPLATES.CLONE(id), input, isTemplateDetail),
    preview: (id: string, input: TemplatePreviewInput): Promise<GovernedResult<RenderedEmail>> => postOne(ENDPOINTS.TEMPLATES.PREVIEW(id), input, isRenderedEmail),
  },
  recipients: {
    list: (filters: RecipientFilters = {}): Promise<PaginatedResult<CampaignRecipientSummary>> => getPage(ENDPOINTS.RECIPIENTS.LIST, filters, isRecipientSummary),
    get: (id: string): Promise<GovernedResult<CampaignRecipientDetail>> => getOne(ENDPOINTS.RECIPIENTS.DETAIL(id), isRecipientDetail),
    retry: (id: string, input: IdempotentActionInput): Promise<GovernedResult<AsyncJobSummary>> => postOne(ENDPOINTS.RECIPIENTS.RETRY(id), input, isAsyncJob),
  },
  deliveries: {
    list: (filters: DeliveryFilters = {}): Promise<PaginatedResult<DeliveryAttemptSummary>> => getPage(ENDPOINTS.DELIVERIES.LIST, filters, isDeliverySummary),
    get: (id: string): Promise<GovernedResult<DeliveryAttemptDetail>> => getOne(ENDPOINTS.DELIVERIES.DETAIL(id), isDeliveryDetail),
  },
  suppressions: {
    list: (filters: SuppressionFilters = {}): Promise<PaginatedResult<SuppressionEntrySummary>> => getPage(ENDPOINTS.SUPPRESSIONS.LIST, filters, isSuppressionSummary),
    get: (id: string): Promise<GovernedResult<SuppressionEntryDetail>> => getOne(ENDPOINTS.SUPPRESSIONS.DETAIL(id), isSuppressionDetail),
    create: (input: SuppressionCreateInput): Promise<GovernedResult<SuppressionEntryDetail>> => postIdempotentCreate(ENDPOINTS.SUPPRESSIONS.CREATE, input, isSuppressionDetail),
    deactivate: (id: string, input: SuppressionDeactivateInput): Promise<GovernedResult<SuppressionEntryDetail>> => postOne(ENDPOINTS.SUPPRESSIONS.DEACTIVATE(id), input, isSuppressionDetail),
  },
  consents: {
    list: (filters: ConsentFilters = {}): Promise<PaginatedResult<ConsentRecordSummary>> => getPage(ENDPOINTS.CONSENTS.LIST, filters, isConsentSummary),
    get: (id: string): Promise<GovernedResult<ConsentRecordDetail>> => getOne(ENDPOINTS.CONSENTS.DETAIL(id), isConsentDetail),
    create: (input: ConsentCreateInput): Promise<GovernedResult<ConsentRecordDetail>> => postIdempotentCreate(ENDPOINTS.CONSENTS.CREATE, input, isConsentDetail),
    revoke: (input: ConsentRevokeInput): Promise<GovernedResult<ConsentRecordDetail>> => postOne(ENDPOINTS.CONSENTS.REVOKE, input, isConsentDetail),
  },
  configuration: {
    current: (): Promise<GovernedResult<EmailMarketingConfiguration>> => getOne(ENDPOINTS.CONFIGURATION.CURRENT, isEmailMarketingConfiguration),
    update: (input: ConfigurationWriteInput): Promise<GovernedResult<EmailMarketingConfiguration>> => putOne(ENDPOINTS.CONFIGURATION.CURRENT, input, isEmailMarketingConfiguration),
    preview: (input: ConfigurationPreviewInput): Promise<GovernedResult<EmailMarketingConfigurationPreview>> => postOne(ENDPOINTS.CONFIGURATION.PREVIEW, input, isEmailMarketingConfigurationPreview),
    history: (): Promise<GovernedResult<readonly EmailMarketingConfigurationVersion[]>> => getOne(
      ENDPOINTS.CONFIGURATION.HISTORY,
      (value): value is readonly EmailMarketingConfigurationVersion[] => Array.isArray(value) && value.every(isEmailMarketingConfigurationVersion),
    ),
    rollback: (input: ConfigurationRollbackInput): Promise<GovernedResult<EmailMarketingConfiguration>> => postOne(ENDPOINTS.CONFIGURATION.ROLLBACK, input, isEmailMarketingConfiguration),
    importDocument: (input: ConfigurationWriteInput): Promise<GovernedResult<EmailMarketingConfiguration>> => postOne(ENDPOINTS.CONFIGURATION.IMPORT, input, isEmailMarketingConfiguration),
    exportDocument: (): Promise<GovernedResult<EmailMarketingConfiguration>> => getOne(ENDPOINTS.CONFIGURATION.EXPORT, isEmailMarketingConfiguration),
  },
  public: {
    unsubscribe: (input: PublicUnsubscribeInput): Promise<GovernedResult<PublicUnsubscribeResponse>> => postOne(ENDPOINTS.PUBLIC_UNSUBSCRIBE, input, isPublicUnsubscribeResponse),
    openUrl: (token: string): string => ENDPOINTS.TRACK_OPEN(token),
    clickUrl: (token: string): string => ENDPOINTS.TRACK_CLICK(token),
  },
  health: (): Promise<GovernedResult<ModuleHealth>> => getOne(ENDPOINTS.HEALTH, isHealth),
} as const;
