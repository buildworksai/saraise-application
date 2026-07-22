/* eslint-disable @typescript-eslint/unbound-method -- mocked API methods are assertion targets, never detached invocations. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import { masterDataService } from "../services/master-data-service";

vi.mock("@/services/api-client", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));
const api = vi.mocked(apiClient);
const meta = { correlation_id: "corr-mdm-1", timestamp: "2026-07-22T00:00:00Z" };
const pagination = { count: 0, page: 1, page_size: 25, total_pages: 0, has_next: false, has_previous: false };

describe("master data v2 service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("consumes the governed list envelope without legacy compatibility", async () => {
    api.get.mockResolvedValueOnce({ data: [], meta, pagination });
    await expect(masterDataService.entities.list({ search: "Acme", page: 2 })).resolves.toEqual({ items: [], meta, pagination });
    expect(api.get).toHaveBeenCalledWith(`${ENDPOINTS.ENTITIES.LIST}?search=Acme&page=2`);
  });

  it("uses contract-owned endpoints for actions", async () => {
    const entity = { id: "entity-1" };
    api.post.mockResolvedValue({ data: entity, meta });
    api.patch.mockResolvedValue({ data: entity, meta });
    api.delete.mockResolvedValue(undefined);
    await masterDataService.entities.restore("entity-1", { expected_version: 2, reason: "Restore", idempotency_key: "restore-1" });
    await masterDataService.entities.update("entity-1", { expected_version: 2, changes: { entity_name: "Updated" }, reason: "Correction", idempotency_key: "update-1" });
    await masterDataService.matchCandidates.review("candidate-1", { decision: "confirm", transition_key: "review-1" });
    await masterDataService.merges.reverse("merge-1", { reason: "Incorrect merge", transition_key: "reverse-1" });
    await masterDataService.qualityRules.delete("rule-1");
    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.ENTITIES.RESTORE("entity-1"), expect.any(Object));
    expect(api.patch).toHaveBeenCalledWith(ENDPOINTS.ENTITIES.UPDATE("entity-1"), expect.any(Object));
    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.MATCH_CANDIDATES.REVIEW("candidate-1"), expect.any(Object));
    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.MERGES.REVERSE("merge-1"), expect.any(Object));
    expect(api.delete).toHaveBeenCalledWith(ENDPOINTS.QUALITY_RULES.DELETE("rule-1"));
  });

  it("returns durable job evidence from scan creation", async () => {
    const job = { id: "job-1", status: "queued" };
    api.post.mockResolvedValueOnce({ data: job, meta });
    await expect(masterDataService.qualityScans.create({ idempotency_key: "scan-1" })).resolves.toEqual({ data: job, meta });
    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.QUALITY_SCANS, { idempotency_key: "scan-1" });
  });
});
