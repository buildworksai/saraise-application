import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, RefreshCw, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ApiProblem, PageHeader, PageSkeleton, StatusPill } from '../components/ModuleShell';
import { documentIntelligenceService } from '../services/document-intelligence-service';

export function HealthStatusPage() {
  const query = useQuery({ queryKey: ['document-intelligence', 'health'], queryFn: documentIntelligenceService.getHealth });
  if (query.isLoading) return <PageSkeleton table={false} />;
  if (query.error || !query.data) return <main className="p-4 sm:p-8"><PageHeader title="Document intelligence health" description="Live readiness and dependency circuit state." /><div className="mt-6"><ApiProblem error={query.error} onRetry={() => { void query.refetch(); }} /></div></main>;
  const Icon = query.data.status === 'healthy' ? CheckCircle2 : query.data.status === 'degraded' ? AlertTriangle : XCircle;
  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader title="Document intelligence health" description="Readiness is reported by the real governed health endpoint; unavailable dependencies are never shown as healthy." actions={<Button variant="outline" onClick={() => { void query.refetch(); }} disabled={query.isFetching}><RefreshCw className={`mr-2 h-4 w-4 ${query.isFetching ? 'animate-spin' : ''}`} />Retry checks</Button>} />
      <Card className="flex items-center gap-4 p-5" aria-live="polite"><Icon className="h-8 w-8 text-primary" /><div><div className="flex items-center gap-3"><h2 className="text-lg font-semibold">Module status</h2><StatusPill status={query.data.status} /></div><p className="mt-1 text-sm text-muted-foreground">Live: {query.data.live ? 'yes' : 'no'} · Ready: {query.data.ready ? 'yes' : 'no'} · checked {new Date(query.data.checked_at).toLocaleString()}</p></div></Card>
      <section className="grid gap-4 md:grid-cols-2" aria-label="Dependency status">{query.data.dependencies.map((dependency) => <Card key={dependency.name} className="p-5"><div className="flex items-center justify-between gap-3"><h2 className="font-semibold">{dependency.name.replaceAll('_', ' ')}</h2><StatusPill status={dependency.status} /></div><p className="mt-3 font-mono text-xs text-muted-foreground">{dependency.code}</p>{dependency.circuit_state && <p className="mt-2 text-sm text-muted-foreground">Circuit: {dependency.circuit_state.replaceAll('_', ' ')}</p>}</Card>)}</section>
    </main>
  );
}
