import { apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type AIModel,
  type AIModelDeployment,
  type AIModelDeploymentCreate,
  type AIModelDeploymentUpdate,
  type AIProvider,
  type AIProviderConfigurationResource,
  type AIProviderCredential,
  type AIProviderCredentialCreate,
  type AIProviderCredentialUpdate,
  type AIProviderRuntimeConfiguration,
  type AIProviderRuntimeConfigurationAudit,
  type AIProviderRuntimeConfigurationVersion,
  type AIUsageLog,
  type ListFilters,
  type ListResponse,
  type ModuleHealth,
  type RuntimeConfigurationDocument,
  type RuntimeConfigurationPreview,
  type RuntimeConfigurationValues,
  type UUID,
} from '../contracts';

export function normalizeList<T>(response: ListResponse<T>): T[] {
  return Array.isArray(response) ? response : response.results;
}

function withFilters(path: string, filters: ListFilters): string {
  const params = new URLSearchParams();
  (Object.entries(filters) as [string, string | undefined][]).forEach(([key, value]) => {
    if (value !== undefined && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

async function list<T>(path: string, filters: ListFilters = {}): Promise<T[]> {
  const response = await apiClient.get<ListResponse<T>>(withFilters(path, filters));
  return normalizeList(response);
}

function mutationHeaders(): RequestInit {
  const randomUUID = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  return { headers: { 'Idempotency-Key': randomUUID } };
}

export const aiProviderConfigurationService = {
  listResources: (filters: ListFilters = {}) =>
    list<AIProviderConfigurationResource>(ENDPOINTS.RESOURCES.LIST, filters),

  listProviders: (filters: ListFilters = {}) => list<AIProvider>(ENDPOINTS.PROVIDERS.LIST, filters),
  getProvider: (id: UUID) => apiClient.get<AIProvider>(ENDPOINTS.PROVIDERS.DETAIL(id)),

  listCredentials: (filters: ListFilters = {}) => list<AIProviderCredential>(ENDPOINTS.CREDENTIALS.LIST, filters),
  getCredential: (id: UUID) => apiClient.get<AIProviderCredential>(ENDPOINTS.CREDENTIALS.DETAIL(id)),
  createCredential: (request: AIProviderCredentialCreate) =>
    apiClient.post<AIProviderCredential>(ENDPOINTS.CREDENTIALS.CREATE, request, mutationHeaders()),
  updateCredential: (id: UUID, request: AIProviderCredentialUpdate) =>
    apiClient.patch<AIProviderCredential>(ENDPOINTS.CREDENTIALS.UPDATE(id), request),
  deleteCredential: (id: UUID) => apiClient.delete<void>(ENDPOINTS.CREDENTIALS.DELETE(id)),

  listModels: (filters: ListFilters = {}) => list<AIModel>(ENDPOINTS.MODELS.LIST, filters),
  getModel: (id: UUID) => apiClient.get<AIModel>(ENDPOINTS.MODELS.DETAIL(id)),

  listDeployments: (filters: ListFilters = {}) => list<AIModelDeployment>(ENDPOINTS.DEPLOYMENTS.LIST, filters),
  getDeployment: (id: UUID) => apiClient.get<AIModelDeployment>(ENDPOINTS.DEPLOYMENTS.DETAIL(id)),
  createDeployment: (request: AIModelDeploymentCreate) =>
    apiClient.post<AIModelDeployment>(ENDPOINTS.DEPLOYMENTS.CREATE, request, mutationHeaders()),
  updateDeployment: (id: UUID, request: AIModelDeploymentUpdate) =>
    apiClient.patch<AIModelDeployment>(ENDPOINTS.DEPLOYMENTS.UPDATE(id), request),
  activateDeployment: (id: UUID) =>
    apiClient.post<AIModelDeployment>(ENDPOINTS.DEPLOYMENTS.ACTIVATE(id)),
  deactivateDeployment: (id: UUID) =>
    apiClient.post<AIModelDeployment>(ENDPOINTS.DEPLOYMENTS.DEACTIVATE(id)),
  deleteDeployment: (id: UUID) => apiClient.delete<void>(ENDPOINTS.DEPLOYMENTS.DELETE(id)),

  listUsageLogs: (filters: ListFilters = {}) => list<AIUsageLog>(ENDPOINTS.USAGE_LOGS.LIST, filters),
  getUsageLog: (id: UUID) => apiClient.get<AIUsageLog>(ENDPOINTS.USAGE_LOGS.DETAIL(id)),
  getHealth: () => apiClient.get<ModuleHealth>(ENDPOINTS.HEALTH),

  getRuntimeConfiguration: () =>
    apiClient.get<AIProviderRuntimeConfiguration>(ENDPOINTS.RUNTIME_CONFIGURATION.CURRENT),
  updateRuntimeConfiguration: (environment: string, values: RuntimeConfigurationValues) =>
    apiClient.put<AIProviderRuntimeConfiguration>(ENDPOINTS.RUNTIME_CONFIGURATION.CURRENT, { environment, values }),
  previewRuntimeConfiguration: (environment: string, values: RuntimeConfigurationValues) =>
    apiClient.post<RuntimeConfigurationPreview>(ENDPOINTS.RUNTIME_CONFIGURATION.PREVIEW, { environment, values }),
  listRuntimeConfigurationVersions: () =>
    apiClient.get<AIProviderRuntimeConfigurationVersion[]>(ENDPOINTS.RUNTIME_CONFIGURATION.VERSIONS),
  listRuntimeConfigurationAudit: () =>
    apiClient.get<AIProviderRuntimeConfigurationAudit[]>(ENDPOINTS.RUNTIME_CONFIGURATION.AUDIT),
  rollbackRuntimeConfiguration: (version: number, environment = 'default') =>
    apiClient.post<AIProviderRuntimeConfiguration>(ENDPOINTS.RUNTIME_CONFIGURATION.ROLLBACK, { version, environment }),
  exportRuntimeConfiguration: () =>
    apiClient.get<RuntimeConfigurationDocument>(ENDPOINTS.RUNTIME_CONFIGURATION.EXPORT),
  importRuntimeConfiguration: (document: RuntimeConfigurationDocument) =>
    apiClient.post<AIProviderRuntimeConfiguration>(ENDPOINTS.RUNTIME_CONFIGURATION.IMPORT, { document }),
};

/** Temporary compatibility alias for older imports outside this module. */
export const ai_provider_configurationService = aiProviderConfigurationService;
