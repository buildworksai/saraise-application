import { ENDPOINTS, MODULE_API_PREFIX, isLead, isV2Envelope, isV2PageEnvelope } from '../contracts';

describe('CRM v2 contracts', () => {
  it('owns every governed endpoint under the v2 prefix', () => {
    expect(MODULE_API_PREFIX).toBe('/api/v2/crm');
    expect(ENDPOINTS.LEADS.TRANSITION('lead-1')).toBe('/api/v2/crm/leads/lead-1/transition/');
    expect(ENDPOINTS.ACCOUNTS.DUPLICATES).toBe('/api/v2/crm/accounts/duplicates/');
    expect(ENDPOINTS.OPPORTUNITIES.TRANSITION('opp-1')).toContain('/opportunities/opp-1/transition/');
    expect(ENDPOINTS.FORECASTING.BY_STAGE).toContain('/forecasting/by-stage/');
    expect(ENDPOINTS.FORECASTING.PREDICT).toContain('/forecasting/predict/');
    expect(ENDPOINTS.JOBS.DETAIL('job-1')).toContain('/jobs/job-1/');
  });

  it('rejects malformed envelopes and shallow entity lookalikes', () => {
    expect(isV2Envelope({ data: {}, meta: { correlation_id: 'req-1', timestamp: '2026-01-01T00:00:00Z' } })).toBe(true);
    expect(isV2Envelope({ data: {} })).toBe(false);
    expect(isV2PageEnvelope({ data: [], meta: { correlation_id: 'req-1', timestamp: '2026-01-01T00:00:00Z', pagination: { count: 0 } } })).toBe(true);
    expect(isLead({ id: 'lead-1', last_name: 'Ada', score: 80 })).toBe(false);
  });
});
