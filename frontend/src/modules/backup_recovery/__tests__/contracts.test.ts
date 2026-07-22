import { describe, expect, it } from "vitest";
import { ENDPOINTS, MODULE_API_PREFIX } from "../contracts";

describe("backup recovery v2 endpoint contract", () => {
  it("publishes the canonical prefix and every public endpoint", () => {
    expect(MODULE_API_PREFIX).toBe("/api/v2/backup-recovery");
    expect(ENDPOINTS).toMatchObject({
      JOBS: { LIST: `${MODULE_API_PREFIX}/jobs/`, CREATE: `${MODULE_API_PREFIX}/jobs/` },
      SCHEDULES: { LIST: `${MODULE_API_PREFIX}/schedules/` },
      RETENTION_POLICIES: { LIST: `${MODULE_API_PREFIX}/retention-policies/` },
      STORAGE_TARGETS: { LIST: `${MODULE_API_PREFIX}/storage-targets/` },
      ARCHIVES: { LIST: `${MODULE_API_PREFIX}/archives/` },
      VERIFICATIONS: { LIST: `${MODULE_API_PREFIX}/verifications/` },
      HEALTH: `${MODULE_API_PREFIX}/health/`,
    });
    expect(ENDPOINTS.JOBS.CANCEL("job-id")).toBe(`${MODULE_API_PREFIX}/jobs/job-id/cancel/`);
    expect(ENDPOINTS.JOBS.RETRY("job-id")).toBe(`${MODULE_API_PREFIX}/jobs/job-id/retry/`);
    expect(ENDPOINTS.SCHEDULES.RUN_NOW("schedule-id")).toBe(
      `${MODULE_API_PREFIX}/schedules/schedule-id/run-now/`
    );
    expect(ENDPOINTS.RETENTION_POLICIES.PREVIEW("policy-id")).toBe(
      `${MODULE_API_PREFIX}/retention-policies/policy-id/preview/`
    );
    expect(ENDPOINTS.STORAGE_TARGETS.SET_DEFAULT("target-id")).toBe(
      `${MODULE_API_PREFIX}/storage-targets/target-id/set-default/`
    );
    expect(ENDPOINTS.STORAGE_TARGETS.PROBE("target-id")).toBe(
      `${MODULE_API_PREFIX}/storage-targets/target-id/probe/`
    );
    expect(ENDPOINTS.ARCHIVES.VERIFY("archive-id")).toBe(
      `${MODULE_API_PREFIX}/archives/archive-id/verify/`
    );
    expect(ENDPOINTS.VERIFICATIONS.CANCEL("verification-id")).toBe(
      `${MODULE_API_PREFIX}/verifications/verification-id/cancel/`
    );
  });

  it("does not publish worker-only completion, failure, expiry, or purge actions", () => {
    const serialized = JSON.stringify(ENDPOINTS);
    expect(serialized).not.toContain("/complete/");
    expect(serialized).not.toContain("/fail/");
    expect(serialized).not.toContain("/expire/");
    expect(serialized).not.toContain("/purge");
    expect(serialized).not.toContain("/start/");
  });
});
