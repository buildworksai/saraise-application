import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiClient } from '@/services/api-client';
import type { ApiV2Envelope, ApiV2Page, GovernedErrorDTO, RecoveryPoint } from '../contracts';
import { backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';

const pagination = { page: 2, page_size: 25, count: 26, total_pages: 2, has_next: false, has_previous: true } as const;
const meta = { correlation_id: 'corr-list', timestamp: '2026-07-21T00:00:00Z', pagination } as const;
const point: RecoveryPoint = {
  id: 'point-1', backup_job_id: 'job-1', backup_archive_id: null, adapter_key: 'local', scope_type: 'tenant', scope_ref: 'tenant', backup_type: 'full', status: 'available', data_cutoff_at: '2026-07-20T00:00:00Z', captured_at: '2026-07-20T00:01:00Z', verified_at: '2026-07-20T00:02:00Z', expires_at: null, size_bytes: 100, checksum_algorithm: 'sha256', checksum_digest: 'a'.repeat(64), verification_evidence: null, created_by: 'actor', transition_history: [], created_at: '2026-07-20T00:01:00Z', updated_at: '2026-07-20T00:02:00Z',
};

describe('backupDisasterRecoveryService', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('unwraps governed data and preserves pagination metadata', async () => {
    const envelope: ApiV2Page<RecoveryPoint> = { data: [point], meta };
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue(envelope);
    await expect(backupDisasterRecoveryService.listRecoveryPoints({ status: 'available', page: 2 })).resolves.toEqual({ items: [point], pagination, correlationId: 'corr-list' });
    expect(get).toHaveBeenCalledWith(expect.stringContaining('status=available'));
    expect(get).toHaveBeenCalledWith(expect.stringContaining('page=2'));
  });

  it('unwraps a detail envelope', async () => {
    const envelope: ApiV2Envelope<RecoveryPoint> = { data: point, meta: { correlation_id: 'corr-detail', timestamp: '2026-07-21T00:00:00Z' } };
    vi.spyOn(apiClient, 'get').mockResolvedValue(envelope);
    await expect(backupDisasterRecoveryService.getRecoveryPoint(point.id)).resolves.toBe(point);
  });

  it('maps governed failures to a typed error with field errors and correlation ID', async () => {
    const governed: GovernedErrorDTO = { error: { code: 'invalid_scope', message: 'Scope is not registered', detail: { scope_ref: ['Choose a registered scope'] }, correlation_id: 'corr-error' } };
    vi.spyOn(apiClient, 'post').mockRejectedValue(new ApiError(governed.error.message, 422, governed));
    const promise = backupDisasterRecoveryService.requestBackup({ backup_type: 'full', scope_type: 'tenant', scope_ref: 'tenant', idempotency_key: 'key' });
    await expect(promise).rejects.toMatchObject({ status: 422, code: 'invalid_scope', correlationId: 'corr-error', fieldErrors: [{ field: 'scope_ref', code: 'invalid', message: 'Choose a registered scope' }] });
  });
});
