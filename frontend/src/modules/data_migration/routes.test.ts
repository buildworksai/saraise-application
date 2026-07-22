import { describe, expect, it } from 'vitest';
import { buildTenantSidebarTree, getTenantRouteValidationIssues, getTenantRoutesForMode, tenantRoutes as discoveredRoutes } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';

describe('data migration route registry', () => {
  it('owns the complete workflow with unique paths and valid contextual parents', () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    expect(tenantRoutes.map((route) => route.path)).toEqual(['/data-migration','/data-migration/jobs/new','/data-migration/jobs/:id/edit','/data-migration/jobs/:id','/data-migration/runs/:id','/data-migration/settings/connections']);
  });
  it('is discovered in every runtime mode and resolves a generated sidebar leaf', () => {
    const discovered = discoveredRoutes.filter((route) => route.module === 'data_migration');
    expect(discovered).toHaveLength(tenantRoutes.length);
    for (const mode of ['development','self-hosted','saas'] as const) expect(getTenantRoutesForMode(tenantRoutes, mode)).toHaveLength(tenantRoutes.length);
    const tree = buildTenantSidebarTree(tenantRoutes);
    expect(tree[0]?.children.map((leaf) => leaf.routeId)).toEqual(['data-migration.jobs.list']);
  });
});
