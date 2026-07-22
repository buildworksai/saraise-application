import { buildTenantSidebarTree, getTenantRoutesForMode, validateTenantRoutes } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';

describe('fixed-assets tenant routes', () => {
  it('publishes every required page with unique ids, paths, and valid parents', () => {
    expect(tenantRoutes).toHaveLength(15);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(15);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(15);
    expect(() => validateTenantRoutes(tenantRoutes)).not.toThrow();
  });

  it.each(['development', 'self-hosted', 'saas'] as const)('is visible in %s mode', (mode) => {
    expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(15);
  });

  it('resolves the four required sidebar leaves', () => {
    const tree = buildTenantSidebarTree(tenantRoutes);
    expect(tree).toHaveLength(1);
    expect(tree[0]?.children.map((leaf) => leaf.path)).toEqual([
      '/fixed-assets/dashboard', '/fixed-assets/assets', '/fixed-assets/categories', '/fixed-assets/depreciation-schedules',
    ]);
  });
});
