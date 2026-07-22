import { describe, expect, it } from 'vitest';
import { getTenantRouteValidationIssues, buildTenantSidebarTree } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';

describe('multi-company tenant routes', () => {
  it('publishes every required page with valid unique registry metadata', () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(tenantRoutes).toHaveLength(27);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(27);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(27);
    expect(tenantRoutes.every((route) => route.title?.endsWith('· SARAISE'))).toBe(true);
    expect(tenantRoutes.every((route) => route.modes?.join(',') === 'development,self-hosted,saas')).toBe(true);
  });

  it('resolves the six required sidebar destinations', () => {
    const branch = buildTenantSidebarTree(tenantRoutes).find((item) => item.module === 'multi_company');
    expect(branch?.children.map((item) => item.label)).toEqual([
      'Companies', 'Transactions', 'Reconciliation', 'Consolidations', 'Transfer Pricing', 'Settings',
    ]);
  });
});
