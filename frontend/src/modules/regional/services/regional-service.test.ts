/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- service request coverage keeps endpoint assertions cohesive. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS, type RegionalConfigurationDocument } from "../contracts";
import { regionalService } from "./regional-service";

vi.mock("@/services/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const document: RegionalConfigurationDocument = {
  resource: {
    name_min_length: 2,
    name_max_length: 80,
    name_default: "Regional policy",
    description_default: "",
    description_max_length: 400,
    default_active: true,
    default_config: { jurisdiction_type: "country" },
    allowed_config_keys: ["country_code", "jurisdiction_type", "compliance_tags"],
    allowed_jurisdiction_types: ["country", "state"],
    max_compliance_tags: 8,
    max_config_bytes: 4096,
    search_fields: ["name", "description"],
  },
  workflow: {
    activation_state: true,
    deactivation_state: false,
    require_delete_confirmation: true,
  },
  api: {
    default_page_size: 25,
    max_page_size: 100,
    allowed_filters: ["is_active", "name"],
    allowed_ordering: ["name", "-name", "created_at", "-created_at"],
  },
  health: { cache_probe_ttl_seconds: 60 },
  rollout: { enabled: true, roles: ["regional-admin"], cohorts: ["default"] },
};

describe("regionalService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "corr-regional-1" });
  });

  it("serializes list filters and bounded pagination", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    await regionalService.listResources("tax policy", 3);

    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.RESOURCES.LIST}?page=3&search=tax+policy`
    );
  });

  it("uses correlation and idempotency headers for resource create/update/delete commands", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ id: "resource-1" });
    vi.mocked(apiClient.patch).mockResolvedValue({ id: "resource-1" });
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await regionalService.createResource(
      { name: "India GST", config: { country_code: "IN" } },
      "00000000-0000-4000-8000-000000000601"
    );
    await regionalService.updateResource("resource-1", {
      description: "Updated",
      config: { compliance_tags: ["gst"] },
    });
    await regionalService.deleteResource("resource-1");

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.RESOURCES.CREATE,
      { name: "India GST", config: { country_code: "IN" } },
      {
        headers: {
          "X-Correlation-ID": "corr-regional-1",
          "Idempotency-Key": "00000000-0000-4000-8000-000000000601",
        },
      }
    );
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.RESOURCES.UPDATE("resource-1"),
      { description: "Updated", config: { compliance_tags: ["gst"] } },
      { headers: { "X-Correlation-ID": "corr-regional-1" } }
    );
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.RESOURCES.DELETE("resource-1"), {
      headers: { "X-Correlation-ID": "corr-regional-1" },
    });
  });

  it("routes workflow transitions with correlation evidence and no request body", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ id: "resource-1" });

    await regionalService.restoreResource("resource-1");
    await regionalService.activateResource("resource-1");
    await regionalService.deactivateResource("resource-1");

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.RESOURCES.RESTORE("resource-1"),
      undefined,
      { headers: { "X-Correlation-ID": "corr-regional-1" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.RESOURCES.ACTIVATE("resource-1"),
      undefined,
      { headers: { "X-Correlation-ID": "corr-regional-1" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.RESOURCES.DEACTIVATE("resource-1"),
      undefined,
      { headers: { "X-Correlation-ID": "corr-regional-1" } }
    );
  });

  it("keeps configuration environment, preview, import, rollback, and export endpoints separate", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ environment: "development", document });
    vi.mocked(apiClient.put).mockResolvedValue({ environment: "development", document });
    vi.mocked(apiClient.post).mockResolvedValue({ environment: "development", document });

    await regionalService.getConfiguration("self-hosted");
    await regionalService.getActiveConfiguration();
    await regionalService.updateConfiguration({ environment: "development", document });
    await regionalService.previewConfiguration("development", document);
    await regionalService.listConfigurationHistory("development");
    await regionalService.rollbackConfiguration("development", 4);
    await regionalService.importConfiguration("development", document);
    await regionalService.exportConfiguration("development");

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.CONFIGURATION.CURRENT}?environment=self-hosted`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(2, ENDPOINTS.CONFIGURATION.ROOT);
    expect(apiClient.put).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.CURRENT,
      { environment: "development", document },
      { headers: { "X-Correlation-ID": "corr-regional-1" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.CONFIGURATION.PREVIEW,
      { environment: "development", document },
      { headers: { "X-Correlation-ID": "corr-regional-1" } }
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.CONFIGURATION.HISTORY}?environment=development`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.CONFIGURATION.ROLLBACK,
      { environment: "development", version: 4 },
      { headers: { "X-Correlation-ID": "corr-regional-1" } }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.CONFIGURATION.IMPORT,
      { environment: "development", document },
      { headers: { "X-Correlation-ID": "corr-regional-1" } }
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      4,
      `${ENDPOINTS.CONFIGURATION.EXPORT}?environment=development`
    );
  });
});
