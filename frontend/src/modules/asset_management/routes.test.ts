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
  it('publishes list, create, detail, and edit with valid contextual ownership', () => {
    expect(tenantRoutes).toHaveLength(4);
    expect(tenantRoutes.map((route) => route.path)).toEqual([
      ROUTES.ASSETS.LIST,
      ROUTES.ASSETS.CREATE,
      ROUTES.ASSETS.DETAIL_PATTERN,
      ROUTES.ASSETS.EDIT_PATTERN,
    ]);
    expect(() => validateTenantRoutes(tenantRoutes)).not.toThrow();
  });

  it.each(['development', 'self-hosted', 'saas'] as const)('is available in %s mode', (mode) => {
    expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(4);
  });

  it('contributes one discoverable asset-register sidebar leaf', () => {
    const tree = buildTenantSidebarTree(tenantRoutes);
    expect(tree).toHaveLength(1);
    expect(tree[0]).toMatchObject({
      module: 'asset_management',
      children: [{ path: ROUTES.ASSETS.LIST, label: 'Asset register' }],
    });
  });

  it('is discovered by the application registry consumed by TenantSidebar', () => {
    expect(registeredTenantRoutes.filter((route) => route.module === 'asset_management'))
      .toHaveLength(4);
    const sidebarBranch = getTenantSidebarTreeForMode('development')
      .find((branch) => branch.module === 'asset_management');
    expect(sidebarBranch?.children.map((child) => child.path)).toEqual([ROUTES.ASSETS.LIST]);
  });
});
