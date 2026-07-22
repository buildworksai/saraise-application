import { lazy } from 'react';
import { Activity, Download, GitBranch, Gauge, Route, Settings, ShieldCheck } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';

const routeDefinitions = [
  { id: 'process-mining.configuration', module: 'process_mining', path: '/process-mining/configuration', title: 'Configuration · Process Mining · SARAISE', sourceFile: 'modules/process_mining/pages/ConfigurationPage.tsx', Page: lazy(() => import('./pages/ConfigurationPage').then(({ ConfigurationPage }) => ({ default: ConfigurationPage }))), navigation: { type: 'sidebar', label: 'Configuration', icon: Settings, order: 460 } },
  { id: 'process-mining.processes.list', module: 'process_mining', path: '/process-mining/processes', sourceFile: 'modules/process_mining/pages/ProcessOverviewPage.tsx', Page: lazy(() => import('./pages/ProcessOverviewPage').then(({ ProcessOverviewPage }) => ({ default: ProcessOverviewPage }))), navigation: { type: 'sidebar', label: 'Processes', icon: Route, order: 400 } },
  { id: 'process-mining.processes.detail', module: 'process_mining', path: '/process-mining/processes/:processName', sourceFile: 'modules/process_mining/pages/ProcessDetailPage.tsx', Page: lazy(() => import('./pages/ProcessDetailPage').then(({ ProcessDetailPage }) => ({ default: ProcessDetailPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.processes.list' } },
  { id: 'process-mining.models.create', module: 'process_mining', path: '/process-mining/models/new', sourceFile: 'modules/process_mining/pages/CreateProcessModelPage.tsx', Page: lazy(() => import('./pages/CreateProcessModelPage').then(({ CreateProcessModelPage }) => ({ default: CreateProcessModelPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.processes.list' } },
  { id: 'process-mining.models.edit', module: 'process_mining', path: '/process-mining/models/:id/edit', sourceFile: 'modules/process_mining/pages/EditProcessModelPage.tsx', Page: lazy(() => import('./pages/EditProcessModelPage').then(({ EditProcessModelPage }) => ({ default: EditProcessModelPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.processes.list' } },
  { id: 'process-mining.models.map', module: 'process_mining', path: '/process-mining/models/:id/map', sourceFile: 'modules/process_mining/pages/ProcessMapPage.tsx', Page: lazy(() => import('./pages/ProcessMapPage').then(({ ProcessMapPage }) => ({ default: ProcessMapPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.processes.list' } },

  { id: 'process-mining.events.list', module: 'process_mining', path: '/process-mining/events', sourceFile: 'modules/process_mining/pages/EventExplorerPage.tsx', Page: lazy(() => import('./pages/EventExplorerPage').then(({ EventExplorerPage }) => ({ default: EventExplorerPage }))), navigation: { type: 'sidebar', label: 'Events', icon: Activity, order: 410 } },
  { id: 'process-mining.events.ingest', module: 'process_mining', path: '/process-mining/events/ingest', sourceFile: 'modules/process_mining/pages/IngestEventsPage.tsx', Page: lazy(() => import('./pages/IngestEventsPage').then(({ IngestEventsPage }) => ({ default: IngestEventsPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.events.list' } },
  { id: 'process-mining.events.detail', module: 'process_mining', path: '/process-mining/events/:id', sourceFile: 'modules/process_mining/pages/EventDetailPage.tsx', Page: lazy(() => import('./pages/EventDetailPage').then(({ EventDetailPage }) => ({ default: EventDetailPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.events.list' } },

  { id: 'process-mining.discoveries.list', module: 'process_mining', path: '/process-mining/discoveries', sourceFile: 'modules/process_mining/pages/DiscoveryListPage.tsx', Page: lazy(() => import('./pages/DiscoveryListPage').then(({ DiscoveryListPage }) => ({ default: DiscoveryListPage }))), navigation: { type: 'sidebar', label: 'Discoveries', icon: GitBranch, order: 420 } },
  { id: 'process-mining.discoveries.create', module: 'process_mining', path: '/process-mining/discoveries/new', sourceFile: 'modules/process_mining/pages/CreateDiscoveryPage.tsx', Page: lazy(() => import('./pages/CreateDiscoveryPage').then(({ CreateDiscoveryPage }) => ({ default: CreateDiscoveryPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.discoveries.list' } },
  { id: 'process-mining.discoveries.detail', module: 'process_mining', path: '/process-mining/discoveries/:id', sourceFile: 'modules/process_mining/pages/DiscoveryDetailPage.tsx', Page: lazy(() => import('./pages/DiscoveryDetailPage').then(({ DiscoveryDetailPage }) => ({ default: DiscoveryDetailPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.discoveries.list' } },

  { id: 'process-mining.conformance.list', module: 'process_mining', path: '/process-mining/conformance', sourceFile: 'modules/process_mining/pages/ConformanceListPage.tsx', Page: lazy(() => import('./pages/ConformanceListPage').then(({ ConformanceListPage }) => ({ default: ConformanceListPage }))), navigation: { type: 'sidebar', label: 'Conformance', icon: ShieldCheck, order: 430 } },
  { id: 'process-mining.conformance.create', module: 'process_mining', path: '/process-mining/conformance/new', sourceFile: 'modules/process_mining/pages/CreateConformancePage.tsx', Page: lazy(() => import('./pages/CreateConformancePage').then(({ CreateConformancePage }) => ({ default: CreateConformancePage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.conformance.list' } },
  { id: 'process-mining.conformance.detail', module: 'process_mining', path: '/process-mining/conformance/:id', sourceFile: 'modules/process_mining/pages/ConformanceDetailPage.tsx', Page: lazy(() => import('./pages/ConformanceDetailPage').then(({ ConformanceDetailPage }) => ({ default: ConformanceDetailPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.conformance.list' } },

  { id: 'process-mining.bottlenecks.list', module: 'process_mining', path: '/process-mining/bottlenecks', sourceFile: 'modules/process_mining/pages/BottleneckListPage.tsx', Page: lazy(() => import('./pages/BottleneckListPage').then(({ BottleneckListPage }) => ({ default: BottleneckListPage }))), navigation: { type: 'sidebar', label: 'Bottlenecks', icon: Gauge, order: 440 } },
  { id: 'process-mining.bottlenecks.create', module: 'process_mining', path: '/process-mining/bottlenecks/new', sourceFile: 'modules/process_mining/pages/CreateBottleneckAnalysisPage.tsx', Page: lazy(() => import('./pages/CreateBottleneckAnalysisPage').then(({ CreateBottleneckAnalysisPage }) => ({ default: CreateBottleneckAnalysisPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.bottlenecks.list' } },
  { id: 'process-mining.bottlenecks.detail', module: 'process_mining', path: '/process-mining/bottlenecks/:id', sourceFile: 'modules/process_mining/pages/BottleneckDetailPage.tsx', Page: lazy(() => import('./pages/BottleneckDetailPage').then(({ BottleneckDetailPage }) => ({ default: BottleneckDetailPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.bottlenecks.list' } },

  { id: 'process-mining.exports.list', module: 'process_mining', path: '/process-mining/exports', sourceFile: 'modules/process_mining/pages/ExportListPage.tsx', Page: lazy(() => import('./pages/ExportListPage').then(({ ExportListPage }) => ({ default: ExportListPage }))), navigation: { type: 'sidebar', label: 'Exports', icon: Download, order: 450 } },
  { id: 'process-mining.exports.create', module: 'process_mining', path: '/process-mining/exports/new', sourceFile: 'modules/process_mining/pages/CreateExportPage.tsx', Page: lazy(() => import('./pages/CreateExportPage').then(({ CreateExportPage }) => ({ default: CreateExportPage }))), navigation: { type: 'contextual', parentRouteId: 'process-mining.exports.list' } },
] as const;

const humanTitle = (sourceFile: string) => {
  const file = sourceFile.split('/').at(-1)?.replace(/Page\.tsx$/, '') ?? 'Process Mining';
  return file.replace(/([a-z])([A-Z])/g, '$1 $2');
};

export const tenantRoutes = routeDefinitions.map((route) => ({
  ...route,
  title: ('title' in route ? route.title : undefined) ?? `${humanTitle(route.sourceFile)} · Process Mining · SARAISE`,
})) satisfies readonly TenantRoute[];

export default tenantRoutes;
