/* eslint-disable @typescript-eslint/prefer-nullish-coalescing -- empty filters intentionally use truthiness. */
import { useDeferredValue, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { performanceMonitoringService } from '../services/performance-monitoring-service';
import type { LogEntry } from '../contracts';
import { EmptyTelemetry, MonitoringPage, OperationalError, PageSkeleton, formatTime } from '../components/MonitoringPage';

export function LogExplorerPage() {
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [level, setLevel] = useState<LogEntry['level'] | ''>('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const logs = useQuery({ queryKey: ['performance-monitoring', 'logs', deferredSearch, level], queryFn: () => performanceMonitoringService.listLogs({ page_size: 100, ordering: '-timestamp', search: deferredSearch || undefined, level: level || undefined }) });

  return (
    <MonitoringPage title="Log explorer" description="Search structured tenant logs and pivot into correlated traces without exposing credentials or cross-tenant evidence.">
      <Card><CardContent className="p-4"><div className="flex flex-col gap-3 sm:flex-row"><label className="relative flex-1"><span className="sr-only">Search log messages</span><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" /><Input className="pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search messages, correlation IDs or attributes" /></label><label><span className="sr-only">Filter by log level</span><select className="h-10 min-w-40 rounded-md border bg-background px-3 text-sm" value={level} onChange={(event) => setLevel(event.target.value as LogEntry['level'] | '')}><option value="">All levels</option>{['trace', 'debug', 'info', 'warn', 'error', 'fatal'].map((item) => <option value={item} key={item}>{item}</option>)}</select></label></div></CardContent></Card>
      {logs.isPending ? <PageSkeleton rows={7} /> : logs.isError ? <OperationalError error={logs.error} onRetry={() => { void logs.refetch(); }} /> : logs.data.items.length === 0 ? <EmptyTelemetry title="No matching log events" description={search || level ? 'No persisted logs match these filters. Clear a filter or widen the time range.' : 'No logs have been ingested for this tenant.'} action={search || level ? <Button variant="outline" onClick={() => { setSearch(''); setLevel(''); }}>Clear filters</Button> : undefined} /> : <Card className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left text-sm"><thead className="border-b bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">Time</th><th className="px-4 py-3">Level</th><th className="px-4 py-3">Message</th><th className="px-4 py-3">Trace</th><th className="px-4 py-3"><span className="sr-only">Details</span></th></tr></thead><tbody>{logs.data.items.map((entry) => <LogRow key={entry.id} entry={entry} expanded={expanded === entry.id} onToggle={() => setExpanded(expanded === entry.id ? null : entry.id)} />)}</tbody></table></div></Card>}
    </MonitoringPage>
  );
}

function LogRow({ entry, expanded, onToggle }: { entry: LogEntry; expanded: boolean; onToggle: () => void }) {
  const levelTone: Record<LogEntry['level'], string> = { trace: 'text-slate-500', debug: 'text-indigo-600', info: 'text-sky-700', warn: 'text-amber-700', error: 'text-red-700', fatal: 'font-bold text-red-800' };
  return <><tr className="border-b align-top hover:bg-muted/30"><td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{formatTime(entry.timestamp)}</td><td className={`px-4 py-3 font-mono text-xs uppercase ${levelTone[entry.level]}`}>{entry.level}</td><td className="max-w-xl px-4 py-3"><p className="break-words text-foreground">{entry.message}</p>{entry.correlation_id ? <p className="mt-1 font-mono text-xs text-muted-foreground">correlation: {entry.correlation_id}</p> : null}</td><td className="max-w-40 truncate px-4 py-3 font-mono text-xs text-muted-foreground">{entry.trace_id || '—'}</td><td className="px-4 py-2"><Button size="sm" variant="ghost" onClick={onToggle} aria-expanded={expanded}>Attributes</Button></td></tr>{expanded ? <tr className="border-b bg-muted/20"><td colSpan={5} className="px-4 py-3"><pre className="max-h-52 overflow-auto rounded-lg bg-slate-950 p-4 text-xs text-slate-100">{JSON.stringify(entry.attributes, null, 2)}</pre></td></tr> : null}</>;
}
