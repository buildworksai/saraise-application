/**
 * Public, provider-neutral contracts for Backup & Disaster Recovery.
 *
 * The UI deliberately models normalized evidence only. Secret references,
 * artifact locators, encryption keys, and provider payloads never cross this
 * boundary.
 */

export type UUID = string;
export type ISODateTime = string;

export type ScopeType = 'tenant' | 'module' | 'database' | 'files';
export type BackupType = 'full' | 'incremental' | 'differential';
export type RecoveryPointStatus =
  | 'discovered'
  | 'verifying'
  | 'available'
  | 'corrupt'
  | 'expired'
  | 'deleted';
export type RestoreTargetEnvironment = 'isolated' | 'standby' | 'production';
export type RestoreMode = 'full' | 'selective';
export type RestoreRunStatus =
  | 'queued'
  | 'validating'
  | 'ready'
  | 'restoring'
  | 'verifying'
  | 'succeeded'
  | 'failed'
  | 'cancelled';
export type RunbookStatus = 'draft' | 'published' | 'retired';
export type RunbookActionType =
  | 'validate_recovery_point'
  | 'restore'
  | 'verify'
  | 'failover'
  | 'failback'
  | 'manual_approval'
  | 'notify'
  | 'extension';
export type OnFailurePolicy = 'stop' | 'continue_degraded';
export type ExerciseType = 'tabletop' | 'restore' | 'failover' | 'full';
export type ExerciseEnvironment = 'isolated' | 'standby' | 'production';
export type ExerciseStatus = 'scheduled' | 'queued' | 'running' | 'passed' | 'failed' | 'cancelled';
export type StepExecutionStatus = 'pending' | 'running' | 'passed' | 'failed' | 'degraded' | 'skipped';
export type ObjectiveBucket = 'day' | 'week' | 'month';
export type HealthState = 'operational' | 'degraded' | 'unavailable';

export type JSONPrimitive = string | number | boolean | null;
export type JSONValue = JSONPrimitive | readonly JSONValue[] | { readonly [key: string]: JSONValue };
export type JSONObject = Readonly<Record<string, JSONValue>>;

export interface TransitionRecord {
  readonly transition_key: string;
  readonly command: string;
  readonly from_state: string;
  readonly to_state: string;
  readonly occurred_at: ISODateTime;
  readonly metadata: JSONObject;
}

export interface ArtifactValidationEvidence {
  readonly kind: 'artifact_validation';
  readonly checksum_valid: boolean;
  readonly artifact_available: boolean;
  readonly encryption_metadata_valid: boolean;
  readonly provider_acknowledged: boolean;
  readonly checked_at: ISODateTime;
}

export interface RestoreValidationEvidence {
  readonly kind: 'restore_validation';
  readonly artifact_valid: boolean;
  readonly target_registered: boolean;
  readonly capacity_available: boolean;
  readonly compatible: boolean;
  readonly conflict_free: boolean;
  readonly checked_at: ISODateTime;
}

export interface RestoreVerificationEvidence {
  readonly kind: 'restore_verification';
  readonly provider_acknowledged: boolean;
  readonly integrity_valid: boolean;
  readonly components_verified: readonly string[];
  readonly verified_at: ISODateTime;
}

export interface ManualApprovalEvidence {
  readonly kind: 'manual_approval';
  readonly approved: boolean;
  readonly approver_id: UUID;
  readonly decided_at: ISODateTime;
  readonly note: string;
}

export interface NotificationEvidence {
  readonly kind: 'notification';
  readonly channel: 'email' | 'in_app' | 'webhook';
  readonly acknowledged: boolean;
  readonly delivered_at: ISODateTime | null;
}

export interface FailoverEvidence {
  readonly kind: 'failover' | 'failback';
  readonly target_ref: string;
  readonly provider_acknowledged: boolean;
  readonly health_check_passed: boolean;
  readonly completed_at: ISODateTime;
}

export interface ExtensionEvidence {
  readonly kind: 'extension';
  readonly extension_action_key: string;
  readonly outcome: 'passed' | 'failed' | 'degraded';
  readonly summary: string;
  readonly completed_at: ISODateTime;
}

export type StepExecutionEvidence =
  | ArtifactValidationEvidence
  | RestoreVerificationEvidence
  | ManualApprovalEvidence
  | NotificationEvidence
  | FailoverEvidence
  | ExtensionEvidence;

export interface ValidateRecoveryPointParameters {
  readonly action_type: 'validate_recovery_point';
  readonly require_checksum: boolean;
  readonly require_encryption: boolean;
}

export interface RestoreParameters {
  readonly action_type: 'restore';
  readonly restore_mode: RestoreMode;
  readonly selected_components: readonly string[];
}

export interface VerifyParameters {
  readonly action_type: 'verify';
  readonly checks: readonly string[];
}

export interface FailoverParameters {
  readonly action_type: 'failover' | 'failback';
  readonly target_ref: string;
}

export interface ManualApprovalParameters {
  readonly action_type: 'manual_approval';
  readonly instructions: string;
}

export interface NotifyParameters {
  readonly action_type: 'notify';
  readonly channel_ref: string;
  readonly message_template: string;
}

export interface ExtensionParameters {
  readonly action_type: 'extension';
  readonly configuration_ref: string;
}

export type RunbookStepParameters =
  | ValidateRecoveryPointParameters
  | RestoreParameters
  | VerifyParameters
  | FailoverParameters
  | ManualApprovalParameters
  | NotifyParameters
  | ExtensionParameters;

interface EntityTimestamps {
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
}

export interface RecoveryPoint extends EntityTimestamps {
  readonly id: UUID;
  readonly scope_type: ScopeType;
  readonly scope_ref: string;
  readonly backup_type: BackupType;
  readonly status: RecoveryPointStatus;
  readonly data_cutoff_at: ISODateTime;
  readonly captured_at: ISODateTime;
  readonly verified_at: ISODateTime | null;
  readonly expires_at: ISODateTime | null;
  readonly size_bytes: number | null;
  readonly verification_evidence: ArtifactValidationEvidence | null;
}

export interface RestoreRun extends EntityTimestamps {
  readonly id: UUID;
  readonly recovery_point_id: UUID;
  readonly runbook_id: UUID | null;
  readonly exercise_id: UUID | null;
  readonly target_environment: RestoreTargetEnvironment;
  readonly target_ref: string;
  readonly restore_mode: RestoreMode;
  readonly selected_components: readonly string[];
  readonly status: RestoreRunStatus;
  readonly requested_at: ISODateTime;
  readonly started_at: ISODateTime | null;
  readonly completed_at: ISODateTime | null;
  readonly achieved_rpo_seconds: number | null;
  readonly achieved_rto_seconds: number | null;
}

export interface DRRunbook extends EntityTimestamps {
  readonly id: UUID;
  readonly name: string;
  readonly slug: string;
  readonly version: number;
  readonly status: RunbookStatus;
  readonly description: string;
  readonly scope_type: ScopeType;
  readonly scope_ref: string;
  readonly backup_schedule_id: UUID | null;
  readonly rpo_target_seconds: number;
  readonly rto_target_seconds: number;
  readonly supersedes_id: UUID | null;
  readonly published_at: ISODateTime | null;
  readonly retired_at: ISODateTime | null;
  readonly steps?: readonly RunbookStep[];
}

export interface RunbookStep extends EntityTimestamps {
  readonly id: UUID;
  readonly runbook_id: UUID;
  readonly step_key: string;
  readonly position: number;
  readonly name: string;
  readonly description: string;
  readonly action_type: RunbookActionType;
  readonly extension_action_key: string | null;
  readonly parameters: RunbookStepParameters;
  readonly timeout_seconds: number;
  readonly retry_limit: number;
  readonly on_failure: OnFailurePolicy;
  readonly approval_permission: string | null;
}

export interface DRExercise extends EntityTimestamps {
  readonly id: UUID;
  readonly name: string;
  readonly runbook_id: UUID;
  readonly recovery_point_id: UUID | null;
  readonly exercise_type: ExerciseType;
  readonly environment: ExerciseEnvironment;
  readonly status: ExerciseStatus;
  readonly scheduled_for: ISODateTime;
  readonly started_at: ISODateTime | null;
  readonly completed_at: ISODateTime | null;
  readonly summary: string;
  readonly observed_rpo_seconds: number | null;
  readonly observed_rto_seconds: number | null;
  readonly rpo_met: boolean | null;
  readonly rto_met: boolean | null;
  readonly failed_step_id: UUID | null;
}

export interface ExerciseEvidenceSummary {
  readonly total_steps: number;
  readonly passed_steps: number;
  readonly failed_steps: number;
  readonly degraded_steps: number;
  readonly skipped_steps: number;
}

export interface DRStepExecution extends EntityTimestamps {
  readonly id: UUID;
  readonly exercise_id: UUID;
  readonly runbook_step_id: UUID;
  readonly status: StepExecutionStatus;
  readonly attempt: number;
  readonly started_at: ISODateTime | null;
  readonly completed_at: ISODateTime | null;
}

export interface BackupExecutionCreateRequest {
  readonly backup_type: BackupType;
  readonly scope_type: ScopeType;
  readonly scope_ref: string;
  readonly idempotency_key: string;
}

export interface BackupExecutionReceipt {
  readonly backup_job_id: UUID;
  readonly async_job_id: UUID;
  readonly status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  readonly requested_at: ISODateTime;
}

export interface DurableJobReceipt {
  readonly async_job_id: UUID;
  readonly status: 'queued';
  readonly accepted_at: ISODateTime;
}

export interface BackupExecutionStatus {
  readonly backup_job_id: UUID;
  readonly status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  readonly completed_at: ISODateTime | null;
  readonly recovery_point_id: UUID | null;
  readonly safe_error: string;
}

export interface RecoveryPointVerifyRequest { readonly idempotency_key: string; }
export interface RecoveryPointExpireRequest { readonly transition_key: string; }

export interface RestoreRunCreateRequest {
  readonly recovery_point_id: UUID;
  readonly runbook_id?: UUID;
  readonly exercise_id?: UUID;
  readonly target_environment: RestoreTargetEnvironment;
  readonly target_ref: string;
  readonly restore_mode: RestoreMode;
  readonly selected_components: readonly string[];
  readonly idempotency_key: string;
}

export interface RestoreRunExecuteRequest { readonly idempotency_key: string; }
export interface RestoreRunCancelRequest { readonly transition_key: string; }

export interface DRRunbookCreateRequest {
  readonly name: string;
  readonly slug: string;
  readonly description: string;
  readonly scope_type: ScopeType;
  readonly scope_ref: string;
  readonly backup_schedule_id?: UUID;
  readonly rpo_target_seconds: number;
  readonly rto_target_seconds: number;
}

export type DRRunbookUpdateRequest = Partial<DRRunbookCreateRequest>;
export interface RunbookTransitionRequest { readonly transition_key: string; }
export interface RunbookStepCreateRequest {
  readonly runbook_id: UUID;
  readonly step_key: string;
  readonly position: number;
  readonly name: string;
  readonly description: string;
  readonly action_type: RunbookActionType;
  readonly extension_action_key?: string;
  readonly approval_permission?: string;
  readonly parameters: RunbookStepParameters;
  readonly timeout_seconds: number;
  readonly retry_limit: number;
  readonly on_failure: OnFailurePolicy;
}
export type RunbookStepUpdateRequest = Partial<Omit<RunbookStepCreateRequest, 'runbook_id'>>;
export interface RunbookStepReorderRequest { readonly step_ids: readonly UUID[]; }

export interface DRExerciseCreateRequest {
  readonly name: string;
  readonly runbook_id: UUID;
  readonly recovery_point_id?: UUID;
  readonly exercise_type: ExerciseType;
  readonly environment: ExerciseEnvironment;
  readonly scheduled_for: ISODateTime;
  readonly idempotency_key: string;
}
export type DRExerciseUpdateRequest = Pick<DRExerciseCreateRequest, 'name' | 'scheduled_for' | 'recovery_point_id'>;
export interface DRExerciseStartRequest { readonly idempotency_key: string; }
export interface DRExerciseCancelRequest { readonly transition_key: string; }

export interface ObjectiveMeasurement {
  readonly restore_run_id: UUID;
  readonly runbook_id: UUID | null;
  readonly rpo_seconds: number | null;
  readonly rto_seconds: number | null;
  readonly rpo_target_seconds: number | null;
  readonly rto_target_seconds: number | null;
  readonly rpo_met: boolean | null;
  readonly rto_met: boolean | null;
  readonly measured_at: ISODateTime;
  readonly outcome: 'succeeded' | 'failed';
}

export interface ObjectiveReportBucket {
  readonly period_start: ISODateTime;
  readonly period_end: ISODateTime;
  readonly runbook_id: UUID;
  readonly runbook_name: string;
  readonly runbook_version: number;
  readonly restore_count: number;
  readonly failed_restore_count: number;
  readonly rpo_compliance_percent: number;
  readonly rto_compliance_percent: number;
  readonly measurements: readonly ObjectiveMeasurement[];
}

export interface ObjectiveReport {
  readonly from: ISODateTime;
  readonly to: ISODateTime;
  readonly bucket: ObjectiveBucket;
  readonly total_restores: number;
  readonly failed_restores: number;
  readonly rpo_compliance_percent: number;
  readonly rto_compliance_percent: number;
  readonly buckets: readonly ObjectiveReportBucket[];
}

export interface ReadinessSummary {
  readonly calculated_at: ISODateTime;
  readonly rpo_compliance_percent: number;
  readonly rto_compliance_percent: number;
  readonly last_verified_recovery_point: RecoveryPoint | null;
  readonly latest_passed_exercise: DRExercise | null;
  readonly latest_successful_restore: RestoreRun | null;
  readonly latest_failed_restore: RestoreRun | null;
  readonly next_scheduled_exercise: DRExercise | null;
  readonly stale_runbook_count: number;
  readonly unpublished_runbook_count: number;
  readonly current_rpo_breaches: number;
  readonly current_rto_breaches: number;
  readonly queue_state: HealthState;
  readonly provider_state: HealthState;
  readonly provider_message: string;
}

export interface BDRQuotaCosts {
  readonly default: number;
  readonly backup_execution: number;
  readonly verification: number;
  readonly restore_validation: number;
  readonly restore_execution: number;
  readonly exercise_execution: number;
}

export interface BDRResilienceConfiguration {
  readonly timeout_seconds: number;
  readonly max_attempts: number;
  readonly initial_backoff_seconds: number;
  readonly max_backoff_seconds: number;
  readonly jitter_seconds: number;
  readonly circuit_failure_threshold: number;
  readonly circuit_reset_seconds: number;
  readonly checksum_chunk_bytes: number;
}

export interface BDRHealthConfiguration {
  readonly probe_timeout_seconds: number;
  readonly probe_timeout_max_seconds: number;
  readonly provider_stale_seconds: number;
  readonly outbox_max_lag_seconds: number;
  readonly exercise_freshness_seconds: number;
  readonly registry_staleness_seconds: number;
  readonly exercise_registry_staleness_seconds: number;
  readonly queue_degradation_seconds: number;
}

export interface BDRProviderConfiguration {
  readonly storage_adapter_key: string;
  readonly local_filesystem_restore_modes: readonly RestoreMode[];
}

export interface BDRRunbookConfiguration {
  readonly default_rpo_seconds: number;
  readonly default_rto_seconds: number;
  readonly objective_min_seconds: number;
  readonly objective_max_seconds: number;
  readonly min_publish_steps: number;
  readonly unpublished_scan_limit: number;
}

export interface BDRStepConfiguration {
  readonly default_timeout_seconds: number;
  readonly min_timeout_seconds: number;
  readonly max_timeout_seconds: number;
  readonly default_retry_limit: number;
  readonly max_retry_limit: number;
  readonly default_on_failure: OnFailurePolicy;
  readonly allowed_failure_behaviors: readonly OnFailurePolicy[];
  readonly max_components: number;
  readonly max_verification_checks: number;
  readonly allowed_verification_checks: readonly string[];
  readonly max_reorder_items: number;
  readonly reorder_collision_offset: number;
  readonly require_draft_for_edits: boolean;
  readonly require_manual_approval_permission: boolean;
}

export interface BDRRestoreConfiguration {
  readonly production_enabled: boolean;
  readonly production_requires_approver: boolean;
  readonly selective_requires_components: boolean;
  readonly full_prohibits_components: boolean;
}

export interface BDRExerciseConfiguration {
  readonly production_enabled: boolean;
  readonly default_schedule_offset_ms: number;
  readonly evidence_freshness_days: number;
}

export interface BDRReportConfiguration {
  readonly allowed_buckets: readonly ObjectiveBucket[];
  readonly default_bucket: ObjectiveBucket;
  readonly default_interval_days: number;
  readonly max_interval_days: number;
  readonly max_results: number;
  readonly compliant_percent: number;
  readonly noncompliant_percent: number;
}

export interface BDRPresentationConfiguration {
  readonly duration_minute_seconds: number;
  readonly duration_hour_seconds: number;
  readonly byte_base: number;
  readonly status_positive: readonly string[];
  readonly status_negative: readonly string[];
  readonly status_warning: readonly string[];
  readonly status_positive_token: string;
  readonly status_negative_token: string;
  readonly status_warning_token: string;
}

export interface BDRPollingConfiguration {
  readonly dashboard_ms: number;
  readonly recovery_point_ms: number;
  readonly restore_ms: number;
  readonly exercise_ms: number;
  readonly exercise_page_size: number;
  readonly active_restore_statuses: readonly RestoreRunStatus[];
  readonly active_exercise_statuses: readonly ExerciseStatus[];
}

export interface BDRWorkflowConfiguration {
  readonly states: readonly string[];
  readonly terminal_states: readonly string[];
  readonly transitions: readonly {
    readonly command: string;
    readonly from_state: string;
    readonly to_state: string;
  }[];
  readonly retention_guard_commands: readonly string[];
}

export interface BDRConfigurationDocument {
  readonly quota_costs: BDRQuotaCosts;
  readonly resilience: BDRResilienceConfiguration;
  readonly health: BDRHealthConfiguration;
  readonly providers: BDRProviderConfiguration;
  readonly runbooks: BDRRunbookConfiguration;
  readonly steps: BDRStepConfiguration;
  readonly restores: BDRRestoreConfiguration;
  readonly exercises: BDRExerciseConfiguration;
  readonly reports: BDRReportConfiguration;
  readonly presentation: BDRPresentationConfiguration;
  readonly polling: BDRPollingConfiguration;
  readonly workflows: Readonly<Record<string, BDRWorkflowConfiguration>>;
}

export interface BDRConfigurationRollout {
  readonly enabled: boolean;
  readonly roles: readonly string[];
  readonly cohorts: readonly string[];
}

export interface BackupDisasterRecoveryConfiguration {
  readonly id: UUID | null;
  readonly tenant_id: UUID;
  readonly environment: string;
  readonly version: number;
  readonly document: BDRConfigurationDocument;
  readonly rollout: BDRConfigurationRollout;
  readonly updated_at: ISODateTime | null;
}

export interface BDRConfigurationMutation {
  readonly document: BDRConfigurationDocument;
  readonly environment?: string;
  readonly rollout?: BDRConfigurationRollout;
}

export interface BDRConfigurationChange {
  readonly path: string;
  readonly before: JSONValue;
  readonly after: JSONValue;
}

export interface BDRConfigurationPreview {
  readonly valid: boolean;
  readonly changes: readonly BDRConfigurationChange[];
  readonly document: BDRConfigurationDocument;
}

export interface BDRConfigurationVersion {
  readonly id: UUID;
  readonly version: number;
  readonly actor_id: UUID;
  readonly correlation_id: UUID;
  readonly prior_value: BDRConfigurationSnapshot | null;
  readonly new_value: BDRConfigurationSnapshot;
  readonly rollback_of: UUID | null;
  readonly created_at: ISODateTime;
}

export interface BDRConfigurationRollbackRequest { readonly version: number; }

export interface BDRConfigurationSnapshot {
  readonly environment: string;
  readonly document: BDRConfigurationDocument;
  readonly rollout: BDRConfigurationRollout;
}

export interface BDRConfigurationExport extends BDRConfigurationSnapshot {
  readonly schema: 'saraise.backup-disaster-recovery.configuration/v1';
  readonly version: number;
}

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

export interface ApiV2Page<T> extends ApiV2Envelope<readonly T[]> {
  readonly meta: ApiV2Meta & { readonly pagination: PaginationMeta };
}

export interface GovernedFieldError {
  readonly field: string;
  readonly code: string;
  readonly message: string;
}

export interface GovernedValidationDetail {
  readonly name?: readonly string[];
  readonly slug?: readonly string[];
  readonly scope_type?: readonly string[];
  readonly scope_ref?: readonly string[];
  readonly backup_type?: readonly string[];
  readonly recovery_point_id?: readonly string[];
  readonly target_environment?: readonly string[];
  readonly target_ref?: readonly string[];
  readonly restore_mode?: readonly string[];
  readonly selected_components?: readonly string[];
  readonly runbook_id?: readonly string[];
  readonly scheduled_for?: readonly string[];
  readonly exercise_type?: readonly string[];
  readonly environment?: readonly string[];
  readonly rpo_target_seconds?: readonly string[];
  readonly rto_target_seconds?: readonly string[];
  readonly parameters?: readonly string[];
  readonly document?: readonly string[];
  readonly rollout?: readonly string[];
  readonly non_field_errors?: readonly string[];
  readonly capability?: string;
  readonly retry_after_seconds?: number;
}

export interface GovernedErrorDetail {
  readonly code: string;
  readonly message: string;
  readonly detail: GovernedValidationDetail | null;
  readonly correlation_id: string;
}

export interface GovernedErrorDTO {
  readonly error: GovernedErrorDetail;
}

export interface PaginatedResult<T> {
  readonly items: readonly T[];
  readonly pagination: PaginationMeta;
  readonly correlationId: string;
}

export interface RecoveryPointFilters {
  readonly status?: RecoveryPointStatus;
  readonly scope_type?: ScopeType;
  readonly scope_ref?: string;
  readonly captured_after?: ISODateTime;
  readonly captured_before?: ISODateTime;
  readonly search?: string;
  readonly ordering?: 'captured_at' | '-captured_at' | 'expires_at' | '-expires_at' | 'size_bytes' | '-size_bytes';
  readonly page?: number;
  readonly page_size?: number;
}

export interface RestoreRunFilters {
  readonly status?: RestoreRunStatus;
  readonly target_environment?: RestoreTargetEnvironment;
  readonly recovery_point?: UUID;
  readonly requested_after?: ISODateTime;
  readonly requested_before?: ISODateTime;
  readonly page?: number;
  readonly page_size?: number;
}

export interface RunbookFilters {
  readonly status?: RunbookStatus;
  readonly scope_type?: ScopeType;
  readonly owner_id?: UUID;
  readonly search?: string;
  readonly ordering?: 'updated_at' | '-updated_at' | 'name' | '-name' | 'version' | '-version';
  readonly page?: number;
  readonly page_size?: number;
}

export interface ExerciseFilters {
  readonly status?: ExerciseStatus;
  readonly exercise_type?: ExerciseType;
  readonly runbook?: UUID;
  readonly scheduled_after?: ISODateTime;
  readonly scheduled_before?: ISODateTime;
  readonly page?: number;
  readonly page_size?: number;
}

export interface StepExecutionFilters {
  readonly exercise: UUID;
  readonly runbook_step?: UUID;
  readonly status?: StepExecutionStatus;
  readonly page?: number;
  readonly page_size?: number;
}

export interface ObjectiveReportFilters {
  readonly runbook_id?: UUID;
  readonly from: ISODateTime;
  readonly to: ISODateTime;
  readonly bucket: ObjectiveBucket;
}

export const MODULE_API_PREFIX = '/api/v2/backup-disaster-recovery';

export const ENDPOINTS = {
  BACKUP_EXECUTIONS: {
    CREATE: `${MODULE_API_PREFIX}/backup-executions/`,
    DETAIL: (backupJobId: UUID) => `${MODULE_API_PREFIX}/backup-executions/${backupJobId}/` as const,
  },
  RECOVERY_POINTS: {
    LIST: `${MODULE_API_PREFIX}/recovery-points/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/recovery-points/${id}/` as const,
    VERIFY: (id: UUID) => `${MODULE_API_PREFIX}/recovery-points/${id}/verify/` as const,
    EXPIRE: (id: UUID) => `${MODULE_API_PREFIX}/recovery-points/${id}/expire/` as const,
  },
  RESTORE_RUNS: {
    LIST: `${MODULE_API_PREFIX}/restore-runs/`,
    CREATE: `${MODULE_API_PREFIX}/restore-runs/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/restore-runs/${id}/` as const,
    EXECUTE: (id: UUID) => `${MODULE_API_PREFIX}/restore-runs/${id}/execute/` as const,
    CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/restore-runs/${id}/cancel/` as const,
  },
  RUNBOOKS: {
    LIST: `${MODULE_API_PREFIX}/runbooks/`,
    CREATE: `${MODULE_API_PREFIX}/runbooks/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/runbooks/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/runbooks/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/runbooks/${id}/` as const,
    CLONE: (id: UUID) => `${MODULE_API_PREFIX}/runbooks/${id}/clone/` as const,
    PUBLISH: (id: UUID) => `${MODULE_API_PREFIX}/runbooks/${id}/publish/` as const,
    RETIRE: (id: UUID) => `${MODULE_API_PREFIX}/runbooks/${id}/retire/` as const,
    REORDER_STEPS: (id: UUID) => `${MODULE_API_PREFIX}/runbooks/${id}/reorder-steps/` as const,
  },
  RUNBOOK_STEPS: {
    LIST: `${MODULE_API_PREFIX}/runbook-steps/`,
    CREATE: `${MODULE_API_PREFIX}/runbook-steps/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/runbook-steps/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/runbook-steps/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/runbook-steps/${id}/` as const,
  },
  EXERCISES: {
    LIST: `${MODULE_API_PREFIX}/exercises/`,
    CREATE: `${MODULE_API_PREFIX}/exercises/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/exercises/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/exercises/${id}/` as const,
    START: (id: UUID) => `${MODULE_API_PREFIX}/exercises/${id}/start/` as const,
    CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/exercises/${id}/cancel/` as const,
  },
  STEP_EXECUTIONS: {
    LIST: `${MODULE_API_PREFIX}/step-executions/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/step-executions/${id}/` as const,
  },
  REPORTS: { OBJECTIVES: `${MODULE_API_PREFIX}/reports/objectives/` },
  READINESS: `${MODULE_API_PREFIX}/readiness/`,
  CONFIGURATIONS: {
    CURRENT: `${MODULE_API_PREFIX}/configurations/current/`,
    PREVIEW: `${MODULE_API_PREFIX}/configurations/preview/`,
    VERSIONS: `${MODULE_API_PREFIX}/configurations/versions/`,
    ROLLBACK: `${MODULE_API_PREFIX}/configurations/rollback/`,
    IMPORT: `${MODULE_API_PREFIX}/configurations/import-document/`,
    EXPORT: `${MODULE_API_PREFIX}/configurations/export-document/`,
  },
} as const;
