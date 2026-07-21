/**
 * Public frontend contract for the Performance Monitoring foundation module.
 *
 * Paid modules may contribute OpenTelemetry-compatible namespaces, semantic
 * attributes, dashboard templates, alert packs and SLO packs without coupling
 * their UI to this module's implementation. API URLs must remain here.
 */

export type UUID = string;
export type ISODateTime = string;
export type HealthState = 'healthy' | 'degraded' | 'stale' | 'no_telemetry' | 'disabled';
export type Severity = 'info' | 'warning' | 'critical';
export type MetricType = 'gauge' | 'counter' | 'histogram' | 'summary';
export type ComparisonOperator = 'gt' | 'gte' | 'lt' | 'lte' | 'eq' | 'neq';
export type AlertCondition = 'above_threshold' | 'below_threshold' | 'rate_of_change' | 'absence';
export type SLAWindow = 'rolling_1h' | 'rolling_24h' | 'calendar_month';
export type TimeRangePreset = '15m' | '1h' | '6h' | '24h' | '7d' | '30d';

export interface PaginationMeta {
  page: number;
  page_size: number;
  count: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface ApiEnvelope<T> {
  data: T;
  meta: { correlation_id: string; timestamp: ISODateTime; pagination?: PaginationMeta };
}

export interface PageResult<T> {
  items: readonly T[];
  pagination: PaginationMeta;
  correlationId: string;
  receivedAt: ISODateTime;
}

export interface ListQuery {
  page?: number;
  page_size?: number;
  search?: string;
  ordering?: string;
}

export interface TelemetrySource {
  id: UUID;
  tenant_id: UUID;
  name: string;
  source_type: 'otlp' | 'prometheus' | 'application' | 'webhook' | 'import';
  description: string;
  status: HealthState;
  sampling_rate: number;
  retention_days?: number;
  daily_event_quota?: number;
  redaction_fields?: string[];
  last_seen_at: ISODateTime | null;
  is_active: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface TelemetrySourceCreate {
  name: string;
  source_type: TelemetrySource['source_type'];
  description?: string;
  sampling_rate?: number;
  retention_days?: number;
  daily_event_quota?: number;
  redaction_fields?: string[];
}

export interface MonitoringEnvironment {
  id: UUID;
  tenant_id: UUID;
  name: string;
  slug: string;
  description: string;
  kind: string;
  is_active: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface MonitoredService {
  id: UUID;
  tenant_id: UUID;
  name: string;
  slug: string;
  environment: UUID;
  source: UUID | null;
  namespace: string;
  version: string;
  owner: string;
  language: string;
  status: HealthState;
  last_seen_at: ISODateTime | null;
  attributes: Record<string, string | number | boolean | null>;
  is_active: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Metric {
  id: UUID;
  tenant_id: UUID;
  metric_name: string;
  display_name: string;
  namespace: string;
  description: string;
  metric_type: MetricType;
  unit: string;
  source: UUID | null;
  service: UUID | null;
  environment: UUID | null;
  default_tags: Record<string, string>;
  expected_interval_seconds: number;
  retention_days: number;
  is_active: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface MetricCreate {
  metric_name: string;
  metric_type: MetricType;
  unit: string;
  description?: string;
  tags?: Record<string, string>;
}

export interface MetricDataPoint {
  id: UUID;
  metric_name: string;
  timestamp: ISODateTime;
  value: number;
  tags: Record<string, string>;
  session_id: string | null;
}

export interface MetricSeries {
  metric_name: string;
  aggregation: string;
  interval: string;
  data: { timestamp: ISODateTime; value: number }[];
}

export interface MetricQuery {
  metric_name: string;
  start?: ISODateTime;
  end?: ISODateTime;
  aggregation?: 'avg' | 'sum' | 'min' | 'max' | 'count' | 'p50' | 'p95' | 'p99';
  interval?: string;
  tags?: Record<string, string>;
}

export interface MetricBatchResult {
  accepted: number;
  rejected: number;
  errors: readonly { index: number; code: string; message: string }[];
}

export interface MetricSummary {
  metric_name: string;
  period: string;
  minimum: number | null;
  maximum: number | null;
  average: number | null;
  count: number;
  p50: number | null;
  p95: number | null;
  p99: number | null;
}

export interface MetricIngest {
  metric_name: string;
  value: number;
  timestamp?: ISODateTime;
  metric_type?: MetricType;
  unit?: string;
  namespace?: string;
  source_id?: UUID;
  service_id?: UUID;
  environment_id?: UUID;
  session_id?: string;
  tags?: Record<string, string>;
  idempotency_key?: string;
}

export interface LogEntry {
  id: UUID;
  tenant_id: UUID;
  timestamp: ISODateTime;
  source: UUID;
  service: UUID | null;
  environment: UUID | null;
  observed_at: ISODateTime;
  level: 'trace' | 'debug' | 'info' | 'warn' | 'error' | 'fatal';
  message: string;
  trace_id: string | null;
  span_id: string | null;
  correlation_id: string | null;
  attributes: Record<string, string | number | boolean | null>;
}

export interface LogQuery extends ListQuery {
  from?: ISODateTime;
  to?: ISODateTime;
  level?: LogEntry['level'];
  service_id?: UUID;
  environment_id?: UUID;
  trace_id?: string;
}

export interface Span {
  id: UUID;
  span_id: string;
  parent_span_id: string | null;
  trace: UUID;
  service: UUID;
  name: string;
  kind: string;
  started_at: ISODateTime;
  ended_at: ISODateTime;
  duration_ms: number;
  status: 'unset' | 'ok' | 'error';
  attributes: Record<string, string | number | boolean | null>;
}

export interface Trace {
  id: UUID;
  tenant_id: UUID;
  trace_id: string;
  source: UUID;
  service: UUID;
  environment: UUID | null;
  name: string;
  started_at: ISODateTime;
  ended_at: ISODateTime;
  duration_ms: number;
  status: 'unset' | 'ok' | 'error';
  span_count: number;
  error_span_count: number;
  sampled: boolean;
  spans?: Span[];
}

export interface TraceQuery extends ListQuery {
  from?: ISODateTime;
  to?: ISODateTime;
  service_id?: UUID;
  environment_id?: UUID;
  status?: Trace['status'];
  min_duration_ms?: number;
}

export interface AlertRule {
  id: UUID;
  tenant_id: UUID;
  name: string;
  description: string;
  metric: UUID | null;
  metric_name: string;
  condition: AlertCondition;
  threshold: number | null;
  evaluation_window_minutes: number;
  evaluation_interval_seconds: number;
  cooldown_minutes: number;
  severity: Severity;
  action: Record<string, unknown>;
  is_active: boolean;
  last_evaluated_at: ISODateTime | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface AlertRuleCreate {
  name: string;
  description?: string;
  /** UI-only selection bridge; the create adapter submits metric_name per API contract. */
  metric?: UUID | null;
  metric_name: string;
  condition: AlertCondition;
  threshold?: number | null;
  evaluation_window_minutes: number;
  evaluation_interval_seconds?: number;
  cooldown_minutes?: number;
  severity: Severity;
  action: Record<string, unknown>;
}

export interface Alert {
  id: UUID;
  tenant_id: UUID;
  alert_rule: UUID;
  metric_name: string;
  status: 'firing' | 'acknowledged' | 'resolved';
  severity: Severity;
  title: string;
  description: string;
  triggered_value: number | null;
  threshold: number;
  triggered_at: ISODateTime;
  last_observed_at: ISODateTime;
  occurrence_count: number;
  acknowledged_at: ISODateTime | null;
  acknowledged_by: UUID | null;
  resolved_at: ISODateTime | null;
  resolution_note: string;
  context: Record<string, unknown>;
}

export interface AlertTransition {
  note?: string;
}

export interface SLADefinition {
  id: UUID;
  tenant_id: UUID;
  name: string;
  description: string;
  metric: UUID | null;
  metric_name: string;
  service: UUID | null;
  service_name: string;
  comparison: 'gte' | 'lte';
  target: number;
  window: SLAWindow;
  expected_interval_seconds: number;
  version: number;
  effective_from: ISODateTime;
  effective_until: ISODateTime | null;
  is_active: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface SLADefinitionCreate {
  metric_name: string;
  service_name: string;
  comparison: 'gte' | 'lte';
  target: number;
  window: SLAWindow;
  expected_interval_seconds?: number;
}

export interface SLAReportRequest {
  sla_id: UUID;
  period: string;
  format: 'json' | 'csv';
}

export interface SLAComplianceRecord {
  id: UUID;
  sla: UUID;
  period_start: ISODateTime;
  period_end: ISODateTime;
  expected_samples: number;
  observed_samples: number;
  compliant_samples: number;
  missing_samples: number;
  actual_value: number;
  target_value: number;
  is_compliant: boolean;
  compliance_percentage: number | null;
  breach_duration_minutes: number;
  status: 'compliant' | 'breached' | 'insufficient_data';
  created_at: ISODateTime;
}

export interface MonitoringSummary {
  state: HealthState;
  generated_at: ISODateTime;
  data_freshness_seconds: number | null;
  services: { total: number; healthy: number; degraded: number; no_data: number };
  telemetry: { sources: number; active_sources: number; events_last_hour: number };
  apm: { request_rate: number | null; error_rate: number | null; latency_p95_ms: number | null };
  alerts: { firing: number; critical: number; acknowledged: number };
  slos: { total: number; compliant: number; at_risk: number; breached: number };
  recent_alerts: Alert[];
  top_services: MonitoredService[];
}

export interface MonitoringDashboard {
  id: UUID;
  tenant_id: UUID;
  name: string;
  description: string;
  is_default: boolean;
  layout: Record<string, unknown>;
  widgets: readonly Record<string, unknown>[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface SLODefinition {
  id: UUID;
  tenant_id: UUID;
  name: string;
  description: string;
  service: UUID;
  indicator_metric: UUID;
  comparison: ComparisonOperator;
  threshold: number;
  objective_percentage: number;
  window_days: number;
  expected_interval_seconds: number;
  error_budget_minutes: number;
  is_active: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface HealthCheck {
  status: 'healthy' | 'degraded' | 'unavailable';
  generated_at: ISODateTime;
  checks: Record<string, { status: string; message?: string }>;
}

export interface ActionResult {
  id: UUID;
  status: string;
  updated_at?: ISODateTime;
}

export interface ExtensionContribution {
  schema_version: '1.0';
  module: string;
  metric_namespaces?: string[];
  semantic_attributes?: Record<string, string>;
  dashboard_templates?: string[];
  alert_rule_packs?: string[];
  slo_packs?: string[];
  drill_down_routes?: Record<string, string>;
}

export const MODULE_API_PREFIX = '/api/v2/performance-monitoring';

const detail = (resource: string, id: string) => `${MODULE_API_PREFIX}/${resource}/${id}/`;

export const ENDPOINTS = {
  DASHBOARDS: {
    LIST: `${MODULE_API_PREFIX}/dashboards/`,
    DETAIL: (id: UUID) => detail('dashboards', id),
  },
  TELEMETRY_SOURCES: {
    LIST: `${MODULE_API_PREFIX}/telemetry-sources/`,
    DETAIL: (id: UUID) => detail('telemetry-sources', id),
  },
  SERVICES: {
    LIST: `${MODULE_API_PREFIX}/services/`,
    DETAIL: (id: UUID) => detail('services', id),
  },
  ENVIRONMENTS: {
    LIST: `${MODULE_API_PREFIX}/environments/`,
    DETAIL: (id: UUID) => detail('environments', id),
  },
  METRICS: {
    LIST: `${MODULE_API_PREFIX}/metrics/`,
    DETAIL: (id: UUID) => detail('metrics', id),
    BATCH: `${MODULE_API_PREFIX}/metrics/batch/`,
    QUERY: `${MODULE_API_PREFIX}/metrics/query/`,
    SUMMARY: `${MODULE_API_PREFIX}/metrics/summary/`,
  },
  DATA_POINTS: { LIST: `${MODULE_API_PREFIX}/metric-data-points/` },
  LOGS: { LIST: `${MODULE_API_PREFIX}/logs/`, DETAIL: (id: UUID) => detail('logs', id) },
  TRACES: { LIST: `${MODULE_API_PREFIX}/traces/`, DETAIL: (id: UUID) => detail('traces', id) },
  SPANS: { FOR_TRACE: (id: UUID) => `${detail('traces', id)}spans/` },
  ALERT_RULES: {
    LIST: `${MODULE_API_PREFIX}/alerts/rules/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/alerts/rules/${id}/`,
  },
  ALERTS: {
    LIST: `${MODULE_API_PREFIX}/alerts/`,
    DETAIL: (id: UUID) => detail('alerts', id),
    EVALUATE: `${MODULE_API_PREFIX}/alerts/evaluate/`,
    ACKNOWLEDGE: (id: UUID) => `${detail('alerts', id)}acknowledge/`,
    RESOLVE: (id: UUID) => `${detail('alerts', id)}resolve/`,
  },
  SLA: {
    LIST: `${MODULE_API_PREFIX}/sla/`,
    DETAIL: (id: UUID) => detail('sla', id),
    COMPLIANCE: (id: UUID) => `${detail('sla', id)}compliance/`,
    REPORTS: `${MODULE_API_PREFIX}/sla/reports/`,
  },
  SLOS: {
    LIST: `${MODULE_API_PREFIX}/slos/`,
    DETAIL: (id: UUID) => detail('slos', id),
    EVALUATE: (id: UUID) => `${detail('slos', id)}evaluate/`,
  },
  COMPLIANCE_RECORDS: {
    LIST: `${MODULE_API_PREFIX}/compliance-records/`,
    DETAIL: (id: UUID) => detail('compliance-records', id),
  },
  REPORTS: { LIST: `${MODULE_API_PREFIX}/reports/`, DETAIL: (id: UUID) => detail('reports', id) },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTES = {
  OVERVIEW: '/performance-monitoring/dashboard',
  METRICS: '/performance-monitoring/metrics',
  LOGS: '/performance-monitoring/logs',
  TRACES: '/performance-monitoring/traces',
  SERVICES: '/performance-monitoring/services',
  ALERTS: '/performance-monitoring/alerts',
  ALERT_RULES: '/performance-monitoring/alerts/rules',
  SLOS: '/performance-monitoring/sla',
  SETUP: '/performance-monitoring/setup',
} as const;
