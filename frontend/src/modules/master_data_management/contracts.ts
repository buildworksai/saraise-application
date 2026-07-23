/* eslint-disable @typescript-eslint/consistent-indexed-object-style -- recursive JSON and immutable wire maps require index signatures. */
/** Governed v2 wire contracts for Master Data Management. */
export type UUID = string;
export type ISODateTime = string;
export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | readonly JsonValue[];
export interface JsonObject { readonly [key: string]: JsonValue; }

export interface JsonSchema {
  readonly type?: "object" | "array" | "string" | "number" | "integer" | "boolean" | "null";
  readonly title?: string;
  readonly description?: string;
  readonly properties?: { readonly [key: string]: JsonSchema };
  readonly required?: readonly string[];
  readonly items?: JsonSchema;
  readonly enum?: readonly JsonPrimitive[];
  readonly const?: JsonPrimitive;
  readonly default?: JsonValue;
  readonly format?: string;
  readonly pattern?: string;
  readonly minimum?: number;
  readonly maximum?: number;
  readonly minLength?: number;
  readonly maxLength?: number;
  readonly minItems?: number;
  readonly maxItems?: number;
  readonly uniqueItems?: boolean;
  readonly additionalProperties?: boolean | JsonSchema;
  readonly [annotation: `x-${string}`]: JsonValue | undefined;
}

export interface ApiMeta { readonly correlation_id: string; readonly timestamp: ISODateTime; }
export interface PaginationMeta { readonly count: number; readonly page: number; readonly page_size: number; readonly total_pages: number; readonly has_next: boolean; readonly has_previous: boolean; }
export interface ApiSuccess<T> { readonly data: T; readonly meta: ApiMeta; }
export interface ApiListSuccess<T> { readonly data: readonly T[]; readonly meta: ApiMeta & { readonly pagination: PaginationMeta }; }
export interface ApiFieldError { readonly field: string; readonly code: string; readonly message: string; }
export interface ApiErrorDetail { readonly code: string; readonly message: string; readonly correlation_id?: string; readonly field_errors?: readonly ApiFieldError[]; }
export interface ApiErrorEnvelope { readonly error: ApiErrorDetail; readonly meta?: ApiMeta; }
export interface ListResult<T> { readonly items: readonly T[]; readonly pagination: PaginationMeta; readonly meta: ApiMeta; }
export interface CollectionResult<T> { readonly items: readonly T[]; readonly meta: ApiMeta; }
export interface ItemResult<T> { readonly data: T; readonly meta: ApiMeta; }

export type EntityStatus = "active" | "pending_review" | "merged" | "archived";
export type QualityIssueStatus = "open" | "in_review" | "resolved" | "waived";
export type MatchCandidateStatus = "pending" | "confirmed" | "rejected" | "merged";
export type MergeStatus = "applied" | "reversed";
export type QualityRuleType = "required" | "format" | "range" | "uniqueness" | "referential" | "timeliness";
export type QualityDimension = "completeness" | "accuracy" | "consistency" | "timeliness" | "uniqueness" | "conformity";
export type IssueSeverity = "info" | "warning" | "error" | "critical";
export type MatchingAlgorithm = "exact" | "normalized" | "fuzzy" | "phonetic";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled" | "timed_out" | "retrying";
export type TenantApplicationMode = "development" | "self-hosted" | "saas";

export interface AuditFields { readonly id: UUID; readonly tenant_id: UUID; readonly created_at: ISODateTime; readonly updated_at: ISODateTime; readonly created_by: UUID; readonly updated_by: UUID | null; }
export interface SoftDeleteFields { readonly is_deleted: boolean; readonly deleted_at: ISODateTime | null; }
export interface TransitionEntry { readonly event: string; readonly from: string; readonly to: string; readonly actor_id: UUID; readonly occurred_at: ISODateTime; readonly correlation_id?: string; }

export interface MasterEntityType extends AuditFields, SoftDeleteFields {
  readonly key: string; readonly display_name: string; readonly description: string; readonly json_schema: JsonSchema; readonly schema_version: number;
  readonly required_fields: readonly string[]; readonly sensitive_fields: readonly string[]; readonly searchable_fields: readonly string[];
  readonly owner_module: string; readonly is_system: boolean; readonly is_active: boolean; readonly metadata: JsonObject;
}
export interface MasterEntityTypeCreateRequest { readonly key: string; readonly display_name: string; readonly description?: string; readonly json_schema: JsonSchema; readonly required_fields?: readonly string[]; readonly sensitive_fields?: readonly string[]; readonly searchable_fields?: readonly string[]; readonly idempotency_key: string; }
export interface MasterEntityTypeUpdateRequest { readonly expected_schema_version: number; readonly changes: { readonly display_name?: string; readonly description?: string; readonly json_schema?: JsonSchema; readonly required_fields?: readonly string[]; readonly sensitive_fields?: readonly string[]; readonly searchable_fields?: readonly string[]; readonly is_active?: boolean; readonly metadata?: JsonObject; }; readonly idempotency_key: string; }
export interface DeactivateTypeRequest { readonly reason: string; readonly idempotency_key: string; }

export interface QualityDimensionScore { readonly dimension: QualityDimension; readonly score: number | null; readonly passed_rules: number; readonly failed_rules: number; readonly evaluated_rules: number; }
export interface QualitySummary { readonly evaluated: boolean; readonly score: number | null; readonly evaluated_at: ISODateTime | null; readonly dimensions: readonly QualityDimensionScore[]; readonly open_issue_count: number; }
export interface MasterDataEntityListItem extends AuditFields, SoftDeleteFields { readonly entity_type: UUID; readonly entity_type_key: string; readonly entity_type_display_name: string; readonly entity_code: string; readonly entity_name: string; readonly source_system: string; readonly source_record_id: string; readonly status: EntityStatus; readonly quality_score: string; readonly quality_evaluated_at: ISODateTime | null; readonly golden_record: UUID | null; readonly is_golden: boolean; readonly version: number; }
export interface MasterDataEntity extends MasterDataEntityListItem { readonly data: JsonObject; readonly quality_summary?: QualitySummary; readonly transition_history: readonly TransitionEntry[]; }
export interface MasterDataEntityCreateRequest { readonly entity_type_id: UUID; readonly entity_code: string; readonly entity_name: string; readonly data: JsonObject; readonly source_system?: string; readonly source_record_id?: string; readonly idempotency_key: string; }
export interface MasterDataEntityUpdateRequest { readonly expected_version: number; readonly changes: { readonly entity_code?: string; readonly entity_name?: string; readonly data?: JsonObject; readonly source_system?: string; readonly source_record_id?: string; }; readonly reason: string; readonly idempotency_key: string; }
export interface EntityVersionActionRequest { readonly expected_version: number; readonly reason: string; readonly idempotency_key: string; }
export interface RollbackEntityRequest extends EntityVersionActionRequest { readonly version_number: number; }

export interface MasterDataVersion { readonly id: UUID; readonly tenant_id: UUID; readonly entity: UUID; readonly version_number: number; readonly entity_type_key: string; readonly entity_code: string; readonly entity_name: string; readonly data_snapshot: JsonObject; readonly status_snapshot: EntityStatus; readonly quality_score_snapshot: string; readonly changed_fields: readonly string[]; readonly change_reason: string; readonly changed_by: UUID; readonly correlation_id: string; readonly created_at: ISODateTime; }

export interface DataQualityRule extends AuditFields, SoftDeleteFields { readonly entity_type: UUID; readonly entity_type_key?: string; readonly name: string; readonly field_path: string; readonly rule_type: QualityRuleType; readonly configuration: JsonObject; readonly dimension: QualityDimension; readonly severity: IssueSeverity; readonly weight: string; readonly is_active: boolean; }
export interface DataQualityRuleWriteRequest { readonly entity_type_id: UUID; readonly name: string; readonly field_path?: string; readonly rule_type: QualityRuleType; readonly configuration: JsonObject; readonly dimension: QualityDimension; readonly severity: IssueSeverity; readonly weight?: string; readonly is_active?: boolean; readonly idempotency_key: string; }
export interface DataQualityRuleUpdateRequest { readonly changes: Partial<Omit<DataQualityRuleWriteRequest, "entity_type_id" | "idempotency_key">>; readonly idempotency_key: string; }
export interface DeactivateRuleRequest { readonly idempotency_key: string; }

export interface DataQualityIssue extends AuditFields { readonly entity: UUID; readonly entity_code?: string; readonly entity_name?: string; readonly rule: UUID | null; readonly rule_name?: string | null; readonly field_path: string; readonly dimension: QualityDimension; readonly severity: IssueSeverity; readonly message: string; readonly evidence: JsonObject; readonly status: QualityIssueStatus; readonly assigned_to: UUID | null; readonly resolution: string; readonly resolved_by: UUID | null; readonly resolved_at: ISODateTime | null; readonly transition_history: readonly TransitionEntry[]; }
export interface AssignQualityIssueRequest { readonly assignee_id: UUID; readonly transition_key: string; }
export interface ResolveQualityIssueRequest { readonly resolution: string; readonly transition_key: string; }

export interface MatchingRule extends AuditFields, SoftDeleteFields { readonly entity_type: UUID; readonly entity_type_key?: string; readonly name: string; readonly algorithm: MatchingAlgorithm; readonly field_weights: { readonly [fieldPath: string]: number }; readonly blocking_fields: readonly string[]; readonly review_threshold: string; readonly auto_confirm_threshold: string; readonly is_active: boolean; }
export interface MatchingRuleWriteRequest { readonly entity_type_id: UUID; readonly name: string; readonly algorithm: MatchingAlgorithm; readonly field_weights: { readonly [fieldPath: string]: number }; readonly blocking_fields: readonly string[]; readonly review_threshold: number; readonly auto_confirm_threshold: number; readonly is_active?: boolean; readonly idempotency_key: string; }
export interface MatchingRuleUpdateRequest { readonly changes: Partial<Omit<MatchingRuleWriteRequest, "entity_type_id" | "idempotency_key">>; readonly idempotency_key: string; }
export interface RuleVersion { readonly id: UUID; readonly tenant_id: UUID; readonly rule: UUID; readonly version_number: number; readonly snapshot: JsonObject; readonly changed_by: UUID; readonly correlation_id: string; readonly change_reason: string; readonly created_at: ISODateTime; }
export interface RulePortableDocument { readonly schema: "saraise.master-data-management.quality-rule" | "saraise.master-data-management.matching-rule"; readonly document_version: 1; readonly rule_id: UUID; readonly version_number: number; readonly snapshot: JsonObject; }
export interface RuleRollbackRequest { readonly version_number: number; readonly reason: string; readonly idempotency_key: string; }
export interface RuleImportRequest { readonly document: RulePortableDocument; readonly reason: string; readonly idempotency_key: string; }
export interface MatchResult { readonly rule_id: UUID; readonly left_entity_id: UUID; readonly right_entity_id: UUID; readonly confidence: string; readonly field_scores: { readonly [fieldPath: string]: number }; readonly evidence: JsonObject; readonly outcome: string; }
export interface MatchPreviewRequest { readonly left_entity_id: UUID; readonly right_entity_id: UUID; readonly rule_id: UUID; }

export interface MatchCandidate extends AuditFields { readonly matching_rule: UUID; readonly matching_rule_name?: string; readonly left_entity: MasterDataEntity; readonly right_entity: MasterDataEntity; readonly confidence: string; readonly field_scores: { readonly [fieldPath: string]: number }; readonly evidence: JsonObject; readonly status: MatchCandidateStatus; readonly reviewed_by: UUID | null; readonly reviewed_at: ISODateTime | null; readonly review_note: string; readonly merge_history: UUID | null; readonly transition_history: readonly TransitionEntry[]; }
export interface MatchReviewRequest { readonly decision: "confirm" | "reject"; readonly note?: string; readonly transition_key: string; }

export interface SurvivorshipField { readonly field_path: string; readonly value: JsonValue; readonly source_entity_id: UUID; readonly source_entity_name?: string; readonly rationale: string; readonly alternatives: readonly { readonly entity_id: UUID; readonly value: JsonValue }[]; }
export interface MergePreview { readonly entity_ids: readonly UUID[]; readonly entity_type_key: string; readonly fields: readonly SurvivorshipField[]; readonly golden_record: JsonObject; readonly conflicts: readonly { readonly code: string; readonly field_path?: string; readonly message: string }[]; readonly preview_token?: string; }
export interface MergePreviewRequest { readonly entity_ids: readonly UUID[]; readonly survivorship_overrides: { readonly [fieldPath: string]: UUID }; }
export interface MergeRequest extends MergePreviewRequest { readonly reason: string; readonly idempotency_key: string; readonly preview_token?: string; }
export interface MergeParticipant { readonly id: UUID; readonly source_entity: UUID; readonly source_version: number; readonly source_snapshot: JsonObject; readonly role: "survivor" | "merged_source"; readonly created_at: ISODateTime; }
export interface MergeHistoryListItem { readonly id: UUID; readonly tenant_id: UUID; readonly golden_record: UUID; readonly golden_record_name?: string; readonly status: MergeStatus; readonly reason: string; readonly merged_by: UUID; readonly reversed_by: UUID | null; readonly reversed_at: ISODateTime | null; readonly participant_count: number; readonly correlation_id: string; readonly created_at: ISODateTime; }
export interface MergeHistory extends MergeHistoryListItem { readonly survivorship_policy: { readonly [fieldPath: string]: UUID }; readonly golden_snapshot_before: JsonObject; readonly golden_snapshot_after: JsonObject; readonly reversal_reason: string; readonly transition_history: readonly TransitionEntry[]; readonly participants: readonly MergeParticipant[]; }
export interface ReverseMergeRequest { readonly reason: string; readonly transition_key: string; }
export interface MergeReversalPreview { readonly merge_id: UUID; readonly can_reverse: boolean; readonly conflicts: readonly { readonly code: string; readonly entity_id: UUID | null; readonly expected_version: number | null; readonly current_version: number | null; readonly message: string }[]; readonly participant_versions: { readonly [entityId: string]: number }; }

export interface ValidationViolation { readonly field_path: string; readonly code: string; readonly message: string; readonly severity: IssueSeverity; }
export interface ValidationFinding { readonly field_path: string; readonly code: string; readonly message: string; readonly dimension: string; readonly severity: IssueSeverity; readonly rule_id: UUID | null; }
export interface ValidationReport { readonly valid: boolean; readonly evaluated: boolean; readonly findings: readonly ValidationFinding[]; }
export interface QualityReport { readonly entity_id: UUID; readonly evaluated: boolean; readonly score: string | null; readonly dimension_scores: { readonly [dimension: string]: number | null }; readonly issue_count: number; readonly findings: readonly ValidationFinding[]; }
export interface QualityScanRequest { readonly entity_type_id: UUID; readonly idempotency_key: string; }
export interface DeduplicationScanRequest { readonly entity_type_id: UUID; readonly rule_ids: readonly UUID[]; readonly idempotency_key: string; }
export interface AsyncJob { readonly id: UUID; readonly command: "master_data_management.quality_scan" | "master_data_management.deduplication_scan"; readonly status: JobStatus; readonly attempts: number; readonly created_at: ISODateTime; readonly updated_at: ISODateTime; readonly started_at: ISODateTime | null; readonly completed_at: ISODateTime | null; readonly error_message: string | null; readonly correlation_id: string; readonly result: JsonObject | null; }
export interface MDMSummary { readonly total_entities: number; readonly active_entities: number; readonly pending_review_entities: number; readonly merged_entities: number; readonly archived_entities: number; readonly quality_evaluated_entities: number; readonly average_quality_score: number | null; readonly score_distribution: readonly { readonly label: string; readonly minimum: number; readonly maximum: number; readonly count: number }[]; readonly quality_trend: readonly { readonly date: string; readonly score: number | null; readonly evaluated_count: number }[]; readonly open_issues: number; readonly critical_issues: number; readonly pending_matches: number; readonly recent_activity: readonly { readonly event: string; readonly aggregate_id: UUID; readonly label: string; readonly occurred_at: ISODateTime; readonly actor_id: UUID; readonly correlation_id: string }[]; }

export interface MasterDataConfigurationDocument {
  readonly environment: string;
  readonly schema_policy: {
    readonly entity_type_key_pattern: string;
    readonly entity_type_key_max_length: number;
    readonly field_path_pattern: string;
    readonly allowed_json_schema_keywords: readonly string[];
    readonly max_payload_bytes: number;
    readonly builtin_entity_types: readonly JsonObject[];
  };
  readonly lifecycle: { readonly allow_physical_delete: boolean; readonly merged_entities_editable: boolean };
  readonly workflows: { readonly entity: JsonObject; readonly quality_issue: JsonObject; readonly match_candidate: JsonObject; readonly merge: JsonObject };
  readonly limits: {
    readonly display_name_max: number; readonly description_max: number; readonly owner_module_max: number;
    readonly entity_code_max: number; readonly entity_name_max: number; readonly source_system_max: number;
    readonly source_record_id_max: number; readonly resolution_max: number; readonly reason_max: number;
    readonly deduplication_scan_max_entities: number; readonly merge_min_entities: number;
    readonly list_page_size: number; readonly selector_page_size: number;
  };
  readonly quality: {
    readonly missing_values: readonly JsonValue[]; readonly rule_schemas: JsonObject;
    readonly referential_target_field_default: string; readonly timeliness_max_age_days_default: number;
    readonly no_rules_evaluated: boolean; readonly no_rules_score: number | null; readonly no_rules_issue_count: number;
    readonly score_scale: number; readonly score_decimal_places: number; readonly auto_resolve_passing: boolean;
    readonly defaults: { readonly rule_type: QualityRuleType; readonly dimension: QualityDimension; readonly severity: IssueSeverity; readonly weight: string };
  };
  readonly matching: {
    readonly algorithms: readonly MatchingAlgorithm[]; readonly soundex_mapping: JsonObject; readonly soundex_output_length: number;
    readonly weight_sum: string; readonly weight_tolerance: string; readonly threshold_min: string; readonly threshold_max: string;
    readonly missing_value_score: string; readonly outcomes: { readonly auto_confirm: string; readonly review: string; readonly no_match: string }; readonly strategy_version: number;
    readonly scan_statuses: readonly EntityStatus[]; readonly skip_incomplete_blocking_keys: boolean; readonly auto_confirm_enabled: boolean;
    readonly review_decisions: readonly ("confirm" | "reject")[];
    readonly defaults: { readonly algorithm: MatchingAlgorithm; readonly review_threshold: string; readonly auto_confirm_threshold: string };
  };
  readonly merge: { readonly allowed_statuses: readonly EntityStatus[]; readonly survivorship_order: readonly string[]; readonly reversal_expected_version_increment: number };
  readonly dashboard: {
    readonly score_buckets: readonly { readonly label: string; readonly minimum: number; readonly maximum: number }[];
    readonly trend_window_days: number; readonly recent_activity_limit: number; readonly minimum_bar_percent: number;
  };
  readonly operational: { readonly health_check_interval_seconds: number; readonly job_poll_interval_ms: number; readonly job_poll_statuses: readonly JobStatus[] };
  readonly ui: {
    readonly sidebar_order: number; readonly skeleton_cards: number; readonly quality_issue_default_status: QualityIssueStatus;
    readonly status_tokens: { readonly danger: "destructive" | "success" | "warning"; readonly success: "destructive" | "success" | "warning"; readonly warning: "destructive" | "success" | "warning" };
    readonly list_page_size: number;
  };
  readonly entity_defaults: { readonly source_system: string };
  readonly feature_rollout: {
    readonly enabled: boolean;
    readonly modes: readonly TenantApplicationMode[];
    readonly roles: readonly string[];
    readonly cohorts: readonly string[];
    readonly percentage: number;
  };
}
export interface MasterDataConfiguration {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly document: MasterDataConfigurationDocument;
  readonly version: number;
  readonly created_at: ISODateTime;
  readonly updated_at: ISODateTime;
  readonly created_by: UUID;
  readonly updated_by: UUID | null;
}
export interface MasterDataConfigurationVersion {
  readonly id: UUID;
  readonly tenant_id: UUID;
  readonly configuration: UUID;
  readonly version: number;
  readonly prior_value: MasterDataConfigurationDocument | null;
  readonly new_value: MasterDataConfigurationDocument;
  readonly actor_id: UUID;
  readonly correlation_id: string;
  readonly change_type: "initialize" | "create" | "update" | "rollback" | "import";
  readonly reason: string;
  readonly created_at: ISODateTime;
}
export interface ConfigurationWriteRequest { readonly document: MasterDataConfigurationDocument; readonly reason: string; readonly idempotency_key: string; }
export interface ConfigurationPreviewRequest { readonly document: MasterDataConfigurationDocument; }
export interface ConfigurationPreview {
  readonly valid: boolean;
  readonly document: MasterDataConfigurationDocument;
  readonly changes: readonly JsonObject[];
}
export interface ConfigurationRollbackRequest { readonly version: number; readonly reason: string; readonly idempotency_key: string; }
export interface ConfigurationExport { readonly module: "master_data_management"; readonly schema_version: number; readonly configuration_version: number; readonly document: MasterDataConfigurationDocument; }

export interface PageQuery { readonly page?: number; readonly page_size?: number; readonly search?: string; readonly ordering?: string; }
export interface EntityTypeFilters extends PageQuery { readonly key?: string; readonly owner_module?: string; readonly is_active?: boolean; }
export interface EntityFilters extends PageQuery { readonly entity_type?: UUID; readonly status?: EntityStatus; readonly quality_min?: number; readonly quality_max?: number; readonly source_system?: string; readonly deleted?: boolean; }
export interface QualityRuleFilters extends PageQuery { readonly entity_type?: UUID; readonly rule_type?: QualityRuleType; readonly dimension?: QualityDimension; readonly severity?: IssueSeverity; readonly is_active?: boolean; }
export interface QualityIssueFilters extends PageQuery { readonly entity?: UUID; readonly entity_type?: UUID; readonly status?: QualityIssueStatus; readonly severity?: IssueSeverity; readonly dimension?: QualityDimension; readonly assigned_to?: UUID; }
export interface MatchingRuleFilters extends PageQuery { readonly entity_type?: UUID; readonly algorithm?: MatchingAlgorithm; readonly is_active?: boolean; }
export interface MatchCandidateFilters extends PageQuery { readonly entity_type?: UUID; readonly status?: MatchCandidateStatus; readonly confidence_min?: number; readonly rule?: UUID; }
export interface MergeFilters extends PageQuery { readonly status?: MergeStatus; readonly golden_record?: UUID; }

export const MODULE_API_PREFIX = "/api/v2/master-data-management" as const;
export const ENDPOINTS = {
  ENTITY_TYPES: { LIST: `${MODULE_API_PREFIX}/entity-types/`, CREATE: `${MODULE_API_PREFIX}/entity-types/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/entity-types/${id}/` as const, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/entity-types/${id}/` as const, DEACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/entity-types/${id}/deactivate/` as const },
  ENTITIES: { LIST: `${MODULE_API_PREFIX}/entities/`, CREATE: `${MODULE_API_PREFIX}/entities/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/entities/${id}/` as const, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/entities/${id}/` as const, ARCHIVE: (id: UUID) => `${MODULE_API_PREFIX}/entities/${id}/` as const, RESTORE: (id: UUID) => `${MODULE_API_PREFIX}/entities/${id}/restore/` as const, VERSIONS: (id: UUID) => `${MODULE_API_PREFIX}/entities/${id}/versions/` as const, VERSION: (id: UUID, version: number) => `${MODULE_API_PREFIX}/entities/${id}/versions/${version}/` as const, ROLLBACK: (id: UUID) => `${MODULE_API_PREFIX}/entities/${id}/rollback/` as const, VALIDATE: (id: UUID) => `${MODULE_API_PREFIX}/entities/${id}/validate/` as const },
  QUALITY_RULES: { LIST: `${MODULE_API_PREFIX}/quality-rules/`, CREATE: `${MODULE_API_PREFIX}/quality-rules/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/quality-rules/${id}/` as const, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/quality-rules/${id}/` as const, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/quality-rules/${id}/` as const, HISTORY: (id: UUID) => `${MODULE_API_PREFIX}/quality-rules/${id}/history/` as const, ROLLBACK: (id: UUID) => `${MODULE_API_PREFIX}/quality-rules/${id}/rollback/` as const, IMPORT: (id: UUID) => `${MODULE_API_PREFIX}/quality-rules/${id}/import/` as const, EXPORT: (id: UUID) => `${MODULE_API_PREFIX}/quality-rules/${id}/export/` as const },
  QUALITY_ISSUES: { LIST: `${MODULE_API_PREFIX}/quality-issues/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/quality-issues/${id}/` as const, ASSIGN: (id: UUID) => `${MODULE_API_PREFIX}/quality-issues/${id}/assign/` as const, RESOLVE: (id: UUID) => `${MODULE_API_PREFIX}/quality-issues/${id}/resolve/` as const, WAIVE: (id: UUID) => `${MODULE_API_PREFIX}/quality-issues/${id}/waive/` as const },
  QUALITY_SCANS: `${MODULE_API_PREFIX}/quality-scans/`,
  MATCHING_RULES: { LIST: `${MODULE_API_PREFIX}/matching-rules/`, CREATE: `${MODULE_API_PREFIX}/matching-rules/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/matching-rules/${id}/` as const, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/matching-rules/${id}/` as const, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/matching-rules/${id}/` as const, HISTORY: (id: UUID) => `${MODULE_API_PREFIX}/matching-rules/${id}/history/` as const, ROLLBACK: (id: UUID) => `${MODULE_API_PREFIX}/matching-rules/${id}/rollback/` as const, IMPORT: (id: UUID) => `${MODULE_API_PREFIX}/matching-rules/${id}/import/` as const, EXPORT: (id: UUID) => `${MODULE_API_PREFIX}/matching-rules/${id}/export/` as const },
  MATCHING: { PREVIEW: `${MODULE_API_PREFIX}/matching/preview/`, SCANS: `${MODULE_API_PREFIX}/matching/scans/` },
  MATCH_CANDIDATES: { LIST: `${MODULE_API_PREFIX}/match-candidates/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/match-candidates/${id}/` as const, REVIEW: (id: UUID) => `${MODULE_API_PREFIX}/match-candidates/${id}/review/` as const },
  MERGES: { LIST: `${MODULE_API_PREFIX}/merges/`, CREATE: `${MODULE_API_PREFIX}/merges/`, PREVIEW: `${MODULE_API_PREFIX}/merges/preview/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/merges/${id}/` as const, REVERSAL_PREVIEW: (id: UUID) => `${MODULE_API_PREFIX}/merges/${id}/reversal-preview/` as const, REVERSE: (id: UUID) => `${MODULE_API_PREFIX}/merges/${id}/reverse/` as const },
  CONFIGURATION: {
    LIST: `${MODULE_API_PREFIX}/configurations/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/configurations/${id}/` as const,
    PREVIEW: `${MODULE_API_PREFIX}/configurations/preview/`,
    HISTORY: `${MODULE_API_PREFIX}/configurations/history/`,
    ROLLBACK: `${MODULE_API_PREFIX}/configurations/rollback/`,
    IMPORT: `${MODULE_API_PREFIX}/configurations/import/`,
    EXPORT: `${MODULE_API_PREFIX}/configurations/export/`,
  },
  DASHBOARD: `${MODULE_API_PREFIX}/dashboard/`, JOB: (id: UUID) => `${MODULE_API_PREFIX}/jobs/${id}/` as const,
  HEALTH: { LIVE: `${MODULE_API_PREFIX}/health/live/`, READY: `${MODULE_API_PREFIX}/health/ready/` },
} as const;

export const ROUTES = {
  DASHBOARD: "/master-data", ENTITY_TYPES: "/master-data/entity-types", ENTITY_TYPE_NEW: "/master-data/entity-types/new", ENTITY_TYPE_DETAIL: (id: UUID) => `/master-data/entity-types/${id}` as const, ENTITY_TYPE_EDIT: (id: UUID) => `/master-data/entity-types/${id}/edit` as const,
  ENTITIES: "/master-data/entities", ENTITY_NEW: "/master-data/entities/new", ENTITY_DETAIL: (id: UUID) => `/master-data/entities/${id}` as const, ENTITY_EDIT: (id: UUID) => `/master-data/entities/${id}/edit` as const, ENTITY_VERSION: (id: UUID, version: number) => `/master-data/entities/${id}/versions/${version}` as const,
  QUALITY_RULES: "/master-data/quality/rules", QUALITY_RULE_NEW: "/master-data/quality/rules/new", QUALITY_RULE_DETAIL: (id: UUID) => `/master-data/quality/rules/${id}` as const, QUALITY_RULE_EDIT: (id: UUID) => `/master-data/quality/rules/${id}/edit` as const,
  QUALITY_ISSUES: "/master-data/quality/issues", QUALITY_ISSUE_DETAIL: (id: UUID) => `/master-data/quality/issues/${id}` as const,
  MATCHING_RULES: "/master-data/matching/rules", MATCHING_RULE_NEW: "/master-data/matching/rules/new", MATCHING_RULE_DETAIL: (id: UUID) => `/master-data/matching/rules/${id}` as const, MATCHING_RULE_EDIT: (id: UUID) => `/master-data/matching/rules/${id}/edit` as const,
  MATCHES: "/master-data/matches", MATCH_DETAIL: (id: UUID) => `/master-data/matches/${id}` as const,
  MERGES: "/master-data/merges", MERGE_DETAIL: (id: UUID) => `/master-data/merges/${id}` as const, JOB_DETAIL: (id: UUID) => `/master-data/jobs/${id}` as const,
  CONFIGURATION: "/master-data/configuration",
} as const;
