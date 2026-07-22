/** Stable frontend contract for the governed process-mining API v2. */

export type UUID = string;
export type ISODateTime = string;
export type AnalysisStatus = 'queued' | 'running' | 'completed' | 'failed' | 'timed_out' | 'cancelled';
export type ExportStatus = AnalysisStatus | 'expired';
export type MiningAlgorithm = 'alpha_miner' | 'heuristic_miner' | 'inductive_miner';
export type ExportFormat = 'xes' | 'csv' | 'json';
export type ModelSourceKind = 'discovered' | 'imported';
export type DeviationType = 'missing_activity' | 'unexpected_activity' | 'wrong_order' | 'skipped_path';
export type BottleneckSeverity = 'critical' | 'high' | 'medium' | 'low';

export interface ApiMeta { correlation_id: string; timestamp: ISODateTime }
export interface PaginationMeta { count: number; page: number; page_size: number; total_pages: number; has_next: boolean; has_previous: boolean }
export interface ApiEnvelope<T> { data: T; meta: ApiMeta }
export interface PaginatedEnvelope<T> { data: T[]; meta: ApiMeta & { pagination: PaginationMeta } }
export interface PaginatedResult<T> { items: T[]; pagination: PaginationMeta; correlationId: string }
export interface ApiErrorDetail { field_errors?: { field: string; code: string; message: string }[]; quota?: { resource: string; remaining: number; reset_at: string | null }; retry_after_seconds?: number }
export interface ApiErrorBody { code: string; message: string; correlation_id: string; detail: ApiErrorDetail }

export interface ProcessEvent { id: UUID; process_name: string; source_module: string; source_event_id: string | null; case_id: string; activity: string; occurred_at: ISODateTime; resource: string | null; attributes?: Record<string, unknown>; ingested_at: ISODateTime; created_at: ISODateTime }
export interface CanonicalEventInput { case_id: string; activity: string; occurred_at: ISODateTime; resource?: string; source_event_id?: string; attributes?: Record<string, unknown> }
export interface EventBatchIngestRequest { process_name: string; source_module: string; events: CanonicalEventInput[] }
export interface IngestRowEvidence { index: number; status: 'accepted' | 'rejected' | 'duplicate'; event_id: UUID | null; code: string; message: string }
export interface IngestResult { accepted: number; rejected: number; duplicates: number; rows: IngestRowEvidence[] }

export interface EventExport { id: UUID; process_name: string; format: ExportFormat; status: ExportStatus; event_filter?: EventFilter; row_count: number | null; byte_size: number | null; sha256: string; expires_at: ISODateTime | null; completed_at: ISODateTime | null; error_code: string; transition_history?: TransitionRecord[]; async_job_id?: UUID | null; created_at: ISODateTime; updated_at: ISODateTime }
export interface EventExportCreateRequest { process_name: string; format: ExportFormat; event_filter: EventFilter; idempotency_key: string }
export interface DiscoveryJob { id: UUID; process_name: string; algorithm: MiningAlgorithm; parameters?: Record<string, unknown>; status: AnalysisStatus; event_count: number; case_count: number; activity_count: number; started_at: ISODateTime | null; completed_at: ISODateTime | null; error_code: string; transition_history?: TransitionRecord[]; async_job_id?: UUID | null; created_at: ISODateTime; updated_at: ISODateTime }
export interface DiscoveryCreateRequest { process_name: string; algorithm: MiningAlgorithm; parameters: Record<string, unknown>; idempotency_key: string }

export interface ProcessModel { id: UUID; name: string; process_name: string; description: string; source_kind: ModelSourceKind; current_version_number: number; reference_version_number: number | null; created_at: ISODateTime; updated_at: ISODateTime }
export interface ProcessModelCreateRequest { name: string; process_name: string; description: string; model_data: ProcessGraph }
export interface ProcessModelUpdateRequest { name: string; description: string }
export interface ProcessGraphNode { id: string; label: string; type: 'start' | 'activity' | 'end' | 'gateway'; frequency: number; extensions?: Record<string, unknown> }
export interface ProcessGraphEdge { id: string; source: string; target: string; frequency: number; duration_seconds: number; extensions?: Record<string, unknown> }
export interface ProcessGraph { schema_version: '1.0'; algorithm?: string; nodes: ProcessGraphNode[]; edges: ProcessGraphEdge[]; extensions?: Record<string, unknown> }
export interface ProcessModelVersion { id: UUID; process_model: UUID; version: number; algorithm: MiningAlgorithm | null; parameters: Record<string, unknown>; model_data: ProcessGraph; event_count: number; case_count: number; activity_count: number; avg_case_duration_seconds: string | null; is_reference: boolean; published_at: ISODateTime; created_at: ISODateTime }
export interface SetReferenceRequest { version_id: UUID; transition_key: string; reason?: string }

export interface ConformanceCheck { id: UUID; process_model_version: UUID; event_filter?: EventFilter; status: AnalysisStatus; fitness: string | null; precision: string | null; generalization: string | null; total_cases: number | null; conformant_cases: number | null; deviating_cases: number | null; started_at: ISODateTime | null; completed_at: ISODateTime | null; error_code: string; transition_history?: TransitionRecord[]; created_at: ISODateTime; updated_at: ISODateTime }
export interface ConformanceCreateRequest { process_model_version_id: UUID; event_filter: EventFilter; idempotency_key: string }
export interface ConformanceDeviation { id: UUID; conformance_check: UUID; case_id: string; deviation_type: DeviationType; expected: string; actual: string; position: number | null; description: string; created_at: ISODateTime }
export interface CaseFitness { id: UUID; conformance_check: UUID; case_id: string; fitness: string; is_conformant: boolean; deviation_count: number; trace_length: number; created_at: ISODateTime }
export type FitnessEvidence = CaseFitness;

export interface ProcessMiningConfigurationDocument {
  environment: 'default' | 'development' | 'self-hosted' | 'saas';
  max_batch_events: number; max_export_events: number; max_export_bytes: number; max_conformance_events: number;
  text_max_length: number; attributes_max_bytes: number; forbidden_attribute_keys: string[]; source_module_max_length: number;
  max_event_age_days: number; future_clock_skew_seconds: number; bulk_insert_batch_size: number; event_query_max_days: number;
  retention_days: number; retention_min_days: number; export_projection_bytes_per_event: number; export_iterator_chunk_size: number;
  checksum_chunk_bytes: number; export_expiry_days: number; discovery_min_events: number; discovery_min_cases: number;
  alpha_max_activities: number; heuristic_default_threshold: number; inductive_default_threshold: number;
  default_discovery_algorithm: MiningAlgorithm; algorithm_threshold_step: number;
  algorithm_threshold_min: number; algorithm_threshold_max: number; low_fitness_threshold: number;
  bottleneck_reuse_minutes: number; bottleneck_min_cases: number; bottleneck_critical_ratio: number;
  bottleneck_high_ratio: number; bottleneck_medium_ratio: number; tail_duration_percentile: number;
  resource_concentration_threshold: number; variant_grouping_percentage: number; outbox_freshness_seconds: number;
  analysis_transitions: Record<string, string[]>; analysis_terminal_states: string[];
  export_transitions: Record<string, string[]>; export_terminal_states: string[];
  default_time_window_days: number; list_page_size: number; detail_page_size: number; polling_interval_ms: number;
  visual_zoom_min: number; visual_zoom_max: number; visual_zoom_step: number; visual_edge_width_min: number;
  visual_edge_width_max: number; visual_frequency_divisor: number; visual_duration_divisor: number;
  visual_canvas_width: number; visual_canvas_height: number; visual_node_width: number; visual_node_height: number;
  visual_layout_columns: number; visual_horizontal_gap: number; visual_vertical_gap: number; visual_layout_padding: number;
  download_timeout_ms: number; download_retry_attempts: number; download_retry_base_ms: number;
  download_circuit_failure_threshold: number; download_circuit_reset_ms: number;
  enabled: boolean; rollout_roles: string[]; rollout_cohorts: string[];
}
export interface ProcessMiningConfiguration { id: UUID; version: number; document: ProcessMiningConfigurationDocument; limits: Partial<Record<keyof ProcessMiningConfigurationDocument, [number, number]>>; updated_at: ISODateTime }
export interface ProcessMiningConfigurationVersion { id: UUID; version: number; document: ProcessMiningConfigurationDocument; source: string; correlation_id: string; created_at: ISODateTime }
export interface ConfigurationPreview { valid: true; current_version: number; changes: Record<string, { from: unknown; to: unknown }>; document: ProcessMiningConfigurationDocument }
export interface ConfigurationExport { schema_version: '1.0'; module: 'process_mining'; version: number; document: ProcessMiningConfigurationDocument }

export interface BottleneckAnalysis { id: UUID; process_name: string; time_range_start: ISODateTime; time_range_end: ISODateTime; status: AnalysisStatus; total_cases: number; total_variants: number; avg_case_duration_seconds: string | null; started_at: ISODateTime | null; completed_at: ISODateTime | null; error_code: string; transition_history?: TransitionRecord[]; created_at: ISODateTime; updated_at: ISODateTime }
export interface BottleneckCreateRequest { process_name: string; time_range_start: ISODateTime; time_range_end: ISODateTime; idempotency_key: string }
export interface BottleneckFinding { id: UUID; analysis: UUID; from_activity: string; to_activity: string; avg_duration_seconds: string; median_duration_seconds: string; p95_duration_seconds: string; case_count: number; severity: BottleneckSeverity; resource_bottleneck: string; rank: number; created_at: ISODateTime }
export interface ProcessVariant { id: UUID; analysis: UUID; variant_key: string; activities: string[]; case_count: number; percentage: string; avg_duration_seconds: string; is_happy_path: boolean; is_grouped_other: boolean; created_at: ISODateTime }
export interface TransitionRecord { transition_key: string; command: string; from_state: string; to_state: string; occurred_at: ISODateTime; metadata: { actor_id: string; reason: string; correlation_id: string } }
export interface TransitionActionRequest { transition_key: string; reason?: string; idempotency_key?: string }

export interface ProcessOverview { process_name: string; event_count: number; case_count: number; last_activity: ISODateTime; has_reference: boolean; model_id: UUID | null; last_discovery: ISODateTime | null }
export interface DependencyHealth { name: string; status: 'healthy' | 'degraded' | 'unavailable'; code: string; checked_at: ISODateTime }
export interface ModuleHealth { status: 'healthy' | 'degraded' | 'unavailable'; live: boolean; ready: boolean; checked_at: ISODateTime; dependencies: DependencyHealth[] }
export interface Capability { adapter_id: string; spi_version: string; implementation_version: string; capabilities: string[]; parameter_schema: Record<string, unknown>; availability: 'installed' | 'locked' | 'setup_required' }

export interface PageQuery { page?: number; page_size?: number; ordering?: string; search?: string }
export interface EventFilter extends PageQuery { process_name?: string; start?: ISODateTime; end?: ISODateTime; case_id?: string; activity?: string; resource?: string; source_module?: string }
export interface ProcessFilters extends PageQuery { process_name?: string; source_module?: string; has_reference?: boolean }
export interface ExportFilters extends PageQuery { process_name?: string; format?: ExportFormat; status?: ExportStatus; created_after?: ISODateTime; created_before?: ISODateTime }
export interface DiscoveryFilters extends PageQuery { process_name?: string; algorithm?: MiningAlgorithm; status?: AnalysisStatus }
export interface ModelFilters extends PageQuery { process_name?: string; source_kind?: ModelSourceKind; has_reference?: boolean }
export interface ConformanceFilters extends PageQuery { process_model_version?: UUID; status?: AnalysisStatus; fitness_min?: string; fitness_max?: string; created_after?: ISODateTime; created_before?: ISODateTime }
export interface DeviationFilters extends PageQuery { deviation_type?: DeviationType; case_id?: string; position?: number }
export interface BottleneckFilters extends PageQuery { process_name?: string; status?: AnalysisStatus; time_range_start?: ISODateTime; time_range_end?: ISODateTime }
export interface FindingFilters extends PageQuery { severity?: BottleneckSeverity; resource?: string }
export interface VariantFilters extends PageQuery { is_happy_path?: boolean; is_grouped_other?: boolean }

export const MODULE_API_PREFIX = '/api/v2/process-mining';

function query(path: string, values: object): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)); });
  const suffix = params.toString();
  return suffix ? `${path}?${suffix}` : path;
}

export const ENDPOINTS = {
  PROCESSES: { LIST: `${MODULE_API_PREFIX}/processes/`, QUERY: (filters: ProcessFilters) => query(`${MODULE_API_PREFIX}/processes/`, filters), DETAIL: (name: string) => `${MODULE_API_PREFIX}/processes/${encodeURIComponent(name)}/` },
  EVENTS: { LIST: `${MODULE_API_PREFIX}/events/`, QUERY: (filters: EventFilter) => query(`${MODULE_API_PREFIX}/events/`, filters), DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/events/${id}/`, INGEST: `${MODULE_API_PREFIX}/events/` },
  EXPORTS: { LIST: `${MODULE_API_PREFIX}/exports/`, QUERY: (filters: ExportFilters) => query(`${MODULE_API_PREFIX}/exports/`, filters), DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/exports/${id}/`, CREATE: `${MODULE_API_PREFIX}/exports/`, DOWNLOAD: (id: UUID) => `${MODULE_API_PREFIX}/exports/${id}/download/`, CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/exports/${id}/cancel/`, RETRY: (id: UUID) => `${MODULE_API_PREFIX}/exports/${id}/retry/` },
  DISCOVERIES: { LIST: `${MODULE_API_PREFIX}/discoveries/`, QUERY: (filters: DiscoveryFilters) => query(`${MODULE_API_PREFIX}/discoveries/`, filters), DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/discoveries/${id}/`, CREATE: `${MODULE_API_PREFIX}/discoveries/`, MODEL: (id: UUID) => `${MODULE_API_PREFIX}/discoveries/${id}/model/`, CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/discoveries/${id}/cancel/`, RETRY: (id: UUID) => `${MODULE_API_PREFIX}/discoveries/${id}/retry/` },
  MODELS: { LIST: `${MODULE_API_PREFIX}/models/`, QUERY: (filters: ModelFilters) => query(`${MODULE_API_PREFIX}/models/`, filters), DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/models/${id}/`, CREATE: `${MODULE_API_PREFIX}/models/`, VERSIONS: (id: UUID, page = 1) => query(`${MODULE_API_PREFIX}/models/${id}/versions/`, { page }), SET_REFERENCE: (id: UUID) => `${MODULE_API_PREFIX}/models/${id}/set-reference/` },
  MODEL_VERSIONS: { DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/model-versions/${id}/` },
  CONFORMANCE: { LIST: `${MODULE_API_PREFIX}/conformance-checks/`, QUERY: (filters: ConformanceFilters) => query(`${MODULE_API_PREFIX}/conformance-checks/`, filters), DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/conformance-checks/${id}/`, CREATE: `${MODULE_API_PREFIX}/conformance-checks/`, DEVIATIONS: (id: UUID, filters: DeviationFilters = {}) => query(`${MODULE_API_PREFIX}/conformance-checks/${id}/deviations/`, filters), FITNESS: (id: UUID) => `${MODULE_API_PREFIX}/conformance-checks/${id}/fitness/`, CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/conformance-checks/${id}/cancel/`, RETRY: (id: UUID) => `${MODULE_API_PREFIX}/conformance-checks/${id}/retry/` },
  BOTTLENECKS: { LIST: `${MODULE_API_PREFIX}/bottleneck-analyses/`, QUERY: (filters: BottleneckFilters) => query(`${MODULE_API_PREFIX}/bottleneck-analyses/`, filters), DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/bottleneck-analyses/${id}/`, CREATE: `${MODULE_API_PREFIX}/bottleneck-analyses/`, FINDINGS: (id: UUID, filters: FindingFilters = {}) => query(`${MODULE_API_PREFIX}/bottleneck-analyses/${id}/findings/`, filters), VARIANTS: (id: UUID, filters: VariantFilters = {}) => query(`${MODULE_API_PREFIX}/bottleneck-analyses/${id}/variants/`, filters), CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/bottleneck-analyses/${id}/cancel/`, RETRY: (id: UUID) => `${MODULE_API_PREFIX}/bottleneck-analyses/${id}/retry/` },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
  CONFIGURATION: {
    CURRENT: `${MODULE_API_PREFIX}/configuration/current/`, UPDATE: `${MODULE_API_PREFIX}/configuration/update/`,
    PREVIEW: `${MODULE_API_PREFIX}/configuration/preview/`, HISTORY: (page = 1) => query(`${MODULE_API_PREFIX}/configuration/history/`, { page }),
    ROLLBACK: `${MODULE_API_PREFIX}/configuration/rollback/`, IMPORT: `${MODULE_API_PREFIX}/configuration/import/`,
    EXPORT: `${MODULE_API_PREFIX}/configuration/export/`,
  },
} as const;

export const PROCESS_MINING_ROUTES = {
  PROCESSES: '/process-mining/processes', EVENTS: '/process-mining/events', EVENT_INGEST: '/process-mining/events/ingest',
  DISCOVERIES: '/process-mining/discoveries', DISCOVERY_CREATE: '/process-mining/discoveries/new',
  CONFORMANCE: '/process-mining/conformance', CONFORMANCE_CREATE: '/process-mining/conformance/new',
  BOTTLENECKS: '/process-mining/bottlenecks', BOTTLENECK_CREATE: '/process-mining/bottlenecks/new',
  EXPORTS: '/process-mining/exports', EXPORT_CREATE: '/process-mining/exports/new', CONFIGURATION: '/process-mining/configuration',
  PROCESS: (name: string) => `/process-mining/processes/${encodeURIComponent(name)}`,
  EVENT: (id: UUID) => `/process-mining/events/${id}`, DISCOVERY: (id: UUID) => `/process-mining/discoveries/${id}`,
  CONFORMANCE_DETAIL: (id: UUID) => `/process-mining/conformance/${id}`, BOTTLENECK: (id: UUID) => `/process-mining/bottlenecks/${id}`,
  MODEL_EDIT: (id: UUID) => `/process-mining/models/${id}/edit`, MODEL_MAP: (id: UUID) => `/process-mining/models/${id}/map`,
  EVENTS_FOR_PROCESS: (name: string) => `/process-mining/events?process_name=${encodeURIComponent(name)}`,
  DISCOVERY_CREATE_FOR_PROCESS: (name: string) => `/process-mining/discoveries/new?process_name=${encodeURIComponent(name)}`,
  BOTTLENECK_CREATE_FOR_PROCESS: (name: string) => `/process-mining/bottlenecks/new?process_name=${encodeURIComponent(name)}`,
  EXPORT_CREATE_FOR_PROCESS: (name: string) => `/process-mining/exports/new?process_name=${encodeURIComponent(name)}`,
} as const;
