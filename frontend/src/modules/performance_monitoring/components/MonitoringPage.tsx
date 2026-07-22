/* eslint-disable react-refresh/only-export-components -- shared state helpers intentionally accompany the module shell. */
import { createContext, useContext, useEffect, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { NavLink } from 'react-router-dom';
import {
  Activity,
  BellRing,
  Gauge,
  Network,
  ScrollText,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';
import { ApiError } from '@/services/api-client';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui';
import { cn } from '@/lib/utils';
import { PerformanceMonitoringApiError, performanceMonitoringService } from '../services/performance-monitoring-service';
import { ROUTES, type HealthState, type MonitoringConfigurationDocument, type Severity } from '../contracts';

const ConfigurationContext = createContext<MonitoringConfigurationDocument | null>(null);

const semanticTokenClasses: Readonly<Record<string, string>> = {
  'status-success': 'bg-primary/10 text-primary',
  'status-warning': 'bg-muted text-foreground',
  'status-danger': 'bg-destructive/10 text-destructive',
  'status-stale': 'border-border bg-muted text-foreground',
  'status-degraded': 'border-destructive/30 bg-destructive/10 text-destructive',
  'log-trace': 'text-muted-foreground',
  'log-debug': 'text-secondary-foreground',
  'log-info': 'text-primary',
  'log-warning': 'text-foreground',
  'log-error': 'text-destructive',
};

function semanticClass(token: string): string {
  return semanticTokenClasses[token] ?? 'bg-muted text-muted-foreground';
}

const sections = [
  { to: ROUTES.OVERVIEW, label: 'Overview', icon: Gauge },
  { to: ROUTES.METRICS, label: 'Metrics', icon: Activity },
  { to: ROUTES.LOGS, label: 'Logs', icon: ScrollText },
  { to: ROUTES.TRACES, label: 'APM & traces', icon: Network },
  { to: ROUTES.ALERTS, label: 'Alerts', icon: BellRing },
  { to: ROUTES.ALERT_RULES, label: 'Alert rules', icon: SlidersHorizontal },
  { to: ROUTES.SLOS, label: 'SLO & SLA', icon: ShieldCheck },
  { to: ROUTES.CATALOG, label: 'Catalog', icon: Network },
  { to: ROUTES.CONFIGURATION, label: 'Configuration', icon: Settings2 },
  { to: ROUTES.SETUP, label: 'Setup', icon: Settings2 },
] as const;

export function MonitoringPage({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const configuration = useQuery({ queryKey: ['performance-monitoring', 'configuration', 'default'], queryFn: () => performanceMonitoringService.getConfiguration() });
  useEffect(() => {
    document.title = `${title} | SARAISE`;
  }, [title]);

  if (configuration.isPending) return <main className="min-h-full p-4 sm:p-8"><PageSkeleton /></main>;
  if (configuration.isError || !configuration.data) return <main className="min-h-full p-4 sm:p-8"><Card className="border-destructive/30"><CardContent className="p-6" role="alert"><h1 className="font-semibold">Monitoring configuration unavailable</h1><p className="mt-2 text-sm text-muted-foreground">Required tenant configuration could not be loaded. Monitoring behavior is disabled rather than using ungoverned defaults.</p><Button className="mt-4" variant="outline" onClick={() => { void configuration.refetch(); }}>Retry</Button></CardContent></Card></main>;
  return (
    <ConfigurationContext.Provider value={configuration.data.document}>
    <main className="min-h-full bg-gradient-to-b from-background to-muted/30 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-[1500px] space-y-6">
        <header className="space-y-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-primary">Observability</p>
              <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{title}</h1>
              <p className="mt-2 max-w-3xl text-sm text-muted-foreground sm:text-base">{description}</p>
            </div>
            {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
          </div>
          <nav aria-label="Performance monitoring sections" className="overflow-x-auto pb-1">
            <div className="flex min-w-max gap-1 rounded-xl border bg-card/80 p-1 shadow-sm backdrop-blur">
              {sections.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end
                  className={({ isActive }) => cn(
                    'inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    isActive ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {label}
                </NavLink>
              ))}
            </div>
          </nav>
        </header>
        {children}
      </div>
    </main>
    </ConfigurationContext.Provider>
  );
}

export function useMonitoringConfiguration(): MonitoringConfigurationDocument {
  const configuration = useContext(ConfigurationContext);
  if (!configuration) throw new Error('Monitoring configuration context is unavailable.');
  return configuration;
}

export function PageSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading monitoring data" className="space-y-4">
      <span className="sr-only">Loading monitoring data</span>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Card key={index}><CardContent className="space-y-3 p-5"><Skeleton className="h-4 w-24" /><Skeleton className="h-8 w-20" /><Skeleton className="h-3 w-32" /></CardContent></Card>
        ))}
      </div>
      <Card><CardContent className="space-y-3 p-5">{Array.from({ length: rows }).map((_, index) => <Skeleton key={index} className="h-12 w-full" />)}</CardContent></Card>
    </div>
  );
}

export function OperationalError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const status = error instanceof PerformanceMonitoringApiError || error instanceof ApiError ? error.status : undefined;
  let title = 'Monitoring data is unavailable';
  let message = 'The monitoring service could not be reached. Check your connection and try again.';
  if (status === 404) {
    title = 'Monitoring resource not found';
    message = 'It may have been removed, or it may belong to another tenant.';
  } else if (status === 401) {
    title = 'Your session has expired';
    message = 'Sign in again to continue viewing operational telemetry.';
  } else if (status === 403) {
    title = 'Permission required';
    message = 'You do not have permission to view this monitoring data.';
  } else if (status === 503) {
    title = 'Telemetry pipeline unavailable';
    message = 'The service reported an explicit dependency failure. Existing evidence has not been replaced with estimated data.';
  }
  return (
    <Card className="border-destructive/30">
      <CardContent className="flex flex-col items-start gap-4 p-6" role="alert">
        <div><h2 className="font-semibold text-foreground">{title}</h2><p className="mt-1 text-sm text-muted-foreground">{message}</p></div>
        <Button variant="outline" onClick={onRetry}>Retry</Button>
      </CardContent>
    </Card>
  );
}

export function StateBanner({ state, children }: { state: 'stale' | 'degraded'; children: ReactNode }) {
  const configuration = useMonitoringConfiguration();
  const token = configuration.visual.status_tokens[state];
  return (
    <div role="status" className={cn('rounded-xl border px-4 py-3 text-sm', semanticClass(token))}>
      <strong>{state === 'stale' ? 'Telemetry is stale. ' : 'Partial data. '}</strong>{children}
    </div>
  );
}

export function StatusPill({ status }: { status: HealthState | Severity | 'firing' | 'acknowledged' | 'resolved' | 'ok' | 'error' | 'unset' | 'compliant' | 'breached' | 'insufficient_data' }) {
  const configuration = useMonitoringConfiguration();
  const token = ['healthy', 'ok', 'compliant', 'resolved'].includes(status)
    ? configuration.visual.status_tokens.success
    : ['critical', 'firing', 'error', 'breached'].includes(status)
      ? configuration.visual.status_tokens.danger
      : status === 'stale'
        ? configuration.visual.status_tokens.stale
        : ['warning', 'degraded', 'acknowledged', 'insufficient_data'].includes(status)
          ? configuration.visual.status_tokens.warning
          : configuration.visual.status_tokens.degraded;
  return <span className={cn('inline-flex rounded-full px-2 py-0.5 text-xs font-semibold capitalize', semanticClass(token))}>{status.replaceAll('_', ' ')}</span>;
}

export function useLogLevelClass(level: 'trace' | 'debug' | 'info' | 'warn' | 'error' | 'fatal'): string {
  const configuration = useMonitoringConfiguration();
  const configured = level === 'warn' ? configuration.visual.log_level_tokens.warning : level === 'fatal' ? configuration.visual.log_level_tokens.error : configuration.visual.log_level_tokens[level];
  return cn(semanticClass(configured), level === 'fatal' && 'font-bold');
}

export function EmptyTelemetry({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <Card className="border-dashed"><CardContent className="flex min-h-56 flex-col items-center justify-center p-8 text-center"><Activity className="mb-4 h-10 w-10 text-muted-foreground" aria-hidden="true" /><h2 className="font-semibold text-foreground">{title}</h2><p className="mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>{action ? <div className="mt-5">{action}</div> : null}</CardContent></Card>
  );
}

export function formatNumber(value: number | null | undefined, options?: Intl.NumberFormatOptions): string {
  return value === null || value === undefined ? 'Unavailable' : new Intl.NumberFormat(undefined, options).format(value);
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return 'Never';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString();
}

export function isStale(value: string | null | undefined, thresholdMinutes: number): boolean {
  if (!value) return true;
  const instant = new Date(value).getTime();
  return Number.isNaN(instant) || Date.now() - instant > thresholdMinutes * 60_000;
}
