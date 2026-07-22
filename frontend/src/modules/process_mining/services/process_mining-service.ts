import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiEnvelope,
  type ApiErrorBody,
  type BottleneckAnalysis,
  type BottleneckCreateRequest,
  type BottleneckFilters,
  type BottleneckFinding,
  type ConformanceCheck,
  type ConformanceCreateRequest,
  type ConformanceDeviation,
  type ConformanceFilters,
  type DeviationFilters,
  type DiscoveryCreateRequest,
  type DiscoveryFilters,
  type DiscoveryJob,
  type EventBatchIngestRequest,
  type EventExport,
  type EventExportCreateRequest,
  type EventFilter,
  type ExportFilters,
  type FindingFilters,
  type FitnessEvidence,
  type IngestResult,
  type ModelFilters,
  type ModuleHealth,
  type PaginatedEnvelope,
  type PaginatedResult,
  type ProcessEvent,
  type ProcessFilters,
  type ProcessModel,
  type ProcessModelCreateRequest,
  type ProcessModelUpdateRequest,
  type ProcessModelVersion,
  type ProcessOverview,
  type ProcessMiningConfiguration,
  type ProcessMiningConfigurationDocument,
  type ProcessMiningConfigurationVersion,
  type ConfigurationPreview,
  type ConfigurationExport,
  type ProcessVariant,
  type SetReferenceRequest,
  type TransitionActionRequest,
  type UUID,
  type VariantFilters,
} from '../contracts';

let cachedConfiguration: ProcessMiningConfigurationDocument | null = null;
let downloadFailures = 0;
let downloadCircuitOpenedAt = 0;

const wait = (milliseconds: number) => new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

async function resilientDownload(id: UUID, configuration: ProcessMiningConfigurationDocument): Promise<Blob> {
  const now = Date.now();
  if (downloadFailures >= configuration.download_circuit_failure_threshold) {
    if (now - downloadCircuitOpenedAt < configuration.download_circuit_reset_ms) {
      throw new ProcessMiningApiError('Export download circuit is open.', 503, 'CIRCUIT_OPEN', null, {});
    }
    downloadFailures = 0;
  }
  let lastError: unknown;
  for (let attempt = 0; attempt <= configuration.download_retry_attempts; attempt += 1) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), configuration.download_timeout_ms);
    try {
      const response = await fetch(ENDPOINTS.EXPORTS.DOWNLOAD(id), { credentials: 'include', signal: controller.signal });
      if (!response.ok) {
        let body: unknown;
        try { body = await response.json(); } catch { body = {}; }
        const error = governedError(new ApiError(response.statusText || 'Download failed', response.status, body));
        if (response.status < 500 || attempt === configuration.download_retry_attempts) throw error;
        lastError = error;
      } else {
        downloadFailures = 0;
        return await response.blob();
      }
    } catch (error) {
      lastError = error;
      if (attempt === configuration.download_retry_attempts) break;
    } finally {
      window.clearTimeout(timeout);
    }
    const maximumDelay = configuration.download_retry_base_ms * (2 ** attempt);
    await wait(Math.random() * maximumDelay);
  }
  downloadFailures += 1;
  if (downloadFailures >= configuration.download_circuit_failure_threshold) downloadCircuitOpenedAt = Date.now();
  throw lastError instanceof Error ? lastError : new Error('Export download failed.');
}

export class ProcessMiningApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
    readonly detail: ApiErrorBody['detail'],
  ) {
    super(message);
    this.name = 'ProcessMiningApiError';
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function governedError(error: ApiError): ProcessMiningApiError {
  const root = isObject(error.details) && isObject(error.details.error) ? error.details.error : null;
  const detail = root && isObject(root.detail) ? root.detail : {};
  return new ProcessMiningApiError(
    root && typeof root.message === 'string' ? root.message : error.message,
    error.status,
    root && typeof root.code === 'string' ? root.code : error.code ?? 'REQUEST_FAILED',
    root && typeof root.correlation_id === 'string' ? root.correlation_id : error.correlationId ?? null,
    detail,
  );
}

async function call<T>(operation: () => Promise<T>): Promise<T> {
  try { return await operation(); }
  catch (error) { if (error instanceof ApiError) throw governedError(error); throw error; }
}

async function data<T>(operation: () => Promise<ApiEnvelope<T>>): Promise<T> {
  return (await call(operation)).data;
}

async function page<T>(operation: () => Promise<PaginatedEnvelope<T>>): Promise<PaginatedResult<T>> {
  const response = await call(operation);
  return { items: response.data, pagination: response.meta.pagination, correlationId: response.meta.correlation_id };
}

export const processMiningService = {
  listProcesses: (filters: ProcessFilters = {}) => page(() => apiClient.get<PaginatedEnvelope<ProcessOverview>>(ENDPOINTS.PROCESSES.QUERY(filters))),
  getProcess: (name: string) => data(() => apiClient.get<ApiEnvelope<ProcessOverview>>(ENDPOINTS.PROCESSES.DETAIL(name))),
  listEvents: (filters: EventFilter) => page(() => apiClient.get<PaginatedEnvelope<ProcessEvent>>(ENDPOINTS.EVENTS.QUERY(filters))),
  getEvent: (id: UUID) => data(() => apiClient.get<ApiEnvelope<ProcessEvent>>(ENDPOINTS.EVENTS.DETAIL(id))),
  ingestEvents: (request: EventBatchIngestRequest) => data(() => apiClient.post<ApiEnvelope<IngestResult>>(ENDPOINTS.EVENTS.INGEST, request)),

  listExports: (filters: ExportFilters = {}) => page(() => apiClient.get<PaginatedEnvelope<EventExport>>(ENDPOINTS.EXPORTS.QUERY(filters))),
  getExport: (id: UUID) => data(() => apiClient.get<ApiEnvelope<EventExport>>(ENDPOINTS.EXPORTS.DETAIL(id))),
  createExport: (request: EventExportCreateRequest) => data(() => apiClient.post<ApiEnvelope<EventExport>>(ENDPOINTS.EXPORTS.CREATE, request)),
  deleteExport: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.EXPORTS.DETAIL(id))),
  cancelExport: (id: UUID, request: TransitionActionRequest) => data(() => apiClient.post<ApiEnvelope<EventExport>>(ENDPOINTS.EXPORTS.CANCEL(id), request)),
  retryExport: (id: UUID, request: TransitionActionRequest) => data(() => apiClient.post<ApiEnvelope<EventExport>>(ENDPOINTS.EXPORTS.RETRY(id), request)),
  downloadExport: async (id: UUID): Promise<Blob> => {
    const configuration = cachedConfiguration ?? (await processMiningService.getConfiguration()).document;
    return resilientDownload(id, configuration);
  },

  listDiscoveries: (filters: DiscoveryFilters = {}) => page(() => apiClient.get<PaginatedEnvelope<DiscoveryJob>>(ENDPOINTS.DISCOVERIES.QUERY(filters))),
  getDiscovery: (id: UUID) => data(() => apiClient.get<ApiEnvelope<DiscoveryJob>>(ENDPOINTS.DISCOVERIES.DETAIL(id))),
  createDiscovery: (request: DiscoveryCreateRequest) => data(() => apiClient.post<ApiEnvelope<DiscoveryJob>>(ENDPOINTS.DISCOVERIES.CREATE, request)),
  deleteDiscovery: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.DISCOVERIES.DETAIL(id))),
  getDiscoveredModel: (id: UUID) => data(() => apiClient.get<ApiEnvelope<ProcessModelVersion>>(ENDPOINTS.DISCOVERIES.MODEL(id))),
  cancelDiscovery: (id: UUID, request: TransitionActionRequest) => data(() => apiClient.post<ApiEnvelope<DiscoveryJob>>(ENDPOINTS.DISCOVERIES.CANCEL(id), request)),
  retryDiscovery: (id: UUID, request: TransitionActionRequest) => data(() => apiClient.post<ApiEnvelope<DiscoveryJob>>(ENDPOINTS.DISCOVERIES.RETRY(id), request)),

  listModels: (filters: ModelFilters = {}) => page(() => apiClient.get<PaginatedEnvelope<ProcessModel>>(ENDPOINTS.MODELS.QUERY(filters))),
  getModel: (id: UUID) => data(() => apiClient.get<ApiEnvelope<ProcessModel>>(ENDPOINTS.MODELS.DETAIL(id))),
  createModel: (request: ProcessModelCreateRequest) => data(() => apiClient.post<ApiEnvelope<ProcessModel>>(ENDPOINTS.MODELS.CREATE, request)),
  updateModel: (id: UUID, request: ProcessModelUpdateRequest) => data(() => apiClient.patch<ApiEnvelope<ProcessModel>>(ENDPOINTS.MODELS.DETAIL(id), request)),
  deleteModel: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.MODELS.DETAIL(id))),
  listModelVersions: (id: UUID, pageNumber = 1) => page(() => apiClient.get<PaginatedEnvelope<ProcessModelVersion>>(ENDPOINTS.MODELS.VERSIONS(id, pageNumber))),
  getModelVersion: (id: UUID) => data(() => apiClient.get<ApiEnvelope<ProcessModelVersion>>(ENDPOINTS.MODEL_VERSIONS.DETAIL(id))),
  setReference: (id: UUID, request: SetReferenceRequest) => data(() => apiClient.post<ApiEnvelope<ProcessModelVersion>>(ENDPOINTS.MODELS.SET_REFERENCE(id), request)),

  listConformance: (filters: ConformanceFilters = {}) => page(() => apiClient.get<PaginatedEnvelope<ConformanceCheck>>(ENDPOINTS.CONFORMANCE.QUERY(filters))),
  getConformance: (id: UUID) => data(() => apiClient.get<ApiEnvelope<ConformanceCheck>>(ENDPOINTS.CONFORMANCE.DETAIL(id))),
  createConformance: (request: ConformanceCreateRequest) => data(() => apiClient.post<ApiEnvelope<ConformanceCheck>>(ENDPOINTS.CONFORMANCE.CREATE, request)),
  deleteConformance: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.CONFORMANCE.DETAIL(id))),
  listDeviations: (id: UUID, filters: DeviationFilters = {}) => page(() => apiClient.get<PaginatedEnvelope<ConformanceDeviation>>(ENDPOINTS.CONFORMANCE.DEVIATIONS(id, filters))),
  getFitness: (id: UUID) => page(() => apiClient.get<PaginatedEnvelope<FitnessEvidence>>(ENDPOINTS.CONFORMANCE.FITNESS(id))),
  cancelConformance: (id: UUID, request: TransitionActionRequest) => data(() => apiClient.post<ApiEnvelope<ConformanceCheck>>(ENDPOINTS.CONFORMANCE.CANCEL(id), request)),
  retryConformance: (id: UUID, request: TransitionActionRequest) => data(() => apiClient.post<ApiEnvelope<ConformanceCheck>>(ENDPOINTS.CONFORMANCE.RETRY(id), request)),

  listBottlenecks: (filters: BottleneckFilters = {}) => page(() => apiClient.get<PaginatedEnvelope<BottleneckAnalysis>>(ENDPOINTS.BOTTLENECKS.QUERY(filters))),
  getBottleneck: (id: UUID) => data(() => apiClient.get<ApiEnvelope<BottleneckAnalysis>>(ENDPOINTS.BOTTLENECKS.DETAIL(id))),
  createBottleneck: (request: BottleneckCreateRequest) => data(() => apiClient.post<ApiEnvelope<BottleneckAnalysis>>(ENDPOINTS.BOTTLENECKS.CREATE, request)),
  deleteBottleneck: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.BOTTLENECKS.DETAIL(id))),
  listFindings: (id: UUID, filters: FindingFilters = {}) => page(() => apiClient.get<PaginatedEnvelope<BottleneckFinding>>(ENDPOINTS.BOTTLENECKS.FINDINGS(id, filters))),
  listVariants: (id: UUID, filters: VariantFilters = {}) => page(() => apiClient.get<PaginatedEnvelope<ProcessVariant>>(ENDPOINTS.BOTTLENECKS.VARIANTS(id, filters))),
  cancelBottleneck: (id: UUID, request: TransitionActionRequest) => data(() => apiClient.post<ApiEnvelope<BottleneckAnalysis>>(ENDPOINTS.BOTTLENECKS.CANCEL(id), request)),
  retryBottleneck: (id: UUID, request: TransitionActionRequest) => data(() => apiClient.post<ApiEnvelope<BottleneckAnalysis>>(ENDPOINTS.BOTTLENECKS.RETRY(id), request)),
  health: () => data(() => apiClient.get<ApiEnvelope<ModuleHealth>>(ENDPOINTS.HEALTH)),
  getConfiguration: async () => {
    const value = await data(() => apiClient.get<ApiEnvelope<ProcessMiningConfiguration>>(ENDPOINTS.CONFIGURATION.CURRENT));
    cachedConfiguration = value.document;
    return value;
  },
  updateConfiguration: async (document: ProcessMiningConfigurationDocument) => {
    const value = await data(() => apiClient.put<ApiEnvelope<ProcessMiningConfiguration>>(ENDPOINTS.CONFIGURATION.UPDATE, { document }));
    cachedConfiguration = value.document;
    return value;
  },
  previewConfiguration: (document: ProcessMiningConfigurationDocument) => data(() => apiClient.post<ApiEnvelope<ConfigurationPreview>>(ENDPOINTS.CONFIGURATION.PREVIEW, { document })),
  configurationHistory: (pageNumber = 1) => page(() => apiClient.get<PaginatedEnvelope<ProcessMiningConfigurationVersion>>(ENDPOINTS.CONFIGURATION.HISTORY(pageNumber))),
  rollbackConfiguration: async (version: number) => {
    const value = await data(() => apiClient.post<ApiEnvelope<ProcessMiningConfiguration>>(ENDPOINTS.CONFIGURATION.ROLLBACK, { version }));
    cachedConfiguration = value.document;
    return value;
  },
  importConfiguration: async (configuration: ConfigurationExport) => {
    const value = await data(() => apiClient.post<ApiEnvelope<ProcessMiningConfiguration>>(ENDPOINTS.CONFIGURATION.IMPORT, { configuration }));
    cachedConfiguration = value.document;
    return value;
  },
  exportConfiguration: () => data(() => apiClient.get<ApiEnvelope<ConfigurationExport>>(ENDPOINTS.CONFIGURATION.EXPORT)),
};

export const process_mining_service = processMiningService;
