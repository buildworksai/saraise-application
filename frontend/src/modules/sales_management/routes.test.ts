import { describe, expect, it } from 'vitest';
import { tenantRoutes } from './routes';

describe('sales management route contract', () => {
  it('publishes unique titled routes with real source files', () => {
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    for (const route of tenantRoutes) {
      expect(route.title.trim().length).toBeGreaterThan(0);
      expect(route.sourceFile).toMatch(/^modules\/sales_management\/pages\/.+\.tsx$/);
      expect(route.modes).toEqual(['development', 'self-hosted', 'saas']);
    }
  });

  it('keeps contextual routes attached to sidebar parents', () => {
    const byId = new Map(tenantRoutes.map((route) => [route.id, route]));
    for (const route of tenantRoutes) {
      if (route.navigation.type !== 'contextual') continue;
      expect(byId.get(route.navigation.parentRouteId)?.navigation.type).toBe('sidebar');
    }
  });

  it('keeps sidebar and route registry in parity', () => {
    expect(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').sort((left, right) => left.navigation.type === 'sidebar' && right.navigation.type === 'sidebar' ? left.navigation.order - right.navigation.order : 0).map((route) => route.navigation.type === 'sidebar' ? route.navigation.label : '')).toEqual([
      'Sales Overview', 'Customers', 'Quotations', 'Sales Orders', 'Deliveries', 'Sales Configuration',
    ]);
    for (const route of tenantRoutes.filter((entry) => entry.navigation.type === 'sidebar')) expect(route.path.includes(':')).toBe(false);
  });

  it('declares static routes before parameter routes', () => {
    expect(tenantRoutes.findIndex((route) => route.path === '/sales-management/configuration')).toBeLessThan(tenantRoutes.findIndex((route) => route.path.includes(':')));
    for (const stem of ['customers', 'quotations', 'sales-orders', 'deliveries']) {
      expect(tenantRoutes.findIndex((route) => route.path === `/sales-management/${stem}/new`)).toBeLessThan(tenantRoutes.findIndex((route) => route.path === `/sales-management/${stem}/:id`));
    }
  });
});
