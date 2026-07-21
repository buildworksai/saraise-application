import { describe, expect, it } from "vitest";
import { ENDPOINTS, QUERY_KEYS, isAccessDecision, isFieldSecurity, isRowPredicate, isVisibility } from "./contracts";

describe("security contracts", () => {
  it("uses only governed v2 endpoints", () => { expect(JSON.stringify(ENDPOINTS)).not.toContain("/api/v1/"); expect(ENDPOINTS.ROLES.DETAIL("r1")).toBe("/api/v2/security-access-control/roles/r1/"); expect(ENDPOINTS.PERMISSION_SETS.PERMISSIONS("s1")).toContain("/permissions/"); expect(ENDPOINTS.ACCESS_DECISIONS.SIMULATE).toContain("access-decisions/simulate"); });
  it("accepts redacted visibility and rejects unknown states", () => { expect(isVisibility("redacted")).toBe(true); expect(isVisibility("obscured")).toBe(false); expect(isFieldSecurity({ id: "f", module: "crm", resource: "contact", field: "email", role_id: "r", visibility: "redacted", edit_control: "read_only" })).toBe(true); });
  it("validates bounded safe predicate AST nodes", () => { expect(isRowPredicate({ op: "and", args: [{ op: "tenant", field: "tenant_id" }, { op: "owner", field: "owner_id" }] })).toBe(true); expect(isRowPredicate({ op: "raw_sql", value: "1=1" })).toBe(false); expect(isRowPredicate({ op: "and", args: [] })).toBe(false); });
  it("rejects incomplete access decisions", () => { expect(isAccessDecision({ decision: "allow" })).toBe(false); });
  it("scopes query keys by normalized filters", () => { expect(QUERY_KEYS.roles({ search: "admin", page: 2 })).toEqual(QUERY_KEYS.roles({ page: 2, search: "admin" })); expect(QUERY_KEYS.role("role-1")).not.toEqual(QUERY_KEYS.role("role-2")); });
});
