import tenantRoutes from '../routes';

describe('CRM tenant route registry', () => {
  it('publishes every sidebar and contextual route with unique ids and paths', () => {
    expect(tenantRoutes.filter(route => route.navigation.type === 'sidebar').map(route => route.path)).toEqual([
      '/crm/dashboard', '/crm/leads', '/crm/accounts', '/crm/contacts', '/crm/opportunities', '/crm/opportunities/pipeline', '/crm/activities',
    ]);
    expect(new Set(tenantRoutes.map(route => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map(route => route.path)).size).toBe(tenantRoutes.length);
    expect(tenantRoutes).toHaveLength(22);
  });

  it('makes every contextual route reachable from an existing sidebar parent', () => {
    const byId = new Map(tenantRoutes.map(route => [route.id, route]));
    for (const route of tenantRoutes) {
      expect(route.Page).toBeDefined();
      if (route.navigation.type !== 'contextual') continue;
      expect(byId.get(route.navigation.parentRouteId)?.navigation.type).toBe('sidebar');
    }
  });
});
