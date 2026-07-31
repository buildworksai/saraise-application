/* eslint-disable max-lines-per-function -- table-driven endpoint and route helper matrices intentionally pin the governed contract surface. */
import { describe, expect, it } from "vitest";
import { ENDPOINTS, ROUTES, isExecutionState, withQuery } from "./contracts";

describe("ai agent v2 contracts", () => {
  it("declares every API under the governed v2 root", () => {
    expect(ENDPOINTS.AGENTS.LIST).toBe("/api/v2/ai-agent-management/agents/");
    expect(ENDPOINTS.AGENTS.CREATE).toBe("/api/v2/ai-agent-management/agents/");
    expect(ENDPOINTS.AGENTS.DETAIL("agent one")).toBe(
      "/api/v2/ai-agent-management/agents/agent%20one/"
    );
    expect(ENDPOINTS.EXECUTIONS.PAUSE("execution/one")).toBe(
      "/api/v2/ai-agent-management/executions/execution%2Fone/pause/"
    );
    expect(ENDPOINTS.SCHEDULES.CANCEL("schedule-1")).toBe(
      "/api/v2/ai-agent-management/schedules/schedule-1/cancel/"
    );
    expect(ENDPOINTS.HEALTH).toBe("/api/v2/ai-agent-management/health/");
  });

  it("encodes allowlisted typed query values and omits empty fields", () => {
    expect(
      withQuery(ENDPOINTS.AGENTS.LIST, {
        search: "close & post",
        status: "active",
        page: 2,
        runner_key: undefined,
      })
    ).toBe("/api/v2/ai-agent-management/agents/?search=close+%26+post&status=active&page=2");
  });

  it("recognizes only governed execution states", () => {
    const validStates = [
      "created",
      "validated",
      "queued",
      "running",
      "paused",
      "completed",
      "failed",
      "terminated",
      "timed_out",
    ] as const;
    const invalidStates = [
      "cancelled",
      "pending",
      "",
      null,
      undefined,
      3,
      { state: "running" },
    ] as const;

    for (const state of validStates) expect(isExecutionState(state)).toBe(true);
    for (const state of invalidStates) expect(isExecutionState(state)).toBe(false);
  });

  it("table-drives governed endpoint actions with encoded identifiers", () => {
    const id = "record/one";
    const cases = [
      [ENDPOINTS.AGENTS.DETAIL(id), "/api/v2/ai-agent-management/agents/record%2Fone/"],
      [ENDPOINTS.AGENTS.UPDATE(id), "/api/v2/ai-agent-management/agents/record%2Fone/"],
      [ENDPOINTS.AGENTS.DELETE(id), "/api/v2/ai-agent-management/agents/record%2Fone/"],
      [ENDPOINTS.AGENTS.ACTIVATE(id), "/api/v2/ai-agent-management/agents/record%2Fone/activate/"],
      [ENDPOINTS.AGENTS.DISABLE(id), "/api/v2/ai-agent-management/agents/record%2Fone/disable/"],
      [ENDPOINTS.AGENTS.RETIRE(id), "/api/v2/ai-agent-management/agents/record%2Fone/retire/"],
      [ENDPOINTS.AGENTS.EXECUTE(id), "/api/v2/ai-agent-management/agents/record%2Fone/execute/"],
      [ENDPOINTS.AGENTS.EVALUATE(id), "/api/v2/ai-agent-management/agents/record%2Fone/evaluate/"],
      [ENDPOINTS.EXECUTIONS.DETAIL(id), "/api/v2/ai-agent-management/executions/record%2Fone/"],
      [
        ENDPOINTS.EXECUTIONS.RESUME(id),
        "/api/v2/ai-agent-management/executions/record%2Fone/resume/",
      ],
      [
        ENDPOINTS.EXECUTIONS.TERMINATE(id),
        "/api/v2/ai-agent-management/executions/record%2Fone/terminate/",
      ],
      [ENDPOINTS.SCHEDULES.DETAIL(id), "/api/v2/ai-agent-management/schedules/record%2Fone/"],
      [ENDPOINTS.APPROVALS.DETAIL(id), "/api/v2/ai-agent-management/approvals/record%2Fone/"],
      [
        ENDPOINTS.APPROVALS.APPROVE(id),
        "/api/v2/ai-agent-management/approvals/record%2Fone/approve/",
      ],
      [
        ENDPOINTS.APPROVALS.REJECT(id),
        "/api/v2/ai-agent-management/approvals/record%2Fone/reject/",
      ],
      [
        ENDPOINTS.APPROVALS.CANCEL(id),
        "/api/v2/ai-agent-management/approvals/record%2Fone/cancel/",
      ],
      [ENDPOINTS.SOD_POLICIES.DETAIL(id), "/api/v2/ai-agent-management/sod-policies/record%2Fone/"],
      [
        ENDPOINTS.SOD_VIOLATIONS.DETAIL(id),
        "/api/v2/ai-agent-management/sod-violations/record%2Fone/",
      ],
      [ENDPOINTS.TOOLS.DETAIL(id), "/api/v2/ai-agent-management/tools/record%2Fone/"],
      [ENDPOINTS.TOOLS.VALIDATE(id), "/api/v2/ai-agent-management/tools/record%2Fone/validate/"],
      [
        ENDPOINTS.TOOL_INVOCATIONS.DETAIL(id),
        "/api/v2/ai-agent-management/tool-invocations/record%2Fone/",
      ],
      [ENDPOINTS.EGRESS_RULES.DETAIL(id), "/api/v2/ai-agent-management/egress-rules/record%2Fone/"],
      [
        ENDPOINTS.EGRESS_REQUESTS.DETAIL(id),
        "/api/v2/ai-agent-management/egress-requests/record%2Fone/",
      ],
      [ENDPOINTS.SECRETS.DETAIL(id), "/api/v2/ai-agent-management/secrets/record%2Fone/"],
      [ENDPOINTS.SECRETS.ROTATE(id), "/api/v2/ai-agent-management/secrets/record%2Fone/rotate/"],
      [
        ENDPOINTS.SECRETS.DEACTIVATE(id),
        "/api/v2/ai-agent-management/secrets/record%2Fone/deactivate/",
      ],
      [
        ENDPOINTS.SECRET_ACCESSES.DETAIL(id),
        "/api/v2/ai-agent-management/secret-accesses/record%2Fone/",
      ],
      [ENDPOINTS.QUOTAS.DETAIL(id), "/api/v2/ai-agent-management/quotas/record%2Fone/"],
      [ENDPOINTS.QUOTA_USAGE.DETAIL(id), "/api/v2/ai-agent-management/quota-usage/record%2Fone/"],
      [ENDPOINTS.SATURATION.DETAIL(id), "/api/v2/ai-agent-management/saturation/record%2Fone/"],
      [
        ENDPOINTS.KILL_SWITCHES.DETAIL(id),
        "/api/v2/ai-agent-management/kill-switches/record%2Fone/",
      ],
      [
        ENDPOINTS.KILL_SWITCHES.DEACTIVATE(id),
        "/api/v2/ai-agent-management/kill-switches/record%2Fone/deactivate/",
      ],
      [ENDPOINTS.TOKEN_USAGE.DETAIL(id), "/api/v2/ai-agent-management/token-usage/record%2Fone/"],
      [ENDPOINTS.COST_RECORDS.DETAIL(id), "/api/v2/ai-agent-management/cost-records/record%2Fone/"],
      [
        ENDPOINTS.COST_SUMMARIES.DETAIL(id),
        "/api/v2/ai-agent-management/cost-summaries/record%2Fone/",
      ],
      [
        ENDPOINTS.COST_SUMMARIES.RECALCULATE,
        "/api/v2/ai-agent-management/cost-summaries/recalculate/",
      ],
      [ENDPOINTS.AUDIT_EVENTS.DETAIL(id), "/api/v2/ai-agent-management/audit-events/record%2Fone/"],
      [ENDPOINTS.AUDIT_TRAILS.DETAIL(id), "/api/v2/ai-agent-management/audit-trails/record%2Fone/"],
      [ENDPOINTS.JOBS.DETAIL(id), "/api/v2/ai-agent-management/jobs/record%2Fone/"],
      [ENDPOINTS.CONFIGURATION.PREVIEW, "/api/v2/ai-agent-management/configuration/preview/"],
      [ENDPOINTS.CONFIGURATION.ROLLBACK, "/api/v2/ai-agent-management/configuration/rollback/"],
    ] as const;

    for (const [actual, expected] of cases) {
      expect(actual).toBe(expected);
      expect(actual).not.toContain("/api/v1/");
    }
  });

  it("table-drives route helpers without encoding path parameters", () => {
    const cases = [
      [ROUTES.AGENTS, "/ai-agents"],
      [ROUTES.AGENT_CREATE, "/ai-agents/create"],
      [ROUTES.AGENT_DETAIL(":id"), "/ai-agents/:id"],
      [ROUTES.AGENT_EDIT(":id"), "/ai-agents/:id/edit"],
      [ROUTES.EXECUTIONS, "/ai-agents/executions"],
      [ROUTES.EXECUTION_DETAIL(":id"), "/ai-agents/executions/:id"],
      [ROUTES.SCHEDULES, "/ai-agents/schedules"],
      [ROUTES.SCHEDULE_CREATE, "/ai-agents/schedules/create"],
      [ROUTES.SCHEDULE_DETAIL(":id"), "/ai-agents/schedules/:id"],
      [ROUTES.APPROVALS, "/ai-agents/approvals"],
      [ROUTES.APPROVAL_DETAIL(":id"), "/ai-agents/approvals/:id"],
      [ROUTES.TOOLS, "/ai-agents/tools"],
      [ROUTES.TOOL_CREATE, "/ai-agents/tools/create"],
      [ROUTES.TOOL_DETAIL(":id"), "/ai-agents/tools/:id"],
      [ROUTES.TOOL_EDIT(":id"), "/ai-agents/tools/:id/edit"],
      [ROUTES.CONFIGURATION, "/ai-agents/configuration"],
      [ROUTES.GOVERNANCE, "/ai-agents/governance"],
      [ROUTES.USAGE, "/ai-agents/usage"],
      [ROUTES.AUDIT, "/ai-agents/audit"],
      [ROUTES.AUDIT_TRAIL_DETAIL(":id"), "/ai-agents/audit/:id"],
      [ROUTES.EVALUATION(":id"), "/ai-agents/:id/evaluation"],
    ] as const;

    for (const [actual, expected] of cases) expect(actual).toBe(expected);
  });

  it("omits null, undefined, and empty query values but preserves false and zero", () => {
    expect(
      withQuery(ENDPOINTS.TOOLS.LIST, {
        is_active: false,
        page: 0,
        search: "",
        owner: null,
        ordering: undefined,
      })
    ).toBe("/api/v2/ai-agent-management/tools/?is_active=false&page=0");
  });
});
