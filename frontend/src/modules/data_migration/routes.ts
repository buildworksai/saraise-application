import { lazy } from 'react';
import { DatabaseZap } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';

const modes = ['development', 'self-hosted', 'saas'] as const;
const parentRouteId = 'data-migration.jobs.list';
const contextual = { type: 'contextual' as const, parentRouteId };

export const tenantRoutes = [
  { id: parentRouteId, module: 'data_migration', path: '/data-migration', sourceFile: 'modules/data_migration/pages/DataMigrationListPage.tsx', Page: lazy(() => import('./pages/DataMigrationListPage').then(({ DataMigrationListPage }) => ({ default: DataMigrationListPage }))), modes, navigation: { type: 'sidebar', label: 'Data migration', icon: DatabaseZap, order: 2400 } },
  { id: 'data-migration.jobs.create', module: 'data_migration', path: '/data-migration/jobs/new', sourceFile: 'modules/data_migration/pages/CreateDataMigrationJobPage.tsx', Page: lazy(() => import('./pages/CreateDataMigrationJobPage').then(({ CreateDataMigrationJobPage }) => ({ default: CreateDataMigrationJobPage }))), modes, navigation: contextual },
  { id: 'data-migration.jobs.edit', module: 'data_migration', path: '/data-migration/jobs/:id/edit', sourceFile: 'modules/data_migration/pages/EditDataMigrationJobPage.tsx', Page: lazy(() => import('./pages/EditDataMigrationJobPage').then(({ EditDataMigrationJobPage }) => ({ default: EditDataMigrationJobPage }))), modes, navigation: contextual },
  { id: 'data-migration.jobs.detail', module: 'data_migration', path: '/data-migration/jobs/:id', sourceFile: 'modules/data_migration/pages/DataMigrationDetailPage.tsx', Page: lazy(() => import('./pages/DataMigrationDetailPage').then(({ DataMigrationDetailPage }) => ({ default: DataMigrationDetailPage }))), modes, navigation: contextual },
  { id: 'data-migration.runs.detail', module: 'data_migration', path: '/data-migration/runs/:id', sourceFile: 'modules/data_migration/pages/MigrationRunDetailPage.tsx', Page: lazy(() => import('./pages/MigrationRunDetailPage').then(({ MigrationRunDetailPage }) => ({ default: MigrationRunDetailPage }))), modes, navigation: contextual },
  { id: 'data-migration.connections.settings', module: 'data_migration', path: '/data-migration/settings/connections', sourceFile: 'modules/data_migration/pages/ExternalConnectionsPage.tsx', Page: lazy(() => import('./pages/ExternalConnectionsPage').then(({ ExternalConnectionsPage }) => ({ default: ExternalConnectionsPage }))), modes, navigation: contextual },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
