import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Check, CheckCircle2, Settings2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { performanceMonitoringService } from '../services/performance-monitoring-service';
import { ROUTES, type Alert } from '../contracts';
import { EmptyTelemetry, MonitoringPage, OperationalError, PageSkeleton, StatusPill, formatNumber, formatTime } from '../components/MonitoringPage';

export function ActiveAlertsPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [status, setStatus] = useState<Alert['status'] | ''>('');
  const alerts = useQuery({ queryKey: ['performance-monitoring', 'alerts', status], queryFn: () => performanceMonitoringService.listAlerts({ page_size: 100, ordering: '-triggered_at', status: status || undefined }) });
  const transition = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'acknowledge' | 'resolve' }) => action === 'acknowledge' ? performanceMonitoringService.acknowledgeAlert(id, { note: 'Acknowledged from alert center' }) : performanceMonitoringService.resolveAlert(id, { note: 'Resolved from alert center' }),
    onSuccess: (_, variables) => { toast.success(variables.action === 'acknowledge' ? 'Alert acknowledged' : 'Alert resolved'); void client.invalidateQueries({ queryKey: ['performance-monitoring', 'alerts'] }); },
    onError: () => toast.error('Alert state could not be updated'),
  });
  return <MonitoringPage title="Alert center" description="Triage firing incidents, acknowledge ownership and preserve resolution evidence." actions={<><select aria-label="Filter alert status" className="h-10 rounded-md border bg-background px-3 text-sm" value={status} onChange={(event) => setStatus(event.target.value as Alert['status'] | '')}><option value="">All states</option><option value="firing">Firing</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option></select><Button variant="outline" onClick={() => navigate(ROUTES.ALERT_RULES)}><Settings2 className="mr-2 h-4 w-4" />Alert rules</Button></>}>
    {alerts.isPending ? <PageSkeleton rows={6} /> : alerts.isError ? <OperationalError error={alerts.error} onRetry={() => { void alerts.refetch(); }} /> : alerts.data.items.length === 0 ? <EmptyTelemetry title={status ? `No ${status} alerts` : 'No alerts recorded'} description={status ? 'There are no persisted alerts in this state.' : 'Alert evaluations have not created any incidents. Configure rules to begin evaluating verified metrics.'} action={<Button variant="outline" onClick={() => navigate(ROUTES.ALERT_RULES)}>Manage alert rules</Button>} /> : <div className="space-y-3">{alerts.data.items.map((alert) => <Card key={alert.id} className={alert.severity === 'critical' && alert.status !== 'resolved' ? 'border-destructive/30' : ''}><CardContent className="p-5"><div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold text-foreground">{alert.title}</h2><StatusPill status={alert.severity} /><StatusPill status={alert.status} /></div><p className="mt-2 text-sm text-muted-foreground">{alert.description || 'No incident description was supplied.'}</p><div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground"><span>Metric <strong className="font-mono text-foreground">{alert.metric_name}</strong></span><span>Observed <strong className="text-foreground">{formatNumber(alert.triggered_value, { maximumFractionDigits: 3 })}</strong></span><span>Threshold <strong className="text-foreground">{formatNumber(alert.threshold, { maximumFractionDigits: 3 })}</strong></span><span>First triggered {formatTime(alert.triggered_at)}</span><span>{alert.occurrence_count} occurrence{alert.occurrence_count === 1 ? '' : 's'}</span></div></div>{alert.status !== 'resolved' ? <div className="flex shrink-0 gap-2">{alert.status === 'firing' ? <Button size="sm" variant="outline" disabled={transition.isPending} onClick={() => transition.mutate({ id: alert.id, action: 'acknowledge' })}><Check className="mr-1 h-4 w-4" />Acknowledge</Button> : null}<Button size="sm" disabled={transition.isPending} onClick={() => transition.mutate({ id: alert.id, action: 'resolve' })}><CheckCircle2 className="mr-1 h-4 w-4" />Resolve</Button></div> : null}</div></CardContent></Card>)}</div>}
  </MonitoringPage>;
}

export const AlertManagementPage = ActiveAlertsPage;
