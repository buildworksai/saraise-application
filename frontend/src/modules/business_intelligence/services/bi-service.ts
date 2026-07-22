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

const queryString = (filters: ListFilters = {}): string => {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
};

const unwrap = <T>(envelope: ApiEnvelope<T>): T => envelope.data;
const unwrapPage = <T>(envelope: ApiEnvelope<T[]>): PageResult<T> => ({
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
});
const mutationInit = (idempotencyKey: string): RequestInit => ({
  headers: { "Idempotency-Key": idempotencyKey },
});
const getPage = async <T>(path: string, filters?: ListFilters): Promise<PageResult<T>> =>
  unwrapPage(await apiClient.get<ApiEnvelope<T[]>>(`${path}${queryString(filters)}`));
const transition = async <T>(
  path: string,
  request: TransitionRequest,
  idempotencyKey: string
): Promise<T> =>
  unwrap(await apiClient.post<ApiEnvelope<T>>(path, request, mutationInit(idempotencyKey)));

export const createIdempotencyKey = (): string =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
export const biQueryKeys = {
  datasets: (tenant: string, filters: ListFilters = {}) =>
    ["business-intelligence", tenant, "datasets", filters] as const,
  dataset: (tenant: string, key: string) =>
    ["business-intelligence", tenant, "dataset", key] as const,
  queries: (tenant: string, filters: ListFilters = {}) =>
    ["business-intelligence", tenant, "queries", filters] as const,
  query: (tenant: string, id: string) => ["business-intelligence", tenant, "query", id] as const,
  reports: (tenant: string, filters: ListFilters = {}) =>
    ["business-intelligence", tenant, "reports", filters] as const,
  report: (tenant: string, id: string) => ["business-intelligence", tenant, "report", id] as const,
  dashboards: (tenant: string, filters: ListFilters = {}) =>
    ["business-intelligence", tenant, "dashboards", filters] as const,
  dashboard: (tenant: string, id: string) =>
    ["business-intelligence", tenant, "dashboard", id] as const,
  widgets: (tenant: string, dashboardId: string, filters: ListFilters = {}) =>
    ["business-intelligence", tenant, "dashboard", dashboardId, "widgets", filters] as const,
  shares: (tenant: string, dashboardId: string, filters: ListFilters = {}) =>
    ["business-intelligence", tenant, "dashboard", dashboardId, "shares", filters] as const,
  executions: (tenant: string, filters: ListFilters = {}) =>
    ["business-intelligence", tenant, "executions", filters] as const,
  execution: (tenant: string, id: string) =>
    ["business-intelligence", tenant, "execution", id] as const,
  result: (tenant: string, id: string, filters: ListFilters = {}) =>
    ["business-intelligence", tenant, "execution", id, "result", filters] as const,
};

export const biService = {
  listDatasets: (filters?: ListFilters) =>
    getPage<DatasetSummary>(ENDPOINTS.DATASETS.LIST, filters),
  getDataset: async (key: string) =>
    unwrap(await apiClient.get<ApiEnvelope<DatasetDescriptor>>(ENDPOINTS.DATASETS.DETAIL(key))),

  listQueries: (filters?: ListFilters) => getPage<QueryListItem>(ENDPOINTS.QUERIES.LIST, filters),
  getQuery: async (id: string) =>
    unwrap(await apiClient.get<ApiEnvelope<QueryDetail>>(ENDPOINTS.QUERIES.DETAIL(id))),
  createQuery: async (data: QueryCreate, key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<QueryDetail>>(
        ENDPOINTS.QUERIES.CREATE,
        data,
        mutationInit(key)
      )
    ),
  updateQuery: async (id: string, data: QueryUpdate, key: string) =>
    unwrap(
      await apiClient.patch<ApiEnvelope<QueryDetail>>(
        ENDPOINTS.QUERIES.UPDATE(id),
        data,
        mutationInit(key)
      )
    ),
  deleteQuery: (id: string, key: string) =>
    apiClient.delete<void>(ENDPOINTS.QUERIES.DELETE(id), mutationInit(key)),
  validateQuery: async (id: string, parameters: ExecutionRequest = {}) =>
    unwrap(
      await apiClient.post<ApiEnvelope<QueryValidation>>(ENDPOINTS.QUERIES.VALIDATE(id), parameters)
    ),
  transitionQuery: (
    id: string,
    command: "publish" | "archive" | "restore",
    request: TransitionRequest,
    key: string
  ) =>
    transition<QueryDetail>(
      ENDPOINTS.QUERIES[command.toUpperCase() as "PUBLISH" | "ARCHIVE" | "RESTORE"](id),
      request,
      key
    ),
  executeQuery: async (id: string, request: ExecutionRequest, key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<EnqueueResult>>(
        ENDPOINTS.QUERIES.EXECUTE(id),
        request,
        mutationInit(key)
      )
    ),

  listReports: (filters?: ListFilters) => getPage<ReportListItem>(ENDPOINTS.REPORTS.LIST, filters),
  getReport: async (id: string) =>
    unwrap(await apiClient.get<ApiEnvelope<ReportDetail>>(ENDPOINTS.REPORTS.DETAIL(id))),
  createReport: async (data: ReportCreate, key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<ReportDetail>>(
        ENDPOINTS.REPORTS.CREATE,
        data,
        mutationInit(key)
      )
    ),
  updateReport: async (id: string, data: ReportUpdate, key: string) =>
    unwrap(
      await apiClient.patch<ApiEnvelope<ReportDetail>>(
        ENDPOINTS.REPORTS.UPDATE(id),
        data,
        mutationInit(key)
      )
    ),
  deleteReport: (id: string, key: string) =>
    apiClient.delete<void>(ENDPOINTS.REPORTS.DELETE(id), mutationInit(key)),
  transitionReport: (
    id: string,
    command: "publish" | "archive" | "restore",
    request: TransitionRequest,
    key: string
  ) =>
    transition<ReportDetail>(
      ENDPOINTS.REPORTS[command.toUpperCase() as "PUBLISH" | "ARCHIVE" | "RESTORE"](id),
      request,
      key
    ),
  executeReport: async (id: string, request: ExecutionRequest, key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<EnqueueResult>>(
        ENDPOINTS.REPORTS.EXECUTE(id),
        request,
        mutationInit(key)
      )
    ),

  listDashboards: (filters?: ListFilters) =>
    getPage<DashboardListItem>(ENDPOINTS.DASHBOARDS.LIST, filters),
  getDashboard: async (id: string) =>
    unwrap(await apiClient.get<ApiEnvelope<DashboardDetail>>(ENDPOINTS.DASHBOARDS.DETAIL(id))),
  createDashboard: async (data: DashboardCreate, key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<DashboardDetail>>(
        ENDPOINTS.DASHBOARDS.CREATE,
        data,
        mutationInit(key)
      )
    ),
  updateDashboard: async (id: string, data: DashboardUpdate, key: string) =>
    unwrap(
      await apiClient.patch<ApiEnvelope<DashboardDetail>>(
        ENDPOINTS.DASHBOARDS.UPDATE(id),
        data,
        mutationInit(key)
      )
    ),
  deleteDashboard: (id: string, key: string) =>
    apiClient.delete<void>(ENDPOINTS.DASHBOARDS.DELETE(id), mutationInit(key)),
  transitionDashboard: (
    id: string,
    command: "publish" | "archive" | "restore",
    request: TransitionRequest,
    key: string
  ) =>
    transition<DashboardDetail>(
      ENDPOINTS.DASHBOARDS[command.toUpperCase() as "PUBLISH" | "ARCHIVE" | "RESTORE"](id),
      request,
      key
    ),
  executeDashboard: async (id: string, request: ExecutionRequest, key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<EnqueueResult>>(
        ENDPOINTS.DASHBOARDS.EXECUTE(id),
        request,
        mutationInit(key)
      )
    ),
  listWidgets: (id: string, filters?: ListFilters) =>
    getPage<DashboardWidget>(ENDPOINTS.DASHBOARDS.WIDGETS(id), filters),
  getWidget: async (id: string, widgetId: string) =>
    unwrap(
      await apiClient.get<ApiEnvelope<DashboardWidget>>(
        ENDPOINTS.DASHBOARDS.WIDGET_DETAIL(id, widgetId)
      )
    ),
  addWidget: async (id: string, data: WidgetCreate, key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<DashboardWidget>>(
        ENDPOINTS.DASHBOARDS.WIDGETS(id),
        data,
        mutationInit(key)
      )
    ),
  updateWidget: async (id: string, widgetId: string, data: WidgetUpdate, key: string) =>
    unwrap(
      await apiClient.patch<ApiEnvelope<DashboardWidget>>(
        ENDPOINTS.DASHBOARDS.WIDGET_DETAIL(id, widgetId),
        data,
        mutationInit(key)
      )
    ),
  removeWidget: (id: string, widgetId: string, key: string) =>
    apiClient.delete<void>(ENDPOINTS.DASHBOARDS.WIDGET_DETAIL(id, widgetId), mutationInit(key)),
  reorderWidgets: async (id: string, version: number, widgets: WidgetReorderItem[], key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<DashboardWidget[]>>(
        ENDPOINTS.DASHBOARDS.WIDGET_REORDER(id),
        { version, widgets },
        mutationInit(key)
      )
    ),
  listShares: (id: string, filters?: ListFilters) =>
    getPage<DashboardShare>(ENDPOINTS.DASHBOARDS.SHARES(id), filters),
  createShare: async (id: string, data: ShareCreate, key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<DashboardShare>>(
        ENDPOINTS.DASHBOARDS.SHARES(id),
        data,
        mutationInit(key)
      )
    ),
  updateShare: async (id: string, shareId: string, data: ShareUpdate, key: string) =>
    unwrap(
      await apiClient.patch<ApiEnvelope<DashboardShare>>(
        ENDPOINTS.DASHBOARDS.SHARE_DETAIL(id, shareId),
        data,
        mutationInit(key)
      )
    ),
  revokeShare: (id: string, shareId: string, key: string) =>
    apiClient.delete<void>(ENDPOINTS.DASHBOARDS.SHARE_DETAIL(id, shareId), mutationInit(key)),

  listExecutions: (filters?: ListFilters) =>
    getPage<ExecutionListItem>(ENDPOINTS.EXECUTIONS.LIST, filters),
  getExecution: async (id: string) =>
    unwrap(await apiClient.get<ApiEnvelope<ExecutionDetail>>(ENDPOINTS.EXECUTIONS.DETAIL(id))),
  getExecutionResult: async (id: string, filters?: ListFilters) =>
    unwrap(
      await apiClient.get<ApiEnvelope<ExecutionResult>>(
        `${ENDPOINTS.EXECUTIONS.RESULT(id)}${queryString(filters)}`
      )
    ),
  cancelExecution: async (id: string, key: string) =>
    unwrap(
      await apiClient.post<ApiEnvelope<ExecutionDetail>>(
        ENDPOINTS.EXECUTIONS.CANCEL(id),
        {},
        mutationInit(key)
      )
    ),
  health: async () => unwrap(await apiClient.get<ApiEnvelope<HealthResponse>>(ENDPOINTS.HEALTH)),
};
