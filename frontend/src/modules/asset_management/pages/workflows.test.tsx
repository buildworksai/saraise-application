import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { Asset, DepreciationEntry } from '../contracts';
import { ROUTES } from '../contracts';
import { AssetForm } from '../components/AssetForm';
import { assetService } from '../services/asset-service';
import { AssetDetailPage } from './AssetDetailPage';
import { AssetListPage } from './AssetListPage';

const asset: Asset = {
  id: '00000000-0000-4000-8000-000000000001',
  tenant_id: '00000000-0000-4000-8000-000000000010',
  asset_code: 'LAP-001',
  asset_name: 'Design laptop',
  category: 'fixed',
  purchase_date: '2026-01-01',
  purchase_cost: '1200.00',
  residual_value: '120.00',
  current_value: '1170.00',
  depreciation_method: 'straight_line',
  useful_life_years: 3,
  declining_balance_rate: null,
  location: 'Studio',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
};

const entry: DepreciationEntry = {
  id: '00000000-0000-4000-8000-000000000002',
  tenant_id: asset.tenant_id,
  asset: asset.id,
  asset_code: asset.asset_code,
  asset_name: asset.asset_name,
  entry_date: '2026-02-01',
  depreciation_amount: '30.00',
  accumulated_depreciation: '30.00',
  book_value: '1170.00',
  created_at: '2026-02-01T00:00:00Z',
};

function renderRoute(element: React.ReactElement, path: string, pattern = path) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={element} />
          <Route path="*" element={<p>Navigated away</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('asset management workflows', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows purposeful empty-register guidance', async () => {
    vi.spyOn(assetService, 'listAssets').mockResolvedValue({
      items: [], count: 0, next: null, previous: null,
    });
    renderRoute(<AssetListPage />, ROUTES.ASSETS.LIST);

    expect(await screen.findByText('No assets yet')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Create asset' })).toHaveLength(2);
  });

  it('submits only changed fields when editing a financially locked asset', () => {
    const submit = vi.fn();
    render(
      <AssetForm
        asset={asset}
        pending={false}
        error={null}
        onCancel={vi.fn()}
        onSubmit={submit}
      />,
    );

    expect(screen.getByRole('button', { name: 'No changes' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Asset name'), { target: { value: 'Design laptop – team A' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    expect(submit).toHaveBeenCalledWith({ asset_name: 'Design laptop – team A' });
  });

  it('enforces the non-depreciating current-asset rule in the form', () => {
    render(
      <AssetForm pending={false} error={null} onCancel={vi.fn()} onSubmit={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'current' } });

    expect(screen.getByLabelText('Depreciation method')).toBeDisabled();
    expect(screen.getByText(/Current assets are not depreciated/u)).toBeInTheDocument();
    expect(screen.queryByLabelText('Useful life (years)')).not.toBeInTheDocument();
  });

  it('runs depreciation as an explicit persisted command', async () => {
    vi.spyOn(assetService, 'getAsset').mockResolvedValue(asset);
    vi.spyOn(assetService, 'listDepreciationEntries').mockResolvedValue({
      items: [], count: 0, next: null, previous: null,
    });
    const calculate = vi.spyOn(assetService, 'calculateDepreciation').mockResolvedValue(entry);
    renderRoute(
      <AssetDetailPage />,
      ROUTES.ASSETS.DETAIL(asset.id),
      ROUTES.ASSETS.DETAIL_PATTERN,
    );

    const calculateButtons = await screen.findAllByRole('button', { name: 'Calculate depreciation' });
    const calculateButton = calculateButtons[0];
    if (!calculateButton) throw new Error('The depreciation command was not rendered.');
    fireEvent.click(calculateButton);
    const entryDate = screen.getByLabelText('Entry date');
    fireEvent.change(entryDate, { target: { value: entry.entry_date } });
    fireEvent.click(screen.getByRole('button', { name: 'Calculate and record' }));

    await waitFor(() => expect(calculate).toHaveBeenCalledWith(asset.id, { entry_date: entry.entry_date }));
  });
});
