/* eslint-disable @typescript-eslint/prefer-nullish-coalescing -- blank display labels intentionally fall back to semantic names. */
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Plus, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { performanceMonitoringService } from '../services/performance-monitoring-service';
import type { MetricCreate, MetricType, TimeRangePreset } from '../contracts';
import { EmptyTelemetry, MonitoringPage, OperationalError, PageSkeleton, StateBanner, formatNumber, formatTime } from '../components/MonitoringPage';

const ranges: Record<TimeRangePreset, number> = { '15m': 15, '1h': 60, '6h': 360, '24h': 1440, '7d': 10080, '30d': 43200 };

export function MetricExplorerPage() {
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState('');
  const [range, setRange] = useState<TimeRangePreset>('1h');
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState<MetricCreate>({ metric_name: '', metric_type: 'gauge', unit: '1' });
  const catalog = useQuery({ queryKey: ['performance-monitoring', 'metrics'], queryFn: () => performanceMonitoringService.listMetrics({ page_size: 100, ordering: 'metric_name' }) });
  useEffect(() => { if (!selectedId && catalog.data?.items[0]) setSelectedId(catalog.data.items[0].id); }, [catalog.data, selectedId]);
  const selected = catalog.data?.items.find((metric) => metric.id === selectedId);
  const window = useMemo(() => ({ start: new Date(Date.now() - ranges[range] * 60_000).toISOString(), end: new Date().toISOString() }), [range]);
  const series = useQuery({
    queryKey: ['performance-monitoring', 'metric-series', selectedId, range],
    queryFn: () => performanceMonitoringService.queryMetric({ metric_name: selected!.metric_name, ...window, aggregation: 'avg', interval: range === '15m' ? '1m' : range === '1h' ? '5m' : '1h' }),
    enabled: Boolean(selectedId),
  });
  const create = useMutation({
    mutationFn: (payload: MetricCreate) => performanceMonitoringService.createMetric(payload),
    onSuccess: (metric) => { toast.success('Metric definition created'); setSelectedId(metric.id); setShowCreate(false); setDraft({ metric_name: '', metric_type: 'gauge', unit: '1' }); void client.invalidateQueries({ queryKey: ['performance-monitoring', 'metrics'] }); },
    onError: () => toast.error('Metric definition could not be created'),
  });

  if (catalog.isPending) return <MonitoringPage title="Metric explorer" description="Query tenant telemetry by metric, interval and time range."><PageSkeleton /></MonitoringPage>;
  if (catalog.isError) return <MonitoringPage title="Metric explorer" description="Query tenant telemetry by metric, interval and time range."><OperationalError error={catalog.error} onRetry={() => { void catalog.refetch(); }} /></MonitoringPage>;

  return (
    <MonitoringPage title="Metric explorer" description="Query tenant telemetry by metric, interval and time range." actions={<Button onClick={() => setShowCreate((value) => !value)}><Plus className="mr-2 h-4 w-4" />Define metric</Button>}>
      {showCreate ? <MetricForm draft={draft} setDraft={setDraft} pending={create.isPending} onCancel={() => setShowCreate(false)} onSubmit={() => create.mutate(draft)} /> : null}
      {catalog.data.items.length === 0 ? <EmptyTelemetry title="No metric definitions" description="Define a real metric, then ingest observations through the governed metric API. Charts remain empty until observations are persisted." action={<Button onClick={() => setShowCreate(true)}>Define first metric</Button>} /> : (
        <div className="grid gap-6 xl:grid-cols-[300px_1fr]">
          <Card className="h-fit"><CardHeader><CardTitle className="text-base">Metric catalog</CardTitle></CardHeader><CardContent className="max-h-[640px] space-y-1 overflow-y-auto">
            {catalog.data.items.map((metric) => <button key={metric.id} type="button" onClick={() => setSelectedId(metric.id)} className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${selectedId === metric.id ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}><span className="block truncate text-sm font-medium">{metric.display_name || metric.metric_name}</span><span className={`block truncate text-xs ${selectedId === metric.id ? 'text-primary-foreground/70' : 'text-muted-foreground'}`}>{metric.metric_name} · {metric.unit}</span></button>)}
          </CardContent></Card>
          <div className="space-y-4">
            <Card><CardHeader className="gap-4 sm:flex-row sm:items-start sm:justify-between"><div><CardTitle className="text-lg">{selected?.display_name || selected?.metric_name}</CardTitle><p className="mt-1 text-sm text-muted-foreground">{selected?.description || 'No description provided.'}</p></div><div className="flex flex-wrap gap-1" aria-label="Time range">{(['15m', '1h', '6h', '24h', '7d'] as const).map((item) => <Button key={item} size="sm" variant={range === item ? 'primary' : 'outline'} onClick={() => setRange(item)}>{item}</Button>)}<Button size="icon" variant="outline" aria-label="Refresh metric" onClick={() => { void series.refetch(); }}><RefreshCw className="h-4 w-4" /></Button></div></CardHeader><CardContent>
              {series.isPending ? <div className="h-80 animate-pulse rounded-lg bg-muted" role="status"><span className="sr-only">Loading metric observations</span></div> : series.isError ? <OperationalError error={series.error} onRetry={() => { void series.refetch(); }} /> : series.data.data.length === 0 ? <EmptyTelemetry title="No observations in this range" description="The metric exists, but no persisted data points match the selected time window and tags." /> : <>
                {new Date(series.data.data[series.data.data.length - 1]!.timestamp).getTime() < Date.now() - (selected?.expected_interval_seconds ?? 60) * 2 * 1000 ? <div className="mb-4"><StateBanner state="stale">The latest observation is older than twice the metric's expected cadence.</StateBanner></div> : null}
                <div className="h-80" role="img" aria-label={`Time series for ${selected?.metric_name ?? 'selected metric'}`}><ResponsiveContainer width="100%" height="100%"><LineChart data={series.data.data}><XAxis dataKey="timestamp" tickFormatter={(value: string) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} minTickGap={35} /><YAxis width={55} /><Tooltip labelFormatter={(value) => formatTime(String(value))} formatter={(value) => [formatNumber(Number(value), { maximumFractionDigits: 3 }), selected?.unit ?? '']} /><Line type="monotone" dataKey="value" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} activeDot={{ r: 4 }} /></LineChart></ResponsiveContainer></div>
                <MetricStatistics values={series.data.data.map((point) => point.value)} unit={selected?.unit ?? ''} />
              </>}
            </CardContent></Card>
          </div>
        </div>
      )}
    </MonitoringPage>
  );
}

function MetricStatistics({ values, unit }: { values: readonly number[]; unit: string }) {
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const average = values.reduce((total, value) => total + value, 0) / values.length;
  const latest = values[values.length - 1];
  return <dl className="mt-4 grid gap-3 sm:grid-cols-4">{[['Latest', latest], ['Average', average], ['Minimum', minimum], ['Maximum', maximum]].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-muted/60 p-3"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold text-foreground">{formatNumber(value as number, { maximumFractionDigits: 3 })} {unit}</dd></div>)}</dl>;
}

function MetricForm({ draft, setDraft, pending, onCancel, onSubmit }: { draft: MetricCreate; setDraft: (value: MetricCreate) => void; pending: boolean; onCancel: () => void; onSubmit: () => void }) {
  const valid = /^[a-z][a-z0-9_.-]*$/.test(draft.metric_name) && draft.unit.trim().length > 0;
  return <Card><CardHeader><CardTitle className="text-lg">Define a metric</CardTitle></CardHeader><CardContent><form className="grid gap-4 md:grid-cols-4" onSubmit={(event) => { event.preventDefault(); if (valid) onSubmit(); }}><label className="text-sm font-medium md:col-span-2">Metric name<Input className="mt-1" value={draft.metric_name} onChange={(event) => setDraft({ ...draft, metric_name: event.target.value.toLowerCase() })} placeholder="checkout.request.duration" aria-describedby="metric-name-help" /><span id="metric-name-help" className="mt-1 block text-xs font-normal text-muted-foreground">Lowercase semantic name; spaces are not allowed.</span></label><label className="text-sm font-medium">Type<select className="mt-1 h-10 w-full rounded-md border bg-background px-3" value={draft.metric_type} onChange={(event) => setDraft({ ...draft, metric_type: event.target.value as MetricType })}>{['gauge', 'counter', 'histogram', 'summary'].map((type) => <option key={type}>{type}</option>)}</select></label><label className="text-sm font-medium">Unit<Input className="mt-1" value={draft.unit} onChange={(event) => setDraft({ ...draft, unit: event.target.value })} placeholder="ms" /></label><div className="flex gap-2 md:col-span-4"><Button type="submit" disabled={!valid || pending}>{pending ? 'Creating…' : 'Create metric'}</Button><Button type="button" variant="outline" onClick={onCancel}>Cancel</Button></div></form></CardContent></Card>;
}
