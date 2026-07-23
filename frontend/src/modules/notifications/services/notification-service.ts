/** Sole HTTP boundary for the governed notifications v2 API. */
import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type AffectedCountResult, type ApiSuccess, type BulkDeliveryCreateInput, type ConfigurationExport,
  type ConfigurationHistoryItem, type ConfigurationImportInput, type ConfigurationRollbackInput,
  type ConfigurationSimulationInput, type ConfigurationSimulationResult, type ConfigurationWriteInput,
  type DeliveryCancelInput, type DeliveryCreateInput, type DeliveryPreviewResult, type DeliveryQuery,
  type DeliveryRetryInput, type EndpointQuery, type EndpointRegisterInput, type EndpointUpdateInput,
  type EndpointVerifyResult, type InboxQuery, type InboxTransitionInput, type LivenessResult,
  type MarkAllReadInput, type Notification, type NotificationConfiguration, type NotificationDelivery,
  type NotificationDeliveryAttempt, type NotificationEndpoint, type NotificationEnvironment,
  type NotificationTemplate, type NotificationTemplateVersion,
  type PaginatedData, type PaginationMeta, type PreferenceMatrix, type PreferenceReplaceInput,
  type ReadinessResult, type TemplateCreateInput, type TemplatePreviewInput, type TemplatePreviewResult,
  type TemplateQuery, type TemplateRollbackInput, type TemplateTransitionInput,
  type TemplateVersionCreateInput, type UnreadCountResult,
} from "../contracts";

interface GovernedCollection<T> extends ApiSuccess<readonly T[]> { readonly meta: ApiSuccess<readonly T[]>["meta"] & { readonly pagination?: PaginationMeta } }

function malformed(message: string, correlationId?: string): ApiError {
  return new ApiError(message, 502, undefined, "MALFORMED_RESPONSE", correlationId);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function unwrap<T>(value: unknown): T {
  if (!isObject(value) || !("data" in value) || !isObject(value.meta) || typeof value.meta.correlation_id !== "string") {
    throw malformed("Notifications returned a malformed governed response.");
  }
  return value.data as T;
}

function unwrapPage<T>(value: unknown): PaginatedData<T> {
  if (!isObject(value) || !Array.isArray(value.data) || !isObject(value.meta) || typeof value.meta.correlation_id !== "string") {
    throw malformed("Notifications returned a malformed collection response.");
  }
  const envelope = value as unknown as GovernedCollection<T>;
  const paginationValue = envelope.meta.pagination;
  if (!paginationValue || typeof paginationValue.page !== "number" || typeof paginationValue.count !== "number" || typeof paginationValue.has_next !== "boolean" || typeof paginationValue.has_previous !== "boolean") {
    throw malformed("Notifications omitted governed pagination metadata.", envelope.meta.correlation_id);
  }
  return {
    items: envelope.data,
    pagination: paginationValue,
    meta: { correlation_id: envelope.meta.correlation_id, timestamp: envelope.meta.timestamp },
    capabilities: Array.isArray(envelope.capabilities) ? envelope.capabilities : [],
  };
}

export function notificationQuery(path: string, filters: object): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

const requestInit = (signal?: AbortSignal, key?: { name: "X-Idempotency-Key" | "X-Transition-Key"; value: string }): RequestInit => ({
  signal,
  headers: key ? { [key.name]: key.value } : undefined,
});
const getOne = async <T>(path: string, signal?: AbortSignal): Promise<T> => unwrap<T>(await apiClient.get<unknown>(path, requestInit(signal)));
const getPage = async <T>(path: string, filters: object, signal?: AbortSignal): Promise<PaginatedData<T>> => unwrapPage<T>(await apiClient.get<unknown>(notificationQuery(path, filters), requestInit(signal)));
const postOne = async <T>(path: string, input?: object, signal?: AbortSignal, key?: { name: "X-Idempotency-Key" | "X-Transition-Key"; value: string }): Promise<T> => unwrap<T>(await apiClient.post<unknown>(path, input, requestInit(signal, key)));

export const NOTIFICATION_QUERY_KEYS = {
  all: ["notifications"] as const,
  inbox: (query: InboxQuery = {}) => ["notifications", "inbox", query] as const,
  inboxItem: (id: string) => ["notifications", "inbox", id] as const,
  unread: ["notifications", "unread-count"] as const,
  preferences: ["notifications", "preferences"] as const,
  templates: (query: TemplateQuery = {}) => ["notifications", "templates", query] as const,
  template: (id: string) => ["notifications", "template", id] as const,
  deliveries: (query: DeliveryQuery = {}) => ["notifications", "deliveries", query] as const,
  delivery: (id: string) => ["notifications", "delivery", id] as const,
  endpoints: (query: EndpointQuery = {}) => ["notifications", "endpoints", query] as const,
  endpoint: (id: string) => ["notifications", "endpoint", id] as const,
  configuration: (environment: NotificationEnvironment) => ["notifications", "configuration", environment] as const,
  configurationHistory: (environment: NotificationEnvironment, page: number) => ["notifications", "configuration", environment, "history", page] as const,
  health: ["notifications", "health"] as const,
};

export const notificationService = {
  /** Compact aggregate used by the global notification bell. */
  getUnreadCount: async (): Promise<number> => (await getOne<UnreadCountResult>(ENDPOINTS.INBOX.UNREAD_COUNT)).count,
  inbox: {
    list: (query: InboxQuery = {}, signal?: AbortSignal) => getPage<Notification>(ENDPOINTS.INBOX.LIST, query, signal),
    get: (id: string, signal?: AbortSignal) => getOne<Notification>(ENDPOINTS.INBOX.DETAIL(id), signal),
    markRead: (id: string, input: InboxTransitionInput, signal?: AbortSignal) => postOne<Notification>(ENDPOINTS.INBOX.MARK_READ(id), input, signal, { name: "X-Transition-Key", value: input.transition_key }),
    markUnread: (id: string, input: InboxTransitionInput, signal?: AbortSignal) => postOne<Notification>(ENDPOINTS.INBOX.MARK_UNREAD(id), input, signal, { name: "X-Transition-Key", value: input.transition_key }),
    archive: (id: string, input: InboxTransitionInput, signal?: AbortSignal) => postOne<Notification>(ENDPOINTS.INBOX.ARCHIVE(id), input, signal, { name: "X-Transition-Key", value: input.transition_key }),
    markAllRead: (input: MarkAllReadInput, signal?: AbortSignal) => postOne<AffectedCountResult>(ENDPOINTS.INBOX.MARK_ALL_READ, input, signal, { name: "X-Transition-Key", value: input.transition_key }),
    unreadCount: (signal?: AbortSignal) => getOne<UnreadCountResult>(ENDPOINTS.INBOX.UNREAD_COUNT, signal),
  },
  templates: {
    list: (query: TemplateQuery = {}, signal?: AbortSignal) => getPage<NotificationTemplate>(ENDPOINTS.TEMPLATES.LIST, query, signal),
    create: (input: TemplateCreateInput, signal?: AbortSignal) => postOne<NotificationTemplate>(ENDPOINTS.TEMPLATES.LIST, input, signal, { name: "X-Idempotency-Key", value: crypto.randomUUID() }),
    get: (id: string, signal?: AbortSignal) => getOne<NotificationTemplate>(ENDPOINTS.TEMPLATES.DETAIL(id), signal),
    update: async (id: string, input: TemplateVersionCreateInput, signal?: AbortSignal): Promise<NotificationTemplate> => unwrap(await apiClient.patch<unknown>(ENDPOINTS.TEMPLATES.DETAIL(id), input, requestInit(signal))),
    archive: async (id: string, input: TemplateTransitionInput, signal?: AbortSignal): Promise<NotificationTemplate> => unwrap(await apiClient.delete<unknown>(ENDPOINTS.TEMPLATES.DETAIL(id), requestInit(signal, { name: "X-Transition-Key", value: input.transition_key }))),
    versions: (id: string, query: { readonly page?: number; readonly page_size?: number } = {}, signal?: AbortSignal) => getPage<NotificationTemplateVersion>(ENDPOINTS.TEMPLATES.VERSIONS(id), query, signal),
    createVersion: (id: string, input: TemplateVersionCreateInput, signal?: AbortSignal) => postOne<NotificationTemplateVersion>(ENDPOINTS.TEMPLATES.VERSIONS(id), input, signal),
    previewDraft: (input: TemplatePreviewInput, signal?: AbortSignal) => postOne<TemplatePreviewResult>(ENDPOINTS.TEMPLATES.PREVIEW_DRAFT, input, signal),
    preview: (id: string, input: TemplatePreviewInput, signal?: AbortSignal) => postOne<TemplatePreviewResult>(ENDPOINTS.TEMPLATES.PREVIEW(id), input, signal),
    activate: (id: string, input: TemplateTransitionInput, signal?: AbortSignal) => postOne<NotificationTemplate>(ENDPOINTS.TEMPLATES.ACTIVATE(id), input, signal, { name: "X-Transition-Key", value: input.transition_key }),
    restore: (id: string, input: TemplateTransitionInput, signal?: AbortSignal) => postOne<NotificationTemplate>(ENDPOINTS.TEMPLATES.RESTORE(id), input, signal, { name: "X-Transition-Key", value: input.transition_key }),
    rollback: (id: string, input: TemplateRollbackInput, signal?: AbortSignal) => postOne<NotificationTemplate>(ENDPOINTS.TEMPLATES.ROLLBACK(id), input, signal, { name: "X-Transition-Key", value: input.transition_key }),
  },
  deliveries: {
    list: (query: DeliveryQuery = {}, signal?: AbortSignal) => getPage<NotificationDelivery>(ENDPOINTS.DELIVERIES.LIST, query, signal),
    create: (input: DeliveryCreateInput, signal?: AbortSignal) => postOne<NotificationDelivery>(input.priority === 1 ? ENDPOINTS.DELIVERIES.URGENT : ENDPOINTS.DELIVERIES.LIST, input, signal, { name: "X-Idempotency-Key", value: input.idempotency_key }),
    bulk: (input: BulkDeliveryCreateInput, signal?: AbortSignal) => postOne<readonly NotificationDelivery[]>(ENDPOINTS.DELIVERIES.BULK, input, signal, { name: "X-Idempotency-Key", value: input.idempotency_key }),
    preview: (input: DeliveryCreateInput, signal?: AbortSignal) => postOne<DeliveryPreviewResult>(ENDPOINTS.DELIVERIES.PREVIEW, input, signal),
    get: (id: string, signal?: AbortSignal) => getOne<NotificationDelivery>(ENDPOINTS.DELIVERIES.DETAIL(id), signal),
    attempts: (id: string, query: { readonly page?: number; readonly page_size?: number } = {}, signal?: AbortSignal) => getPage<NotificationDeliveryAttempt>(ENDPOINTS.DELIVERIES.ATTEMPTS(id), query, signal),
    retry: (id: string, input: DeliveryRetryInput, signal?: AbortSignal) => postOne<NotificationDelivery>(ENDPOINTS.DELIVERIES.RETRY(id), input, signal, { name: "X-Idempotency-Key", value: input.idempotency_key }),
    cancel: (id: string, input: DeliveryCancelInput, signal?: AbortSignal) => postOne<NotificationDelivery>(ENDPOINTS.DELIVERIES.CANCEL(id), input, signal, { name: "X-Transition-Key", value: input.transition_key }),
  },
  preferences: {
    get: (signal?: AbortSignal) => getOne<PreferenceMatrix>(ENDPOINTS.PREFERENCES.ME, signal),
    replace: async (input: PreferenceReplaceInput, signal?: AbortSignal): Promise<PreferenceMatrix> => unwrap(await apiClient.put<unknown>(ENDPOINTS.PREFERENCES.ME, input, requestInit(signal))),
    reset: (signal?: AbortSignal) => postOne<PreferenceMatrix>(ENDPOINTS.PREFERENCES.RESET, undefined, signal),
  },
  endpoints: {
    list: (query: EndpointQuery = {}, signal?: AbortSignal) => getPage<NotificationEndpoint>(ENDPOINTS.ENDPOINTS.LIST, query, signal),
    register: (input: EndpointRegisterInput, signal?: AbortSignal) => postOne<NotificationEndpoint>(ENDPOINTS.ENDPOINTS.LIST, input, signal),
    get: (id: string, signal?: AbortSignal) => getOne<NotificationEndpoint>(ENDPOINTS.ENDPOINTS.DETAIL(id), signal),
    update: async (id: string, input: EndpointUpdateInput, signal?: AbortSignal): Promise<NotificationEndpoint> => unwrap(await apiClient.patch<unknown>(ENDPOINTS.ENDPOINTS.DETAIL(id), input, requestInit(signal))),
    revoke: async (id: string, signal?: AbortSignal): Promise<NotificationEndpoint | undefined> => {
      const response = await apiClient.delete<unknown>(ENDPOINTS.ENDPOINTS.DETAIL(id), requestInit(signal));
      return response === undefined ? undefined : unwrap<NotificationEndpoint>(response);
    },
    verify: (id: string, signal?: AbortSignal) => postOne<EndpointVerifyResult>(ENDPOINTS.ENDPOINTS.VERIFY(id), undefined, signal),
  },
  configuration: {
    get: (environment: NotificationEnvironment, signal?: AbortSignal) => getOne<NotificationConfiguration>(ENDPOINTS.CONFIGURATION.DETAIL(environment), signal),
    update: async (environment: NotificationEnvironment, input: ConfigurationWriteInput, signal?: AbortSignal): Promise<NotificationConfiguration> => unwrap(await apiClient.patch<unknown>(ENDPOINTS.CONFIGURATION.DETAIL(environment), input, requestInit(signal))),
    simulate: (environment: NotificationEnvironment, input: ConfigurationSimulationInput, signal?: AbortSignal) => postOne<ConfigurationSimulationResult>(ENDPOINTS.CONFIGURATION.SIMULATE(environment), input, signal),
    history: (environment: NotificationEnvironment, query: { readonly page?: number; readonly page_size?: number } = {}, signal?: AbortSignal) => getPage<ConfigurationHistoryItem>(ENDPOINTS.CONFIGURATION.HISTORY(environment), query, signal),
    rollback: (environment: NotificationEnvironment, input: ConfigurationRollbackInput, signal?: AbortSignal) => postOne<NotificationConfiguration>(ENDPOINTS.CONFIGURATION.ROLLBACK(environment), input, signal),
    importDocument: (environment: NotificationEnvironment, input: ConfigurationImportInput, signal?: AbortSignal) => postOne<NotificationConfiguration | ConfigurationSimulationResult>(ENDPOINTS.CONFIGURATION.IMPORT(environment), input, signal),
    exportDocument: (environment: NotificationEnvironment, signal?: AbortSignal) => getOne<ConfigurationExport>(ENDPOINTS.CONFIGURATION.EXPORT(environment), signal),
  },
  health: {
    live: (signal?: AbortSignal) => getOne<LivenessResult>(ENDPOINTS.HEALTH.LIVE, signal),
    ready: (signal?: AbortSignal) => getOne<ReadinessResult>(ENDPOINTS.HEALTH.READY, signal),
  },
} as const;

// Named exports keep shell integrations (for example NotificationBell) source-compatible.
export type { Notification, NotificationPreference } from "../contracts";
