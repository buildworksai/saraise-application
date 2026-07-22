import { describe, expect, it } from "vitest";
import { ENDPOINTS, MODULE_API_PREFIX, ROUTES } from "../contracts";

describe("master data contracts", () => {
  it("publishes only governed v2 endpoints", () => {
    expect(MODULE_API_PREFIX).toBe("/api/v2/master-data-management");
    expect(JSON.stringify(ENDPOINTS)).not.toContain("/api/v1/");
    expect(ENDPOINTS.ENTITIES.VERSION("entity", 4)).toBe("/api/v2/master-data-management/entities/entity/versions/4/");
    expect(ENDPOINTS.MERGES.REVERSE("merge")).toBe("/api/v2/master-data-management/merges/merge/reverse/");
  });

  it("builds every parameterized application path", () => {
    expect(ROUTES.ENTITY_TYPE_EDIT("type")).toBe("/master-data/entity-types/type/edit");
    expect(ROUTES.ENTITY_VERSION("entity", 2)).toBe("/master-data/entities/entity/versions/2");
    expect(ROUTES.QUALITY_ISSUE_DETAIL("issue")).toBe("/master-data/quality/issues/issue");
    expect(ROUTES.MATCH_DETAIL("match")).toBe("/master-data/matches/match");
    expect(ROUTES.JOB_DETAIL("job")).toBe("/master-data/jobs/job");
  });
});
