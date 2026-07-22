/** Typed public contract for the technical DAG orchestration module. */

export type JSONPrimitive = string | number | boolean | null;
export interface JSONObject {
  readonly [key: string]: JSONValue;
}
export type JSONValue = JSONPrimitive | JSONObject | readonly JSONValue[];

export type DefinitionStatus = "draft" | "published" | "retired";
export type NodeType = "internal" | "workflow" | "extension";
export type EdgeCondition = "on_success" | "on_failure" | "always";
export type ScheduleStatus = "active" | "paused" | "retired";
export type MisfirePolicy = "skip" | "run_once";
export type ConcurrencyPolicy = "allow" | "forbid";
export type RunTriggerType = "manual" | "schedule" | "workflow" | "event";
export type RunStatus =
  | "queued"
  | "running"
  | "paused"
  | "cancelling"
  | "succeeded"
  | "failed"
  | "cancelled";
export type TaskRunStatus =
  | "blocked"
  | "ready"
  | "queued"
  | "running"
  | "retry_wait"
  | "succeeded"
  | "failed"
  | "skipped"
  | "cancelled";
export type RetryAttemptStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "timed_out"
  | "cancelled";
export type ValidationSeverity = "error" | "warning";
export type CapabilityAvailability =
  | "available"
  | "locked"
  | "setup_required"
  | "unavailable";

export interface TransitionEvidence {
  readonly transition: string;
  readonly from: string;
  readonly to: string;
  readonly actor_id: string | null;
  readonly occurred_at: string;
  readonly correlation_id?: string;
}

export interface PaginationMeta {
  readonly count: number;
  readonly page: number;
  readonly page_size: number;
  readonly total_pages: number;
  readonly has_next: boolean;
  readonly has_previous: boolean;
}

export interface ResponseMeta {
  readonly correlation_id: string;
  readonly timestamp: string;
  readonly pagination?: PaginationMeta;
}

export interface APIEnvelope<T> {
  readonly data: T;
  readonly meta: ResponseMeta;
}

export interface APIFieldError {
  readonly code: string;
  readonly message: string;
  readonly field?: string;
  readonly pointer?: string;
}

export interface APIErrorEnvelope {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly details: readonly APIFieldError[];
  };
  readonly meta: ResponseMeta;
}

export interface PageRequest {
  readonly [key: string]: string | number | boolean | undefined;
  readonly page?: number;
  readonly page_size?: number;
}

export interface PageResult<T> {
  readonly items: readonly T[];
  readonly pagination: PaginationMeta;
  readonly correlationId: string;
  readonly receivedAt: string;
}

export interface DefinitionListDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly key: string;
  readonly version: number;
  readonly name: string;
  readonly description: string;
  readonly status: DefinitionStatus;
  readonly is_current: boolean;
  readonly graph_revision: number;
  readonly node_count: number;
  readonly schedule_count: number;
  readonly last_run_at: string | null;
  readonly success_rate: number | null;
  readonly updated_at: string;
  readonly created_at: string;
}

export interface OrchestrationNodeDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly definition_id: string;
  readonly key: string;
  readonly name: string;
  readonly description: string;
  readonly node_type: NodeType;
  readonly handler_key: string;
  readonly config: JSONObject;
  readonly input_mapping: JSONObject;
  readonly timeout_seconds: number | null;
  readonly max_attempts: number | null;
  readonly retry_initial_delay_seconds: number;
  readonly retry_backoff_multiplier: string;
  readonly retry_max_delay_seconds: number;
  readonly priority: number;
  readonly is_deleted: boolean;
  readonly created_by: string;
  readonly updated_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface OrchestrationNodeListDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly definition_id: string;
  readonly key: string;
  readonly name: string;
  readonly node_type: NodeType;
  readonly handler_key: string;
  readonly priority: number;
  readonly timeout_seconds: number | null;
  readonly max_attempts: number | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface OrchestrationEdgeDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly definition_id: string;
  readonly upstream_node_id: string;
  readonly downstream_node_id: string;
  readonly condition: EdgeCondition;
  readonly priority: number;
  readonly is_deleted: boolean;
  readonly created_by: string;
  readonly updated_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface GraphValidationIssue {
  readonly code: string;
  readonly severity: ValidationSeverity;
  readonly message: string;
  readonly entity_type: "definition" | "node" | "edge";
  readonly entity_id: string | null;
  readonly pointer: string | null;
  readonly remediation: string | null;
}

export interface GraphValidationResult {
  readonly valid: boolean;
  readonly validated_revision: number;
  readonly issues: readonly GraphValidationIssue[];
}

export interface DefinitionDetailDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly key: string;
  readonly version: number;
  readonly name: string;
  readonly description: string;
  readonly status: DefinitionStatus;
  readonly is_current: boolean;
  readonly max_parallel_tasks: number;
  readonly default_timeout_seconds: number;
  readonly default_max_attempts: number;
  readonly input_schema: JSONObject;
  readonly output_schema: JSONObject;
  readonly output_mapping: JSONObject;
  readonly labels: Readonly<Record<string, string>>;
  readonly graph_revision: number;
  readonly contract_snapshot: JSONObject;
  readonly transition_history: readonly TransitionEvidence[];
  readonly is_deleted: boolean;
  readonly created_by: string;
  readonly updated_by: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly deleted_at: string | null;
  readonly nodes: readonly OrchestrationNodeDTO[];
  readonly edges: readonly OrchestrationEdgeDTO[];
}

export interface DefinitionCreateRequest {
  readonly key: string;
  readonly name: string;
  readonly description?: string;
  readonly max_parallel_tasks?: number;
  readonly default_timeout_seconds?: number;
  readonly default_max_attempts?: number;
  readonly input_schema?: JSONObject;
  readonly output_schema?: JSONObject;
  readonly output_mapping?: JSONObject;
  readonly labels?: Readonly<Record<string, string>>;
}

export interface DefinitionUpdateRequest {
  readonly name?: string;
  readonly description?: string;
  readonly max_parallel_tasks?: number;
  readonly default_timeout_seconds?: number;
  readonly default_max_attempts?: number;
  readonly input_schema?: JSONObject;
  readonly output_schema?: JSONObject;
  readonly output_mapping?: JSONObject;
  readonly labels?: Readonly<Record<string, string>>;
  readonly transition_key?: string;
  readonly expected_revision?: number;
}

export interface DefinitionFilters extends PageRequest {
  readonly status?: DefinitionStatus;
  readonly key?: string;
  readonly is_current?: boolean;
  readonly search?: string;
  readonly version?: number;
  readonly ordering?: "updated_at" | "-updated_at" | "name" | "-name" | "version" | "-version";
}

export interface NodeCreateRequest {
  readonly key: string;
  readonly name: string;
  readonly description?: string;
  readonly node_type: NodeType;
  readonly handler_key: string;
  readonly config?: JSONObject;
  readonly input_mapping?: JSONObject;
  readonly timeout_seconds?: number | null;
  readonly max_attempts?: number | null;
  readonly retry_initial_delay_seconds?: number;
  readonly retry_backoff_multiplier?: string;
  readonly retry_max_delay_seconds?: number;
  readonly priority?: number;
}

export type NodeUpdateRequest = Partial<NodeCreateRequest>;

export interface EdgeCreateRequest {
  readonly upstream_node_id: string;
  readonly downstream_node_id: string;
  readonly condition: EdgeCondition;
  readonly priority?: number;
}

export interface EdgeUpdateRequest {
  readonly condition?: EdgeCondition;
  readonly priority?: number;
}

export interface OrchestrationScheduleListDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly definition_id: string;
  readonly definition_name: string;
  readonly definition_key: string;
  readonly definition_version: number;
  readonly name: string;
  readonly cron_expression: string;
  readonly timezone: string;
  readonly status: ScheduleStatus;
  readonly misfire_policy: MisfirePolicy;
  readonly concurrency_policy: ConcurrencyPolicy;
  readonly next_run_at: string;
  readonly last_enqueued_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface OrchestrationScheduleDetailDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly definition_id: string;
  readonly name: string;
  readonly cron_expression: string;
  readonly timezone: string;
  readonly status: ScheduleStatus;
  readonly misfire_policy: MisfirePolicy;
  readonly concurrency_policy: ConcurrencyPolicy;
  readonly input: JSONObject;
  readonly next_run_at: string;
  readonly last_enqueued_at: string | null;
  readonly transition_history: readonly TransitionEvidence[];
  readonly is_deleted: boolean;
  readonly deleted_at: string | null;
  readonly created_by: string;
  readonly updated_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ScheduleCreateRequest {
  readonly definition_id: string;
  readonly name: string;
  readonly cron_expression: string;
  readonly timezone: string;
  readonly misfire_policy: MisfirePolicy;
  readonly concurrency_policy: ConcurrencyPolicy;
  readonly input?: JSONObject;
}

export interface ScheduleUpdateRequest {
  readonly name?: string;
  readonly cron_expression?: string;
  readonly timezone?: string;
  readonly misfire_policy?: MisfirePolicy;
  readonly concurrency_policy?: ConcurrencyPolicy;
  readonly input?: JSONObject;
}

export interface ScheduleFilters extends PageRequest {
  readonly status?: ScheduleStatus;
  readonly definition_id?: string;
  readonly due_before?: string;
  readonly search?: string;
  readonly ordering?: "next_run_at" | "-next_run_at" | "name" | "-name";
}

export interface RetryAttemptDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly task_run_id: string;
  readonly attempt_number: number;
  readonly status: RetryAttemptStatus;
  readonly available_at: string;
  readonly correlation_id: string;
  readonly output: JSONValue | null;
  readonly error_code: string;
  readonly error_message: string;
  readonly duration_ms: number | null;
  readonly transition_history: readonly TransitionEvidence[];
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface TaskRunListDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly run_id: string;
  readonly node_id: string;
  readonly node_key: string;
  readonly node_name: string;
  readonly status: TaskRunStatus;
  readonly remaining_dependencies: number;
  readonly current_attempt: number;
  readonly max_attempts: number;
  readonly error_code: string;
  readonly error_message: string;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface TaskRunDetailDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly run_id: string;
  readonly node_id: string;
  readonly node: OrchestrationNodeDTO;
  readonly status: TaskRunStatus;
  readonly input: JSONValue;
  readonly output: JSONValue | null;
  readonly remaining_dependencies: number;
  readonly current_attempt: number;
  readonly max_attempts: number;
  readonly error_code: string;
  readonly error_message: string;
  readonly transition_history: readonly TransitionEvidence[];
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly attempts: readonly RetryAttemptDTO[];
}

export interface RunListDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly definition_id: string;
  readonly definition_name: string;
  readonly definition_key: string;
  readonly definition_version: number;
  readonly schedule_id: string | null;
  readonly parent_run_id: string | null;
  readonly trigger_type: RunTriggerType;
  readonly status: RunStatus;
  readonly idempotency_key: string;
  readonly correlation_id: string;
  readonly requested_by: string;
  readonly task_count: number;
  readonly completed_task_count: number;
  readonly failed_task_count: number;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface RunGraphSnapshot {
  readonly nodes: readonly OrchestrationNodeDTO[];
  readonly edges: readonly OrchestrationEdgeDTO[];
}

export interface RunDetailDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly definition_id: string;
  readonly definition_name: string;
  readonly definition_key: string;
  readonly definition_version: number;
  readonly schedule_id: string | null;
  readonly parent_run_id: string | null;
  readonly trigger_type: RunTriggerType;
  readonly status: RunStatus;
  readonly input: JSONValue;
  readonly output: JSONValue | null;
  readonly requested_by: string;
  readonly idempotency_key: string;
  readonly correlation_id: string;
  readonly task_count: number;
  readonly completed_task_count: number;
  readonly failed_task_count: number;
  readonly error_code: string;
  readonly error_message: string;
  readonly transition_history: readonly TransitionEvidence[];
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export type ConfigurationEnvironment = "development" | "self-hosted" | "saas";

export interface OrchestrationConfigurationDocument {
  readonly limits: {
    readonly json_bytes: number;
    readonly json_depth: number;
    readonly parallel_tasks_min: number;
    readonly parallel_tasks_max: number;
    readonly timeout_seconds_min: number;
    readonly timeout_seconds_max: number;
    readonly attempts_min: number;
    readonly attempts_max: number;
    readonly retry_multiplier_min: number;
    readonly retry_multiplier_max: number;
    readonly page_size_default: number;
    readonly page_size_max: number;
    readonly idempotency_key_length: number;
    readonly event_metadata_bytes: number;
    readonly schedule_scan_batch: number;
    readonly definition_name_min: number;
    readonly definition_name_max: number;
    readonly description_max: number;
    readonly schedule_name_min: number;
    readonly schedule_name_max: number;
  };
  readonly defaults: {
    readonly max_parallel_tasks: number;
    readonly timeout_seconds: number;
    readonly max_attempts: number;
    readonly retry_initial_delay_seconds: number;
    readonly retry_backoff_multiplier: number;
    readonly retry_max_delay_seconds: number;
    readonly retry_jitter_ratio: number;
    readonly edge_condition: EdgeCondition;
    readonly edge_priority: number;
    readonly timezone: string;
    readonly schedule_status: ScheduleStatus;
    readonly misfire_policy: MisfirePolicy;
    readonly concurrency_policy: ConcurrencyPolicy;
    readonly cron_expression: string;
    readonly input_schema: JSONObject;
    readonly output_schema: JSONObject;
  };
  readonly workflow: JSONObject;
  readonly integrations: JSONObject;
  readonly scheduler: {
    readonly cron_fields: number;
    readonly search_horizon_days: number;
    readonly active_status: ScheduleStatus;
    readonly enqueue_misfire_policies: readonly MisfirePolicy[];
    readonly forbid_overlap_policy: ConcurrencyPolicy;
  };
  readonly health: {
    readonly scanner_heartbeat_ttl_seconds: number;
    readonly pending_outbox_freshness_seconds: number;
    readonly scanner_freshness_seconds: number;
    readonly registry_staleness_seconds: number;
  };
  readonly ui: {
    readonly definition_detail_page_size: number;
    readonly definition_page_size: number;
    readonly schedule_page_size: number;
    readonly task_run_page_size: number;
    readonly published_definition_page_size: number;
    readonly run_poll_interval_ms: number;
    readonly run_detail_poll_interval_ms: number;
    readonly event_poll_interval_ms: number;
    readonly cron_preview_count: number;
    readonly skeleton_rows: number;
    readonly duration_seconds_threshold_ms: number;
    readonly zoom_default: number;
    readonly zoom_min: number;
    readonly zoom_max: number;
    readonly zoom_step: number;
  };
}

export interface OrchestrationConfigurationDTO {
  readonly id?: string;
  readonly environment: ConfigurationEnvironment;
  readonly cohort: string;
  readonly version: number;
  readonly document: OrchestrationConfigurationDocument;
  readonly enabled: boolean;
  readonly rollout_percentage: number;
  readonly allowed_roles: readonly string[];
  readonly updated_by?: string;
  readonly correlation_id?: string;
  readonly updated_at?: string;
}

export interface ConfigurationWriteRequest {
  readonly environment: ConfigurationEnvironment;
  readonly cohort: string;
  readonly document: OrchestrationConfigurationDocument;
  readonly enabled: boolean;
  readonly rollout_percentage: number;
  readonly allowed_roles: readonly string[];
}

export interface ConfigurationPreviewDTO {
  readonly valid: true;
  readonly changed_sections: readonly string[];
  readonly before: OrchestrationConfigurationDocument;
  readonly after: OrchestrationConfigurationDocument;
}

export interface ConfigurationVersionDTO {
  readonly id: string;
  readonly version: number;
  readonly document: OrchestrationConfigurationDocument;
  readonly enabled: boolean;
  readonly rollout_percentage: number;
  readonly allowed_roles: readonly string[];
  readonly actor_id: string;
  readonly correlation_id: string;
  readonly parent_version_id: string | null;
  readonly rollback_of_id: string | null;
  readonly created_at: string;
}

export interface ConfigurationAuditDTO {
  readonly id: string;
  readonly version: number;
  readonly action: string;
  readonly actor_id: string;
  readonly correlation_id: string;
  readonly before: OrchestrationConfigurationDTO | null;
  readonly after: OrchestrationConfigurationDTO;
  readonly changed_at: string;
}

export interface RunStartRequest {
  readonly definition_id: string;
  readonly input: JSONObject;
  readonly idempotency_key: string;
  readonly trigger_type: RunTriggerType;
  readonly schedule_id?: string;
}

export interface RunControlRequest {
  readonly transition_key: string;
}

export interface RunRetryRequest {
  readonly idempotency_key: string;
}

export interface TaskRetryRequest {
  readonly idempotency_key: string;
}

export interface RunFilters extends PageRequest {
  readonly status?: RunStatus;
  readonly definition_id?: string;
  readonly schedule_id?: string;
  readonly trigger_type?: RunTriggerType;
  readonly created_from?: string;
  readonly created_to?: string;
  readonly correlation_id?: string;
  readonly search?: string;
  readonly ordering?: "created_at" | "-created_at" | "completed_at" | "-completed_at";
}

export interface TaskRunFilters extends PageRequest {
  readonly status?: TaskRunStatus;
  readonly node_id?: string;
  readonly ordering?:
    | "created_at"
    | "-created_at"
    | "started_at"
    | "-started_at"
    | "completed_at"
    | "-completed_at";
}

export interface OrchestrationEventDTO {
  readonly id: string;
  readonly tenant_id: string;
  readonly aggregate_type: string;
  readonly aggregate_id: string;
  readonly event_type: string;
  readonly actor_id: string | null;
  readonly correlation_id: string;
  readonly payload: JSONObject;
  readonly occurred_at: string;
}

export interface RunTimelineEntry {
  readonly id: string;
  readonly occurred_at: string;
  readonly event_type: string;
  readonly aggregate_type: string;
  readonly aggregate_id: string;
  readonly actor_id: string | null;
  readonly correlation_id: string;
  readonly evidence: JSONObject;
}

export interface NodeDescriptorDTO {
  readonly key: string;
  readonly display_name: string;
  readonly category: string;
  readonly description: string;
  readonly configuration_schema: JSONObject;
  readonly input_schema: JSONObject;
  readonly output_schema: JSONObject;
  readonly icon_key: string;
  readonly capability: string;
  readonly source_module: string;
  readonly spi_version: string;
  readonly module_version: string;
  readonly executor_version: string;
  readonly availability: CapabilityAvailability;
  readonly availability_reason?: string;
  readonly retry_safety: string;
}

export interface HealthCheckDTO {
  readonly status: "ready" | "not_ready";
  readonly checks: Readonly<Record<string, string>>;
}

export const MODULE_API_PREFIX = "/api/v2/automation-orchestration";

export const ENDPOINTS = {
  CONFIGURATION: {
    DETAIL: `${MODULE_API_PREFIX}/configuration/`,
    UPDATE: `${MODULE_API_PREFIX}/configuration/`,
    PREVIEW: `${MODULE_API_PREFIX}/configuration/preview/`,
    VERSIONS: `${MODULE_API_PREFIX}/configuration/versions/`,
    AUDITS: `${MODULE_API_PREFIX}/configuration/audits/`,
    ROLLBACK: `${MODULE_API_PREFIX}/configuration/rollback/`,
    IMPORT: `${MODULE_API_PREFIX}/configuration/import/`,
    EXPORT: `${MODULE_API_PREFIX}/configuration/export/`,
  },
  DEFINITIONS: {
    LIST: `${MODULE_API_PREFIX}/definitions/`,
    CREATE: `${MODULE_API_PREFIX}/definitions/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/` as const,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/` as const,
    VALIDATE: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/validate/` as const,
    PUBLISH: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/publish/` as const,
    CLONE: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/clone/` as const,
    RETIRE: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/retire/` as const,
    SNAPSHOT: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/snapshot/` as const,
    NODES: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/nodes/` as const,
    EDGES: (id: string) => `${MODULE_API_PREFIX}/definitions/${id}/edges/` as const,
  },
  NODES: {
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/nodes/${id}/` as const,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/nodes/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/nodes/${id}/` as const,
  },
  EDGES: {
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/edges/${id}/` as const,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/edges/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/edges/${id}/` as const,
  },
  SCHEDULES: {
    LIST: `${MODULE_API_PREFIX}/schedules/`,
    CREATE: `${MODULE_API_PREFIX}/schedules/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/` as const,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/` as const,
    PAUSE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/pause/` as const,
    RESUME: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/resume/` as const,
    RETIRE: (id: string) => `${MODULE_API_PREFIX}/schedules/${id}/retire/` as const,
  },
  RUNS: {
    LIST: `${MODULE_API_PREFIX}/runs/`,
    START: `${MODULE_API_PREFIX}/runs/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/` as const,
    PAUSE: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/pause/` as const,
    RESUME: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/resume/` as const,
    CANCEL: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/cancel/` as const,
    RETRY: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/retry/` as const,
    TASK_RUNS: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/task-runs/` as const,
    EVENTS: (id: string) => `${MODULE_API_PREFIX}/runs/${id}/events/` as const,
  },
  TASK_RUNS: {
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/task-runs/${id}/` as const,
    RETRY: (id: string) => `${MODULE_API_PREFIX}/task-runs/${id}/retry/` as const,
    RECONCILE: (id: string) => `${MODULE_API_PREFIX}/task-runs/${id}/reconcile/` as const,
  },
  NODE_TYPES: `${MODULE_API_PREFIX}/node-types/`,
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTE_PATHS = {
  DEFINITIONS: "/automation-orchestration",
  DEFINITION_CREATE: "/automation-orchestration/definitions/new",
  DEFINITION_DETAIL: (id: string) => `/automation-orchestration/definitions/${id}` as const,
  DEFINITION_EDIT: (id: string) => `/automation-orchestration/definitions/${id}/edit` as const,
  CONFIGURATION: "/automation-orchestration/configuration",
  SCHEDULES: "/automation-orchestration/schedules",
  SCHEDULE_CREATE: "/automation-orchestration/schedules/new",
  SCHEDULE_EDIT: (id: string) => `/automation-orchestration/schedules/${id}/edit` as const,
  RUNS: "/automation-orchestration/runs",
  RUN_DETAIL: (id: string) => `/automation-orchestration/runs/${id}` as const,
} as const;
