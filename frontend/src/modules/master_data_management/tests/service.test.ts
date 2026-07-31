/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method -- mocked API methods are assertion targets, never detached invocations. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import { masterDataService } from "../services/master-data-service";

vi.mock("@/services/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
const api = vi.mocked(apiClient);
const meta = { correlation_id: "corr-mdm-1", timestamp: "2026-07-22T00:00:00Z" };
const pagination = {
  count: 0,
  page: 1,
  page_size: 25,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};

describe("master data v2 service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("consumes the governed list envelope without legacy compatibility", async () => {
    api.get.mockResolvedValueOnce({ data: [], meta, pagination });
    await expect(masterDataService.entities.list({ search: "Acme", page: 2 })).resolves.toEqual({
      items: [],
      meta,
      pagination,
    });
    expect(api.get).toHaveBeenCalledWith(`${ENDPOINTS.ENTITIES.LIST}?search=Acme&page=2`);
  });

  it("prefers governed meta pagination, falls back to legacy pagination, and fails closed when absent", async () => {
    const governedPagination = { ...pagination, count: 2, total_pages: 1 };
    const legacyPagination = { ...pagination, count: 1, page_size: 10 };
    const governedMeta = { ...meta, pagination: governedPagination };
    api.get
      .mockResolvedValueOnce({ data: [], meta: governedMeta, pagination: legacyPagination })
      .mockResolvedValueOnce({ data: [], meta, pagination: legacyPagination })
      .mockResolvedValueOnce({ data: [], meta });

    await expect(masterDataService.entities.list()).resolves.toMatchObject({
      pagination: governedPagination,
      meta: governedMeta,
    });
    await expect(masterDataService.entities.list()).resolves.toMatchObject({
      pagination: legacyPagination,
      meta,
    });
    await expect(masterDataService.entities.list()).rejects.toThrow(
      "Master Data list response is missing governed pagination metadata."
    );
    expect(api.get).toHaveBeenNthCalledWith(1, ENDPOINTS.ENTITIES.LIST);
    expect(api.get).toHaveBeenNthCalledWith(2, ENDPOINTS.ENTITIES.LIST);
    expect(api.get).toHaveBeenNthCalledWith(3, ENDPOINTS.ENTITIES.LIST);
  });

  it("serializes governed query primitives and omits empty or unsupported filter values", async () => {
    api.get.mockResolvedValue({ data: [], meta, pagination });

    await masterDataService.entityTypes.list({
      search: "",
      page: 0,
      page_size: undefined,
      is_active: false,
    });
    await masterDataService.entities.list({
      search: "",
      quality_min: 0,
      deleted: false,
      source_system: undefined,
    });

    expect(api.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.ENTITY_TYPES.LIST}?page=0&is_active=false`
    );
    expect(api.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.ENTITIES.LIST}?quality_min=0&deleted=false`
    );
  });

  it("wraps governed item envelopes without dropping response evidence", async () => {
    const summary = {
      total_entities: 2,
      active_entities: 1,
      pending_review_entities: 1,
      merged_entities: 0,
      archived_entities: 0,
      quality_evaluated_entities: 1,
      average_quality_score: 98,
      score_distribution: [],
      quality_trend: [],
      open_issues: 0,
      critical_issues: 0,
      pending_matches: 0,
      recent_activity: [],
    };
    api.get.mockResolvedValueOnce({ data: summary, meta });

    await expect(masterDataService.dashboard.get()).resolves.toEqual({ data: summary, meta });
    expect(api.get).toHaveBeenCalledWith(ENDPOINTS.DASHBOARD);
  });

  it("uses contract-owned endpoints for actions", async () => {
    const entity = { id: "entity-1" };
    api.post.mockResolvedValue({ data: entity, meta });
    api.patch.mockResolvedValue({ data: entity, meta });
    api.delete.mockResolvedValue(undefined);
    await masterDataService.entities.restore("entity-1", {
      expected_version: 2,
      reason: "Restore",
      idempotency_key: "restore-1",
    });
    await masterDataService.entities.update("entity-1", {
      expected_version: 2,
      changes: { entity_name: "Updated" },
      reason: "Correction",
      idempotency_key: "update-1",
    });
    await masterDataService.matchCandidates.review("candidate-1", {
      decision: "confirm",
      transition_key: "review-1",
    });
    await masterDataService.merges.reverse("merge-1", {
      reason: "Incorrect merge",
      transition_key: "reverse-1",
    });
    await masterDataService.qualityRules.delete("rule-1", { idempotency_key: "deactivate-rule-1" });
    expect(api.post).toHaveBeenCalledWith(
      ENDPOINTS.ENTITIES.RESTORE("entity-1"),
      expect.any(Object)
    );
    expect(api.patch).toHaveBeenCalledWith(
      ENDPOINTS.ENTITIES.UPDATE("entity-1"),
      expect.any(Object)
    );
    expect(api.post).toHaveBeenCalledWith(
      ENDPOINTS.MATCH_CANDIDATES.REVIEW("candidate-1"),
      expect.any(Object)
    );
    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.MERGES.REVERSE("merge-1"), expect.any(Object));
    expect(api.delete).toHaveBeenCalledWith(ENDPOINTS.QUALITY_RULES.DELETE("rule-1"), {
      body: JSON.stringify({ idempotency_key: "deactivate-rule-1" }),
    });
  });

  it("returns durable job evidence from scan creation", async () => {
    const job = { id: "job-1", status: "queued" };
    api.post.mockResolvedValueOnce({ data: job, meta });
    await expect(
      masterDataService.qualityScans.create({
        entity_type_id: "entity-type-1",
        idempotency_key: "scan-1",
      })
    ).resolves.toEqual({ data: job, meta });
    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.QUALITY_SCANS, {
      entity_type_id: "entity-type-1",
      idempotency_key: "scan-1",
    });
  });
});
