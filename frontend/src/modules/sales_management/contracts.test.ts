import { describe, expect, it } from 'vitest';
import { ENDPOINTS, MODULE_API_PREFIX } from './contracts';

describe('sales management API contract', () => {
  it('uses only the governed v2 prefix', () => expect(MODULE_API_PREFIX).toBe('/api/v2/sales-management'));
  it('encodes every dynamic path segment', () => {
    expect(ENDPOINTS.CUSTOMERS.DETAIL('tenant/id ?')).toBe('/api/v2/sales-management/customers/tenant%2Fid%20%3F/');
    expect(ENDPOINTS.QUOTATIONS.COMMAND('quote/id', 'convert')).toBe('/api/v2/sales-management/quotations/quote%2Fid/commands/convert/');
    expect(ENDPOINTS.CONFIGURATION.VERSION(7)).toBe('/api/v2/sales-management/configuration/versions/7/');
  });
});
