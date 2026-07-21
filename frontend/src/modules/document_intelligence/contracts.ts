/** Public, provider-neutral contracts for the Document Intelligence v2 API. */

export type UUID = string;
export type ISODateTime = string;
export type DecimalString = string;

export type ExtractionEngine =
  | 'tesseract'
  | 'aws_textract'
  | 'azure_form_recognizer'
  | 'google_vision'
  | (string & {});
export type ExtractionType = 'text' | 'structured' | 'table' | 'zone';
export type ExtractionStatus =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'needs_review'
  | 'failed'
  | 'cancelled'
  | 'timed_out';
export type ClassificationStatus =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timed_out';
export type ReviewStatus = 'not_required' | 'pending' | 'confirmed' | 'corrected';
export type TrainingStatus =
  | 'queued'
  | 'training'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timed_out';
export type ModelVersionStatus = 'candidate' | 'active' | 'retired' | 'failed';
export type TemplateStatus = 'draft' | 'active' | 'inactive' | 'retired';
export type ZoneType = 'text' | 'table' | 'checkbox' | 'barcode';
export type ExpectedDataType =
  | 'string'
  | 'integer'
  | 'decimal'
  | 'date'
  | 'boolean'
  | 'array';

export interface NormalizedBounds {
  x: DecimalString;
  y: DecimalString;
  width: DecimalString;
  height: DecimalString;
}

export interface EvidenceValidation {
  rule: string;
  valid: boolean;
  message: string;
}

export type NormalizedEvidenceValue = string | number | boolean | null | readonly string[];

/** Immutable field-level evidence shared with paid-module mappings. */
export interface ExtractedFieldEvidence {
  key: string;
  raw_value: string | null;
  normalized_value: NormalizedEvidenceValue;
  data_type: ExpectedDataType;
  confidence: DecimalString;
  page_number: number;
  bounds: NormalizedBounds | null;
  source_span: { start: number; end: number } | null;
  validation: readonly EvidenceValidation[];
}

export interface StructuredExtractionData {
  schema_version: string;
  fields: readonly ExtractedFieldEvidence[];
}

export interface ExtractedTableCell {
  row: number;
  column: number;
  row_span: number;
  column_span: number;
  value: string;
  confidence: DecimalString;
  bounds: NormalizedBounds | null;
}

export interface ExtractedTable {
  page_number: number;
  rows: number;
  columns: number;
  bounds: NormalizedBounds | null;
  cells: readonly ExtractedTableCell[];
}

export interface ProviderEvidence {
  adapter_key: string;
  adapter_version: string | null;
  provider_request_id: string | null;
  result_checksum: string | null;
}

export interface EntityTimestamps {
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface SoftDeleteFields {
  is_deleted: boolean;
  deleted_at: ISODateTime | null;
}

/** Immutable domain transition evidence stored with each aggregate. */
export interface DomainTransition {
  transition_key: string;
  command: string;
  from_state: string;
  to_state: string;
  occurred_at: ISODateTime;
  metadata: {
    actor_id: UUID;
    reason: string;
    correlation_id: string;
  };
}

export interface DocumentExtraction extends EntityTimestamps, SoftDeleteFields {
  id: UUID;
  tenant_id: UUID;
  created_by: UUID;
  document_id: UUID;
  document_version_id: UUID;
  async_job_id: UUID;
  idempotency_key: string;
  engine: ExtractionEngine;
  extraction_type: ExtractionType;
  template: UUID | null;
  status: ExtractionStatus;
  raw_text: string | null;
  structured_data: StructuredExtractionData | null;
  table_data: readonly ExtractedTable[] | null;
  confidence: DecimalString | null;
  page_count: number | null;
  processing_time_ms: number | null;
  failure_code: string;
  failure_message: string;
  started_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  transition_history: readonly DomainTransition[];
}

export type DocumentExtractionListItem = Pick<DocumentExtraction,
  | 'id' | 'tenant_id' | 'created_by' | 'document_id' | 'document_version_id'
  | 'engine' | 'extraction_type' | 'template' | 'status' | 'confidence'
  | 'page_count' | 'processing_time_ms' | 'created_at' | 'updated_at'
  | 'completed_at' | 'is_deleted' | 'deleted_at'
>;

export interface DocumentExtractionPage extends EntityTimestamps {
  id: UUID;
  tenant_id: UUID;
  created_by: UUID;
  extraction: UUID;
  page_number: number;
  width: number;
  height: number;
  raw_text: string;
  structured_data: StructuredExtractionData;
  table_data: readonly ExtractedTable[];
  confidence: DecimalString;
  provider_metadata: ProviderEvidence;
}

export interface DocumentClassification extends EntityTimestamps, SoftDeleteFields {
  id: UUID;
  tenant_id: UUID;
  created_by: UUID;
  document_id: UUID;
  document_version_id: UUID;
  async_job_id: UUID;
  idempotency_key: string;
  model_version: UUID;
  status: ClassificationStatus;
  category: string | null;
  confidence: DecimalString | null;
  secondary_category: string;
  secondary_confidence: DecimalString | null;
  needs_review: boolean;
  review_status: ReviewStatus;
  reviewed_category: string;
  reviewed_by: UUID | null;
  reviewed_at: ISODateTime | null;
  review_note: string;
  processing_time_ms: number | null;
  failure_code: string;
  failure_message: string;
  completed_at: ISODateTime | null;
  transition_history: readonly DomainTransition[];
}

export type DocumentClassificationListItem = Pick<DocumentClassification,
  | 'id' | 'tenant_id' | 'created_by' | 'document_id' | 'document_version_id'
  | 'status' | 'category' | 'confidence' | 'needs_review' | 'review_status'
  | 'model_version' | 'processing_time_ms' | 'created_at' | 'completed_at'
  | 'updated_at' | 'is_deleted' | 'deleted_at'
>;

export interface DocumentClassificationScore extends EntityTimestamps {
  id: UUID;
  tenant_id: UUID;
  created_by: UUID;
  classification: UUID;
  category: string;
  confidence: DecimalString;
  rank: number;
}

export interface TrainingItem {
  document_id: UUID;
  document_version_id: UUID;
  category: string;
}

export interface ClassifierTrainingJob extends EntityTimestamps {
  id: UUID;
  tenant_id: UUID;
  created_by: UUID;
  async_job_id: UUID;
  idempotency_key: string;
  name: string;
  training_items: readonly TrainingItem[];
  training_data_count: number;
  category_counts: Readonly<Record<string, number>>;
  requested_version: string;
  status: TrainingStatus;
  accuracy: DecimalString | null;
  failure_code: string;
  failure_message: string;
  started_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  transition_history: readonly DomainTransition[];
}

export type ClassifierTrainingJobListItem = Pick<ClassifierTrainingJob,
  | 'id' | 'tenant_id' | 'created_by' | 'name' | 'requested_version' | 'status'
  | 'training_data_count' | 'category_counts' | 'accuracy' | 'created_at'
  | 'started_at' | 'completed_at' | 'updated_at'
>;

export interface ClassifierTrainingJobDetail extends ClassifierTrainingJob {
  job: JobSummary;
}

export interface ClassifierModelVersion extends EntityTimestamps {
  id: UUID;
  tenant_id: UUID;
  created_by: UUID;
  version: string;
  provider_key: string;
  artifact_ref: string;
  artifact_checksum: string;
  training_job: UUID;
  accuracy: DecimalString;
  status: ModelVersionStatus;
  activated_by: UUID | null;
  activated_at: ISODateTime | null;
  retired_at: ISODateTime | null;
  transition_history: readonly DomainTransition[];
}

export type ClassifierModelVersionListItem = Pick<ClassifierModelVersion,
  | 'id' | 'tenant_id' | 'created_by' | 'version' | 'provider_key' | 'accuracy'
  | 'status' | 'training_job' | 'activated_by' | 'activated_at' | 'retired_at'
  | 'created_at' | 'updated_at'
>;

export interface ExtractionTemplate extends EntityTimestamps, SoftDeleteFields {
  id: UUID;
  tenant_id: UUID;
  created_by: UUID;
  name: string;
  description: string;
  document_category: string;
  engine: ExtractionEngine;
  match_threshold: DecimalString;
  status: TemplateStatus;
  version: number;
  activated_at: ISODateTime | null;
  transition_history: readonly DomainTransition[];
  zones: readonly ExtractionTemplateZone[];
}

export type ExtractionTemplateListItem = Pick<ExtractionTemplate,
  | 'id' | 'tenant_id' | 'created_by' | 'name' | 'description' | 'document_category'
  | 'engine' | 'match_threshold' | 'status' | 'version' | 'activated_at'
  | 'created_at' | 'updated_at' | 'is_deleted' | 'deleted_at'
> & { zone_count: number };

export interface ExtractionTemplateZone extends EntityTimestamps, SoftDeleteFields {
  id: UUID;
  tenant_id: UUID;
  created_by: UUID;
  template: UUID;
  zone_name: string;
  extraction_key: string;
  zone_type: ZoneType;
  x: DecimalString;
  y: DecimalString;
  width: DecimalString;
  height: DecimalString;
  page_number: number;
  expected_data_type: ExpectedDataType;
  is_required: boolean;
}

export interface TransitionDTO {
  id: UUID;
  from_status: string;
  to_status: string;
  actor_id: UUID | null;
  reason: string;
  metadata: { correlation_id?: string; causation_id?: string; transition_key?: string };
  created_at: ISODateTime;
}

export interface JobSummary {
  id: UUID;
  command: string;
  status: string;
  attempts: number;
  correlation_id: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  started_at: ISODateTime | null;
  completed_at: ISODateTime | null;
  transitions: readonly TransitionDTO[];
}

export interface ProviderFailure {
  adapter_key: string;
  code: string;
  message: string;
  retryable: boolean;
}

export type HealthStatus = 'healthy' | 'degraded' | 'unavailable';
export interface DependencyHealth {
  name: 'database' | 'async_execution' | 'dms' | 'providers';
  status: HealthStatus;
  code: string;
  checked_at: ISODateTime;
  circuit_state?: 'closed' | 'open' | 'half_open' | 'not_applicable';
}

export interface ModuleHealth {
  status: HealthStatus;
  live: boolean;
  ready: boolean;
  checked_at: ISODateTime;
  dependencies: readonly DependencyHealth[];
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total_pages: number;
  count: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface ApiV2Meta {
  correlation_id: string;
  timestamp: ISODateTime;
}

export interface ApiV2Envelope<T> {
  data: T;
  meta: ApiV2Meta;
}

export interface ApiV2PaginatedEnvelope<T> {
  data: readonly T[];
  meta: ApiV2Meta & { pagination: PaginationMeta };
}

export interface ApiV2ErrorDetail {
  field_errors?: readonly { field: string; code: string; message: string }[];
  quota?: { resource: string; remaining: number; reset_at: ISODateTime | null };
  retry_after_seconds?: number;
}

export interface ApiV2ErrorBody {
  code: string;
  message: string;
  detail: ApiV2ErrorDetail;
  correlation_id: string;
}

export interface ApiV2ErrorEnvelope {
  error: ApiV2ErrorBody;
}

export interface PaginatedResult<T> {
  items: readonly T[];
  pagination: PaginationMeta;
  correlationId: string;
}

export interface AcceptedExtraction {
  extraction: DocumentExtraction;
  job: JobSummary;
}
export interface AcceptedClassification {
  classification: DocumentClassification;
  job: JobSummary;
}
export interface AcceptedTrainingJob {
  training_job: ClassifierTrainingJob;
  job: JobSummary;
}
export interface TemplateMatchResult {
  matched: boolean;
  template_id: UUID | null;
  confidence: DecimalString;
  processing_time_ms: number;
  evidence: { threshold_met: boolean };
}

export interface PageFilters {
  page?: number;
  page_size?: number;
  search?: string;
  ordering?: string;
}
export interface ExtractionFilters extends PageFilters {
  document_id?: UUID;
  status?: ExtractionStatus;
  engine?: ExtractionEngine;
  extraction_type?: ExtractionType;
  template_id?: UUID;
  created_after?: ISODateTime;
  created_before?: ISODateTime;
  confidence_min?: DecimalString;
}

export function parseExtractionStatus(value: string | null): ExtractionStatus | undefined {
  switch (value) {
    case 'queued': case 'processing': case 'completed': case 'needs_review': case 'failed': case 'cancelled': case 'timed_out': return value;
    default: return undefined;
  }
}

export function parseClassificationStatus(value: string | null): ClassificationStatus | undefined {
  switch (value) {
    case 'queued': case 'processing': case 'completed': case 'failed': case 'cancelled': case 'timed_out': return value;
    default: return undefined;
  }
}

export function parseTemplateStatus(value: string | null): TemplateStatus | undefined {
  switch (value) {
    case 'draft': case 'active': case 'inactive': case 'retired': return value;
    default: return undefined;
  }
}
export interface ClassificationFilters extends PageFilters {
  document_id?: UUID;
  status?: ClassificationStatus;
  category?: string;
  confidence_min?: DecimalString;
  confidence_max?: DecimalString;
  needs_review?: boolean;
  review_status?: ReviewStatus;
}
export interface TemplateFilters extends PageFilters {
  status?: TemplateStatus;
  document_category?: string;
  engine?: ExtractionEngine;
}
export interface TrainingJobFilters extends PageFilters {
  status?: TrainingStatus;
}
export interface ModelVersionFilters extends PageFilters {
  status?: ModelVersionStatus;
  provider_key?: string;
}

export interface DocumentExtractionCreateRequest {
  document_id: UUID;
  document_version_id: UUID;
  engine: ExtractionEngine;
  extraction_type: ExtractionType;
  template_id?: UUID;
  idempotency_key: string;
}
export interface DocumentClassificationCreateRequest {
  document_id: UUID;
  document_version_id: UUID;
  idempotency_key: string;
}
export interface ClassificationReviewRequest {
  category: string;
  note: string;
}
export interface RetryRequest { idempotency_key: string }
export interface CancelRequest { reason: string }
export interface TransitionRequest { transition_key: string }
export interface TemplateMatchRequest { document_id: UUID; document_version_id: UUID }
export interface CloneTemplateRequest { name: string }

export interface ExtractionTemplateZoneInput {
  zone_name: string;
  extraction_key: string;
  zone_type: ZoneType;
  x: DecimalString;
  y: DecimalString;
  width: DecimalString;
  height: DecimalString;
  page_number: number;
  expected_data_type: ExpectedDataType;
  is_required: boolean;
}
export interface ExtractionTemplateCreateRequest {
  name: string;
  description: string;
  document_category: string;
  engine: ExtractionEngine;
  match_threshold: DecimalString;
  zones: readonly ExtractionTemplateZoneInput[];
}
export interface ExtractionTemplateUpdateRequest {
  name?: string;
  description?: string;
  document_category?: string;
  engine?: ExtractionEngine;
  match_threshold?: DecimalString;
}
export type ExtractionTemplateZoneCreateRequest = ExtractionTemplateZoneInput & { template_id: UUID };
export type ExtractionTemplateZoneUpdateRequest = Partial<ExtractionTemplateZoneInput>;
export interface ClassifierTrainingJobCreateRequest {
  name: string;
  items: readonly TrainingItem[];
  requested_version: string;
  idempotency_key: string;
}

export const MODULE_API_PREFIX = '/api/v2/document-intelligence';
export const ENDPOINTS = {
  EXTRACTIONS: {
    LIST: `${MODULE_API_PREFIX}/extractions/`, CREATE: `${MODULE_API_PREFIX}/extractions/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/extractions/${id}/` as const,
    PAGES: (id: UUID) => `${MODULE_API_PREFIX}/extractions/${id}/pages/` as const,
    RETRY: (id: UUID) => `${MODULE_API_PREFIX}/extractions/${id}/retry/` as const,
    CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/extractions/${id}/cancel/` as const,
  },
  EXTRACTION_PAGES: { DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/extraction-pages/${id}/` as const },
  CLASSIFICATIONS: {
    LIST: `${MODULE_API_PREFIX}/classifications/`, CREATE: `${MODULE_API_PREFIX}/classifications/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/classifications/${id}/` as const,
    SCORES: (id: UUID) => `${MODULE_API_PREFIX}/classifications/${id}/scores/` as const,
    REVIEW: (id: UUID) => `${MODULE_API_PREFIX}/classifications/${id}/review/` as const,
    RETRY: (id: UUID) => `${MODULE_API_PREFIX}/classifications/${id}/retry/` as const,
    CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/classifications/${id}/cancel/` as const,
  },
  CLASSIFICATION_SCORES: { DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/classification-scores/${id}/` as const },
  TEMPLATES: {
    LIST: `${MODULE_API_PREFIX}/templates/`, CREATE: `${MODULE_API_PREFIX}/templates/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/templates/${id}/` as const,
    ACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/templates/${id}/activate/` as const,
    DEACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/templates/${id}/deactivate/` as const,
    CLONE: (id: UUID) => `${MODULE_API_PREFIX}/templates/${id}/clone/` as const,
    MATCH: (id: UUID) => `${MODULE_API_PREFIX}/templates/${id}/match/` as const,
  },
  TEMPLATE_ZONES: {
    LIST: `${MODULE_API_PREFIX}/template-zones/`, CREATE: `${MODULE_API_PREFIX}/template-zones/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/template-zones/${id}/` as const,
  },
  TRAINING_JOBS: {
    LIST: `${MODULE_API_PREFIX}/training-jobs/`, CREATE: `${MODULE_API_PREFIX}/training-jobs/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/training-jobs/${id}/` as const,
    RETRY: (id: UUID) => `${MODULE_API_PREFIX}/training-jobs/${id}/retry/` as const,
    CANCEL: (id: UUID) => `${MODULE_API_PREFIX}/training-jobs/${id}/cancel/` as const,
  },
  MODEL_VERSIONS: {
    LIST: `${MODULE_API_PREFIX}/model-versions/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/model-versions/${id}/` as const,
    ACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/model-versions/${id}/activate/` as const,
    ROLLBACK: (id: UUID) => `${MODULE_API_PREFIX}/model-versions/${id}/rollback/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
