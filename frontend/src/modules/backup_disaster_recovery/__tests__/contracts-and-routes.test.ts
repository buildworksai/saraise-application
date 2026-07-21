import { describe, expect, it } from 'vitest';
import { ENDPOINTS, MODULE_API_PREFIX } from '../contracts';
import { tenantRoutes } from '../routes';

describe('backup and disaster recovery contracts', () => {
  it('constructs every governed v2 resource and action endpoint', () => {
    expect(MODULE_API_PREFIX).toBe('/api/v2/backup-disaster-recovery');
    expect(ENDPOINTS.BACKUP_EXECUTIONS.CREATE).toBe(`${MODULE_API_PREFIX}/backup-executions/`);
    expect(ENDPOINTS.RECOVERY_POINTS.VERIFY('point')).toBe(`${MODULE_API_PREFIX}/recovery-points/point/verify/`);
    expect(ENDPOINTS.RESTORE_RUNS.EXECUTE('restore')).toBe(`${MODULE_API_PREFIX}/restore-runs/restore/execute/`);
    expect(ENDPOINTS.RUNBOOKS.REORDER_STEPS('book')).toBe(`${MODULE_API_PREFIX}/runbooks/book/reorder-steps/`);
    expect(ENDPOINTS.EXERCISES.CANCEL('exercise')).toBe(`${MODULE_API_PREFIX}/exercises/exercise/cancel/`);
    expect(ENDPOINTS.STEP_EXECUTIONS.DETAIL('evidence')).toBe(`${MODULE_API_PREFIX}/step-executions/evidence/`);
    expect(ENDPOINTS.REPORTS.OBJECTIVES).toBe(`${MODULE_API_PREFIX}/reports/objectives/`);
    expect(ENDPOINTS.READINESS).toBe(`${MODULE_API_PREFIX}/readiness/`);
  });
});

describe('tenant route registry', () => {
  it('registers all 16 exact paths once', () => {
    expect(tenantRoutes).toHaveLength(16);
    expect(tenantRoutes.map((route) => route.path)).toEqual([
      '/backup-disaster-recovery',
      '/backup-disaster-recovery/backups/new',
      '/backup-disaster-recovery/recovery-points',
      '/backup-disaster-recovery/recovery-points/:id',
      '/backup-disaster-recovery/restores',
      '/backup-disaster-recovery/restores/new',
      '/backup-disaster-recovery/restores/:id',
      '/backup-disaster-recovery/runbooks',
      '/backup-disaster-recovery/runbooks/new',
      '/backup-disaster-recovery/runbooks/:id',
      '/backup-disaster-recovery/runbooks/:id/edit',
      '/backup-disaster-recovery/exercises',
      '/backup-disaster-recovery/exercises/new',
      '/backup-disaster-recovery/exercises/:id',
      '/backup-disaster-recovery/exercises/:id/edit',
      '/backup-disaster-recovery/reports/objectives',
    ]);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(16);
  });

  it('resolves every contextual route to a registered sidebar parent', () => {
    const ids = new Set(tenantRoutes.map((route) => route.id));
    const contextual = tenantRoutes.filter((route) => route.navigation.type === 'contextual');
    expect(contextual).toHaveLength(10);
    contextual.forEach((route) => {
      if (route.navigation.type === 'contextual') expect(ids.has(route.navigation.parentRouteId)).toBe(true);
    });
    expect(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').map((route) => route.navigation.type === 'sidebar' ? route.navigation.label : '')).toEqual(['Overview','Recovery points','Restores','Runbooks','Exercises','Recovery objectives']);
  });
});
