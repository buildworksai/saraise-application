/* eslint-disable complexity -- APM state matrix keeps independent trace and service failures visible. */
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, Network } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { performanceMonitoringService } from '../services/performance-monitoring-service';
import type { MonitoredService, Trace } from '../contracts';
import { EmptyTelemetry, MonitoringPage, OperationalError, PageSkeleton, StateBanner, StatusPill, formatNumber, formatTime, isStale } from '../components/MonitoringPage';

export function TraceExplorerPage() {
  const [view, setView] = useState<'services' | 'traces'>('services');
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null);
  const configuration = useQuery({ queryKey: ['performance-monitoring', 'configuration', 'default'], queryFn: () => performanceMonitoringService.getConfiguration() });
  const services = useQuery({ queryKey: ['performance-monitoring', 'services', 'apm'], queryFn: () => performanceMonitoringService.listServices({ page_size: 100, ordering: 'name' }) });
  const traces = useQuery({ queryKey: ['performance-monitoring', 'traces'], queryFn: () => performanceMonitoringService.listTraces({ page_size: 100, ordering: '-started_at' }) });
  const spans = useQuery({ queryKey: ['performance-monitoring', 'spans', selectedTrace?.id], queryFn: () => performanceMonitoringService.listTraceSpans(selectedTrace!.id), enabled: Boolean(selectedTrace) });
  const serviceNames = useMemo(() => new Map(services.data?.items.map((service) => [service.id, service.name])), [services.data]);
  const loading = services.isPending && traces.isPending;
  const allFailed = services.isError && traces.isError;

  return <MonitoringPage title="APM & distributed traces" description="Follow requests across services, inspect spans and see where tenant workloads are degraded." actions={<div className="flex rounded-lg border p-1"><Button size="sm" variant={view === 'services' ? 'primary' : 'ghost'} onClick={() => setView('services')}><Network className="mr-2 h-4 w-4" />Service map</Button><Button size="sm" variant={view === 'traces' ? 'primary' : 'ghost'} onClick={() => setView('traces')}><Activity className="mr-2 h-4 w-4" />Traces</Button></div>}>
    {loading ? <PageSkeleton /> : allFailed ? <OperationalError error={services.error} onRetry={() => { void services.refetch(); void traces.refetch(); }} /> : <>
      {services.isError || traces.isError ? <StateBanner state="degraded">One APM data source is unavailable. The available inventory is shown without inferred dependencies.</StateBanner> : null}
      {view === 'services' ? <ServiceMap services={services.data?.items ?? []} traceCount={traces.data?.pagination.count} staleThresholdMinutes={configuration.data?.document.query.global_stale_threshold_minutes} /> : <TraceList traces={traces.data?.items ?? []} serviceNames={serviceNames} selected={selectedTrace} onSelect={setSelectedTrace} />}
      {selectedTrace ? <Card><CardHeader className="flex-row items-start justify-between space-y-0"><div><CardTitle className="text-lg">Trace details</CardTitle><p className="mt-1 break-all font-mono text-xs text-muted-foreground">{selectedTrace.trace_id}</p></div><Button variant="ghost" onClick={() => setSelectedTrace(null)}>Close</Button></CardHeader><CardContent>{spans.isPending ? <div className="h-40 animate-pulse rounded bg-muted" /> : spans.isError ? <OperationalError error={spans.error} onRetry={() => { void spans.refetch(); }} /> : spans.data.length === 0 ? <p className="py-8 text-center text-sm text-muted-foreground">This trace has no persisted spans.</p> : <div className="space-y-2">{spans.data.map((span) => <div key={span.id} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-[1fr_auto_auto] sm:items-center"><div><p className="font-medium text-foreground">{span.name}</p><p className="text-xs text-muted-foreground">{serviceNames.get(span.service) ?? span.service} · {span.kind}</p></div><StatusPill status={span.status} /><span className="font-mono text-xs text-muted-foreground">{formatNumber(span.duration_ms, { maximumFractionDigits: 2 })} ms</span></div>)}</div>}</CardContent></Card> : null}
    </>}
  </MonitoringPage>;
}

function ServiceMap({ services, traceCount, staleThresholdMinutes }: { services: readonly MonitoredService[]; traceCount?: number; staleThresholdMinutes?: number }) {
  if (services.length === 0) return <EmptyTelemetry title="No APM services discovered" description="Instrument a service and send OTLP traces before a service map can be drawn. Dependencies are never fabricated from configuration alone." />;
  const stale = staleThresholdMinutes !== undefined && services.some((service) => isStale(service.last_seen_at, staleThresholdMinutes));
  return <div className="space-y-4">{stale ? <StateBanner state="stale">One or more services have stopped reporting. Their last verified state remains visible.</StateBanner> : null}<Card><CardHeader><CardTitle className="text-lg">Service inventory <span className="ml-2 text-sm font-normal text-muted-foreground">{traceCount === undefined ? 'Trace count unavailable' : `${traceCount} traces indexed`}</span></CardTitle></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{services.map((service) => <article key={service.id} className="relative overflow-hidden rounded-xl border bg-card p-4 shadow-sm"><div className="absolute inset-y-0 left-0 w-1 bg-primary" /><div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold text-foreground">{service.name}</h2><p className="text-xs text-muted-foreground">{service.namespace} · {service.language || 'runtime unknown'}</p></div><StatusPill status={service.status} /></div><dl className="mt-4 grid grid-cols-2 gap-3 text-xs"><div><dt className="text-muted-foreground">Version</dt><dd className="mt-1 font-medium">{service.version || 'Unavailable'}</dd></div><div><dt className="text-muted-foreground">Last seen</dt><dd className="mt-1 font-medium">{formatTime(service.last_seen_at)}</dd></div></dl></article>)}</CardContent></Card></div>;
}

function TraceList({ traces, serviceNames, selected, onSelect }: { traces: readonly Trace[]; serviceNames: Map<string, string>; selected: Trace | null; onSelect: (trace: Trace) => void }) {
  if (traces.length === 0) return <EmptyTelemetry title="No traces in the selected tenant" description="Trace ingestion has not produced durable evidence yet. Verify the collector and sampling configuration." />;
  return <Card className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[800px] text-left text-sm"><thead className="border-b bg-muted/50 text-xs uppercase text-muted-foreground"><tr><th className="px-4 py-3">Operation</th><th className="px-4 py-3">Service</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Duration</th><th className="px-4 py-3">Spans</th><th className="px-4 py-3">Started</th></tr></thead><tbody>{traces.map((trace) => <tr key={trace.id} onClick={() => onSelect(trace)} className={`cursor-pointer border-b hover:bg-muted/40 ${selected?.id === trace.id ? 'bg-muted' : ''}`}><td className="px-4 py-3 font-medium">{trace.name}</td><td className="px-4 py-3">{serviceNames.get(trace.service) ?? trace.service}</td><td className="px-4 py-3"><StatusPill status={trace.status} /></td><td className="px-4 py-3 font-mono text-xs">{formatNumber(trace.duration_ms, { maximumFractionDigits: 2 })} ms</td><td className="px-4 py-3">{trace.span_count} <span className="text-destructive">({trace.error_span_count} errors)</span></td><td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{formatTime(trace.started_at)}</td></tr>)}</tbody></table></div></Card>;
}
