/* eslint-disable complexity, max-lines-per-function */
import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus, Search, X } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { useAuthStore } from '@/stores/auth-store';
import { ROUTES, type AssetCategory, type AssetFilters } from '../contracts';
import {
  EmptyPanel,
  formatAmount,
  formatDate,
  PageHeader,
  PageSkeleton,
  ProblemState,
  StatusPill,
  titleCase,
} from '../components/AssetManagementUI';
import { assetQueryKeys, assetService } from '../services/asset-service';

const PAGE_SIZE = 20;

function positivePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function optionalParam(params: URLSearchParams, key: string): string | undefined {
  const value = params.get(key);
  return value === null || value === '' ? undefined : value;
}

function parseFilters(params: URLSearchParams): AssetFilters {
  const active = params.get('is_active');
  return {
    page: positivePage(params.get('page')),
    page_size: PAGE_SIZE,
    search: optionalParam(params, 'search'),
    category: (params.get('category') as AssetCategory | null) ?? undefined,
    is_active: active === null ? undefined : active === 'true',
    purchase_date_after: optionalParam(params, 'purchase_date_after'),
    purchase_date_before: optionalParam(params, 'purchase_date_before'),
    ordering: optionalParam(params, 'ordering') ?? 'asset_code',
  };
}

export const AssetListPage = () => {
  const navigate = useNavigate();
  const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const [params, setParams] = useSearchParams();
  const filters = parseFilters(params);
  const [search, setSearch] = useState(filters.search ?? '');
  const query = useQuery({
    queryKey: assetQueryKeys.assets(tenantId, filters),
    queryFn: () => assetService.listAssets(filters),
  });

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page') next.set('page', '1');
    setParams(next);
  };
  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    update('search', search.trim());
  };
  const clearFilters = () => {
    setSearch('');
    setParams(new URLSearchParams());
  };
  const hasFilters = [
    filters.search,
    filters.category,
    filters.is_active,
    filters.purchase_date_after,
    filters.purchase_date_before,
  ].some((value) => value !== undefined);

  if (query.isLoading) return <PageSkeleton table />;
  if (query.error) {
    return <main className="p-4 sm:p-8"><ProblemState error={query.error} onRetry={() => void query.refetch()} /></main>;
  }

  const result = query.data;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Asset register"
        description="Track acquisition value, location, and verified depreciation history for tenant-owned assets."
        actions={(
          <Button onClick={() => navigate(ROUTES.ASSETS.CREATE)}>
            <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
            Create asset
          </Button>
        )}
      />

      <Card className="space-y-4 p-4">
        <form className="flex flex-col gap-2 sm:flex-row" role="search" onSubmit={submitSearch}>
          <Input
            aria-label="Search assets"
            placeholder="Search code, name, or location"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Button type="submit" variant="secondary">
            <Search className="mr-2 h-4 w-4" aria-hidden="true" />
            Search
          </Button>
        </form>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <select
            aria-label="Category filter"
            className="h-10 rounded-md border border-input bg-background px-3"
            value={filters.category ?? ''}
            onChange={(event) => update('category', event.target.value)}
          >
            <option value="">All categories</option>
            <option value="fixed">Fixed assets</option>
            <option value="intangible">Intangible assets</option>
            <option value="current">Current assets</option>
          </select>
          <select
            aria-label="Status filter"
            className="h-10 rounded-md border border-input bg-background px-3"
            value={filters.is_active === undefined ? '' : String(filters.is_active)}
            onChange={(event) => update('is_active', event.target.value)}
          >
            <option value="">All statuses</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
          <Input
            aria-label="Purchased on or after"
            title="Purchased on or after"
            type="date"
            value={filters.purchase_date_after ?? ''}
            onChange={(event) => update('purchase_date_after', event.target.value)}
          />
          <Input
            aria-label="Purchased on or before"
            title="Purchased on or before"
            type="date"
            value={filters.purchase_date_before ?? ''}
            onChange={(event) => update('purchase_date_before', event.target.value)}
          />
          <select
            aria-label="Sort assets"
            className="h-10 rounded-md border border-input bg-background px-3"
            value={filters.ordering}
            onChange={(event) => update('ordering', event.target.value)}
          >
            <option value="asset_code">Code A–Z</option>
            <option value="-created_at">Newest first</option>
            <option value="-purchase_date">Latest purchase date</option>
            <option value="-purchase_cost">Highest purchase cost</option>
            <option value="-current_value">Highest current value</option>
          </select>
        </div>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            <X className="mr-2 h-4 w-4" aria-hidden="true" />
            Clear filters
          </Button>
        )}
      </Card>

      {!result || result.items.length === 0 ? (
        <EmptyPanel
          title={hasFilters ? 'No assets match this view' : 'No assets yet'}
          description={hasFilters
            ? 'Clear one or more filters to broaden the register.'
            : 'Create the first asset to begin tracking its lifecycle and depreciation.'}
          action={hasFilters
            ? { label: 'Clear filters', onClick: clearFilters }
            : { label: 'Create asset', onClick: () => navigate(ROUTES.ASSETS.CREATE) }}
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <caption className="sr-only">Assets in the current register view</caption>
              <thead className="bg-muted text-left">
                <tr>
                  {['Code', 'Name', 'Category', 'Purchase date', 'Purchase cost', 'Current value', 'Method', 'Status'].map((heading) => (
                    <th key={heading} scope="col" className="px-4 py-3 font-medium">{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.items.map((asset) => (
                  <tr key={asset.id} className="border-t hover:bg-muted/50">
                    <td className="px-4 py-3">
                      <button
                        className="font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => navigate(ROUTES.ASSETS.DETAIL(asset.id))}
                      >
                        {asset.asset_code}
                      </button>
                    </td>
                    <td className="px-4 py-3">{asset.asset_name}</td>
                    <td className="px-4 py-3">{titleCase(asset.category)}</td>
                    <td className="px-4 py-3">{formatDate(asset.purchase_date)}</td>
                    <td className="px-4 py-3 tabular-nums">{formatAmount(asset.purchase_cost)}</td>
                    <td className="px-4 py-3 font-medium tabular-nums">{formatAmount(asset.current_value)}</td>
                    <td className="px-4 py-3">{titleCase(asset.depreciation_method)}</td>
                    <td className="px-4 py-3"><StatusPill active={asset.is_active} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="flex flex-col gap-3 border-t p-4 sm:flex-row sm:items-center sm:justify-between" aria-label="Asset register pagination">
            <p className="text-sm text-muted-foreground">
              {result.count} {result.count === 1 ? 'asset' : 'assets'} · Page {filters.page ?? 1}
            </p>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                disabled={!result.previous}
                onClick={() => update('page', String(Math.max((filters.page ?? 1) - 1, 1)))}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                disabled={!result.next}
                onClick={() => update('page', String((filters.page ?? 1) + 1))}
              >
                Next
              </Button>
            </div>
          </nav>
        </Card>
      )}
    </main>
  );
};
