import { describe, expect, it } from 'vitest';
import { ENDPOINTS, MODULE_API_PREFIX } from './contracts';

describe('multi-company governed contract', () => {
  it('uses v2 exclusively and safely encodes dynamic resources', () => {
    expect(MODULE_API_PREFIX).toBe('/api/v2/multi-company');
    expect(ENDPOINTS.COMPANIES.DETAIL('a/b')).toBe('/api/v2/multi-company/companies/a%2Fb/');
    expect(ENDPOINTS.CONSOLIDATIONS.ELIMINATIONS('run')).toBe('/api/v2/multi-company/consolidation-runs/run/eliminations/');
    expect(JSON.stringify(ENDPOINTS)).not.toContain('/api/v1');
  });

  it('declares all governed resource roots', () => {
    expect(ENDPOINTS.COMPANIES.LIST).toContain('/companies/');
    expect(ENDPOINTS.COMPANY_ACCESS.LIST).toContain('/company-access/');
    expect(ENDPOINTS.TRANSACTIONS.LIST).toContain('/transactions/');
    expect(ENDPOINTS.RECONCILIATION).toContain('/reconciliation/');
    expect(ENDPOINTS.CONSOLIDATIONS.LIST).toContain('/consolidation-runs/');
    expect(ENDPOINTS.TRANSFER_PRICING_RULES.LIST).toContain('/transfer-pricing-rules/');
    expect(ENDPOINTS.CONFIGURATION.LIST).toContain('/configuration/versions/');
    expect(ENDPOINTS.HEALTH).toContain('/health/');
  });
});
