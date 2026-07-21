import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ClassificationDetailPage } from './ClassificationDetailPage';
import { ClassificationOverviewPage } from './ClassificationOverviewPage';
import { CreateExtractionPage } from './CreateExtractionPage';
import { CreateTemplatePage } from './CreateTemplatePage';
import { CreateTrainingJobPage } from './CreateTrainingJobPage';
import { EditTemplatePage } from './EditTemplatePage';
import { ExtractionDetailPage } from './ExtractionDetailPage';
import { TrainingJobDetailPage } from './TrainingJobDetailPage';
import { TrainingModelPage } from './TrainingModelPage';
import { TemplateDetailPage } from './TemplateDetailPage';
import { TemplateListPage } from './TemplateListPage';
import { documentIntelligenceService } from '../services/document-intelligence-service';
import {
  candidateModel,
  classificationDetail,
  extractionDetail,
  modelDetail,
  page,
  retiredModel,
  templateDetail,
  trainingDetail,
} from './test-fixtures';

const authState = vi.hoisted(() => ({ user: null as { tenant_role: string | null } | null }));
vi.mock('@/stores/auth-store', () => ({
  useAuthStore: (selector: (state: typeof authState) => boolean) => selector(authState),
}));

function renderRoute(element: React.ReactElement, path = '/document-intelligence/test', pattern = path) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route path={pattern} element={element} /><Route path="*" element={<p>Navigated</p>} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function setAdmin(): void {
  authState.user = { tenant_role: 'tenant_admin' };
}

describe('document intelligence page workflows', () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    authState.user = null;
  });

  it('submits extraction references with a deterministic idempotency key and pending state', async () => {
    const create = vi.spyOn(documentIntelligenceService, 'createExtraction')
      .mockImplementation(() => new Promise(() => undefined));
    renderRoute(<CreateExtractionPage />);

    fireEvent.change(screen.getByLabelText('DMS document UUID'), { target: { value: 'document-1' } });
    fireEvent.change(screen.getByLabelText('Immutable version UUID'), { target: { value: 'version-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue extraction' }));

    await waitFor(() => expect(create).toHaveBeenCalledWith({
      document_id: 'document-1',
      document_version_id: 'version-1',
      engine: 'tesseract',
      extraction_type: 'text',
      template_id: undefined,
      idempotency_key: 'document-intelligence:extract:document-1:version-1:text:tesseract',
    }));
    expect(screen.getByRole('button', { name: 'Validating and queuing…' })).toBeDisabled();
  });

  it('renders immutable extraction evidence and the explicit page-empty state', async () => {
    vi.spyOn(documentIntelligenceService, 'getExtraction').mockResolvedValue(extractionDetail);
    vi.spyOn(documentIntelligenceService, 'listExtractionPages').mockResolvedValue(page([]));
    renderRoute(<ExtractionDetailPage />, `/document-intelligence/extractions/${extractionDetail.id}`, '/document-intelligence/extractions/:id');

    expect(await screen.findByText('Immutable DMS source')).toBeInTheDocument();
    expect(screen.getByText('Page evidence is not available yet.')).toBeInTheDocument();
    expect(screen.getByText(extractionDetail.document_version_id)).toBeInTheDocument();
  });

  it('records review separately from the immutable classification result', async () => {
    setAdmin();
    vi.spyOn(documentIntelligenceService, 'getClassification').mockResolvedValue(classificationDetail);
    vi.spyOn(documentIntelligenceService, 'listClassificationScores').mockResolvedValue(page([]));
    const review = vi.spyOn(documentIntelligenceService, 'reviewClassification').mockResolvedValue({
      ...classificationDetail,
      review_status: 'corrected',
      reviewed_category: 'purchase_order',
    });
    renderRoute(<ClassificationDetailPage />, `/document-intelligence/classifications/${classificationDetail.id}`, '/document-intelligence/classifications/:id');

    fireEvent.click(await screen.findByRole('button', { name: 'Review' }));
    fireEvent.change(screen.getByLabelText('Reviewed category slug'), { target: { value: 'purchase_order' } });
    fireEvent.change(screen.getByLabelText('Review note'), { target: { value: 'Verified against source' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save review' }));

    await waitFor(() => expect(review).toHaveBeenCalledWith(classificationDetail.id, {
      category: 'purchase_order',
      note: 'Verified against source',
    }));
    expect(screen.getByText('invoice')).toBeInTheDocument();
  });

  it('shows the classification empty state without exposing privileged actions', async () => {
    vi.spyOn(documentIntelligenceService, 'listClassifications').mockResolvedValue(page([]));
    renderRoute(<ClassificationOverviewPage />, '/document-intelligence/classifications', '/document-intelligence/classifications');

    expect(await screen.findByText('No classifications found')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Classify document' })).not.toBeInTheDocument();
  });

  it('creates a provider-neutral draft template from validated form state', async () => {
    const create = vi.spyOn(documentIntelligenceService, 'createTemplate').mockResolvedValue(templateDetail);
    renderRoute(<CreateTemplatePage />);

    fireEvent.change(screen.getByLabelText('Template name'), { target: { value: 'Invoice evidence' } });
    fireEvent.change(screen.getByLabelText('Document category (optional)'), { target: { value: 'invoice' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create draft' }));

    await waitFor(() => expect(create).toHaveBeenCalledWith({
      name: 'Invoice evidence',
      description: '',
      document_category: 'invoice',
      engine: 'tesseract',
      match_threshold: '0.7000',
      zones: [],
    }));
  });

  it('protects active template evidence by offering a cloned draft instead of editing', async () => {
    const active = { ...templateDetail, status: 'active' as const, activated_at: templateDetail.created_at };
    vi.spyOn(documentIntelligenceService, 'getTemplate').mockResolvedValue(active);
    vi.spyOn(documentIntelligenceService, 'listTemplateZones').mockResolvedValue(page([]));
    const clone = vi.spyOn(documentIntelligenceService, 'cloneTemplate').mockResolvedValue({
      ...templateDetail,
      id: '00000000-0000-4000-8000-000000000031',
      version: 2,
    });
    renderRoute(<EditTemplatePage />, `/document-intelligence/templates/${active.id}/edit`, '/document-intelligence/templates/:id/edit');

    fireEvent.click(await screen.findByRole('button', { name: 'Clone draft revision' }));
    await waitFor(() => expect(clone).toHaveBeenCalledWith(active.id, { name: 'Invoice template revision 2' }));
    expect(screen.queryByRole('button', { name: 'Save template' })).not.toBeInTheDocument();
  });

  it('renders template-list empty guidance and performs explicit draft activation', async () => {
    vi.spyOn(documentIntelligenceService, 'listTemplates').mockResolvedValue(page([]));
    const listView = renderRoute(<TemplateListPage />, '/document-intelligence/templates', '/document-intelligence/templates');
    expect(await screen.findByText('No extraction templates')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create template' })).not.toBeInTheDocument();
    listView.unmount();

    setAdmin();
    vi.spyOn(documentIntelligenceService, 'getTemplate').mockResolvedValue(templateDetail);
    vi.spyOn(documentIntelligenceService, 'listTemplateZones').mockResolvedValue(page([]));
    const activate = vi.spyOn(documentIntelligenceService, 'activateTemplate').mockResolvedValue({
      ...templateDetail,
      status: 'active',
      activated_at: templateDetail.created_at,
    });
    renderRoute(<TemplateDetailPage />, `/document-intelligence/templates/${templateDetail.id}`, '/document-intelligence/templates/:id');

    fireEvent.click(await screen.findByRole('button', { name: 'Activate' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Activate' }));
    await waitFor(() => expect(activate).toHaveBeenCalledWith(templateDetail.id, expect.objectContaining({ transition_key: expect.any(String) })));
  });

  it('submits a real 50-item training set after client-side category validation', async () => {
    const create = vi.spyOn(documentIntelligenceService, 'createTrainingJob')
      .mockImplementation(() => new Promise(() => undefined));
    const rows = Array.from({ length: 50 }, (_, index) =>
      `document-${index}, version-${index}, ${index < 25 ? 'invoice' : 'receipt'}`,
    ).join('\n');
    renderRoute(<CreateTrainingJobPage />);

    fireEvent.change(screen.getByLabelText('Training job name'), { target: { value: 'AP classifier' } });
    fireEvent.change(screen.getByLabelText('Requested model version'), { target: { value: '2.0.0' } });
    fireEvent.change(screen.getByLabelText('Training examples'), { target: { value: rows } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue training' }));

    await waitFor(() => expect(create).toHaveBeenCalledOnce());
    const request = create.mock.calls[0][0];
    expect(request.items).toHaveLength(50);
    expect(request.idempotency_key).toMatch(/^document-intelligence:train:2.0.0:50:/u);
    expect(screen.getByRole('button', { name: 'Validating and queuing…' })).toBeDisabled();
  });

  it('supports explicit candidate activation and retained-version rollback', async () => {
    setAdmin();
    vi.spyOn(documentIntelligenceService, 'listTrainingJobs').mockResolvedValue(page([]));
    vi.spyOn(documentIntelligenceService, 'listModelVersions').mockResolvedValue(page([candidateModel, retiredModel]));
    const activate = vi.spyOn(documentIntelligenceService, 'activateModelVersion')
      .mockResolvedValue(modelDetail({ ...candidateModel, status: 'active' }));
    const rollback = vi.spyOn(documentIntelligenceService, 'rollbackModelVersion')
      .mockResolvedValue(modelDetail({ ...retiredModel, status: 'active' }));
    renderRoute(<TrainingModelPage />, '/document-intelligence/training', '/document-intelligence/training');

    fireEvent.click(await screen.findByRole('button', { name: 'Activate candidate' }));
    fireEvent.click(screen.getByRole('button', { name: 'Activate' }));
    await waitFor(() => expect(activate).toHaveBeenCalledWith(candidateModel.id, expect.objectContaining({ transition_key: expect.any(String) })));

    fireEvent.click(screen.getByRole('button', { name: 'Rollback to version' }));
    fireEvent.click(screen.getByRole('button', { name: 'Rollback' }));
    await waitFor(() => expect(rollback).toHaveBeenCalledWith(retiredModel.id, expect.objectContaining({ transition_key: expect.any(String) })));
  });

  it('polls active training while preserving durable transition evidence', async () => {
    vi.useFakeTimers();
    const get = vi.spyOn(documentIntelligenceService, 'getTrainingJob').mockResolvedValue(trainingDetail);
    renderRoute(<TrainingJobDetailPage />, `/document-intelligence/training/${trainingDetail.id}`, '/document-intelligence/training/:id');

    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByText('Worker claimed job')).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(get.mock.calls.length).toBeGreaterThan(1);
  });
});
