import { describe, expect, it } from 'vitest'; import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry'; import { ROUTES } from '../contracts'; import { tenantRoutes } from '../routes';
describe('Human Resources route inventory', () => {
  it('publishes a sidebar NavItem and title for every routed HR page', () => {
    expect(tenantRoutes).toHaveLength(21);
    expect(tenantRoutes.every((route) => route.navigation.type === 'sidebar')).toBe(true);
    expect(tenantRoutes.every((route) => Boolean(route.title?.trim()))).toBe(true);
    expect(tenantRoutes.map((route) => route.path)).toContain(ROUTES.CONFIGURATION);
  });
  it('has unique paths and valid sidebar parents', () => {
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(tenantRoutes.filter((route) => route.navigation.type === 'sidebar')).toHaveLength(tenantRoutes.length);
  });
});
