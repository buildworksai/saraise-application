import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Paginated, RiskAssessment } from '../contracts';
import { complianceRiskService as service, ComplianceRiskApiError } from '../services/compliance-risk-service';
import { RiskAssessmentListPage } from './RiskPages';

const { authState } = vi.hoisted(() => ({ authState: { user: { id: 'user-1', email: 'officer@example.com', username: 'officer', is_staff: false, is_superuser: false, tenant_id: 'tenant-a', platform_role: null, tenant_role: 'compliance_officer' }, isAuthenticated: true, isLoading: false } }));
vi.mock('@/stores/auth-store', () => ({ useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState) }));

const pagination = { page: 1, page_size: 25, count: 0, total_pages: 0, has_next: false, has_previous: false };
const result = (items: RiskAssessment[]): Paginated<RiskAssessment> => ({ items, pagination: { ...pagination, count: items.length, total_pages: items.length ? 1 : 0 }, correlation_id: 'corr-list' });
const risk: RiskAssessment = { id: 'risk-1', risk_code: 'RISK-001', name: 'Supplier compliance', category: 'compliance', description: 'Assess supplier controls', likelihood: 4, impact: 5, inherent_score: '20.00', residual_likelihood: null, residual_impact: null, residual_score: null, risk_level: 'critical', qualitative_rationale: '', mitigation_strategy: '', owner_id: 'owner-1', review_date: '2026-08-01', status: 'assessed', accepted_until: null, closed_at: null, transition_history: [], created_at: '2026-07-23T00:00:00Z', updated_at: '2026-07-23T00:00:00Z', created_by_id: 'actor-1', updated_by_id: null };

function renderPage() { const client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/compliance-risk-management/risks']}><RiskAssessmentListPage/></MemoryRouter></QueryClientProvider>); }

describe('compliance risk pages', () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it('renders geometry-matching loading state then a permission-aware empty state', async () => {
    vi.spyOn(service, 'listRisks').mockResolvedValue(result([])); renderPage();
    expect(screen.getByLabelText('Loading compliance risk information')).toHaveAttribute('aria-busy', 'true');
    expect(await screen.findByText('No risks match this view')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Create risk' })).toBeEnabled();
    expect(document.title).toContain('Risk register');
  });

  it('renders governed successful data without client-derived scoring', async () => {
    vi.spyOn(service, 'listRisks').mockResolvedValue(result([risk])); renderPage();
    expect(await screen.findByRole('button', { name: 'RISK-001' })).toBeVisible();
    expect(screen.getByText('20.00')).toBeVisible();
    expect(screen.getAllByText('Critical').some((element) => element.tagName === 'SPAN')).toBe(true);
  });

  it('shows retryable governed errors with correlation ID', async () => {
    vi.spyOn(service, 'listRisks').mockRejectedValue(new ComplianceRiskApiError('Temporarily unavailable', 503, 'CAPABILITY_UNAVAILABLE', 'corr-failed')); renderPage();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('corr-failed'));
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled();
  });
});
