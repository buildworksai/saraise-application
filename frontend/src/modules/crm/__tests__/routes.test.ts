import tenantRoutes from '../routes';

describe('CRM tenant route registry', () => {
  it('publishes every CRM page as a sidebar-resolvable route with unique ids and paths', () => {
    expect(tenantRoutes.filter(route => route.navigation.type === 'sidebar').map(route => route.path)).toEqual([
      '/crm/dashboard','/crm/leads','/crm/leads/new','/crm/leads/:id','/crm/leads/:id/edit','/crm/accounts','/crm/accounts/new','/crm/accounts/:id','/crm/accounts/:id/edit','/crm/contacts','/crm/contacts/new','/crm/contacts/:id','/crm/contacts/:id/edit','/crm/opportunities','/crm/opportunities/pipeline','/crm/opportunities/new','/crm/opportunities/:id','/crm/opportunities/:id/edit','/crm/activities','/crm/activities/new','/crm/activities/:id','/crm/activities/:id/edit','/crm/configuration',
    ]);
    expect(new Set(tenantRoutes.map(route => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map(route => route.path)).size).toBe(tenantRoutes.length);
    expect(tenantRoutes).toHaveLength(23);
  });

  it('gives every page a stable parameter-free sidebar destination', () => {
    for (const route of tenantRoutes) {
      expect(route.Page).toBeDefined();
      expect(route.navigation.type).toBe('sidebar');
      if(route.navigation.type==='sidebar')expect(route.navigation.path??route.path).not.toContain(':');
    }
  });
});
