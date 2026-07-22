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
import { BackupDisasterRecoveryConfigurationPage } from '../pages/BackupDisasterRecoveryConfigurationPage';
import { RestoreRunCreatePage } from '../pages/RestoreRunCreatePage';
import { configurationFixture } from './configuration-fixture';

const readiness: ReadinessSummary = {
  calculated_at: '2026-07-21T00:00:00Z', rpo_compliance_percent: 98, rto_compliance_percent: 95, last_verified_recovery_point: null, latest_passed_exercise: null, latest_successful_restore: null, latest_failed_restore: null, next_scheduled_exercise: null, stale_runbook_count: 1, unpublished_runbook_count: 2, current_rpo_breaches: 0, current_rto_breaches: 1, queue_state: 'operational', provider_state: 'operational', provider_message: 'Local encrypted storage is operational',
};

const renderPage = (page: ReactElement, initialPath = '/backup-disaster-recovery') => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[initialPath]}><Routes><Route path="*" element={page} /></Routes></MemoryRouter></QueryClientProvider>);
};

afterEach(() => vi.restoreAllMocks());

const mockConfiguration = () => vi.spyOn(backupDisasterRecoveryService, 'getConfiguration').mockResolvedValue(configurationFixture);

describe('DisasterRecoveryDashboardPage', () => {
  it('preserves layout with an accessible skeleton while loading', () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockReturnValue(new Promise<ReadinessSummary>(() => undefined));
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(screen.getByLabelText('Loading disaster recovery data')).toHaveAttribute('aria-busy', 'true');
  });

  it('renders an actionable domain empty state and compliance metrics', async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockResolvedValue(readiness);
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByRole('heading', { name: 'Disaster recovery readiness' })).toBeInTheDocument();
    expect(screen.getByText('Establish your recovery baseline')).toBeInTheDocument();
    expect(screen.getByText('98.0%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request your first backup' })).toBeInTheDocument();
    expect(document.title).toBe('Disaster recovery readiness | SARAISE');
  });

  it('announces queue or provider degradation without provider secrets', async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockResolvedValue({ ...readiness, provider_state: 'degraded', provider_message: 'Storage probe timed out' });
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByRole('status')).toHaveTextContent('Some recovery operations are degraded');
    expect(screen.getAllByText('Storage probe timed out')).toHaveLength(2);
  });

  it('shows a governed correlation ID and retry control', async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockRejectedValue(new BackupDisasterRecoveryError('Queue is unavailable', 503, 'queue_unavailable', 'corr-503'));
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Correlation ID: corr-503');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('does not render actions when access is denied', async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, 'getReadiness').mockRejectedValue(new BackupDisasterRecoveryError('Access denied', 403, 'permission_denied', 'corr-403'));
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByText('Permission required')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /backup/i })).not.toBeInTheDocument();
  });
});

describe('configuration-first UI', () => {
  it('keeps production restore unavailable without collecting step-up proof', () => {
    renderPage(<RestoreRunCreatePage />, '/backup-disaster-recovery/restores/new');
    expect(screen.getByRole('option', { name: 'Production (unavailable)' })).toBeDisabled();
    expect(screen.queryByLabelText(/step-up/i)).not.toBeInTheDocument();
  });

  it('requires a server preview before applying configuration', async () => {
    vi.spyOn(backupDisasterRecoveryService, 'getConfiguration').mockResolvedValue(configurationFixture);
    vi.spyOn(backupDisasterRecoveryService, 'listConfigurationVersions').mockResolvedValue([]);
    const preview = vi.spyOn(backupDisasterRecoveryService, 'previewConfiguration').mockResolvedValue({ valid: true, changes: [], document: configurationFixture.document });
    renderPage(<BackupDisasterRecoveryConfigurationPage />, '/backup-disaster-recovery/configuration');
    expect(await screen.findByRole('heading', { name: 'Disaster recovery configuration' })).toBeInTheDocument();
    const apply = screen.getByRole('button', { name: 'Apply configuration' });
    expect(apply).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Preview changes' }));
    await waitFor(() => expect(preview).toHaveBeenCalledTimes(1));
    expect(apply).toBeEnabled();
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
    await act(async () => { finish?.({ backup_job_id: 'job', async_job_id: 'async', status: 'queued', requested_at: '2026-07-21T00:00:00Z' }); await pending; });
  });
});
