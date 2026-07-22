import { useQuery } from '@tanstack/react-query';
import { Activity, Download, GitBranch } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ApiProblem, MetricCard, PageHeader, PageSkeleton } from '../components/ModuleShell';
import { formatDate, useCanManageProcessMining } from '../components/utils';
import { PROCESS_MINING_ROUTES } from '../contracts';
import { processMiningService } from '../services/process_mining-service';

export function ProcessDetailPage() {
  const { processName = '' } = useParams(); const name = decodeURIComponent(processName); const navigate = useNavigate(); const canManage = useCanManageProcessMining();
  const query = useQuery({ queryKey: ['process-mining', 'process', name], queryFn: () => processMiningService.getProcess(name), enabled: Boolean(name) });
  if (query.isLoading) return <PageSkeleton/>; if (query.error || !query.data) return <main className="p-4 sm:p-8"><ApiProblem error={query.error} onRetry={() => void query.refetch()}/></main>;
  const item = query.data;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={item.process_name} description="A single evidence path across trace activity, immutable model versions, conformance, bottlenecks, variants, and exports." actions={<><Button variant="outline" onClick={() => navigate(PROCESS_MINING_ROUTES.EVENTS_FOR_PROCESS(name))}><Activity className="mr-2 h-4 w-4"/>Explore events</Button>{canManage && <Button onClick={() => navigate(PROCESS_MINING_ROUTES.DISCOVERY_CREATE_FOR_PROCESS(name))}><GitBranch className="mr-2 h-4 w-4"/>New discovery</Button>}</>}/><section className="grid gap-4 sm:grid-cols-3"><MetricCard label="Events" value={item.event_count} detail="Immutable event evidence"/><MetricCard label="Cases" value={item.case_count} detail="Correlated traces"/><MetricCard label="Reference model" value={item.has_reference ? 'Ready' : 'Not selected'} detail="Explicit conformance baseline"/></section><section className="grid gap-4 lg:grid-cols-2"><Card className="p-6"><h2 className="font-semibold">Evidence timeline</h2><dl className="mt-4 grid gap-3 text-sm"><div><dt className="text-muted-foreground">Latest activity</dt><dd>{formatDate(item.last_activity)}</dd></div><div><dt className="text-muted-foreground">Latest discovery</dt><dd>{formatDate(item.last_discovery)}</dd></div></dl></Card><Card className="p-6"><h2 className="font-semibold">Next evidence step</h2><p className="mt-2 text-sm text-muted-foreground">Inspect raw traces, compare a versioned map, quantify deviations, or produce a checksum-verifiable export.</p><div className="mt-4 flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={() => item.model_id && navigate(PROCESS_MINING_ROUTES.MODEL_MAP(item.model_id))} disabled={!item.model_id}>Open map</Button><Button size="sm" variant="secondary" onClick={() => navigate(PROCESS_MINING_ROUTES.BOTTLENECK_CREATE_FOR_PROCESS(name))}>Analyze bottlenecks</Button><Button size="sm" variant="secondary" onClick={() => navigate(PROCESS_MINING_ROUTES.EXPORT_CREATE_FOR_PROCESS(name))}><Download className="mr-2 h-4 w-4"/>Export</Button></div></Card></section></main>;
}
