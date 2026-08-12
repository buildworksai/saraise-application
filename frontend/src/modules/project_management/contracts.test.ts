import { describe, expect, it } from "vitest";
import { ENDPOINTS, MODULE_API_PREFIX } from "./contracts";

describe("project management contracts", () => {
  it("keeps governed endpoint builders rooted under the v2 module prefix", () => {
    expect(MODULE_API_PREFIX).toBe("/api/v2/project-management");
    expect(ENDPOINTS.PROJECTS.LIST).toBe("/api/v2/project-management/projects/");
    expect(ENDPOINTS.PROJECTS.SUMMARY("project/1")).toBe(
      "/api/v2/project-management/projects/project/1/summary/"
    );
    expect(ENDPOINTS.TASKS.REORDER("task-1")).toBe(
      "/api/v2/project-management/tasks/task-1/reorder/"
    );
    expect(ENDPOINTS.MILESTONES.REOPEN("milestone-1")).toBe(
      "/api/v2/project-management/milestones/milestone-1/reopen/"
    );
    expect(ENDPOINTS.CONFIGURATION.VERSION("version-4")).toBe(
      "/api/v2/project-management/configuration/versions/version-4/"
    );
    expect(ENDPOINTS.HEALTH).toBe("/api/v2/project-management/health/");
    expect(ENDPOINTS.MY_WORK).toBe("/api/v2/project-management/my-work/");
  });
});
