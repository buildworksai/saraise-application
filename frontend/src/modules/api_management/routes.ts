import { lazy } from 'react';
import { Boxes, FileSearch, Plus, Settings } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';
import { ROUTES } from './contracts';

export const tenantRoutes = [
  {
    id: 'api-management.resources.list',
    module: 'api_management',
    path: ROUTES.RESOURCES,
    title: 'API Management resources · SARAISE',
    sourceFile: 'modules/api_management/pages/ApiManagementListPage.tsx',
    Page: lazy(() => import('./pages/ApiManagementListPage').then(({ ApiManagementListPage }) => ({ default: ApiManagementListPage }))),
    navigation: { type: 'sidebar', label: 'Resources', icon: Boxes, runtimeOrderKey: 'resources_list' },
  },
  {
    id: 'api-management.resources.create',
    module: 'api_management',
    path: ROUTES.RESOURCE_CREATE,
    title: 'Create API Management resource · SARAISE',
    sourceFile: 'modules/api_management/pages/CreateApiManagementResourcePage.tsx',
    Page: lazy(() => import('./pages/CreateApiManagementResourcePage').then(({ CreateApiManagementResourcePage }) => ({ default: CreateApiManagementResourcePage }))),
    navigation: { type: 'sidebar', label: 'Create resource', icon: Plus, runtimeOrderKey: 'resources_create' },
  },
  {
    id: 'api-management.resources.detail',
    module: 'api_management',
    path: ROUTES.RESOURCE_DETAIL_PATTERN,
    title: 'API Management resource · SARAISE',
    sourceFile: 'modules/api_management/pages/ApiManagementDetailPage.tsx',
    Page: lazy(() => import('./pages/ApiManagementDetailPage').then(({ ApiManagementDetailPage }) => ({ default: ApiManagementDetailPage }))),
    navigation: { type: 'sidebar', label: 'Open resource', icon: FileSearch, runtimeOrderKey: 'resources_detail', path: ROUTES.RESOURCES },
  },
  {
    id: 'api-management.configuration',
    module: 'api_management',
    path: ROUTES.CONFIGURATION,
    title: 'API Management configuration · SARAISE',
    sourceFile: 'modules/api_management/pages/ApiManagementConfigurationPage.tsx',
    Page: lazy(() => import('./pages/ApiManagementConfigurationPage').then(({ ApiManagementConfigurationPage }) => ({ default: ApiManagementConfigurationPage }))),
    navigation: { type: 'sidebar', label: 'Configuration', icon: Settings, runtimeOrderKey: 'configuration' },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
