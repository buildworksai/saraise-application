import { ENDPOINTS, MODULE_API_PREFIX } from './contracts';

describe('compliance risk governed contracts', () => {
  it('uses only the governed v2 prefix', () => {
    expect(MODULE_API_PREFIX).toBe('/api/v2/compliance-risk-management');
    expect(JSON.stringify(ENDPOINTS)).not.toContain('/api/v1/');
  });

  it('publishes every required static collection and action path', () => {
    expect(ENDPOINTS.RISKS.LIST).toBe(`${MODULE_API_PREFIX}/risks/`);
    expect(ENDPOINTS.RISKS.SCORE_PREVIEW).toBe(`${MODULE_API_PREFIX}/risks/score-preview/`);
    expect(ENDPOINTS.CONTROLS.LIST).toBe(`${MODULE_API_PREFIX}/controls/`);
    expect(ENDPOINTS.TESTS.LIST).toBe(`${MODULE_API_PREFIX}/tests/`);
    expect(ENDPOINTS.REQUIREMENTS.LIST).toBe(`${MODULE_API_PREFIX}/requirements/`);
    expect(ENDPOINTS.CALENDAR.LIST).toBe(`${MODULE_API_PREFIX}/calendar/`);
    expect(ENDPOINTS.REMEDIATIONS.LIST).toBe(`${MODULE_API_PREFIX}/remediations/`);
    expect(ENDPOINTS.DASHBOARD).toBe(`${MODULE_API_PREFIX}/dashboard/`);
    expect(ENDPOINTS.HEATMAP).toBe(`${MODULE_API_PREFIX}/heatmap/`);
    expect(ENDPOINTS.CONFIGURATION.ROLLBACK).toBe(`${MODULE_API_PREFIX}/configuration/rollback/`);
    expect(ENDPOINTS.HEALTH.READY).toBe(`${MODULE_API_PREFIX}/health/ready/`);
  });

  it('encodes identifiers and emits exact nested resource paths', () => {
    expect(ENDPOINTS.RISKS.DETAIL('risk id')).toBe(`${MODULE_API_PREFIX}/risks/risk%20id/`);
    expect(ENDPOINTS.RISKS.CONTROLS('risk id')).toBe(`${MODULE_API_PREFIX}/risks/risk%20id/controls/`);
    expect(ENDPOINTS.CONTROLS.TESTS('control/id')).toBe(`${MODULE_API_PREFIX}/controls/control%2Fid/tests/`);
  });
});
