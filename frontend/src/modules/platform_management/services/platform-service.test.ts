/**
 * Platform Service Tests
 * 
 * Unit tests for platform-service.ts
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { platformService } from './platform-service';
import { apiClient } from '@/services/api-client';

// Mock apiClient
vi.mock('@/services/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('platformService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('settings', () => {
    it('should list all settings', async () => {
      const mockSettings = [
        { id: '1', key: 'max_tenants', value: '1000', category: 'limits' },
      ];
      const apiGet = vi.spyOn(apiClient, 'get');
      apiGet.mockResolvedValue(mockSettings);

      const result = await platformService.settings.list();

      expect(apiGet).toHaveBeenCalledWith('/api/v1/platform/settings/');
      expect(result).toEqual(mockSettings);
    });

    it('should get setting by id', async () => {
      const mockSetting = { id: '1', key: 'max_tenants', value: '1000' };
      const apiGet = vi.spyOn(apiClient, 'get');
      apiGet.mockResolvedValue(mockSetting);

      const result = await platformService.settings.get('1');

      expect(apiGet).toHaveBeenCalledWith('/api/v1/platform/settings/1/');
      expect(result).toEqual(mockSetting);
    });
  });

  describe('health', () => {
    it('should get current health status', async () => {
      const apiGet = vi.spyOn(apiClient, 'get');
      const mockSummary = {
        status: 'healthy',
        healthy: 3,
        degraded: 0,
        unhealthy: 0,
        total: 3,
        timestamp: '2026-01-01T00:00:00Z',
      };
      const mockRecords = [
        { service_name: 'database', status: 'healthy' },
        { service_name: 'cache', status: 'healthy' },
      ];
      apiGet
        .mockResolvedValueOnce(mockSummary)
        .mockResolvedValueOnce(mockRecords);

      const result = await platformService.health.getCurrent();

      expect(apiGet).toHaveBeenCalledWith('/api/v1/platform/health/summary/');
      expect(apiGet).toHaveBeenCalledWith('/api/v1/platform/health/');
      expect(result.status).toEqual('healthy');
    });
  });

  describe('metrics', () => {
    it('should get current metrics', async () => {
      const mockMetrics = { metrics_data: { tenant_metrics: { total: 487 } } };
      const apiGet = vi.spyOn(apiClient, 'get');
      apiGet.mockResolvedValue(mockMetrics);

      const result = await platformService.metrics.getCurrent('30d', 'complete');

      expect(apiGet).toHaveBeenCalledWith('/api/v1/platform/metrics/current/?time_range=30d&metric_type=complete');
      expect(result).toEqual(mockMetrics.metrics_data);
    });
  });

  describe('alerts', () => {
    it('should get active alerts', async () => {
      const result = await platformService.alerts.getActive();

      expect(result).toEqual([]);
    });

    it('should resolve alert', async () => {
      const result = await platformService.alerts.resolve('1');
      expect(result).toEqual(null);
    });
  });
});
