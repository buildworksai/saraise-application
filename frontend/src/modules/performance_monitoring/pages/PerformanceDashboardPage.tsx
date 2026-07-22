/* eslint-disable complexity -- state matrix explicitly distinguishes loading, total failure, partial failure, stale and empty telemetry. */
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Activity, AlertTriangle, ArrowRight, RadioTower, Server } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { performanceMonitoringService } from '../services/performance-monitoring-service';
import { ROUTES } from '../contracts';
import {
  EmptyTelemetry,
  MonitoringPage,
  OperationalError,
  PageSkeleton,
  StateBanner,
  StatusPill,
  formatNumber,
  formatTime,
  isStale,
} from '../components/MonitoringPage';

const queryOptions = { page_size: 100, ordering: '-updated_at' } as const;

export function PerformanceDashboardPage() {
  const navigate = useNavigate();
  const configuration = useQuery({ queryKey: ['performance-monitoring', 'configuration', 'default'], queryFn: () => performanceMonitoringService.getConfiguration() });
  const sources = useQuery({ queryKey: ['performance-monitoring', 'sources', 'overview'], queryFn: () => performanceMonitoringService.listTelemetrySources(queryOptions) });
  const services = useQuery({ queryKey: ['performance-monitoring', 'services', 'overview'], queryFn: () => performanceMonitoringService.listServices(queryOptions) });
  const metrics = useQuery({ queryKey: ['performance-monitoring', 'metrics', 'overview'], queryFn: () => performanceMonitoringService.listMetrics(queryOptions) });
  const alerts = useQuery({ queryKey: ['performance-monitoring', 'alerts', 'overview'], queryFn: () => performanceMonitoringService.listAlerts({ ...queryOptions, status: 'firing' }) });
  const slas = useQuery({ queryKey: ['performance-monitoring', 'sla', 'overview'], queryFn: () => performanceMonitoringService.listSLAs(queryOptions) });
  const queries = [configuration, sources, services, metrics, alerts, slas];
  const retry = () => { queries.forEach((query) => { void query.refetch(); }); };

  if (queries.every((query) => query.isPending)) {
    return <MonitoringPage title="Performance overview" description="Live service health, telemetry freshness, incidents and objectives in one tenant-safe view."><PageSkeleton /></MonitoringPage>;
  }
  const errors = queries.filter((query) => query.isError);
  if (errors.length === queries.length) {
    return <MonitoringPage title="Performance overview" description="Live service health, telemetry freshness, incidents and objectives in one tenant-safe view."><OperationalError error={errors[0]?.error} onRetry={retry} /></MonitoringPage>;
  }

  const sourceItems = sources.data?.items ?? [];
  const serviceItems = services.data?.items ?? [];
  const metricItems = metrics.data?.items ?? [];
  const alertItems = alerts.data?.items ?? [];
  const hasTelemetry = sourceItems.length > 0 || metricItems.length > 0 || serviceItems.length > 0;
  const telemetryStale = sourceItems.length > 0 && configuration.data !== undefined && sourceItems.every((source) => isStale(source.last_seen_at, configuration.data.document.query.global_stale_threshold_minutes));
  const healthyServices = services.data ? serviceItems.filter((service) => service.status === 'healthy').length : null;
  const criticalAlerts = alerts.data ? alertItems.filter((alert) => alert.severity === 'critical').length : null;

  return (
    <MonitoringPage
      title="Performance overview"
      description="Live service health, telemetry freshness, incidents and objectives in one tenant-safe view."
      actions={<Button onClick={() => navigate(ROUTES.SETUP)}><RadioTower className="mr-2 h-4 w-4" />Connect telemetry</Button>}
    >
      {errors.length > 0 ? <StateBanner state="degraded">{errors.length} data source{errors.length === 1 ? ' is' : 's are'} unavailable. Available evidence is shown without estimates.</StateBanner> : null}
      {telemetryStale ? <StateBanner state="stale">No connected source has reported within the configured {configuration.data?.document.query.global_stale_threshold_minutes} minute freshness window. Investigate collectors before relying on this view.</StateBanner> : null}
      {!hasTelemetry && errors.length === 0 ? (
        <EmptyTelemetry
          title="No telemetry received yet"
          description="Connect an OpenTelemetry collector or application source. This dashboard will populate only after verified telemetry arrives."
          action={<Button onClick={() => navigate(ROUTES.SETUP)}>Open instrumentation setup</Button>}
        />
      ) : (
        <>
          <section aria-label="Operational summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard icon={Server} label="Services healthy" value={healthyServices === null ? 'Unavailable' : `${healthyServices} / ${serviceItems.length}`} helper={services.data ? `${serviceItems.filter((service) => service.status === 'degraded').length} degraded` : 'Service inventory unavailable'} />
            <SummaryCard icon={Activity} label="Metric streams" value={metrics.data ? formatNumber(metrics.data.pagination.count) : 'Unavailable'} helper={metrics.data ? 'Verified metric definitions' : 'Metric catalog unavailable'} />
            <SummaryCard icon={AlertTriangle} label="Critical incidents" value={formatNumber(criticalAlerts)} helper={alerts.data ? `${alerts.data.pagination.count} firing alert${alerts.data.pagination.count === 1 ? '' : 's'}` : 'Alert state unavailable'} intent={criticalAlerts ? 'danger' : 'default'} />
            <SummaryCard icon={RadioTower} label="SLA definitions" value={slas.data ? formatNumber(slas.data.pagination.count) : 'Unavailable'} helper="Use the SLA workspace for measured compliance" />
          </section>

          <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0"><CardTitle className="text-lg">Service health</CardTitle><Button variant="ghost" size="sm" onClick={() => navigate(ROUTES.TRACES)}>Explore APM <ArrowRight className="ml-1 h-4 w-4" /></Button></CardHeader>
              <CardContent className="space-y-2">
                {serviceItems.length === 0 ? <p className="py-8 text-center text-sm text-muted-foreground">No monitored services are registered.</p> : serviceItems.slice(0, configuration.data?.document.defaults.dashboard.service_list_limit).map((service) => (
                  <div key={service.id} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-[1fr_auto_auto] sm:items-center">
                    <div><p className="font-medium text-foreground">{service.name}</p><p className="text-xs text-muted-foreground">Last seen {formatTime(service.last_seen_at)}</p></div>
                    <StatusPill status={service.status} />
                    <div className="text-left text-xs text-muted-foreground sm:text-right"><p>{service.namespace}</p><p>{service.version || 'Version unavailable'}</p></div>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0"><CardTitle className="text-lg">Active incidents</CardTitle><Button variant="ghost" size="sm" onClick={() => navigate(ROUTES.ALERTS)}>Open alert center <ArrowRight className="ml-1 h-4 w-4" /></Button></CardHeader>
              <CardContent className="space-y-3">
                {alertItems.length === 0 ? <p className="py-8 text-center text-sm text-muted-foreground">No firing alerts in available data.</p> : alertItems.slice(0, configuration.data?.document.defaults.dashboard.alert_list_limit).map((alert) => (
                  <div key={alert.id} className="rounded-lg border p-3"><div className="flex items-start justify-between gap-3"><p className="font-medium text-foreground">{alert.title}</p><StatusPill status={alert.severity} /></div><p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{alert.description}</p><p className="mt-2 text-xs text-muted-foreground">Started {formatTime(alert.triggered_at)}</p></div>
                ))}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </MonitoringPage>
  );
}

/** Compatibility export for the canonical API specification. */
export const MetricsDashboardPage = PerformanceDashboardPage;

function SummaryCard({ icon: Icon, label, value, helper, intent = 'default' }: { icon: typeof Activity; label: string; value: string; helper: string; intent?: 'default' | 'danger' }) {
  return <Card><CardContent className="p-5"><div className="flex items-center justify-between"><p className="text-sm font-medium text-muted-foreground">{label}</p><Icon className={intent === 'danger' ? 'h-5 w-5 text-destructive' : 'h-5 w-5 text-primary'} /></div><p className="mt-3 text-2xl font-semibold text-foreground">{value}</p><p className="mt-1 text-xs text-muted-foreground">{helper}</p></CardContent></Card>;
}
