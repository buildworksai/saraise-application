/** Canonical frontend contract for Integration Platform API v2. */

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
// Recursive JSON needs an interface; a Record alias is rejected as a circular alias by TypeScript.
// eslint-disable-next-line @typescript-eslint/consistent-indexed-object-style
export interface JsonObject { readonly [key: string]: JsonValue }

export type ConnectorType = 'api' | 'webhook' | 'database' | 'file' | 'message_queue';
export type ConnectorCapability = 'test' | 'pull' | 'push' | 'receive' | 'deliver';
export type IntegrationStatus = 'inactive' | 'testing' | 'active' | 'error';
export type CredentialType = 'api_key' | 'oauth_token' | 'username_password' | 'certificate';
export type CredentialStatus = 'active' | 'revoked' | 'expired';
export type WebhookDirection = 'inbound' | 'outbound';
export type WebhookStatus = 'inactive' | 'active' | 'error';
export type DeliveryStatus = 'queued' | 'delivering' | 'retrying' | 'delivered' | 'dead_letter' | 'cancelled';
export type SyncDirection = 'pull' | 'push';
export type JobStatus = 'queued' | 'running' | 'retrying' | 'succeeded' | 'failed' | 'cancelled' | 'timed_out';
export type TransformationOperation = 'rename' | 'string_case' | 'trim' | 'number' | 'date_format' | 'default' | 'enum_map';

export interface ApiMeta { correlation_id: string; timestamp: string }
export interface PaginatedMeta extends ApiMeta {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}
export interface ApiEnvelope<T> { data: T; meta: ApiMeta }
export interface PaginatedEnvelope<T> {
  data: T[];
  meta: ApiMeta & { pagination: Omit<PaginatedMeta, keyof ApiMeta> };
}
export interface ApiErrorDetail { field?: string; message: string; code?: string }
export interface ApiError {
  error: { code: string; message: string; details?: ApiErrorDetail[]; correlation_id: string };
  meta?: { timestamp: string };
}

export interface TransitionEvidence {
  transition: string;
  from_status: string;
  to_status: string;
  occurred_at: string;
  actor_id?: string;
  transition_key: string;
}

export interface OperationEvidence {
  outcome: 'succeeded' | 'failed';
  occurred_at: string;
  correlation_id: string;
  job_id?: string;
  duration_ms?: number;
  error_code?: string;
  error_message?: string;
  records_read?: number;
  records_written?: number;
  records_failed?: number;
  zero_source_proven?: boolean;
}

export interface JsonSchemaProperty {
  type?: 'string' | 'number' | 'integer' | 'boolean' | 'object' | 'array';
  title?: string;
  description?: string;
  format?: string;
  enum?: JsonPrimitive[];
  default?: JsonValue;
  secret?: boolean;
}
export interface ConnectorJsonSchema {
  type: 'object';
  title?: string;
  description?: string;
  required?: string[];
  properties: Readonly<Record<string, JsonSchemaProperty>>;
  additionalProperties?: boolean;
}

export interface Connector {
  id: string;
  key: string;
  name: string;
  connector_type: ConnectorType;
  adapter_key: string;
  version: string;
  capabilities: ConnectorCapability[];
  module_id: string;
  access_policy: 'public' | 'entitlement_required';
  required_entitlement: string;
  is_active: boolean;
  is_entitled: boolean;
  entitlement_reason?: string;
  adapter_available: boolean;
  created_at: string;
  updated_at: string;
}
export interface ConnectorDetail extends Connector {
  schema: ConnectorJsonSchema;
  credential_schema: ConnectorJsonSchema;
}
export interface ConnectorSchema {
  connector_id: string;
  config_schema: ConnectorJsonSchema;
  credential_schema: ConnectorJsonSchema;
}
export interface ConnectorHealth {
  connector_id: string;
  status: 'healthy' | 'degraded' | 'unavailable';
  adapter_registered: boolean;
  circuit_state: 'closed' | 'open' | 'half_open' | 'unavailable';
  checked_at: string;
  reason?: string;
  correlation_id: string;
}

export interface Integration {
  id: string;
  connector_id: string;
  connector_name: string;
  name: string;
  description: string;
  integration_type: ConnectorType;
  status: IntegrationStatus;
  last_tested_at: string | null;
  last_test_job_id: string | null;
  last_sync_job_id: string | null;
  last_error_code: string;
  last_error_message: string;
  credentials_count: number;
  mappings_count: number;
  created_at: string;
  updated_at: string;
}
export interface IntegrationDetail extends Integration {
  config: JsonObject;
  transition_history: TransitionEvidence[];
  latest_test_evidence: OperationEvidence | null;
  latest_sync_evidence: OperationEvidence | null;
}
export interface IntegrationCreateRequest {
  connector_id: string;
  name: string;
  description?: string;
  integration_type: ConnectorType;
  config: JsonObject;
}
export interface IntegrationUpdateRequest { name?: string; description?: string; config?: JsonObject }
export interface TransitionRequest { transition_key: string }
export interface IntegrationTestRequest { idempotency_key: string }
export interface IntegrationSyncRequest {
  direction: SyncDirection;
  mapping_ids: string[];
  idempotency_key: string;
}
export interface AsyncJobReceipt {
  job_id: string;
  status: JobStatus;
  correlation_id: string;
  accepted_at: string;
  poll_after_ms: number;
}
export interface AsyncJobState extends AsyncJobReceipt {
  operation: 'integration_test' | 'integration_sync' | 'webhook_delivery';
  started_at: string | null;
  completed_at: string | null;
  progress_percent: number;
  evidence: OperationEvidence | null;
}

export interface IntegrationCredential {
  id: string;
  integration_id: string;
  credential_type: CredentialType;
  display_hint: string;
  version: number;
  status: CredentialStatus;
  expires_at: string | null;
  rotated_at: string | null;
  revoked_at: string | null;
  created_at: string;
}
export interface CredentialCreateRequest { credential_type: CredentialType; plaintext: string; expires_at?: string | null }
export interface CredentialRotateRequest { plaintext: string; expires_at?: string | null; idempotency_key: string }
export type CredentialRevokeRequest = TransitionRequest;

export interface Webhook {
  id: string;
  name: string;
  direction: WebhookDirection;
  url: string;
  public_id: string;
  events: string[];
  status: WebhookStatus;
  timeout_seconds: number;
  max_attempts: number;
  last_received_at: string | null;
  last_delivered_at: string | null;
  last_error_code: string;
  created_at: string;
  updated_at: string;
}
export interface WebhookDetail extends Webhook { config: JsonObject; transition_history: TransitionEvidence[]; delivery_summary: DeliverySummary }
export interface WebhookCreateRequest {
  name: string;
  direction: WebhookDirection;
  url?: string;
  events: string[];
  config?: JsonObject;
  timeout_seconds?: number;
  max_attempts?: number;
}
export interface WebhookUpdateRequest { name?: string; url?: string; events?: string[]; config?: JsonObject; timeout_seconds?: number; max_attempts?: number }
export interface WebhookSecretOnce { webhook: WebhookDetail; signing_secret: string; shown_once: true }
export interface InboundWebhookRequest { timestamp: string; nonce: string; signature: string; raw_body: string }
export interface InboundWebhookReceipt { job_id: string; correlation_id: string; accepted_at: string }
export interface DeliverySummary { queued: number; retrying: number; delivered: number; dead_letter: number; success_rate: number | null }

export interface WebhookDelivery {
  id: string;
  webhook_id: string;
  webhook_name: string;
  event: string;
  status: DeliveryStatus;
  attempt_count: number;
  max_attempts: number;
  next_attempt_at: string | null;
  response_code: number | null;
  error_code: string;
  duration_ms: number | null;
  job_id: string;
  correlation_id: string;
  delivered_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface WebhookDeliveryDetail extends WebhookDelivery {
  payload: JsonObject;
  payload_hash: string;
  idempotency_key: string;
  error_message: string;
  transition_history: TransitionEvidence[];
  attempts: WebhookDeliveryAttempt[];
}
export interface WebhookDeliveryAttempt {
  id: string;
  attempt_number: number;
  outcome: 'delivered' | 'retrying' | 'dead_letter';
  response_code: number | null;
  error_code: string;
  duration_ms: number | null;
  job_id: string;
  correlation_id: string;
  occurred_at: string;
}
export type DeliveryRedriveRequest = TransitionRequest;

export interface TransformationSpec { operation: TransformationOperation; options?: JsonObject }
export interface DataMapping {
  id: string;
  integration_id: string;
  integration_name: string;
  name: string;
  source_field: string;
  target_field: string;
  transform: TransformationSpec;
  position: number;
  is_required: boolean;
  default_value: JsonValue;
  created_at: string;
  updated_at: string;
}
export interface DataMappingCreateRequest {
  integration_id: string;
  name: string;
  source_field: string;
  target_field: string;
  transform: TransformationSpec;
  position?: number;
  is_required?: boolean;
  default_value?: JsonValue;
}
export type DataMappingUpdateRequest = Partial<Omit<DataMappingCreateRequest, 'integration_id'>>;
export interface MappingValidationRequest { integration_id: string; mappings: DataMappingCreateRequest[]; source_schema: ConnectorJsonSchema; target_schema: ConnectorJsonSchema }
export interface MappingFieldResult { mapping_id?: string; source_field: string; target_field: string; valid: boolean; message?: string }
export interface MappingValidationResult { valid: boolean; errors: { index: number; message: string }[]; mapping_count: number }
export interface MappingPreviewRequest { integration_id: string; mapping_ids: string[]; sample: JsonObject }
export interface MappingPreviewFailure { record_index: number; mapping_id: string; source_field: string; target_field: string; code: string; message: string }
export interface MappingPreviewResult { records: JsonObject[]; failures: MappingPreviewFailure[] }

export interface HealthCheck { name: 'database' | 'outbox' | 'broker' | 'adapters' | 'dependency_circuits'; status: 'healthy' | 'degraded' | 'unavailable'; detail: string; critical: boolean; evidence: JsonObject }
export interface IntegrationPlatformHealth { status: 'healthy' | 'degraded' | 'unavailable'; module: 'integration-platform'; version: string; checked_at: string; checks: HealthCheck[] }

export interface IntegrationPlatformConfigurationDocument {
  schema_version: number;
  environment: string;
  adapter: { spi_version: string; capabilities: ConnectorCapability[]; adapter_key_max_length: number; cursor_max_length: number };
  transformations: { operations: TransformationOperation[]; string_case_modes: string[]; number_modes: string[]; default_number_mode: string; default_input_date_format: string; allow_unmapped_enum: boolean; max_chain_length: number };
  validation: { name_max_length: number; description_max_length: number; credential_max_length: number; url_max_length: number; event_name_pattern: string; event_name_max_length: number; nonce_max_length: number; signature_max_length: number; error_code_max_length: number };
  security: { connector_access_policy: 'explicit_entitlement'; secret_field_names: string[]; signature_window_seconds: number; payload_max_bytes: number; credential_hint_characters: number; signing_secret_bytes: number; outbound_nonce_bytes: number; diagnostic_fields: string[] };
  webhooks: { timeout_seconds_default: number; timeout_seconds_min: number; timeout_seconds_max: number; max_attempts_default: number; max_attempts_min: number; max_attempts_max: number; success_status_min: number; success_status_max: number; retry_statuses: number[]; retry_server_error_min: number; retry_delay_max_seconds: number; connect_timeout_max_seconds: number; http_client_retries: number; inbound_rate: string };
  synchronization: { directions: SyncDirection[]; active_statuses: IntegrationStatus[]; pull_batch_limit: number; quota_cost: number };
  workflows: { integration_delete_statuses: IntegrationStatus[]; integration_activation_statuses: IntegrationStatus[]; activation_requires_successful_test: boolean; integration_transitions: Readonly<Record<string, string[]>>; credential_transitions: Readonly<Record<string, string[]>>; webhook_transitions: Readonly<Record<string, string[]>>; delivery_transitions: Readonly<Record<string, string[]>> };
  jobs: { poll_after_ms: number; progress_min: number; progress_max: number; terminal_progress: number };
  list: { page_size: number; connector_page_size: number; refresh_interval_ms: number; active_delivery_poll_ms: number; integration_poll_ms: number; integration_ordering: string; integration_ordering_fields: string[]; webhook_ordering: string; webhook_ordering_fields: string[]; delivery_ordering: string; mapping_ordering: string; mapping_ordering_fields: string[] };
  quotas: Readonly<Record<string, number>>;
  mapping: { default_position: number; default_required: boolean; preview_record_limit: number };
  health: { probe_timeout_seconds: number; broker_acknowledgement_seconds: number };
  feature_flags: Readonly<Record<string, { enabled: boolean; roles: string[]; cohorts: string[] }>>;
  navigation: { base_order: number; route_order: Readonly<Record<string, number>>; status_positive: string[]; status_warning: string[]; status_danger: string[] };
}
export interface IntegrationPlatformConfiguration {
  id: string | null;
  tenant_id: string;
  environment: string;
  version: number;
  document: IntegrationPlatformConfigurationDocument;
  updated_at: string | null;
  updated_by: string | null;
}
export interface ConfigurationWriteRequest { environment: string; document: IntegrationPlatformConfigurationDocument }
export interface ConfigurationPreview {
  valid: boolean; environment: string; from_version: number; to_version: number;
  changed_sections: string[]; before: IntegrationPlatformConfigurationDocument; after: IntegrationPlatformConfigurationDocument;
}
export interface ConfigurationVersion { id: string; environment: string; version: number; document: IntegrationPlatformConfigurationDocument; created_by: string; correlation_id: string; created_at: string }
export interface ConfigurationAudit { id: string; environment: string; action: 'update' | 'import' | 'rollback'; from_version: number | null; to_version: number; before: IntegrationPlatformConfigurationDocument | null; after: IntegrationPlatformConfigurationDocument; changed_by: string; correlation_id: string; created_at: string }
export interface IntegrationPlatformManageCapability { allowed: boolean; permission: string; reason_code: string }

export interface PaginationParams { page?: number; page_size?: number }
export interface IntegrationFilters extends PaginationParams { search?: string; status?: IntegrationStatus; integration_type?: ConnectorType; connector_id?: string; ordering?: 'name' | '-name' | 'created_at' | '-created_at' | 'updated_at' | '-updated_at' | 'status' | '-status' }
export interface ConnectorFilters extends PaginationParams { search?: string; connector_type?: ConnectorType; module_id?: string; is_active?: boolean }
export interface WebhookFilters extends PaginationParams { search?: string; direction?: WebhookDirection; status?: WebhookStatus; event?: string }
export interface DeliveryFilters extends PaginationParams { webhook_id?: string; status?: DeliveryStatus; event?: string; created_after?: string; created_before?: string }
export interface MappingFilters extends PaginationParams { search?: string; integration_id?: string; source_field?: string; target_field?: string }

export const MODULE_API_PREFIX = '/api/v2/integration-platform';
export const INBOUND_WEBHOOK_HEADERS = {
  TIMESTAMP: 'X-SARAISE-Webhook-Timestamp',
  NONCE: 'X-SARAISE-Webhook-Nonce',
  SIGNATURE: 'X-SARAISE-Webhook-Signature',
} as const;
export const ENDPOINTS = {
  INTEGRATIONS: {
    LIST: `${MODULE_API_PREFIX}/integrations/`, CREATE: `${MODULE_API_PREFIX}/integrations/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/`, UPDATE: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/`, DELETE: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/`,
    ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/activate/`, DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/deactivate/`, TEST: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/test/`, SYNC: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/sync/`, JOB: (id: string, jobId: string) => `${MODULE_API_PREFIX}/integrations/${id}/jobs/${jobId}/`,
    CREDENTIALS: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/credentials/`,
  },
  CREDENTIALS: { DETAIL: (id: string) => `${MODULE_API_PREFIX}/integration-credentials/${id}/`, ROTATE: (id: string) => `${MODULE_API_PREFIX}/integration-credentials/${id}/rotate/`, REVOKE: (id: string) => `${MODULE_API_PREFIX}/integration-credentials/${id}/revoke/` },
  CONNECTORS: { LIST: `${MODULE_API_PREFIX}/connectors/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/connectors/${id}/`, SCHEMA: (id: string) => `${MODULE_API_PREFIX}/connectors/${id}/schema/`, HEALTH: (id: string) => `${MODULE_API_PREFIX}/connectors/${id}/health/` },
  WEBHOOKS: { LIST: `${MODULE_API_PREFIX}/webhooks/`, CREATE: `${MODULE_API_PREFIX}/webhooks/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/webhooks/${id}/`, UPDATE: (id: string) => `${MODULE_API_PREFIX}/webhooks/${id}/`, DELETE: (id: string) => `${MODULE_API_PREFIX}/webhooks/${id}/`, ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/webhooks/${id}/activate/`, DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/webhooks/${id}/deactivate/`, ROTATE_SECRET: (id: string) => `${MODULE_API_PREFIX}/webhooks/${id}/rotate-secret/`, INBOUND: (publicId: string) => `${MODULE_API_PREFIX}/webhooks/inbound/${publicId}/` },
  DELIVERIES: { LIST: `${MODULE_API_PREFIX}/webhook-deliveries/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/webhook-deliveries/${id}/`, REDRIVE: (id: string) => `${MODULE_API_PREFIX}/webhook-deliveries/${id}/redrive/` },
  MAPPINGS: { LIST: `${MODULE_API_PREFIX}/data-mappings/`, CREATE: `${MODULE_API_PREFIX}/data-mappings/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/data-mappings/${id}/`, UPDATE: (id: string) => `${MODULE_API_PREFIX}/data-mappings/${id}/`, DELETE: (id: string) => `${MODULE_API_PREFIX}/data-mappings/${id}/`, VALIDATE: `${MODULE_API_PREFIX}/data-mappings/validate/`, PREVIEW: `${MODULE_API_PREFIX}/data-mappings/preview/` },
  CONFIGURATION: { CURRENT: `${MODULE_API_PREFIX}/configuration/`, MANAGE_CAPABILITY: `${MODULE_API_PREFIX}/configuration/manage-capability/`, PREVIEW: `${MODULE_API_PREFIX}/configuration/preview/`, ROLLBACK: `${MODULE_API_PREFIX}/configuration/rollback/`, IMPORT: `${MODULE_API_PREFIX}/configuration/import/`, EXPORT: `${MODULE_API_PREFIX}/configuration/export/`, VERSIONS: `${MODULE_API_PREFIX}/configuration/versions/`, AUDITS: `${MODULE_API_PREFIX}/configuration/audits/` },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTE_PATHS = {
  INTEGRATIONS: '/integration-platform', INTEGRATION_CREATE: '/integration-platform/new', INTEGRATION_DETAIL: (id: string) => `/integration-platform/${id}`, INTEGRATION_EDIT: (id: string) => `/integration-platform/${id}/edit`,
  INTEGRATION_CREDENTIALS: (id: string) => `/integration-platform/${id}/credentials`, CREDENTIAL_CREATE: (id: string) => `/integration-platform/${id}/credentials/new`, CREDENTIAL_ROTATE: (id: string, credentialId: string) => `/integration-platform/${id}/credentials/${credentialId}/rotate`,
  CONNECTORS: '/integration-platform/connectors', CONNECTOR_DETAIL: (id: string) => `/integration-platform/connectors/${id}`, CONNECTOR_SETUP: (id: string) => `/integration-platform/connectors/${id}/setup`,
  WEBHOOKS: '/integration-platform/webhooks', WEBHOOK_CREATE: '/integration-platform/webhooks/new', WEBHOOK_DETAIL: (id: string) => `/integration-platform/webhooks/${id}`, WEBHOOK_EDIT: (id: string) => `/integration-platform/webhooks/${id}/edit`,
  DELIVERIES: '/integration-platform/deliveries', DELIVERY_DETAIL: (id: string) => `/integration-platform/deliveries/${id}`,
  MAPPINGS: '/integration-platform/mappings', MAPPING_CREATE: '/integration-platform/mappings/new', MAPPING_DETAIL: (id: string) => `/integration-platform/mappings/${id}`, MAPPING_EDIT: (id: string) => `/integration-platform/mappings/${id}/edit`,
  CONFIGURATION: '/integration-platform/configuration',
  MODULE_INSTALL: (moduleId: string) => `/marketplace/${moduleId}`,
} as const;
