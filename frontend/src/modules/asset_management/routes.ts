import { lazy } from 'react';
import { Boxes } from 'lucide-react';
import type { TenantRoute } from '@/navigation/tenant-route-types';
import { ROUTES } from './contracts';

const MODULE = 'asset_management';
const modes = ['development', 'self-hosted', 'saas'] as const;
const contextual = (parentRouteId: string) => ({ type: 'contextual' as const, parentRouteId });

export const tenantRoutes = [
  {
    id: 'asset_management.assets.list',
    module: MODULE,
    path: ROUTES.ASSETS.LIST,
    sourceFile: 'modules/asset_management/pages/AssetListPage.tsx',
    Page: lazy(() => import('./pages/AssetListPage').then(({ AssetListPage }) => ({ default: AssetListPage }))),
    modes,
    navigation: { type: 'sidebar', label: 'Asset register', icon: Boxes, order: 510 },
  },
  {
    id: 'asset_management.assets.create',
    module: MODULE,
    path: ROUTES.ASSETS.CREATE,
    sourceFile: 'modules/asset_management/pages/CreateAssetPage.tsx',
    Page: lazy(() => import('./pages/CreateAssetPage').then(({ CreateAssetPage }) => ({ default: CreateAssetPage }))),
    modes,
    navigation: contextual('asset_management.assets.list'),
  },
  {
    id: 'asset_management.assets.detail',
    module: MODULE,
    path: ROUTES.ASSETS.DETAIL_PATTERN,
    sourceFile: 'modules/asset_management/pages/AssetDetailPage.tsx',
    Page: lazy(() => import('./pages/AssetDetailPage').then(({ AssetDetailPage }) => ({ default: AssetDetailPage }))),
    modes,
    navigation: contextual('asset_management.assets.list'),
  },
  {
    id: 'asset_management.assets.edit',
    module: MODULE,
    path: ROUTES.ASSETS.EDIT_PATTERN,
    sourceFile: 'modules/asset_management/pages/EditAssetPage.tsx',
    Page: lazy(() => import('./pages/EditAssetPage').then(({ EditAssetPage }) => ({ default: EditAssetPage }))),
    modes,
    navigation: contextual('asset_management.assets.list'),
  },
] satisfies readonly TenantRoute[];

export default tenantRoutes;
