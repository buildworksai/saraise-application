/** Canonical, governed v2 contracts owned by the notifications module. */

export type UUID = string;
export type ISODateTime = string;
export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | readonly JsonValue[];
// eslint-disable-next-line @typescript-eslint/consistent-indexed-object-style -- interface indirection preserves a finite recursive JSON type.
export interface JsonObject { readonly [key: string]: JsonValue }

export type NotificationChannel = "in_app" | "email" | "sms" | "push" | "webhook";
export type TemplateStatus = "draft" | "active" | "archived";
export type NotificationStatus = "unread" | "read" | "archived";
export type NotificationType = "info" | "success" | "warning" | "error" | "workflow" | "approval" | "system" | "security";
export type DeliveryStatus = "pending" | "queued" | "sending" | "sent" | "delivered" | "retry_wait" | "failed" | "cancelled" | "skipped";
export type AttemptOutcome = "accepted" | "retryable_failure" | "permanent_failure" | "circuit_open" | "timeout";
export type DigestMode = "immediate" | "hourly" | "daily" | "weekly";
export type NotificationEnvironment = "development" | "staging" | "production";
export type EndpointKind = "push" | "webhook";
export type EndpointDeviceType = "web" | "android" | "ios" | "";
export type RecipientType = "user" | "email" | "phone" | "push_endpoint" | "webhook_endpoint";
export type ContentType = "text/plain" | "text/html" | "application/json";

export interface PaginationMeta { readonly count: number; readonly page: number; readonly page_size: number; readonly total_pages: number; readonly has_next: boolean; readonly has_previous: boolean }
export interface ApiMeta { readonly correlation_id: UUID; readonly timestamp: ISODateTime; readonly pagination?: PaginationMeta }
export interface ApiSuccess<T> { readonly data: T; readonly meta: ApiMeta; readonly capabilities?: readonly string[] }
export interface PaginatedData<T> { readonly items: readonly T[]; readonly pagination: PaginationMeta; readonly meta: ApiMeta; readonly capabilities: readonly string[] }
export interface ApiFieldError { readonly field: string; readonly code: string; readonly message: string }
export interface StableApiError { readonly error: { readonly code: string; readonly message: string; readonly correlation_id: UUID | null; readonly field_errors?: readonly ApiFieldError[] } }

export interface TransitionRecord { readonly action: string; readonly from_state: string; readonly to_state: string; readonly actor_id: UUID; readonly transition_key: string; readonly correlation_id: UUID; readonly at: ISODateTime }
export interface VariableDefinition { readonly type: "string" | "number" | "boolean" | "object" | "array"; readonly required: boolean; readonly example?: JsonValue; readonly description?: string }
export type VariablesSchema = Readonly<Record<string, VariableDefinition>>;

export interface NotificationTemplateVersion {
  readonly id: UUID; readonly version: number; readonly subject_template: string; readonly body_template: string;
  readonly variables_schema: VariablesSchema; readonly content_type: ContentType; readonly created_by: UUID;
  readonly correlation_id: UUID; readonly created_at: ISODateTime;
}
export interface NotificationTemplate {
  readonly id: UUID; readonly code: string; readonly name: string; readonly category: string; readonly channel: NotificationChannel;
  readonly locale: string; readonly status: TemplateStatus; readonly active_version: NotificationTemplateVersion | null;
  readonly latest_version?: NotificationTemplateVersion | null; readonly transition_history?: readonly TransitionRecord[];
  readonly created_by: UUID; readonly updated_by: UUID; readonly created_at: ISODateTime; readonly updated_at: ISODateTime;
}
export interface TemplateCreateInput { readonly code: string; readonly name: string; readonly category: string; readonly channel: NotificationChannel; readonly locale: string; readonly subject_template: string; readonly body_template: string; readonly variables_schema: VariablesSchema; readonly content_type: ContentType }
export interface TemplateVersionCreateInput { readonly name?: string; readonly category?: string; readonly subject_template: string; readonly body_template: string; readonly variables_schema: VariablesSchema; readonly content_type: ContentType }
export interface TemplatePreviewInput { readonly context: JsonObject; readonly draft?: TemplateVersionCreateInput }
export interface TemplatePreviewResult { readonly subject: string; readonly body: string; readonly content_type: ContentType; readonly diagnostics: readonly { readonly level: "info" | "warning" | "error"; readonly variable?: string; readonly message: string }[] }
export interface TemplateTransitionInput { readonly transition_key: string; readonly version?: number }
export interface TemplateRollbackInput { readonly version: number; readonly transition_key: string }

export interface Notification {
  readonly id: UUID; readonly delivery_id: UUID | null; readonly notification_type: NotificationType; readonly category: string;
  readonly title: string; readonly message: string; readonly status: NotificationStatus; readonly read_at: ISODateTime | null;
  readonly action_url: string; readonly metadata: JsonObject; readonly expires_at: ISODateTime | null;
  readonly transition_history?: readonly TransitionRecord[]; readonly created_at: ISODateTime; readonly updated_at: ISODateTime;
}
export interface InboxTransitionInput { readonly transition_key: string }
export interface MarkAllReadInput { readonly transition_key: string }
export interface AffectedCountResult { readonly affected_count: number }
export interface UnreadCountResult { readonly count: number }

export interface NotificationDeliveryAttempt {
  readonly id: UUID; readonly attempt_number: number; readonly adapter_key: string; readonly outcome: AttemptOutcome;
  readonly provider_message_id: string; readonly error_code: string; readonly latency_ms: number;
  readonly started_at: ISODateTime; readonly completed_at: ISODateTime; readonly correlation_id: UUID;
}
export interface NotificationDelivery {
  readonly id: UUID; readonly template_version_id: UUID; readonly job_id: UUID; readonly idempotency_key: string;
  readonly recipient_type: RecipientType; readonly recipient_user_id: UUID | null; readonly recipient_display: string;
  readonly channel: NotificationChannel; readonly category: string; readonly priority: number; readonly status: DeliveryStatus;
  readonly scheduled_at: ISODateTime | null; readonly next_attempt_at: ISODateTime | null; readonly attempt_count: number;
  readonly max_attempts: number; readonly provider_message_id: string; readonly failure_code: string; readonly failure_message: string;
  readonly transition_history: readonly TransitionRecord[]; readonly correlation_id: UUID; readonly sent_at: ISODateTime | null;
  readonly delivered_at: ISODateTime | null; readonly created_at: ISODateTime; readonly updated_at: ISODateTime;
  readonly attempts?: readonly NotificationDeliveryAttempt[];
}
export interface DeliveryRecipientInput { readonly type: RecipientType; readonly user_id?: UUID; readonly endpoint_id?: UUID; readonly address?: string }
export interface DeliveryCreateInput { readonly template_id: UUID; readonly template_version?: number; readonly recipient: DeliveryRecipientInput; readonly context: JsonObject; readonly priority: number; readonly scheduled_at?: ISODateTime | null; readonly idempotency_key: string }
export interface BulkDeliveryCreateInput { readonly deliveries: readonly DeliveryCreateInput[]; readonly idempotency_key: string }
export interface DeliveryPreviewResult extends TemplatePreviewResult { readonly recipient_display: string; readonly effective_channel: NotificationChannel; readonly preference_decision: "allowed" | "quiet_hours" | "disabled" | "mandatory" }
export interface DeliveryRetryInput { readonly idempotency_key: string }
export interface DeliveryCancelInput { readonly transition_key: string }

export interface NotificationPreference {
  readonly id?: UUID; readonly channel: NotificationChannel; readonly category: string; readonly enabled: boolean;
  readonly digest_mode: DigestMode; readonly quiet_hours_start: string | null; readonly quiet_hours_end: string | null;
  readonly timezone: string; readonly mandatory: boolean; readonly source: "override" | "tenant_default" | "mandatory_policy";
  readonly updated_at?: ISODateTime;
}
export interface PreferenceMatrix { readonly categories: readonly string[]; readonly channels: readonly NotificationChannel[]; readonly preferences: readonly NotificationPreference[] }
export interface PreferenceUpsertInput { readonly channel: NotificationChannel; readonly category: string; readonly enabled: boolean; readonly digest_mode: DigestMode; readonly quiet_hours_start: string | null; readonly quiet_hours_end: string | null; readonly timezone: string }
export interface PreferenceReplaceInput { readonly preferences: readonly PreferenceUpsertInput[] }

export interface NotificationEndpoint {
  readonly id: UUID; readonly user_id: UUID | null; readonly kind: EndpointKind; readonly device_type: EndpointDeviceType;
  readonly address_display: string; readonly display_name: string; readonly secret_ref: string; readonly is_active: boolean;
  readonly health: "unverified" | "healthy" | "degraded" | "revoked"; readonly last_verified_at: ISODateTime | null;
  readonly last_used_at: ISODateTime | null; readonly created_by: UUID; readonly created_at: ISODateTime; readonly updated_at: ISODateTime;
}
export interface EndpointRegisterInput { readonly kind: EndpointKind; readonly device_type: EndpointDeviceType; readonly address: string; readonly display_name: string; readonly secret_ref?: string }
export interface EndpointUpdateInput { readonly display_name?: string; readonly secret_ref?: string; readonly is_active?: boolean }
export interface EndpointVerifyResult { readonly verified: boolean; readonly health: NotificationEndpoint["health"]; readonly verified_at: ISODateTime | null; readonly endpoint: NotificationEndpoint; readonly error_code?: string }

export interface RetryConfiguration { readonly max_attempts: number; readonly base_seconds: number; readonly maximum_seconds: number }
export interface CircuitConfiguration { readonly failure_threshold: number; readonly reset_seconds: number }
export interface ChannelConfiguration { readonly enabled: boolean; readonly adapter_key: string; readonly credential_ref: string; readonly sender_ref: string; readonly timeout_seconds: number; readonly retry: RetryConfiguration; readonly circuit: CircuitConfiguration; readonly rate_limit_per_minute: number }
export interface FeatureRollout { readonly enabled: boolean; readonly tenant_ids: readonly UUID[]; readonly roles: readonly string[]; readonly cohorts: readonly string[] }
export interface ConfigurationPreferenceDefaults { readonly default_enabled: boolean; readonly mandatory_categories: readonly string[] }
export interface BackoffConfiguration { readonly base_seconds: number; readonly maximum_seconds: number }
export interface RetentionConfiguration { readonly delivery_days: number; readonly inbox_days: number }
export interface PayloadLimitConfiguration { readonly context_bytes: number; readonly metadata_bytes: number }
export interface DigestScheduleConfiguration { readonly hourly_minute: number; readonly daily_time: string; readonly weekly_day: number }
export interface QuietHoursConfiguration { readonly start: string | null; readonly end: string | null; readonly timezone: string }
export interface ProviderCallbackConfiguration { readonly timestamp_tolerance_seconds: number }
export interface NotificationConfigurationDocument {
  readonly schema_version: number; readonly channels: Readonly<Record<NotificationChannel, ChannelConfiguration>>;
  readonly preferences: ConfigurationPreferenceDefaults; readonly batch_size: number; readonly max_attempts: number;
  readonly backoff: BackoffConfiguration; readonly retention: RetentionConfiguration; readonly limits: PayloadLimitConfiguration;
  readonly allowed_action_url_hosts: readonly string[]; readonly allowed_webhook_hosts: readonly string[];
  readonly feature_flags: Readonly<Record<string, FeatureRollout>>; readonly digest_schedules: DigestScheduleConfiguration;
  readonly quiet_hours: QuietHoursConfiguration; readonly provider_callbacks: ProviderCallbackConfiguration;
}
export interface NotificationConfiguration { readonly id: UUID; readonly environment: NotificationEnvironment; readonly active_version: number; readonly document: NotificationConfigurationDocument; readonly checksum?: string; readonly created_by: UUID; readonly updated_by: UUID; readonly created_at: ISODateTime; readonly updated_at: ISODateTime }
export interface ConfigurationWriteInput { readonly expected_version: number; readonly document: NotificationConfigurationDocument; readonly change_summary: string }
export interface ConfigurationSimulationInput { readonly document: NotificationConfigurationDocument; readonly scenario: { readonly channel: NotificationChannel; readonly category: string; readonly priority: number } }
export interface ConfigurationSimulationResult { readonly valid: boolean; readonly changes: readonly { readonly path: string; readonly before: JsonValue; readonly after: JsonValue; readonly impact: string }[]; readonly decision: string; readonly warnings: readonly string[] }
export interface NotificationConfigurationVersion { readonly version: number; readonly document: NotificationConfigurationDocument; readonly checksum: string; readonly created_by: UUID; readonly correlation_id: UUID; readonly change_summary: string; readonly created_at: ISODateTime }
export interface NotificationConfigurationAudit { readonly id: UUID; readonly version: number; readonly actor_id: UUID; readonly correlation_id: UUID; readonly action: "create" | "update" | "import" | "rollback"; readonly before_checksum: string | null; readonly after_checksum: string; readonly changed_paths: readonly string[]; readonly created_at: ISODateTime }
export interface ConfigurationHistoryItem { readonly version: NotificationConfigurationVersion; readonly audit: NotificationConfigurationAudit }
export interface ConfigurationRollbackInput { readonly target_version: number; readonly expected_version: number; readonly change_summary: string }
export interface ConfigurationImportInput { readonly document: NotificationConfigurationDocument; readonly expected_version: number; readonly dry_run: boolean; readonly change_summary: string }
export interface ConfigurationExport { readonly schema_version: number; readonly environment: NotificationEnvironment; readonly exported_at: ISODateTime; readonly configuration: NotificationConfigurationDocument }

export interface HealthComponent { readonly status: "ready" | "unavailable" | "disabled"; readonly code: string; readonly details?: JsonObject }
export interface LivenessResult { readonly module: "notifications"; readonly status: "live"; readonly live: true }
export interface ReadinessResult { readonly module: "notifications"; readonly status: "ready" | "not_ready"; readonly ready: boolean; readonly code: string; readonly components: Readonly<Record<string, HealthComponent>> }

export interface PageQuery { readonly page?: number; readonly page_size?: number; readonly ordering?: string; readonly search?: string }
export interface InboxQuery extends PageQuery { readonly status?: NotificationStatus; readonly type?: NotificationType; readonly category?: string; readonly created_after?: ISODateTime; readonly created_before?: ISODateTime }
export interface TemplateQuery extends PageQuery { readonly channel?: NotificationChannel; readonly category?: string; readonly locale?: string; readonly status?: TemplateStatus }
export interface DeliveryQuery extends PageQuery { readonly status?: DeliveryStatus; readonly channel?: NotificationChannel; readonly category?: string; readonly recipient_user?: UUID; readonly created_after?: ISODateTime; readonly created_before?: ISODateTime }
export interface EndpointQuery extends PageQuery { readonly kind?: EndpointKind; readonly active?: boolean }

export const MODULE_API_PREFIX = "/api/v2/notifications";
const withId = (root: string, id: string): string => `${root}/${encodeURIComponent(id)}`;
export const ENDPOINTS = {
  INBOX: { LIST: `${MODULE_API_PREFIX}/inbox/`, DETAIL: (id: string) => `${withId(`${MODULE_API_PREFIX}/inbox`, id)}/`, MARK_READ: (id: string) => `${withId(`${MODULE_API_PREFIX}/inbox`, id)}/mark-read/`, MARK_UNREAD: (id: string) => `${withId(`${MODULE_API_PREFIX}/inbox`, id)}/mark-unread/`, ARCHIVE: (id: string) => `${withId(`${MODULE_API_PREFIX}/inbox`, id)}/archive/`, MARK_ALL_READ: `${MODULE_API_PREFIX}/inbox/mark-all-read/`, UNREAD_COUNT: `${MODULE_API_PREFIX}/inbox/unread-count/` },
  TEMPLATES: { LIST: `${MODULE_API_PREFIX}/templates/`, PREVIEW_DRAFT: `${MODULE_API_PREFIX}/templates/preview-draft/`, DETAIL: (id: string) => `${withId(`${MODULE_API_PREFIX}/templates`, id)}/`, VERSIONS: (id: string) => `${withId(`${MODULE_API_PREFIX}/templates`, id)}/versions/`, PREVIEW: (id: string) => `${withId(`${MODULE_API_PREFIX}/templates`, id)}/preview/`, ACTIVATE: (id: string) => `${withId(`${MODULE_API_PREFIX}/templates`, id)}/activate/`, RESTORE: (id: string) => `${withId(`${MODULE_API_PREFIX}/templates`, id)}/restore/`, ROLLBACK: (id: string) => `${withId(`${MODULE_API_PREFIX}/templates`, id)}/rollback/` },
  DELIVERIES: { LIST: `${MODULE_API_PREFIX}/deliveries/`, URGENT: `${MODULE_API_PREFIX}/deliveries/urgent/`, BULK: `${MODULE_API_PREFIX}/deliveries/bulk/`, PREVIEW: `${MODULE_API_PREFIX}/deliveries/preview/`, DETAIL: (id: string) => `${withId(`${MODULE_API_PREFIX}/deliveries`, id)}/`, ATTEMPTS: (id: string) => `${withId(`${MODULE_API_PREFIX}/deliveries`, id)}/attempts/`, RETRY: (id: string) => `${withId(`${MODULE_API_PREFIX}/deliveries`, id)}/retry/`, CANCEL: (id: string) => `${withId(`${MODULE_API_PREFIX}/deliveries`, id)}/cancel/` },
  PREFERENCES: { ME: `${MODULE_API_PREFIX}/preferences/me/`, RESET: `${MODULE_API_PREFIX}/preferences/me/reset/` },
  ENDPOINTS: { LIST: `${MODULE_API_PREFIX}/endpoints/`, DETAIL: (id: string) => `${withId(`${MODULE_API_PREFIX}/endpoints`, id)}/`, VERIFY: (id: string) => `${withId(`${MODULE_API_PREFIX}/endpoints`, id)}/verify/` },
  CONFIGURATION: { DETAIL: (environment: NotificationEnvironment) => `${MODULE_API_PREFIX}/configuration/${environment}/`, SIMULATE: (environment: NotificationEnvironment) => `${MODULE_API_PREFIX}/configuration/${environment}/simulate/`, HISTORY: (environment: NotificationEnvironment) => `${MODULE_API_PREFIX}/configuration/${environment}/history/`, ROLLBACK: (environment: NotificationEnvironment) => `${MODULE_API_PREFIX}/configuration/${environment}/rollback/`, IMPORT: (environment: NotificationEnvironment) => `${MODULE_API_PREFIX}/configuration/${environment}/import/`, EXPORT: (environment: NotificationEnvironment) => `${MODULE_API_PREFIX}/configuration/${environment}/export/` },
  HEALTH: { LIVE: `${MODULE_API_PREFIX}/health/live/`, READY: `${MODULE_API_PREFIX}/health/ready/` },
} as const;

export const PATHS = {
  INBOX: "/notifications", DETAIL: (id: string) => `/notifications/${id}`, PREFERENCES: "/notifications/preferences",
  TEMPLATES: "/notifications/templates", TEMPLATE_CREATE: "/notifications/templates/new", TEMPLATE_DETAIL: (id: string) => `/notifications/templates/${id}`, TEMPLATE_EDIT: (id: string) => `/notifications/templates/${id}/edit`,
  DELIVERIES: "/notifications/deliveries", DELIVERY_CREATE: "/notifications/deliveries/new", DELIVERY_DETAIL: (id: string) => `/notifications/deliveries/${id}`,
  ENDPOINTS: "/notifications/endpoints", ENDPOINT_CREATE: "/notifications/endpoints/new", ENDPOINT_EDIT: (id: string) => `/notifications/endpoints/${id}/edit`,
  CONFIGURATION: "/notifications/configuration", CONFIGURATION_HISTORY: "/notifications/configuration/history", HEALTH: "/notifications/health",
} as const;
