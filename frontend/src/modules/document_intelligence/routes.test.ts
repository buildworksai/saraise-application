import { tenantRoutes } from './routes';

describe('document intelligence route contract', () => {
  it('publishes every governed registry route with title metadata', () => {
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
      '/document-intelligence/configuration',
      '/document-intelligence/health',
    ]);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(14);
    tenantRoutes.forEach((route) => expect(route.title).toBeTruthy());
  });

  it('publishes a safe sidebar NavItem for every page', () => {
    const sidebarIds = new Set(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').map((route) => route.id));
    expect(sidebarIds.size).toBe(tenantRoutes.length);
    tenantRoutes.forEach((route) => {
      expect(route.module).toBe('document_intelligence');
      expect(route.navigation.type).toBe('sidebar');
      if (route.navigation.type === 'sidebar') {
        expect(route.navigation.label).toBeTruthy();
        expect(route.navigation.icon).toBeTruthy();
        const navigationPath = route.navigation.path ?? route.path;
        expect(navigationPath).not.toContain(':');
      }
    });
  });
});
