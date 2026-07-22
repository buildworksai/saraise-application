/* eslint-disable @typescript-eslint/prefer-nullish-coalescing -- truthiness is intentional for form validation. */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Play, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { performanceMonitoringService } from '../services/performance-monitoring-service';
import { ROUTES, type AlertCondition, type AlertRuleCreate, type MonitoringConfigurationDocument, type Severity } from '../contracts';
import { EmptyTelemetry, MonitoringPage, OperationalError, PageSkeleton, StatusPill, formatTime } from '../components/MonitoringPage';

function emptyRule(configuration: MonitoringConfigurationDocument): AlertRuleCreate {
  const defaults = configuration.defaults.alert_rule;
  return { name: '', metric_name: '', condition: configuration.allowlists.alert_conditions[0] as AlertCondition, threshold: defaults.threshold, evaluation_window_minutes: defaults.evaluation_window_minutes, evaluation_interval_seconds: defaults.evaluation_interval_seconds, cooldown_minutes: defaults.cooldown_minutes, severity: defaults.severity, action: { channels: defaults.notification_channels } };
}

export function AlertRulesPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState<AlertRuleCreate | null>(null);
  const configuration = useQuery({ queryKey: ['performance-monitoring', 'configuration', 'default'], queryFn: () => performanceMonitoringService.getConfiguration() });
  const rules = useQuery({ queryKey: ['performance-monitoring', 'alert-rules'], queryFn: () => performanceMonitoringService.listAlertRules({ page_size: 100, ordering: 'name' }) });
  useEffect(() => { if (configuration.data && !draft) setDraft(emptyRule(configuration.data.document)); }, [configuration.data, draft]);
  const create = useMutation({ mutationFn: (payload: AlertRuleCreate) => performanceMonitoringService.createAlertRule(payload), onSuccess: () => { toast.success('Alert rule created'); setShowCreate(false); if (configuration.data) setDraft(emptyRule(configuration.data.document)); void client.invalidateQueries({ queryKey: ['performance-monitoring', 'alert-rules'] }); }, onError: () => toast.error('Alert rule could not be created') });
  const evaluate = useMutation({ mutationFn: (id: string) => performanceMonitoringService.evaluateAlertRule(id), onSuccess: () => { toast.success('Rule evaluated against persisted observations'); void client.invalidateQueries({ queryKey: ['performance-monitoring', 'alerts'] }); }, onError: () => toast.error('Rule evaluation failed') });
  return <MonitoringPage title="Alert rules" description="Define threshold, change and absence policies over real metric streams." actions={<><Button variant="outline" onClick={() => navigate(ROUTES.ALERTS)}><ArrowLeft className="mr-2 h-4 w-4" />Alert center</Button><Button disabled={!draft} onClick={() => setShowCreate((value) => !value)}><Plus className="mr-2 h-4 w-4" />New rule</Button></>}>
    {showCreate && draft && configuration.data ? <RuleForm draft={draft} configuration={configuration.data.document} setDraft={setDraft} pending={create.isPending} onCancel={() => setShowCreate(false)} onSubmit={() => create.mutate(draft)} /> : null}
    {rules.isPending ? <PageSkeleton rows={5} /> : rules.isError ? <OperationalError error={rules.error} onRetry={() => { void rules.refetch(); }} /> : rules.data.items.length === 0 ? <EmptyTelemetry title="No alert rules configured" description="Create a rule against a registered or forward-referenced metric. Evaluation failures remain explicit." action={<Button onClick={() => setShowCreate(true)}>Create first rule</Button>} /> : <div className="grid gap-4 lg:grid-cols-2">{rules.data.items.map((rule) => <Card key={rule.id}><CardContent className="p-5"><div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold text-foreground">{rule.name}</h2><p className="mt-1 font-mono text-xs text-muted-foreground">{rule.metric_name}</p></div><StatusPill status={rule.severity} /></div><p className="mt-3 text-sm text-muted-foreground">{rule.description || `${rule.condition.replaceAll('_', ' ')} ${rule.threshold ?? ''}`}</p><div className="mt-4 flex items-center justify-between text-xs text-muted-foreground"><span>Last evaluated {formatTime(rule.last_evaluated_at)}</span><Button size="sm" variant="outline" disabled={evaluate.isPending || !rule.is_active} onClick={() => evaluate.mutate(rule.id)}><Play className="mr-1 h-3.5 w-3.5" />Evaluate</Button></div></CardContent></Card>)}</div>}
  </MonitoringPage>;
}

function RuleForm({ draft, configuration, setDraft, pending, onCancel, onSubmit }: { draft: AlertRuleCreate; configuration: MonitoringConfigurationDocument; setDraft: (draft: AlertRuleCreate) => void; pending: boolean; onCancel: () => void; onSubmit: () => void }) {
  const valid = Boolean(draft.name.trim() && (draft.metric || draft.metric_name?.trim()) && draft.evaluation_window_minutes <= configuration.limits.evaluation_window_max_minutes && (draft.condition === 'absence' || draft.threshold !== null && draft.threshold !== undefined));
  return <Card><CardHeader><CardTitle className="text-lg">Create alert rule</CardTitle></CardHeader><CardContent><form className="grid gap-4 md:grid-cols-3" onSubmit={(event) => { event.preventDefault(); if (valid) onSubmit(); }}>
    <label className="text-sm font-medium">Name<Input className="mt-1" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
    <label className="text-sm font-medium">Metric name<Input className="mt-1" value={draft.metric_name ?? ''} onChange={(event) => setDraft({ ...draft, metric_name: event.target.value.toLowerCase(), metric: null })} placeholder="api.error.rate" /></label>
    <label className="text-sm font-medium">Condition<select className="mt-1 h-10 w-full rounded-md border bg-background px-3" value={draft.condition} onChange={(event) => { const condition = event.target.value as AlertCondition; setDraft({ ...draft, condition, threshold: condition === 'absence' ? null : draft.threshold ?? configuration.defaults.alert_rule.threshold }); }}>{configuration.allowlists.alert_conditions.map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
    {draft.condition !== 'absence' ? <label className="text-sm font-medium">Threshold<Input className="mt-1" type="number" step="any" value={draft.threshold ?? ''} onChange={(event) => setDraft({ ...draft, threshold: Number(event.target.value) })} /></label> : null}
    <label className="text-sm font-medium">Evaluation window (minutes)<Input className="mt-1" type="number" min={1} max={configuration.limits.evaluation_window_max_minutes} value={draft.evaluation_window_minutes} onChange={(event) => setDraft({ ...draft, evaluation_window_minutes: Number(event.target.value) })} /></label>
    <label className="text-sm font-medium">Severity<select className="mt-1 h-10 w-full rounded-md border bg-background px-3" value={draft.severity} onChange={(event) => setDraft({ ...draft, severity: event.target.value as Severity })}>{configuration.allowlists.severities.map((value) => <option key={value}>{value}</option>)}</select></label>
    <div className="flex gap-2 md:col-span-3"><Button type="submit" disabled={!valid || pending}>{pending ? 'Creating…' : 'Create rule'}</Button><Button type="button" variant="outline" onClick={onCancel}>Cancel</Button></div>
  </form></CardContent></Card>;
}
