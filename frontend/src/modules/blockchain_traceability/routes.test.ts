import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';

describe('blockchain traceability route contract', () => {
  it('publishes every page as a titled, discoverable sidebar NavItem', () => {
    expect(tenantRoutes).toHaveLength(26);
    expect(tenantRoutes.every((route) => route.navigation.type === 'sidebar')).toBe(true);
    expect(tenantRoutes.every((route) => Boolean(route.title?.trim()))).toBe(true);
    expect(tenantRoutes.every((route) => route.navigation.type !== 'sidebar' || Boolean(route.navigation.label.trim()))).toBe(true);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(26);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(26);
  });

  it('passes registry parity and ownership validation', () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(tenantRoutes.every((route) => route.module === 'blockchain_traceability')).toBe(true);
    expect(tenantRoutes.every((route) => route.sourceFile.startsWith('modules/blockchain_traceability/pages/'))).toBe(true);
    expect(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').every((route) => !(route.navigation.path ?? route.path).includes(':'))).toBe(true);
    expect(tenantRoutes.filter((route) => route.path.includes(':')).every((route) => route.navigation.type === 'sidebar' && !route.navigation.path?.includes(':'))).toBe(true);
  });
});
