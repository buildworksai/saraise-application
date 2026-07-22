import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { useAuthStore } from '@/stores/auth-store';
import type { CategoryFilters, DepreciationMethod } from '../contracts';
import { EmptyPanel, PageHeader, PageSkeleton, Pagination, ProblemState, StatusPill, titleCase } from '../components/FixedAssetsUI';
import { fixedAssetQueryKeys, fixedAssetsService } from '../services/fixed-assets-service';

export const AssetCategoryListPage = () => {
  const navigate = useNavigate(); const [params, setParams] = useSearchParams(); const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const filters: CategoryFilters = { page: Number(params.get('page') ?? 1), page_size: 25, search: params.get('search') ?? undefined, method: (params.get('method') as DepreciationMethod | null) ?? undefined };
  const query = useQuery({ queryKey: fixedAssetQueryKeys.categories(tenantId, filters), queryFn: () => fixedAssetsService.listCategories(filters) });
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); if (key !== 'page') next.set('page', '1'); setParams(next); };
  if (query.isLoading) return <PageSkeleton table/>;
  if (query.error) return <main className="p-4 sm:p-8"><ProblemState error={query.error} onRetry={() => void query.refetch()}/></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Asset categories" description="Govern default depreciation assumptions and tenant-validated accounting mappings." actions={<Button onClick={() => navigate('/fixed-assets/categories/new')}><Plus className="mr-2 h-4 w-4"/>Create category</Button>}/><Card className="grid gap-3 p-4 sm:grid-cols-2"><Input aria-label="Search categories" placeholder="Search code or name" value={filters.search ?? ''} onChange={(event) => update('search', event.target.value)}/><select aria-label="Depreciation method filter" className="h-10 rounded-md border bg-background px-3" value={filters.method ?? ''} onChange={(event) => update('method', event.target.value)}><option value="">All methods</option>{['straight_line','declining_balance','units_of_production'].map((method) => <option key={method} value={method}>{titleCase(method)}</option>)}</select></Card>{!query.data?.items.length ? <EmptyPanel title="No categories match this view" description="Create the first category with complete accounting mappings." action={{ label: 'Create category', onClick: () => navigate('/fixed-assets/categories/new') }}/> : <Card className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead className="bg-muted text-left"><tr>{['Code','Name','Method','Useful life','Status'].map((heading) => <th key={heading} className="px-4 py-3">{heading}</th>)}</tr></thead><tbody>{query.data.items.map((category) => <tr key={category.id} className="border-t hover:bg-muted/50"><td className="px-4 py-3"><button className="font-medium text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring" onClick={() => navigate(`/fixed-assets/categories/${category.id}`)}>{category.code}</button></td><td className="px-4 py-3">{category.name}</td><td className="px-4 py-3">{titleCase(category.default_depreciation_method)}</td><td className="px-4 py-3">{category.default_useful_life_months} months</td><td className="px-4 py-3"><StatusPill value={category.is_active ? 'active' : 'inactive'}/></td></tr>)}</tbody></table></div><Pagination meta={query.data.pagination} onPage={(page) => update('page', String(page))}/></Card>}</main>;
};
