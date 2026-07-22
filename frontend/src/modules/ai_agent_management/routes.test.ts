import { describe, expect, it } from "vitest";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "./routes";

describe("ai agent module routes", () => {
  it("publishes exactly the required discoverable areas", () => {
    const labels = tenantRoutes.flatMap((route) => route.navigation.type === "sidebar" ? [route.navigation.label] : []);
    expect(labels).toEqual(["Agents", "Executions", "Approvals", "Governance", "Usage", "Audit"]);
    expect(tenantRoutes.every((route) => route.module === "ai_agent_management")).toBe(true);
  });

  it("has unique paths and valid contextual parents", () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
  });

  it("registers all required contextual workflows", () => {
    const paths = tenantRoutes.map((route) => route.path);
    expect(paths).toEqual(expect.arrayContaining([
      "/ai-agents/create", "/ai-agents/:id", "/ai-agents/:id/edit", "/ai-agents/:id/evaluation",
      "/ai-agents/executions/:id", "/ai-agents/schedules", "/ai-agents/schedules/create", "/ai-agents/schedules/:id",
      "/ai-agents/approvals/:id", "/ai-agents/tools", "/ai-agents/tools/create", "/ai-agents/tools/:id", "/ai-agents/tools/:id/edit", "/ai-agents/audit/:id",
    ]));
  });
});
