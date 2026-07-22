import { describe, expect, it } from "vitest";
import { ENDPOINTS, MODULE_API_PREFIX, QUERY_KEYS, ROUTES } from "./contracts";

describe("bank reconciliation v2 contract", () => {
  it("constructs governed endpoints without v1 paths", () => {
    expect(MODULE_API_PREFIX).toBe("/api/v2/bank-reconciliation");
    expect(ENDPOINTS.ACCOUNTS.DETAIL("account-id")).toBe(
      "/api/v2/bank-reconciliation/accounts/account-id/"
    );
    expect(ENDPOINTS.RECONCILIATIONS.GENERATE_CANDIDATES("session-id")).toBe(
      "/api/v2/bank-reconciliation/reconciliations/session-id/generate-candidates/"
    );
    expect(MODULE_API_PREFIX).toContain("/api/v2/");
  });

  it("scopes query keys by filters and application routes by ID", () => {
    expect(QUERY_KEYS.accounts.list({ page: 2 })).not.toEqual(
      QUERY_KEYS.accounts.list({ page: 1 })
    );
    expect(ROUTES.RECONCILIATION_WORKSPACE("session-id")).toBe(
      "/bank-reconciliation/reconciliations/session-id/workspace"
    );
  });
});
