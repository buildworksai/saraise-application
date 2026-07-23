import { apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type PaginatedRegionalResources,
  type RegionalConfiguration,
  type RegionalConfigurationDocument,
  type RegionalConfigurationEnvironment,
  type RegionalConfigurationExport,
  type RegionalConfigurationHistoryItem,
  type RegionalConfigurationPreview,
  type RegionalConfigurationWrite,
  type RegionalResource,
  type RegionalResourceCreate,
  type RegionalResourceUpdate,
} from '../contracts';

const withEnvironment = (endpoint: string, environment: string): string =>
  `${endpoint}?environment=${encodeURIComponent(environment)}`;

const correlationHeaders = (): Record<string, string> => ({
  'X-Correlation-ID': crypto.randomUUID(),
});

export const regionalService = {
  listResources: (
    search?: string,
    page = 1,
  ): Promise<PaginatedRegionalResources> => {
    const parameters = new URLSearchParams({ page: String(page) });
    if (search) parameters.set('search', search);
    return apiClient.get<PaginatedRegionalResources>(
      `${ENDPOINTS.RESOURCES.LIST}?${parameters.toString()}`,
    );
  },

  getResource: (id: string): Promise<RegionalResource> =>
    apiClient.get<RegionalResource>(ENDPOINTS.RESOURCES.DETAIL(id)),

  createResource: (
    data: RegionalResourceCreate,
    idempotencyKey = crypto.randomUUID(),
  ): Promise<RegionalResource> =>
    apiClient.post<RegionalResource>(ENDPOINTS.RESOURCES.CREATE, data, {
      headers: {
        ...correlationHeaders(),
        'Idempotency-Key': idempotencyKey,
      },
    }),

  updateResource: (
    id: string,
    data: RegionalResourceUpdate,
  ): Promise<RegionalResource> =>
    apiClient.patch<RegionalResource>(ENDPOINTS.RESOURCES.UPDATE(id), data, {
      headers: correlationHeaders(),
    }),

  deleteResource: (id: string): Promise<void> =>
    apiClient.delete<void>(ENDPOINTS.RESOURCES.DELETE(id), {
      headers: correlationHeaders(),
    }),

  restoreResource: (id: string): Promise<RegionalResource> =>
    apiClient.post<RegionalResource>(ENDPOINTS.RESOURCES.RESTORE(id), undefined, {
      headers: correlationHeaders(),
    }),

  activateResource: (id: string): Promise<RegionalResource> =>
    apiClient.post<RegionalResource>(ENDPOINTS.RESOURCES.ACTIVATE(id), undefined, {
      headers: correlationHeaders(),
    }),

  deactivateResource: (id: string): Promise<RegionalResource> =>
    apiClient.post<RegionalResource>(ENDPOINTS.RESOURCES.DEACTIVATE(id), undefined, {
      headers: correlationHeaders(),
    }),

  getConfiguration: (environment: RegionalConfigurationEnvironment): Promise<RegionalConfiguration> =>
    apiClient.get<RegionalConfiguration>(
      withEnvironment(ENDPOINTS.CONFIGURATION.CURRENT, environment),
    ),

  getActiveConfiguration: (): Promise<RegionalConfiguration> =>
    apiClient.get<RegionalConfiguration>(ENDPOINTS.CONFIGURATION.ROOT),

  updateConfiguration: (
    request: RegionalConfigurationWrite,
  ): Promise<RegionalConfiguration> =>
    apiClient.put<RegionalConfiguration>(ENDPOINTS.CONFIGURATION.CURRENT, request, {
      headers: correlationHeaders(),
    }),

  previewConfiguration: (
    environment: RegionalConfigurationEnvironment,
    document: RegionalConfigurationDocument,
  ): Promise<RegionalConfigurationPreview> =>
    apiClient.post<RegionalConfigurationPreview>(
      ENDPOINTS.CONFIGURATION.PREVIEW,
      { environment, document },
      { headers: correlationHeaders() },
    ),

  listConfigurationHistory: (
    environment: RegionalConfigurationEnvironment,
  ): Promise<RegionalConfigurationHistoryItem[]> =>
    apiClient.get<RegionalConfigurationHistoryItem[]>(
      withEnvironment(ENDPOINTS.CONFIGURATION.HISTORY, environment),
    ),

  rollbackConfiguration: (
    environment: RegionalConfigurationEnvironment,
    version: number,
  ): Promise<RegionalConfiguration> =>
    apiClient.post<RegionalConfiguration>(
      ENDPOINTS.CONFIGURATION.ROLLBACK,
      { environment, version },
      { headers: correlationHeaders() },
    ),

  importConfiguration: (
    environment: RegionalConfigurationEnvironment,
    document: RegionalConfigurationDocument,
  ): Promise<RegionalConfiguration> =>
    apiClient.post<RegionalConfiguration>(
      ENDPOINTS.CONFIGURATION.IMPORT,
      { environment, document },
      { headers: correlationHeaders() },
    ),

  exportConfiguration: (
    environment: RegionalConfigurationEnvironment,
  ): Promise<RegionalConfigurationExport> =>
    apiClient.get<RegionalConfigurationExport>(
      withEnvironment(ENDPOINTS.CONFIGURATION.EXPORT, environment),
    ),
};
