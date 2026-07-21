/* eslint-disable @typescript-eslint/unbound-method -- Vitest asserts intentionally reference mock methods. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import type { APIEnvelope, DefinitionListDTO } from "../../contracts";
import { ENDPOINTS } from "../../contracts";
import { automationOrchestrationService as service } from "../../services/automation-orchestration-service";

vi.mock("@/services/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const definition: DefinitionListDTO = {
  id: "00000000-0000-4000-8000-000000000001",
  tenant_id: "00000000-0000-4000-8000-000000000002",
  key: "daily-close",
  version: 1,
  name: "Daily close",
  description: "Close daily ledgers",
  status: "published",
  is_current: true,
  graph_revision: 2,
  node_count: 3,
  schedule_count: 1,
  last_run_at: null,
  success_rate: null,
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const listEnvelope: APIEnvelope<readonly DefinitionListDTO[]> = {
  data: [definition],
  meta: {
    correlation_id: "corr-1",
    timestamp: "2026-07-21T00:00:00Z",
    pagination: {
      count: 1,
      page: 1,
      page_size: 25,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
  },
};

describe("automation orchestration service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps governed paginated list envelopes and preserves metadata", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(listEnvelope);
    const result = await service.listDefinitions({ status: "published", page: 1 });
    expect(result.items).toEqual([definition]);
    expect(result.pagination.count).toBe(1);
    expect(result.correlationId).toBe("corr-1");
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.DEFINITIONS.LIST}?status=published&page=1`,
    );
  });

  it("fails explicitly when a list omits governed pagination", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [],
      meta: { correlation_id: "corr-2", timestamp: "2026-07-21T00:00:00Z" },
    });
    await expect(service.listDefinitions()).rejects.toThrow("without pagination metadata");
  });

  it("uses PATCH for draft updates and POST for graph validation", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ data: definition, meta: listEnvelope.meta });
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { valid: true, validated_revision: 2, issues: [] },
      meta: listEnvelope.meta,
    });
    await service.updateDefinition(definition.id, { name: "Close", expected_revision: 2 });
    await service.validateDefinition(definition.id);
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.DEFINITIONS.UPDATE(definition.id), {
      name: "Close",
      expected_revision: 2,
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.DEFINITIONS.VALIDATE(definition.id),
      {},
    );
  });

  it("delegates deletion without fabricating a response", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);
    await expect(service.deleteNode("node-id")).resolves.toBeUndefined();
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.NODES.DELETE("node-id"));
  });
});
