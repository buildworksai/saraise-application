import { describe, expect, it } from 'vitest';
import { ENDPOINTS, MODULE_API_PREFIX, ROUTES } from '../contracts';

describe('compliance contracts', () => {
  it('uses only the governed v2 module prefix', () => {
    expect(MODULE_API_PREFIX).toBe('/api/v2/compliance-management');
    expect(ENDPOINTS.FRAMEWORKS.LIST).toBe(`${MODULE_API_PREFIX}/frameworks/`);
    expect(ENDPOINTS.POLICIES.PUBLISH('policy-1')).toBe(`${MODULE_API_PREFIX}/policies/policy-1/publish/`);
    expect(ENDPOINTS.CONFIGURATION.ROLLBACK('revision-1')).toBe(`${MODULE_API_PREFIX}/configuration/revision-1/rollback/`);
    expect(ENDPOINTS.EVIDENCE_LINKS.DELETE('link-1')).toBe(`${MODULE_API_PREFIX}/evidence-links/link-1/`);
  });

  it('publishes every user journey route without tenant identifiers', () => {
    expect(ROUTES.DASHBOARD).toBe('/compliance-management');
    expect(ROUTES.FRAMEWORK_EDIT('framework-1')).toContain('framework-1/edit');
    expect(ROUTES.REQUIREMENT_DETAIL('requirement-1')).toContain('requirement-1');
    expect(ROUTES.POLICY_EDIT('policy-1')).toContain('policy-1/edit');
    expect(ROUTES.EVIDENCE_EDIT('evidence-1')).toContain('evidence-1/edit');
    expect(JSON.stringify(ROUTES)).not.toContain('tenant');
  });
});
