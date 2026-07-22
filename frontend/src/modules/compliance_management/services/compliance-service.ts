import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';
import type {
  ActivityFilters, AssessmentCreateRequest, AssessmentFilters, AsyncJobDTO, ComplianceActivity,
  ComplianceAssessment, ComplianceConfigurationRevision, ComplianceEvidence, ComplianceFramework,
  CompliancePolicy, CompliancePolicyVersion, ComplianceRequirement, ConfigurationFilters,
  ConfigurationPortableDocument, ConfigurationPreviewDTO, ConfigurationWriteRequest, DashboardSummaryDTO, EvidenceFilters,
  EvidenceLinkRequest, EvidenceUpdateRequest, EvidenceValidationDTO, EvidenceWriteRequest,
  FrameworkFilters, FrameworkImportRequest, FrameworkStatusSnapshot, FrameworkUpdateRequest,
  FrameworkWriteRequest, GapAnalysisDTO, ListQuery, MappingBulkRequest, MappingFilters,
  MappingWriteRequest, PaginatedEnvelope, PolicyFilters, PolicyReviseRequest,
  PolicyUpdateRequest, PolicyVersionCreateRequest, PolicyWriteRequest, RequirementBulkImportRequest,
  RequirementFilters, RequirementPolicyMapping, RequirementUpdateRequest, RequirementWriteRequest,
  ScorecardDTO, StableErrorDTO, SuccessEnvelope, TransitionRequest, UUID,
} from '../contracts';

type QueryValue = string | number | boolean | null | undefined;

export class ComplianceContractError extends Error {
  constructor(message: string) { super(message); this.name = 'ComplianceContractError'; }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function requireSuccess<T>(response: SuccessEnvelope<T>): T {
  if (!isObject(response) || !('data' in response) || !isObject(response.meta) || typeof response.meta.correlation_id !== 'string') {
    throw new ComplianceContractError('The compliance API returned an invalid governed success envelope.');
  }
  return response.data;
}

function requirePage<T>(response: PaginatedEnvelope<T>): PaginatedEnvelope<T> {
  if (!isObject(response) || !Array.isArray(response.data) || !isObject(response.meta) || !isObject(response.meta.pagination) || typeof response.meta.correlation_id !== 'string') {
    throw new ComplianceContractError('The compliance API returned an invalid governed paginated envelope.');
  }
  return response;
}

const configurationDocument = (revision: ComplianceConfigurationRevision): ComplianceConfigurationRevision['document'] => {
  return {
    policy_code_prefix: revision.policy_code_prefix,
    default_review_frequency_days: revision.default_review_frequency_days,
    expiry_warning_days: revision.expiry_warning_days,
    evidence_warning_days: revision.evidence_warning_days,
    minimum_assessment_note_length: revision.minimum_assessment_note_length,
    allow_external_evidence_urls: revision.allow_external_evidence_urls,
    bulk_import_row_limit: revision.bulk_import_row_limit,
    regulation_categories: revision.regulation_categories,
    rollout: revision.rollout,
  };
};
const configurationRevision = (revision: ComplianceConfigurationRevision): ComplianceConfigurationRevision => ({ ...revision, document: configurationDocument(revision) });
const configurationPayload = ({ environment, document }: ConfigurationWriteRequest) => ({
  environment,
  policy_code_prefix: document.policy_code_prefix,
  default_review_frequency_days: document.default_review_frequency_days,
  expiry_warning_days: document.expiry_warning_days,
  evidence_warning_days: document.evidence_warning_days,
  minimum_assessment_note_length: document.minimum_assessment_note_length,
  allow_external_evidence_urls: document.allow_external_evidence_urls,
  bulk_import_row_limit: document.bulk_import_row_limit,
  regulation_categories: document.regulation_categories,
  rollout: document.rollout,
});

export function serializeQuery(path: string, query: object): string {
  const params = new URLSearchParams();
  Object.entries(query as Readonly<Record<string, QueryValue>>).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  const serialized = params.toString();
  return serialized ? `${path}?${serialized}` : path;
}

export function createIdempotencyKey(scope: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `compliance-ui:${scope}:${suffix}`;
}

const keyHeader = (key: string): RequestInit => ({ headers: { 'Idempotency-Key': key } });
const get = async <T>(path: string): Promise<T> => requireSuccess(await apiClient.get<SuccessEnvelope<T>>(path));
const page = async <T>(path: string, query: object = {}): Promise<PaginatedEnvelope<T>> => requirePage(await apiClient.get<PaginatedEnvelope<T>>(serializeQuery(path, query)));
const post = async <T>(path: string, body: unknown, key?: string): Promise<T> => requireSuccess(await apiClient.post<SuccessEnvelope<T>>(path, body, key ? keyHeader(key) : undefined));
const patch = async <T>(path: string, body: unknown): Promise<T> => requireSuccess(await apiClient.patch<SuccessEnvelope<T>>(path, body));

export const complianceService = {
  frameworks: {
    list: (filters: FrameworkFilters = {}) => page<ComplianceFramework>(ENDPOINTS.FRAMEWORKS.LIST, filters),
    get: (id: UUID) => get<ComplianceFramework>(ENDPOINTS.FRAMEWORKS.DETAIL(id)),
    create: (body: FrameworkWriteRequest) => post<ComplianceFramework>(ENDPOINTS.FRAMEWORKS.CREATE, body),
    update: (id: UUID, body: FrameworkUpdateRequest) => patch<ComplianceFramework>(ENDPOINTS.FRAMEWORKS.UPDATE(id), body),
    archive: (id: UUID) => apiClient.delete<void>(ENDPOINTS.FRAMEWORKS.DELETE(id)),
    activate: (id: UUID, body: TransitionRequest) => post<ComplianceFramework>(ENDPOINTS.FRAMEWORKS.ACTIVATE(id), body, body.transition_key),
    status: (id: UUID) => get<FrameworkStatusSnapshot>(ENDPOINTS.FRAMEWORKS.STATUS(id)),
    export: (id: UUID) => get<FrameworkImportRequest>(ENDPOINTS.FRAMEWORKS.EXPORT(id)),
    import: (body: FrameworkImportRequest, key: string) => post<ComplianceFramework | AsyncJobDTO>(ENDPOINTS.FRAMEWORKS.IMPORT, { package: body }, key),
  },
  requirements: {
    list: (filters: RequirementFilters = {}) => page<ComplianceRequirement>(ENDPOINTS.REQUIREMENTS.LIST, filters),
    get: (id: UUID) => get<ComplianceRequirement>(ENDPOINTS.REQUIREMENTS.DETAIL(id)),
    create: (body: RequirementWriteRequest) => post<ComplianceRequirement>(ENDPOINTS.REQUIREMENTS.CREATE, body),
    update: (id: UUID, body: RequirementUpdateRequest) => patch<ComplianceRequirement>(ENDPOINTS.REQUIREMENTS.UPDATE(id), body),
    archive: (id: UUID) => apiClient.delete<void>(ENDPOINTS.REQUIREMENTS.DELETE(id)),
    restore: (id: UUID, body: TransitionRequest) => post<ComplianceRequirement>(ENDPOINTS.REQUIREMENTS.RESTORE(id), body, body.transition_key),
    import: (body: RequirementBulkImportRequest, key: string) => post<readonly ComplianceRequirement[] | AsyncJobDTO>(ENDPOINTS.REQUIREMENTS.IMPORT, body, key),
  },
  policies: {
    list: (filters: PolicyFilters = {}) => page<CompliancePolicy>(ENDPOINTS.POLICIES.LIST, filters),
    get: (id: UUID) => get<CompliancePolicy>(ENDPOINTS.POLICIES.DETAIL(id)),
    create: (body: PolicyWriteRequest) => post<CompliancePolicy>(ENDPOINTS.POLICIES.CREATE, body),
    update: (id: UUID, body: PolicyUpdateRequest) => patch<CompliancePolicy>(ENDPOINTS.POLICIES.UPDATE(id), body),
    archive: (id: UUID) => apiClient.delete<void>(ENDPOINTS.POLICIES.DELETE(id)),
    versions: (id: UUID, filters: ListQuery = {}) => page<CompliancePolicyVersion>(ENDPOINTS.POLICIES.VERSIONS(id), filters),
    createVersion: (id: UUID, body: PolicyVersionCreateRequest, key: string) => post<CompliancePolicyVersion>(ENDPOINTS.POLICIES.VERSIONS(id), body, key),
    transition: (id: UUID, action: 'submit' | 'request-changes' | 'approve' | 'publish', body: TransitionRequest) => {
      const endpoint = { submit: ENDPOINTS.POLICIES.SUBMIT, 'request-changes': ENDPOINTS.POLICIES.REQUEST_CHANGES, approve: ENDPOINTS.POLICIES.APPROVE, publish: ENDPOINTS.POLICIES.PUBLISH }[action];
      return post<CompliancePolicy>(endpoint(id), body, body.transition_key);
    },
    revise: (id: UUID, body: PolicyReviseRequest) => post<CompliancePolicy>(ENDPOINTS.POLICIES.REVISE(id), body, body.transition_key),
  },
  mappings: {
    list: (filters: MappingFilters = {}) => page<RequirementPolicyMapping>(ENDPOINTS.MAPPINGS.LIST, filters),
    get: (id: UUID) => get<RequirementPolicyMapping>(ENDPOINTS.MAPPINGS.DETAIL(id)),
    create: (body: MappingWriteRequest, key: string) => post<RequirementPolicyMapping>(ENDPOINTS.MAPPINGS.CREATE, body, key),
    update: (id: UUID, body: Partial<MappingWriteRequest>) => patch<RequirementPolicyMapping>(ENDPOINTS.MAPPINGS.UPDATE(id), body),
    remove: (id: UUID) => apiClient.delete<void>(ENDPOINTS.MAPPINGS.DELETE(id)),
    bulk: (body: MappingBulkRequest, key: string) => post<readonly RequirementPolicyMapping[]>(ENDPOINTS.MAPPINGS.BULK, body, key),
    gaps: (frameworkId: UUID, asOf?: string) => get<GapAnalysisDTO>(serializeQuery(ENDPOINTS.GAPS, { framework_id: frameworkId, as_of: asOf })),
  },
  assessments: {
    list: (filters: AssessmentFilters = {}) => page<ComplianceAssessment>(ENDPOINTS.ASSESSMENTS.LIST, filters),
    get: (id: UUID) => get<ComplianceAssessment>(ENDPOINTS.ASSESSMENTS.DETAIL(id)),
    create: (body: AssessmentCreateRequest, key: string) => post<ComplianceAssessment>(ENDPOINTS.ASSESSMENTS.CREATE, body, key),
    scorecard: (frameworkId: UUID, asOf?: string) => get<ScorecardDTO>(serializeQuery(ENDPOINTS.ASSESSMENTS.SCORECARD, { framework_id: frameworkId, as_of: asOf })),
  },
  evidence: {
    list: (filters: EvidenceFilters = {}) => page<ComplianceEvidence>(ENDPOINTS.EVIDENCE.LIST, filters),
    get: (id: UUID) => get<ComplianceEvidence>(ENDPOINTS.EVIDENCE.DETAIL(id)),
    create: (body: EvidenceWriteRequest) => post<ComplianceEvidence>(ENDPOINTS.EVIDENCE.CREATE, body),
    update: (id: UUID, body: EvidenceUpdateRequest) => patch<ComplianceEvidence>(ENDPOINTS.EVIDENCE.UPDATE(id), body),
    archive: (id: UUID) => apiClient.delete<void>(ENDPOINTS.EVIDENCE.DELETE(id)),
    validate: (id: UUID, key = createIdempotencyKey('validate-evidence')) => post<EvidenceValidationDTO>(ENDPOINTS.EVIDENCE.VALIDATE(id), {}, key),
    link: (id: UUID, body: EvidenceLinkRequest) => post<ComplianceEvidence>(ENDPOINTS.EVIDENCE.REQUIREMENTS(id), body),
    unlink: (id: UUID) => apiClient.delete<void>(ENDPOINTS.EVIDENCE_LINKS.DELETE(id)),
  },
  configuration: {
    list: async (filters: ConfigurationFilters = {}) => { const result = await page<ComplianceConfigurationRevision>(ENDPOINTS.CONFIGURATION.LIST, filters); return { ...result, data: result.data.map(configurationRevision) }; },
    get: async (id: UUID) => configurationRevision(await get<ComplianceConfigurationRevision>(ENDPOINTS.CONFIGURATION.DETAIL(id))),
    create: async (body: ConfigurationWriteRequest) => configurationRevision(await post<ComplianceConfigurationRevision>(ENDPOINTS.CONFIGURATION.CREATE, configurationPayload(body))),
    update: async (id: UUID, body: ConfigurationWriteRequest) => configurationRevision(await patch<ComplianceConfigurationRevision>(ENDPOINTS.CONFIGURATION.UPDATE(id), configurationPayload(body))),
    preview: (id: UUID) => get<ConfigurationPreviewDTO>(ENDPOINTS.CONFIGURATION.PREVIEW(id)),
    activate: async (id: UUID, body: TransitionRequest) => configurationRevision(await post<ComplianceConfigurationRevision>(ENDPOINTS.CONFIGURATION.ACTIVATE(id), body, body.transition_key)),
    rollback: async (id: UUID, body: TransitionRequest) => configurationRevision(await post<ComplianceConfigurationRevision>(ENDPOINTS.CONFIGURATION.ROLLBACK(id), body, body.transition_key)),
    export: (id: UUID) => get<ConfigurationPortableDocument>(ENDPOINTS.CONFIGURATION.EXPORT(id)),
    import: async (document: ConfigurationPortableDocument, key: string) => configurationRevision(await post<ComplianceConfigurationRevision>(ENDPOINTS.CONFIGURATION.IMPORT, { document }, key)),
  },
  activity: (filters: ActivityFilters = {}) => page<ComplianceActivity>(ENDPOINTS.ACTIVITY, filters),
  dashboard: (frameworkId?: UUID, asOf?: string) => get<DashboardSummaryDTO>(serializeQuery(ENDPOINTS.DASHBOARD, { framework_id: frameworkId, as_of: asOf })),
  job: (id: UUID) => get<AsyncJobDTO>(ENDPOINTS.JOB(id)),
};

export function fieldError(error: unknown, field: string): string | undefined {
  if (!isObject(error) || !('details' in error) || !isObject(error.details)) return undefined;
  const details = error.details as unknown as StableErrorDTO;
  return details.error?.field_errors?.find((item) => item.field === field)?.message;
}
