import { describe, expect, it } from "vitest";
import { ENDPOINTS, MODULE_API_PREFIX } from "../../contracts";

describe("automation orchestration contracts", () => {
  it("publishes only the governed v2 module prefix", () => {
    expect(MODULE_API_PREFIX).toBe("/api/v2/automation-orchestration");
    expect(JSON.stringify(ENDPOINTS)).not.toContain("/api/v1/");
    expect(JSON.stringify(ENDPOINTS)).not.toContain("resources");
  });

  it("builds every nested lifecycle path", () => {
    expect(ENDPOINTS.DEFINITIONS.VALIDATE("definition-id")).toBe(
      "/api/v2/automation-orchestration/definitions/definition-id/validate/",
    );
    expect(ENDPOINTS.DEFINITIONS.SNAPSHOT("definition-id")).toContain("/snapshot/");
    expect(ENDPOINTS.SCHEDULES.RETIRE("schedule-id")).toContain("/retire/");
    expect(ENDPOINTS.RUNS.TASK_RUNS("run-id")).toContain("/task-runs/");
    expect(ENDPOINTS.TASK_RUNS.RETRY("task-id")).toContain("/retry/");
  });
});
