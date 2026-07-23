import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type ApiManagementConfigurationSchema, type ApiManagementResource } from '../contracts';
import { api_managementService } from './api_management-service';

vi.mock('@/services/api-client', () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const getMock = vi.spyOn(apiClient, 'get');
const postMock = vi.spyOn(apiClient, 'post');

const resource = {
  id: '00000000-0000-4000-8000-000000000001',
  name: 'Resource',
  description: '',
  is_active: true,
  config: {},
  version: 1,
  created_at: '2026-07-23T10:00:00Z',
  updated_at: '2026-07-23T10:00:00Z',
} satisfies ApiManagementResource;

describe('api_managementService', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('normalizes a transitional list response without fabricating items', async () => {
    getMock.mockResolvedValue([resource]);
    await expect(api_managementService.listResources({ search: 'Resource', page: 1 })).resolves.toEqual({ count: 1, next: null, previous: null, results: [resource] });
    expect(getMock).toHaveBeenCalledWith(ENDPOINTS.RESOURCES.LIST({ search: 'Resource', page: 1 }));
  });

  it('sends resource idempotency in the required header, never the body', async () => {
    postMock.mockResolvedValue(resource);
    const idempotencyKey = '00000000-0000-4000-8000-000000000010';
    await api_managementService.createResource({ name: resource.name, config: {}, idempotency_key: idempotencyKey });
    expect(postMock).toHaveBeenCalledWith(ENDPOINTS.RESOURCES.CREATE, { name: resource.name, config: {} }, { headers: { 'Idempotency-Key': idempotencyKey } });
  });

  it('adds fresh idempotency headers to lifecycle operations', async () => {
    const idempotencyKey = '00000000-0000-4000-8000-000000000011';
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(idempotencyKey);
    postMock.mockResolvedValue(resource);
    await api_managementService.activateResource(resource.id);
    expect(postMock).toHaveBeenCalledWith(ENDPOINTS.RESOURCES.ACTIVATE(resource.id), undefined, { headers: { 'Idempotency-Key': idempotencyKey } });
    await api_managementService.restoreResource(resource.id);
    expect(postMock).toHaveBeenLastCalledWith(ENDPOINTS.RESOURCES.RESTORE(resource.id), undefined, { headers: { 'Idempotency-Key': idempotencyKey } });
  });

  it('uses governed resource version and rollback endpoints', async () => {
    const idempotencyKey = '00000000-0000-4000-8000-000000000012';
    getMock.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    await api_managementService.listResourceVersions(resource.id);
    expect(getMock).toHaveBeenCalledWith(ENDPOINTS.RESOURCES.VERSIONS(resource.id));
    postMock.mockResolvedValue(resource);
    await api_managementService.rollbackResource(resource.id, {
      version: 1,
      idempotency_key: idempotencyKey,
    });
    expect(postMock).toHaveBeenCalledWith(
      ENDPOINTS.RESOURCES.ROLLBACK(resource.id),
      { version: 1 },
      { headers: { 'Idempotency-Key': idempotencyKey } },
    );
  });

  it('uses only the configuration endpoint registry', async () => {
    postMock.mockResolvedValue({ valid: true, normalized_document: {}, changes: [] });
    await api_managementService.previewConfiguration('staging', { document: { page_size: 25 } });
    expect(postMock).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.PREVIEW('staging'), { document: { page_size: 25 } });
    getMock.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    await api_managementService.listConfigurationHistory('staging', { page: 2, page_size: 25 });
    expect(getMock).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.HISTORY('staging', { page: 2, page_size: 25 }));
  });

  it('loads runtime configuration only from the server-selected governed environment', async () => {
    const schema = {
      schema_version: 2,
      environment: 'production',
      environments: ['development', 'production'],
      fields: {},
      dependencies: [],
      navigation: {
        resources_list: { order: 1 },
        resources_create: { order: 2 },
        resources_detail: { order: 3 },
        configuration: { order: 4 },
      },
      platform_hard_ceilings: {},
    } satisfies ApiManagementConfigurationSchema;
    getMock.mockResolvedValueOnce(schema).mockResolvedValueOnce({ environment: 'production' });

    await api_managementService.getRuntimeConfiguration();

    expect(getMock).toHaveBeenNthCalledWith(1, ENDPOINTS.CONFIGURATION.SCHEMA());
    expect(getMock).toHaveBeenNthCalledWith(2, ENDPOINTS.CONFIGURATION.CURRENT('production'));
  });

  it('fails closed when the selected runtime environment is not registered', async () => {
    getMock.mockResolvedValue({
      schema_version: 2,
      environment: 'production',
      environments: ['development'],
      fields: {},
      dependencies: [],
      navigation: {
        resources_list: { order: 1 },
        resources_create: { order: 2 },
        resources_detail: { order: 3 },
        configuration: { order: 4 },
      },
      platform_hard_ceilings: {},
    } satisfies ApiManagementConfigurationSchema);

    await expect(api_managementService.getRuntimeConfiguration()).rejects.toThrow(
      'no valid runtime environment',
    );
    expect(getMock).toHaveBeenCalledTimes(1);
  });
});
