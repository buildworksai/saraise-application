import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';

describe('DMS tenant route registry', () => {
  it('publishes the seven required unique and structurally valid routes', () => {
    expect(tenantRoutes).toHaveLength(7);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(7);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(7);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
  });

  it('links every contextual page to the primary document browser', () => {
    const sidebar = tenantRoutes.find((route) => route.navigation.type === 'sidebar');
    expect(sidebar?.id).toBe('dms.documents.list');
    for (const route of tenantRoutes) if (route.navigation.type === 'contextual') expect(route.navigation.parentRouteId).toBe(sidebar?.id);
  });
});
