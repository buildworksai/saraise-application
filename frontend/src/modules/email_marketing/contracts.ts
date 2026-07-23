/** Public, runtime-validated contract for the governed email-marketing v2 API. */
export type UUID = string;
export type ISODateTime = string;
export type CampaignStatus = 'draft' | 'scheduled' | 'queueing' | 'sending' | 'paused' | 'sent' | 'failed' | 'cancelled';
export type TemplateStatus = 'draft' | 'active' | 'archived';
export type RecipientStatus = 'resolved' | 'suppressed' | 'queued' | 'sending' | 'accepted' | 'delivered' | 'bounced' | 'failed' | 'unsubscribed' | 'complained' | 'cancelled';
export type DeliveryAttemptStatus = 'queued' | 'sending' | 'accepted' | 'deferred' | 'delivered' | 'bounced' | 'failed' | 'timed_out';
export type DeliveryEventType = 'accepted' | 'delivered' | 'opened' | 'clicked' | 'deferred' | 'bounced' | 'complained' | 'unsubscribed';
export type ConsentStatus = 'granted' | 'revoked';
export type ConsentLawfulBasis = 'consent' | 'legitimate_interest' | 'contractual';
export type ConsentSource = 'form' | 'import' | 'api' | 'crm_event' | 'administrator' | 'unsubscribe';
export type SuppressionScope = 'marketing' | 'all';
export type SuppressionReason = 'unsubscribe' | 'hard_bounce' | 'complaint' | 'manual' | 'legal';
export type SuppressionSource = 'user' | 'provider_event' | 'administrator' | 'migration';
export type HealthState = 'ready' | 'degraded' | 'unhealthy';
export type Ordering<T extends string> = T | `-${T}`;

export interface ApiV2PaginationMeta { readonly count: number; readonly page: number; readonly page_size: number; readonly total_pages: number; readonly has_next: boolean; readonly has_previous: boolean }
export interface ApiV2Meta { readonly correlation_id: string; readonly timestamp: ISODateTime; readonly pagination?: ApiV2PaginationMeta }
export interface ApiV2Envelope<T> { readonly data: T; readonly meta: ApiV2Meta }
export interface ApiV2Page<T> extends ApiV2Envelope<readonly T[]> { readonly meta: ApiV2Meta & { readonly pagination: ApiV2PaginationMeta } }
export interface GovernedApiError { readonly error: { readonly code: string; readonly message: string; readonly detail: Readonly<Record<string, unknown>>; readonly correlation_id: string } }
export interface GovernedResult<T> { readonly data: T; readonly correlationId: string; readonly timestamp: ISODateTime }
export interface PaginatedResult<T> { readonly items: readonly T[]; readonly pagination: ApiV2PaginationMeta; readonly correlationId: string; readonly timestamp: ISODateTime }

export interface TransitionEvidence { readonly key: string; readonly action?: string; readonly from_state: string; readonly to_state: string; readonly occurred_at: ISODateTime; readonly actor_id: UUID | null; readonly correlation_id?: string; readonly reason?: string }
export interface AuditFields { readonly created_at: ISODateTime; readonly updated_at: ISODateTime; readonly created_by: UUID | null; readonly updated_by: UUID | null }

export interface EmailCampaignSummary {
  readonly id: UUID; readonly campaign_code: string; readonly campaign_name: string; readonly campaign_type: string; readonly subject: string; readonly status: CampaignStatus;
  readonly template_id: UUID | null; readonly scheduled_at: ISODateTime | null; readonly timezone: string; readonly resolved_recipient_count: number;
  readonly sent_count: number; readonly delivered_count: number; readonly opened_count: number; readonly clicked_count: number; readonly bounced_count: number; readonly failed_count: number;
  readonly created_at: ISODateTime; readonly updated_at: ISODateTime;
}
export interface EmailCampaignDetail extends EmailCampaignSummary, AuditFields {
  readonly description: string; readonly preview_text: string; readonly from_name: string; readonly from_email: string; readonly reply_to_email: string | null;
  readonly audience_definition: Readonly<Record<string, unknown>>; readonly audience_snapshot_at: ISODateTime | null; readonly queue_started_at: ISODateTime | null;
  readonly send_started_at: ISODateTime | null; readonly completed_at: ISODateTime | null; readonly content_snapshot_subject: string;
  readonly content_snapshot_html: string; readonly content_snapshot_text: string; readonly template_version_snapshot: number | null;
  readonly unique_opened_count: number; readonly unique_clicked_count: number; readonly unsubscribed_count: number; readonly complaint_count: number;
  readonly transition_history: readonly TransitionEvidence[]; readonly last_error_code: string; readonly last_error_detail: string; readonly is_deleted: boolean;
}
export interface CampaignCreateInput { readonly campaign_code: string; readonly campaign_name: string; readonly description?: string; readonly campaign_type?: string; readonly template_id?: UUID | null; readonly subject: string; readonly preview_text?: string; readonly from_name: string; readonly from_email: string; readonly reply_to_email?: string | null; readonly audience_definition: Readonly<Record<string, unknown>>; readonly timezone?: string }
export type CampaignUpdateInput = Partial<CampaignCreateInput>;
export interface ScheduleCampaignInput { readonly scheduled_at: ISODateTime; readonly timezone: string; readonly idempotency_key: string }
export interface IdempotentActionInput { readonly idempotency_key: string }
export interface SendCampaignInput extends IdempotentActionInput { readonly preflight_receipt: string }
export interface TransitionInput { readonly idempotency_key: string; readonly reason?: string }

export interface EmailTemplateSummary { readonly id: UUID; readonly template_code: string; readonly template_name: string; readonly category: string; readonly subject: string; readonly status: TemplateStatus; readonly version: number; readonly usage_count: number; readonly updated_at: ISODateTime }
export interface EmailTemplateDetail extends EmailTemplateSummary, AuditFields { readonly description: string; readonly preview_text: string; readonly body_html: string; readonly body_text: string; readonly design_json: Readonly<Record<string, unknown>>; readonly last_used_at: ISODateTime | null; readonly is_active: boolean; readonly is_deleted: boolean }
export interface TemplateCreateInput { readonly template_code: string; readonly template_name: string; readonly description?: string; readonly category?: string; readonly subject: string; readonly preview_text?: string; readonly body_html: string; readonly body_text?: string; readonly design_json: Readonly<Record<string, unknown>> }
export type TemplateUpdateInput = Partial<Omit<TemplateCreateInput, 'template_code'>>;
export interface CloneTemplateInput { readonly new_code: string }
export interface TemplatePreviewInput { readonly sample_data: Readonly<Record<string, unknown>> }
export interface RenderedEmail { readonly subject: string; readonly html: string; readonly text: string; readonly warnings: readonly string[] }

export interface AsyncJobSummary { readonly id: UUID; readonly job_type: string; readonly status: string; readonly idempotency_key: string; readonly created_at: ISODateTime; readonly correlation_id: string }
export interface EligibilityDecision { readonly eligible: boolean; readonly reason_code: string | null; readonly detail: string }
export interface CampaignPreflight { readonly content_valid: boolean; readonly receipt: string; readonly rendered: boolean; readonly resolved_count: number; readonly eligible_count: number; readonly suppressed_count: number; readonly consent_failure_count: number; readonly suppression_failure_count: number; readonly sender_healthy: boolean; readonly sender_detail: string; readonly quota_required: number; readonly quota_remaining: number | null; readonly scheduled_at: ISODateTime | null; readonly timezone: string; readonly blocking_reasons: readonly string[] }
export interface CampaignAnalytics { readonly campaign_id: UUID; readonly resolved: number; readonly eligible: number; readonly sent: number; readonly delivered: number; readonly unique_opened: number; readonly unique_clicked: number; readonly bounced: number; readonly failed: number; readonly unsubscribed: number; readonly complained: number; readonly delivery_rate: number; readonly unique_open_rate: number; readonly unique_click_rate: number; readonly bounce_rate: number; readonly counter_drift: Readonly<Record<string, number>>; readonly preflight: CampaignPreflight }

export interface CampaignRecipientSummary { readonly id: UUID; readonly campaign_id: UUID; readonly recipient_key: string | null; readonly email: string; readonly display_name: string; readonly status: RecipientStatus; readonly suppression_reason: string; readonly created_at: ISODateTime }
export interface CampaignRecipientDetail extends CampaignRecipientSummary { readonly personalization_data: Readonly<Record<string, unknown>>; readonly consent_record_id: UUID | null; readonly resolved_at: ISODateTime | null; readonly queued_at: ISODateTime | null; readonly accepted_at: ISODateTime | null; readonly delivered_at: ISODateTime | null; readonly failed_at: ISODateTime | null; readonly last_error_code: string; readonly transition_history: readonly TransitionEvidence[]; readonly delivery_attempts: readonly DeliveryAttemptSummary[]; readonly events: readonly DeliveryEvent[] }
export interface DeliveryAttemptSummary { readonly id: UUID; readonly recipient_id: UUID; readonly attempt_number: number; readonly status: DeliveryAttemptStatus; readonly error_code: string; readonly started_at: ISODateTime | null; readonly accepted_at: ISODateTime | null; readonly created_at: ISODateTime; readonly completed_at: ISODateTime | null }
export interface DeliveryAttemptDetail extends DeliveryAttemptSummary { readonly updated_at: ISODateTime; readonly events: readonly DeliveryEvent[] }
export interface DeliveryEvent { readonly id: UUID; readonly recipient_id: UUID; readonly attempt_id: UUID | null; readonly gateway_key: string; readonly provider_event_id: string; readonly event_type: DeliveryEventType; readonly occurred_at: ISODateTime; readonly link_url_hash: string; readonly bounce_class: '' | 'hard' | 'soft' | 'block'; readonly metadata: Readonly<Record<string, unknown>>; readonly correlation_id: string; readonly created_at: ISODateTime }

export interface SuppressionEntrySummary { readonly id: UUID; readonly email: string; readonly scope: SuppressionScope; readonly reason: SuppressionReason; readonly source: SuppressionSource; readonly active: boolean; readonly suppressed_at: ISODateTime; readonly expires_at: ISODateTime | null }
export interface SuppressionEntryDetail extends SuppressionEntrySummary, AuditFields { readonly evidence_event_id: UUID | null; readonly notes: string; readonly deactivated_at: ISODateTime | null; readonly deactivated_by: UUID | null }
export interface SuppressionCreateInput { readonly email: string; readonly scope: SuppressionScope; readonly reason: SuppressionReason; readonly source: SuppressionSource; readonly expires_at?: ISODateTime | null; readonly notes?: string }
export interface SuppressionDeactivateInput { readonly reason: string }

export interface ConsentRecordSummary { readonly id: UUID; readonly email: string; readonly purpose: string; readonly status: ConsentStatus; readonly lawful_basis: ConsentLawfulBasis; readonly source: ConsentSource; readonly notice_version: string; readonly captured_at: ISODateTime; readonly created_at: ISODateTime }
export interface ConsentRecordDetail extends ConsentRecordSummary { readonly actor_id: UUID | null; readonly supersedes_id: UUID | null }
export interface ConsentCreateInput { readonly email: string; readonly purpose?: string; readonly status: ConsentStatus; readonly lawful_basis: ConsentLawfulBasis; readonly source: ConsentSource; readonly notice_version: string }
export interface ConsentRevokeInput { readonly email: string; readonly purpose: string; readonly source: ConsentSource; readonly notice_version?: string }
export interface PublicUnsubscribeInput { readonly token: string; readonly occurred_at: ISODateTime }
export interface PublicUnsubscribeResponse { readonly suppression_id: UUID; readonly status: 'unsubscribed' }

export type ConfigurationStatusTone = 'success' | 'error' | 'warning' | 'neutral';
export interface EmailMarketingDefaultsConfiguration {
  readonly campaign_type: string;
  readonly audience_resolver: string;
  readonly delivery_gateway: string;
  readonly timezone: string;
  readonly template_category: string;
  readonly consent_purpose: string;
  readonly audience_schema_version: number;
}
export interface EmailMarketingLimitsConfiguration {
  readonly json_max_depth: number;
  readonly json_max_keys: number;
  readonly evidence_json_max_bytes: number;
  readonly evidence_json_max_depth: number;
  readonly evidence_json_max_keys: number;
  readonly template_design_max_bytes: number;
  readonly audience_definition_max_bytes: number;
  readonly consent_evidence_max_bytes: number;
  readonly personalization_max_bytes: number;
  readonly serializer_json_max_bytes: number;
  readonly serializer_json_max_depth: number;
  readonly serializer_json_max_keys: number;
  readonly json_key_max_length: number;
  readonly personalization_max_keys: number;
  readonly recipient_count_max: number;
  readonly recipient_key_max_length: number;
  readonly display_name_max_length: number;
  readonly subject_max_length: number;
  readonly preview_text_max_length: number;
  readonly search_max_length: number;
  readonly max_recipients: number;
}
export interface EmailMarketingPaginationConfiguration {
  readonly default_page_size: number;
  readonly max_page_size: number;
  readonly page_size_options: readonly number[];
}
export interface EmailMarketingTransitionsConfiguration {
  readonly campaign: readonly string[];
  readonly template: readonly string[];
  readonly recipient: readonly string[];
}
export interface EmailMarketingWorkflowConfiguration {
  readonly campaign_types: readonly string[];
  readonly audience_resolver_keys: readonly string[];
  readonly audience_schema_versions: readonly number[];
  readonly campaign_editable_states: readonly CampaignStatus[];
  readonly campaign_archivable_states: readonly CampaignStatus[];
  readonly campaign_physical_delete_protected_states: readonly CampaignStatus[];
  readonly campaign_archive_blocking_recipient_states: readonly RecipientStatus[];
  readonly template_editable_states: readonly TemplateStatus[];
  readonly recipient_initial_states: readonly RecipientStatus[];
  readonly terminal_recipient_states: readonly RecipientStatus[];
  readonly preflight_blocking_codes: readonly string[];
  readonly provider_acknowledgement_mapping: Readonly<Record<string, RecipientStatus>>;
  readonly provider_event_recipient_mapping: Readonly<Record<string, RecipientStatus>>;
  readonly provider_event_command_mapping: Readonly<Record<string, string>>;
  readonly transitions: EmailMarketingTransitionsConfiguration;
}
export interface EmailMarketingComplianceConfiguration {
  readonly permanent_suppression_reasons: readonly SuppressionReason[];
  readonly protected_overwrite_reasons: readonly SuppressionReason[];
  readonly suppression_scopes: readonly SuppressionScope[];
  readonly suppression_reasons: readonly SuppressionReason[];
  readonly suppression_sources: readonly SuppressionSource[];
  readonly automatic_suppression_events: readonly DeliveryEventType[];
  readonly automatic_suppression_reasons: Readonly<Record<string, SuppressionReason>>;
  readonly consent_sources: readonly ConsentSource[];
  readonly consent_lawful_bases: readonly ConsentLawfulBasis[];
  readonly consent_required_status: ConsentStatus;
  readonly suppression_scopes_by_purpose: Readonly<Record<string, readonly SuppressionScope[]>>;
}
export interface EmailMarketingResilienceConfiguration {
  readonly delivery_timeout_seconds: number;
  readonly retry_max_attempts: number;
  readonly retry_base_delay_seconds: number;
  readonly retry_max_delay_seconds: number;
  readonly retry_jitter_seconds: number;
  readonly circuit_failure_threshold: number;
  readonly circuit_reset_seconds: number;
  readonly webhook_replay_window_seconds: number;
}
export interface EmailMarketingTokenConfiguration {
  readonly preflight_receipt_seconds: number;
  readonly tracking_token_days: number;
  readonly unsubscribe_token_days: number;
}
export interface EmailMarketingIntegrationConfiguration {
  readonly allowed_delivery_backends: readonly string[];
  readonly simulated_delivery_backends: readonly string[];
  readonly gateway_keys: readonly string[];
}
export interface EmailMarketingFilterConfiguration {
  readonly default_ordering_by_resource: Readonly<Record<string, string>>;
  readonly search_fields_by_resource: Readonly<Record<string, readonly string[]>>;
}
export interface EmailMarketingHealthConfiguration {
  readonly outbox_freshness_seconds: number;
  readonly probe_staleness_seconds: number;
}
export interface EmailMarketingRateLimitConfiguration {
  readonly public_per_minute: number;
}
export interface EmailMarketingQuotaConfiguration {
  readonly api_reads: number;
  readonly api_writes: number;
  readonly audience_resolutions: number;
  readonly monthly_recipients: number;
}
export interface EmailMarketingFeatureFlagConfiguration {
  readonly enabled: boolean;
  readonly rollout_percentage: number;
  readonly roles: readonly string[];
  readonly cohorts: readonly string[];
}
export interface EmailMarketingDisplayConfiguration {
  readonly status_semantics: Readonly<Record<string, ConfigurationStatusTone>>;
}
export interface EmailMarketingConfigurationDocument {
  readonly schema_version: number;
  readonly defaults: EmailMarketingDefaultsConfiguration;
  readonly limits: EmailMarketingLimitsConfiguration;
  readonly pagination: EmailMarketingPaginationConfiguration;
  readonly workflows: EmailMarketingWorkflowConfiguration;
  readonly compliance: EmailMarketingComplianceConfiguration;
  readonly resilience: EmailMarketingResilienceConfiguration;
  readonly tokens: EmailMarketingTokenConfiguration;
  readonly integrations: EmailMarketingIntegrationConfiguration;
  readonly filters: EmailMarketingFilterConfiguration;
  readonly health: EmailMarketingHealthConfiguration;
  readonly rate_limits: EmailMarketingRateLimitConfiguration;
  readonly quotas: EmailMarketingQuotaConfiguration;
  readonly feature_flags: EmailMarketingFeatureFlagConfiguration;
  readonly display: EmailMarketingDisplayConfiguration;
}
export interface EmailMarketingConfiguration {
  readonly id: UUID;
  readonly environment: string;
  readonly version: number;
  readonly document: EmailMarketingConfigurationDocument;
  readonly updated_at: ISODateTime;
  readonly updated_by: UUID | null;
}
export interface EmailMarketingConfigurationChange {
  readonly path: string;
  readonly before: unknown;
  readonly after: unknown;
}
export interface EmailMarketingConfigurationPreview {
  readonly valid: true;
  readonly normalized_document: EmailMarketingConfigurationDocument;
  readonly changes: readonly EmailMarketingConfigurationChange[];
  readonly warnings: readonly string[];
}
export interface EmailMarketingConfigurationVersion {
  readonly id: UUID;
  readonly version: number;
  readonly previous_version: number | null;
  readonly change_type: 'materialized' | 'updated' | 'imported' | 'rollback';
  readonly actor_id: UUID | null;
  readonly correlation_id: string;
  readonly previous_document: EmailMarketingConfigurationDocument | null;
  readonly document: EmailMarketingConfigurationDocument;
  readonly created_at: ISODateTime;
  readonly rollback_source_version: number | null;
}
export interface ConfigurationWriteInput { readonly document: EmailMarketingConfigurationDocument; readonly expected_version: number }
export interface ConfigurationPreviewInput { readonly document: EmailMarketingConfigurationDocument }
export interface ConfigurationRollbackInput { readonly target_version: number; readonly expected_version: number }

export interface DependencyHealth { readonly name: string; readonly status: HealthState; readonly detail: string; readonly checked_at: ISODateTime }
export interface ModuleHealth { readonly status: HealthState; readonly ready: boolean; readonly checks: readonly DependencyHealth[]; readonly migration: string; readonly checked_at: ISODateTime }

interface PageFilters { readonly page?: number; readonly page_size?: number }
export type CampaignOrderingField = 'created_at' | 'scheduled_at' | 'campaign_name' | 'status';
export interface CampaignFilters extends PageFilters { readonly search?: string; readonly status?: CampaignStatus; readonly campaign_type?: string; readonly template_id?: UUID; readonly scheduled_after?: ISODateTime; readonly scheduled_before?: ISODateTime; readonly created_after?: ISODateTime; readonly created_before?: ISODateTime; readonly ordering?: Ordering<CampaignOrderingField> }
export type TemplateOrderingField = 'template_code' | 'template_name' | 'updated_at';
export interface TemplateFilters extends PageFilters { readonly search?: string; readonly status?: TemplateStatus; readonly category?: string; readonly ordering?: Ordering<TemplateOrderingField> }
export interface RecipientFilters extends PageFilters { readonly campaign_id?: UUID; readonly status?: RecipientStatus; readonly email?: string; readonly ordering?: Ordering<'created_at' | 'status'> }
export interface DeliveryFilters extends PageFilters { readonly campaign_id?: UUID; readonly recipient_id?: UUID; readonly status?: DeliveryAttemptStatus; readonly gateway_key?: string; readonly created_after?: ISODateTime; readonly created_before?: ISODateTime; readonly ordering?: Ordering<'created_at' | 'status'> }
export interface SuppressionFilters extends PageFilters { readonly active?: boolean; readonly scope?: SuppressionScope; readonly reason?: SuppressionReason; readonly email?: string; readonly ordering?: Ordering<'suppressed_at' | 'email'> }
export interface ConsentFilters extends PageFilters { readonly status?: ConsentStatus; readonly purpose?: string; readonly source?: ConsentSource; readonly email?: string; readonly captured_after?: ISODateTime; readonly captured_before?: ISODateTime; readonly ordering?: Ordering<'captured_at' | 'email'> }

export const MODULE_API_PREFIX = '/api/v2/email-marketing';
const resource = (name: string) => `${MODULE_API_PREFIX}/${name}/` as const;
export const ENDPOINTS = {
  CAMPAIGNS: { LIST: resource('campaigns'), CREATE: resource('campaigns'), DETAIL: (id: UUID) => `${resource('campaigns')}${id}/` as const, UPDATE: (id: UUID) => `${resource('campaigns')}${id}/` as const, DELETE: (id: UUID) => `${resource('campaigns')}${id}/` as const, RESOLVE_AUDIENCE: (id: UUID) => `${resource('campaigns')}${id}/resolve-audience/` as const, SCHEDULE: (id: UUID) => `${resource('campaigns')}${id}/schedule/` as const, UNSCHEDULE: (id: UUID) => `${resource('campaigns')}${id}/unschedule/` as const, SEND: (id: UUID) => `${resource('campaigns')}${id}/send/` as const, PAUSE: (id: UUID) => `${resource('campaigns')}${id}/pause/` as const, RESUME: (id: UUID) => `${resource('campaigns')}${id}/resume/` as const, CANCEL: (id: UUID) => `${resource('campaigns')}${id}/cancel/` as const, ANALYTICS: (id: UUID) => `${resource('campaigns')}${id}/analytics/` as const },
  TEMPLATES: { LIST: resource('templates'), CREATE: resource('templates'), DETAIL: (id: UUID) => `${resource('templates')}${id}/` as const, UPDATE: (id: UUID) => `${resource('templates')}${id}/` as const, DELETE: (id: UUID) => `${resource('templates')}${id}/` as const, ACTIVATE: (id: UUID) => `${resource('templates')}${id}/activate/` as const, ARCHIVE: (id: UUID) => `${resource('templates')}${id}/archive/` as const, CLONE: (id: UUID) => `${resource('templates')}${id}/clone/` as const, PREVIEW: (id: UUID) => `${resource('templates')}${id}/preview/` as const },
  RECIPIENTS: { LIST: resource('recipients'), DETAIL: (id: UUID) => `${resource('recipients')}${id}/` as const, RETRY: (id: UUID) => `${resource('recipients')}${id}/retry/` as const },
  DELIVERIES: { LIST: resource('deliveries'), DETAIL: (id: UUID) => `${resource('deliveries')}${id}/` as const },
  SUPPRESSIONS: { LIST: resource('suppressions'), CREATE: resource('suppressions'), DETAIL: (id: UUID) => `${resource('suppressions')}${id}/` as const, DEACTIVATE: (id: UUID) => `${resource('suppressions')}${id}/deactivate/` as const },
  CONSENTS: { LIST: resource('consents'), CREATE: resource('consents'), DETAIL: (id: UUID) => `${resource('consents')}${id}/` as const, REVOKE: `${resource('consents')}revoke/` },
  CONFIGURATION: {
    CURRENT: `${resource('configuration')}current/`,
    PREVIEW: `${resource('configuration')}preview/`,
    HISTORY: `${resource('configuration')}history/`,
    ROLLBACK: `${resource('configuration')}rollback/`,
    IMPORT: `${resource('configuration')}import-document/`,
    EXPORT: `${resource('configuration')}export-document/`,
  },
  PUBLIC_UNSUBSCRIBE: `${MODULE_API_PREFIX}/public/unsubscribe/`, TRACK_OPEN: (token: string) => `${MODULE_API_PREFIX}/t/${encodeURIComponent(token)}/open.gif` as const, TRACK_CLICK: (token: string) => `${MODULE_API_PREFIX}/t/${encodeURIComponent(token)}/click/` as const, HEALTH: resource('health'),
} as const;

export const ROUTES = { CAMPAIGNS: '/email-marketing/campaigns', CAMPAIGN_CREATE: '/email-marketing/campaigns/new', CAMPAIGN_DETAIL: (id: UUID) => `/email-marketing/campaigns/${id}` as const, CAMPAIGN_EDIT: (id: UUID) => `/email-marketing/campaigns/${id}/edit` as const, TEMPLATES: '/email-marketing/templates', TEMPLATE_CREATE: '/email-marketing/templates/new', TEMPLATE_DETAIL: (id: UUID) => `/email-marketing/templates/${id}` as const, TEMPLATE_EDIT: (id: UUID) => `/email-marketing/templates/${id}/edit` as const, DELIVERY: '/email-marketing/delivery', RECIPIENT_DETAIL: (id: UUID) => `/email-marketing/delivery/recipients/${id}` as const, DELIVERY_DETAIL: (id: UUID) => `/email-marketing/delivery/attempts/${id}` as const, SUPPRESSIONS: '/email-marketing/suppressions', SUPPRESSION_CREATE: '/email-marketing/suppressions/new', SUPPRESSION_DETAIL: (id: UUID) => `/email-marketing/suppressions/${id}` as const, CONSENTS: '/email-marketing/consents', CONSENT_CREATE: '/email-marketing/consents/new', CONSENT_DETAIL: (id: UUID) => `/email-marketing/consents/${id}` as const, CONFIGURATION: '/email-marketing/configuration' } as const;

export const isRecord = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
export function isPaginationMeta(value: unknown): value is ApiV2PaginationMeta { return isRecord(value) && ['count', 'page', 'page_size', 'total_pages'].every((key) => Number.isInteger(value[key])) && typeof value.has_next === 'boolean' && typeof value.has_previous === 'boolean'; }
export function isApiV2Envelope(value: unknown): value is ApiV2Envelope<unknown> { return isRecord(value) && 'data' in value && isRecord(value.meta) && typeof value.meta.correlation_id === 'string' && typeof value.meta.timestamp === 'string'; }
export function isApiV2Page(value: unknown): value is ApiV2Page<unknown> { return isApiV2Envelope(value) && Array.isArray(value.data) && isPaginationMeta(value.meta.pagination); }

const hasStrings = (value: Record<string, unknown>, keys: readonly string[]) => keys.every((key) => typeof value[key] === 'string');
export const isCampaignSummary = (value: unknown): value is EmailCampaignSummary => isRecord(value) && hasStrings(value, ['id', 'campaign_code', 'campaign_name', 'campaign_type', 'subject', 'status', 'timezone', 'created_at', 'updated_at']) && typeof value.resolved_recipient_count === 'number';
export const isCampaignDetail = (value: unknown): value is EmailCampaignDetail => isRecord(value) && isCampaignSummary(value) && hasStrings(value, ['from_name', 'from_email', 'description']) && Array.isArray(value.transition_history);
export const isTemplateSummary = (value: unknown): value is EmailTemplateSummary => isRecord(value) && hasStrings(value, ['id', 'template_code', 'template_name', 'category', 'subject', 'status', 'updated_at']) && typeof value.version === 'number';
export const isTemplateDetail = (value: unknown): value is EmailTemplateDetail => isRecord(value) && isTemplateSummary(value) && hasStrings(value, ['body_html', 'body_text', 'description']) && isRecord(value.design_json);
export const isRecipientSummary = (value: unknown): value is CampaignRecipientSummary => isRecord(value) && hasStrings(value, ['id', 'campaign_id', 'email', 'display_name', 'status', 'created_at']);
export const isRecipientDetail = (value: unknown): value is CampaignRecipientDetail => isRecord(value) && isRecipientSummary(value) && Array.isArray(value.delivery_attempts) && Array.isArray(value.events);
export const isDeliverySummary = (value: unknown): value is DeliveryAttemptSummary => isRecord(value) && hasStrings(value, ['id', 'recipient_id', 'status', 'error_code', 'created_at']) && typeof value.attempt_number === 'number';
export const isDeliveryDetail = (value: unknown): value is DeliveryAttemptDetail => isRecord(value) && isDeliverySummary(value) && typeof value.updated_at === 'string' && Array.isArray(value.events);
export const isSuppressionSummary = (value: unknown): value is SuppressionEntrySummary => isRecord(value) && hasStrings(value, ['id', 'email', 'scope', 'reason', 'source', 'suppressed_at']) && typeof value.active === 'boolean';
export const isSuppressionDetail = (value: unknown): value is SuppressionEntryDetail => isRecord(value) && isSuppressionSummary(value) && hasStrings(value, ['notes', 'created_at', 'updated_at']);
export const isConsentSummary = (value: unknown): value is ConsentRecordSummary => isRecord(value) && hasStrings(value, ['id', 'email', 'purpose', 'status', 'lawful_basis', 'source', 'notice_version', 'captured_at', 'created_at']);
export const isConsentDetail = (value: unknown): value is ConsentRecordDetail => isRecord(value) && isConsentSummary(value) && (value.actor_id === null || typeof value.actor_id === 'string') && (value.supersedes_id === null || typeof value.supersedes_id === 'string');
export const isAsyncJob = (value: unknown): value is AsyncJobSummary => isRecord(value) && hasStrings(value, ['id', 'job_type', 'status', 'idempotency_key', 'created_at', 'correlation_id']);
export const isCampaignAnalytics = (value: unknown): value is CampaignAnalytics => isRecord(value) && typeof value.delivery_rate === 'number' && isRecord(value.preflight);
export const isRenderedEmail = (value: unknown): value is RenderedEmail => isRecord(value) && hasStrings(value, ['subject', 'html', 'text']) && Array.isArray(value.warnings);
export const isHealth = (value: unknown): value is ModuleHealth => isRecord(value) && typeof value.ready === 'boolean' && ['ready', 'degraded', 'unhealthy'].includes(String(value.status)) && Array.isArray(value.checks);
export const isPublicUnsubscribeResponse = (value: unknown): value is PublicUnsubscribeResponse => isRecord(value) && typeof value.suppression_id === 'string' && value.status === 'unsubscribed';
export const isEmailMarketingConfigurationDocument = (value: unknown): value is EmailMarketingConfigurationDocument => isRecord(value) && Number.isInteger(value.schema_version) && ['defaults', 'limits', 'pagination', 'workflows', 'compliance', 'resilience', 'tokens', 'integrations', 'filters', 'health', 'rate_limits', 'quotas', 'feature_flags', 'display'].every((key) => isRecord(value[key]));
export const isEmailMarketingConfiguration = (value: unknown): value is EmailMarketingConfiguration => isRecord(value) && hasStrings(value, ['id', 'environment', 'updated_at']) && Number.isInteger(value.version) && isEmailMarketingConfigurationDocument(value.document);
export const isEmailMarketingConfigurationPreview = (value: unknown): value is EmailMarketingConfigurationPreview => isRecord(value) && value.valid === true && isEmailMarketingConfigurationDocument(value.normalized_document) && Array.isArray(value.changes) && Array.isArray(value.warnings);
export const isEmailMarketingConfigurationVersion = (value: unknown): value is EmailMarketingConfigurationVersion => isRecord(value) && hasStrings(value, ['id', 'change_type', 'correlation_id', 'created_at']) && Number.isInteger(value.version) && isEmailMarketingConfigurationDocument(value.document);
