/* eslint-disable max-lines-per-function -- cohesive endpoint contract coverage for the module service. */
import { ApiError, apiClient } from "@/services/api-client";
import {
  DocumentIntelligenceApiError,
  documentIntelligenceService,
} from "./document-intelligence-service";
import { ENDPOINTS } from "../contracts";
import type {
  ApiV2Envelope,
  ApiV2PaginatedEnvelope,
  DocumentExtractionListItem,
  ModuleHealth,
} from "../contracts";

const meta = { correlation_id: "corr-1", timestamp: "2026-07-21T10:00:00Z" };

describe("document intelligence v2 service", () => {
  afterEach(() => vi.restoreAllMocks());

  it("unwraps governed data without synthesizing health", async () => {
    const health: ModuleHealth = {
      status: "healthy",
      live: true,
      ready: true,
      checked_at: meta.timestamp,
      dependencies: [],
    };
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: health,
      meta,
    } satisfies ApiV2Envelope<ModuleHealth>);
    await expect(documentIntelligenceService.getHealth()).resolves.toEqual(health);
  });

  it("passes bounded server filters through URLSearchParams", async () => {
    const envelope: ApiV2PaginatedEnvelope<DocumentExtractionListItem> = {
      data: [],
      meta: {
        ...meta,
        pagination: {
          count: 0,
          page: 2,
          page_size: 25,
          total_pages: 0,
          has_next: false,
          has_previous: true,
        },
      },
    };
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(envelope);
    await documentIntelligenceService.listExtractions({
      page: 2,
      status: "needs_review",
      engine: "tesseract",
      confidence_min: "0.8000",
      ordering: "-created_at",
    });
    expect(get).toHaveBeenCalledWith(expect.stringContaining("page=2"));
    expect(get).toHaveBeenCalledWith(expect.stringContaining("status=needs_review"));
    expect(get).toHaveBeenCalledWith(expect.stringContaining("confidence_min=0.8000"));
  });

  it("serializes every governed list query without dropping bounded filters", async () => {
    const envelope: ApiV2PaginatedEnvelope<never> = {
      data: [],
      meta: {
        ...meta,
        pagination: {
          count: 0,
          page: 1,
          page_size: 10,
          total_pages: 0,
          has_next: false,
          has_previous: false,
        },
      },
    };
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(envelope);

    await documentIntelligenceService.listClassifications({
      document_id: "document-1",
      status: "completed",
      category: "invoice",
      confidence_min: "0.7000",
      confidence_max: "0.9900",
      needs_review: false,
      review_status: "confirmed",
      search: "customer",
      ordering: "-confidence",
    });
    await documentIntelligenceService.listTemplates({
      status: "active",
      document_category: "invoice",
      engine: "tesseract",
      page_size: 50,
    });
    await documentIntelligenceService.listTrainingJobs({ status: "failed", page: 3 });
    await documentIntelligenceService.listModelVersions({
      status: "candidate",
      provider_key: "provider.alpha",
    });

    expect(get).toHaveBeenNthCalledWith(1, expect.stringContaining("needs_review=false"));
    expect(get).toHaveBeenNthCalledWith(1, expect.stringContaining("confidence_max=0.9900"));
    expect(get).toHaveBeenNthCalledWith(2, expect.stringContaining("document_category=invoice"));
    expect(get).toHaveBeenNthCalledWith(3, expect.stringContaining("status=failed"));
    expect(get).toHaveBeenNthCalledWith(4, expect.stringContaining("provider_key=provider.alpha"));
  });

  it("uses the exact extraction and classification lifecycle endpoints", async () => {
    const response = { data: { id: "resource-1" }, meta } satisfies ApiV2Envelope<unknown>;
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(response);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(response);
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined);

    await documentIntelligenceService.createExtraction({ document_id: "document-1" } as never);
    await documentIntelligenceService.getExtraction("extraction-1");
    await documentIntelligenceService.listExtractionPages("extraction-1");
    await documentIntelligenceService.getExtractionPage("page-1");
    await documentIntelligenceService.retryExtraction("extraction-1", {
      idempotency_key: "retry-extraction-once",
    });
    await documentIntelligenceService.cancelExtraction("extraction-1", { reason: "cancel" });
    await documentIntelligenceService.archiveExtraction("extraction-1");
    await documentIntelligenceService.createClassification({ document_id: "document-1" } as never);
    await documentIntelligenceService.getClassification("classification-1");
    await documentIntelligenceService.listClassificationScores("classification-1");
    await documentIntelligenceService.getClassificationScore("score-1");
    await documentIntelligenceService.reviewClassification("classification-1", {
      reviewed_category: "invoice",
      review_note: "confirmed",
      idempotency_key: "review-once",
    } as never);
    await documentIntelligenceService.retryClassification("classification-1", {
      idempotency_key: "retry-classification-once",
    });
    await documentIntelligenceService.cancelClassification("classification-1", {
      reason: "cancel",
    });
    await documentIntelligenceService.archiveClassification("classification-1");

    expect(post).toHaveBeenCalledWith(ENDPOINTS.EXTRACTIONS.CREATE, {
      document_id: "document-1",
    });
    expect(get).toHaveBeenCalledWith(ENDPOINTS.EXTRACTIONS.DETAIL("extraction-1"));
    expect(get).toHaveBeenCalledWith(ENDPOINTS.EXTRACTIONS.PAGES("extraction-1"));
    expect(get).toHaveBeenCalledWith(ENDPOINTS.EXTRACTION_PAGES.DETAIL("page-1"));
    expect(post).toHaveBeenCalledWith(ENDPOINTS.EXTRACTIONS.RETRY("extraction-1"), {
      idempotency_key: "retry-extraction-once",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.EXTRACTIONS.CANCEL("extraction-1"), {
      reason: "cancel",
    });
    expect(del).toHaveBeenCalledWith(ENDPOINTS.EXTRACTIONS.DETAIL("extraction-1"));
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CLASSIFICATIONS.CREATE, {
      document_id: "document-1",
    });
    expect(get).toHaveBeenCalledWith(ENDPOINTS.CLASSIFICATIONS.DETAIL("classification-1"));
    expect(get).toHaveBeenCalledWith(ENDPOINTS.CLASSIFICATIONS.SCORES("classification-1"));
    expect(get).toHaveBeenCalledWith(ENDPOINTS.CLASSIFICATION_SCORES.DETAIL("score-1"));
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CLASSIFICATIONS.REVIEW("classification-1"), {
      reviewed_category: "invoice",
      review_note: "confirmed",
      idempotency_key: "review-once",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CLASSIFICATIONS.CANCEL("classification-1"), {
      reason: "cancel",
    });
    expect(del).toHaveBeenCalledWith(ENDPOINTS.CLASSIFICATIONS.DETAIL("classification-1"));
  });

  it("routes templates, zones, training, models, and configuration through governed endpoints", async () => {
    const response = { data: { id: "resource-1" }, meta } satisfies ApiV2Envelope<unknown>;
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(response);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(response);
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue(response);
    const put = vi.spyOn(apiClient, "put").mockResolvedValue(response);
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined);

    await documentIntelligenceService.createTemplate({ name: "Invoice" } as never);
    await documentIntelligenceService.getTemplate("template-1");
    await documentIntelligenceService.updateTemplate("template-1", { name: "Updated" } as never);
    await documentIntelligenceService.activateTemplate("template-1", {
      transition_key: "activate-template",
    });
    await documentIntelligenceService.deactivateTemplate("template-1", {
      transition_key: "deactivate-template",
    });
    await documentIntelligenceService.cloneTemplate("template-1", { name: "Copy" } as never);
    await documentIntelligenceService.matchTemplate("template-1", {
      document_id: "doc-1",
      document_version_id: "version-1",
    });
    await documentIntelligenceService.archiveTemplate("template-1");
    await documentIntelligenceService.listTemplateZones("template-1", 200);
    await documentIntelligenceService.createTemplateZone({ template: "template-1" } as never);
    await documentIntelligenceService.getTemplateZone("zone-1");
    await documentIntelligenceService.updateTemplateZone("zone-1", { label: "Total" } as never);
    await documentIntelligenceService.deleteTemplateZone("zone-1");
    await documentIntelligenceService.createTrainingJob({ name: "Train" } as never);
    await documentIntelligenceService.getTrainingJob("job-1");
    await documentIntelligenceService.retryTrainingJob("job-1", {
      idempotency_key: "retry-training-once",
    });
    await documentIntelligenceService.cancelTrainingJob("job-1", { reason: "cancel" });
    await documentIntelligenceService.getModelVersion("model-1");
    await documentIntelligenceService.activateModelVersion("model-1", {
      transition_key: "activate-model",
    });
    await documentIntelligenceService.rollbackModelVersion("model-1", {
      transition_key: "rollback-model",
    });
    await documentIntelligenceService.getConfiguration();
    await documentIntelligenceService.updateConfiguration({ document: {} } as never);
    await documentIntelligenceService.listConfigurationVersions();
    await documentIntelligenceService.listConfigurationAudit();
    await documentIntelligenceService.simulateConfiguration({ document: {} } as never);
    await documentIntelligenceService.rollbackConfiguration({
      version: 2,
      change_reason: "rollback",
    });
    await documentIntelligenceService.importConfiguration({ document: {} } as never);
    await documentIntelligenceService.exportConfiguration();

    expect(post).toHaveBeenCalledWith(ENDPOINTS.TEMPLATES.CREATE, { name: "Invoice" });
    expect(get).toHaveBeenCalledWith(ENDPOINTS.TEMPLATES.DETAIL("template-1"));
    expect(patch).toHaveBeenCalledWith(ENDPOINTS.TEMPLATES.DETAIL("template-1"), {
      name: "Updated",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.TEMPLATES.ACTIVATE("template-1"), {
      transition_key: "activate-template",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.TEMPLATES.DEACTIVATE("template-1"), {
      transition_key: "deactivate-template",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.TEMPLATES.CLONE("template-1"), { name: "Copy" });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.TEMPLATES.MATCH("template-1"), {
      document_id: "doc-1",
      document_version_id: "version-1",
    });
    expect(del).toHaveBeenCalledWith(ENDPOINTS.TEMPLATES.DETAIL("template-1"));
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.TEMPLATE_ZONES.LIST}?template_id=template-1&page_size=200`
    );
    expect(post).toHaveBeenCalledWith(ENDPOINTS.TEMPLATE_ZONES.CREATE, {
      template: "template-1",
    });
    expect(get).toHaveBeenCalledWith(ENDPOINTS.TEMPLATE_ZONES.DETAIL("zone-1"));
    expect(patch).toHaveBeenCalledWith(ENDPOINTS.TEMPLATE_ZONES.DETAIL("zone-1"), {
      label: "Total",
    });
    expect(del).toHaveBeenCalledWith(ENDPOINTS.TEMPLATE_ZONES.DETAIL("zone-1"));
    expect(post).toHaveBeenCalledWith(ENDPOINTS.TRAINING_JOBS.CREATE, { name: "Train" });
    expect(get).toHaveBeenCalledWith(ENDPOINTS.TRAINING_JOBS.DETAIL("job-1"));
    expect(post).toHaveBeenCalledWith(ENDPOINTS.TRAINING_JOBS.RETRY("job-1"), {
      idempotency_key: "retry-training-once",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.TRAINING_JOBS.CANCEL("job-1"), {
      reason: "cancel",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.MODEL_VERSIONS.ACTIVATE("model-1"), {
      transition_key: "activate-model",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.MODEL_VERSIONS.ROLLBACK("model-1"), {
      transition_key: "rollback-model",
    });
    expect(put).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.CURRENT, { document: {} });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.SIMULATE, { document: {} });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.ROLLBACK, {
      version: 2,
      change_reason: "rollback",
    });
    expect(get).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.EXPORT);
  });

  it("normalizes nested v2 failures with correlation and quota detail", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("failed", 429, {
        error: {
          code: "quota_exhausted",
          message: "Quota exhausted",
          detail: { quota: { resource: "pages", remaining: 0, reset_at: null } },
          correlation_id: "corr-quota",
        },
      })
    );
    const error = await documentIntelligenceService
      .getHealth()
      .catch((failure: unknown) => failure);
    expect(error).toBeInstanceOf(DocumentIntelligenceApiError);
    if (!(error instanceof DocumentIntelligenceApiError))
      throw new Error("Expected normalized module error");
    expect(error.code).toBe("quota_exhausted");
    expect(error.correlationId).toBe("corr-quota");
    expect(error.detail.quota?.remaining).toBe(0);
  });
});
