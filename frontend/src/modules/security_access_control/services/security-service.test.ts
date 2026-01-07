/**
 * Security Service Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { securityService } from './security-service';
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

describe('securityService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('roles.list', () => {
    it('should fetch list of roles', async () => {
      const mockRoles = [
        { id: '1', name: 'Admin', description: 'Administrator role' },
        { id: '2', name: 'User', description: 'Regular user role' },
      ];

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockRoles);

      const result = await securityService.roles.list();

      expect(result).toEqual(mockRoles);
      expect(apiClient.get).toHaveBeenCalled();
    });
  });

  describe('roles.get', () => {
    it('should fetch single role', async () => {
      const mockRole = { id: '1', name: 'Admin', description: 'Administrator role' };

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockRole);

      const result = await securityService.roles.get('1');

      expect(result).toEqual(mockRole);
      expect(apiClient.get).toHaveBeenCalled();
    });
  });

  describe('permissions.list', () => {
    it('should fetch list of permissions', async () => {
      const mockPermissions = [
        { id: '1', name: 'read:agents', description: 'Read agents' },
        { id: '2', name: 'write:agents', description: 'Write agents' },
      ];

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockPermissions);

      const result = await securityService.permissions.list();

      expect(result).toEqual(mockPermissions);
      expect(apiClient.get).toHaveBeenCalled();
    });
  });
});

