import type {
  ClassifierModelVersion,
  ClassifierModelVersionListItem,
  ClassifierTrainingJobDetail,
  DocumentClassification,
  DocumentExtraction,
  ExtractionTemplate,
  JobSummary,
  PaginatedResult,
} from '../contracts';

export const timestamp = '2026-07-21T10:00:00Z';

export const jobSummary: JobSummary = {
  id: '00000000-0000-4000-8000-000000000090',
  command: 'document_intelligence.train_classifier',
  status: 'running',
  attempts: 1,
  correlation_id: 'corr-workflow',
  created_at: timestamp,
  updated_at: timestamp,
  started_at: timestamp,
  completed_at: null,
  transitions: [{
    id: '00000000-0000-4000-8000-000000000091',
    from_status: 'queued',
    to_status: 'running',
    actor_id: '00000000-0000-4000-8000-000000000002',
    reason: 'Worker claimed job',
    metadata: { correlation_id: 'corr-workflow' },
    created_at: timestamp,
  }],
};

const domainTransition = [{
  transition_key: 'initial',
  command: 'enqueue',
  from_state: '',
  to_state: 'queued',
  occurred_at: timestamp,
  metadata: {
    actor_id: '00000000-0000-4000-8000-000000000002',
    reason: 'Submitted',
    correlation_id: 'corr-workflow',
  },
}] as const;

export const extractionDetail: DocumentExtraction = {
  id: '00000000-0000-4000-8000-000000000010',
  tenant_id: '00000000-0000-4000-8000-000000000001',
  created_by: '00000000-0000-4000-8000-000000000002',
  document_id: '00000000-0000-4000-8000-000000000003',
  document_version_id: '00000000-0000-4000-8000-000000000004',
  async_job_id: jobSummary.id,
  idempotency_key: 'extract-once',
  engine: 'tesseract',
  extraction_type: 'text',
  template: null,
  status: 'completed',
  raw_text: 'Invoice total 125.00',
  structured_data: { schema_version: '1.0', fields: [] },
  table_data: [],
  confidence: '0.9300',
  page_count: 1,
  processing_time_ms: 82,
  failure_code: '',
  failure_message: '',
  started_at: timestamp,
  completed_at: timestamp,
  transition_history: domainTransition,
  is_deleted: false,
  deleted_at: null,
  created_at: timestamp,
  updated_at: timestamp,
};

export const classificationDetail: DocumentClassification = {
  id: '00000000-0000-4000-8000-000000000020',
  tenant_id: extractionDetail.tenant_id,
  created_by: extractionDetail.created_by,
  document_id: extractionDetail.document_id,
  document_version_id: extractionDetail.document_version_id,
  async_job_id: jobSummary.id,
  idempotency_key: 'classify-once',
  model_version: '00000000-0000-4000-8000-000000000021',
  status: 'completed',
  category: 'invoice',
  confidence: '0.8800',
  secondary_category: 'receipt',
  secondary_confidence: '0.0900',
  needs_review: true,
  review_status: 'pending',
  reviewed_category: '',
  reviewed_by: null,
  reviewed_at: null,
  review_note: '',
  processing_time_ms: 40,
  failure_code: '',
  failure_message: '',
  completed_at: timestamp,
  transition_history: domainTransition,
  is_deleted: false,
  deleted_at: null,
  created_at: timestamp,
  updated_at: timestamp,
};

export const templateDetail: ExtractionTemplate = {
  id: '00000000-0000-4000-8000-000000000030',
  tenant_id: extractionDetail.tenant_id,
  created_by: extractionDetail.created_by,
  name: 'Invoice template',
  description: 'Normalized invoice evidence',
  document_category: 'invoice',
  engine: 'tesseract',
  match_threshold: '0.8000',
  status: 'draft',
  version: 1,
  activated_at: null,
  transition_history: domainTransition,
  zones: [],
  is_deleted: false,
  deleted_at: null,
  created_at: timestamp,
  updated_at: timestamp,
};

export const trainingDetail: ClassifierTrainingJobDetail = {
  id: '00000000-0000-4000-8000-000000000040',
  tenant_id: extractionDetail.tenant_id,
  created_by: extractionDetail.created_by,
  async_job_id: jobSummary.id,
  idempotency_key: 'train-once',
  name: 'Invoice classifier',
  training_items: [],
  training_data_count: 50,
  category_counts: { invoice: 25, receipt: 25 },
  requested_version: '2.0.0',
  status: 'training',
  accuracy: null,
  failure_code: '',
  failure_message: '',
  started_at: timestamp,
  completed_at: null,
  transition_history: domainTransition,
  created_at: timestamp,
  updated_at: timestamp,
  job: jobSummary,
};

export const candidateModel: ClassifierModelVersionListItem = {
  id: '00000000-0000-4000-8000-000000000050',
  tenant_id: extractionDetail.tenant_id,
  created_by: extractionDetail.created_by,
  version: '2.0.0',
  provider_key: 'local_classifier',
  training_job: trainingDetail.id,
  accuracy: '0.9100',
  status: 'candidate',
  activated_by: null,
  activated_at: null,
  retired_at: null,
  created_at: timestamp,
  updated_at: timestamp,
};

export const retiredModel: ClassifierModelVersionListItem = {
  ...candidateModel,
  id: '00000000-0000-4000-8000-000000000051',
  version: '1.0.0',
  status: 'retired',
  retired_at: timestamp,
};

export function modelDetail(model: ClassifierModelVersionListItem): ClassifierModelVersion {
  return {
    ...model,
    artifact_ref: 'tenant/models/model.bin',
    artifact_checksum: 'sha256:abc',
    transition_history: domainTransition,
  };
}

export function page<T>(items: readonly T[]): PaginatedResult<T> {
  return {
    items,
    pagination: {
      count: items.length,
      page: 1,
      page_size: 25,
      total_pages: items.length > 0 ? 1 : 0,
      has_next: false,
      has_previous: false,
    },
    correlationId: 'corr-workflow',
  };
}
