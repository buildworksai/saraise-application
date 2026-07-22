import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ConditionDescriptorDTO,
  type DefinitionValidationResultDTO,
  type GovernedEnvelope,
  type HandlerDescriptorDTO,
  type InstanceFilters,
  type LookupOptionDTO,
  type PaginatedResult,
  type StableApiErrorBody,
  type SubjectResolverDescriptorDTO,
  type TaskFilters,
  type UUID,
  type WorkflowCloneDTO,
  type WorkflowCreateDTO,
  type WorkflowDetailDTO,
  type WorkflowFilters,
  type WorkflowInstanceCancelDTO,
  type WorkflowInstanceDetailDTO,
  type WorkflowInstanceListDTO,
  type WorkflowInstanceStartDTO,
  type WorkflowListDTO,
  type WorkflowPublishDTO,
  type WorkflowTaskCompleteDTO,
  type WorkflowTaskDetailDTO,
  type WorkflowTaskListDTO,
  type WorkflowTaskRejectDTO,
  type WorkflowUpdateDTO,
} from "../contracts";

export class WorkflowApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
    readonly fieldErrors: readonly { readonly field: string; readonly code: string; readonly message: string }[],
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = "WorkflowApiError";
  }
}

function isObject(value: unknown): value is Readonly<Record<string, unknown>> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseGoverned(error: ApiError): StableApiErrorBody["error"] | null {
  if (!isObject(error.details) || !isObject(error.details.error)) return null;
  const body = error.details.error;
  if (typeof body.code !== "string" || typeof body.message !== "string" || typeof body.correlation_id !== "string") return null;
  const detail = isObject(body.detail) ? body.detail : {};
  const fieldErrors = Array.isArray(detail.field_errors)
    ? detail.field_errors.flatMap((item) => isObject(item) && typeof item.field === "string" && typeof item.code === "string" && typeof item.message === "string" ? [{ field: item.field, code: item.code, message: item.message }] : [])
    : [];
  return { code: body.code, message: body.message, correlation_id: body.correlation_id, detail: { field_errors: fieldErrors, retryable: detail.retryable === true } };
}

async function call<T>(operation: () => Promise<T>): Promise<T> {
  try { return await operation(); }
  catch (error) {
    if (!(error instanceof ApiError)) throw error;
    const governed = parseGoverned(error);
    throw new WorkflowApiError(governed?.message ?? error.message, error.status, governed?.code ?? error.code ?? "request_failed", governed?.correlation_id ?? error.correlationId ?? null, governed?.detail.field_errors ?? [], governed?.detail.retryable ?? error.status >= 500);
  }
}

function withQuery(path: string, values: object): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== undefined && value !== "") query.set(key, String(value));
  const encoded = query.toString();
  return encoded ? `${path}?${encoded}` : path;
}

async function data<T>(operation: () => Promise<GovernedEnvelope<T>>): Promise<T> { return (await call(operation)).data; }
async function page<T>(operation: () => Promise<GovernedEnvelope<readonly T[]>>): Promise<PaginatedResult<T>> {
  const envelope = await call(operation);
  if (!envelope.meta.pagination) throw new WorkflowApiError("The API response omitted pagination evidence.", 502, "invalid_response", envelope.meta.correlation_id, [], false);
  return { items: envelope.data, pagination: envelope.meta.pagination, correlationId: envelope.meta.correlation_id, receivedAt: envelope.meta.timestamp };
}

export const workflowService = {
  workflows: {
    list: (filters: WorkflowFilters = {}) => page(() => apiClient.get<GovernedEnvelope<readonly WorkflowListDTO[]>>(withQuery(ENDPOINTS.WORKFLOWS.LIST, filters))),
    get: (id: UUID) => data(() => apiClient.get<GovernedEnvelope<WorkflowDetailDTO>>(ENDPOINTS.WORKFLOWS.DETAIL(id))),
    create: (request: WorkflowCreateDTO) => data(() => apiClient.post<GovernedEnvelope<WorkflowDetailDTO>>(ENDPOINTS.WORKFLOWS.CREATE, request)),
    update: (id: UUID, request: WorkflowUpdateDTO) => data(() => apiClient.patch<GovernedEnvelope<WorkflowDetailDTO>>(ENDPOINTS.WORKFLOWS.UPDATE(id), request)),
    delete: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.WORKFLOWS.DELETE(id))),
    validate: (request: WorkflowCreateDTO) => data(() => apiClient.post<GovernedEnvelope<DefinitionValidationResultDTO>>(ENDPOINTS.WORKFLOWS.VALIDATE, request)),
    publish: (id: UUID, request: WorkflowPublishDTO) => data(() => apiClient.post<GovernedEnvelope<WorkflowDetailDTO>>(ENDPOINTS.WORKFLOWS.PUBLISH(id), request)),
    archive: (id: UUID, request: WorkflowPublishDTO) => data(() => apiClient.post<GovernedEnvelope<WorkflowDetailDTO>>(ENDPOINTS.WORKFLOWS.ARCHIVE(id), request)),
    clone: (id: UUID, request: WorkflowCloneDTO = {}) => data(() => apiClient.post<GovernedEnvelope<WorkflowDetailDTO>>(ENDPOINTS.WORKFLOWS.CLONE(id), request)),
  },
  instances: {
    list: (filters: InstanceFilters = {}) => page(() => apiClient.get<GovernedEnvelope<readonly WorkflowInstanceListDTO[]>>(withQuery(ENDPOINTS.INSTANCES.LIST, filters))),
    get: (id: UUID) => data(() => apiClient.get<GovernedEnvelope<WorkflowInstanceDetailDTO>>(ENDPOINTS.INSTANCES.DETAIL(id))),
    start: (request: WorkflowInstanceStartDTO) => data(() => apiClient.post<GovernedEnvelope<WorkflowInstanceDetailDTO>>(ENDPOINTS.INSTANCES.START, request)),
    cancel: (id: UUID, request: WorkflowInstanceCancelDTO) => data(() => apiClient.post<GovernedEnvelope<WorkflowInstanceDetailDTO>>(ENDPOINTS.INSTANCES.CANCEL(id), request)),
  },
  tasks: {
    list: (filters: TaskFilters = {}) => page(() => apiClient.get<GovernedEnvelope<readonly WorkflowTaskListDTO[]>>(withQuery(ENDPOINTS.TASKS.LIST, filters))),
    get: (id: UUID) => data(() => apiClient.get<GovernedEnvelope<WorkflowTaskDetailDTO>>(ENDPOINTS.TASKS.DETAIL(id))),
    complete: (id: UUID, request: WorkflowTaskCompleteDTO) => data(() => apiClient.post<GovernedEnvelope<WorkflowTaskDetailDTO>>(ENDPOINTS.TASKS.COMPLETE(id), request)),
    reject: (id: UUID, request: WorkflowTaskRejectDTO) => data(() => apiClient.post<GovernedEnvelope<WorkflowTaskDetailDTO>>(ENDPOINTS.TASKS.REJECT(id), request)),
  },
  catalog: {
    actions: () => data(() => apiClient.get<GovernedEnvelope<readonly HandlerDescriptorDTO[]>>(ENDPOINTS.CATALOG.ACTIONS)),
    conditions: () => data(() => apiClient.get<GovernedEnvelope<readonly ConditionDescriptorDTO[]>>(ENDPOINTS.CATALOG.CONDITIONS)),
    subjects: () => data(() => apiClient.get<GovernedEnvelope<readonly SubjectResolverDescriptorDTO[]>>(ENDPOINTS.CATALOG.SUBJECTS)),
    assignees: (search = "") => data(() => apiClient.get<GovernedEnvelope<readonly LookupOptionDTO[]>>(withQuery(ENDPOINTS.CATALOG.ASSIGNEES, { search }))),
    lookup: (key: string, search = "") => data(() => apiClient.get<GovernedEnvelope<readonly LookupOptionDTO[]>>(withQuery(ENDPOINTS.CATALOG.LOOKUP(key), { search }))),
  },
};
