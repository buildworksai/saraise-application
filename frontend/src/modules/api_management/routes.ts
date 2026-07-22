import { lazy } from 'react';
import { Boxes, Settings } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';
import { ROUTES } from './contracts';

const contextual = (parentRouteId: string) => ({ type: 'contextual' as const, parentRouteId });

export const tenantRoutes = [
  {
    id: 'api-management.resources.list',
    module: 'api_management',
    path: ROUTES.RESOURCES,
    title: 'API Management resources · SARAISE',
    sourceFile: 'modules/api_management/pages/ApiManagementListPage.tsx',
    Page: lazy(() => import('./pages/ApiManagementListPage').then(({ ApiManagementListPage }) => ({ default: ApiManagementListPage }))),
    navigation: { type: 'sidebar', label: 'Resources', icon: Boxes, order: 340 },
  },
  {
    id: 'api-management.resources.create',
    module: 'api_management',
    path: ROUTES.RESOURCE_CREATE,
    title: 'Create API Management resource · SARAISE',
    sourceFile: 'modules/api_management/pages/CreateApiManagementResourcePage.tsx',
    Page: lazy(() => import('./pages/CreateApiManagementResourcePage').then(({ CreateApiManagementResourcePage }) => ({ default: CreateApiManagementResourcePage }))),
    navigation: contextual('api-management.resources.list'),
  },
  {
    id: 'api-management.resources.detail',
    module: 'api_management',
    path: ROUTES.RESOURCE_DETAIL_PATTERN,
    title: 'API Management resource · SARAISE',
    sourceFile: 'modules/api_management/pages/ApiManagementDetailPage.tsx',
    Page: lazy(() => import('./pages/ApiManagementDetailPage').then(({ ApiManagementDetailPage }) => ({ default: ApiManagementDetailPage }))),
    navigation: contextual('api-management.resources.list'),
  },
  {
    id: 'api-management.configuration',
    module: 'api_management',
    path: ROUTES.CONFIGURATION,
    title: 'API Management configuration · SARAISE',
    sourceFile: 'modules/api_management/pages/ApiManagementConfigurationPage.tsx',
    Page: lazy(() => import('./pages/ApiManagementConfigurationPage').then(({ ApiManagementConfigurationPage }) => ({ default: ApiManagementConfigurationPage }))),
    navigation: { type: 'sidebar', label: 'Configuration', icon: Settings, order: 341 },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
