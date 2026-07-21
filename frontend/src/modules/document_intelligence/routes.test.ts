import { tenantRoutes } from './routes';

describe('document intelligence route contract', () => {
  it('publishes all twelve required registry routes', () => {
    expect(tenantRoutes.map((route) => route.path)).toEqual([
      '/document-intelligence/extractions',
      '/document-intelligence/extractions/new',
      '/document-intelligence/extractions/:id',
      '/document-intelligence/classifications',
      '/document-intelligence/classifications/:id',
      '/document-intelligence/templates',
      '/document-intelligence/templates/new',
      '/document-intelligence/templates/:id',
      '/document-intelligence/templates/:id/edit',
      '/document-intelligence/training',
      '/document-intelligence/training/new',
      '/document-intelligence/training/:id',
    ]);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(12);
  });

  it('connects every contextual page to a sidebar leaf', () => {
    const sidebarIds = new Set(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').map((route) => route.id));
    expect(sidebarIds.size).toBe(4);
    tenantRoutes.forEach((route) => {
      expect(route.module).toBe('document_intelligence');
      if (route.navigation.type === 'contextual') expect(sidebarIds.has(route.navigation.parentRouteId)).toBe(true);
    });
  });
});
