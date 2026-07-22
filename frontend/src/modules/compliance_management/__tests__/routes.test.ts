import { describe, expect, it } from 'vitest';
import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from '../routes';

describe('compliance route descriptors', () => {
  it('passes registry validation in every runtime mode', () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(tenantRoutes.every((route) => route.modes?.join(',') === 'development,self-hosted,saas')).toBe(true);
  });

  it('makes the five primary workspaces discoverable and keeps contextual routes parameter-safe', () => {
    const sidebar = tenantRoutes.filter((route) => route.navigation.type === 'sidebar');
    expect(sidebar.map((route) => route.path)).toEqual([
      '/compliance-management', '/compliance-management/frameworks', '/compliance-management/requirements',
      '/compliance-management/policies', '/compliance-management/evidence',
    ]);
    expect(sidebar.some((route) => route.path.includes(':'))).toBe(false);
    expect(tenantRoutes.find((route) => route.path === '/compliance-management/policies/:id/edit')).toBeDefined();
  });
});
