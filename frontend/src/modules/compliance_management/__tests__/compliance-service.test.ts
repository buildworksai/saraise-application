/* eslint-disable @typescript-eslint/unbound-method -- Vitest replaces and inspects singleton client methods intentionally. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import type {
  ComplianceConfigurationDocument,
  ComplianceConfigurationRevision,
  PaginatedEnvelope,
  SuccessEnvelope,
} from "../contracts";
import {
  ComplianceContractError,
  createIdempotencyKey,
  complianceService,
  fieldError,
  serializeQuery,
} from "../services/compliance-service";

vi.mock("@/services/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
const meta = {
  correlation_id: "8ca11dd6-1d4b-45eb-b9e6-9889df6be4df",
  timestamp: "2026-07-23T00:00:00Z",
};
const successEnvelope = <T>(data: T): SuccessEnvelope<T> => ({ data, meta });
const emptyPage = <T>(): PaginatedEnvelope<T> => ({
  data: [],
  meta: {
    ...meta,
    pagination: {
      page: 1,
      page_size: 25,
      count: 0,
      total_pages: 0,
      has_next: false,
      has_previous: false,
    },
  },
});

const configurationDocument: ComplianceConfigurationDocument = {
  policy_code_prefix: "POL",
  default_review_frequency_days: 365,
  expiry_warning_days: 45,
  evidence_warning_days: 30,
  minimum_assessment_note_length: 20,
  allow_external_evidence_urls: true,
  bulk_import_row_limit: 500,
  regulation_categories: ["security"],
  rollout: { frameworks: { enabled: true, roles: ["admin"], cohorts: ["beta"] } },
};

const configurationRevision: ComplianceConfigurationRevision = {
  id: "configuration-1",
  environment: "staging",
  version: 2,
  status: "draft",
  ...configurationDocument,
  document: configurationDocument,
  created_by: "admin-1",
  created_at: "2026-08-01T00:00:00Z",
  activated_at: null,
  activated_by: null,
};

describe("compliance service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("preserves pagination metadata and serializes typed filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [],
      meta: {
        ...meta,
        pagination: {
          page: 2,
          page_size: 25,
          count: 30,
          total_pages: 2,
          has_next: false,
          has_previous: true,
        },
      },
    });
    const result = await complianceService.policies.list({
      page: 2,
      status: "draft",
      search: "privacy",
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.POLICIES.LIST}?page=2&status=draft&search=privacy`
    );
    expect(result.meta.pagination.count).toBe(30);
  });

  it("rejects malformed responses instead of fabricating an empty list", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ results: [] });
    await expect(complianceService.frameworks.list()).rejects.toBeInstanceOf(
      ComplianceContractError
    );
  });

  it("sends the transition key as the Idempotency-Key header", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "policy-1" }, meta });
    await complianceService.policies.transition("policy-1", "submit", {
      transition_key: "transition-1",
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.POLICIES.SUBMIT("policy-1"),
      { transition_key: "transition-1" },
      { headers: { "Idempotency-Key": "transition-1" } }
    );
  });

  it("omits blank query values deterministically", () => {
    expect(serializeQuery("/items/", { search: "", page: 1, status: undefined })).toBe(
      "/items/?page=1"
    );
  });
});

describe("compliance service framework and requirement endpoints", () => {
  beforeEach(() => vi.clearAllMocks());

  it("routes framework and requirement methods to stable endpoints with explicit mutation keys", async () => {
    const success = successEnvelope({ id: "record-1" });
    vi.mocked(apiClient.get).mockResolvedValue(success);
    vi.mocked(apiClient.post).mockResolvedValue(success);
    vi.mocked(apiClient.patch).mockResolvedValue(success);
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await complianceService.frameworks.get("framework-1");
    await complianceService.frameworks.create({
      code: "SOC2",
      name: "SOC 2",
      version: "2026",
      category: "security",
      source_kind: "custom",
    });
    await complianceService.frameworks.update("framework-1", { name: "SOC 2 2026" });
    await complianceService.frameworks.archive("framework-1");
    await complianceService.frameworks.activate("framework-1", { transition_key: "fw-activate" });
    await complianceService.frameworks.status("framework-1");
    await complianceService.frameworks.export("framework-1");
    await complianceService.frameworks.import(
      {
        schema: "saraise.compliance.framework/v1",
        framework: {
          code: "ISO",
          name: "ISO 27001",
          version: "2026",
          category: "security",
          source_kind: "imported",
        },
        requirements: [],
      },
      "framework-import"
    );

    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.FRAMEWORKS.DETAIL("framework-1"));
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.FRAMEWORKS.UPDATE("framework-1"), {
      name: "SOC 2 2026",
    });
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.FRAMEWORKS.DELETE("framework-1"));
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.FRAMEWORKS.ACTIVATE("framework-1"),
      { transition_key: "fw-activate" },
      { headers: { "Idempotency-Key": "fw-activate" } }
    );
    const frameworkImportCall = vi
      .mocked(apiClient.post)
      .mock.calls.find(([path]) => path === ENDPOINTS.FRAMEWORKS.IMPORT);
    expect(frameworkImportCall?.[1]).toMatchObject({
      package: { schema: "saraise.compliance.framework/v1" },
    });
    expect(frameworkImportCall?.[2]).toEqual({
      headers: { "Idempotency-Key": "framework-import" },
    });

    await complianceService.requirements.get("requirement-1");
    await complianceService.requirements.create({
      framework_id: "framework-1",
      code: "CC1.1",
      title: "Governance",
      description: "Governance is defined.",
    });
    await complianceService.requirements.update("requirement-1", { title: "Updated" });
    await complianceService.requirements.archive("requirement-1");
    await complianceService.requirements.restore("requirement-1", {
      transition_key: "restore-requirement",
    });
    await complianceService.requirements.import(
      {
        framework_id: "framework-1",
        rows: [
          {
            framework_id: "framework-1",
            code: "CC2.1",
            title: "Communication",
            description: "Communication is documented.",
          },
        ],
      },
      "requirements-import"
    );

    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.REQUIREMENTS.RESTORE("requirement-1"),
      { transition_key: "restore-requirement" },
      { headers: { "Idempotency-Key": "restore-requirement" } }
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.REQUIREMENTS.IMPORT,
      expect.objectContaining({ framework_id: "framework-1" }),
      { headers: { "Idempotency-Key": "requirements-import" } }
    );
  });
});

describe("compliance service policy lifecycle endpoints", () => {
  beforeEach(() => vi.clearAllMocks());

  it("routes policy lifecycle methods to stable endpoints with explicit mutation keys", async () => {
    const success = successEnvelope({ id: "record-1" });
    vi.mocked(apiClient.get).mockResolvedValue(success);
    vi.mocked(apiClient.post).mockResolvedValue(success);
    vi.mocked(apiClient.patch).mockResolvedValue(success);
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await complianceService.policies.get("policy-1");
    await complianceService.policies.create({
      code: "POL-1",
      title: "Policy",
      category: "security",
    });
    await complianceService.policies.update("policy-1", { summary: "Updated" });
    await complianceService.policies.archive("policy-1");
    await complianceService.policies.createVersion(
      "policy-1",
      { content: "body", change_summary: "Initial" },
      "policy-version"
    );
    await complianceService.policies.transition("policy-1", "request-changes", {
      transition_key: "policy-request-changes",
      reason: "Needs more evidence",
    });
    await complianceService.policies.transition("policy-1", "approve", {
      transition_key: "policy-approve",
    });
    await complianceService.policies.transition("policy-1", "publish", {
      transition_key: "policy-publish",
    });
    await complianceService.policies.revise("policy-1", {
      content: "next",
      change_summary: "Revision",
      transition_key: "policy-revise",
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.POLICIES.VERSIONS("policy-1"),
      { content: "body", change_summary: "Initial" },
      { headers: { "Idempotency-Key": "policy-version" } }
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.POLICIES.REQUEST_CHANGES("policy-1"),
      { transition_key: "policy-request-changes", reason: "Needs more evidence" },
      { headers: { "Idempotency-Key": "policy-request-changes" } }
    );
  });
});

describe("compliance service mapping, assessment, and evidence endpoints", () => {
  beforeEach(() => vi.clearAllMocks());

  it("routes mapping, assessment, and evidence methods to governed endpoints", async () => {
    const success = successEnvelope({ id: "record-1" });
    vi.mocked(apiClient.get).mockResolvedValue(success);
    vi.mocked(apiClient.post).mockResolvedValue(success);
    vi.mocked(apiClient.patch).mockResolvedValue(success);
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await complianceService.mappings.get("mapping-1");
    await complianceService.mappings.create(
      { requirement_id: "requirement-1", policy_id: "policy-1", coverage: "full" },
      "mapping-create"
    );
    await complianceService.mappings.update("mapping-1", { coverage: "partial" });
    await complianceService.mappings.remove("mapping-1");
    await complianceService.mappings.bulk(
      { rows: [{ requirement_id: "requirement-1", policy_id: "policy-1", coverage: "full" }] },
      "mapping-bulk"
    );
    await complianceService.mappings.gaps("framework-1", "2026-08-01");

    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.MAPPINGS.BULK,
      { rows: [{ requirement_id: "requirement-1", policy_id: "policy-1", coverage: "full" }] },
      { headers: { "Idempotency-Key": "mapping-bulk" } }
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.GAPS}?framework_id=framework-1&as_of=2026-08-01`
    );

    await complianceService.assessments.get("assessment-1");
    await complianceService.assessments.create(
      { requirement_id: "requirement-1", status: "partial", notes: "Some evidence missing." },
      "assessment-create"
    );
    await complianceService.assessments.scorecard("framework-1", "2026-08-01");
    await complianceService.evidence.get("evidence-1");
    await complianceService.evidence.create({
      name: "SOC report",
      evidence_type: "report",
      reference_kind: "external_url",
      external_uri: "https://example.invalid/soc.pdf",
      classification: "confidential",
    });
    await complianceService.evidence.update("evidence-1", { classification: "restricted" });
    await complianceService.evidence.archive("evidence-1");
    await complianceService.evidence.validate("evidence-1", "evidence-validate");
    await complianceService.evidence.link("evidence-1", {
      requirement_id: "requirement-1",
      relevance: "primary",
    });
    await complianceService.evidence.unlink("link-1");

    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.EVIDENCE.VALIDATE("evidence-1"),
      {},
      { headers: { "Idempotency-Key": "evidence-validate" } }
    );
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.EVIDENCE_LINKS.DELETE("link-1"));
  });
});

describe("compliance service configuration endpoints", () => {
  beforeEach(() => vi.clearAllMocks());

  it("normalizes configuration documents across list, write, preview, and import workflows", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: [configurationRevision],
      meta: {
        ...meta,
        pagination: {
          page: 1,
          page_size: 25,
          count: 1,
          total_pages: 1,
          has_next: false,
          has_previous: false,
        },
      },
    });
    const listed = await complianceService.configuration.list({ environment: "staging" });
    expect(listed.data[0]?.document).toEqual(configurationDocument);

    vi.mocked(apiClient.get).mockResolvedValue(successEnvelope(configurationRevision));
    vi.mocked(apiClient.post).mockResolvedValue(successEnvelope(configurationRevision));
    vi.mocked(apiClient.patch).mockResolvedValue(successEnvelope(configurationRevision));
    await complianceService.configuration.get("configuration-1");
    await complianceService.configuration.create({
      environment: "staging",
      document: listed.data[0]?.document ?? configurationDocument,
    });
    await complianceService.configuration.update("configuration-1", {
      environment: "production",
      document: listed.data[0]?.document ?? configurationDocument,
    });
    await complianceService.configuration.preview("configuration-1");
    await complianceService.configuration.activate("configuration-1", {
      transition_key: "configuration-activate",
    });
    await complianceService.configuration.rollback("configuration-1", {
      transition_key: "configuration-rollback",
    });
    await complianceService.configuration.export("configuration-1");
    await complianceService.configuration.import(
      {
        schema: "saraise.compliance.configuration/v1",
        environment: "staging",
        configuration: listed.data[0]?.document ?? configurationDocument,
      },
      "configuration-import"
    );

    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.CREATE,
      expect.objectContaining({
        environment: "staging",
        policy_code_prefix: "POL",
        default_review_frequency_days: 365,
        rollout: { frameworks: { enabled: true, roles: ["admin"], cohorts: ["beta"] } },
      }),
      undefined
    );
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.UPDATE("configuration-1"),
      expect.objectContaining({ environment: "production", policy_code_prefix: "POL" })
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.ACTIVATE("configuration-1"),
      { transition_key: "configuration-activate" },
      { headers: { "Idempotency-Key": "configuration-activate" } }
    );
    const importCall = vi
      .mocked(apiClient.post)
      .mock.calls.find(([path]) => path === ENDPOINTS.CONFIGURATION.IMPORT);
    expect(importCall?.[1]).toMatchObject({
      document: { schema: "saraise.compliance.configuration/v1" },
    });
    expect(importCall?.[2]).toEqual({ headers: { "Idempotency-Key": "configuration-import" } });
  });
});

describe("compliance service activity and utility endpoints", () => {
  beforeEach(() => vi.clearAllMocks());

  it("covers activity, dashboard, jobs, generated idempotency keys, and stable field errors", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(emptyPage());
    await complianceService.activity({ entity_type: "policy", correlation_id: "corr-1" });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.ACTIVITY}?entity_type=policy&correlation_id=corr-1`
    );

    vi.mocked(apiClient.get).mockResolvedValue(successEnvelope({ id: "job-1" }));
    await complianceService.dashboard("framework-1", "2026-08-01");
    await complianceService.job("job-1");
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.DASHBOARD}?framework_id=framework-1&as_of=2026-08-01`
    );
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.JOB("job-1"));

    const randomUUID = vi.fn(() => "uuid-1");
    vi.stubGlobal("crypto", { randomUUID });
    expect(createIdempotencyKey("evidence")).toBe("compliance-ui:evidence:uuid-1");
    vi.unstubAllGlobals();

    expect(
      fieldError(
        {
          details: {
            error: {
              code: "invalid",
              message: "Invalid",
              field_errors: [{ field: "code", code: "required", message: "Code is required." }],
            },
          },
        },
        "code"
      )
    ).toBe("Code is required.");
    expect(fieldError(new Error("plain"), "code")).toBeUndefined();
  });
});
