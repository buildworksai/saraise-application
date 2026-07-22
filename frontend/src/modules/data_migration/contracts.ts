/** Typed public contract for the governed data-migration API. */

export const MODULE_API_PREFIX = '/api/v2/data-migration';

export interface PaginatedMeta {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface ResponseMeta {
  correlation_id: string;
  timestamp: string;
  pagination?: PaginatedMeta;
}

export interface ApiEnvelope<T> {
  data: T;
  meta: ResponseMeta;
}

export interface ApiErrorDetail {
  field?: string;
  code: string;
  message: string;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    correlation_id: string;
    details?: readonly ApiErrorDetail[];
  };
}

export interface PaginatedResult<T> {
  items: readonly T[];
  pagination: PaginatedMeta;
  correlationId: string;
}

export type SourceType = 'csv' | 'excel' | 'json' | 'xml' | 'database' | 'api';
export type WriteMode = 'create' | 'upsert';
export type JobStatus = 'draft' | 'ready' | 'archived';
export type RunStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled' | 'rolled_back';
export type RollbackStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface CsvSourceConfig {
  source_type: 'csv';
  delimiter: ',' | ';' | '\t' | '|';
  encoding: 'utf-8' | 'utf-8-sig' | 'utf-16';
  header_row: number;
  batch_size: number;
}

export interface ExcelSourceConfig {
  source_type: 'excel';
  sheet: string;
  header_row: number;
  batch_size: number;
}

export interface JsonSourceConfig {
  source_type: 'json';
  encoding: 'utf-8' | 'utf-8-sig' | 'utf-16';
  json_path: string;
  batch_size: number;
}

export interface XmlSourceConfig {
  source_type: 'xml';
  encoding: 'utf-8' | 'utf-8-sig' | 'utf-16';
  record_path: string;
  batch_size: number;
}

export interface DatabaseEqualityFilter {
  column: string;
  value: string | number | boolean | null;
}

export interface DatabaseSourceConfig {
  source_type: 'database';
  connection_id: string;
  table: string;
  columns: readonly string[];
  filters: readonly DatabaseEqualityFilter[];
  batch_size: number;
}

export interface ApiQueryParameter {
  name: string;
  value: string;
}

export interface ApiSourceConfig {
  source_type: 'api';
  connection_id: string;
  relative_path: string;
  method: 'GET';
  query_parameters: readonly ApiQueryParameter[];
  results_path: string;
  page_parameter: string;
  page_size_parameter: string;
  page_size: number;
}

export type SourceConfig = CsvSourceConfig | ExcelSourceConfig | JsonSourceConfig | XmlSourceConfig | DatabaseSourceConfig | ApiSourceConfig;
export type SourceConfigInput = Omit<CsvSourceConfig, 'source_type'> | Omit<ExcelSourceConfig, 'source_type'> | Omit<JsonSourceConfig, 'source_type'> | Omit<XmlSourceConfig, 'source_type'> | Omit<DatabaseSourceConfig, 'source_type'> | Omit<ApiSourceConfig, 'source_type'>;

export type TransformConfig =
  | { transform_type: 'identity' }
  | { transform_type: 'cast'; target_type: 'string' | 'integer' | 'decimal' | 'boolean' | 'date' | 'datetime' }
  | { transform_type: 'default'; value: string | number | boolean | null; only_when_empty: boolean }
  | { transform_type: 'lookup'; lookup_name: string; source_key: string; result_field: string }
  | { transform_type: 'concat'; source_fields: readonly string[]; separator: string }
  | { transform_type: 'split'; delimiter: string; index: number }
  | { transform_type: 'regex_replace'; pattern: string; replacement: string }
  | { transform_type: 'date_parse'; input_format: string; output_format: string; timezone: string }
  | { transform_type: 'boolean_map'; true_values: readonly string[]; false_values: readonly string[] };

export type ValidationRuleConfig =
  | { rule_type: 'required'; trim: boolean }
  | { rule_type: 'type'; expected_type: 'string' | 'integer' | 'decimal' | 'boolean' | 'date' | 'datetime' }
  | { rule_type: 'range'; minimum?: number; maximum?: number; inclusive: boolean }
  | { rule_type: 'length'; minimum?: number; maximum?: number }
  | { rule_type: 'regex'; pattern: string; flags: readonly ('i' | 'm')[] }
  | { rule_type: 'unique'; scope_fields: readonly string[] }
  | { rule_type: 'referential'; adapter: string; entity: string; lookup_field: string }
  | { rule_type: 'allowed_values'; values: readonly (string | number | boolean)[]; case_sensitive: boolean };

export interface LatestRunSummary {
  id: string;
  mode: 'dry_run' | 'commit';
  status: RunStatus;
  processed_records: number;
  total_records: number;
  succeeded_records: number;
  failed_records: number;
  warning_records: number;
  created_at: string;
  completed_at: string | null;
}

export type JobAction = 'read' | 'update' | 'delete' | 'validate' | 'archive' | 'restore' | 'inspect' | 'preview' | 'dry_run' | 'run' | 'export';

export interface ExternalConnection {
  id: string;
  name: string;
  kind: 'postgresql' | 'mysql' | 'http';
  is_active: boolean;
  created_at: string;
  updated_at: string;
  allowed_actions?: readonly ('read' | 'update' | 'rotate' | 'deactivate' | 'test')[];
}

export interface MigrationJob {
  id: string;
  name: string;
  description: string;
  source_type: SourceType;
  source_artifact_id: string | null;
  source_config: SourceConfigInput;
  target_adapter: string;
  target_entity: string;
  write_mode: WriteMode;
  lookup_fields: readonly string[];
  status: JobStatus;
  configuration_version: number;
  readiness: { ready: boolean; blockers: readonly { code: string; message: string; section: 'source' | 'target' | 'mappings' | 'rules' }[] };
  latest_run: LatestRunSummary | null;
  allowed_actions?: readonly JobAction[];
  created_at: string;
  updated_at: string;
}

export interface MigrationJobVersion {
  id: string;
  job: string;
  version: number;
  snapshot: ExportDefinitionPayload;
  change_summary: string;
  created_by: string;
  correlation_id: string;
  created_at: string;
}

export interface MigrationMapping {
  id: string;
  job: string;
  source_field: string;
  target_field: string;
  position: number;
  transform_type: TransformConfig['transform_type'];
  transform_config: TransformConfig;
  is_required: boolean;
  origin: 'manual' | 'deterministic' | 'extension';
  confidence: string | null;
  created_at: string;
  updated_at: string;
}

export interface ValidationRule {
  id: string;
  job: string;
  field_name: string;
  rule_type: ValidationRuleConfig['rule_type'];
  rule_config: ValidationRuleConfig;
  error_message: string;
  severity: 'warning' | 'error';
  position: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MigrationRun {
  id: string;
  job: string;
  job_version: string;
  mode: 'dry_run' | 'commit';
  status: RunStatus;
  source_checksum: string;
  total_records: number;
  processed_records: number;
  succeeded_records: number;
  failed_records: number;
  warning_records: number;
  started_at: string | null;
  completed_at: string | null;
  cancel_requested_at: string | null;
  correlation_id: string;
  rollback_eligible: boolean;
  allowed_actions?: readonly ('cancel' | 'rollback' | 'export_issues')[];
  created_at: string;
  updated_at: string;
}

export interface RedactedSample {
  fields: readonly { name: string; value: string | number | boolean | null; redacted: boolean }[];
}

export interface MigrationRunIssue {
  id: string;
  run: string;
  row_number: number | null;
  field_name: string;
  stage: 'source' | 'mapping' | 'validation' | 'target' | 'system';
  severity: 'warning' | 'error';
  code: string;
  message: string;
  remediation?: string;
  redacted_sample: RedactedSample;
  created_at: string;
}

export interface MigrationChange {
  id: string;
  run: string;
  sequence: number;
  target_adapter: string;
  target_entity: string;
  target_record_id: string;
  operation: 'create' | 'update';
  after_checksum: string;
  reversed_at: string | null;
  created_at: string;
}

export interface MigrationRollback {
  id: string;
  run: string;
  status: RollbackStatus;
  records_total: number;
  records_reversed: number;
  records_failed: number;
  failure_summary: string;
  started_at: string | null;
  completed_at: string | null;
  correlation_id: string;
  created_at: string;
  updated_at: string;
}

export type MigrationJobCreate = {
  name: string;
  description: string;
  source_type: SourceType;
  source_artifact_id?: string | null;
  source_config: SourceConfigInput;
  target_adapter: string;
  target_entity: string;
  write_mode: WriteMode;
  lookup_fields: readonly string[];
};

export type MigrationJobUpdate = Partial<Omit<MigrationJobCreate, 'source_type'>> & { source_type?: SourceType; expected_version: number };
export interface MigrationMappingCreate { source_field: string; target_field: string; position: number; transform_config: TransformConfig; is_required: boolean }
export type MigrationMappingUpdate = Partial<MigrationMappingCreate>;
export interface MappingReorderPayload { ordered_ids: readonly string[]; expected_version: number }
export interface ValidationRuleCreate { field_name: string; rule_config: ValidationRuleConfig; error_message: string; severity: 'warning' | 'error'; position: number; is_active: boolean }
export type ValidationRuleUpdate = Partial<ValidationRuleCreate>;
export interface RuleReorderPayload { ordered_ids: readonly string[]; expected_version: number }
export interface RunRequest { idempotency_key: string }
export interface CancelRunRequest { transition_key: string }
export interface RollbackRequest { idempotency_key: string }
export interface InspectRequest { idempotency_key: string }
export interface RestoreVersionRequest { expected_version: number; change_summary: string }

export interface ExternalConnectionCreate {
  name: string;
  kind: ExternalConnection['kind'];
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  base_url?: string;
  credential_ref: string;
  tls_mode: 'verify-full';
  public_options: { connect_timeout_seconds?: number; read_timeout_seconds?: number };
}
export type ExternalConnectionUpdate = Partial<Omit<ExternalConnectionCreate, 'kind' | 'credential_ref'>>;

export interface SourceProfileField { name: string; detected_type: string; nullable: boolean; distinct_estimate: number; samples: readonly string[] }
export interface SourceProfile { fields: readonly SourceProfileField[]; representative_values: readonly RedactedSample[]; row_estimate: number; source_checksum: string; warnings: readonly string[] }
export interface AsyncOperationAccepted { async_job_id: string; status: 'queued' | 'running' | 'succeeded' | 'failed' }
export interface PreviewRecord { fields: readonly { name: string; value: string | number | boolean | null; redacted: boolean }[] }
export interface PreviewResult { records: readonly PreviewRecord[]; source_checksum: string; truncated: boolean }
export interface MappingSuggestion { id: string; source_field: string; target_field: string; transform_config?: TransformConfig; confidence: number; rationale?: string; pii?: boolean; origin: 'deterministic' | 'extension' }
export interface DefinitionDiffEntry { path: string; operation: 'add' | 'remove' | 'replace'; before?: string | number | boolean | null; after?: string | number | boolean | null }
export interface DefinitionDiff { from_version: number | null; to_version: number | null; entries: readonly DefinitionDiffEntry[]; warnings: readonly string[] }
export interface ConnectionTestResult { verified: boolean; outcome: 'success' | 'timeout' | 'circuit_open' | 'denied_destination' | 'authentication_failed' | 'unavailable'; checked_at: string; latency_ms?: number; code: string; message: string }
export interface ExportDefinitionPayload { schema_version: '2.0'; checksum: string; job: MigrationJobCreate; mappings: readonly MigrationMappingCreate[]; rules: readonly ValidationRuleCreate[] }
export interface ImportDefinitionPayload { document: ExportDefinitionPayload; preview_only: boolean }
export interface ImportDefinitionResult { job: MigrationJob | null; diff: DefinitionDiff; checksum_valid: boolean }

export interface DataMigrationConfiguration {
  source_row_limit: number;
  batch_size: number;
  connect_timeout_seconds: number;
  read_timeout_seconds: number;
  retry_count: number;
  issue_sample_limit: number;
  preview_row_limit: number;
  retention_days: number;
  allowed_target_adapters: readonly string[];
  enabled_roles: readonly string[];
  rollout_percentage: number;
  enabled: boolean;
  version: number;
  updated_at?: string;
}
export type DataMigrationConfigurationValues = Omit<DataMigrationConfiguration, 'version' | 'updated_at'>;
export interface DataMigrationConfigurationUpdate extends DataMigrationConfigurationValues { expected_version: number }
export interface ConfigurationDiff { from_version: number; changes: readonly { field: string; before?: unknown; after?: unknown }[] }
export interface ConfigurationPreviewResponse { from_version: number; changes: readonly { field: string; before: string | number | boolean | readonly string[] | null; after: string | number | boolean | readonly string[] | null }[] }
export interface DataMigrationConfigurationVersion { id: string; configuration: string; version: number; before: DataMigrationConfigurationValues; after: DataMigrationConfigurationValues; changed_by: string; correlation_id: string; created_at: string; change_summary?: string }
export interface ConfigurationExportDocument { schema_version: 1; checksum: string; configuration: DataMigrationConfigurationValues }
export interface ConfigurationImportPayload extends ConfigurationExportDocument { expected_version: number }

export interface JobFilters { page?: number; page_size?: number; search?: string; status?: JobStatus; source_type?: SourceType; target_adapter?: string; target_entity?: string; ordering?: 'name' | '-name' | 'created_at' | '-created_at' | 'updated_at' | '-updated_at' }
export interface RunFilters { page?: number; page_size?: number; mode?: MigrationRun['mode']; status?: RunStatus; created_after?: string; created_before?: string }
export interface IssueFilters { page?: number; page_size?: number; severity?: MigrationRunIssue['severity']; stage?: MigrationRunIssue['stage']; code?: string; row_number?: number }
export interface PageFilters { page?: number; page_size?: number }

/** All data-migration URLs live here; callers must never construct API paths. */
export const ENDPOINTS = {
  JOBS: {
    LIST: `${MODULE_API_PREFIX}/jobs/`, CREATE: `${MODULE_API_PREFIX}/jobs/`, IMPORT: `${MODULE_API_PREFIX}/jobs/import/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/` as const,
    VALIDATE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/validate/` as const,
    ARCHIVE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/archive/` as const,
    RESTORE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/restore/` as const,
    SOURCE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/source/` as const,
    INSPECT: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/inspect/` as const,
    PREVIEW: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/preview/` as const,
    EXPORT: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/export/` as const,
    VERSIONS: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/versions/` as const,
    RESTORE_VERSION: (id: string, version: number) => `${MODULE_API_PREFIX}/jobs/${id}/versions/${version}/restore/` as const,
    MAPPINGS: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/mappings/` as const,
    SUGGEST_MAPPINGS: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/mappings/suggest/` as const,
    APPLY_MAPPINGS: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/mappings/apply/` as const,
    RULES: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/validation-rules/` as const,
    RUNS: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/runs/` as const,
    DRY_RUNS: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/dry-runs/` as const,
  },
  MAPPINGS: { DETAIL: (id: string) => `${MODULE_API_PREFIX}/mappings/${id}/` as const },
  RULES: { DETAIL: (id: string) => `${MODULE_API_PREFIX}/validation-rules/${id}/` as const },
  RUNS: {
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/` as const,
    ISSUES: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/issues/` as const,
    EXPORT_ISSUES: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/issues/export/` as const,
    CANCEL: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/cancel/` as const,
    ROLLBACK: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/rollback/` as const,
  },
  ROLLBACKS: { DETAIL: (id: string) => `${MODULE_API_PREFIX}/rollbacks/${id}/` as const },
  CONNECTIONS: {
    LIST: `${MODULE_API_PREFIX}/connections/`, CREATE: `${MODULE_API_PREFIX}/connections/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/connections/${id}/` as const,
    DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/connections/${id}/deactivate/` as const,
    TEST: (id: string) => `${MODULE_API_PREFIX}/connections/${id}/test/` as const,
  },
  CONFIGURATION: {
    DETAIL: `${MODULE_API_PREFIX}/configuration/`,
    PREVIEW: `${MODULE_API_PREFIX}/configuration/preview/`,
    VERSIONS: `${MODULE_API_PREFIX}/configuration/versions/`,
    RESTORE: (version: number) => `${MODULE_API_PREFIX}/configuration/versions/${version}/restore/` as const,
    EXPORT: `${MODULE_API_PREFIX}/configuration/export/`,
    IMPORT: `${MODULE_API_PREFIX}/configuration/import/`,
  },
  HEALTH: { LIVE: `${MODULE_API_PREFIX}/health/live/`, READY: `${MODULE_API_PREFIX}/health/ready/` },
} as const;
