/** Typed v2 contract for the open-source compliance workspace. */
export type UUID = string;
export type ISODate = string;
export type ISODateTime = string;

export interface EnvelopeMeta { correlation_id: UUID; timestamp: ISODateTime }
export interface PaginationMeta { page: number; page_size: number; count: number; total_pages: number; has_next: boolean; has_previous: boolean }
export interface SuccessEnvelope<T> { data: T; meta: EnvelopeMeta }
export interface PaginatedEnvelope<T> { data: readonly T[]; meta: EnvelopeMeta & { pagination: PaginationMeta } }
export interface FieldError { field: string; code: string; message: string }
export interface StableErrorDTO { error: { code: string; message: string; correlation_id?: UUID; field_errors?: readonly FieldError[]; retry_after?: number } }

export interface AuditFields { created_at: ISODateTime; updated_at: ISODateTime; created_by: UUID | null; updated_by: UUID | null; deleted_at: ISODateTime | null; deleted_by: UUID | null }
export type AllowedActions = readonly string[];
export type FrameworkStatus = 'draft' | 'active' | 'archived';
export type PolicyStatus = 'draft' | 'in_review' | 'approved' | 'published' | 'archived';
export type RequirementStatus = 'active' | 'archived';
export type AssessmentStatus = 'not_assessed' | 'in_progress' | 'compliant' | 'partial' | 'non_compliant' | 'not_applicable';

export interface ComplianceFramework extends AuditFields { id: UUID; code: string; name: string; version: string; category: string; description: string; source_kind: 'custom' | 'imported' | 'extension'; source_package: string; source_version: string; status: FrameworkStatus; requirement_count?: number; allowed_actions?: AllowedActions }
export interface FrameworkWriteRequest { code: string; name: string; version: string; category: string; description?: string; source_kind: ComplianceFramework['source_kind']; source_package?: string; source_version?: string }
export type FrameworkUpdateRequest = Partial<FrameworkWriteRequest>;
export interface FrameworkImportRequest { schema: 'saraise.compliance.framework/v1'; framework: FrameworkWriteRequest; requirements: readonly Omit<RequirementWriteRequest, 'framework_id'>[] }
export interface FrameworkStatusSnapshot { framework: ComplianceFramework; readiness: ScorecardDTO; gaps: GapAnalysisDTO }

export interface ComplianceRequirement extends AuditFields { id: UUID; framework: UUID; framework_code?: string; code: string; title: string; description: string; section: string; guidance: string; applicability: 'applicable' | 'not_applicable'; applicability_rationale: string; status: RequirementStatus; sort_order: number; tags: readonly string[]; latest_assessment?: ComplianceAssessment | null; mapping_count?: number; evidence_count?: number; gap_status?: string; allowed_actions?: AllowedActions }
export interface RequirementWriteRequest { framework_id: UUID; code: string; title: string; description: string; section?: string; guidance?: string; applicability?: ComplianceRequirement['applicability']; applicability_rationale?: string; sort_order?: number; tags?: readonly string[] }
export type RequirementUpdateRequest = Partial<RequirementWriteRequest>;
export interface RequirementBulkImportRequest { framework_id: UUID; rows: readonly RequirementWriteRequest[] }

export interface CompliancePolicy extends AuditFields { id: UUID; code: string; title: string; summary: string; category: string; owner: UUID | null; owner_name?: string; review_frequency_days: number; effective_date: ISODate | null; expiry_date: ISODate | null; next_review_date: ISODate | null; status: PolicyStatus; current_version: number; versions?: readonly CompliancePolicyVersion[]; mapping_count?: number; allowed_actions?: AllowedActions }
export interface CompliancePolicyVersion { id: UUID; policy: UUID; version: number; content: string; content_sha256: string; change_summary: string; created_by: UUID | null; created_at: ISODateTime; approved_by: UUID | null; approved_at: ISODateTime | null; published_by: UUID | null; published_at: ISODateTime | null }
export interface PolicyWriteRequest { code: string; title: string; summary?: string; category: string; owner_id?: string | null; review_frequency_days?: number; effective_date?: ISODate | null; expiry_date?: ISODate | null }
export type PolicyUpdateRequest = Partial<PolicyWriteRequest>;
export interface PolicyVersionCreateRequest { content: string; change_summary: string }
export interface TransitionRequest { transition_key: string; reason?: string }
export interface PolicyReviseRequest extends TransitionRequest { content: string; change_summary: string }

export interface RequirementPolicyMapping extends AuditFields { id: UUID; requirement: UUID; requirement_code?: string; policy: UUID; policy_code?: string; policy_version: UUID | null; coverage: 'none' | 'partial' | 'full' | 'not_applicable'; rationale: string; mapped_at: ISODateTime }
export interface MappingWriteRequest { requirement_id: UUID; policy_id: UUID; policy_version_id?: UUID | null; coverage: RequirementPolicyMapping['coverage']; rationale?: string }
export interface MappingBulkRequest { rows: readonly MappingWriteRequest[] }
export interface GapDTO { requirement_id: UUID; code: string; title: string; coverage: 'none' | 'partial'; reason: string }
export interface GapAnalysisDTO { framework_id: UUID; total: number; gap_count: number; gaps: readonly GapDTO[] }

export interface ComplianceAssessment { id: UUID; requirement: UUID; requirement_code?: string; mapping: UUID | null; status: AssessmentStatus; notes: string; assessor: UUID | null; assessed_at: ISODateTime; due_date: ISODate | null; source: 'manual' | 'import' | 'extension'; created_at: ISODateTime }
export interface AssessmentCreateRequest { requirement_id: UUID; mapping_id?: UUID | null; status: AssessmentStatus; notes?: string; due_date?: ISODate | null; assessed_at?: ISODateTime; source?: 'manual' | 'import' | 'extension' }
export interface ScorecardDTO { framework_id: UUID; score: number; earned_points: number; possible_points: number; formula: string; requirements: readonly { requirement_id: UUID; code: string; status: AssessmentStatus; points: number }[] }

export interface ComplianceEvidence extends AuditFields { id: UUID; name: string; description: string; evidence_type: 'document' | 'report' | 'screenshot' | 'log' | 'attestation' | 'external_reference'; reference_kind: 'dms_document' | 'external_url' | 'text_reference'; document_id: UUID | null; external_uri: string; text_reference: string; sha256: string; classification: 'public' | 'internal' | 'confidential' | 'restricted'; collection_method: 'manual' | 'import' | 'extension'; collected_by: string | null; collected_at: ISODateTime; valid_from: ISODateTime | null; valid_until: ISODateTime | null; requirement_links?: readonly EvidenceRequirementLink[]; allowed_actions?: AllowedActions }
export interface EvidenceWriteRequest { name: string; description?: string; evidence_type: ComplianceEvidence['evidence_type']; reference_kind: ComplianceEvidence['reference_kind']; document_id?: UUID | null; external_uri?: string; text_reference?: string; sha256?: string; classification: ComplianceEvidence['classification']; collection_method?: ComplianceEvidence['collection_method']; collected_at?: ISODateTime; valid_from?: ISODateTime | null; valid_until?: ISODateTime | null }
export type EvidenceUpdateRequest = Partial<EvidenceWriteRequest>;
export interface EvidenceRequirementLink { id: UUID; evidence: UUID; requirement: UUID; requirement_code?: string; relevance: string; created_at: ISODateTime }
export interface EvidenceLinkRequest { requirement_id: UUID; relevance: 'supporting' | 'primary' | 'contradicting'; notes?: string }
export interface EvidenceValidationDTO { evidence_id: UUID; reference_valid: boolean; hash_valid: boolean; fresh: boolean; checked_at: ISODateTime }

export type RuntimeEnvironment = 'development' | 'staging' | 'production';
export interface RolloutRule { enabled?: boolean; roles?: readonly string[]; cohorts?: readonly string[] }
export type RolloutConfiguration = Readonly<Record<string, RolloutRule>>;
export interface ComplianceConfigurationDocument { policy_code_prefix: string; default_review_frequency_days: number; expiry_warning_days: number; evidence_warning_days: number; minimum_assessment_note_length: number; allow_external_evidence_urls: boolean; bulk_import_row_limit: number; regulation_categories: readonly string[]; rollout: RolloutConfiguration }
export interface ComplianceConfigurationRevision { id: UUID; environment: RuntimeEnvironment; version: number; status: 'draft' | 'active' | 'superseded'; policy_code_prefix: string; default_review_frequency_days: number; expiry_warning_days: number; evidence_warning_days: number; minimum_assessment_note_length: number; allow_external_evidence_urls: boolean; bulk_import_row_limit: number; regulation_categories: readonly string[]; rollout: RolloutConfiguration; document: ComplianceConfigurationDocument; created_by: string | null; created_at: ISODateTime; activated_at: ISODateTime | null; activated_by: string | null; allowed_actions?: AllowedActions }
export interface ConfigurationWriteRequest { environment: RuntimeEnvironment; document: ComplianceConfigurationDocument }
export interface ConfigurationPortableDocument { schema: 'saraise.compliance.configuration/v1'; environment: RuntimeEnvironment; configuration: ComplianceConfigurationDocument }
export interface ConfigurationDiff { field: string; before: unknown; after: unknown }
export interface ConfigurationPreviewDTO { revision_id: UUID; environment: RuntimeEnvironment; diff: readonly ConfigurationDiff[]; affected: { frameworks: number; policies: number; evidence: number } }

export interface ComplianceActivity { id: UUID; entity_type: string; entity_id: UUID; action: string; actor: string | null; occurred_at: ISODateTime; correlation_id: UUID; reason: string; before: Readonly<Record<string, unknown>>; after: Readonly<Record<string, unknown>> }
export interface DashboardSummaryDTO { frameworks: number; requirements: number; unassessed_requirements: number; gaps: number; review_queue: number; expiring_evidence: number }
export interface AsyncJobDTO { id: UUID; command: string; status: 'queued' | 'running' | 'succeeded' | 'failed' | 'timed_out' | 'cancelled'; progress: number; created_at: ISODateTime; completed_at: ISODateTime | null; error_code: string; result: Readonly<Record<string, unknown>> | null }

export interface ListQuery { page?: number; page_size?: number; search?: string; ordering?: string }
export interface FrameworkFilters extends ListQuery { status?: FrameworkStatus; category?: string; source_kind?: ComplianceFramework['source_kind'] }
export interface RequirementFilters extends ListQuery { framework_id?: UUID; status?: RequirementStatus; applicability?: ComplianceRequirement['applicability'] }
export interface PolicyFilters extends ListQuery { status?: PolicyStatus; category?: string; owner_id?: UUID; review_due_before?: ISODate; expiry_before?: ISODate }
export interface MappingFilters extends ListQuery { framework_id?: UUID; requirement_id?: UUID; policy_id?: UUID; coverage?: RequirementPolicyMapping['coverage'] }
export interface AssessmentFilters extends ListQuery { framework_id?: UUID; requirement_id?: UUID; status?: AssessmentStatus; due_before?: ISODate; due_after?: ISODate }
export interface EvidenceFilters extends ListQuery { type?: ComplianceEvidence['evidence_type']; classification?: ComplianceEvidence['classification']; requirement_id?: UUID; valid_before?: ISODate }
export interface ConfigurationFilters extends ListQuery { environment?: RuntimeEnvironment; status?: ComplianceConfigurationRevision['status'] }
export interface ActivityFilters extends ListQuery { entity_type?: string; entity_id?: UUID; actor_id?: UUID; action?: string; correlation_id?: UUID; occurred_after?: ISODateTime; occurred_before?: ISODateTime }

export const MODULE_API_PREFIX = '/api/v2/compliance-management';
const detail = (resource: string, id: UUID) => `${MODULE_API_PREFIX}/${resource}/${id}/` as const;
export const ENDPOINTS = {
  FRAMEWORKS: { LIST: `${MODULE_API_PREFIX}/frameworks/`, CREATE: `${MODULE_API_PREFIX}/frameworks/`, DETAIL: (id: UUID) => detail('frameworks', id), UPDATE: (id: UUID) => detail('frameworks', id), DELETE: (id: UUID) => detail('frameworks', id), ACTIVATE: (id: UUID) => `${detail('frameworks', id)}activate/` as const, EXPORT: (id: UUID) => `${detail('frameworks', id)}export/` as const, IMPORT: `${MODULE_API_PREFIX}/frameworks/import/`, STATUS: (id: UUID) => `${detail('frameworks', id)}status/` as const },
  REQUIREMENTS: { LIST: `${MODULE_API_PREFIX}/requirements/`, CREATE: `${MODULE_API_PREFIX}/requirements/`, DETAIL: (id: UUID) => detail('requirements', id), UPDATE: (id: UUID) => detail('requirements', id), DELETE: (id: UUID) => detail('requirements', id), RESTORE: (id: UUID) => `${detail('requirements', id)}restore/` as const, IMPORT: `${MODULE_API_PREFIX}/requirements/import/` },
  POLICIES: { LIST: `${MODULE_API_PREFIX}/policies/`, CREATE: `${MODULE_API_PREFIX}/policies/`, DETAIL: (id: UUID) => detail('policies', id), UPDATE: (id: UUID) => detail('policies', id), DELETE: (id: UUID) => detail('policies', id), VERSIONS: (id: UUID) => `${detail('policies', id)}versions/` as const, SUBMIT: (id: UUID) => `${detail('policies', id)}submit/` as const, REQUEST_CHANGES: (id: UUID) => `${detail('policies', id)}request-changes/` as const, APPROVE: (id: UUID) => `${detail('policies', id)}approve/` as const, PUBLISH: (id: UUID) => `${detail('policies', id)}publish/` as const, REVISE: (id: UUID) => `${detail('policies', id)}revise/` as const },
  MAPPINGS: { LIST: `${MODULE_API_PREFIX}/mappings/`, CREATE: `${MODULE_API_PREFIX}/mappings/`, DETAIL: (id: UUID) => detail('mappings', id), UPDATE: (id: UUID) => detail('mappings', id), DELETE: (id: UUID) => detail('mappings', id), BULK: `${MODULE_API_PREFIX}/mappings/bulk/` },
  GAPS: `${MODULE_API_PREFIX}/gaps/`,
  ASSESSMENTS: { LIST: `${MODULE_API_PREFIX}/assessments/`, CREATE: `${MODULE_API_PREFIX}/assessments/`, DETAIL: (id: UUID) => detail('assessments', id), SCORECARD: `${MODULE_API_PREFIX}/assessments/scorecard/` },
  EVIDENCE: { LIST: `${MODULE_API_PREFIX}/evidence/`, CREATE: `${MODULE_API_PREFIX}/evidence/`, DETAIL: (id: UUID) => detail('evidence', id), UPDATE: (id: UUID) => detail('evidence', id), DELETE: (id: UUID) => detail('evidence', id), VALIDATE: (id: UUID) => `${detail('evidence', id)}validate/` as const, REQUIREMENTS: (id: UUID) => `${detail('evidence', id)}requirements/` as const },
  EVIDENCE_LINKS: { DELETE: (id: UUID) => detail('evidence-links', id) },
  CONFIGURATION: { LIST: `${MODULE_API_PREFIX}/configuration/`, CREATE: `${MODULE_API_PREFIX}/configuration/`, DETAIL: (id: UUID) => detail('configuration', id), UPDATE: (id: UUID) => detail('configuration', id), PREVIEW: (id: UUID) => `${detail('configuration', id)}preview/` as const, ACTIVATE: (id: UUID) => `${detail('configuration', id)}activate/` as const, ROLLBACK: (id: UUID) => `${detail('configuration', id)}rollback/` as const, EXPORT: (id: UUID) => `${detail('configuration', id)}export/` as const, IMPORT: `${MODULE_API_PREFIX}/configuration/import/` },
  ACTIVITY: `${MODULE_API_PREFIX}/activity/`, DASHBOARD: `${MODULE_API_PREFIX}/dashboard/`, JOB: (id: UUID) => detail('jobs', id),
} as const;

export const ROUTES = {
  DASHBOARD: '/compliance-management', FRAMEWORKS: '/compliance-management/frameworks', FRAMEWORK_CREATE: '/compliance-management/frameworks/new', FRAMEWORK_DETAIL: (id: UUID) => `/compliance-management/frameworks/${id}`, FRAMEWORK_EDIT: (id: UUID) => `/compliance-management/frameworks/${id}/edit`,
  REQUIREMENTS: '/compliance-management/requirements', REQUIREMENT_CREATE: '/compliance-management/requirements/new', REQUIREMENT_DETAIL: (id: UUID) => `/compliance-management/requirements/${id}`, REQUIREMENT_EDIT: (id: UUID) => `/compliance-management/requirements/${id}/edit`,
  POLICIES: '/compliance-management/policies', POLICY_CREATE: '/compliance-management/policies/new', POLICY_DETAIL: (id: UUID) => `/compliance-management/policies/${id}`, POLICY_EDIT: (id: UUID) => `/compliance-management/policies/${id}/edit`,
  MAPPINGS: '/compliance-management/mappings', ASSESSMENTS: '/compliance-management/assessments', ASSESSMENT_CREATE: '/compliance-management/assessments/new',
  EVIDENCE: '/compliance-management/evidence', EVIDENCE_CREATE: '/compliance-management/evidence/new', EVIDENCE_DETAIL: (id: UUID) => `/compliance-management/evidence/${id}`, EVIDENCE_EDIT: (id: UUID) => `/compliance-management/evidence/${id}/edit`,
  CONFIGURATION: '/compliance-management/configuration', CONFIGURATION_DETAIL: (id: UUID) => `/compliance-management/configuration/${id}`, CONFIGURATION_EDIT: (id: UUID) => `/compliance-management/configuration/${id}/edit`, ACTIVITY: '/compliance-management/activity',
} as const;
