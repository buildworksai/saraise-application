import { describe, expect, it } from 'vitest';
import { getTenantRouteValidationIssues } from '@/navigation/tenant-route-registry';
import { tenantRoutes } from './routes';
describe('email marketing tenant routes', () => {
  it('publishes five sidebar leaves and contextual children', () => { const leaves = tenantRoutes.filter((route) => route.navigation.type === 'sidebar'); expect(leaves.map((route) => route.navigation.type === 'sidebar' ? route.navigation.label : '')).toEqual(['Campaigns', 'Templates', 'Delivery', 'Suppressions', 'Consents']); expect(tenantRoutes).toHaveLength(17); });
  it('supports every runtime mode and passes registry validation', () => { expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]); expect(tenantRoutes.every((route) => route.modes?.join(',') === 'development,self-hosted,saas')).toBe(true); expect(tenantRoutes.filter((route) => route.navigation.type === 'contextual')).toHaveLength(12); });
});
