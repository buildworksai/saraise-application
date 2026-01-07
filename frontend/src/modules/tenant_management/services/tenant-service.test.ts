/**
 * Tenant Service Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { tenantService } from './tenant-service';
import { apiClient } from '@/services/api-client';

// Mock apiClient
vi.mock('@/services/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('tenantService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('tenants.list', () => {
    it('should fetch list of tenants', async () => {
      const mockTenants = [
        { id: '1', name: 'Tenant 1', domain: 'tenant1.com', is_active: true },
        { id: '2', name: 'Tenant 2', domain: 'tenant2.com', is_active: false },
      ];

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockTenants);

      const result = await tenantService.tenants.list();

      expect(result).toEqual(mockTenants);
      expect(apiClient.get).toHaveBeenCalled();
    });
  });

  describe('tenants.get', () => {
    it('should fetch single tenant', async () => {
      const mockTenant = { id: '1', name: 'Tenant 1', domain: 'tenant1.com', is_active: true };

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockTenant);

      const result = await tenantService.tenants.get('1');

      expect(result).toEqual(mockTenant);
      expect(apiClient.get).toHaveBeenCalled();
    });
  });
});

