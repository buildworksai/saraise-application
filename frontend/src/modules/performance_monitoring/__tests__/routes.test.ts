import { describe, expect, it } from 'vitest';
import { ROUTES } from '../contracts';
import { tenantRoutes } from '../routes';

describe('performance monitoring route surface', () => {
  it('registers every operational workspace and keeps paths unique', () => {
    const paths = tenantRoutes.map((route) => route.path);
    expect(paths).toEqual(expect.arrayContaining([
      ROUTES.INDEX,
      ROUTES.OVERVIEW,
      ROUTES.METRICS,
      ROUTES.LOGS,
      ROUTES.TRACES,
      ROUTES.ALERTS,
      ROUTES.ALERT_RULES,
      ROUTES.SLOS,
      ROUTES.CATALOG,
      ROUTES.CONFIGURATION,
      ROUTES.SETUP,
    ]));
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('makes every page discoverable in the tenant sidebar', () => {
    const dashboard = tenantRoutes.find((route) => route.id === 'performance-monitoring.dashboard');
    const rules = tenantRoutes.find((route) => route.id === 'performance-monitoring.alert-rules');
    expect(dashboard?.navigation.type).toBe('sidebar');
    expect(rules?.navigation.type).toBe('sidebar');
    expect(tenantRoutes.every((route) => route.navigation.type === 'sidebar')).toBe(true);
  });
});
