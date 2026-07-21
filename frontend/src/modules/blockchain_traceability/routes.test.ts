import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';

describe('blockchain traceability route contract', () => {
  it('publishes all 24 required pages with seven sidebar leaves', () => {
    expect(tenantRoutes).toHaveLength(24);
    expect(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').map((route) => route.navigation.type === 'sidebar' ? route.navigation.label : '')).toEqual(['Assets', 'Events', 'Anchors', 'Credentials', 'Compliance', 'Verify', 'Networks']);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(24);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(24);
  });

  it('passes registry parity and ownership validation', () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(tenantRoutes.every((route) => route.module === 'blockchain_traceability')).toBe(true);
    expect(tenantRoutes.every((route) => route.sourceFile.startsWith('modules/blockchain_traceability/pages/'))).toBe(true);
    expect(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').every((route) => !route.path.includes(':'))).toBe(true);
  });
});
