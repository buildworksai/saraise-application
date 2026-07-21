import { describe, expect, it } from 'vitest';
import { ROUTES } from '../contracts';
import { tenantRoutes } from '../routes';

describe('performance monitoring route surface', () => {
  it('registers every operational workspace and keeps paths unique', () => {
    const paths = tenantRoutes.map((route) => route.path);
    expect(paths).toEqual(expect.arrayContaining([
      ROUTES.OVERVIEW,
      ROUTES.METRICS,
      ROUTES.LOGS,
      ROUTES.TRACES,
      ROUTES.ALERTS,
      ROUTES.ALERT_RULES,
      ROUTES.SLOS,
      ROUTES.SETUP,
    ]));
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('makes the dashboard discoverable and keeps alert rules contextual', () => {
    const dashboard = tenantRoutes.find((route) => route.id === 'performance-monitoring.dashboard');
    const rules = tenantRoutes.find((route) => route.id === 'performance-monitoring.alert-rules');
    expect(dashboard?.navigation.type).toBe('sidebar');
    expect(rules?.navigation).toEqual({ type: 'contextual', parentRouteId: 'performance-monitoring.alerts' });
  });
});
