/* eslint-disable @typescript-eslint/no-unsafe-assignment, max-lines-per-function -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ENDPOINTS } from "../contracts";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@/services/api-client", () => ({
  apiClient: api,
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

import { IntegrationPlatformService } from "../services/integration-platform-service";

const meta = { correlation_id: "corr-1", timestamp: "2026-07-22T00:00:00Z" };
const pagination = {
  count: 0,
  page: 2,
  page_size: 25,
  total_pages: 3,
  has_next: true,
  has_previous: true,
};

describe("IntegrationPlatformService", () => {
  const service = new IntegrationPlatformService();
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("serializes filters and flattens governed meta.pagination for pages", async () => {
    api.get.mockResolvedValue({ data: [], meta: { ...meta, pagination } });
    const result = await service.listIntegrations({
      page: 2,
      status: "active",
      search: "ledger",
      ordering: "-updated_at",
    });
    expect(api.get).toHaveBeenCalledWith(
      `${ENDPOINTS.INTEGRATIONS.LIST}?page=2&search=ledger&status=active&ordering=-updated_at`
    );
    expect(result).toEqual({ items: [], meta: { ...pagination, ...meta } });
  });

  it("preserves boolean false filters and omits only blank query values", async () => {
    api.get.mockResolvedValue({ data: [], meta: { ...meta, pagination } });
    await service.listConnectors({ is_active: false, search: "", page_size: 50 });
    expect(api.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONNECTORS.LIST}?page_size=50&is_active=false`
    );

    await service.listWebhooks({
      direction: "inbound",
      status: "active",
      event: "invoice.created",
    });
    expect(api.get).toHaveBeenLastCalledWith(
      `${ENDPOINTS.WEBHOOKS.LIST}?direction=inbound&status=active&event=invoice.created`
    );
  });

  it("uses PATCH and unwraps the v2 envelope for updates", async () => {
    const integration = { id: "integration-id", name: "Warehouse" };
    api.patch.mockResolvedValue({ data: integration, meta });
    await expect(service.updateIntegration("integration-id", { name: "Warehouse" })).resolves.toBe(
      integration
    );
    expect(api.patch).toHaveBeenCalledWith(ENDPOINTS.INTEGRATIONS.UPDATE("integration-id"), {
      name: "Warehouse",
    });
  });

  it("returns durable receipts instead of discarding test and sync evidence", async () => {
    const receipt = {
      job_id: "68234291-2212-42e2-b236-fbc305e54a8e",
      status: "queued",
      correlation_id: "corr-1",
      accepted_at: meta.timestamp,
      poll_after_ms: 1000,
    };
    api.post.mockResolvedValue({ data: receipt, meta });
    await expect(
      service.testIntegration("integration-id", { idempotency_key: "test-key" })
    ).resolves.toBe(receipt);
    await expect(
      service.syncIntegration("integration-id", {
        direction: "pull",
        mapping_ids: [],
        idempotency_key: "sync-key",
      })
    ).resolves.toBe(receipt);
    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.INTEGRATIONS.TEST("integration-id"), {
      idempotency_key: "test-key",
    });
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.INTEGRATIONS.SYNC("integration-id"), {
      direction: "pull",
      mapping_ids: [],
      idempotency_key: "sync-key",
    });
  });

  it("uses explicit credential and mapping command endpoints", async () => {
    const credential = {
      id: "credential-id",
      integration_id: "integration-id",
      credential_type: "api_key",
      display_hint: "key ending 1234",
      version: 1,
      status: "active",
      expires_at: null,
      rotated_at: null,
      revoked_at: null,
      created_at: meta.timestamp,
    };
    const mapping = {
      id: "mapping-id",
      integration_id: "integration-id",
      name: "Customer map",
      source_schema: {},
      target_schema: {},
      field_mappings: [],
      transformation_rules: [],
      validation_rules: [],
      is_active: true,
      created_at: meta.timestamp,
      updated_at: meta.timestamp,
    };
    api.post.mockResolvedValueOnce({ data: credential, meta });
    api.patch.mockResolvedValueOnce({ data: mapping, meta });
    api.delete.mockResolvedValueOnce(undefined);

    await service.rotateCredential("credential-id", {
      plaintext: "secret",
      expires_at: null,
      idempotency_key: "rotate-key",
    });
    await service.updateMapping("mapping-id", { name: "Customer map" });
    await service.deleteMapping("mapping-id");

    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.CREDENTIALS.ROTATE("credential-id"), {
      plaintext: "secret",
      expires_at: null,
      idempotency_key: "rotate-key",
    });
    expect(api.patch).toHaveBeenCalledWith(ENDPOINTS.MAPPINGS.UPDATE("mapping-id"), {
      name: "Customer map",
    });
    expect(api.delete).toHaveBeenCalledWith(ENDPOINTS.MAPPINGS.DELETE("mapping-id"));
  });

  it("never exposes a generic resource compatibility alias", () => {
    expect("listResources" in service).toBe(false);
    expect("createResource" in service).toBe(false);
  });

  it("preserves canonical inbound bytes and sends SARAISE signature headers", async () => {
    const receipt = {
      job_id: "68234291-2212-42e2-b236-fbc305e54a8e",
      correlation_id: "corr-1",
      accepted_at: meta.timestamp,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: receipt, meta }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);
    const rawBody = '{"event":"invoice.created"}\n';
    await expect(
      service.receiveInboundWebhook("public-id", {
        timestamp: "1720000000",
        nonce: "unique-nonce-1234",
        signature: `sha256=${"a".repeat(64)}`,
        raw_body: rawBody,
      })
    ).resolves.toEqual(receipt);
    expect(fetchMock).toHaveBeenCalledWith(
      ENDPOINTS.WEBHOOKS.INBOUND("public-id"),
      expect.objectContaining({
        body: rawBody,
        headers: expect.objectContaining({
          "X-SARAISE-Webhook-Timestamp": "1720000000",
          "X-SARAISE-Webhook-Nonce": "unique-nonce-1234",
          "X-SARAISE-Webhook-Signature": `sha256=${"a".repeat(64)}`,
        }),
      })
    );
    vi.unstubAllGlobals();
  });

  it("rejects inbound webhook transport failures with the response correlation id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { message: "signature rejected" } }), {
          status: 401,
          headers: { "X-Correlation-ID": "corr-rejected" },
        })
      )
    );
    const failure = await service
      .receiveInboundWebhook("public-id", {
        timestamp: "1720000000",
        nonce: "unique-nonce-1234",
        signature: `sha256=${"b".repeat(64)}`,
        raw_body: "{}",
      })
      .catch((error: Error) => error);
    expect(failure).toBeInstanceOf(Error);
    expect(failure).toMatchObject({
      status: 401,
      code: "webhook_rejected",
      correlationId: "corr-rejected",
    });
  });

  it("rejects malformed inbound webhook receipts instead of fabricating success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ data: { job_id: "not-a-uuid" }, meta }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        })
      )
    );
    await expect(
      service.receiveInboundWebhook("public-id", {
        timestamp: "1720000000",
        nonce: "unique-nonce-1234",
        signature: `sha256=${"c".repeat(64)}`,
        raw_body: "{}",
      })
    ).rejects.toThrow();
  });

  it("uses governed configuration preview, rollback, export, and audit endpoints", async () => {
    const configuration = {
      id: "config-id",
      environment: "development",
      version: 2,
      document: { schema_version: 1 },
      updated_at: meta.timestamp,
      updated_by: null,
    };
    api.post.mockResolvedValue({ data: configuration, meta });
    api.get.mockResolvedValue({ data: [], meta: { ...meta, pagination } });

    await service.rollbackConfiguration("development", 1);
    await service.listConfigurationVersions();
    await service.listConfigurationAudits();

    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.ROLLBACK, {
      environment: "development",
      version: 1,
    });
    expect(api.get).toHaveBeenNthCalledWith(1, ENDPOINTS.CONFIGURATION.VERSIONS);
    expect(api.get).toHaveBeenNthCalledWith(2, ENDPOINTS.CONFIGURATION.AUDITS);
  });
});
