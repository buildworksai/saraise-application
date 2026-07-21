import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ActionResult,
  type Alert,
  type AlertRule,
  type AlertRuleCreate,
  type AlertTransition,
  type ApiEnvelope,
  type HealthCheck,
  type ListQuery,
  type LogEntry,
  type LogQuery,
  type Metric,
  type MetricCreate,
  type MetricBatchResult,
  type MetricIngest,
  type MetricQuery,
  type MetricSeries,
  type MetricSummary,
  type MonitoringEnvironment,
  type MonitoredService,
  type MonitoringDashboard,
  type PageResult,
  type SLAComplianceRecord,
  type SLADefinition,
  type SLADefinitionCreate,
  type SLAReportRequest,
  type SLODefinition,
  type Span,
  type TelemetrySource,
  type TelemetrySourceCreate,
  type Trace,
  type TraceQuery,
  type UUID,
} from '../contracts';

type QueryValue = string | number | boolean | undefined;

export class PerformanceMonitoringApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
  ) {
    super(message);
    this.name = 'PerformanceMonitoringApiError';
  }
}

function withQuery(path: string, query: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `${path}?${encoded}` : path;
}

function queryValues(query: ListQuery = {}): Record<string, QueryValue> {
  return { page: query.page, page_size: query.page_size, search: query.search, ordering: query.ordering };
}

async function call<T>(request: () => Promise<ApiEnvelope<T>>): Promise<ApiEnvelope<T>> {
  try {
    return await request();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    throw new PerformanceMonitoringApiError(
      error.message,
      error.status,
      error.code ?? 'request_failed',
      error.correlationId ?? null,
    );
  }
}

async function data<T>(request: () => Promise<ApiEnvelope<T>>): Promise<T> {
  return (await call(request)).data;
}

async function page<T>(request: () => Promise<ApiEnvelope<readonly T[]>>): Promise<PageResult<T>> {
  const envelope = await call(request);
  if (!envelope.meta.pagination) {
    throw new Error('The monitoring API returned a list without pagination metadata.');
  }
  return {
    items: envelope.data,
    pagination: envelope.meta.pagination,
    correlationId: envelope.meta.correlation_id,
    receivedAt: envelope.meta.timestamp,
  };
}

export const performanceMonitoringService = {
  listTelemetrySources(query: ListQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly TelemetrySource[]>>(
      withQuery(ENDPOINTS.TELEMETRY_SOURCES.LIST, queryValues(query)),
    ));
  },
  createTelemetrySource(payload: TelemetrySourceCreate) {
    return data(() => apiClient.post<ApiEnvelope<TelemetrySource>>(ENDPOINTS.TELEMETRY_SOURCES.LIST, payload));
  },
  listEnvironments(query: ListQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly MonitoringEnvironment[]>>(
      withQuery(ENDPOINTS.ENVIRONMENTS.LIST, queryValues(query)),
    ));
  },
  listServices(query: ListQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly MonitoredService[]>>(
      withQuery(ENDPOINTS.SERVICES.LIST, queryValues(query)),
    ));
  },
  getService(id: UUID) {
    return data(() => apiClient.get<ApiEnvelope<MonitoredService>>(ENDPOINTS.SERVICES.DETAIL(id)));
  },
  listDashboards(query: ListQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly MonitoringDashboard[]>>(
      withQuery(ENDPOINTS.DASHBOARDS.LIST, queryValues(query)),
    ));
  },
  listMetrics(query: ListQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly Metric[]>>(
      withQuery(ENDPOINTS.METRICS.LIST, queryValues(query)),
    ));
  },
  getMetric(id: UUID) {
    return data(() => apiClient.get<ApiEnvelope<Metric>>(ENDPOINTS.METRICS.DETAIL(id)));
  },
  createMetric(payload: MetricCreate) {
    return data(() => apiClient.post<ApiEnvelope<Metric>>(ENDPOINTS.METRICS.LIST, payload));
  },
  ingestMetricBatch(payload: readonly MetricIngest[]) {
    return data(() => apiClient.post<ApiEnvelope<MetricBatchResult>>(ENDPOINTS.METRICS.BATCH, { data_points: payload }));
  },
  queryMetric(query: MetricQuery) {
    return data(() => apiClient.get<ApiEnvelope<MetricSeries>>(
      withQuery(ENDPOINTS.METRICS.QUERY, {
        metric_name: query.metric_name,
        start: query.start,
        end: query.end,
        aggregation: query.aggregation,
        interval: query.interval,
        tags: query.tags ? Object.entries(query.tags).map(([key, value]) => `${key}=${value}`).join(',') : undefined,
      }),
    ));
  },
  summarizeMetrics(metricNames: readonly string[], period = '1h') {
    return data(() => apiClient.get<ApiEnvelope<{ summaries: readonly MetricSummary[] }>>(
      withQuery(ENDPOINTS.METRICS.SUMMARY, { metric_names: metricNames.join(','), period }),
    ));
  },
  listLogs(query: LogQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly LogEntry[]>>(
      withQuery(ENDPOINTS.LOGS.LIST, {
        ...queryValues(query),
        from: query.from,
        to: query.to,
        level: query.level,
        service_id: query.service_id,
        environment_id: query.environment_id,
        trace_id: query.trace_id,
      }),
    ));
  },
  getLog(id: UUID) {
    return data(() => apiClient.get<ApiEnvelope<LogEntry>>(ENDPOINTS.LOGS.DETAIL(id)));
  },
  listTraces(query: TraceQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly Trace[]>>(
      withQuery(ENDPOINTS.TRACES.LIST, {
        ...queryValues(query),
        from: query.from,
        to: query.to,
        service_id: query.service_id,
        environment_id: query.environment_id,
        status: query.status,
        min_duration_ms: query.min_duration_ms,
      }),
    ));
  },
  getTrace(id: UUID) {
    return data(() => apiClient.get<ApiEnvelope<Trace>>(ENDPOINTS.TRACES.DETAIL(id)));
  },
  listTraceSpans(id: UUID) {
    return data(() => apiClient.get<ApiEnvelope<readonly Span[]>>(ENDPOINTS.SPANS.FOR_TRACE(id)));
  },
  listAlertRules(query: ListQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly AlertRule[]>>(
      withQuery(ENDPOINTS.ALERT_RULES.LIST, queryValues(query)),
    ));
  },
  createAlertRule(payload: AlertRuleCreate) {
    const { name, metric_name, condition, threshold, evaluation_window_minutes, cooldown_minutes, severity, action } = payload;
    return data(() => apiClient.post<ApiEnvelope<AlertRule>>(ENDPOINTS.ALERT_RULES.LIST, {
      name,
      metric_name,
      condition,
      threshold,
      evaluation_window_minutes,
      cooldown_minutes,
      severity,
      action,
    }));
  },
  evaluateAlertRule(id: UUID) {
    return data(() => apiClient.post<ApiEnvelope<ActionResult>>(ENDPOINTS.ALERTS.EVALUATE, { rule_id: id }));
  },
  listAlerts(query: ListQuery & { status?: Alert['status']; severity?: Severity } = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly Alert[]>>(
      withQuery(ENDPOINTS.ALERTS.LIST, { ...queryValues(query), status: query.status, severity: query.severity }),
    ));
  },
  acknowledgeAlert(id: UUID, payload: AlertTransition = {}) {
    return data(() => apiClient.post<ApiEnvelope<Alert>>(ENDPOINTS.ALERTS.ACKNOWLEDGE(id), payload));
  },
  resolveAlert(id: UUID, payload: AlertTransition = {}) {
    return data(() => apiClient.post<ApiEnvelope<Alert>>(ENDPOINTS.ALERTS.RESOLVE(id), payload));
  },
  listSLAs(query: ListQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly SLADefinition[]>>(
      withQuery(ENDPOINTS.SLA.LIST, queryValues(query)),
    ));
  },
  createSLA(payload: SLADefinitionCreate) {
    return data(() => apiClient.post<ApiEnvelope<SLADefinition>>(ENDPOINTS.SLA.LIST, payload));
  },
  evaluateSLA(id: UUID) {
    return data(() => apiClient.get<ApiEnvelope<SLAComplianceRecord>>(ENDPOINTS.SLA.COMPLIANCE(id)));
  },
  generateSLAReport(payload: SLAReportRequest) {
    return data(() => apiClient.post<ApiEnvelope<ActionResult>>(ENDPOINTS.SLA.REPORTS, payload));
  },
  listSLOs(query: ListQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly SLODefinition[]>>(
      withQuery(ENDPOINTS.SLOS.LIST, queryValues(query)),
    ));
  },
  createSLO(payload: SLADefinitionCreate) {
    return data(() => apiClient.post<ApiEnvelope<SLODefinition>>(ENDPOINTS.SLOS.LIST, payload));
  },
  evaluateSLO(id: UUID) {
    return data(() => apiClient.post<ApiEnvelope<SLAComplianceRecord>>(ENDPOINTS.SLOS.EVALUATE(id), {}));
  },
  listComplianceRecords(query: ListQuery = {}) {
    return page(() => apiClient.get<ApiEnvelope<readonly SLAComplianceRecord[]>>(
      withQuery(ENDPOINTS.COMPLIANCE_RECORDS.LIST, queryValues(query)),
    ));
  },
  getHealth() {
    return data(() => apiClient.get<ApiEnvelope<HealthCheck>>(ENDPOINTS.HEALTH));
  },
};

type Severity = Alert['severity'];
