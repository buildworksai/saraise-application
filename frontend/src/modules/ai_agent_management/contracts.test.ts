import { describe, expect, it } from "vitest";
import { ENDPOINTS, withQuery } from "./contracts";

describe("ai agent v2 contracts", () => {
  it("declares every API under the governed v2 root", () => {
    expect(ENDPOINTS.AGENTS.LIST).toBe("/api/v2/ai-agent-management/agents/");
    expect(ENDPOINTS.EXECUTIONS.PAUSE("execution/one")).toBe("/api/v2/ai-agent-management/executions/execution%2Fone/pause/");
    expect(ENDPOINTS.SCHEDULES.CANCEL("schedule-1")).toBe("/api/v2/ai-agent-management/schedules/schedule-1/cancel/");
    expect(ENDPOINTS.HEALTH).toBe("/api/v2/ai-agent-management/health/");
  });

  it("encodes allowlisted typed query values and omits empty fields", () => {
    expect(withQuery(ENDPOINTS.AGENTS.LIST, { search: "close & post", status: "active", page: 2, runner_key: undefined })).toBe("/api/v2/ai-agent-management/agents/?search=close+%26+post&status=active&page=2");
  });
});
