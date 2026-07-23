import {
  buildTenantSidebarTree,
  getTenantSidebarTreeForMode,
  getTenantRoutesForMode,
  tenantRoutes as registeredTenantRoutes,
  validateTenantRoutes,
} from '@/navigation/tenant-route-registry';
import { ROUTES } from './contracts';
import { tenantRoutes } from './routes';

describe('asset-management tenant routes', () => {
  it('publishes list, create, detail, edit, and configuration with valid ownership', () => {
    expect(tenantRoutes).toHaveLength(5);
    expect(tenantRoutes.map((route) => route.path)).toEqual([
      ROUTES.ASSETS.LIST,
      ROUTES.ASSETS.CREATE,
      ROUTES.ASSETS.DETAIL_PATTERN,
      ROUTES.ASSETS.EDIT_PATTERN,
      ROUTES.ASSETS.CONFIGURATION,
    ]);
    expect(() => validateTenantRoutes(tenantRoutes)).not.toThrow();
  });

  it.each(['development', 'self-hosted', 'saas'] as const)('is available in %s mode', (mode) => {
    expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(5);
  });

  it('contributes discoverable sidebar leaves for every page', () => {
    const tree = buildTenantSidebarTree(tenantRoutes);
    expect(tree).toHaveLength(1);
    expect(tree[0]).toMatchObject({
      module: 'asset_management',
      children: [
        { path: ROUTES.ASSETS.LIST, label: 'Asset register' },
        { path: ROUTES.ASSETS.CREATE, label: 'Create asset' },
        { path: ROUTES.ASSETS.LIST, label: 'Asset details' },
        { path: ROUTES.ASSETS.LIST, label: 'Edit asset' },
        { path: ROUTES.ASSETS.CONFIGURATION, label: 'Configuration' },
      ],
    });
  });

  it('is discovered by the application registry consumed by TenantSidebar', () => {
    expect(registeredTenantRoutes.filter((route) => route.module === 'asset_management'))
      .toHaveLength(5);
    const sidebarBranch = getTenantSidebarTreeForMode('development')
      .find((branch) => branch.module === 'asset_management');
    expect(sidebarBranch?.children.map((child) => child.path)).toEqual([
      ROUTES.ASSETS.LIST,
      ROUTES.ASSETS.CREATE,
      ROUTES.ASSETS.LIST,
      ROUTES.ASSETS.LIST,
      ROUTES.ASSETS.CONFIGURATION,
    ]);
  });
});
