import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LayoutDashboard, Plus, Server } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import type { MonitoringDashboardCreate, MonitoringEnvironmentCreate } from '../contracts';
import { performanceMonitoringService } from '../services/performance-monitoring-service';
import { EmptyTelemetry, MonitoringPage, OperationalError, PageSkeleton, StatusPill, formatTime } from '../components/MonitoringPage';

const blankEnvironment = (kind: string): MonitoringEnvironmentCreate => ({ name: '', slug: '', description: '', kind, is_active: true });
const blankDashboard = (refreshInterval: number): MonitoringDashboardCreate => ({ name: '', description: '', layout: {}, variables: [], refresh_interval_seconds: refreshInterval, is_default: false, is_active: true });

export function MonitoringCatalogPage() {
  const client = useQueryClient();
  const [environmentDraft, setEnvironmentDraft] = useState<MonitoringEnvironmentCreate | null>(null);
  const [dashboardDraft, setDashboardDraft] = useState<MonitoringDashboardCreate | null>(null);
  const environments = useQuery({ queryKey: ['performance-monitoring', 'environments'], queryFn: () => performanceMonitoringService.listEnvironments({ page_size: 100, ordering: 'name' }) });
  const dashboards = useQuery({ queryKey: ['performance-monitoring', 'dashboards'], queryFn: () => performanceMonitoringService.listDashboards({ page_size: 100, ordering: 'name' }) });
  const configuration = useQuery({ queryKey: ['performance-monitoring', 'configuration', 'catalog-defaults'], queryFn: () => performanceMonitoringService.getConfiguration() });
  const createEnvironment = useMutation({ mutationFn: (payload: MonitoringEnvironmentCreate) => performanceMonitoringService.createEnvironment(payload), onSuccess: () => { setEnvironmentDraft(null); toast.success('Monitoring environment created'); void client.invalidateQueries({ queryKey: ['performance-monitoring', 'environments'] }); }, onError: () => toast.error('Monitoring environment could not be created') });
  const createDashboard = useMutation({ mutationFn: (payload: MonitoringDashboardCreate) => performanceMonitoringService.createDashboard(payload), onSuccess: () => { setDashboardDraft(null); toast.success('Dashboard created'); void client.invalidateQueries({ queryKey: ['performance-monitoring', 'dashboards'] }); }, onError: () => toast.error('Dashboard could not be created') });

  if (environments.isPending || dashboards.isPending || configuration.isPending) return <MonitoringPage title="Monitoring catalog" description="Manage tenant environments and persisted dashboard definitions."><PageSkeleton /></MonitoringPage>;
  const failure = environments.error ?? dashboards.error ?? configuration.error;
  if (failure || !environments.data || !dashboards.data || !configuration.data) return <MonitoringPage title="Monitoring catalog" description="Manage tenant environments and persisted dashboard definitions."><OperationalError error={failure} onRetry={() => { void environments.refetch(); void dashboards.refetch(); void configuration.refetch(); }} /></MonitoringPage>;
  const defaults = configuration.data.document.defaults;

  return <MonitoringPage title="Monitoring catalog" description="Manage tenant environments and dashboards using the same governed API used by automation.">
    <div className="grid gap-6 xl:grid-cols-2">
      <Card><CardHeader className="flex-row items-center justify-between"><div><CardTitle>Environments</CardTitle><p className="mt-1 text-sm text-muted-foreground">Deployment boundaries used to isolate service telemetry.</p></div><Button size="sm" onClick={() => setEnvironmentDraft(blankEnvironment(defaults.environment.kind))}><Plus className="mr-1 h-4 w-4" />Environment</Button></CardHeader><CardContent className="space-y-3">
        {environmentDraft ? <form className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); createEnvironment.mutate(environmentDraft); }}><label className="text-sm font-medium">Name<Input className="mt-1" required value={environmentDraft.name} onChange={(event) => setEnvironmentDraft({ ...environmentDraft, name: event.target.value })} /></label><label className="text-sm font-medium">Slug<Input className="mt-1" required pattern="[a-z0-9-]+" value={environmentDraft.slug} onChange={(event) => setEnvironmentDraft({ ...environmentDraft, slug: event.target.value.toLowerCase() })} /></label><label className="text-sm font-medium">Kind<Input className="mt-1" required value={environmentDraft.kind} onChange={(event) => setEnvironmentDraft({ ...environmentDraft, kind: event.target.value })} /></label><div className="flex items-end gap-2"><Button type="submit" disabled={createEnvironment.isPending}>Save</Button><Button type="button" variant="outline" onClick={() => setEnvironmentDraft(null)}>Cancel</Button></div></form> : null}
        {environments.data.items.length === 0 ? <EmptyTelemetry title="No environments" description="Create an environment before registering monitored services." /> : environments.data.items.map((environment) => <div key={environment.id} className="flex items-center justify-between rounded-lg border p-3"><div className="flex items-center gap-3"><Server className="h-5 w-5 text-primary" /><div><p className="font-medium">{environment.name}</p><p className="text-xs text-muted-foreground">{environment.kind} · {environment.slug}</p></div></div><StatusPill status={environment.is_active ? 'healthy' : 'disabled'} /></div>)}
      </CardContent></Card>
      <Card><CardHeader className="flex-row items-center justify-between"><div><CardTitle>Dashboards</CardTitle><p className="mt-1 text-sm text-muted-foreground">Versioned layouts consumed by monitoring clients.</p></div><Button size="sm" onClick={() => setDashboardDraft(blankDashboard(defaults.dashboard.refresh_interval_seconds))}><Plus className="mr-1 h-4 w-4" />Dashboard</Button></CardHeader><CardContent className="space-y-3">
        {dashboardDraft ? <form className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); createDashboard.mutate(dashboardDraft); }}><label className="text-sm font-medium">Name<Input className="mt-1" required value={dashboardDraft.name} onChange={(event) => setDashboardDraft({ ...dashboardDraft, name: event.target.value })} /></label><label className="text-sm font-medium">Refresh interval (seconds)<Input className="mt-1" type="number" min={1} required value={dashboardDraft.refresh_interval_seconds} onChange={(event) => setDashboardDraft({ ...dashboardDraft, refresh_interval_seconds: Number(event.target.value) })} /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={dashboardDraft.is_default} onChange={(event) => setDashboardDraft({ ...dashboardDraft, is_default: event.target.checked })} />Default dashboard</label><div className="flex items-end gap-2"><Button type="submit" disabled={createDashboard.isPending}>Save</Button><Button type="button" variant="outline" onClick={() => setDashboardDraft(null)}>Cancel</Button></div></form> : null}
        {dashboards.data.items.length === 0 ? <EmptyTelemetry title="No dashboards" description="Create a persisted dashboard definition for this tenant." /> : dashboards.data.items.map((dashboard) => <div key={dashboard.id} className="flex items-center justify-between rounded-lg border p-3"><div className="flex items-center gap-3"><LayoutDashboard className="h-5 w-5 text-primary" /><div><p className="font-medium">{dashboard.name}</p><p className="text-xs text-muted-foreground">Updated {formatTime(dashboard.updated_at)}</p></div></div>{dashboard.is_default ? <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary">Default</span> : null}</div>)}
      </CardContent></Card>
    </div>
  </MonitoringPage>;
}
