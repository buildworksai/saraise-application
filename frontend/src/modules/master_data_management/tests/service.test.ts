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

  it("routes quality rule history, rollback, import, export, and issue transitions", async () => {
    const rule = { id: "quality-rule-1", version: 4 };
    const issue = { id: "issue-1", status: "assigned" };
    api.get.mockResolvedValueOnce({ data: [], meta, pagination }).mockResolvedValueOnce({
      data: { kind: "quality-rule", rule },
      meta,
    });
    api.post.mockResolvedValue({ data: rule, meta });

    await masterDataService.qualityRules.history("quality-rule-1");
    await masterDataService.qualityRules.rollback("quality-rule-1", {
      version_number: 3,
      reason: "Bad rule import",
      idempotency_key: "quality-rollback-1",
    });
    await masterDataService.qualityRules.importDocument("quality-rule-1", {
      document: {
        schema: "saraise.master-data-management.quality-rule",
        document_version: 1,
        rule_id: "quality-rule-1",
        version_number: 5,
        snapshot: { kind: "quality-rule" },
      },
      reason: "Promote reviewed quality rule",
      idempotency_key: "quality-import-1",
    });
    await masterDataService.qualityRules.exportDocument("quality-rule-1");
    await masterDataService.qualityIssues.assign("issue-1", {
      assignee_id: "steward-1",
      transition_key: "assign-1",
    });
    api.post.mockResolvedValueOnce({ data: { ...issue, status: "resolved" }, meta });
    await masterDataService.qualityIssues.resolve("issue-1", {
      resolution: "Corrected source payload",
      transition_key: "resolve-1",
    });
    api.post.mockResolvedValueOnce({ data: { ...issue, status: "waived" }, meta });
    await masterDataService.qualityIssues.waive("issue-1", {
      resolution: "Accepted exception",
      transition_key: "waive-1",
    });

    expect(api.get).toHaveBeenNthCalledWith(1, ENDPOINTS.QUALITY_RULES.HISTORY("quality-rule-1"));
    expect(api.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.QUALITY_RULES.ROLLBACK("quality-rule-1"),
      expect.objectContaining({ version_number: 3, idempotency_key: "quality-rollback-1" })
    );
    expect(api.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.QUALITY_RULES.IMPORT("quality-rule-1"),
      expect.objectContaining({ reason: "Promote reviewed quality rule" })
    );
    expect(api.get).toHaveBeenNthCalledWith(2, ENDPOINTS.QUALITY_RULES.EXPORT("quality-rule-1"));
    expect(api.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.QUALITY_ISSUES.ASSIGN("issue-1"),
      expect.objectContaining({ assignee_id: "steward-1" })
    );
    expect(api.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.QUALITY_ISSUES.RESOLVE("issue-1"),
      expect.objectContaining({ resolution: "Corrected source payload" })
    );
    expect(api.post).toHaveBeenNthCalledWith(
      5,
      ENDPOINTS.QUALITY_ISSUES.WAIVE("issue-1"),
      expect.objectContaining({ resolution: "Accepted exception" })
    );
  });

  it("routes matching rule governance, preview, scan, and candidate filters", async () => {
    const rule = { id: "matching-rule-1", version: 7 };
    api.get.mockResolvedValue({ data: [], meta, pagination });
    api.post.mockResolvedValue({ data: rule, meta });
    api.patch.mockResolvedValue({ data: rule, meta });
    api.delete.mockResolvedValue(undefined);

    await masterDataService.matchingRules.create({
      entity_type_id: "type-1",
      name: "Customer exact email",
      algorithm: "exact",
      field_weights: { "data.email": 1 },
      blocking_fields: ["data.email"],
      review_threshold: 0.8,
      auto_confirm_threshold: 0.95,
      is_active: true,
      idempotency_key: "matching-create-1",
    });
    await masterDataService.matchingRules.update("matching-rule-1", {
      changes: { review_threshold: 0.85 },
      idempotency_key: "matching-update-1",
    });
    await masterDataService.matchingRules.rollback("matching-rule-1", {
      version_number: 6,
      reason: "Rollback",
      idempotency_key: "matching-rollback-1",
    });
    await masterDataService.matchingRules.importDocument("matching-rule-1", {
      document: {
        schema: "saraise.master-data-management.matching-rule",
        document_version: 1,
        rule_id: "matching-rule-1",
        version_number: 8,
        snapshot: { kind: "matching-rule" },
      },
      reason: "Promote reviewed matching rule",
      idempotency_key: "matching-import-1",
    });
    await masterDataService.matchingRules.exportDocument("matching-rule-1");
    await masterDataService.matchingRules.delete("matching-rule-1", {
      idempotency_key: "matching-delete-1",
    });
    await masterDataService.matching.preview({
      entity_id: "entity-1",
      candidate_id: "entity-2",
      matching_rule_id: "matching-rule-1",
    } as never);
    await masterDataService.matching.scan({
      entity_type_id: "type-1",
      rule_ids: ["matching-rule-1"],
      idempotency_key: "dedupe-scan-1",
    });
    await masterDataService.matchCandidates.list({
      entity_type: "type-1",
      status: "pending",
      page: 2,
    } as never);

    expect(api.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.MATCHING_RULES.CREATE,
      expect.objectContaining({ name: "Customer exact email" })
    );
    expect(api.patch).toHaveBeenCalledWith(
      ENDPOINTS.MATCHING_RULES.UPDATE("matching-rule-1"),
      expect.objectContaining({ idempotency_key: "matching-update-1" })
    );
    expect(api.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.MATCHING_RULES.ROLLBACK("matching-rule-1"),
      expect.objectContaining({ version_number: 6 })
    );
    expect(api.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.MATCHING_RULES.IMPORT("matching-rule-1"),
      expect.objectContaining({ reason: "Promote reviewed matching rule" })
    );
    expect(api.get).toHaveBeenCalledWith(ENDPOINTS.MATCHING_RULES.EXPORT("matching-rule-1"));
    expect(api.delete).toHaveBeenCalledWith(ENDPOINTS.MATCHING_RULES.DELETE("matching-rule-1"), {
      body: JSON.stringify({ idempotency_key: "matching-delete-1" }),
    });
    expect(api.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.MATCHING.PREVIEW,
      expect.objectContaining({ matching_rule_id: "matching-rule-1" })
    );
    expect(api.post).toHaveBeenNthCalledWith(
      5,
      ENDPOINTS.MATCHING.SCANS,
      expect.objectContaining({ idempotency_key: "dedupe-scan-1" })
    );
    expect(api.get).toHaveBeenLastCalledWith(
      `${ENDPOINTS.MATCH_CANDIDATES.LIST}?entity_type=type-1&status=pending&page=2`
    );
  });

  it("routes merge preview/create/reversal, configuration, job, health, and validation helpers", async () => {
    const merge = { id: "merge-1", status: "applied" };
    const configuration = { id: "config-1", version: 3 };
    api.get.mockResolvedValue({ data: configuration, meta: { ...meta, pagination } });
    api.post.mockResolvedValue({ data: merge, meta });
    api.patch.mockResolvedValue({ data: configuration, meta });

    await masterDataService.merges.list({ status: "applied", page: 3 });
    await masterDataService.merges.preview({
      source_entity_ids: ["entity-2"],
      survivor_entity_id: "entity-1",
      idempotency_key: "merge-preview-1",
    } as never);
    await masterDataService.merges.create({
      source_entity_ids: ["entity-2"],
      survivor_entity_id: "entity-1",
      reason: "Duplicate",
      idempotency_key: "merge-create-1",
    } as never);
    await masterDataService.merges.reversalPreview("merge-1");
    await masterDataService.configuration.current();
    await masterDataService.configuration.create({
      document: {},
      reason: "Create governed configuration",
      idempotency_key: "config-create-1",
    } as never);
    await masterDataService.configuration.update("config-1", {
      document: {},
      reason: "Update governed configuration",
      idempotency_key: "config-update-1",
    } as never);
    await masterDataService.configuration.preview({
      document: {},
    } as never);
    await masterDataService.configuration.history();
    await masterDataService.configuration.rollback({
      version: 2,
      reason: "Rollback governed configuration",
      idempotency_key: "config-rollback-1",
    });
    await masterDataService.configuration.importDocument({
      document: {},
      reason: "Import governed configuration",
      idempotency_key: "config-import-1",
    } as never);
    await masterDataService.configuration.exportDocument();
    await masterDataService.jobs.get("job-1");
    await masterDataService.health.live();
    await masterDataService.health.ready();

    expect(masterDataService.validation.report({ data: { valid: true } as never, meta })).toEqual({
      data: { valid: true },
      meta,
    });
    expect(api.get).toHaveBeenNthCalledWith(1, `${ENDPOINTS.MERGES.LIST}?status=applied&page=3`);
    expect(api.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.MERGES.PREVIEW,
      expect.objectContaining({ idempotency_key: "merge-preview-1" })
    );
    expect(api.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.MERGES.CREATE,
      expect.objectContaining({ reason: "Duplicate" })
    );
    expect(api.get).toHaveBeenNthCalledWith(2, ENDPOINTS.MERGES.REVERSAL_PREVIEW("merge-1"));
    expect(api.get).toHaveBeenNthCalledWith(3, ENDPOINTS.CONFIGURATION.LIST);
    expect(api.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.CONFIGURATION.LIST,
      expect.objectContaining({ idempotency_key: "config-create-1" })
    );
    expect(api.patch).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.DETAIL("config-1"),
      expect.objectContaining({ reason: "Update governed configuration" })
    );
    expect(api.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.CONFIGURATION.PREVIEW,
      expect.objectContaining({ document: {} })
    );
    expect(api.get).toHaveBeenNthCalledWith(4, ENDPOINTS.CONFIGURATION.HISTORY);
    expect(api.post).toHaveBeenNthCalledWith(
      5,
      ENDPOINTS.CONFIGURATION.ROLLBACK,
      expect.objectContaining({ version: 2 })
    );
    expect(api.post).toHaveBeenNthCalledWith(
      6,
      ENDPOINTS.CONFIGURATION.IMPORT,
      expect.objectContaining({ reason: "Import governed configuration" })
    );
    expect(api.get).toHaveBeenNthCalledWith(5, ENDPOINTS.CONFIGURATION.EXPORT);
    expect(api.get).toHaveBeenNthCalledWith(6, ENDPOINTS.JOB("job-1"));
    expect(api.get).toHaveBeenNthCalledWith(7, ENDPOINTS.HEALTH.LIVE);
    expect(api.get).toHaveBeenNthCalledWith(8, ENDPOINTS.HEALTH.READY);
  });
});
