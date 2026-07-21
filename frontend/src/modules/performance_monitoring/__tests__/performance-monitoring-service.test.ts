/* eslint-disable @typescript-eslint/unbound-method -- assertions intentionally reference Vitest mocks. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type ApiEnvelope, type Metric } from '../contracts';
import { performanceMonitoringService as service } from '../services/performance-monitoring-service';

vi.mock('@/services/api-client', () => ({
  ApiError: class ApiError extends Error {},
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const meta = {
  correlation_id: 'corr-performance-1',
  timestamp: '2026-07-22T00:00:00Z',
  pagination: { page: 1, page_size: 25, count: 1, total_pages: 1, has_next: false, has_previous: false },
};

const metric: Metric = {
  id: '00000000-0000-4000-8000-000000000001',
  tenant_id: '00000000-0000-4000-8000-000000000002',
  metric_name: 'api.response_time',
  display_name: 'API response time',
  namespace: 'api',
  description: '',
  metric_type: 'histogram',
  unit: 'ms',
  source: null,
  service: null,
  environment: null,
  default_tags: {},
  expected_interval_seconds: 60,
  retention_days: 30,
  is_active: true,
  created_at: '2026-07-22T00:00:00Z',
  updated_at: '2026-07-22T00:00:00Z',
};

describe('performanceMonitoringService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('unwraps governed paginated responses and preserves trace metadata', async () => {
    const envelope: ApiEnvelope<readonly Metric[]> = { data: [metric], meta };
    vi.mocked(apiClient.get).mockResolvedValue(envelope);
    await expect(service.listMetrics({ page: 1, search: 'response' })).resolves.toMatchObject({ items: [metric], correlationId: 'corr-performance-1' });
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.METRICS.LIST}?page=1&search=response`);
  });

  it('rejects a list that omits pagination instead of fabricating counts', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: { correlation_id: 'corr', timestamp: meta.timestamp } });
    await expect(service.listMetrics()).rejects.toThrow('without pagination metadata');
  });

  it('uses the governed batch shape and preserves partial failures', async () => {
    const result = { accepted: 1, rejected: 1, errors: [{ index: 1, code: 'invalid_value', message: 'Value is not finite' }] };
    vi.mocked(apiClient.post).mockResolvedValue({ data: result, meta });
    const points = [{ metric_name: 'api.requests', value: 1 }, { metric_name: 'api.requests', value: Number.NaN }];
    await expect(service.ingestMetricBatch(points)).resolves.toEqual(result);
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.METRICS.BATCH, { data_points: points });
  });

  it('encodes the documented metric query contract', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { metric_name: 'api.response_time', aggregation: 'p95', interval: '5m', data: [] }, meta });
    await service.queryMetric({ metric_name: 'api.response_time', start: '2026-07-21T00:00:00Z', end: '2026-07-22T00:00:00Z', aggregation: 'p95', interval: '5m', tags: { region: 'in' } });
    expect(apiClient.get).toHaveBeenCalledWith(expect.stringContaining(`${ENDPOINTS.METRICS.QUERY}?metric_name=api.response_time`));
    expect(apiClient.get).toHaveBeenCalledWith(expect.stringContaining('tags=region%3Din'));
  });

  it('posts alert transitions and complete SLA report requests', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: metric.id, status: 'accepted' }, meta });
    await service.acknowledgeAlert(metric.id, { note: 'Investigating' });
    await service.resolveAlert(metric.id, { note: 'Recovered' });
    await service.generateSLAReport({ sla_id: metric.id, period: 'calendar_month', format: 'json' });
    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.ALERTS.ACKNOWLEDGE(metric.id), { note: 'Investigating' });
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.ALERTS.RESOLVE(metric.id), { note: 'Recovered' });
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.SLA.REPORTS, { sla_id: metric.id, period: 'calendar_month', format: 'json' });
  });
});
