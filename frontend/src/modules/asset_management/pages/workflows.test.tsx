import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { Asset, AssetConfiguration, AssetConfigurationDocument, DepreciationEntry } from '../contracts';
import { ROUTES } from '../contracts';
import { AssetForm } from '../components/AssetForm';
import { assetService } from '../services/asset-service';
import { AssetDetailPage } from './AssetDetailPage';
import { AssetListPage } from './AssetListPage';

const asset: Asset = {
  id: '00000000-0000-4000-8000-000000000001',
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
  asset: asset.id,
  asset_code: asset.asset_code,
  asset_name: asset.asset_name,
  entry_date: '2026-02-01',
  depreciation_amount: '30.00',
  accumulated_depreciation: '30.00',
  book_value: '1170.00',
  created_at: '2026-02-01T00:00:00Z',
};

const configurationDocument: AssetConfigurationDocument = {
  environment: 'default',
  enabled: true,
  rollout_roles: [],
  rollout_cohorts: [],
  asset_code_max_length: 50,
  asset_name_max_length: 255,
  location_max_length: 255,
  monetary_max_digits: 15,
  monetary_decimal_places: 2,
  minimum_purchase_cost: '0.01',
  default_residual_value: '0.00',
  default_current_value: '0.00',
  new_asset_active_default: true,
  allowed_categories: ['fixed', 'intangible', 'current'],
  default_category: 'fixed',
  allowed_depreciation_methods: ['straight_line', 'declining_balance', 'none'],
  default_depreciation_method: 'straight_line',
  non_depreciable_categories: ['current'],
  useful_life_min_years: 1,
  useful_life_max_years: 100,
  default_useful_life_years: 5,
  declining_rate_min: '0.0001',
  declining_rate_max: '100.0000',
  percentage_divisor: '100',
  double_declining_factor: '2',
  annual_cap: '1',
  accounting_periods_per_year: 12,
  posting_frequency: 'monthly',
  require_chronological_depreciation: true,
  require_useful_life_for_depreciation: true,
  declining_rate_requires_declining_method: true,
  inactive_assets_depreciable: false,
  allow_depreciation_before_purchase: false,
  lock_financial_fields_after_history: true,
  archive_sets_inactive: true,
  archive_confirmation: 'asset_code',
  asset_list_page_size: 25,
  asset_list_max_page_size: 100,
  asset_list_default_ordering: 'asset_code',
  asset_detail_history_page_size: 12,
  asset_search_fields: ['asset_code', 'asset_name', 'location'],
  asset_ordering_fields: ['asset_code', 'asset_name', 'purchase_date', 'purchase_cost', 'current_value', 'created_at'],
  tenant_throttle_rate: '240/minute',
  health_interval_seconds: 60,
};

const configuration: AssetConfiguration = {
  id: '00000000-0000-4000-8000-000000000003',
  version: 1,
  document: configurationDocument,
  limits: {},
  updated_at: '2026-01-01T00:00:00Z',
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
    vi.spyOn(assetService, 'getConfiguration').mockResolvedValue(configuration);
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
        configuration={configurationDocument}
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
    render(<AssetForm configuration={configurationDocument} pending={false} error={null} onCancel={vi.fn()} onSubmit={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'current' } });

    expect(screen.getByLabelText('Depreciation method')).toBeDisabled();
    expect(screen.getByText(/Current assets are not depreciated/u)).toBeInTheDocument();
    expect(screen.queryByLabelText('Useful life (years)')).not.toBeInTheDocument();
  });

  it('runs depreciation as an explicit persisted command', async () => {
    vi.spyOn(assetService, 'getAsset').mockResolvedValue(asset);
    vi.spyOn(assetService, 'getConfiguration').mockResolvedValue(configuration);
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
