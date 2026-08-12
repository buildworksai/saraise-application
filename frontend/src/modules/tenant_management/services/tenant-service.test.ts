/* eslint-disable @typescript-eslint/unbound-method -- apiClient.get is a Vitest mock in this file. */
/* eslint-disable max-lines-per-function -- mutation contract matrix is intentionally colocated for this generated service. */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/services/api-client";
import { tenantService } from "./tenant-service";

vi.mock("@/services/api-client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

const mockedGet = vi.mocked(apiClient.get);

async function expectListCall(
  action: () => Promise<unknown[]>,
  expectedUrl: string,
  response: unknown[] | null | undefined = [{ id: "record-1" }]
) {
  mockedGet.mockResolvedValueOnce(response);

  const result = await action();

  expect(result).toEqual(response ?? []);
  expect(mockedGet).toHaveBeenCalledTimes(1);
  expect(mockedGet).toHaveBeenCalledWith(expectedUrl);
}

async function expectDetailCall(
  action: () => Promise<unknown>,
  expectedUrl: string,
  response: unknown
) {
  mockedGet.mockResolvedValueOnce(response);

  const result = await action();

  expect(result).toEqual(response);
  expect(mockedGet).toHaveBeenCalledTimes(1);
  expect(mockedGet).toHaveBeenCalledWith(expectedUrl);
}

describe("tenantService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("exposes every tenant management service group", () => {
    expect(Object.keys(tenantService).sort()).toEqual([
      "healthScores",
      "modules",
      "resourceUsage",
      "settings",
      "tenants",
    ]);
    expect(Object.keys(tenantService.tenants).sort()).toEqual([
      "get",
      "getHealthScores",
      "getModules",
      "getResourceUsage",
      "list",
    ]);
    expect(Object.keys(tenantService.modules).sort()).toEqual(["get", "list"]);
    expect(Object.keys(tenantService.resourceUsage).sort()).toEqual(["get", "list"]);
    expect(Object.keys(tenantService.settings).sort()).toEqual(["get", "list"]);
    expect(Object.keys(tenantService.healthScores).sort()).toEqual(["get", "list"]);
  });

  it("lists tenants without query parameters and falls back to an empty list", async () => {
    await expectListCall(
      () => tenantService.tenants.list(),
      "/api/v1/tenant-management/tenants/",
      null
    );
  });

  it("lists tenants with status, subscription plan, and search filters", async () => {
    await expectListCall(
      () =>
        tenantService.tenants.list({
          status: "active",
          subscription_plan_id: "plan-enterprise",
          search: "north region",
        }),
      "/api/v1/tenant-management/tenants/?status=active&subscription_plan_id=plan-enterprise&search=north+region"
    );
  });

  it("gets one tenant by id", async () => {
    await expectDetailCall(
      () => tenantService.tenants.get("tenant-1"),
      "/api/v1/tenant-management/tenants/tenant-1/",
      { id: "tenant-1", name: "North Region" }
    );
  });

  it("gets tenant modules with an empty-list fallback", async () => {
    await expectListCall(
      () => tenantService.tenants.getModules("tenant-1"),
      "/api/v1/tenant-management/tenants/tenant-1/modules/",
      []
    );
  });

  it("gets tenant modules from a null response as an empty list", async () => {
    await expectListCall(
      () => tenantService.tenants.getModules("tenant-1"),
      "/api/v1/tenant-management/tenants/tenant-1/modules/",
      null
    );
  });

  it("gets tenant resource usage without date bounds", async () => {
    await expectListCall(
      () => tenantService.tenants.getResourceUsage("tenant-1"),
      "/api/v1/tenant-management/tenants/tenant-1/resource_usage/",
      undefined
    );
  });

  it("gets tenant resource usage with date bounds", async () => {
    await expectListCall(
      () =>
        tenantService.tenants.getResourceUsage("tenant-1", {
          date_from: "2026-01-01",
          date_to: "2026-01-31",
        }),
      "/api/v1/tenant-management/tenants/tenant-1/resource_usage/?date_from=2026-01-01&date_to=2026-01-31"
    );
  });

  it("gets tenant health scores with date bounds", async () => {
    await expectListCall(
      () =>
        tenantService.tenants.getHealthScores("tenant-1", {
          date_from: "2026-02-01",
          date_to: "2026-02-28",
        }),
      "/api/v1/tenant-management/tenants/tenant-1/health_scores/?date_from=2026-02-01&date_to=2026-02-28"
    );
  });

  it("gets tenant health scores without date bounds", async () => {
    await expectListCall(
      () => tenantService.tenants.getHealthScores("tenant-1"),
      "/api/v1/tenant-management/tenants/tenant-1/health_scores/",
      null
    );
  });

  it("lists modules without filters", async () => {
    await expectListCall(
      () => tenantService.modules.list(),
      "/api/v1/tenant-management/modules/",
      null
    );
  });

  it("lists modules with all filters and preserves a false enabled filter", async () => {
    await expectListCall(
      () =>
        tenantService.modules.list({
          tenant_id: "tenant-1",
          module_name: "inventory",
          is_enabled: false,
        }),
      "/api/v1/tenant-management/modules/?tenant_id=tenant-1&module_name=inventory&is_enabled=false"
    );
  });

  it("lists modules with true enabled filter", async () => {
    await expectListCall(
      () => tenantService.modules.list({ is_enabled: true }),
      "/api/v1/tenant-management/modules/?is_enabled=true"
    );
  });

  it("gets one module by id", async () => {
    await expectDetailCall(
      () => tenantService.modules.get("module-1"),
      "/api/v1/tenant-management/modules/module-1/",
      { id: "module-1", module_name: "inventory" }
    );
  });

  it("lists resource usage without filters", async () => {
    await expectListCall(
      () => tenantService.resourceUsage.list(),
      "/api/v1/tenant-management/resource-usage/",
      undefined
    );
  });

  it("lists resource usage with tenant and date filters", async () => {
    await expectListCall(
      () =>
        tenantService.resourceUsage.list({
          tenant_id: "tenant-1",
          date_from: "2026-03-01",
          date_to: "2026-03-31",
        }),
      "/api/v1/tenant-management/resource-usage/?tenant_id=tenant-1&date_from=2026-03-01&date_to=2026-03-31"
    );
  });

  it("gets one resource usage record by id", async () => {
    await expectDetailCall(
      () => tenantService.resourceUsage.get("usage-1"),
      "/api/v1/tenant-management/resource-usage/usage-1/",
      { id: "usage-1", tenant: "tenant-1" }
    );
  });

  it("lists settings without filters", async () => {
    await expectListCall(
      () => tenantService.settings.list(),
      "/api/v1/tenant-management/settings/",
      null
    );
  });

  it("lists settings with tenant and category filters", async () => {
    await expectListCall(
      () => tenantService.settings.list({ tenant_id: "tenant-1", category: "security" }),
      "/api/v1/tenant-management/settings/?tenant_id=tenant-1&category=security"
    );
  });

  it("gets one setting by id", async () => {
    await expectDetailCall(
      () => tenantService.settings.get("setting-1"),
      "/api/v1/tenant-management/settings/setting-1/",
      { id: "setting-1", tenant: "tenant-1" }
    );
  });

  it("lists health scores without filters", async () => {
    await expectListCall(
      () => tenantService.healthScores.list(),
      "/api/v1/tenant-management/health-scores/",
      undefined
    );
  });

  it("lists health scores with tenant, date, and zero churn filters", async () => {
    await expectListCall(
      () =>
        tenantService.healthScores.list({
          tenant_id: "tenant-1",
          date_from: "2026-04-01",
          date_to: "2026-04-30",
          churn_risk_min: 0,
        }),
      "/api/v1/tenant-management/health-scores/?tenant_id=tenant-1&date_from=2026-04-01&date_to=2026-04-30&churn_risk_min=0"
    );
  });

  it("lists health scores with a positive churn filter", async () => {
    await expectListCall(
      () => tenantService.healthScores.list({ churn_risk_min: 25 }),
      "/api/v1/tenant-management/health-scores/?churn_risk_min=25"
    );
  });

  it("gets one health score by id", async () => {
    await expectDetailCall(
      () => tenantService.healthScores.get("health-1"),
      "/api/v1/tenant-management/health-scores/health-1/",
      { id: "health-1", tenant: "tenant-1" }
    );
  });
});
