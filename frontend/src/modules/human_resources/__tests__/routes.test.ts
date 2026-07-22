import { describe, expect, it } from 'vitest'; import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry'; import { ROUTES } from '../contracts'; import { tenantRoutes } from '../routes';
describe('Human Resources route inventory', () => {
  it('contains exactly five sidebar and fifteen contextual routes', () => {
    expect(tenantRoutes).toHaveLength(20);
    expect(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').map((route) => route.path)).toEqual([ROUTES.OVERVIEW, ROUTES.EMPLOYEES, ROUTES.DEPARTMENTS, ROUTES.ATTENDANCE, ROUTES.LEAVE]);
    expect(tenantRoutes.filter((route) => route.navigation.type === 'contextual')).toHaveLength(15);
  });
  it('has unique paths and valid sidebar parents', () => {
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    const ids = new Set(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').map((route) => route.id));
    for (const route of tenantRoutes) if (route.navigation.type === 'contextual') expect(ids.has(route.navigation.parentRouteId)).toBe(true);
  });
});
