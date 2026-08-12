import { apiClient } from "@/services/api-client";
import type {
  ApiEnvelope,
  DashboardCreate,
  DashboardDetail,
  DashboardListItem,
  DashboardShare,
  DashboardUpdate,
  DatasetDescriptor,
  DatasetSummary,
  EnqueueResult,
  ExecutionDetail,
  ExecutionListItem,
  ExecutionRequest,
  ExecutionResult,
  HealthResponse,
  ListFilters,
  PageResult,
  QueryCreate,
  QueryDetail,
  QueryListItem,
  QueryUpdate,
  QueryValidation,
  ReportCreate,
  ReportDetail,
  ReportListItem,
  ReportUpdate,
  ShareCreate,
  ShareUpdate,
  TransitionRequest,
  WidgetCreate,
  DashboardWidget,
  WidgetReorderItem,
  WidgetUpdate,
} from "../contracts";
import { ENDPOINTS } from "../contracts";

function queryString(filters: ListFilters = {}): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

function unwrap<T>(envelope: ApiEnvelope<T>): T {
  return envelope.data;
}

function unwrapPage<T>(envelope: ApiEnvelope<T[]>): PageResult<T> {
  return {
    items: envelope.data,
    meta: envelope.meta.pagination ?? {
      count: envelope.data.length,
      page: 1,
      page_size: envelope.data.length,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
    correlationId: envelope.meta.correlation_id,
  };
}

function mutationInit(idempotencyKey: string): RequestInit {
  return {
    headers: { "Idempotency-Key": idempotencyKey },
  };
}

async function getPage<T>(path: string, filters?: ListFilters): Promise<PageResult<T>> {
  return unwrapPage(await apiClient.get<ApiEnvelope<T[]>>(`${path}${queryString(filters)}`));
}

async function transition<T>(
  path: string,
  request: TransitionRequest,
  idempotencyKey: string
): Promise<T> {
  return unwrap(await apiClient.post<ApiEnvelope<T>>(path, request, mutationInit(idempotencyKey)));
}

export function createIdempotencyKey(): string {
  return (
    globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
  );
}

class BusinessIntelligenceQueryKeys {
  datasets(tenant: string, filters: ListFilters = {}) {
    return ["business-intelligence", tenant, "datasets", filters] as const;
  }

  dataset(tenant: string, key: string) {
    return ["business-intelligence", tenant, "dataset", key] as const;
  }

  queries(tenant: string, filters: ListFilters = {}) {
    return ["business-intelligence", tenant, "queries", filters] as const;
  }

  query(tenant: string, id: string) {
    return ["business-intelligence", tenant, "query", id] as const;
  }

  reports(tenant: string, filters: ListFilters = {}) {
    return ["business-intelligence", tenant, "reports", filters] as const;
  }

  report(tenant: string, id: string) {
    return ["business-intelligence", tenant, "report", id] as const;
  }

  dashboards(tenant: string, filters: ListFilters = {}) {
    return ["business-intelligence", tenant, "dashboards", filters] as const;
  }

  dashboard(tenant: string, id: string) {
    return ["business-intelligence", tenant, "dashboard", id] as const;
  }

  widgets(tenant: string, dashboardId: string, filters: ListFilters = {}) {
    return ["business-intelligence", tenant, "dashboard", dashboardId, "widgets", filters] as const;
  }

  shares(tenant: string, dashboardId: string, filters: ListFilters = {}) {
    return ["business-intelligence", tenant, "dashboard", dashboardId, "shares", filters] as const;
  }

  executions(tenant: string, filters: ListFilters = {}) {
    return ["business-intelligence", tenant, "executions", filters] as const;
  }

  execution(tenant: string, id: string) {
    return ["business-intelligence", tenant, "execution", id] as const;
  }

  result(tenant: string, id: string, filters: ListFilters = {}) {
    return ["business-intelligence", tenant, "execution", id, "result", filters] as const;
  }
}

export const biQueryKeys = new BusinessIntelligenceQueryKeys();

class BusinessIntelligenceService {
  listDatasets(filters?: ListFilters) {
    return getPage<DatasetSummary>(ENDPOINTS.DATASETS.LIST, filters);
  }

  async getDataset(key: string) {
    return unwrap(
      await apiClient.get<ApiEnvelope<DatasetDescriptor>>(ENDPOINTS.DATASETS.DETAIL(key))
    );
  }

  listQueries(filters?: ListFilters) {
    return getPage<QueryListItem>(ENDPOINTS.QUERIES.LIST, filters);
  }

  async getQuery(id: string) {
    return unwrap(await apiClient.get<ApiEnvelope<QueryDetail>>(ENDPOINTS.QUERIES.DETAIL(id)));
  }

  async createQuery(data: QueryCreate, key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<QueryDetail>>(
        ENDPOINTS.QUERIES.CREATE,
        data,
        mutationInit(key)
      )
    );
  }

  async updateQuery(id: string, data: QueryUpdate, key: string) {
    return unwrap(
      await apiClient.patch<ApiEnvelope<QueryDetail>>(
        ENDPOINTS.QUERIES.UPDATE(id),
        data,
        mutationInit(key)
      )
    );
  }

  deleteQuery(id: string, key: string) {
    return apiClient.delete<void>(ENDPOINTS.QUERIES.DELETE(id), mutationInit(key));
  }

  async validateQuery(id: string, parameters: ExecutionRequest = {}) {
    return unwrap(
      await apiClient.post<ApiEnvelope<QueryValidation>>(ENDPOINTS.QUERIES.VALIDATE(id), parameters)
    );
  }

  transitionQuery(
    id: string,
    command: "publish" | "archive" | "restore",
    request: TransitionRequest,
    key: string
  ) {
    return transition<QueryDetail>(
      ENDPOINTS.QUERIES[command.toUpperCase() as "PUBLISH" | "ARCHIVE" | "RESTORE"](id),
      request,
      key
    );
  }

  async executeQuery(id: string, request: ExecutionRequest, key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<EnqueueResult>>(
        ENDPOINTS.QUERIES.EXECUTE(id),
        request,
        mutationInit(key)
      )
    );
  }

  listReports(filters?: ListFilters) {
    return getPage<ReportListItem>(ENDPOINTS.REPORTS.LIST, filters);
  }

  async getReport(id: string) {
    return unwrap(await apiClient.get<ApiEnvelope<ReportDetail>>(ENDPOINTS.REPORTS.DETAIL(id)));
  }

  async createReport(data: ReportCreate, key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<ReportDetail>>(
        ENDPOINTS.REPORTS.CREATE,
        data,
        mutationInit(key)
      )
    );
  }

  async updateReport(id: string, data: ReportUpdate, key: string) {
    return unwrap(
      await apiClient.patch<ApiEnvelope<ReportDetail>>(
        ENDPOINTS.REPORTS.UPDATE(id),
        data,
        mutationInit(key)
      )
    );
  }

  deleteReport(id: string, key: string) {
    return apiClient.delete<void>(ENDPOINTS.REPORTS.DELETE(id), mutationInit(key));
  }

  transitionReport(
    id: string,
    command: "publish" | "archive" | "restore",
    request: TransitionRequest,
    key: string
  ) {
    return transition<ReportDetail>(
      ENDPOINTS.REPORTS[command.toUpperCase() as "PUBLISH" | "ARCHIVE" | "RESTORE"](id),
      request,
      key
    );
  }

  async executeReport(id: string, request: ExecutionRequest, key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<EnqueueResult>>(
        ENDPOINTS.REPORTS.EXECUTE(id),
        request,
        mutationInit(key)
      )
    );
  }

  listDashboards(filters?: ListFilters) {
    return getPage<DashboardListItem>(ENDPOINTS.DASHBOARDS.LIST, filters);
  }

  async getDashboard(id: string) {
    return unwrap(
      await apiClient.get<ApiEnvelope<DashboardDetail>>(ENDPOINTS.DASHBOARDS.DETAIL(id))
    );
  }

  async createDashboard(data: DashboardCreate, key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<DashboardDetail>>(
        ENDPOINTS.DASHBOARDS.CREATE,
        data,
        mutationInit(key)
      )
    );
  }

  async updateDashboard(id: string, data: DashboardUpdate, key: string) {
    return unwrap(
      await apiClient.patch<ApiEnvelope<DashboardDetail>>(
        ENDPOINTS.DASHBOARDS.UPDATE(id),
        data,
        mutationInit(key)
      )
    );
  }

  deleteDashboard(id: string, key: string) {
    return apiClient.delete<void>(ENDPOINTS.DASHBOARDS.DELETE(id), mutationInit(key));
  }

  transitionDashboard(
    id: string,
    command: "publish" | "archive" | "restore",
    request: TransitionRequest,
    key: string
  ) {
    return transition<DashboardDetail>(
      ENDPOINTS.DASHBOARDS[command.toUpperCase() as "PUBLISH" | "ARCHIVE" | "RESTORE"](id),
      request,
      key
    );
  }

  async executeDashboard(id: string, request: ExecutionRequest, key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<EnqueueResult>>(
        ENDPOINTS.DASHBOARDS.EXECUTE(id),
        request,
        mutationInit(key)
      )
    );
  }

  listWidgets(id: string, filters?: ListFilters) {
    return getPage<DashboardWidget>(ENDPOINTS.DASHBOARDS.WIDGETS(id), filters);
  }

  async getWidget(id: string, widgetId: string) {
    return unwrap(
      await apiClient.get<ApiEnvelope<DashboardWidget>>(
        ENDPOINTS.DASHBOARDS.WIDGET_DETAIL(id, widgetId)
      )
    );
  }

  async addWidget(id: string, data: WidgetCreate, key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<DashboardWidget>>(
        ENDPOINTS.DASHBOARDS.WIDGETS(id),
        data,
        mutationInit(key)
      )
    );
  }

  async updateWidget(id: string, widgetId: string, data: WidgetUpdate, key: string) {
    return unwrap(
      await apiClient.patch<ApiEnvelope<DashboardWidget>>(
        ENDPOINTS.DASHBOARDS.WIDGET_DETAIL(id, widgetId),
        data,
        mutationInit(key)
      )
    );
  }

  removeWidget(id: string, widgetId: string, key: string) {
    return apiClient.delete<void>(
      ENDPOINTS.DASHBOARDS.WIDGET_DETAIL(id, widgetId),
      mutationInit(key)
    );
  }

  async reorderWidgets(id: string, version: number, widgets: WidgetReorderItem[], key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<DashboardWidget[]>>(
        ENDPOINTS.DASHBOARDS.WIDGET_REORDER(id),
        { version, widgets },
        mutationInit(key)
      )
    );
  }

  listShares(id: string, filters?: ListFilters) {
    return getPage<DashboardShare>(ENDPOINTS.DASHBOARDS.SHARES(id), filters);
  }

  async createShare(id: string, data: ShareCreate, key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<DashboardShare>>(
        ENDPOINTS.DASHBOARDS.SHARES(id),
        data,
        mutationInit(key)
      )
    );
  }

  async updateShare(id: string, shareId: string, data: ShareUpdate, key: string) {
    return unwrap(
      await apiClient.patch<ApiEnvelope<DashboardShare>>(
        ENDPOINTS.DASHBOARDS.SHARE_DETAIL(id, shareId),
        data,
        mutationInit(key)
      )
    );
  }

  revokeShare(id: string, shareId: string, key: string) {
    return apiClient.delete<void>(
      ENDPOINTS.DASHBOARDS.SHARE_DETAIL(id, shareId),
      mutationInit(key)
    );
  }

  listExecutions(filters?: ListFilters) {
    return getPage<ExecutionListItem>(ENDPOINTS.EXECUTIONS.LIST, filters);
  }

  async getExecution(id: string) {
    return unwrap(
      await apiClient.get<ApiEnvelope<ExecutionDetail>>(ENDPOINTS.EXECUTIONS.DETAIL(id))
    );
  }

  async getExecutionResult(id: string, filters?: ListFilters) {
    return unwrap(
      await apiClient.get<ApiEnvelope<ExecutionResult>>(
        `${ENDPOINTS.EXECUTIONS.RESULT(id)}${queryString(filters)}`
      )
    );
  }

  async cancelExecution(id: string, key: string) {
    return unwrap(
      await apiClient.post<ApiEnvelope<ExecutionDetail>>(
        ENDPOINTS.EXECUTIONS.CANCEL(id),
        {},
        mutationInit(key)
      )
    );
  }

  async health() {
    return unwrap(await apiClient.get<ApiEnvelope<HealthResponse>>(ENDPOINTS.HEALTH));
  }
}

export const biService = new BusinessIntelligenceService();
