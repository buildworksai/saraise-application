/* eslint-disable max-lines-per-function -- service request coverage intentionally keeps related endpoint assertions together. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { multiCompanyService } from "./multi-company-service";

const clientMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
vi.mock("@/services/api-client", () => ({
  apiClient: clientMocks,
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public details?: unknown,
      public code?: string,
      public correlationId?: string
    ) {
      super(message);
    }
  },
}));

const meta = { correlation_id: "corr-1", timestamp: "2026-07-23T00:00:00Z" };

describe("multiCompanyService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps only governed paginated responses and preserves support metadata", async () => {
    clientMocks.get.mockResolvedValue({
      data: [],
      meta: {
        ...meta,
        pagination: {
          count: 27,
          page: 2,
          page_size: 25,
          total_pages: 2,
          has_next: false,
          has_previous: true,
        },
      },
    });
    const result = await multiCompanyService.listCompanies({ page: 2, search: "ACME" });
    expect(clientMocks.get).toHaveBeenCalledWith(
      "/api/v2/multi-company/companies/?page=2&search=ACME"
    );
    expect(result.meta.correlation_id).toBe("corr-1");
    expect(result.pagination.count).toBe(27);
  });

  it("fails explicitly when a list response is malformed instead of fabricating an empty result", async () => {
    clientMocks.get.mockResolvedValue({ results: [] });
    await expect(multiCompanyService.listTransactions()).rejects.toMatchObject({
      status: 502,
      code: "INVALID_API_ENVELOPE",
    });
  });

  it("sends idempotency evidence for durable financial commands", async () => {
    clientMocks.post.mockResolvedValue({ data: { id: "job-1" }, meta });
    await multiCompanyService.postTransaction(
      "transaction-1",
      { expected_version: 4, transition_key: "transition-1" },
      "idem-1"
    );
    expect(clientMocks.post).toHaveBeenCalledWith(
      "/api/v2/multi-company/transactions/transaction-1/post/",
      { expected_version: 4, transition_key: "transition-1" },
      { headers: { "Idempotency-Key": "idem-1" } }
    );
  });

  it("keeps delete, hierarchy, and consolidation query boundaries explicit", async () => {
    clientMocks.get.mockResolvedValue({
      data: [],
      meta: {
        ...meta,
        pagination: {
          count: 0,
          page: 1,
          page_size: 25,
          total_pages: 1,
          has_next: false,
          has_previous: false,
        },
      },
    });
    clientMocks.delete.mockResolvedValue({ data: null, meta });

    await multiCompanyService.getHierarchy("company/root");
    await multiCompanyService.listSubsidiaries("company-1", true);
    await multiCompanyService.listConsolidationGroup("North America", {
      page: 3,
      ordering: "-created_at",
    });
    await multiCompanyService.deleteCompany("company-1", 7);

    expect(clientMocks.get).toHaveBeenNthCalledWith(
      1,
      "/api/v2/multi-company/companies/hierarchy/?root_company_id=company%2Froot"
    );
    expect(clientMocks.get).toHaveBeenNthCalledWith(
      2,
      "/api/v2/multi-company/companies/company-1/subsidiaries/?recursive=true"
    );
    expect(clientMocks.get).toHaveBeenNthCalledWith(
      3,
      "/api/v2/multi-company/companies/consolidation-groups/North%20America/?page=3&ordering=-created_at"
    );
    expect(clientMocks.delete).toHaveBeenCalledWith(
      "/api/v2/multi-company/companies/company-1/?expected_version=7"
    );
  });

  it("separates configuration preview, rollback, export, and import contracts", async () => {
    const exported = {
      format: "saraise.multi-company.configuration",
      format_version: "1.0",
      environment: "production",
      schema_version: "2026.1",
      source_version: 12,
      settings: { feature_flags: { consolidation: true } },
      change_summary: "export current production policy",
      signature: "sig",
    };
    clientMocks.get.mockResolvedValue({ data: exported, meta });
    clientMocks.post.mockResolvedValue({ data: { id: "config-1" }, meta });

    await multiCompanyService.previewConfiguration("config-1");
    await multiCompanyService.rollbackConfiguration("config-1", {
      transition_key: "rollback-10",
      change_summary: "Rollback unsafe pricing tolerance",
    });
    await multiCompanyService.exportConfiguration("production", 12);
    await multiCompanyService.importConfiguration(exported as never);

    expect(clientMocks.post).toHaveBeenNthCalledWith(
      1,
      "/api/v2/multi-company/configuration/versions/config-1/preview/",
      undefined,
      undefined
    );
    expect(clientMocks.post).toHaveBeenNthCalledWith(
      2,
      "/api/v2/multi-company/configuration/versions/config-1/rollback/",
      {
        transition_key: "rollback-10",
        change_summary: "Rollback unsafe pricing tolerance",
      },
      undefined
    );
    expect(clientMocks.get).toHaveBeenCalledWith(
      "/api/v2/multi-company/configuration/export/?environment=production&version=12"
    );
    expect(clientMocks.post).toHaveBeenNthCalledWith(
      3,
      "/api/v2/multi-company/configuration/import/",
      { document: exported },
      undefined
    );
  });

  it("attaches idempotency keys to create and reversal commands that mutate accounting state", async () => {
    clientMocks.post.mockResolvedValue({ data: { id: "resource-1" }, meta });

    await multiCompanyService.createCompany({
      company_code: "ACME",
      company_name: "Acme",
      legal_name: "Acme Inc.",
      currency: "USD",
      idempotency_key: "company-key",
    });
    await multiCompanyService.createTransferPricingRule({
      name: "Cost plus",
      source_company_id: "source-1",
      target_company_id: "target-1",
      product_category: "services",
      transaction_type: "service",
      pricing_method: "cost_plus",
      parameters: { operating_cost: "100.00" },
      effective_from: "2026-08-01",
      idempotency_key: "pricing-key",
    });
    await multiCompanyService.reverseTransaction(
      "transaction-1",
      { expected_version: 3, transition_key: "reverse-1", reason: "Duplicate posting" },
      "reverse-key"
    );

    expect(clientMocks.post).toHaveBeenNthCalledWith(
      1,
      "/api/v2/multi-company/companies/",
      expect.objectContaining({ idempotency_key: "company-key" }),
      { headers: { "Idempotency-Key": "company-key" } }
    );
    expect(clientMocks.post).toHaveBeenNthCalledWith(
      2,
      "/api/v2/multi-company/transfer-pricing-rules/",
      expect.objectContaining({ idempotency_key: "pricing-key" }),
      { headers: { "Idempotency-Key": "pricing-key" } }
    );
    expect(clientMocks.post).toHaveBeenNthCalledWith(
      3,
      "/api/v2/multi-company/transactions/transaction-1/reverse/",
      { expected_version: 3, transition_key: "reverse-1", reason: "Duplicate posting" },
      { headers: { "Idempotency-Key": "reverse-key" } }
    );
  });
});
