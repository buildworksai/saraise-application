import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Building2, CircleDollarSign, Clock3 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { useAuthStore } from '@/stores/auth-store';
import { EmptyPanel, formatMoney, PageHeader, PageSkeleton, ProblemState } from '../components/FixedAssetsUI';
import { fixedAssetQueryKeys, fixedAssetsService } from '../services/fixed-assets-service';

export const FixedAssetDashboardPage = () => {
  const navigate = useNavigate(); const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const query = useQuery({ queryKey: fixedAssetQueryKeys.dashboard(tenantId), queryFn: fixedAssetsService.dashboard });
  if (query.isLoading) return <PageSkeleton/>;
  if (query.error) return <main className="p-4 sm:p-8"><ProblemState error={query.error} onRetry={() => void query.refetch()}/></main>;
  if (!query.data || query.data.asset_counts.total === 0) return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Fixed assets" description="Trace every asset from purchase cost to disposal."/><EmptyPanel title="Your asset register is empty" description="Create an account-mapped category, then register your first asset." action={{ label: 'Create category', onClick: () => navigate('/fixed-assets/categories/new') }}/></main>;
  const data = query.data;
  const cards = [{ label: 'Assets', value: data.asset_counts.total, Icon: Building2 }, { label: 'Pending postings', value: data.pending_postings, Icon: Clock3 }, { label: 'Failed postings', value: data.failed_postings, Icon: AlertTriangle }];
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Fixed asset dashboard" description="Financial lifecycle health, grouped by currency without unsafe cross-currency totals." actions={<Button onClick={() => navigate('/fixed-assets/assets/new')}>Register asset</Button>}/><section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Lifecycle summary">{cards.map(({ label, value, Icon }) => <Card key={label} className="p-5"><Icon className="h-5 w-5 text-primary"/><p className="mt-3 text-sm text-muted-foreground">{label}</p><p className="mt-1 text-3xl font-semibold">{value}</p></Card>)}</section><Card className="p-6"><h2 className="font-semibold">Net book value by currency</h2><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{data.book_value_by_currency.map((total) => <div key={total.currency} className="rounded-md border p-4"><CircleDollarSign className="h-5 w-5 text-primary"/><p className="mt-2 text-xs text-muted-foreground">{total.currency}</p><p className="text-lg font-semibold">{formatMoney(total.amount, total.currency)}</p></div>)}</div></Card><Card className="p-6"><h2 className="font-semibold">Lifecycle activity</h2><dl className="mt-4 grid gap-4 sm:grid-cols-2"><div><dt className="text-sm text-muted-foreground">Impairments</dt><dd className="text-2xl font-semibold">{data.impairments}</dd></div><div><dt className="text-sm text-muted-foreground">Disposals</dt><dd className="text-2xl font-semibold">{data.disposals}</dd></div></dl></Card></main>;
};
