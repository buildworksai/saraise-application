import { apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ApiManagementConfiguration,
  type ApiManagementResource,
  type ApiManagementResourceCreate,
  type ApiManagementResourceUpdate,
  type ConfigurationPreview,
  type ConfigurationPreviewRequest,
  type ConfigurationRollbackRequest,
  type ConfigurationVersion,
  type ConfigurationWriteRequest,
  type PaginatedResponse,
  type PortableApiManagementConfiguration,
  type ResourceListFilters,
} from '../contracts';

function isPage<T>(value: PaginatedResponse<T> | readonly T[]): value is PaginatedResponse<T> {
  return !Array.isArray(value);
}

function asPage<T>(value: PaginatedResponse<T> | readonly T[]): PaginatedResponse<T> {
  if (isPage(value)) return value;
  return { count: value.length, next: null, previous: null, results: value };
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
  getConfiguration: (): Promise<ApiManagementConfiguration> => apiClient.get(ENDPOINTS.CONFIGURATION.CURRENT),
  updateConfiguration: (request: ConfigurationWriteRequest): Promise<ApiManagementConfiguration> => apiClient.put(ENDPOINTS.CONFIGURATION.CURRENT, request),
  previewConfiguration: (request: ConfigurationPreviewRequest): Promise<ConfigurationPreview> => apiClient.post(ENDPOINTS.CONFIGURATION.PREVIEW, request),
  listConfigurationHistory: async (): Promise<readonly ConfigurationVersion[]> => {
    const response = await apiClient.get<PaginatedResponse<ConfigurationVersion> | readonly ConfigurationVersion[]>(ENDPOINTS.CONFIGURATION.HISTORY);
    return asPage(response).results;
  },
  rollbackConfiguration: (request: ConfigurationRollbackRequest): Promise<ApiManagementConfiguration> => apiClient.post(ENDPOINTS.CONFIGURATION.ROLLBACK, request),
  importConfiguration: (request: ConfigurationWriteRequest): Promise<ApiManagementConfiguration> => apiClient.post(ENDPOINTS.CONFIGURATION.IMPORT, request),
  exportConfiguration: (): Promise<PortableApiManagementConfiguration> => apiClient.get(ENDPOINTS.CONFIGURATION.EXPORT),
};
