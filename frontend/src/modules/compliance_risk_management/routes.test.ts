import { buildTenantSidebarTree, getTenantRoutesForMode, validateTenantRoutes } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';

describe('compliance risk tenant routes', () => {
  it('publishes unique lazy routes with valid contextual parents', () => {
    expect(tenantRoutes).toHaveLength(30);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    expect(() => validateTenantRoutes(tenantRoutes)).not.toThrow();
    expect(tenantRoutes.every((route) => '$$typeof' in route.Page)).toBe(true);
  });

  it.each(['development', 'self-hosted', 'saas'] as const)('is available in %s mode', (mode) => {
    expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(tenantRoutes.length);
  });

  it('derives exactly the seven required sidebar routes', () => {
    expect(buildTenantSidebarTree(tenantRoutes)[0]?.children.map((leaf) => leaf.path)).toEqual([
      '/compliance-risk-management/dashboard', '/compliance-risk-management/risks',
      '/compliance-risk-management/controls', '/compliance-risk-management/requirements',
      '/compliance-risk-management/calendar', '/compliance-risk-management/remediations',
      '/compliance-risk-management/configuration',
    ]);
  });
});
