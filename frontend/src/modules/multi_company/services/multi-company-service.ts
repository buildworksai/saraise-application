import { apiClient, ApiError } from '@/services/api-client';
import {
  ENDPOINTS,
  type AccessGrantCreateRequest, type AccessGrantFilters, type ApiEnvelope, type ApiMeta,
  type ApplyPricingRequest, type ApprovalRequest, type AsyncJob, type Company,
  type CompanyAccessGrant, type CompanyCreateRequest, type CompanyFilters, type CompanyHierarchy,
  type CompanyUpdateRequest, type ConfigurationCreateRequest, type ConfigurationFilters,
  type ConfigurationImpact, type ConfigurationRollbackRequest, type ConfigurationUpdateRequest,
  type ConfigurationVersion, type ConsolidatedReport, type ConsolidationCreateRequest,
  type ConsolidationFilters, type ConsolidationRun, type ConsolidationUpdateRequest,
  type EliminationCreateRequest, type EliminationEntry, type EliminationFilters, type HealthStatus,
  type ExtensionCatalogEntry,
  type IntercompanyTransaction, type PaginatedEnvelope, type PageFilters, type ReasonTransitionRequest,
  type ReconciliationFilters, type ReconciliationRow, type ResolveDisputeRequest,
  type SignedConfigurationExport, type TransactionCreateRequest, type TransactionFilters,
  type TransactionUpdateRequest, type TransferPriceRequest, type TransferPriceResult,
  type TransferPricingFilters, type TransferPricingRule, type TransferPricingRuleCreateRequest,
  type TransferPricingRuleUpdateRequest, type TransitionRequest, type UUID,
} from '../contracts';

export interface GovernedResult<T> { data: T; meta: ApiMeta }
export interface GovernedPage<T> extends GovernedResult<readonly T[]> { pagination: PaginatedEnvelope<T>['meta']['pagination'] }

function isObject(value: unknown): value is Readonly<Record<string, unknown>> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function unwrap<T>(payload: ApiEnvelope<T>): GovernedResult<T> {
  if (!isObject(payload) || !('data' in payload) || !isObject(payload.meta) ||
      typeof payload.meta.correlation_id !== 'string' || typeof payload.meta.timestamp !== 'string') {
    throw new ApiError('The server returned an invalid governed response.', 502, payload, 'INVALID_API_ENVELOPE');
  }
  return { data: payload.data, meta: payload.meta as unknown as ApiMeta };
}

function unwrapPage<T>(payload: PaginatedEnvelope<T>): GovernedPage<T> {
  const result = unwrap<readonly T[]>(payload);
  const pagination = payload.meta.pagination;
  if (!Array.isArray(result.data) || !isObject(pagination) || typeof pagination.count !== 'number' ||
      typeof pagination.page !== 'number' || typeof pagination.page_size !== 'number' ||
      typeof pagination.total_pages !== 'number' || typeof pagination.has_next !== 'boolean' ||
      typeof pagination.has_previous !== 'boolean') {
    throw new ApiError('The server returned invalid pagination metadata.', 502, payload, 'INVALID_PAGINATION_ENVELOPE', result.meta.correlation_id);
  }
  return { ...result, pagination };
}

function params(filters: object): string {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
  });
  const encoded = query.toString();
  return encoded ? `?${encoded}` : '';
}

const idempotency = (key: string): RequestInit => ({ headers: { 'Idempotency-Key': key } });
const get = async <T>(url: string) => unwrap(await apiClient.get<ApiEnvelope<T>>(url));
const post = async <T>(url: string, body?: unknown, init?: RequestInit) => unwrap(await apiClient.post<ApiEnvelope<T>>(url, body, init));
const patch = async <T>(url: string, body: unknown) => unwrap(await apiClient.patch<ApiEnvelope<T>>(url, body));

export const multiCompanyService = {
  listCompanies: async (filters: CompanyFilters = {}): Promise<GovernedPage<Company>> => unwrapPage(await apiClient.get<PaginatedEnvelope<Company>>(`${ENDPOINTS.COMPANIES.LIST}${params(filters)}`)),
  getCompany: (id: UUID) => get<Company>(ENDPOINTS.COMPANIES.DETAIL(id)),
  createCompany: (body: CompanyCreateRequest) => post<Company>(ENDPOINTS.COMPANIES.CREATE, body, idempotency(body.idempotency_key)),
  updateCompany: (id: UUID, body: CompanyUpdateRequest) => patch<Company>(ENDPOINTS.COMPANIES.UPDATE(id), body),
  deleteCompany: async (id: UUID, expectedVersion: number): Promise<GovernedResult<null>> => unwrap(await apiClient.delete<ApiEnvelope<null>>(`${ENDPOINTS.COMPANIES.DELETE(id)}?expected_version=${expectedVersion}`)),
  deactivateCompany: (id: UUID, body: TransitionRequest) => post<Company>(ENDPOINTS.COMPANIES.DEACTIVATE(id), body),
  reactivateCompany: (id: UUID, body: TransitionRequest) => post<Company>(ENDPOINTS.COMPANIES.REACTIVATE(id), body),
  getHierarchy: (rootCompanyId?: UUID) => get<CompanyHierarchy>(`${ENDPOINTS.COMPANIES.HIERARCHY}${rootCompanyId ? `?root_company_id=${encodeURIComponent(rootCompanyId)}` : ''}`),
  listSubsidiaries: async (id: UUID, recursive = false) => unwrapPage(await apiClient.get<PaginatedEnvelope<Company>>(`${ENDPOINTS.COMPANIES.SUBSIDIARIES(id)}?recursive=${recursive}`)),
  listConsolidationGroup: async (group: string, filters: PageFilters = {}) => unwrapPage(await apiClient.get<PaginatedEnvelope<Company>>(`${ENDPOINTS.COMPANIES.CONSOLIDATION_GROUP(group)}${params(filters)}`)),

  listAccessGrants: async (filters: AccessGrantFilters = {}) => unwrapPage(await apiClient.get<PaginatedEnvelope<CompanyAccessGrant>>(`${ENDPOINTS.COMPANY_ACCESS.LIST}${params(filters)}`)),
  getAccessGrant: (id: UUID) => get<CompanyAccessGrant>(ENDPOINTS.COMPANY_ACCESS.DETAIL(id)),
  grantAccess: (body: AccessGrantCreateRequest) => post<CompanyAccessGrant>(ENDPOINTS.COMPANY_ACCESS.CREATE, body),
  revokeAccess: (id: UUID, reason: string) => post<CompanyAccessGrant>(ENDPOINTS.COMPANY_ACCESS.REVOKE(id), { reason }),

  listTransactions: async (filters: TransactionFilters = {}) => unwrapPage(await apiClient.get<PaginatedEnvelope<IntercompanyTransaction>>(`${ENDPOINTS.TRANSACTIONS.LIST}${params(filters)}`)),
  getTransaction: (id: UUID) => get<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.DETAIL(id)),
  createTransaction: (body: TransactionCreateRequest) => post<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.CREATE, body, idempotency(body.idempotency_key)),
  updateTransaction: (id: UUID, body: TransactionUpdateRequest) => patch<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.UPDATE(id), body),
  submitTransaction: (id: UUID, body: TransitionRequest) => post<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.SUBMIT(id), body),
  approveTransaction: (id: UUID, body: ApprovalRequest) => post<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.APPROVE(id), body),
  disputeTransaction: (id: UUID, body: ReasonTransitionRequest) => post<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.DISPUTE(id), body),
  resolveDispute: (id: UUID, body: ResolveDisputeRequest) => post<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.RESOLVE_DISPUTE(id), body),
  applyTransferPricing: (id: UUID, body: ApplyPricingRequest) => post<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.APPLY_TRANSFER_PRICING(id), body),
  postTransaction: (id: UUID, body: TransitionRequest, key: string) => post<AsyncJob>(ENDPOINTS.TRANSACTIONS.POST(id), body, idempotency(key)),
  retryTransactionPosting: (id: UUID, body: TransitionRequest, key: string) => post<AsyncJob>(ENDPOINTS.TRANSACTIONS.RETRY_POSTING(id), body, idempotency(key)),
  cancelTransaction: (id: UUID, body: ReasonTransitionRequest) => post<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.CANCEL(id), body),
  reverseTransaction: (id: UUID, body: ReasonTransitionRequest, key: string) => post<IntercompanyTransaction>(ENDPOINTS.TRANSACTIONS.REVERSE(id), body, idempotency(key)),
  getReconciliation: async (filters: ReconciliationFilters = {}) => unwrapPage(await apiClient.get<PaginatedEnvelope<ReconciliationRow>>(`${ENDPOINTS.RECONCILIATION}${params(filters)}`)),

  listConsolidations: async (filters: ConsolidationFilters = {}) => unwrapPage(await apiClient.get<PaginatedEnvelope<ConsolidationRun>>(`${ENDPOINTS.CONSOLIDATIONS.LIST}${params(filters)}`)),
  getConsolidation: (id: UUID) => get<ConsolidationRun>(ENDPOINTS.CONSOLIDATIONS.DETAIL(id)),
  createConsolidation: (body: ConsolidationCreateRequest) => post<ConsolidationRun>(ENDPOINTS.CONSOLIDATIONS.CREATE, body, idempotency(body.idempotency_key)),
  updateConsolidation: (id: UUID, body: ConsolidationUpdateRequest) => patch<ConsolidationRun>(ENDPOINTS.CONSOLIDATIONS.UPDATE(id), body),
  executeConsolidation: (id: UUID, body: TransitionRequest, key: string) => post<AsyncJob>(ENDPOINTS.CONSOLIDATIONS.EXECUTE(id), body, idempotency(key)),
  retryConsolidation: (id: UUID, body: TransitionRequest, key: string) => post<AsyncJob>(ENDPOINTS.CONSOLIDATIONS.RETRY(id), body, idempotency(key)),
  approveConsolidation: (id: UUID, body: TransitionRequest) => post<ConsolidationRun>(ENDPOINTS.CONSOLIDATIONS.APPROVE(id), body),
  publishConsolidation: (id: UUID, body: TransitionRequest) => post<ConsolidationRun>(ENDPOINTS.CONSOLIDATIONS.PUBLISH(id), body),
  cancelConsolidation: (id: UUID, body: ReasonTransitionRequest) => post<ConsolidationRun>(ENDPOINTS.CONSOLIDATIONS.CANCEL(id), body),
  listEliminations: async (runId: UUID, filters: EliminationFilters = {}) => unwrapPage(await apiClient.get<PaginatedEnvelope<EliminationEntry>>(`${ENDPOINTS.CONSOLIDATIONS.ELIMINATIONS(runId)}${params(filters)}`)),
  createElimination: (runId: UUID, body: EliminationCreateRequest) => post<EliminationEntry>(ENDPOINTS.CONSOLIDATIONS.ELIMINATIONS(runId), body, idempotency(body.idempotency_key)),
  getElimination: (id: UUID) => get<EliminationEntry>(ENDPOINTS.ELIMINATIONS.DETAIL(id)),
  getConsolidatedReport: (id: UUID) => get<ConsolidatedReport>(ENDPOINTS.CONSOLIDATIONS.REPORT(id)),

  listTransferPricingRules: async (filters: TransferPricingFilters = {}) => unwrapPage(await apiClient.get<PaginatedEnvelope<TransferPricingRule>>(`${ENDPOINTS.TRANSFER_PRICING_RULES.LIST}${params(filters)}`)),
  getTransferPricingRule: (id: UUID) => get<TransferPricingRule>(ENDPOINTS.TRANSFER_PRICING_RULES.DETAIL(id)),
  createTransferPricingRule: (body: TransferPricingRuleCreateRequest) => post<TransferPricingRule>(ENDPOINTS.TRANSFER_PRICING_RULES.CREATE, body, idempotency(body.idempotency_key)),
  updateTransferPricingRule: (id: UUID, body: TransferPricingRuleUpdateRequest) => patch<TransferPricingRule>(ENDPOINTS.TRANSFER_PRICING_RULES.UPDATE(id), body),
  deleteTransferPricingRule: async (id: UUID, expectedVersion: number) => unwrap(await apiClient.delete<ApiEnvelope<null>>(`${ENDPOINTS.TRANSFER_PRICING_RULES.DELETE(id)}?expected_version=${expectedVersion}`)),
  calculateTransferPrice: (body: TransferPriceRequest) => post<TransferPriceResult>(ENDPOINTS.TRANSFER_PRICING.CALCULATE, body),
  previewTransferPrices: (body: TransferPriceRequest) => post<readonly TransferPriceResult[]>(ENDPOINTS.TRANSFER_PRICING.PREVIEW, body),

  listConfigurationVersions: async (filters: ConfigurationFilters = {}) => unwrapPage(await apiClient.get<PaginatedEnvelope<ConfigurationVersion>>(`${ENDPOINTS.CONFIGURATION.LIST}${params(filters)}`)),
  getConfigurationVersion: (id: UUID) => get<ConfigurationVersion>(ENDPOINTS.CONFIGURATION.DETAIL(id)),
  createConfigurationVersion: (body: ConfigurationCreateRequest) => post<ConfigurationVersion>(ENDPOINTS.CONFIGURATION.CREATE, body),
  updateConfigurationVersion: (id: UUID, body: ConfigurationUpdateRequest) => patch<ConfigurationVersion>(ENDPOINTS.CONFIGURATION.UPDATE(id), body),
  validateConfiguration: (id: UUID) => post<ConfigurationImpact>(ENDPOINTS.CONFIGURATION.VALIDATE(id)),
  previewConfiguration: (id: UUID) => post<ConfigurationImpact>(ENDPOINTS.CONFIGURATION.PREVIEW(id)),
  activateConfiguration: (id: UUID, transitionKey: string) => post<ConfigurationVersion>(ENDPOINTS.CONFIGURATION.ACTIVATE(id), { transition_key: transitionKey }),
  rollbackConfiguration: (id: UUID, body: ConfigurationRollbackRequest) => post<ConfigurationVersion>(ENDPOINTS.CONFIGURATION.ROLLBACK(id), body),
  exportConfiguration: (environment: string, version?: number) => get<SignedConfigurationExport>(`${ENDPOINTS.CONFIGURATION.EXPORT}?environment=${encodeURIComponent(environment)}${version === undefined ? '' : `&version=${version}`}`),
  importConfiguration: (body: SignedConfigurationExport) => post<ConfigurationVersion>(ENDPOINTS.CONFIGURATION.IMPORT, { document: body }),
  getExtensionCatalog: () => get<readonly ExtensionCatalogEntry[]>(ENDPOINTS.EXTENSIONS.CATALOG),
  getJob: (id: UUID) => get<AsyncJob>(ENDPOINTS.JOBS.DETAIL(id)),
  getHealth: () => get<HealthStatus>(ENDPOINTS.HEALTH),
};
