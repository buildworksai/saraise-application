import type {
  ClassifierModelVersion,
  ClassifierModelVersionListItem,
  ClassifierTrainingJobDetail,
  DocumentClassification,
  DocumentIntelligenceConfiguration,
  DocumentExtraction,
  ExtractionTemplate,
  JobSummary,
  PaginatedResult,
} from '../contracts';

export const timestamp = '2026-07-21T10:00:00Z';

export const documentIntelligenceConfiguration: DocumentIntelligenceConfiguration = {
  id: '00000000-0000-4000-8000-000000000001', tenant_id: '00000000-0000-4000-8000-000000000002',
  version: 1, environment: 'development', created_by: '00000000-0000-4000-8000-000000000003',
  updated_by: '00000000-0000-4000-8000-000000000003', created_at: timestamp, updated_at: timestamp,
  document: {
    limits: { max_document_bytes: 52_428_800, max_pages: 10_000, max_text_characters: 20_000_000, max_structured_bytes: 20_000_000, max_categories: 1_000, category_schema: 'lowercase_slug_v1', category_slug_max_length: 80, content_handle_max_length: 1_000, page_dimension_max: 1_000_000, search_max_length: 100 },
    providers: { allowed_mime_types: ['application/pdf'], allowed_extraction_types: ['text', 'structured', 'table', 'zone'], allowed_ocr_engines: ['tesseract'], default_ocr_engine: 'tesseract', default_classifier_provider: 'local_naive_bayes', artifact_root_environment_variable: 'DOCUMENT_INTELLIGENCE_ARTIFACT_ROOT' },
    extraction: { max_active: 5, stale_job_hours: 24 },
    classifier: { feature_buckets: 1_024, provider_max_categories: 100, minimum_training_documents: 50, minimum_documents_per_category: 5, activation_accuracy_threshold: 0.8, secondary_confidence_threshold: 0.3 },
    review: { low_confidence_threshold: 0.5, note_max_length: 4_000 },
    templates: { default_engine: 'tesseract', default_match_threshold: 0.7 },
    resilience: { stream_chunk_size_bytes: 1_048_576, timeout_seconds: 300, max_attempts: 3, initial_backoff_seconds: 0.25, max_backoff_seconds: 4, jitter_ratio: 0.2, circuit_failure_threshold: 5, circuit_recovery_seconds: 30 },
    health: { stale_after_seconds: 30 },
    observability: { provider_duration_buckets_seconds: [0.1, 1, 10], queue_delay_buckets_seconds: [1, 10, 60] },
    editor: { new_zone: { x: 0.1, y: 0.1, width: 0.3, height: 0.1, page_number: 1, zone_type: 'text', expected_data_type: 'string', is_required: false }, coordinate_snap: 0.01, coordinate_precision: 4, undo_history_limit: 20, zoom_min_percent: 70, zoom_max_percent: 150, zoom_step_percent: 10 },
    ui: { page_size: 25, template_zone_page_size: 100, poll_interval_ms: 5_000, stale_after_ms: 15_000, confidence_filter_presets: [0.5, 0.8, 0.95], positive_statuses: ['completed', 'active', 'confirmed'], warning_statuses: ['needs_review', 'pending', 'timed_out'], navigation_order: { extractions: 300, classifications: 310, training: 320, templates: 330, health: 340, configuration: 350 } },
    feature_flags: { auto_classification_enabled: false, rollout_percentage: 0, allowed_roles: [], allowed_cohorts: [] },
    workflows: { extraction: [], classification: [], training: [], model_version: [], template: [] },
  },
};

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
