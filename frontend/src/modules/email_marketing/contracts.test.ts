import { describe, expect, it } from 'vitest';
import { ENDPOINTS, MODULE_API_PREFIX, ROUTES, isApiV2Envelope, isApiV2Page, isPaginationMeta } from './contracts';
describe('email marketing contracts', () => {
  const pagination = { count: 0, page: 1, page_size: 25, total_pages: 0, has_next: false, has_previous: false };
  it('publishes only the canonical v2 endpoint prefix', () => { expect(MODULE_API_PREFIX).toBe('/api/v2/email-marketing'); expect(JSON.stringify(ENDPOINTS)).not.toContain('/api/v1/'); expect(ENDPOINTS.CAMPAIGNS.SEND('campaign')).toBe('/api/v2/email-marketing/campaigns/campaign/send/'); expect(ENDPOINTS.TRACK_OPEN('a/b')).toContain('a%2Fb'); });
  it('builds every contextual route', () => { expect(ROUTES.CAMPAIGN_EDIT('id')).toBe('/email-marketing/campaigns/id/edit'); expect(ROUTES.DELIVERY_DETAIL('id')).toBe('/email-marketing/delivery/attempts/id'); expect(ROUTES.CONSENT_DETAIL('id')).toBe('/email-marketing/consents/id'); });
  it('rejects legacy and malformed envelopes', () => { expect(isApiV2Envelope([])).toBe(false); expect(isApiV2Page({ results: [] })).toBe(false); expect(isPaginationMeta({ ...pagination, page_size: '25' })).toBe(false); expect(isApiV2Page({ data: [], meta: { correlation_id: 'corr', timestamp: '2026-07-22T00:00:00Z', pagination } })).toBe(true); });
});
