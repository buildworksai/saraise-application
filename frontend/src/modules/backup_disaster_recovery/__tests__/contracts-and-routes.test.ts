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
    expect(ENDPOINTS.CONFIGURATIONS.CURRENT).toBe(`${MODULE_API_PREFIX}/configurations/current/`);
    expect(ENDPOINTS.CONFIGURATIONS.PREVIEW).toBe(`${MODULE_API_PREFIX}/configurations/preview/`);
    expect(ENDPOINTS.CONFIGURATIONS.ROLLBACK).toBe(`${MODULE_API_PREFIX}/configurations/rollback/`);
    expect(ENDPOINTS.CONFIGURATIONS.IMPORT).toBe(`${MODULE_API_PREFIX}/configurations/import-document/`);
    expect(ENDPOINTS.CONFIGURATIONS.EXPORT).toBe(`${MODULE_API_PREFIX}/configurations/export-document/`);
  });
});

describe('tenant route registry', () => {
  it('registers all 23 exact paths once', () => {
    expect(tenantRoutes).toHaveLength(23);
    expect(tenantRoutes.map((route) => route.path)).toEqual([
      '/backup-disaster-recovery',
      '/backup-disaster-recovery/backups/new',
      '/backup-disaster-recovery/recovery-points',
      '/backup-disaster-recovery/recovery-points/open',
      '/backup-disaster-recovery/recovery-points/:id',
      '/backup-disaster-recovery/restores',
      '/backup-disaster-recovery/restores/new',
      '/backup-disaster-recovery/restores/open',
      '/backup-disaster-recovery/restores/:id',
      '/backup-disaster-recovery/runbooks',
      '/backup-disaster-recovery/runbooks/new',
      '/backup-disaster-recovery/runbooks/open',
      '/backup-disaster-recovery/runbooks/open/edit',
      '/backup-disaster-recovery/runbooks/:id',
      '/backup-disaster-recovery/runbooks/:id/edit',
      '/backup-disaster-recovery/exercises',
      '/backup-disaster-recovery/exercises/new',
      '/backup-disaster-recovery/exercises/open',
      '/backup-disaster-recovery/exercises/open/edit',
      '/backup-disaster-recovery/exercises/:id',
      '/backup-disaster-recovery/exercises/:id/edit',
      '/backup-disaster-recovery/reports/objectives',
      '/backup-disaster-recovery/configuration',
    ]);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(23);
  });

  it('resolves every contextual route to a registered sidebar parent', () => {
    const ids = new Set(tenantRoutes.map((route) => route.id));
    const contextual = tenantRoutes.filter((route) => route.navigation.type === 'contextual');
    const sidebarSourceFiles = new Set(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').map((route) => route.sourceFile));
    expect(contextual).toHaveLength(6);
    contextual.forEach((route) => {
      if (route.navigation.type === 'contextual') expect(ids.has(route.navigation.parentRouteId)).toBe(true);
      expect(sidebarSourceFiles.has(route.sourceFile)).toBe(true);
    });
    expect(tenantRoutes.filter((route) => route.navigation.type === 'sidebar').map((route) => route.navigation.type === 'sidebar' ? route.navigation.label : '')).toEqual(['Overview','Request backup','Recovery points','Open recovery point','Restores','Plan restore','Open restore run','Runbooks','Create runbook','Open runbook','Edit runbook','Exercises','Schedule exercise','Open exercise','Edit exercise','Recovery objectives','Configuration']);
  });
});
