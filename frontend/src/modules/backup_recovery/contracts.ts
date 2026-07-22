/** Provider-neutral, governed API v2 contracts for Backup Recovery. */

export type UUID = string;
export type ISODateTime = string;
export type BackupType = "full" | "incremental" | "differential";
export type ScopeType = "tenant" | "module" | "database" | "files";
export type BackupJobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export type BackupFrequency = "hourly" | "daily" | "weekly" | "monthly";
export type ArchiveLifecycle = "available" | "expired" | "purged";
export type IntegrityStatus = "unknown" | "verifying" | "verified" | "corrupt";
export type VerificationStatus = "pending" | "running" | "passed" | "failed" | "cancelled";
export type SortDirection<T extends string> = T | `-${T}`;

export interface ActionCapability {
  allowed: boolean;
  reason_code?: string;
  reason?: string;
}
export type AllowedCommands = Readonly<Record<string, ActionCapability>>;

interface EntityBase {
  id: UUID;
  created_by: string;
  updated_by: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}
interface MutableEntityBase extends EntityBase {
  is_deleted: boolean;
  deleted_at: ISODateTime | null;
}

export interface BackupStorageTarget extends MutableEntityBase {
  name: string;
  adapter_key: string;
  locator_prefix_ref: string;
  configuration_ref: string;
  encryption_key_ref: string;
  is_default: boolean;
  is_active: boolean;
  allowed_commands?: AllowedCommands;
}

export interface BackupRetentionPolicy extends MutableEntityBase {
  name: string;
  description: string;
  archive_after_days: number | null;
  retention_days: number;
  keep_last_successful: number;
  is_active: boolean;
  allowed_commands?: AllowedCommands;
}

export interface BackupSchedule extends MutableEntityBase {
  name: string;
  scope_type: ScopeType;
  scope_ref: string;
  backup_type: BackupType;
  frequency: BackupFrequency;
  schedule_time: string | null;
  day_of_week: number | null;
  day_of_month: number | null;
  timezone: string;
  storage_target: UUID;
  storage_target_name?: string;
  retention_policy: UUID;
  retention_policy_name?: string;
  is_active: boolean;
  next_run_at: ISODateTime | null;
  last_run_at: ISODateTime | null;
  description: string;
  allowed_commands?: AllowedCommands;
}

export interface StateTransition {
  command: string;
  from: string;
  to: string;
  at: ISODateTime;
  actor_id?: string;
  correlation_id?: string;
}

export interface BackupJob extends MutableEntityBase {
  schedule: UUID | null;
  schedule_name?: string | null;
  storage_target: UUID;
  storage_target_name?: string;
  retention_policy: UUID | null;
  retry_of: UUID | null;
  base_job: UUID | null;
  async_job_id: UUID | null;
  scope_type: ScopeType;
  scope_ref: string;
  backup_type: BackupType;
  status: BackupJobStatus;
  idempotency_key: string;
  description: string;
  requested_at: ISODateTime;
  started_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  data_cutoff_at: ISODateTime | null;
  size_bytes: number | null;
  error_code: string;
  error_message: string;
  transition_history: readonly StateTransition[];
  archive?: BackupArchiveSummary | null;
  correlation_id?: string | null;
  allowed_commands?: AllowedCommands;
}

export interface BackupArchiveSummary {
  id: UUID;
  lifecycle: ArchiveLifecycle;
  checksum_algorithm: string;
  checksum_digest?: string;
  integrity_status: IntegrityStatus;
}

export interface BackupArchive extends EntityBase {
  backup_job: UUID;
  backup_type?: BackupType;
  lifecycle: ArchiveLifecycle;
  adapter_key: string;
  artifact_locator_ref: string;
  size_bytes: number;
  checksum_algorithm: string;
  checksum_digest: string;
  provider_acknowledgement: string;
  data_cutoff_at: ISODateTime;
  captured_at: ISODateTime;
  expires_at: ISODateTime | null;
  archived_at: ISODateTime;
  integrity_status: IntegrityStatus;
  last_verified_at: ISODateTime | null;
  purged_at: ISODateTime | null;
  allowed_commands?: AllowedCommands;
}

export interface BackupVerification extends EntityBase {
  archive: UUID;
  async_job_id: UUID | null;
  status: VerificationStatus;
  idempotency_key: string;
  requested_at: ISODateTime;
  started_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  checksum_matches: boolean | null;
  artifact_available: boolean | null;
  encryption_metadata_valid: boolean | null;
  provider_acknowledged: boolean | null;
  evidence: Readonly<Record<string, unknown>>;
  error_code: string;
  error_message: string;
  correlation_id?: string | null;
  allowed_commands?: AllowedCommands;
}

export interface BackupJobCreate {
  backup_type: BackupType;
  scope_type: ScopeType;
  scope_ref: string;
  idempotency_key: string;
  storage_target_id?: UUID;
  retention_policy_id?: UUID;
  schedule_id?: UUID;
  description?: string;
}
export interface BackupJobUpdate {
  description: string;
}
export interface BackupJobCancelRequest {
  transition_key: string;
}
export interface BackupJobRetryRequest {
  idempotency_key: string;
}
export interface BackupRequestReceipt {
  job_id: UUID;
  async_job_id: UUID;
  status: BackupJobStatus;
  idempotency_key: string;
  correlation_id?: string;
}

export interface BackupScheduleCreate {
  name: string;
  scope_type: ScopeType;
  scope_ref: string;
  backup_type: BackupType;
  frequency: BackupFrequency;
  schedule_time?: string | null;
  day_of_week?: number | null;
  day_of_month?: number | null;
  timezone: string;
  storage_target_id: UUID;
  retention_policy_id: UUID;
  description?: string;
}
export type BackupScheduleUpdate = Partial<BackupScheduleCreate>;
export interface ScheduleRunNowRequest {
  idempotency_key: string;
}

export interface BackupRetentionPolicyCreate {
  name: string;
  description?: string;
  archive_after_days?: number | null;
  retention_days: number;
  keep_last_successful?: number;
}
export type BackupRetentionPolicyUpdate = Partial<BackupRetentionPolicyCreate>;
export interface RetentionPreview {
  captured_at: ISODateTime;
  archive_at: ISODateTime | null;
  expires_at: ISODateTime;
  retention_days: number;
  archive_after_days: number | null;
  keep_last_successful: number;
}

export interface BackupStorageTargetCreate {
  name: string;
  adapter_key: string;
  locator_prefix_ref: string;
  configuration_ref: string;
  encryption_key_ref?: string;
}
export type BackupStorageTargetUpdate = Partial<BackupStorageTargetCreate>;
export interface StorageTargetProbeResult {
  healthy: boolean;
  message: string;
  checked_at: ISODateTime;
  details: Readonly<Record<string, unknown>>;
  correlation_id?: string;
}

export interface BackupVerificationCreate {
  idempotency_key: string;
}
export interface BackupVerificationCancelRequest {
  transition_key: string;
}

export interface BackupJobFilters {
  status?: BackupJobStatus;
  backup_type?: BackupType;
  schedule_id?: UUID;
  scope_type?: ScopeType;
  scope_ref?: string;
  requested_after?: string;
  requested_before?: string;
  search?: string;
  ordering?: SortDirection<"requested_at" | "completed_at" | "size_bytes">;
  page?: number;
  page_size?: number;
}
export interface BackupScheduleFilters {
  is_active?: boolean;
  frequency?: BackupFrequency;
  backup_type?: BackupType;
  scope_type?: ScopeType;
  storage_target_id?: UUID;
  search?: string;
  ordering?: SortDirection<"name" | "next_run_at" | "created_at">;
  page?: number;
  page_size?: number;
}
export interface RetentionPolicyFilters {
  is_active?: boolean;
  search?: string;
  ordering?: SortDirection<"name" | "retention_days" | "created_at">;
  page?: number;
  page_size?: number;
}
export interface StorageTargetFilters {
  is_active?: boolean;
  is_default?: boolean;
  adapter_key?: string;
  search?: string;
  ordering?: SortDirection<"name" | "created_at">;
  page?: number;
  page_size?: number;
}
export interface ArchiveFilters {
  lifecycle?: ArchiveLifecycle;
  integrity_status?: IntegrityStatus;
  backup_job_id?: UUID;
  backup_type?: BackupType;
  expires_before?: string;
  captured_after?: string;
  search?: string;
  ordering?: SortDirection<"captured_at" | "expires_at" | "size_bytes">;
  page?: number;
  page_size?: number;
}
export interface VerificationFilters {
  status?: VerificationStatus;
  archive_id?: UUID;
  requested_after?: string;
  requested_before?: string;
  ordering?: SortDirection<"requested_at" | "completed_at">;
  page?: number;
  page_size?: number;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  count: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}
export interface ApiV2Meta {
  correlation_id: string;
  timestamp: ISODateTime;
  pagination?: PaginationMeta;
}
export interface ApiV2Envelope<T> {
  data: T;
  meta: ApiV2Meta;
}
export interface ApiV2Page<T> {
  data: T[];
  meta: ApiV2Meta & { pagination: PaginationMeta };
}
export interface PaginatedResult<T> {
  items: T[];
  pagination: PaginationMeta;
  correlationId: string;
}
export interface GovernedFieldError {
  field: string;
  code?: string;
  message: string;
}
export interface GovernedError {
  code: string;
  message: string;
  detail: unknown;
  /** Some gateways project status in-body; the HTTP status remains authoritative. */
  status?: number;
  field_errors?: readonly GovernedFieldError[] | Record<string, readonly string[]>;
  correlation_id?: string;
}
export interface GovernedErrorEnvelope {
  error: GovernedError;
  meta?: Partial<ApiV2Meta>;
}

export interface DependencyHealth {
  key: string;
  status: "healthy" | "degraded" | "unavailable";
  critical: boolean;
  detail?: string;
  latency_ms?: number;
}
export interface ModuleHealth {
  status: "healthy" | "degraded" | "unavailable";
  ready: boolean;
  checked_at: ISODateTime;
  database: DependencyHealth;
  async_jobs: DependencyHealth;
  outbox: DependencyHealth;
  scheduler: DependencyHealth;
  adapters: readonly DependencyHealth[];
  oldest_pending_outbox_seconds?: number | null;
  correlation_id?: string;
}

export const MODULE_API_PREFIX = "/api/v2/backup-recovery";
export const ENDPOINTS = {
  JOBS: {
    LIST: `${MODULE_API_PREFIX}/jobs/`,
    CREATE: `${MODULE_API_PREFIX}/jobs/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/`,
    CANCEL: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/cancel/`,
    RETRY: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/retry/`,
  },
  SCHEDULES: {
    LIST: `${MODULE_API_PREFIX}/schedules/`,
    CREATE: `${MODULE_API_PREFIX}/schedules/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/`,
    ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/activate/`,
    DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/deactivate/`,
    RUN_NOW: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/run-now/`,
  },
  RETENTION_POLICIES: {
    LIST: `${MODULE_API_PREFIX}/retention-policies/`,
    CREATE: `${MODULE_API_PREFIX}/retention-policies/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/retention-policies/${id}/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/retention-policies/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/retention-policies/${id}/`,
    ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/retention-policies/${id}/activate/`,
    DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/retention-policies/${id}/deactivate/`,
    PREVIEW: (id: string) => `${MODULE_API_PREFIX}/retention-policies/${id}/preview/`,
  },
  STORAGE_TARGETS: {
    LIST: `${MODULE_API_PREFIX}/storage-targets/`,
    CREATE: `${MODULE_API_PREFIX}/storage-targets/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/storage-targets/${id}/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/storage-targets/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/storage-targets/${id}/`,
    ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/storage-targets/${id}/activate/`,
    DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/storage-targets/${id}/deactivate/`,
    SET_DEFAULT: (id: string) => `${MODULE_API_PREFIX}/storage-targets/${id}/set-default/`,
    PROBE: (id: string) => `${MODULE_API_PREFIX}/storage-targets/${id}/probe/`,
  },
  ARCHIVES: {
    LIST: `${MODULE_API_PREFIX}/archives/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/archives/${id}/`,
    VERIFY: (id: string) => `${MODULE_API_PREFIX}/archives/${id}/verify/`,
  },
  VERIFICATIONS: {
    LIST: `${MODULE_API_PREFIX}/verifications/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/verifications/${id}/`,
    CANCEL: (id: string) => `${MODULE_API_PREFIX}/verifications/${id}/cancel/`,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
