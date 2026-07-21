import { ENDPOINTS, MODULE_API_PREFIX, ROUTE_PATHS, type ComplianceResult, type VerificationOutcome } from './contracts';

describe('blockchain traceability v2 contracts', () => {
  it('constructs every governed API family from the v2 prefix', () => {
    expect(MODULE_API_PREFIX).toBe('/api/v2/blockchain-traceability');
    expect(ENDPOINTS.NETWORKS.ACTIVATE('network-1')).toBe('/api/v2/blockchain-traceability/networks/network-1/activate/');
    expect(ENDPOINTS.ASSETS.VERIFY_CHAIN('asset-1')).toBe('/api/v2/blockchain-traceability/assets/asset-1/verify-chain/');
    expect(ENDPOINTS.ANCHORS.RETRY('anchor-1')).toBe('/api/v2/blockchain-traceability/anchors/anchor-1/retry/');
    expect(ENDPOINTS.CREDENTIALS.VERIFY).toBe('/api/v2/blockchain-traceability/credentials/verify/');
    expect(ENDPOINTS.COMPLIANCE_EVIDENCE.SUPERSEDE('evidence-1')).toContain('/compliance-evidence/evidence-1/supersede/');
  });

  it('publishes typed contextual path helpers and exact literals', () => {
    const outcome: VerificationOutcome = 'dependency_unavailable';
    const result: ComplianceResult = 'not_applicable';
    expect([outcome, result]).toEqual(['dependency_unavailable', 'not_applicable']);
    expect(ROUTE_PATHS.ASSET_DETAIL('asset-1')).toBe('/blockchain-traceability/assets/asset-1');
    expect(ROUTE_PATHS.ATTEMPT_DETAIL('attempt-1')).toBe('/blockchain-traceability/verification-attempts/attempt-1');
  });
});
