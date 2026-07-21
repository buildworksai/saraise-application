import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BackupExecutionReceipt, ReadinessSummary } from '../contracts';
import { BackupDisasterRecoveryError, backupDisasterRecoveryService } from '../services/backup_disaster_recovery-service';
import { BackupExecutionCreatePage } from '../pages/BackupExecutionCreatePage';
import { DisasterRecoveryDashboardPage } from '../pages/DisasterRecoveryDashboardPage';

const readiness: ReadinessSummary = {
  calculated_at: '2026-07-21T00:00:00Z', rpo_compliance_percent: 98, rto_compliance_percent: 95, last_verified_recovery_point: null, latest_passed_exercise: null, latest_successful_restore: null, latest_failed_restore: null, next_scheduled_exercise: null, stale_runbook_count: 1, unpublished_runbook_count: 2, current_rpo_breaches: 0, current_rto_breaches: 1, queue_state: 'operational', provider_state: 'operational', provider_message: 'Local encrypted storage is operational',
};

const renderPage = (page: ReactElement, initialPath = '/backup-disaster-recovery') => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[initialPath]}><Routes><Route path="*" element={page} /></Routes></MemoryRouter></QueryClientProvider>);
};

afterEach(() => vi.restoreAllMocks());

describe('DisasterRecoveryDashboardPage', () => {
  it('preserves layout with an accessible skeleton while loading', () => {
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockReturnValue(new Promise<ReadinessSummary>(() => undefined));
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(screen.getByLabelText('Loading disaster recovery data')).toHaveAttribute('aria-busy', 'true');
  });

  it('renders an actionable domain empty state and compliance metrics', async () => {
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockResolvedValue(readiness);
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByRole('heading', { name: 'Disaster recovery readiness' })).toBeInTheDocument();
    expect(screen.getByText('Establish your recovery baseline')).toBeInTheDocument();
    expect(screen.getByText('98.0%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request your first backup' })).toBeInTheDocument();
  });

  it('announces queue or provider degradation without provider secrets', async () => {
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockResolvedValue({ ...readiness, provider_state: 'degraded', provider_message: 'Storage probe timed out' });
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByRole('status')).toHaveTextContent('Some recovery operations are degraded');
    expect(screen.getAllByText('Storage probe timed out')).toHaveLength(2);
  });

  it('shows a governed correlation ID and retry control', async () => {
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockRejectedValue(new BackupDisasterRecoveryError('Queue is unavailable', 503, 'queue_unavailable', 'corr-503'));
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Correlation ID: corr-503');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('does not render actions when access is denied', async () => {
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockRejectedValue(new BackupDisasterRecoveryError('Access denied', 403, 'permission_denied', 'corr-403'));
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByText('Permission required')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /backup/i })).not.toBeInTheDocument();
  });
});

describe('BackupExecutionCreatePage', () => {
  it('validates the scope before submission', async () => {
    const request = vi.spyOn(backupDisasterRecoveryService, 'requestBackup');
    renderPage(<BackupExecutionCreatePage />, '/backup-disaster-recovery/backups/new');
    const input = screen.getByLabelText('Canonical scope reference');
    await userEvent.clear(input);
    await userEvent.click(screen.getByRole('button', { name: 'Queue backup' }));
    expect(await screen.findByText('Enter the canonical scope reference.')).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it('prevents duplicate destructive submissions while a request is pending', async () => {
    let finish: ((receipt: BackupExecutionReceipt) => void) | undefined;
    const pending = new Promise<BackupExecutionReceipt>((resolve) => { finish = resolve; });
    const request = vi.spyOn(backupDisasterRecoveryService, 'requestBackup').mockReturnValue(pending);
    renderPage(<BackupExecutionCreatePage />, '/backup-disaster-recovery/backups/new');
    const button = screen.getByRole('button', { name: 'Queue backup' });
    await userEvent.click(button);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: 'Queuing backup…' })).toBeDisabled();
    await act(async () => { finish?.({ backup_job_id: 'job', async_job_id: 'async', idempotency_key: 'key', status: 'queued', requested_at: '2026-07-21T00:00:00Z' }); await pending; });
  });
});
