import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ApiProblem, OutcomeBadge, PageSkeleton, ProofBadge, stableEvidenceJson } from '../components/ModuleShell';
import { BlockchainTraceabilityApiError, blockchainTraceabilityService } from '../services/blockchain_traceability-service';
import { IssueAuthenticityCredentialPage } from './IssueAuthenticityCredentialPage';
import type { AuthenticityCredential } from '../contracts';

const credential: AuthenticityCredential = {
  id: 'credential-1', tenant_id: 'tenant-1', asset_id: 'asset-1', public_id: 'public-1', credential_type: 'product_authenticity', claims: { sku: 'SKU-1' }, claims_hash: 'a'.repeat(64), signature_algorithm: 'ed25519', signature: 'signature', status: 'active', transition_history: [], issued_at: '2026-07-22T10:00:00Z', expires_at: null, revoked_at: null, revocation_reason: '', created_by: 'actor-1', created_at: '2026-07-22T10:00:00Z', updated_at: '2026-07-22T10:00:00Z',
};

describe('blockchain traceability UX safeguards', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('uses a structural skeleton instead of plain loading text', () => {
    render(<PageSkeleton />);
    expect(screen.getByLabelText('Loading traceability evidence')).toHaveAttribute('aria-busy', 'true');
  });

  it('uses exact proof language and never makes simulated evidence green', () => {
    render(<><ProofBadge status="locally_consistent" /><ProofBadge status="externally_verified" /><OutcomeBadge outcome="verified" simulated /></>);
    expect(screen.getByText('Locally consistent — not externally anchored')).toBeInTheDocument();
    expect(screen.getByText('Externally verified')).toBeInTheDocument();
    expect(screen.getByText('Simulated provider — verification unavailable')).not.toHaveClass('text-emerald-700');
  });

  it('renders governed correlation IDs and permission denial distinctly', () => {
    render(<ApiProblem error={new BlockchainTraceabilityApiError('Denied', 403, 'permission_denied', {}, 'corr-denied')} />);
    expect(screen.getByText('Permission required')).toBeInTheDocument();
    expect(screen.getByText('Correlation ID: corr-denied')).toBeInTheDocument();
  });

  it('exports evidence with deterministic property ordering', () => {
    expect(stableEvidenceJson({ z: 1, nested: { z: true, a: false }, a: 2 })).toBe(stableEvidenceJson({ a: 2, nested: { a: false, z: true }, z: 1 }));
  });

  it('shows the authenticity token only in the explicit one-time handoff', async () => {
    vi.spyOn(blockchainTraceabilityService, 'issueCredential').mockResolvedValue({ credential, token: 'one-time-secret', token_recoverable: false });
    render(<MemoryRouter><IssueAuthenticityCredentialPage /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText('Asset ID'), { target: { value: 'asset-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Issue and reveal token once' }));
    await waitFor(() => expect(screen.getByText('Secure one-time token handoff')).toBeInTheDocument());
    expect(screen.getByText('one-time-secret')).toBeInTheDocument();
    expect(screen.getByText(/Non-recoverable/)).toBeInTheDocument();
    expect(blockchainTraceabilityService.issueCredential).toHaveBeenCalledWith({ asset_id: 'asset-1', expires_at: null, claims: {} });
  });
});
