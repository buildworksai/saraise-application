import { apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type APIEnvelope,
  type DefinitionCreateRequest,
  type DefinitionDetailDTO,
  type DefinitionFilters,
  type DefinitionListDTO,
  type DefinitionUpdateRequest,
  type EdgeCreateRequest,
  type EdgeUpdateRequest,
  type GraphValidationResult,
  type HealthCheckDTO,
  type NodeCreateRequest,
  type NodeDescriptorDTO,
  type NodeUpdateRequest,
  type OrchestrationEdgeDTO,
  type OrchestrationEventDTO,
  type OrchestrationNodeDTO,
  type OrchestrationNodeListDTO,
  type OrchestrationScheduleDetailDTO,
  type OrchestrationScheduleListDTO,
  type PageResult,
  type RunControlRequest,
  type RunDetailDTO,
  type RunFilters,
  type RunListDTO,
  type RunRetryRequest,
  type RunStartRequest,
  type ScheduleCreateRequest,
  type ScheduleFilters,
  type ScheduleUpdateRequest,
  type TaskRetryRequest,
  type TaskRunDetailDTO,
  type TaskRunFilters,
  type TaskRunListDTO,
} from "../contracts";

type QueryScalar = string | number | boolean | undefined;
type QueryValues = Readonly<Record<string, QueryScalar>>;

function withQuery(path: string, values: QueryValues): string {
  const search = new URLSearchParams();
  for (const key of Object.keys(values)) {
    const value = values[key];
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

function unwrap<T>(envelope: APIEnvelope<T>): T {
  return envelope.data;
}

function unwrapPage<T>(envelope: APIEnvelope<readonly T[]>): PageResult<T> {
  if (!envelope.meta.pagination) {
    throw new Error("The orchestration API returned a list without pagination metadata.");
  }
  return {
    items: envelope.data,
    pagination: envelope.meta.pagination,
    correlationId: envelope.meta.correlation_id,
    receivedAt: envelope.meta.timestamp,
  };
}

async function remove(path: string): Promise<void> {
  await apiClient.delete<void>(path);
}

export const automationOrchestrationService = {
  async listDefinitions(filters: DefinitionFilters = {}): Promise<PageResult<DefinitionListDTO>> {
    const envelope = await apiClient.get<APIEnvelope<readonly DefinitionListDTO[]>>(
      withQuery(ENDPOINTS.DEFINITIONS.LIST, filters),
    );
    return unwrapPage(envelope);
  },

  async createDefinition(data: DefinitionCreateRequest): Promise<DefinitionDetailDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<DefinitionDetailDTO>>(ENDPOINTS.DEFINITIONS.CREATE, data),
    );
  },

  async getDefinition(id: string): Promise<DefinitionDetailDTO> {
    return unwrap(await apiClient.get<APIEnvelope<DefinitionDetailDTO>>(ENDPOINTS.DEFINITIONS.DETAIL(id)));
  },

  async updateDefinition(id: string, data: DefinitionUpdateRequest): Promise<DefinitionDetailDTO> {
    return unwrap(
      await apiClient.patch<APIEnvelope<DefinitionDetailDTO>>(ENDPOINTS.DEFINITIONS.UPDATE(id), data),
    );
  },

  deleteDefinition(id: string): Promise<void> {
    return remove(ENDPOINTS.DEFINITIONS.DELETE(id));
  },

  async validateDefinition(id: string): Promise<GraphValidationResult> {
    return unwrap(
      await apiClient.post<APIEnvelope<GraphValidationResult>>(ENDPOINTS.DEFINITIONS.VALIDATE(id), {}),
    );
  },

  async publishDefinition(id: string, transitionKey: string): Promise<DefinitionDetailDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<DefinitionDetailDTO>>(ENDPOINTS.DEFINITIONS.PUBLISH(id), {
        transition_key: transitionKey,
      }),
    );
  },

  async cloneDefinition(id: string): Promise<DefinitionDetailDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<DefinitionDetailDTO>>(ENDPOINTS.DEFINITIONS.CLONE(id), {}),
    );
  },

  async retireDefinition(id: string, transitionKey: string): Promise<DefinitionDetailDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<DefinitionDetailDTO>>(ENDPOINTS.DEFINITIONS.RETIRE(id), {
        transition_key: transitionKey,
      }),
    );
  },

  async getDefinitionSnapshot(id: string): Promise<DefinitionDetailDTO> {
    return unwrap(await apiClient.get<APIEnvelope<DefinitionDetailDTO>>(ENDPOINTS.DEFINITIONS.SNAPSHOT(id)));
  },

  async listNodes(definitionId: string): Promise<PageResult<OrchestrationNodeListDTO>> {
    return unwrapPage(
      await apiClient.get<APIEnvelope<readonly OrchestrationNodeListDTO[]>>(
        ENDPOINTS.DEFINITIONS.NODES(definitionId),
      ),
    );
  },

  async createNode(definitionId: string, data: NodeCreateRequest): Promise<OrchestrationNodeDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<OrchestrationNodeDTO>>(
        ENDPOINTS.DEFINITIONS.NODES(definitionId),
        data,
      ),
    );
  },

  async getNode(id: string): Promise<OrchestrationNodeDTO> {
    return unwrap(await apiClient.get<APIEnvelope<OrchestrationNodeDTO>>(ENDPOINTS.NODES.DETAIL(id)));
  },

  async updateNode(id: string, data: NodeUpdateRequest): Promise<OrchestrationNodeDTO> {
    return unwrap(
      await apiClient.patch<APIEnvelope<OrchestrationNodeDTO>>(ENDPOINTS.NODES.UPDATE(id), data),
    );
  },

  deleteNode(id: string): Promise<void> {
    return remove(ENDPOINTS.NODES.DELETE(id));
  },

  async listEdges(definitionId: string): Promise<PageResult<OrchestrationEdgeDTO>> {
    return unwrapPage(
      await apiClient.get<APIEnvelope<readonly OrchestrationEdgeDTO[]>>(
        ENDPOINTS.DEFINITIONS.EDGES(definitionId),
      ),
    );
  },

  async createEdge(definitionId: string, data: EdgeCreateRequest): Promise<OrchestrationEdgeDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<OrchestrationEdgeDTO>>(
        ENDPOINTS.DEFINITIONS.EDGES(definitionId),
        data,
      ),
    );
  },

  async getEdge(id: string): Promise<OrchestrationEdgeDTO> {
    return unwrap(await apiClient.get<APIEnvelope<OrchestrationEdgeDTO>>(ENDPOINTS.EDGES.DETAIL(id)));
  },

  async updateEdge(id: string, data: EdgeUpdateRequest): Promise<OrchestrationEdgeDTO> {
    return unwrap(
      await apiClient.patch<APIEnvelope<OrchestrationEdgeDTO>>(ENDPOINTS.EDGES.UPDATE(id), data),
    );
  },

  deleteEdge(id: string): Promise<void> {
    return remove(ENDPOINTS.EDGES.DELETE(id));
  },

  async listSchedules(filters: ScheduleFilters = {}): Promise<PageResult<OrchestrationScheduleListDTO>> {
    const envelope = await apiClient.get<APIEnvelope<readonly OrchestrationScheduleListDTO[]>>(
      withQuery(ENDPOINTS.SCHEDULES.LIST, filters),
    );
    return unwrapPage(envelope);
  },

  async createSchedule(data: ScheduleCreateRequest): Promise<OrchestrationScheduleDetailDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<OrchestrationScheduleDetailDTO>>(ENDPOINTS.SCHEDULES.CREATE, data),
    );
  },

  async getSchedule(id: string): Promise<OrchestrationScheduleDetailDTO> {
    return unwrap(
      await apiClient.get<APIEnvelope<OrchestrationScheduleDetailDTO>>(ENDPOINTS.SCHEDULES.DETAIL(id)),
    );
  },

  async updateSchedule(id: string, data: ScheduleUpdateRequest): Promise<OrchestrationScheduleDetailDTO> {
    return unwrap(
      await apiClient.patch<APIEnvelope<OrchestrationScheduleDetailDTO>>(ENDPOINTS.SCHEDULES.UPDATE(id), data),
    );
  },

  deleteSchedule(id: string): Promise<void> {
    return remove(ENDPOINTS.SCHEDULES.DELETE(id));
  },

  async pauseSchedule(id: string, transitionKey: string): Promise<OrchestrationScheduleDetailDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<OrchestrationScheduleDetailDTO>>(ENDPOINTS.SCHEDULES.PAUSE(id), {
        transition_key: transitionKey,
      }),
    );
  },

  async resumeSchedule(id: string, transitionKey: string): Promise<OrchestrationScheduleDetailDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<OrchestrationScheduleDetailDTO>>(ENDPOINTS.SCHEDULES.RESUME(id), {
        transition_key: transitionKey,
      }),
    );
  },

  async retireSchedule(id: string, transitionKey: string): Promise<OrchestrationScheduleDetailDTO> {
    return unwrap(
      await apiClient.post<APIEnvelope<OrchestrationScheduleDetailDTO>>(ENDPOINTS.SCHEDULES.RETIRE(id), {
        transition_key: transitionKey,
      }),
    );
  },

  async listRuns(filters: RunFilters = {}): Promise<PageResult<RunListDTO>> {
    const envelope = await apiClient.get<APIEnvelope<readonly RunListDTO[]>>(
      withQuery(ENDPOINTS.RUNS.LIST, filters),
    );
    return unwrapPage(envelope);
  },

  async startRun(data: RunStartRequest): Promise<RunDetailDTO> {
    return unwrap(await apiClient.post<APIEnvelope<RunDetailDTO>>(ENDPOINTS.RUNS.START, data));
  },

  async getRun(id: string): Promise<RunDetailDTO> {
    return unwrap(await apiClient.get<APIEnvelope<RunDetailDTO>>(ENDPOINTS.RUNS.DETAIL(id)));
  },

  async pauseRun(id: string, data: RunControlRequest): Promise<RunDetailDTO> {
    return unwrap(await apiClient.post<APIEnvelope<RunDetailDTO>>(ENDPOINTS.RUNS.PAUSE(id), data));
  },

  async resumeRun(id: string, data: RunControlRequest): Promise<RunDetailDTO> {
    return unwrap(await apiClient.post<APIEnvelope<RunDetailDTO>>(ENDPOINTS.RUNS.RESUME(id), data));
  },

  async cancelRun(id: string, data: RunControlRequest): Promise<RunDetailDTO> {
    return unwrap(await apiClient.post<APIEnvelope<RunDetailDTO>>(ENDPOINTS.RUNS.CANCEL(id), data));
  },

  async retryRun(id: string, data: RunRetryRequest): Promise<RunDetailDTO> {
    return unwrap(await apiClient.post<APIEnvelope<RunDetailDTO>>(ENDPOINTS.RUNS.RETRY(id), data));
  },

  async listTaskRuns(runId: string, filters: TaskRunFilters = {}): Promise<PageResult<TaskRunListDTO>> {
    const envelope = await apiClient.get<APIEnvelope<readonly TaskRunListDTO[]>>(
      withQuery(ENDPOINTS.RUNS.TASK_RUNS(runId), filters),
    );
    return unwrapPage(envelope);
  },

  async getTaskRun(id: string): Promise<TaskRunDetailDTO> {
    return unwrap(await apiClient.get<APIEnvelope<TaskRunDetailDTO>>(ENDPOINTS.TASK_RUNS.DETAIL(id)));
  },

  async retryTaskRun(id: string, data: TaskRetryRequest): Promise<TaskRunDetailDTO> {
    return unwrap(await apiClient.post<APIEnvelope<TaskRunDetailDTO>>(ENDPOINTS.TASK_RUNS.RETRY(id), data));
  },

  async listEvents(runId: string): Promise<PageResult<OrchestrationEventDTO>> {
    return unwrapPage(
      await apiClient.get<APIEnvelope<readonly OrchestrationEventDTO[]>>(ENDPOINTS.RUNS.EVENTS(runId)),
    );
  },

  async listNodeTypes(): Promise<PageResult<NodeDescriptorDTO>> {
    return unwrapPage(await apiClient.get<APIEnvelope<readonly NodeDescriptorDTO[]>>(withQuery(ENDPOINTS.NODE_TYPES, { page_size: 100 })));
  },

  async getHealth(): Promise<HealthCheckDTO> {
    return unwrap(await apiClient.get<APIEnvelope<HealthCheckDTO>>(ENDPOINTS.HEALTH));
  },
};

export type AutomationOrchestrationService = typeof automationOrchestrationService;
