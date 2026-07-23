import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';

describe('DMS tenant route registry', () => {
  it('publishes all eight required unique, titled, and structurally valid routes', () => {
    expect(tenantRoutes).toHaveLength(8);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(8);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(8);
    expect(tenantRoutes.every((route) => Boolean(route.title))).toBe(true);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
  });

  it('links every contextual page to the primary document browser', () => {
    const sidebar = tenantRoutes.find((route) => route.navigation.type === 'sidebar');
    expect(sidebar?.id).toBe('dms.documents.list');
    for (const route of tenantRoutes) if (route.navigation.type === 'contextual') expect(route.navigation.parentRouteId).toBe(sidebar?.id);
  });

  it('publishes configuration as a governed sidebar destination', () => {
    const configuration = tenantRoutes.find((route) => route.id === 'dms.configuration');
    expect(configuration?.path).toBe('/dms/configuration');
    expect(configuration?.requiredPermission).toBe('dms.configuration:read');
    expect(configuration?.navigation.type).toBe('sidebar');
  });
});
