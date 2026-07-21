import { lazy } from 'react';
import { Activity, BellRing, Gauge, Network, ScrollText, Settings2, ShieldCheck } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';
import { ROUTES } from './contracts';

const moduleName = 'performance_monitoring';
const contextual = (parentRouteId: string) => ({ type: 'contextual' as const, parentRouteId });

export const tenantRoutes = [
  { id: 'performance-monitoring.index', module: moduleName, path: '/performance-monitoring', sourceFile: 'modules/performance_monitoring/pages/PerformanceMonitoringIndexPage.tsx', Page: lazy(() => import('./pages/PerformanceMonitoringIndexPage').then(({ PerformanceMonitoringIndexPage }) => ({ default: PerformanceMonitoringIndexPage }))), navigation: contextual('performance-monitoring.dashboard') },
  { id: 'performance-monitoring.dashboard', module: moduleName, path: ROUTES.OVERVIEW, sourceFile: 'modules/performance_monitoring/pages/MetricsDashboardPage.tsx', Page: lazy(() => import('./pages/MetricsDashboardPage').then(({ MetricsDashboardPage }) => ({ default: MetricsDashboardPage }))), navigation: { type: 'sidebar', label: 'Overview', icon: Gauge, order: 600 } },
  { id: 'performance-monitoring.metrics', module: moduleName, path: ROUTES.METRICS, sourceFile: 'modules/performance_monitoring/pages/MetricExplorerPage.tsx', Page: lazy(() => import('./pages/MetricExplorerPage').then(({ MetricExplorerPage }) => ({ default: MetricExplorerPage }))), navigation: { type: 'sidebar', label: 'Metrics', icon: Activity, order: 610 } },
  { id: 'performance-monitoring.logs', module: moduleName, path: ROUTES.LOGS, sourceFile: 'modules/performance_monitoring/pages/LogExplorerPage.tsx', Page: lazy(() => import('./pages/LogExplorerPage').then(({ LogExplorerPage }) => ({ default: LogExplorerPage }))), navigation: { type: 'sidebar', label: 'Logs', icon: ScrollText, order: 620 } },
  { id: 'performance-monitoring.traces', module: moduleName, path: ROUTES.TRACES, sourceFile: 'modules/performance_monitoring/pages/TraceExplorerPage.tsx', Page: lazy(() => import('./pages/TraceExplorerPage').then(({ TraceExplorerPage }) => ({ default: TraceExplorerPage }))), navigation: { type: 'sidebar', label: 'APM & traces', icon: Network, order: 630 } },
  { id: 'performance-monitoring.alerts', module: moduleName, path: ROUTES.ALERTS, sourceFile: 'modules/performance_monitoring/pages/ActiveAlertsPage.tsx', Page: lazy(() => import('./pages/ActiveAlertsPage').then(({ ActiveAlertsPage }) => ({ default: ActiveAlertsPage }))), navigation: { type: 'sidebar', label: 'Active alerts', icon: BellRing, order: 640 } },
  { id: 'performance-monitoring.alert-rules', module: moduleName, path: ROUTES.ALERT_RULES, sourceFile: 'modules/performance_monitoring/pages/AlertRulesPage.tsx', Page: lazy(() => import('./pages/AlertRulesPage').then(({ AlertRulesPage }) => ({ default: AlertRulesPage }))), navigation: contextual('performance-monitoring.alerts') },
  { id: 'performance-monitoring.sla', module: moduleName, path: ROUTES.SLOS, sourceFile: 'modules/performance_monitoring/pages/SLAManagementPage.tsx', Page: lazy(() => import('./pages/SLAManagementPage').then(({ SLAManagementPage }) => ({ default: SLAManagementPage }))), navigation: { type: 'sidebar', label: 'SLO & SLA', icon: ShieldCheck, order: 650 } },
  { id: 'performance-monitoring.setup', module: moduleName, path: ROUTES.SETUP, sourceFile: 'modules/performance_monitoring/pages/InstrumentationSetupPage.tsx', Page: lazy(() => import('./pages/InstrumentationSetupPage').then(({ InstrumentationSetupPage }) => ({ default: InstrumentationSetupPage }))), navigation: { type: 'sidebar', label: 'Instrumentation', icon: Settings2, order: 660 } },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
