import { useQuery } from '@tanstack/react-query';
import { Download, GitBranch, Plus, Search } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { ApiProblem, DataTable, EmptyPanel, MetricCard, PageHeader, PageSkeleton, Pagination } from '../components/ModuleShell';
import { PROCESS_MINING_ROUTES } from '../contracts';
import { formatDate, useCanManageProcessMining } from '../components/utils';
import { processMiningService } from '../services/process_mining-service';

export function ProcessOverviewPage() {
  const navigate = useNavigate();
  const canManage = useCanManageProcessMining();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get('search') ?? '');
  const page = Number(params.get('page') ?? 1);
  const configuration = useQuery({ queryKey: ['process-mining', 'configuration'], queryFn: processMiningService.getConfiguration });
  const query = useQuery({ queryKey: ['process-mining', 'processes', page, params.get('search'), configuration.data?.version], queryFn: () => processMiningService.listProcesses({ page, page_size: configuration.data?.document.list_page_size, search: params.get('search') ?? undefined, ordering: '-last_activity' }), enabled: Boolean(configuration.data) });
  if (query.isLoading || configuration.isLoading) return <PageSkeleton/>;
  if (query.error || configuration.error || !query.data) return <main className="p-4 sm:p-8"><ApiProblem error={query.error ?? configuration.error} onRetry={() => { void query.refetch(); void configuration.refetch(); }}/></main>;
  const events = query.data.items.reduce((sum, item) => sum + item.event_count, 0);
  const cases = query.data.items.reduce((sum, item) => sum + item.case_count, 0);
  const update = (nextPage: number, nextSearch = params.get('search') ?? '') => setParams({ ...(nextSearch ? { search: nextSearch } : {}), page: String(nextPage) });
  const eventQuery = (name: string) => `${PROCESS_MINING_ROUTES.EVENTS}?process_name=${encodeURIComponent(name)}`;
  const exportQuery = (name: string) => `${PROCESS_MINING_ROUTES.EXPORT_CREATE}?process_name=${encodeURIComponent(name)}`;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Process landscape" description="Follow immutable operational evidence from a process summary to models, conformance, bottlenecks, variants, and audit exports." actions={canManage ? <><Button variant="outline" onClick={() => navigate(PROCESS_MINING_ROUTES.EVENT_INGEST)}><Plus className="mr-2 h-4 w-4"/>Ingest events</Button><Button onClick={() => navigate(PROCESS_MINING_ROUTES.DISCOVERY_CREATE)}><GitBranch className="mr-2 h-4 w-4"/>Discover process</Button></> : undefined}/><section className="grid gap-4 sm:grid-cols-3" aria-label="Process totals"><MetricCard label="Processes" value={query.data.pagination.count} detail="Distinct process identities"/><MetricCard label="Events on page" value={events} detail="Immutable evidence rows"/><MetricCard label="Cases on page" value={cases} detail="Distinct correlated traces"/></section><Card className="p-4"><form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); update(1, search.trim()); }}><Input aria-label="Search processes" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search process name"/><Button type="submit" variant="secondary"><Search className="mr-2 h-4 w-4"/>Search</Button></form></Card>{query.data.items.length === 0 ? <EmptyPanel title="No process evidence yet" description="Ingest a canonical event batch to create the first traceable process landscape." action={canManage ? <Button onClick={() => navigate(PROCESS_MINING_ROUTES.EVENT_INGEST)}>Ingest canonical events</Button> : undefined}/> : <Card className="overflow-hidden"><DataTable headers={['Process', 'Events', 'Cases', 'Last activity', 'Reference model', 'Actions']} rows={query.data.items.map((item) => [<button className="font-semibold text-primary focus-visible:ring-2 focus-visible:ring-ring" onClick={() => navigate(PROCESS_MINING_ROUTES.PROCESS(item.process_name))}>{item.process_name}</button>, item.event_count, item.case_count, formatDate(item.last_activity), item.has_reference ? 'Selected' : 'Not selected', <div className="flex gap-1"><Button size="sm" variant="ghost" onClick={() => navigate(eventQuery(item.process_name))}>Evidence</Button><Button size="sm" variant="ghost" onClick={() => navigate(exportQuery(item.process_name))} aria-label={`Export ${item.process_name}`}><Download className="h-4 w-4"/></Button></div>])}/><Pagination value={query.data.pagination} onPage={(value) => update(value)}/></Card>}</main>;
}
