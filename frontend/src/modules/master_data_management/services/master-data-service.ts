import { apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiListSuccess,
  type ApiSuccess,
  type AssignQualityIssueRequest,
  type AsyncJob,
  type DataQualityIssue,
  type DataQualityRule,
  type DataQualityRuleUpdateRequest,
  type DataQualityRuleWriteRequest,
  type DeduplicationScanRequest,
  type DeactivateTypeRequest,
  type EntityFilters,
  type EntityTypeFilters,
  type EntityVersionActionRequest,
  type ItemResult,
  type ListResult,
  type MasterDataEntity,
  type MasterDataEntityCreateRequest,
  type MasterDataEntityListItem,
  type MasterDataEntityUpdateRequest,
  type MasterDataVersion,
  type MasterEntityType,
  type MasterEntityTypeCreateRequest,
  type MasterEntityTypeUpdateRequest,
  type MatchCandidate,
  type MatchCandidateFilters,
  type MatchingRule,
  type MatchingRuleFilters,
  type MatchingRuleUpdateRequest,
  type MatchingRuleWriteRequest,
  type MatchPreviewRequest,
  type MatchResult,
  type MatchReviewRequest,
  type MDMSummary,
  type MergeFilters,
  type MergeHistory,
  type MergePreview,
  type MergePreviewRequest,
  type MergeRequest,
  type QualityIssueFilters,
  type QualityReport,
  type QualityRuleFilters,
  type QualityScanRequest,
  type ResolveQualityIssueRequest,
  type ReverseMergeRequest,
  type RollbackEntityRequest,
  type UUID,
  type ValidationReport,
} from "../contracts";

function withQuery(path: string, query?: object): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if ((typeof value === "string" || typeof value === "number" || typeof value === "boolean") && value !== "") params.set(key, String(value));
  }
  const serialized = params.toString();
  return serialized ? `${path}?${serialized}` : path;
}

function item<T>(response: ApiSuccess<T>): ItemResult<T> {
  return { data: response.data, meta: response.meta };
}

function list<T>(response: ApiListSuccess<T>): ListResult<T> {
  return { items: response.data, pagination: response.meta.pagination, meta: response.meta };
}

async function getItem<T>(path: string): Promise<ItemResult<T>> {
  return item(await apiClient.get<ApiSuccess<T>>(path));
}

async function getList<T>(path: string, filters?: object): Promise<ListResult<T>> {
  return list(await apiClient.get<ApiListSuccess<T>>(withQuery(path, filters)));
}

export const masterDataService = {
  dashboard: {
    get: (entityTypeId?: UUID) => getItem<MDMSummary>(withQuery(ENDPOINTS.DASHBOARD, { entity_type: entityTypeId })),
  },
  entityTypes: {
    list: (filters: EntityTypeFilters = {}) => getList<MasterEntityType>(ENDPOINTS.ENTITY_TYPES.LIST, filters),
    get: (id: UUID) => getItem<MasterEntityType>(ENDPOINTS.ENTITY_TYPES.DETAIL(id)),
    create: async (request: MasterEntityTypeCreateRequest) => item(await apiClient.post<ApiSuccess<MasterEntityType>>(ENDPOINTS.ENTITY_TYPES.CREATE, request)),
    update: async (id: UUID, request: MasterEntityTypeUpdateRequest) => item(await apiClient.patch<ApiSuccess<MasterEntityType>>(ENDPOINTS.ENTITY_TYPES.UPDATE(id), request)),
    deactivate: async (id: UUID, request: DeactivateTypeRequest) => item(await apiClient.post<ApiSuccess<MasterEntityType>>(ENDPOINTS.ENTITY_TYPES.DEACTIVATE(id), request)),
  },
  entities: {
    list: (filters: EntityFilters = {}) => getList<MasterDataEntityListItem>(ENDPOINTS.ENTITIES.LIST, filters),
    get: (id: UUID) => getItem<MasterDataEntity>(ENDPOINTS.ENTITIES.DETAIL(id)),
    create: async (request: MasterDataEntityCreateRequest) => item(await apiClient.post<ApiSuccess<MasterDataEntity>>(ENDPOINTS.ENTITIES.CREATE, request)),
    update: async (id: UUID, request: MasterDataEntityUpdateRequest) => item(await apiClient.patch<ApiSuccess<MasterDataEntity>>(ENDPOINTS.ENTITIES.UPDATE(id), request)),
    archive: async (id: UUID, request: EntityVersionActionRequest) => apiClient.delete<void>(ENDPOINTS.ENTITIES.ARCHIVE(id), { body: JSON.stringify(request) }),
    restore: async (id: UUID, request: EntityVersionActionRequest) => item(await apiClient.post<ApiSuccess<MasterDataEntity>>(ENDPOINTS.ENTITIES.RESTORE(id), request)),
    versions: (id: UUID, page = 1) => getList<MasterDataVersion>(ENDPOINTS.ENTITIES.VERSIONS(id), { page }),
    version: (id: UUID, version: number) => getItem<MasterDataVersion>(ENDPOINTS.ENTITIES.VERSION(id, version)),
    rollback: async (id: UUID, request: RollbackEntityRequest) => item(await apiClient.post<ApiSuccess<MasterDataEntity>>(ENDPOINTS.ENTITIES.ROLLBACK(id), request)),
    validate: async (id: UUID, idempotencyKey: string) => item(await apiClient.post<ApiSuccess<QualityReport>>(ENDPOINTS.ENTITIES.VALIDATE(id), { idempotency_key: idempotencyKey })),
  },
  qualityRules: {
    list: (filters: QualityRuleFilters = {}) => getList<DataQualityRule>(ENDPOINTS.QUALITY_RULES.LIST, filters),
    get: (id: UUID) => getItem<DataQualityRule>(ENDPOINTS.QUALITY_RULES.DETAIL(id)),
    create: async (request: DataQualityRuleWriteRequest) => item(await apiClient.post<ApiSuccess<DataQualityRule>>(ENDPOINTS.QUALITY_RULES.CREATE, request)),
    update: async (id: UUID, request: DataQualityRuleUpdateRequest) => item(await apiClient.patch<ApiSuccess<DataQualityRule>>(ENDPOINTS.QUALITY_RULES.UPDATE(id), request)),
    delete: (id: UUID) => apiClient.delete<void>(ENDPOINTS.QUALITY_RULES.DELETE(id)),
  },
  qualityIssues: {
    list: (filters: QualityIssueFilters = {}) => getList<DataQualityIssue>(ENDPOINTS.QUALITY_ISSUES.LIST, filters),
    get: (id: UUID) => getItem<DataQualityIssue>(ENDPOINTS.QUALITY_ISSUES.DETAIL(id)),
    assign: async (id: UUID, request: AssignQualityIssueRequest) => item(await apiClient.post<ApiSuccess<DataQualityIssue>>(ENDPOINTS.QUALITY_ISSUES.ASSIGN(id), request)),
    resolve: async (id: UUID, request: ResolveQualityIssueRequest) => item(await apiClient.post<ApiSuccess<DataQualityIssue>>(ENDPOINTS.QUALITY_ISSUES.RESOLVE(id), request)),
    waive: async (id: UUID, request: ResolveQualityIssueRequest) => item(await apiClient.post<ApiSuccess<DataQualityIssue>>(ENDPOINTS.QUALITY_ISSUES.WAIVE(id), request)),
  },
  qualityScans: {
    create: async (request: QualityScanRequest) => item(await apiClient.post<ApiSuccess<AsyncJob>>(ENDPOINTS.QUALITY_SCANS, request)),
  },
  matchingRules: {
    list: (filters: MatchingRuleFilters = {}) => getList<MatchingRule>(ENDPOINTS.MATCHING_RULES.LIST, filters),
    get: (id: UUID) => getItem<MatchingRule>(ENDPOINTS.MATCHING_RULES.DETAIL(id)),
    create: async (request: MatchingRuleWriteRequest) => item(await apiClient.post<ApiSuccess<MatchingRule>>(ENDPOINTS.MATCHING_RULES.CREATE, request)),
    update: async (id: UUID, request: MatchingRuleUpdateRequest) => item(await apiClient.patch<ApiSuccess<MatchingRule>>(ENDPOINTS.MATCHING_RULES.UPDATE(id), request)),
    delete: (id: UUID) => apiClient.delete<void>(ENDPOINTS.MATCHING_RULES.DELETE(id)),
  },
  matching: {
    preview: async (request: MatchPreviewRequest) => item(await apiClient.post<ApiSuccess<MatchResult>>(ENDPOINTS.MATCHING.PREVIEW, request)),
    scan: async (request: DeduplicationScanRequest) => item(await apiClient.post<ApiSuccess<AsyncJob>>(ENDPOINTS.MATCHING.SCANS, request)),
  },
  matchCandidates: {
    list: (filters: MatchCandidateFilters = {}) => getList<MatchCandidate>(ENDPOINTS.MATCH_CANDIDATES.LIST, filters),
    get: (id: UUID) => getItem<MatchCandidate>(ENDPOINTS.MATCH_CANDIDATES.DETAIL(id)),
    review: async (id: UUID, request: MatchReviewRequest) => item(await apiClient.post<ApiSuccess<MatchCandidate>>(ENDPOINTS.MATCH_CANDIDATES.REVIEW(id), request)),
  },
  merges: {
    list: (filters: MergeFilters = {}) => getList<MergeHistory>(ENDPOINTS.MERGES.LIST, filters),
    get: (id: UUID) => getItem<MergeHistory>(ENDPOINTS.MERGES.DETAIL(id)),
    preview: async (request: MergePreviewRequest) => item(await apiClient.post<ApiSuccess<MergePreview>>(ENDPOINTS.MERGES.PREVIEW, request)),
    create: async (request: MergeRequest) => item(await apiClient.post<ApiSuccess<MergeHistory>>(ENDPOINTS.MERGES.CREATE, request)),
    reverse: async (id: UUID, request: ReverseMergeRequest) => item(await apiClient.post<ApiSuccess<MergeHistory>>(ENDPOINTS.MERGES.REVERSE(id), request)),
  },
  jobs: { get: (id: UUID) => getItem<AsyncJob>(ENDPOINTS.JOB(id)) },
  health: {
    live: () => getItem<{ readonly status: "ok" }>(ENDPOINTS.HEALTH.LIVE),
    ready: () => getItem<{ readonly status: "ready"; readonly components: readonly { readonly code: string; readonly ready: boolean }[] }>(ENDPOINTS.HEALTH.READY),
  },
  validation: {
    report: (response: ApiSuccess<ValidationReport>) => item(response),
  },
} as const;
