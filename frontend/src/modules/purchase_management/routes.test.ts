import { describe, expect, it } from 'vitest';

import {
  buildTenantSidebarTree,
  getTenantRouteValidationIssues,
  tenantRoutes as discoveredRoutes,
} from '@/navigation/tenant-route-registry';

import { tenantRoutes } from './routes';

describe('purchase-management tenant routes', () => {
  it('registers every module-owned route through discovery', () => {
    const discovered = discoveredRoutes.filter((route) => route.module === 'purchase_management');
    expect(discovered).toHaveLength(tenantRoutes.length);
    expect(discovered.map((route) => route.path)).toEqual(
      expect.arrayContaining([
        '/purchase-management/suppliers',
        '/purchase-management/requisitions',
        '/purchase-management/rfqs',
        '/purchase-management/quotes',
        '/purchase-management/purchase-orders',
        '/purchase-management/receipts',
        '/purchase-management/settings',
      ]),
    );
  });

  it('has unique paths, valid parents, and six workflow sidebar groups plus settings', () => {
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    const sidebarLeaves = tenantRoutes.filter((route) => route.navigation.type === 'sidebar');
    expect(sidebarLeaves).toHaveLength(7);
    expect(buildTenantSidebarTree(tenantRoutes).flatMap((group) => group.children)).toHaveLength(7);
  });

  it('sets a human-readable title on every page', () => {
    expect(tenantRoutes.every((route) => typeof route.title === 'string' && route.title.trim().length > 0)).toBe(true);
  });
});
