/** Typed public contract for the governed Business Intelligence v2 API. */

export type JSONScalar = string | number | boolean | null;
export type JSONValue = JSONScalar | JSONObject | readonly JSONValue[];
// Recursive JSON objects require an index signature; Record cannot express this recursion in TypeScript 5.3.
// eslint-disable-next-line @typescript-eslint/consistent-indexed-object-style
export interface JSONObject {
  readonly [key: string]: JSONValue;
}

export interface ApiEnvelope<T> {
  data: T;
  meta: { correlation_id: string; timestamp: string; pagination?: PaginatedMeta };
}
export interface PaginatedMeta {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}
export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    correlation_id?: string;
    field_errors?: Record<string, readonly string[]>;
    details?: JSONValue;
  };
}
export interface PageResult<T> {
  items: T[];
  meta: PaginatedMeta;
  correlationId: string;
}
export type ListFilters = Record<string, string | number | boolean | undefined | null>;

export type LifecycleState = "draft" | "published" | "archived";
export type LifecycleCommand = "publish" | "archive" | "restore";
export type ScalarType = "string" | "integer" | "number" | "boolean" | "date" | "datetime" | "uuid";
export type FilterOperator =
  | "eq"
  | "neq"
  | "in"
  | "not_in"
  | "contains"
  | "starts_with"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "is_null"
  | "between";
export type Sensitivity = "public" | "internal" | "confidential" | "restricted";
export type EntitlementState = "free" | "available" | "locked";
export interface DatasetDimension {
  key: string;
  label: string;
  type: ScalarType;
  filter_operators: FilterOperator[];
  sensitivity: Sensitivity;
  description?: string;
}
export interface DatasetMeasure {
  key: string;
  label: string;
  result_type: ScalarType;
  aggregation: string;
  formatting?: string;
  description?: string;
}
export interface DatasetEntitlement {
  state: EntitlementState;
  required_entitlement?: string;
  upgrade_url?: string;
  reason?: string;
}
export interface DatasetSummary {
  key: string;
  module: string;
  label: string;
  description: string;
  version: string;
  freshness: string;
  entitlement: DatasetEntitlement;
  dimension_count: number;
  measure_count: number;
}
export interface DatasetDescriptor
  extends Omit<DatasetSummary, "dimension_count" | "measure_count"> {
  dimensions: DatasetDimension[];
  measures: DatasetMeasure[];
  supported_grouping: string[];
  supported_ordering: string[];
  required_permission: string;
  maximum_row_limit: number;
}

export interface QueryFilter {
  field: string;
  operator: FilterOperator;
  value?: JSONValue;
  parameter?: string;
}
export interface QueryMeasureSelection {
  key: string;
  alias?: string;
}
export interface QueryGrouping {
  dimension: string;
}
export interface QueryOrdering {
  field: string;
  direction: "asc" | "desc";
}
export interface QueryParameterDefinition {
  type: ScalarType;
  required?: boolean;
  default?: JSONValue;
  label?: string;
  description?: string;
}
export type ParameterSchema = Record<string, QueryParameterDefinition>;
export interface TransitionRecord {
  command:
    | LifecycleCommand
    | "create"
    | "update"
    | "delete"
    | "enqueue"
    | "start"
    | "succeed"
    | "fail"
    | "cancel";
  from_state?: string;
  to_state: string;
  actor_id?: string;
  reason?: string;
  correlation_id?: string;
  timestamp: string;
}
export interface QueryListItem {
  id: string;
  query_code: string;
  name: string;
  description: string;
  dataset_key: string;
  state: LifecycleState;
  version: number;
  updated_at: string;
  created_by_id: string;
  last_execution?: ExecutionListItem | null;
}
export interface QueryDetail extends QueryListItem {
  dataset_version: string;
  dataset_schema_fingerprint: string;
  dimensions: string[];
  measures: QueryMeasureSelection[];
  filters: QueryFilter[];
  grouping: QueryGrouping[];
  ordering: QueryOrdering[];
  parameters_schema: ParameterSchema;
  row_limit: number;
  cache_ttl_seconds: number;
  transition_history: TransitionRecord[];
  created_at: string;
  updated_by_id: string;
}
export interface QueryCreate {
  query_code: string;
  name: string;
  description?: string;
  dataset_key: string;
  dimensions: string[];
  measures: QueryMeasureSelection[];
  filters?: QueryFilter[];
  grouping?: QueryGrouping[];
  ordering?: QueryOrdering[];
  parameters_schema?: ParameterSchema;
  row_limit?: number;
  cache_ttl_seconds?: number;
}
export type QueryUpdate = Partial<QueryCreate> & { version: number };
export interface QueryValidation {
  valid: boolean;
  columns?: ResultColumn[];
  warnings?: string[];
  normalized_definition?: JSONObject;
}

export type ReportType = "table" | "pivot" | "chart" | "kpi";
export interface QuerySummary {
  id: string;
  query_code: string;
  name: string;
  dataset_key: string;
  state: LifecycleState;
  version: number;
}
export interface ReportListItem {
  id: string;
  report_code: string;
  report_name: string;
  description: string;
  report_type: ReportType;
  state: LifecycleState;
  version: number;
  dataset_key?: string;
  query_definition?: QuerySummary | string;
  updated_at: string;
  last_execution?: ExecutionListItem | null;
}
export interface ReportDetail extends ReportListItem {
  query_definition: QuerySummary;
  visualization: JSONObject;
  default_parameters: JSONObject;
  transition_history: TransitionRecord[];
  created_at: string;
  created_by_id: string;
  updated_by_id: string;
}
export interface ReportCreate {
  report_code: string;
  report_name: string;
  description?: string;
  report_type: ReportType;
  query_definition_id: string;
  visualization?: JSONObject;
  default_parameters?: JSONObject;
}
export type ReportUpdate = Partial<ReportCreate> & { version: number };

export interface DashboardListItem {
  id: string;
  dashboard_code: string;
  dashboard_name: string;
  description: string;
  state: LifecycleState;
  version: number;
  effective_access?: "owner" | "view" | "edit";
  widget_count?: number;
  last_refresh?: string | null;
  updated_at: string;
}
export interface DashboardDetail extends DashboardListItem {
  global_filters: QueryFilter[];
  refresh_interval_seconds: number | null;
  widgets: DashboardWidget[];
  shares?: DashboardShare[];
  transition_history: TransitionRecord[];
  created_at: string;
  created_by_id: string;
  updated_by_id: string;
}
export interface DashboardCreate {
  dashboard_code: string;
  dashboard_name: string;
  description?: string;
  global_filters?: QueryFilter[];
  refresh_interval_seconds?: number | null;
}
export type DashboardUpdate = Partial<DashboardCreate> & { version: number };
export type WidgetType = "kpi" | "table" | "bar" | "line" | "area" | "pie" | "funnel";
export interface DashboardWidget {
  id: string;
  dashboard_id?: string;
  query_definition?: QuerySummary | string | null;
  report?: ReportListItem | string | null;
  widget_type: WidgetType;
  title: string;
  description: string;
  x: number;
  y: number;
  width: number;
  height: number;
  visualization: JSONObject;
  filters: QueryFilter[];
  refresh_interval_seconds: number | null;
  display_order: number;
  version: number;
  updated_at: string;
}
export interface WidgetCreate {
  query_definition_id?: string | null;
  report_id?: string | null;
  widget_type: WidgetType;
  title: string;
  description?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  visualization?: JSONObject;
  filters?: QueryFilter[];
  refresh_interval_seconds?: number | null;
  display_order: number;
}
export type WidgetUpdate = Partial<WidgetCreate> & { version: number };
export interface WidgetReorderItem {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  display_order: number;
  version: number;
}
export interface DashboardShare {
  id: string;
  dashboard_id?: string;
  subject_type: "user" | "role";
  subject_id: string;
  access_level: "view" | "edit";
  shared_by_id: string;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface ShareCreate {
  subject_type: "user" | "role";
  subject_id: string;
  access_level: "view" | "edit";
  expires_at?: string | null;
}
export type ShareUpdate = Partial<Pick<ShareCreate, "access_level" | "expires_at">>;

export type ExecutionStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "timed_out";
export interface ExecutionListItem {
  id: string;
  job_id?: string;
  status: ExecutionStatus;
  query_definition_id?: string;
  report_id?: string | null;
  dashboard_id?: string | null;
  dataset_key: string;
  dataset_version: string;
  dataset_schema_fingerprint: string;
  definition_version: number;
  actor_id?: string;
  row_count: number | null;
  truncated: boolean;
  cache_hit: boolean;
  duration_ms: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
export interface ExecutionDetail extends ExecutionListItem {
  parameters: JSONObject;
  transition_history: TransitionRecord[];
  result_columns: ResultColumn[];
  error_code: string;
  error_message: string;
  effective_query_fingerprint: string;
  freshness_token: string;
  data_as_of: string | null;
  result_purged_at: string | null;
}
export interface ResultColumn {
  key: string;
  label: string;
  type: ScalarType;
  formatting?: string;
}
export interface ExecutionResult {
  execution_id: string;
  columns: ResultColumn[];
  rows: JSONObject[];
  row_count: number;
  truncated: boolean;
  cache_hit: boolean;
  definition_version: number;
  dataset_key: string;
  dataset_version: string;
  dataset_schema_fingerprint: string;
  effective_query_fingerprint: string;
  freshness_token: string;
  data_as_of?: string | null;
}
export interface ExecutionRequest {
  parameters?: JSONObject;
}
export interface EnqueueResult {
  execution_id?: string;
  execution_ids?: string[];
  job_id?: string;
  job_ids?: string[];
  status: ExecutionStatus;
}
export interface HealthResponse {
  status: "healthy" | "degraded" | "unavailable";
  ready: boolean;
  dependencies: Record<string, { status: string; [key: string]: JSONValue }>;
}
export interface TransitionRequest {
  version: number;
  reason?: string;
}

export const MODULE_API_PREFIX = "/api/v2/business-intelligence";
export const ENDPOINTS = {
  DATASETS: {
    LIST: `${MODULE_API_PREFIX}/datasets/`,
    DETAIL: (key: string) => `${MODULE_API_PREFIX}/datasets/${encodeURIComponent(key)}/` as const,
  },
  QUERIES: {
    LIST: `${MODULE_API_PREFIX}/queries/`,
    CREATE: `${MODULE_API_PREFIX}/queries/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/queries/${id}/` as const,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/queries/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/queries/${id}/` as const,
    VALIDATE: (id: string) => `${MODULE_API_PREFIX}/queries/${id}/validate/` as const,
    PUBLISH: (id: string) => `${MODULE_API_PREFIX}/queries/${id}/publish/` as const,
    ARCHIVE: (id: string) => `${MODULE_API_PREFIX}/queries/${id}/archive/` as const,
    RESTORE: (id: string) => `${MODULE_API_PREFIX}/queries/${id}/restore/` as const,
    EXECUTE: (id: string) => `${MODULE_API_PREFIX}/queries/${id}/execute/` as const,
  },
  REPORTS: {
    LIST: `${MODULE_API_PREFIX}/reports/`,
    CREATE: `${MODULE_API_PREFIX}/reports/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/` as const,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/` as const,
    PUBLISH: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/publish/` as const,
    ARCHIVE: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/archive/` as const,
    RESTORE: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/restore/` as const,
    EXECUTE: (id: string) => `${MODULE_API_PREFIX}/reports/${id}/execute/` as const,
  },
  DASHBOARDS: {
    LIST: `${MODULE_API_PREFIX}/dashboards/`,
    CREATE: `${MODULE_API_PREFIX}/dashboards/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/` as const,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/` as const,
    PUBLISH: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/publish/` as const,
    ARCHIVE: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/archive/` as const,
    RESTORE: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/restore/` as const,
    EXECUTE: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/execute/` as const,
    WIDGETS: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/widgets/` as const,
    WIDGET_DETAIL: (id: string, widgetId: string) =>
      `${MODULE_API_PREFIX}/dashboards/${id}/widgets/${widgetId}/` as const,
    WIDGET_REORDER: (id: string) =>
      `${MODULE_API_PREFIX}/dashboards/${id}/widgets/reorder/` as const,
    SHARES: (id: string) => `${MODULE_API_PREFIX}/dashboards/${id}/shares/` as const,
    SHARE_DETAIL: (id: string, shareId: string) =>
      `${MODULE_API_PREFIX}/dashboards/${id}/shares/${shareId}/` as const,
  },
  EXECUTIONS: {
    LIST: `${MODULE_API_PREFIX}/executions/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/executions/${id}/` as const,
    RESULT: (id: string) => `${MODULE_API_PREFIX}/executions/${id}/result/` as const,
    CANCEL: (id: string) => `${MODULE_API_PREFIX}/executions/${id}/cancel/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
