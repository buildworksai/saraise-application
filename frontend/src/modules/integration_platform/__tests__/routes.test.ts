import { describe, expect, it } from 'vitest';
import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from '../routes';

describe('Integration Platform route descriptors', () => {
  it('registers five sidebar destinations and all contextual workflows', () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    const sidebar = tenantRoutes.filter((route) => route.navigation.type === 'sidebar');
    expect(sidebar.map((route) => route.path)).toEqual([
      '/integration-platform', '/integration-platform/connectors', '/integration-platform/webhooks',
      '/integration-platform/deliveries', '/integration-platform/mappings',
    ]);
    expect(tenantRoutes).toHaveLength(20);
    expect(tenantRoutes.every((route) => route.sourceFile.startsWith('modules/integration_platform/pages/'))).toBe(true);
  });

  it('links every contextual page to a same-module sidebar parent', () => {
    const sidebarIds = new Set(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').map((route) => route.id));
    for (const route of tenantRoutes) if (route.navigation.type === 'contextual') expect(sidebarIds.has(route.navigation.parentRouteId)).toBe(true);
  });
});
