/** Public, provider-neutral contracts for the Blockchain Traceability v2 API. */

export type UUID = string;
export type ISODateTime = string;
export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | readonly JsonValue[];
export interface JsonObject { readonly [key: string]: JsonValue }

export type LedgerNetworkStatus = 'draft' | 'active' | 'degraded' | 'disabled';
export type TraceabilityAssetStatus = 'draft' | 'active' | 'recalled' | 'retired';
export type LedgerAnchorStatus = 'queued' | 'submitting' | 'submitted' | 'confirmed' | 'failed';
export type AuthenticityCredentialStatus = 'active' | 'revoked' | 'expired';
export type ComplianceEvidenceStatus = 'draft' | 'finalized' | 'superseded';
export type ComplianceResult = 'pass' | 'fail' | 'warning' | 'not_applicable';
export type VerificationType = 'chain' | 'anchor' | 'authenticity' | 'compliance';
export type VerificationOutcome =
  | 'verified'
  | 'invalid'
  | 'not_authentic'
  | 'inconclusive'
  | 'dependency_unavailable';
export type ProofStatus =
  | 'locally_consistent'
  | 'externally_verified'
  | 'invalid'
  | 'unavailable';
export type HealthStatus = 'healthy' | 'degraded' | 'unavailable';

export interface TransitionEvidence {
  transition_key: string;
  command: string;
  from_state: string;
  to_state: string;
  actor_id: string;
  occurred_at: ISODateTime;
  reason?: string;
  correlation_id?: string;
}

export interface MutableAuditFields {
  created_at: ISODateTime;
  updated_at: ISODateTime;
  created_by: string;
  updated_by: string;
  is_deleted: boolean;
  deleted_at: ISODateTime | null;
  deleted_by: string;
}

export interface LedgerNetwork extends MutableAuditFields {
  id: UUID;
  tenant_id: UUID;
  network_key: string;
  name: string;
  description: string;
  provider_type: string;
  dependency_key: string;
  network_namespace: string;
  chain_id: string;
  credential_configured: boolean;
  confirmation_depth: number;
  supports_batch_anchors: boolean;
  supports_finality: boolean;
  provider_options: JsonObject;
  status: LedgerNetworkStatus;
  transition_history: readonly TransitionEvidence[];
  last_health_status: string;
  last_health_code: string;
  last_health_checked_at: ISODateTime | null;
  last_successful_anchor_at: ISODateTime | null;
}

/** Exact fields emitted by LedgerNetworkListSerializer. */
export type LedgerNetworkListItem = Pick<LedgerNetwork,
  | 'id' | 'tenant_id' | 'network_key' | 'name' | 'provider_type'
  | 'network_namespace' | 'chain_id' | 'confirmation_depth'
  | 'supports_batch_anchors' | 'supports_finality' | 'status'
  | 'credential_configured' | 'last_health_status' | 'last_health_code'
  | 'last_health_checked_at' | 'last_successful_anchor_at'
  | 'created_at' | 'updated_at'
>;

export interface TraceabilityAsset extends MutableAuditFields {
  id: UUID;
  tenant_id: UUID;
  asset_key: string;
  name: string;
  description: string;
  product_ref: string;
  batch_ref: string;
  serial_number: string;
  gtin: string;
  asset_type: string;
  status: TraceabilityAssetStatus;
  attributes: JsonObject;
  head_sequence: number;
  head_hash: string;
  transition_history: readonly TransitionEvidence[];
  activated_at: ISODateTime | null;
  recalled_at: ISODateTime | null;
  retired_at: ISODateTime | null;
}

/** Exact fields emitted by TraceabilityAssetListSerializer. */
export type TraceabilityAssetListItem = Pick<TraceabilityAsset,
  | 'id' | 'tenant_id' | 'asset_key' | 'name' | 'product_ref'
  | 'batch_ref' | 'serial_number' | 'gtin' | 'asset_type' | 'status'
  | 'head_sequence' | 'head_hash' | 'activated_at' | 'recalled_at'
  | 'retired_at' | 'created_at' | 'updated_at'
>;

export interface TraceabilityEvent {
  id: UUID;
  tenant_id: UUID;
  asset_id: UUID;
  sequence: number;
  idempotency_key: string;
  event_type: string;
  schema_version: number;
  occurred_at: ISODateTime;
  recorded_at: ISODateTime;
  actor_ref: string;
  location: JsonObject;
  payload: JsonObject;
  previous_hash: string;
  event_hash: string;
  hash_algorithm: 'sha256';
  created_by: string;
  correlation_id: string;
}

/** Exact fields emitted by TraceabilityEventListSerializer. */
export type TraceabilityEventListItem = Pick<TraceabilityEvent,
  | 'id' | 'tenant_id' | 'asset_id' | 'sequence' | 'event_type'
  | 'schema_version' | 'occurred_at' | 'recorded_at' | 'actor_ref'
  | 'previous_hash' | 'event_hash' | 'hash_algorithm' | 'correlation_id'
>;

export interface LedgerAnchor {
  id: UUID;
  tenant_id: UUID;
  asset_id: UUID;
  network_id: UUID;
  start_sequence: number;
  end_sequence: number;
  root_hash: string;
  hash_algorithm: 'sha256';
  idempotency_key: string;
  status: LedgerAnchorStatus;
  transition_history: readonly TransitionEvidence[];
  async_job_id: UUID | null;
  provider_transaction_id: string;
  transaction_hash: string;
  block_number: number | null;
  block_hash: string;
  confirmations: number;
  provider_receipt: JsonObject;
  failure_code: string;
  failure_message: string;
  submitted_at: ISODateTime | null;
  confirmed_at: ISODateTime | null;
  last_checked_at: ISODateTime | null;
  created_by: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

/** Exact fields emitted by LedgerAnchorListSerializer. */
export type LedgerAnchorListItem = Pick<LedgerAnchor,
  | 'id' | 'tenant_id' | 'asset_id' | 'network_id' | 'start_sequence'
  | 'end_sequence' | 'root_hash' | 'hash_algorithm' | 'status'
  | 'async_job_id' | 'provider_transaction_id' | 'transaction_hash'
  | 'block_number' | 'block_hash' | 'confirmations' | 'failure_code'
  | 'submitted_at' | 'confirmed_at' | 'last_checked_at' | 'created_at'
  | 'updated_at'
>;

export interface AuthenticityCredential {
  id: UUID;
  tenant_id: UUID;
  asset_id: UUID;
  public_id: string;
  credential_type: string;
  claims: JsonObject;
  claims_hash: string;
  signature_algorithm: string;
  issuer_key_ref?: never;
  signature: string;
  status: AuthenticityCredentialStatus;
  transition_history: readonly TransitionEvidence[];
  issued_at: ISODateTime;
  expires_at: ISODateTime | null;
  revoked_at: ISODateTime | null;
  revocation_reason: string;
  created_by: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

/** Exact fields emitted by AuthenticityCredentialListSerializer. */
export type AuthenticityCredentialListItem = Pick<AuthenticityCredential,
  | 'id' | 'tenant_id' | 'asset_id' | 'public_id' | 'credential_type'
  | 'status' | 'issued_at' | 'expires_at' | 'revoked_at' | 'created_at'
  | 'updated_at'
>;

export interface ComplianceEvidence extends MutableAuditFields {
  id: UUID;
  tenant_id: UUID;
  asset_id: UUID;
  event_id: UUID | null;
  evidence_key: string;
  evidence_type: string;
  standard: string;
  jurisdiction: string;
  result: ComplianceResult;
  details: JsonObject;
  document_ref: UUID | null;
  content_hash: string;
  observed_at: ISODateTime;
  valid_until: ISODateTime | null;
  status: ComplianceEvidenceStatus;
  transition_history: readonly TransitionEvidence[];
  supersedes_id: UUID | null;
  finalized_at: ISODateTime | null;
}

/** Exact fields emitted by ComplianceEvidenceListSerializer. */
export type ComplianceEvidenceListItem = Pick<ComplianceEvidence,
  | 'id' | 'tenant_id' | 'asset_id' | 'event_id' | 'evidence_key'
  | 'evidence_type' | 'standard' | 'jurisdiction' | 'result' | 'status'
  | 'observed_at' | 'valid_until' | 'finalized_at' | 'created_at'
  | 'updated_at'
>;

export interface ProofEvidence {
  proof_status?: ProofStatus;
  checked_sequences?: number;
  failing_sequence?: number | null;
  expected_hash?: string;
  actual_hash?: string;
  provider_type?: string;
  provider_evidence?: JsonObject;
  local_chain_valid?: boolean;
  externally_anchored?: boolean;
  simulated_provider?: boolean;
  explanation?: string;
}

export interface VerificationAttempt {
  id: UUID;
  tenant_id: UUID;
  verification_type: VerificationType;
  asset_id: UUID | null;
  anchor_id: UUID | null;
  credential_id: UUID | null;
  compliance_evidence_id: UUID | null;
  idempotency_key: string;
  outcome: VerificationOutcome;
  reason_code: string;
  chain_head_hash: string;
  proof_evidence: ProofEvidence;
  actor_id: string;
  source_fingerprint: string;
  correlation_id: string;
  latency_ms: number;
  created_at: ISODateTime;
}

/** Exact fields emitted by VerificationAttemptListSerializer. */
export type VerificationAttemptListItem = Pick<VerificationAttempt,
  | 'id' | 'tenant_id' | 'verification_type' | 'asset_id' | 'anchor_id'
  | 'credential_id' | 'compliance_evidence_id' | 'outcome' | 'reason_code'
  | 'chain_head_hash' | 'correlation_id' | 'latency_ms' | 'created_at'
>;

export type AssetHistoryItem =
  | { kind: 'event'; occurred_at: ISODateTime; sequence: number; event: TraceabilityEvent }
  | { kind: 'anchor'; occurred_at: ISODateTime; sequence?: number; anchor: LedgerAnchor }
  | { kind: 'credential'; occurred_at: ISODateTime; sequence?: number; credential: AuthenticityCredential }
  | { kind: 'compliance'; occurred_at: ISODateTime; sequence?: number; evidence: ComplianceEvidence };

export interface AssetHistory {
  asset: TraceabilityAsset;
  items: readonly AssetHistoryItem[];
  proof_status: ProofStatus;
  failing_sequence: number | null;
  pagination: ApiV2Pagination;
}

export interface ProviderHealth {
  status: HealthStatus;
  code: string;
  checked_at: ISODateTime;
  provider_type: string;
  simulated: boolean;
  latency_ms?: number;
}

export interface OperationResult<T> {
  ok: boolean;
  code: string;
  message: string;
  value: T | null;
}

export interface AsyncJobReference {
  id: UUID;
  command: 'blockchain_traceability.submit_anchor';
  status: 'queued';
  correlation_id: string;
}

export interface QueuedAnchor {
  anchor: LedgerAnchor;
  job: AsyncJobReference;
  queued: true;
}

export interface IssuedCredential {
  credential: AuthenticityCredential;
  token: string;
  token_recoverable: false;
}

export interface HealthDependency {
  name: 'database' | 'cache' | 'async_outbox' | 'adapters' | 'network';
  status: HealthStatus;
  code: string;
  checked_at: ISODateTime;
  circuit_state?: 'closed' | 'open' | 'half_open' | 'not_applicable';
}

export interface ModuleHealth {
  status: HealthStatus;
  checked_at: ISODateTime;
  dependencies: readonly HealthDependency[];
}

export interface ApiV2Pagination {
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
  meta: ApiV2Meta & { pagination: ApiV2Pagination };
}

export interface FieldError {
  field: string;
  code: string;
  message: string;
}

export interface GovernedErrorDetail {
  field_errors?: readonly FieldError[];
  retry_after_seconds?: number;
  quota?: { resource: string; remaining: number; reset_at: ISODateTime | null };
  state?: string;
}

export interface GovernedApiError {
  code: string;
  message: string;
  detail: GovernedErrorDetail;
  correlation_id: string;
}

export interface PageResult<T> {
  items: readonly T[];
  pagination: ApiV2Pagination;
  correlationId: string;
}

export interface PageFilters {
  page?: number;
  page_size?: number;
  search?: string;
  ordering?: string;
}

export interface LedgerNetworkFilters extends PageFilters {
  status?: LedgerNetworkStatus;
  provider_type?: string;
}

export interface TraceabilityAssetFilters extends PageFilters {
  status?: TraceabilityAssetStatus;
  product_ref?: string;
  batch_ref?: string;
  serial_number?: string;
  gtin?: string;
  asset_type?: string;
}

export interface TraceabilityEventFilters extends PageFilters {
  asset_id?: UUID;
  event_type?: string;
  occurred_after?: ISODateTime;
  occurred_before?: ISODateTime;
  actor_ref?: string;
}

export interface LedgerAnchorFilters extends PageFilters {
  asset_id?: UUID;
  network_id?: UUID;
  status?: LedgerAnchorStatus;
  created_after?: ISODateTime;
  created_before?: ISODateTime;
}

export interface AuthenticityCredentialFilters extends PageFilters {
  asset_id?: UUID;
  status?: AuthenticityCredentialStatus;
  credential_type?: string;
  expires_after?: ISODateTime;
  expires_before?: ISODateTime;
}

export interface ComplianceEvidenceFilters extends PageFilters {
  asset_id?: UUID;
  evidence_type?: string;
  standard?: string;
  jurisdiction?: string;
  result?: ComplianceResult;
  status?: ComplianceEvidenceStatus;
  observed_after?: ISODateTime;
  observed_before?: ISODateTime;
}

export interface VerificationAttemptFilters extends PageFilters {
  verification_type?: VerificationType;
  outcome?: VerificationOutcome;
  asset_id?: UUID;
  reason_code?: string;
  created_after?: ISODateTime;
  created_before?: ISODateTime;
}

export interface LedgerNetworkCreate {
  network_key: string;
  name: string;
  description?: string;
  provider_type: string;
  dependency_key: string;
  network_namespace: string;
  chain_id?: string;
  secret_ref?: string;
  confirmation_depth?: number;
  supports_batch_anchors?: boolean;
  supports_finality?: boolean;
  provider_options?: JsonObject;
}
export type LedgerNetworkUpdate = Partial<Omit<LedgerNetworkCreate, 'network_key'>>;

export interface TraceabilityAssetCreate {
  asset_key: string;
  name: string;
  description?: string;
  product_ref?: string;
  batch_ref?: string;
  serial_number?: string;
  gtin?: string;
  asset_type: string;
  attributes?: JsonObject;
}
export type TraceabilityAssetUpdate = Partial<Omit<TraceabilityAssetCreate, 'asset_key'>>;

export interface TraceabilityEventAppend {
  asset_id: UUID;
  idempotency_key: string;
  event_type: string;
  schema_version?: number;
  occurred_at: ISODateTime;
  actor_ref: string;
  location?: JsonObject;
  payload?: JsonObject;
}

export interface LedgerAnchorCreate {
  asset_id: UUID;
  network_id: UUID;
  start_sequence: number;
  end_sequence: number;
  idempotency_key: string;
}

export interface AuthenticityCredentialIssue {
  asset_id: UUID;
  claims: JsonObject;
  expires_at?: ISODateTime | null;
}

export interface ComplianceEvidenceCreate {
  asset_id: UUID;
  event_id?: UUID | null;
  evidence_key: string;
  evidence_type: string;
  standard: string;
  jurisdiction?: string;
  result: ComplianceResult;
  details?: JsonObject;
  document_ref?: UUID | null;
  observed_at: ISODateTime;
  valid_until?: ISODateTime | null;
  supersedes_id?: UUID | null;
}
export type ComplianceEvidenceUpdate = Partial<Omit<ComplianceEvidenceCreate, 'asset_id' | 'evidence_key'>>;

export interface TransitionRequest { transition_key: string }
export interface RecallRequest extends TransitionRequest { reason: string }
export interface CredentialRevokeRequest extends TransitionRequest { reason: string }
export interface ChainVerificationRequest { idempotency_key: string }
export interface AuthenticityVerificationRequest { public_id: string; token: string; idempotency_key: string }
export type EvidenceSupersedeRequest = TransitionRequest & ComplianceEvidenceCreate;

export const MODULE_API_PREFIX = '/api/v2/blockchain-traceability';

export const ENDPOINTS = {
  NETWORKS: {
    LIST: `${MODULE_API_PREFIX}/networks/`,
    CREATE: `${MODULE_API_PREFIX}/networks/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/networks/${id}/` as const,
    ACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/networks/${id}/activate/` as const,
    DISABLE: (id: UUID) => `${MODULE_API_PREFIX}/networks/${id}/disable/` as const,
    PROBE: (id: UUID) => `${MODULE_API_PREFIX}/networks/${id}/probe/` as const,
  },
  ASSETS: {
    LIST: `${MODULE_API_PREFIX}/assets/`,
    CREATE: `${MODULE_API_PREFIX}/assets/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/assets/${id}/` as const,
    ACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/assets/${id}/activate/` as const,
    RECALL: (id: UUID) => `${MODULE_API_PREFIX}/assets/${id}/recall/` as const,
    RELEASE_RECALL: (id: UUID) => `${MODULE_API_PREFIX}/assets/${id}/release-recall/` as const,
    RETIRE: (id: UUID) => `${MODULE_API_PREFIX}/assets/${id}/retire/` as const,
    HISTORY: (id: UUID) => `${MODULE_API_PREFIX}/assets/${id}/history/` as const,
    VERIFY_CHAIN: (id: UUID) => `${MODULE_API_PREFIX}/assets/${id}/verify-chain/` as const,
  },
  EVENTS: {
    LIST: `${MODULE_API_PREFIX}/events/`,
    CREATE: `${MODULE_API_PREFIX}/events/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/events/${id}/` as const,
  },
  ANCHORS: {
    LIST: `${MODULE_API_PREFIX}/anchors/`,
    CREATE: `${MODULE_API_PREFIX}/anchors/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/anchors/${id}/` as const,
    RETRY: (id: UUID) => `${MODULE_API_PREFIX}/anchors/${id}/retry/` as const,
    REFRESH: (id: UUID) => `${MODULE_API_PREFIX}/anchors/${id}/refresh/` as const,
    VERIFY: (id: UUID) => `${MODULE_API_PREFIX}/anchors/${id}/verify/` as const,
  },
  CREDENTIALS: {
    LIST: `${MODULE_API_PREFIX}/credentials/`,
    CREATE: `${MODULE_API_PREFIX}/credentials/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/credentials/${id}/` as const,
    REVOKE: (id: UUID) => `${MODULE_API_PREFIX}/credentials/${id}/revoke/` as const,
    VERIFY: `${MODULE_API_PREFIX}/credentials/verify/`,
  },
  COMPLIANCE_EVIDENCE: {
    LIST: `${MODULE_API_PREFIX}/compliance-evidence/`,
    CREATE: `${MODULE_API_PREFIX}/compliance-evidence/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/compliance-evidence/${id}/` as const,
    FINALIZE: (id: UUID) => `${MODULE_API_PREFIX}/compliance-evidence/${id}/finalize/` as const,
    SUPERSEDE: (id: UUID) => `${MODULE_API_PREFIX}/compliance-evidence/${id}/supersede/` as const,
    VERIFY: (id: UUID) => `${MODULE_API_PREFIX}/compliance-evidence/${id}/verify/` as const,
  },
  VERIFICATION_ATTEMPTS: {
    LIST: `${MODULE_API_PREFIX}/verification-attempts/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/verification-attempts/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTE_PATHS = {
  NETWORKS: '/blockchain-traceability/networks',
  NETWORK_CREATE: '/blockchain-traceability/networks/new',
  NETWORK_DETAIL: (id: UUID) => `/blockchain-traceability/networks/${id}` as const,
  NETWORK_EDIT: (id: UUID) => `/blockchain-traceability/networks/${id}/edit` as const,
  ASSETS: '/blockchain-traceability/assets',
  ASSET_CREATE: '/blockchain-traceability/assets/new',
  ASSET_DETAIL: (id: UUID) => `/blockchain-traceability/assets/${id}` as const,
  ASSET_EDIT: (id: UUID) => `/blockchain-traceability/assets/${id}/edit` as const,
  EVENTS: '/blockchain-traceability/events',
  EVENT_APPEND: '/blockchain-traceability/events/new',
  EVENT_DETAIL: (id: UUID) => `/blockchain-traceability/events/${id}` as const,
  ANCHORS: '/blockchain-traceability/anchors',
  ANCHOR_CREATE: '/blockchain-traceability/anchors/new',
  ANCHOR_DETAIL: (id: UUID) => `/blockchain-traceability/anchors/${id}` as const,
  CREDENTIALS: '/blockchain-traceability/credentials',
  CREDENTIAL_ISSUE: '/blockchain-traceability/credentials/new',
  CREDENTIAL_DETAIL: (id: UUID) => `/blockchain-traceability/credentials/${id}` as const,
  COMPLIANCE: '/blockchain-traceability/compliance',
  COMPLIANCE_CREATE: '/blockchain-traceability/compliance/new',
  COMPLIANCE_DETAIL: (id: UUID) => `/blockchain-traceability/compliance/${id}` as const,
  COMPLIANCE_EDIT: (id: UUID) => `/blockchain-traceability/compliance/${id}/edit` as const,
  VERIFY: '/blockchain-traceability/verify',
  ATTEMPTS: '/blockchain-traceability/verification-attempts',
  ATTEMPT_DETAIL: (id: UUID) => `/blockchain-traceability/verification-attempts/${id}` as const,
} as const;
