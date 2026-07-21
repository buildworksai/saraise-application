import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type AcceptedClassification,
  type AcceptedExtraction,
  type AcceptedTrainingJob,
  type ApiV2Envelope,
  type ApiV2ErrorBody,
  type ApiV2PaginatedEnvelope,
  type CancelRequest,
  type ClassificationFilters,
  type ClassificationReviewRequest,
  type ClassifierModelVersion,
  type ClassifierModelVersionListItem,
  type ClassifierTrainingJobDetail,
  type ClassifierTrainingJobListItem,
  type ClassifierTrainingJobCreateRequest,
  type DocumentClassification,
  type DocumentClassificationListItem,
  type DocumentClassificationCreateRequest,
  type DocumentClassificationScore,
  type DocumentExtraction,
  type DocumentExtractionListItem,
  type DocumentExtractionCreateRequest,
  type DocumentExtractionPage,
  type ExtractionFilters,
  type ExtractionTemplate,
  type ExtractionTemplateListItem,
  type ExtractionTemplateCreateRequest,
  type ExtractionTemplateUpdateRequest,
  type ExtractionTemplateZone,
  type ExtractionTemplateZoneCreateRequest,
  type ExtractionTemplateZoneUpdateRequest,
  type ModelVersionFilters,
  type ModuleHealth,
  type PaginatedResult,
  type RetryRequest,
  type TemplateFilters,
  type TemplateMatchRequest,
  type TemplateMatchResult,
  type TrainingJobFilters,
  type TransitionRequest,
  type UUID,
  type CloneTemplateRequest,
} from '../contracts';

export class DocumentIntelligenceApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
    readonly detail: ApiV2ErrorBody['detail'],
  ) {
    super(message);
    this.name = 'DocumentIntelligenceApiError';
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function readErrorDetail(value: unknown): ApiV2ErrorBody['detail'] {
  if (!isObject(value)) return {};
  const result: ApiV2ErrorBody['detail'] = {};
  if (typeof value.retry_after_seconds === 'number') result.retry_after_seconds = value.retry_after_seconds;
  if (isObject(value.quota) && typeof value.quota.resource === 'string' && typeof value.quota.remaining === 'number') {
    result.quota = {
      resource: value.quota.resource,
      remaining: value.quota.remaining,
      reset_at: typeof value.quota.reset_at === 'string' ? value.quota.reset_at : null,
    };
  }
  if (Array.isArray(value.field_errors)) {
    result.field_errors = value.field_errors.flatMap((entry) =>
      isObject(entry) && typeof entry.field === 'string' && typeof entry.code === 'string' && typeof entry.message === 'string'
        ? [{ field: entry.field, code: entry.code, message: entry.message }]
        : [],
    );
  }
  return result;
}

function readV2Error(error: ApiError): ApiV2ErrorBody | null {
  if (!isObject(error.details) || !isObject(error.details.error)) return null;
  const body = error.details.error;
  if (
    typeof body.code !== 'string' ||
    typeof body.message !== 'string' ||
    typeof body.correlation_id !== 'string'
  ) return null;
  return {
    code: body.code,
    message: body.message,
    correlation_id: body.correlation_id,
    detail: readErrorDetail(body.detail),
  };
}

async function call<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    const governed = readV2Error(error);
    throw new DocumentIntelligenceApiError(
      governed?.message ?? error.message,
      error.status,
      governed?.code ?? error.code ?? 'request_failed',
      governed?.correlation_id ?? error.correlationId ?? null,
      governed?.detail ?? {},
    );
  }
}

async function getData<T>(operation: () => Promise<ApiV2Envelope<T>>): Promise<T> {
  return (await call(operation)).data;
}

async function getPage<T>(
  operation: () => Promise<ApiV2PaginatedEnvelope<T>>,
): Promise<PaginatedResult<T>> {
  const envelope = await call(operation);
  return {
    items: envelope.data,
    pagination: envelope.meta.pagination,
    correlationId: envelope.meta.correlation_id,
  };
}

function addPageFilters(params: URLSearchParams, filters: { page?: number; page_size?: number; search?: string; ordering?: string }): void {
  if (filters.page !== undefined) params.set('page', String(filters.page));
  if (filters.page_size !== undefined) params.set('page_size', String(filters.page_size));
  if (filters.search) params.set('search', filters.search);
  if (filters.ordering) params.set('ordering', filters.ordering);
}

function withQuery(path: string, params: URLSearchParams): string {
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

function extractionQuery(filters: ExtractionFilters): string {
  const params = new URLSearchParams();
  addPageFilters(params, filters);
  if (filters.document_id) params.set('document_id', filters.document_id);
  if (filters.status) params.set('status', filters.status);
  if (filters.engine) params.set('engine', filters.engine);
  if (filters.extraction_type) params.set('extraction_type', filters.extraction_type);
  if (filters.template_id) params.set('template_id', filters.template_id);
  if (filters.created_after) params.set('created_after', filters.created_after);
  if (filters.created_before) params.set('created_before', filters.created_before);
  if (filters.confidence_min) params.set('confidence_min', filters.confidence_min);
  return withQuery(ENDPOINTS.EXTRACTIONS.LIST, params);
}

function classificationQuery(filters: ClassificationFilters): string {
  const params = new URLSearchParams();
  addPageFilters(params, filters);
  if (filters.document_id) params.set('document_id', filters.document_id);
  if (filters.status) params.set('status', filters.status);
  if (filters.category) params.set('category', filters.category);
  if (filters.confidence_min) params.set('confidence_min', filters.confidence_min);
  if (filters.confidence_max) params.set('confidence_max', filters.confidence_max);
  if (filters.needs_review !== undefined) params.set('needs_review', String(filters.needs_review));
  if (filters.review_status) params.set('review_status', filters.review_status);
  return withQuery(ENDPOINTS.CLASSIFICATIONS.LIST, params);
}

function templateQuery(filters: TemplateFilters): string {
  const params = new URLSearchParams();
  addPageFilters(params, filters);
  if (filters.status) params.set('status', filters.status);
  if (filters.document_category) params.set('document_category', filters.document_category);
  if (filters.engine) params.set('engine', filters.engine);
  return withQuery(ENDPOINTS.TEMPLATES.LIST, params);
}

function trainingQuery(filters: TrainingJobFilters): string {
  const params = new URLSearchParams();
  addPageFilters(params, filters);
  if (filters.status) params.set('status', filters.status);
  return withQuery(ENDPOINTS.TRAINING_JOBS.LIST, params);
}

function modelQuery(filters: ModelVersionFilters): string {
  const params = new URLSearchParams();
  addPageFilters(params, filters);
  if (filters.status) params.set('status', filters.status);
  if (filters.provider_key) params.set('provider_key', filters.provider_key);
  return withQuery(ENDPOINTS.MODEL_VERSIONS.LIST, params);
}

export const documentIntelligenceService = {
  listExtractions: (filters: ExtractionFilters = {}) =>
    getPage(() => apiClient.get<ApiV2PaginatedEnvelope<DocumentExtractionListItem>>(extractionQuery(filters))),
  createExtraction: (request: DocumentExtractionCreateRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<AcceptedExtraction>>(ENDPOINTS.EXTRACTIONS.CREATE, request)),
  getExtraction: (id: UUID) =>
    getData(() => apiClient.get<ApiV2Envelope<DocumentExtraction>>(ENDPOINTS.EXTRACTIONS.DETAIL(id))),
  archiveExtraction: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.EXTRACTIONS.DETAIL(id))),
  listExtractionPages: (id: UUID) =>
    getPage(() => apiClient.get<ApiV2PaginatedEnvelope<DocumentExtractionPage>>(ENDPOINTS.EXTRACTIONS.PAGES(id))),
  getExtractionPage: (id: UUID) =>
    getData(() => apiClient.get<ApiV2Envelope<DocumentExtractionPage>>(ENDPOINTS.EXTRACTION_PAGES.DETAIL(id))),
  retryExtraction: (id: UUID, request: RetryRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<AcceptedExtraction>>(ENDPOINTS.EXTRACTIONS.RETRY(id), request)),
  cancelExtraction: (id: UUID, request: CancelRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<DocumentExtraction>>(ENDPOINTS.EXTRACTIONS.CANCEL(id), request)),

  listClassifications: (filters: ClassificationFilters = {}) =>
    getPage(() => apiClient.get<ApiV2PaginatedEnvelope<DocumentClassificationListItem>>(classificationQuery(filters))),
  createClassification: (request: DocumentClassificationCreateRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<AcceptedClassification>>(ENDPOINTS.CLASSIFICATIONS.CREATE, request)),
  getClassification: (id: UUID) =>
    getData(() => apiClient.get<ApiV2Envelope<DocumentClassification>>(ENDPOINTS.CLASSIFICATIONS.DETAIL(id))),
  archiveClassification: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.CLASSIFICATIONS.DETAIL(id))),
  listClassificationScores: (id: UUID) =>
    getPage(() => apiClient.get<ApiV2PaginatedEnvelope<DocumentClassificationScore>>(ENDPOINTS.CLASSIFICATIONS.SCORES(id))),
  getClassificationScore: (id: UUID) =>
    getData(() => apiClient.get<ApiV2Envelope<DocumentClassificationScore>>(ENDPOINTS.CLASSIFICATION_SCORES.DETAIL(id))),
  reviewClassification: (id: UUID, request: ClassificationReviewRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<DocumentClassification>>(ENDPOINTS.CLASSIFICATIONS.REVIEW(id), request)),
  retryClassification: (id: UUID, request: RetryRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<AcceptedClassification>>(ENDPOINTS.CLASSIFICATIONS.RETRY(id), request)),
  cancelClassification: (id: UUID, request: CancelRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<DocumentClassification>>(ENDPOINTS.CLASSIFICATIONS.CANCEL(id), request)),

  listTemplates: (filters: TemplateFilters = {}) =>
    getPage(() => apiClient.get<ApiV2PaginatedEnvelope<ExtractionTemplateListItem>>(templateQuery(filters))),
  createTemplate: (request: ExtractionTemplateCreateRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<ExtractionTemplate>>(ENDPOINTS.TEMPLATES.CREATE, request)),
  getTemplate: (id: UUID) =>
    getData(() => apiClient.get<ApiV2Envelope<ExtractionTemplate>>(ENDPOINTS.TEMPLATES.DETAIL(id))),
  updateTemplate: (id: UUID, request: ExtractionTemplateUpdateRequest) =>
    getData(() => apiClient.patch<ApiV2Envelope<ExtractionTemplate>>(ENDPOINTS.TEMPLATES.DETAIL(id), request)),
  archiveTemplate: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.TEMPLATES.DETAIL(id))),
  activateTemplate: (id: UUID, request: TransitionRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<ExtractionTemplate>>(ENDPOINTS.TEMPLATES.ACTIVATE(id), request)),
  deactivateTemplate: (id: UUID, request: TransitionRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<ExtractionTemplate>>(ENDPOINTS.TEMPLATES.DEACTIVATE(id), request)),
  cloneTemplate: (id: UUID, request: CloneTemplateRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<ExtractionTemplate>>(ENDPOINTS.TEMPLATES.CLONE(id), request)),
  matchTemplate: (id: UUID, request: TemplateMatchRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<TemplateMatchResult>>(ENDPOINTS.TEMPLATES.MATCH(id), request)),
  listTemplateZones: (templateId: UUID) => {
    const params = new URLSearchParams({ template_id: templateId, page_size: '100' });
    return getPage(() => apiClient.get<ApiV2PaginatedEnvelope<ExtractionTemplateZone>>(withQuery(ENDPOINTS.TEMPLATE_ZONES.LIST, params)));
  },
  createTemplateZone: (request: ExtractionTemplateZoneCreateRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<ExtractionTemplateZone>>(ENDPOINTS.TEMPLATE_ZONES.CREATE, request)),
  getTemplateZone: (id: UUID) =>
    getData(() => apiClient.get<ApiV2Envelope<ExtractionTemplateZone>>(ENDPOINTS.TEMPLATE_ZONES.DETAIL(id))),
  updateTemplateZone: (id: UUID, request: ExtractionTemplateZoneUpdateRequest) =>
    getData(() => apiClient.patch<ApiV2Envelope<ExtractionTemplateZone>>(ENDPOINTS.TEMPLATE_ZONES.DETAIL(id), request)),
  deleteTemplateZone: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.TEMPLATE_ZONES.DETAIL(id))),

  listTrainingJobs: (filters: TrainingJobFilters = {}) =>
    getPage(() => apiClient.get<ApiV2PaginatedEnvelope<ClassifierTrainingJobListItem>>(trainingQuery(filters))),
  createTrainingJob: (request: ClassifierTrainingJobCreateRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<AcceptedTrainingJob>>(ENDPOINTS.TRAINING_JOBS.CREATE, request)),
  getTrainingJob: (id: UUID) =>
    getData(() => apiClient.get<ApiV2Envelope<ClassifierTrainingJobDetail>>(ENDPOINTS.TRAINING_JOBS.DETAIL(id))),
  retryTrainingJob: (id: UUID, request: RetryRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<AcceptedTrainingJob>>(ENDPOINTS.TRAINING_JOBS.RETRY(id), request)),
  cancelTrainingJob: (id: UUID, request: CancelRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<ClassifierTrainingJobDetail>>(ENDPOINTS.TRAINING_JOBS.CANCEL(id), request)),

  listModelVersions: (filters: ModelVersionFilters = {}) =>
    getPage(() => apiClient.get<ApiV2PaginatedEnvelope<ClassifierModelVersionListItem>>(modelQuery(filters))),
  getModelVersion: (id: UUID) =>
    getData(() => apiClient.get<ApiV2Envelope<ClassifierModelVersion>>(ENDPOINTS.MODEL_VERSIONS.DETAIL(id))),
  activateModelVersion: (id: UUID, request: TransitionRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<ClassifierModelVersion>>(ENDPOINTS.MODEL_VERSIONS.ACTIVATE(id), request)),
  rollbackModelVersion: (id: UUID, request: TransitionRequest) =>
    getData(() => apiClient.post<ApiV2Envelope<ClassifierModelVersion>>(ENDPOINTS.MODEL_VERSIONS.ROLLBACK(id), request)),
  getHealth: () => getData(() => apiClient.get<ApiV2Envelope<ModuleHealth>>(ENDPOINTS.HEALTH)),
};
