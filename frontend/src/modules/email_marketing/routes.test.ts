import { describe, expect, it } from 'vitest';
import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';
describe('email marketing tenant routes', () => {
  it('publishes configuration and a discoverable NavItem descriptor for every page', () => { const leaves = tenantRoutes.filter((route) => route.navigation.type === 'sidebar'); expect(leaves.map((route) => route.navigation.type === 'sidebar' ? route.navigation.label : '')).toEqual(['Campaigns', 'Templates', 'Delivery', 'Suppressions', 'Consents', 'Configuration']); expect(tenantRoutes).toHaveLength(18); expect(tenantRoutes.every((route) => route.navigation.type === 'sidebar' || Boolean(route.navigation.label && route.navigation.icon && route.navigation.order))).toBe(true); });
  it('supports every runtime mode, browser title, and registry invariant', () => { expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]); expect(tenantRoutes.every((route) => route.modes?.join(',') === 'development,self-hosted,saas')).toBe(true); expect(tenantRoutes.every((route) => Boolean(route.title))).toBe(true); expect(tenantRoutes.filter((route) => route.navigation.type === 'contextual')).toHaveLength(12); });
});
