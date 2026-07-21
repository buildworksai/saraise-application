import { ApiError, apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiV2Envelope,
  type ApiV2PaginatedEnvelope,
  type AssetHistory,
  type AuthenticityCredential,
  type AuthenticityCredentialFilters,
  type AuthenticityCredentialIssue,
  type AuthenticityCredentialListItem,
  type AuthenticityVerificationRequest,
  type ChainVerificationRequest,
  type ComplianceEvidence,
  type ComplianceEvidenceCreate,
  type ComplianceEvidenceFilters,
  type ComplianceEvidenceListItem,
  type ComplianceEvidenceUpdate,
  type CredentialRevokeRequest,
  type EvidenceSupersedeRequest,
  type GovernedApiError,
  type GovernedErrorDetail,
  type IssuedCredential,
  type LedgerAnchor,
  type LedgerAnchorCreate,
  type LedgerAnchorFilters,
  type LedgerAnchorListItem,
  type LedgerNetwork,
  type LedgerNetworkCreate,
  type LedgerNetworkFilters,
  type LedgerNetworkListItem,
  type LedgerNetworkUpdate,
  type ModuleHealth,
  type OperationResult,
  type PageFilters,
  type PageResult,
  type ProviderHealth,
  type QueuedAnchor,
  type RecallRequest,
  type TraceabilityAsset,
  type TraceabilityAssetCreate,
  type TraceabilityAssetFilters,
  type TraceabilityAssetListItem,
  type TraceabilityAssetUpdate,
  type TraceabilityEvent,
  type TraceabilityEventAppend,
  type TraceabilityEventFilters,
  type TraceabilityEventListItem,
  type TransitionRequest,
  type UUID,
  type VerificationAttempt,
  type VerificationAttemptFilters,
  type VerificationAttemptListItem,
} from '../contracts';

export class BlockchainTraceabilityApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly detail: GovernedErrorDetail,
    readonly correlationId: string | null,
  ) {
    super(message);
    this.name = 'BlockchainTraceabilityApiError';
  }

  get permissionDenied(): boolean {
    return this.status === 401 || this.status === 403;
  }

  get fieldErrors(): ReadonlyMap<string, string> {
    return new Map(this.detail.field_errors?.map(({ field, message }) => [field, message]) ?? []);
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function parseDetail(value: unknown): GovernedErrorDetail {
  if (!isObject(value)) return {};
  const detail: GovernedErrorDetail = {};
  if (typeof value.retry_after_seconds === 'number') detail.retry_after_seconds = value.retry_after_seconds;
  if (typeof value.state === 'string') detail.state = value.state;
  if (isObject(value.quota) && typeof value.quota.resource === 'string' && typeof value.quota.remaining === 'number') {
    detail.quota = {
      resource: value.quota.resource,
      remaining: value.quota.remaining,
      reset_at: typeof value.quota.reset_at === 'string' ? value.quota.reset_at : null,
    };
  }
  if (Array.isArray(value.field_errors)) {
    detail.field_errors = value.field_errors.flatMap((entry) => {
      if (!isObject(entry) || typeof entry.field !== 'string' || typeof entry.code !== 'string' || typeof entry.message !== 'string') return [];
      return [{ field: entry.field, code: entry.code, message: entry.message }];
    });
  }
  return detail;
}

function parseGovernedError(error: ApiError): GovernedApiError | null {
  if (!isObject(error.details) || !isObject(error.details.error)) return null;
  const body = error.details.error;
  if (typeof body.code !== 'string' || typeof body.message !== 'string' || typeof body.correlation_id !== 'string') return null;
  return { code: body.code, message: body.message, correlation_id: body.correlation_id, detail: parseDetail(body.detail) };
}

async function call<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    const governed = parseGovernedError(error);
    throw new BlockchainTraceabilityApiError(
      governed?.message ?? error.message,
      error.status,
      governed?.code ?? error.code ?? 'request_failed',
      governed?.detail ?? {},
      governed?.correlation_id ?? error.correlationId ?? null,
    );
  }
}

async function getData<T>(operation: () => Promise<ApiV2Envelope<T>>): Promise<T> {
  return (await call(operation)).data;
}

async function getPage<T>(operation: () => Promise<ApiV2PaginatedEnvelope<T>>): Promise<PageResult<T>> {
  const envelope = await call(operation);
  return { items: envelope.data, pagination: envelope.meta.pagination, correlationId: envelope.meta.correlation_id };
}

function setPageFilters(params: URLSearchParams, filters: PageFilters): void {
  if (filters.page !== undefined) params.set('page', String(filters.page));
  if (filters.page_size !== undefined) params.set('page_size', String(filters.page_size));
  if (filters.search) params.set('search', filters.search);
  if (filters.ordering) params.set('ordering', filters.ordering);
}

function setString(params: URLSearchParams, key: string, value?: string): void {
  if (value) params.set(key, value);
}

function withQuery(path: string, params: URLSearchParams): string {
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function networkQuery(filters: LedgerNetworkFilters): string {
  const params = new URLSearchParams(); setPageFilters(params, filters);
  setString(params, 'status', filters.status); setString(params, 'provider_type', filters.provider_type);
  return withQuery(ENDPOINTS.NETWORKS.LIST, params);
}

export function assetQuery(filters: TraceabilityAssetFilters): string {
  const params = new URLSearchParams(); setPageFilters(params, filters);
  setString(params, 'status', filters.status); setString(params, 'product_ref', filters.product_ref);
  setString(params, 'batch_ref', filters.batch_ref); setString(params, 'serial_number', filters.serial_number);
  setString(params, 'gtin', filters.gtin); setString(params, 'asset_type', filters.asset_type);
  return withQuery(ENDPOINTS.ASSETS.LIST, params);
}

export function eventQuery(filters: TraceabilityEventFilters): string {
  const params = new URLSearchParams(); setPageFilters(params, filters);
  setString(params, 'asset_id', filters.asset_id); setString(params, 'event_type', filters.event_type);
  setString(params, 'occurred_after', filters.occurred_after); setString(params, 'occurred_before', filters.occurred_before);
  setString(params, 'actor_ref', filters.actor_ref);
  return withQuery(ENDPOINTS.EVENTS.LIST, params);
}

export function anchorQuery(filters: LedgerAnchorFilters): string {
  const params = new URLSearchParams(); setPageFilters(params, filters);
  setString(params, 'asset_id', filters.asset_id); setString(params, 'network_id', filters.network_id);
  setString(params, 'status', filters.status); setString(params, 'created_after', filters.created_after);
  setString(params, 'created_before', filters.created_before);
  return withQuery(ENDPOINTS.ANCHORS.LIST, params);
}

export function credentialQuery(filters: AuthenticityCredentialFilters): string {
  const params = new URLSearchParams(); setPageFilters(params, filters);
  setString(params, 'asset_id', filters.asset_id); setString(params, 'status', filters.status);
  setString(params, 'credential_type', filters.credential_type); setString(params, 'expires_after', filters.expires_after);
  setString(params, 'expires_before', filters.expires_before);
  return withQuery(ENDPOINTS.CREDENTIALS.LIST, params);
}

export function evidenceQuery(filters: ComplianceEvidenceFilters): string {
  const params = new URLSearchParams(); setPageFilters(params, filters);
  setString(params, 'asset_id', filters.asset_id); setString(params, 'evidence_type', filters.evidence_type);
  setString(params, 'standard', filters.standard); setString(params, 'jurisdiction', filters.jurisdiction);
  setString(params, 'result', filters.result); setString(params, 'status', filters.status);
  setString(params, 'observed_after', filters.observed_after); setString(params, 'observed_before', filters.observed_before);
  return withQuery(ENDPOINTS.COMPLIANCE_EVIDENCE.LIST, params);
}

export function attemptQuery(filters: VerificationAttemptFilters): string {
  const params = new URLSearchParams(); setPageFilters(params, filters);
  setString(params, 'verification_type', filters.verification_type); setString(params, 'outcome', filters.outcome);
  setString(params, 'asset_id', filters.asset_id); setString(params, 'reason_code', filters.reason_code);
  setString(params, 'created_after', filters.created_after); setString(params, 'created_before', filters.created_before);
  return withQuery(ENDPOINTS.VERIFICATION_ATTEMPTS.LIST, params);
}

export const blockchainTraceabilityService = {
  listNetworks: (filters: LedgerNetworkFilters = {}) => getPage(() => apiClient.get<ApiV2PaginatedEnvelope<LedgerNetworkListItem>>(networkQuery(filters))),
  createNetwork: (request: LedgerNetworkCreate) => getData(() => apiClient.post<ApiV2Envelope<LedgerNetwork>>(ENDPOINTS.NETWORKS.CREATE, request)),
  getNetwork: (id: UUID) => getData(() => apiClient.get<ApiV2Envelope<LedgerNetwork>>(ENDPOINTS.NETWORKS.DETAIL(id))),
  updateNetwork: (id: UUID, request: LedgerNetworkUpdate) => getData(() => apiClient.patch<ApiV2Envelope<LedgerNetwork>>(ENDPOINTS.NETWORKS.DETAIL(id), request)),
  deleteNetwork: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.NETWORKS.DETAIL(id))),
  activateNetwork: (id: UUID, request: TransitionRequest) => getData(() => apiClient.post<ApiV2Envelope<LedgerNetwork>>(ENDPOINTS.NETWORKS.ACTIVATE(id), request)),
  disableNetwork: (id: UUID, request: TransitionRequest) => getData(() => apiClient.post<ApiV2Envelope<LedgerNetwork>>(ENDPOINTS.NETWORKS.DISABLE(id), request)),
  probeNetwork: (id: UUID) => getData(() => apiClient.post<ApiV2Envelope<OperationResult<ProviderHealth>>>(ENDPOINTS.NETWORKS.PROBE(id))),

  listAssets: (filters: TraceabilityAssetFilters = {}) => getPage(() => apiClient.get<ApiV2PaginatedEnvelope<TraceabilityAssetListItem>>(assetQuery(filters))),
  registerAsset: (request: TraceabilityAssetCreate) => getData(() => apiClient.post<ApiV2Envelope<TraceabilityAsset>>(ENDPOINTS.ASSETS.CREATE, request)),
  getAsset: (id: UUID) => getData(() => apiClient.get<ApiV2Envelope<TraceabilityAsset>>(ENDPOINTS.ASSETS.DETAIL(id))),
  updateAsset: (id: UUID, request: TraceabilityAssetUpdate) => getData(() => apiClient.patch<ApiV2Envelope<TraceabilityAsset>>(ENDPOINTS.ASSETS.DETAIL(id), request)),
  deleteAsset: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.ASSETS.DETAIL(id))),
  activateAsset: (id: UUID, request: TransitionRequest) => getData(() => apiClient.post<ApiV2Envelope<TraceabilityAsset>>(ENDPOINTS.ASSETS.ACTIVATE(id), request)),
  recallAsset: (id: UUID, request: RecallRequest) => getData(() => apiClient.post<ApiV2Envelope<TraceabilityAsset>>(ENDPOINTS.ASSETS.RECALL(id), request)),
  releaseAssetRecall: (id: UUID, request: TransitionRequest) => getData(() => apiClient.post<ApiV2Envelope<TraceabilityAsset>>(ENDPOINTS.ASSETS.RELEASE_RECALL(id), request)),
  retireAsset: (id: UUID, request: TransitionRequest) => getData(() => apiClient.post<ApiV2Envelope<TraceabilityAsset>>(ENDPOINTS.ASSETS.RETIRE(id), request)),
  getAssetHistory: (id: UUID, filters: PageFilters = {}) => {
    const params = new URLSearchParams(); setPageFilters(params, filters);
    return getData(() => apiClient.get<ApiV2Envelope<AssetHistory>>(withQuery(ENDPOINTS.ASSETS.HISTORY(id), params)));
  },
  verifyAssetChain: (id: UUID, request: ChainVerificationRequest) => getData(() => apiClient.post<ApiV2Envelope<VerificationAttempt>>(ENDPOINTS.ASSETS.VERIFY_CHAIN(id), request)),

  listEvents: (filters: TraceabilityEventFilters = {}) => getPage(() => apiClient.get<ApiV2PaginatedEnvelope<TraceabilityEventListItem>>(eventQuery(filters))),
  appendEvent: (request: TraceabilityEventAppend) => getData(() => apiClient.post<ApiV2Envelope<TraceabilityEvent>>(ENDPOINTS.EVENTS.CREATE, request)),
  getEvent: (id: UUID) => getData(() => apiClient.get<ApiV2Envelope<TraceabilityEvent>>(ENDPOINTS.EVENTS.DETAIL(id))),

  listAnchors: (filters: LedgerAnchorFilters = {}) => getPage(() => apiClient.get<ApiV2PaginatedEnvelope<LedgerAnchorListItem>>(anchorQuery(filters))),
  requestAnchor: (request: LedgerAnchorCreate) => getData(() => apiClient.post<ApiV2Envelope<QueuedAnchor>>(ENDPOINTS.ANCHORS.CREATE, request)),
  getAnchor: (id: UUID) => getData(() => apiClient.get<ApiV2Envelope<LedgerAnchor>>(ENDPOINTS.ANCHORS.DETAIL(id))),
  retryAnchor: (id: UUID, request: TransitionRequest) => getData(() => apiClient.post<ApiV2Envelope<QueuedAnchor>>(ENDPOINTS.ANCHORS.RETRY(id), request)),
  refreshAnchor: (id: UUID) => getData(() => apiClient.post<ApiV2Envelope<OperationResult<LedgerAnchor>>>(ENDPOINTS.ANCHORS.REFRESH(id))),
  verifyAnchor: (id: UUID, request: ChainVerificationRequest) => getData(() => apiClient.post<ApiV2Envelope<VerificationAttempt>>(ENDPOINTS.ANCHORS.VERIFY(id), request)),

  listCredentials: (filters: AuthenticityCredentialFilters = {}) => getPage(() => apiClient.get<ApiV2PaginatedEnvelope<AuthenticityCredentialListItem>>(credentialQuery(filters))),
  issueCredential: (request: AuthenticityCredentialIssue) => getData(() => apiClient.post<ApiV2Envelope<IssuedCredential>>(ENDPOINTS.CREDENTIALS.CREATE, request)),
  getCredential: (id: UUID) => getData(() => apiClient.get<ApiV2Envelope<AuthenticityCredential>>(ENDPOINTS.CREDENTIALS.DETAIL(id))),
  revokeCredential: (id: UUID, request: CredentialRevokeRequest) => getData(() => apiClient.post<ApiV2Envelope<AuthenticityCredential>>(ENDPOINTS.CREDENTIALS.REVOKE(id), request)),
  verifyAuthenticity: (request: AuthenticityVerificationRequest) => getData(() => apiClient.post<ApiV2Envelope<VerificationAttempt>>(ENDPOINTS.CREDENTIALS.VERIFY, request)),

  listComplianceEvidence: (filters: ComplianceEvidenceFilters = {}) => getPage(() => apiClient.get<ApiV2PaginatedEnvelope<ComplianceEvidenceListItem>>(evidenceQuery(filters))),
  createComplianceEvidence: (request: ComplianceEvidenceCreate) => getData(() => apiClient.post<ApiV2Envelope<ComplianceEvidence>>(ENDPOINTS.COMPLIANCE_EVIDENCE.CREATE, request)),
  getComplianceEvidence: (id: UUID) => getData(() => apiClient.get<ApiV2Envelope<ComplianceEvidence>>(ENDPOINTS.COMPLIANCE_EVIDENCE.DETAIL(id))),
  updateComplianceEvidence: (id: UUID, request: ComplianceEvidenceUpdate) => getData(() => apiClient.patch<ApiV2Envelope<ComplianceEvidence>>(ENDPOINTS.COMPLIANCE_EVIDENCE.DETAIL(id), request)),
  deleteComplianceEvidence: (id: UUID) => call(() => apiClient.delete<void>(ENDPOINTS.COMPLIANCE_EVIDENCE.DETAIL(id))),
  finalizeComplianceEvidence: (id: UUID, request: TransitionRequest) => getData(() => apiClient.post<ApiV2Envelope<ComplianceEvidence>>(ENDPOINTS.COMPLIANCE_EVIDENCE.FINALIZE(id), request)),
  supersedeComplianceEvidence: (id: UUID, request: EvidenceSupersedeRequest) => getData(() => apiClient.post<ApiV2Envelope<ComplianceEvidence>>(ENDPOINTS.COMPLIANCE_EVIDENCE.SUPERSEDE(id), request)),
  verifyComplianceEvidence: (id: UUID, request: ChainVerificationRequest) => getData(() => apiClient.post<ApiV2Envelope<VerificationAttempt>>(ENDPOINTS.COMPLIANCE_EVIDENCE.VERIFY(id), request)),

  listVerificationAttempts: (filters: VerificationAttemptFilters = {}) => getPage(() => apiClient.get<ApiV2PaginatedEnvelope<VerificationAttemptListItem>>(attemptQuery(filters))),
  getVerificationAttempt: (id: UUID) => getData(() => apiClient.get<ApiV2Envelope<VerificationAttempt>>(ENDPOINTS.VERIFICATION_ATTEMPTS.DETAIL(id))),
  getHealth: () => getData(() => apiClient.get<ApiV2Envelope<ModuleHealth>>(ENDPOINTS.HEALTH)),
};
