import { lazy } from 'react';
import { Boxes, FilePlus2, Pencil, Search, Settings } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';
import { ROUTES } from './contracts';

const MODULE = 'asset_management';
const modes = ['development', 'self-hosted', 'saas'] as const;
const contextual = (parentRouteId: string, label: string, icon: typeof Boxes, order: number) => ({
  type: 'contextual' as const,
  parentRouteId,
  label,
  icon,
  order,
});

export const tenantRoutes = [
  {
    id: 'asset_management.assets.list',
    module: MODULE,
    path: ROUTES.ASSETS.LIST,
    sourceFile: 'modules/asset_management/pages/AssetListPage.tsx',
    Page: lazy(() => import('./pages/AssetListPage').then(({ AssetListPage }) => ({ default: AssetListPage }))),
    title: 'Asset register',
    requiredPermission: 'asset.asset:read',
    modes,
    navigation: { type: 'sidebar', label: 'Asset register', icon: Boxes, order: 510 },
  },
  {
    id: 'asset_management.assets.create',
    module: MODULE,
    path: ROUTES.ASSETS.CREATE,
    sourceFile: 'modules/asset_management/pages/CreateAssetPage.tsx',
    Page: lazy(() => import('./pages/CreateAssetPage').then(({ CreateAssetPage }) => ({ default: CreateAssetPage }))),
    title: 'Create asset',
    requiredPermission: 'asset.asset:create',
    modes,
    navigation: contextual('asset_management.assets.list', 'Create asset', FilePlus2, 511),
  },
  {
    id: 'asset_management.assets.detail',
    module: MODULE,
    path: ROUTES.ASSETS.DETAIL_PATTERN,
    sourceFile: 'modules/asset_management/pages/AssetDetailPage.tsx',
    Page: lazy(() => import('./pages/AssetDetailPage').then(({ AssetDetailPage }) => ({ default: AssetDetailPage }))),
    title: 'Asset details',
    requiredPermission: 'asset.asset:read',
    modes,
    navigation: contextual('asset_management.assets.list', 'Asset details', Search, 512),
  },
  {
    id: 'asset_management.assets.edit',
    module: MODULE,
    path: ROUTES.ASSETS.EDIT_PATTERN,
    sourceFile: 'modules/asset_management/pages/EditAssetPage.tsx',
    Page: lazy(() => import('./pages/EditAssetPage').then(({ EditAssetPage }) => ({ default: EditAssetPage }))),
    title: 'Edit asset',
    requiredPermission: 'asset.asset:update',
    modes,
    navigation: contextual('asset_management.assets.list', 'Edit asset', Pencil, 513),
  },
  {
    id: 'asset_management.configuration',
    module: MODULE,
    path: ROUTES.ASSETS.CONFIGURATION,
    sourceFile: 'modules/asset_management/pages/AssetConfigurationPage.tsx',
    Page: lazy(() => import('./pages/AssetConfigurationPage').then(({ AssetConfigurationPage }) => ({ default: AssetConfigurationPage }))),
    title: 'Asset configuration',
    requiredPermission: 'asset.configuration:read',
    modes,
    navigation: { type: 'sidebar', label: 'Configuration', icon: Settings, order: 514 },
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
