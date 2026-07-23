import { describe, expect, it } from 'vitest';

import { ENDPOINTS, MODULE_API_PREFIX, ROUTES } from './contracts';

describe('purchase-management contracts', () => {
  it('publishes one governed v2 API authority', () => {
    expect(MODULE_API_PREFIX).toBe('/api/v2/purchase-management');
    expect(ENDPOINTS.SUPPLIERS.LIST).toBe(`${MODULE_API_PREFIX}/suppliers/`);
    expect(ENDPOINTS.REQUISITIONS.SUBMIT('pr-1')).toBe(
      `${MODULE_API_PREFIX}/requisitions/pr-1/submit/`,
    );
    expect(ENDPOINTS.RFQS.COMPARE('rfq-1')).toBe(`${MODULE_API_PREFIX}/rfqs/rfq-1/compare-quotes/`);
    expect(ENDPOINTS.PURCHASE_ORDERS.DISPATCH('po-1')).toBe(
      `${MODULE_API_PREFIX}/purchase-orders/po-1/dispatch/`,
    );
    expect(ENDPOINTS.CONFIGURATIONS.ROLLBACK('version-1')).toBe(
      `${MODULE_API_PREFIX}/configurations/versions/version-1/rollback/`,
    );
  });

  it('keeps contextual URLs owned by the module contract', () => {
    expect(ROUTES.SUPPLIERS.EDIT('supplier-1')).toBe('/purchase-management/suppliers/supplier-1/edit');
    expect(ROUTES.CONFIGURATION_VERSION('version-1')).toBe(
      '/purchase-management/settings/versions/version-1',
    );
  });
});
