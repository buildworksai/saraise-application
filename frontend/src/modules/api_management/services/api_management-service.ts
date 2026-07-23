import { apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiManagementConfiguration,
  type ApiManagementConfigurationSchema,
  type ApiManagementResource,
  type ApiManagementResourceCreate,
  type ApiManagementResourceUpdate,
  type ApiManagementResourceVersion,
  type ConfigurationImportRequest,
  type ConfigurationHistoryFilters,
  type ConfigurationPreview,
  type ConfigurationPreviewRequest,
  type ConfigurationRollbackRequest,
  type ConfigurationVersion,
  type ConfigurationWriteRequest,
  type DeploymentEnvironment,
  type PaginatedResponse,
  type PortableApiManagementConfiguration,
  type ResourceListFilters,
  type ResourceRollbackRequest,
} from '../contracts';

function isPage<T>(value: PaginatedResponse<T> | readonly T[]): value is PaginatedResponse<T> {
  return !Array.isArray(value);
}

function asPage<T>(value: PaginatedResponse<T> | readonly T[]): PaginatedResponse<T> {
  if (isPage(value)) return value;
  return { count: value.length, next: null, previous: null, results: value };
}

async function getRuntimeConfiguration(): Promise<ApiManagementConfiguration> {
  const schema = await apiClient.get<ApiManagementConfigurationSchema>(ENDPOINTS.CONFIGURATION.SCHEMA());
  if (!schema.environment || !schema.environments.includes(schema.environment)) {
    throw new Error('The server configuration schema has no valid runtime environment.');
  }
  return apiClient.get(ENDPOINTS.CONFIGURATION.CURRENT(schema.environment));
}

export const api_managementService = {
  listResources: async (filters: ResourceListFilters = {}): Promise<PaginatedResponse<ApiManagementResource>> => {
    const response = await apiClient.get<PaginatedResponse<ApiManagementResource> | readonly ApiManagementResource[]>(ENDPOINTS.RESOURCES.LIST(filters));
    return asPage(response);
  },
  getResource: (id: string): Promise<ApiManagementResource> => apiClient.get(ENDPOINTS.RESOURCES.DETAIL(id)),
  createResource: (data: ApiManagementResourceCreate): Promise<ApiManagementResource> => {
    const { idempotency_key, ...body } = data;
    return apiClient.post(ENDPOINTS.RESOURCES.CREATE, body, { headers: { 'Idempotency-Key': idempotency_key } });
  },
  updateResource: (id: string, data: ApiManagementResourceUpdate): Promise<ApiManagementResource> => {
    const { idempotency_key, ...body } = data;
    return apiClient.put(ENDPOINTS.RESOURCES.UPDATE(id), body, { headers: { 'Idempotency-Key': idempotency_key } });
  },
  deleteResource: (id: string): Promise<void> => apiClient.delete(ENDPOINTS.RESOURCES.DELETE(id), { headers: { 'Idempotency-Key': crypto.randomUUID() } }),
  restoreResource: (id: string): Promise<ApiManagementResource> => apiClient.post(ENDPOINTS.RESOURCES.RESTORE(id), undefined, { headers: { 'Idempotency-Key': crypto.randomUUID() } }),
  activateResource: (id: string): Promise<ApiManagementResource> => apiClient.post(ENDPOINTS.RESOURCES.ACTIVATE(id), undefined, { headers: { 'Idempotency-Key': crypto.randomUUID() } }),
  deactivateResource: (id: string): Promise<ApiManagementResource> => apiClient.post(ENDPOINTS.RESOURCES.DEACTIVATE(id), undefined, { headers: { 'Idempotency-Key': crypto.randomUUID() } }),
  listResourceVersions: (id: string): Promise<PaginatedResponse<ApiManagementResourceVersion>> =>
    apiClient.get(ENDPOINTS.RESOURCES.VERSIONS(id)),
  rollbackResource: (id: string, request: ResourceRollbackRequest): Promise<ApiManagementResource> => {
    const { idempotency_key, ...body } = request;
    return apiClient.post(ENDPOINTS.RESOURCES.ROLLBACK(id), body, {
      headers: { 'Idempotency-Key': idempotency_key },
    });
  },
  getConfigurationSchema: (environment?: DeploymentEnvironment): Promise<ApiManagementConfigurationSchema> =>
    apiClient.get(ENDPOINTS.CONFIGURATION.SCHEMA(environment)),
  getRuntimeConfiguration,
  getConfiguration: (environment: DeploymentEnvironment): Promise<ApiManagementConfiguration> => apiClient.get(ENDPOINTS.CONFIGURATION.CURRENT(environment)),
  updateConfiguration: (environment: DeploymentEnvironment, request: ConfigurationWriteRequest): Promise<ApiManagementConfiguration> => apiClient.put(ENDPOINTS.CONFIGURATION.CURRENT(environment), request),
  previewConfiguration: (environment: DeploymentEnvironment, request: ConfigurationPreviewRequest): Promise<ConfigurationPreview> => apiClient.post(ENDPOINTS.CONFIGURATION.PREVIEW(environment), request),
  listConfigurationHistory: (environment: DeploymentEnvironment, filters: ConfigurationHistoryFilters = {}): Promise<PaginatedResponse<ConfigurationVersion>> => apiClient.get(ENDPOINTS.CONFIGURATION.HISTORY(environment, filters)),
  rollbackConfiguration: (environment: DeploymentEnvironment, request: ConfigurationRollbackRequest): Promise<ApiManagementConfiguration> => apiClient.post(ENDPOINTS.CONFIGURATION.ROLLBACK(environment), request),
  importConfiguration: (environment: DeploymentEnvironment, request: ConfigurationImportRequest): Promise<ApiManagementConfiguration> => apiClient.post(ENDPOINTS.CONFIGURATION.IMPORT(environment), request),
  exportConfiguration: (environment: DeploymentEnvironment): Promise<PortableApiManagementConfiguration> => apiClient.get(ENDPOINTS.CONFIGURATION.EXPORT(environment)),
};
