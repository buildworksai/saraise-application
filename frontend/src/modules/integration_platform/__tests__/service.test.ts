/* eslint-disable @typescript-eslint/no-unsafe-assignment, max-lines-per-function -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ENDPOINTS } from "../contracts";
import type { IntegrationPlatformConfigurationDocument } from "../contracts";

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
const configDocument: IntegrationPlatformConfigurationDocument = {
  schema_version: 1,
  environment: "production",
  adapter: {
    spi_version: "1",
    capabilities: ["test", "pull", "push", "receive", "deliver"],
    adapter_key_max_length: 80,
    cursor_max_length: 255,
  },
  transformations: {
    operations: ["rename", "trim", "string_case", "number", "date_format", "default", "enum_map"],
    string_case_modes: ["upper", "lower"],
    number_modes: ["integer"],
    default_number_mode: "integer",
    default_input_date_format: "iso",
    allow_unmapped_enum: false,
    max_chain_length: 3,
  },
  validation: {
    name_max_length: 120,
    description_max_length: 500,
    credential_max_length: 128,
    url_max_length: 500,
    event_name_pattern: "^[a-z.]+$",
    event_name_max_length: 64,
    nonce_max_length: 64,
    signature_max_length: 128,
    error_code_max_length: 64,
  },
  security: {
    connector_access_policy: "explicit_entitlement",
    secret_field_names: ["token"],
    signature_window_seconds: 300,
    payload_max_bytes: 65536,
    credential_hint_characters: 4,
    signing_secret_bytes: 32,
    outbound_nonce_bytes: 16,
    diagnostic_fields: ["status"],
  },
  webhooks: {
    timeout_seconds_default: 10,
    timeout_seconds_min: 1,
    timeout_seconds_max: 30,
    max_attempts_default: 3,
    max_attempts_min: 1,
    max_attempts_max: 10,
    success_status_min: 200,
    success_status_max: 299,
    retry_statuses: [429],
    retry_server_error_min: 500,
    retry_delay_max_seconds: 60,
    connect_timeout_max_seconds: 5,
    http_client_retries: 2,
    inbound_rate: "60/min",
  },
  synchronization: {
    directions: ["pull", "push"],
    active_statuses: ["active"],
    pull_batch_limit: 500,
    quota_cost: 1,
  },
  workflows: {
    integration_delete_statuses: ["inactive", "error"],
    integration_activation_statuses: ["inactive"],
    activation_requires_successful_test: true,
    integration_transitions: { inactive: ["activate"], active: ["deactivate"] },
    credential_transitions: { active: ["revoke"] },
    webhook_transitions: { inactive: ["activate"], active: ["deactivate"] },
    delivery_transitions: { dead_letter: ["redrive"] },
  },
  jobs: { poll_after_ms: 1000, progress_min: 0, progress_max: 100, terminal_progress: 100 },
  list: {
    page_size: 25,
    connector_page_size: 50,
    refresh_interval_ms: 30000,
    active_delivery_poll_ms: 5000,
    integration_poll_ms: 5000,
    integration_ordering: "-updated_at",
    integration_ordering_fields: ["name", "-updated_at"],
    webhook_ordering: "-updated_at",
    webhook_ordering_fields: ["name"],
    delivery_ordering: "-created_at",
    mapping_ordering: "position",
    mapping_ordering_fields: ["position"],
  },
  quotas: { sync_jobs: 100 },
  mapping: { default_position: 0, default_required: false, preview_record_limit: 5 },
  health: { probe_timeout_seconds: 3, broker_acknowledgement_seconds: 2 },
  feature_flags: { push_synchronization: { enabled: true, roles: [], cohorts: [] } },
  navigation: {
    base_order: 10,
    route_order: {},
    status_positive: ["active", "available", "delivered", "healthy", "closed", "succeeded"],
    status_warning: ["testing", "retrying", "locked"],
    status_danger: ["error", "dead_letter", "unavailable", "failed"],
  },
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

  it("routes integration lifecycle, credentials, connectors, and health reads through registry endpoints", async () => {
    const integration = { id: "integration-id", name: "Warehouse", version: 3 };
    const credential = { id: "credential-id", integration_id: "integration-id", version: 1 };
    const connector = { id: "connector-id", name: "ERP connector" };
    const schema = { id: "schema-id", fields: [] };
    const health = { status: "healthy", checked_at: meta.timestamp };
    const job = {
      job_id: "68234291-2212-42e2-b236-fbc305e54a8e",
      status: "succeeded",
      correlation_id: "corr-1",
    };
    api.post
      .mockResolvedValueOnce({ data: integration, meta })
      .mockResolvedValueOnce({ data: integration, meta })
      .mockResolvedValueOnce({ data: integration, meta })
      .mockResolvedValueOnce({ data: credential, meta })
      .mockResolvedValueOnce({ data: credential, meta });
    api.get
      .mockResolvedValueOnce({ data: integration, meta })
      .mockResolvedValueOnce({ data: job, meta })
      .mockResolvedValueOnce({ data: [credential], meta })
      .mockResolvedValueOnce({ data: credential, meta })
      .mockResolvedValueOnce({ data: connector, meta })
      .mockResolvedValueOnce({ data: schema, meta })
      .mockResolvedValueOnce({ data: health, meta })
      .mockResolvedValueOnce({ data: health, meta })
      .mockResolvedValueOnce({ data: { can_manage: true }, meta });
    api.delete.mockResolvedValueOnce(undefined);

    await service.createIntegration({
      name: "Warehouse",
    } as Parameters<typeof service.createIntegration>[0]);
    await service.getIntegration("integration-id");
    await service.deleteIntegration("integration-id");
    await service.activateIntegration("integration-id", { transition_key: "activate-key" });
    await service.deactivateIntegration("integration-id", { transition_key: "deactivate-key" });
    await service.getIntegrationJob("integration-id", job.job_id);
    await service.listCredentials("integration-id");
    await service.createCredential("integration-id", {
      credential_type: "api_key",
      plaintext: "secret",
    } as Parameters<typeof service.createCredential>[1]);
    await service.getCredential("credential-id");
    await service.revokeCredential("credential-id", { transition_key: "revoke-key" });
    await service.getConnector("connector-id");
    await service.getConnectorSchema("connector-id");
    await service.getConnectorHealth("connector-id");
    await service.getHealth();
    await service.getManageCapability();

    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.INTEGRATIONS.CREATE, {
      name: "Warehouse",
    });
    expect(api.get).toHaveBeenNthCalledWith(1, ENDPOINTS.INTEGRATIONS.DETAIL("integration-id"));
    expect(api.delete).toHaveBeenCalledWith(ENDPOINTS.INTEGRATIONS.DELETE("integration-id"));
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.INTEGRATIONS.ACTIVATE("integration-id"), {
      transition_key: "activate-key",
    });
    expect(api.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.INTEGRATIONS.DEACTIVATE("integration-id"),
      { transition_key: "deactivate-key" }
    );
    expect(api.get).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.INTEGRATIONS.JOB("integration-id", job.job_id)
    );
    expect(api.get).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.INTEGRATIONS.CREDENTIALS("integration-id")
    );
    expect(api.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.INTEGRATIONS.CREDENTIALS("integration-id"),
      { credential_type: "api_key", plaintext: "secret" }
    );
    expect(api.get).toHaveBeenNthCalledWith(4, ENDPOINTS.CREDENTIALS.DETAIL("credential-id"));
    expect(api.post).toHaveBeenNthCalledWith(5, ENDPOINTS.CREDENTIALS.REVOKE("credential-id"), {
      transition_key: "revoke-key",
    });
    expect(api.get).toHaveBeenNthCalledWith(5, ENDPOINTS.CONNECTORS.DETAIL("connector-id"));
    expect(api.get).toHaveBeenNthCalledWith(6, ENDPOINTS.CONNECTORS.SCHEMA("connector-id"));
    expect(api.get).toHaveBeenNthCalledWith(7, ENDPOINTS.CONNECTORS.HEALTH("connector-id"));
    expect(api.get).toHaveBeenNthCalledWith(8, ENDPOINTS.HEALTH);
    expect(api.get).toHaveBeenNthCalledWith(9, ENDPOINTS.CONFIGURATION.MANAGE_CAPABILITY);
  });

  it("routes webhook delivery, mapping, and configuration write behaviors through governed endpoints", async () => {
    const webhook = { id: "webhook-id", status: "active" };
    const delivery = { id: "delivery-id", status: "failed" };
    const mapping = { id: "mapping-id", name: "Customer mapping" };
    const configuration = {
      id: "config-id",
      environment: "production",
      version: 3,
      tenant_id: "tenant-id",
      document: configDocument,
      updated_at: meta.timestamp,
      updated_by: "operator",
    };
    api.get
      .mockResolvedValueOnce({ data: webhook, meta })
      .mockResolvedValueOnce({ data: delivery, meta })
      .mockResolvedValueOnce({ data: mapping, meta })
      .mockResolvedValueOnce({ data: configuration, meta })
      .mockResolvedValueOnce({ data: configuration, meta });
    api.patch.mockResolvedValueOnce({ data: webhook, meta });
    api.post
      .mockResolvedValueOnce({ data: { secret: "once" }, meta }) // pragma: allowlist secret
      .mockResolvedValueOnce({ data: webhook, meta })
      .mockResolvedValueOnce({ data: webhook, meta })
      .mockResolvedValueOnce({ data: { secret: "rotated" }, meta }) // pragma: allowlist secret
      .mockResolvedValueOnce({ data: delivery, meta })
      .mockResolvedValueOnce({ data: mapping, meta })
      .mockResolvedValueOnce({ data: { valid: true }, meta })
      .mockResolvedValueOnce({ data: { output: [] }, meta })
      .mockResolvedValueOnce({ data: configuration, meta })
      .mockResolvedValueOnce({ data: { valid: true, diff: [] }, meta })
      .mockResolvedValueOnce({ data: configuration, meta });
    api.delete.mockResolvedValueOnce(undefined);

    await service.createWebhook({ name: "Inbound" } as Parameters<typeof service.createWebhook>[0]);
    await service.getWebhook("webhook-id");
    await service.updateWebhook("webhook-id", { name: "Inbound updated" });
    await service.deleteWebhook("webhook-id");
    await service.activateWebhook("webhook-id", { transition_key: "activate-webhook-key" });
    await service.deactivateWebhook("webhook-id", { transition_key: "deactivate-webhook-key" });
    await service.rotateWebhookSecret("webhook-id", { transition_key: "rotate-webhook-key" });
    await service.listDeliveries({ webhook_id: "webhook-id", status: "dead_letter" });
    await service.getDelivery("delivery-id");
    await service.redriveDelivery("delivery-id", { transition_key: "redrive-key" });
    await service.listMappings({ integration_id: "integration-id", source_field: "email" });
    await service.createMapping({ name: "Customer mapping" } as Parameters<
      typeof service.createMapping
    >[0]);
    await service.getMapping("mapping-id");
    await service.validateMappings({
      integration_id: "integration-id",
      mappings: [],
      source_schema: { type: "object", properties: {} },
      target_schema: { type: "object", properties: {} },
    });
    await service.previewMappings({
      integration_id: "integration-id",
      mapping_ids: ["mapping-id"],
      sample: { email: "ada@example.com" },
    });
    await service.getConfiguration();
    await service.saveConfiguration({
      environment: "production",
      document: configDocument,
    });
    await service.previewConfiguration({
      environment: "production",
      document: configDocument,
    });
    await service.importConfiguration({
      environment: "production",
      document: configDocument,
    });
    await service.exportConfiguration();

    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.WEBHOOKS.CREATE, { name: "Inbound" });
    expect(api.get).toHaveBeenNthCalledWith(1, ENDPOINTS.WEBHOOKS.DETAIL("webhook-id"));
    expect(api.patch).toHaveBeenCalledWith(ENDPOINTS.WEBHOOKS.UPDATE("webhook-id"), {
      name: "Inbound updated",
    });
    expect(api.delete).toHaveBeenCalledWith(ENDPOINTS.WEBHOOKS.DELETE("webhook-id"));
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.WEBHOOKS.ACTIVATE("webhook-id"), {
      transition_key: "activate-webhook-key",
    });
    expect(api.post).toHaveBeenNthCalledWith(3, ENDPOINTS.WEBHOOKS.DEACTIVATE("webhook-id"), {
      transition_key: "deactivate-webhook-key",
    });
    expect(api.post).toHaveBeenNthCalledWith(4, ENDPOINTS.WEBHOOKS.ROTATE_SECRET("webhook-id"), {
      transition_key: "rotate-webhook-key",
    });
    expect(api.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.DELIVERIES.LIST}?webhook_id=webhook-id&status=dead_letter`
    );
    expect(api.get).toHaveBeenNthCalledWith(3, ENDPOINTS.DELIVERIES.DETAIL("delivery-id"));
    expect(api.post).toHaveBeenNthCalledWith(5, ENDPOINTS.DELIVERIES.REDRIVE("delivery-id"), {
      transition_key: "redrive-key",
    });
    expect(api.get).toHaveBeenNthCalledWith(
      4,
      `${ENDPOINTS.MAPPINGS.LIST}?integration_id=integration-id&source_field=email`
    );
    expect(api.post).toHaveBeenNthCalledWith(6, ENDPOINTS.MAPPINGS.CREATE, {
      name: "Customer mapping",
    });
    expect(api.get).toHaveBeenNthCalledWith(5, ENDPOINTS.MAPPINGS.DETAIL("mapping-id"));
    expect(api.post).toHaveBeenNthCalledWith(7, ENDPOINTS.MAPPINGS.VALIDATE, {
      integration_id: "integration-id",
      mappings: [],
      source_schema: { type: "object", properties: {} },
      target_schema: { type: "object", properties: {} },
    });
    expect(api.post).toHaveBeenNthCalledWith(8, ENDPOINTS.MAPPINGS.PREVIEW, {
      integration_id: "integration-id",
      mapping_ids: ["mapping-id"],
      sample: { email: "ada@example.com" },
    });
    expect(api.get).toHaveBeenNthCalledWith(6, ENDPOINTS.CONFIGURATION.CURRENT);
    expect(api.post).toHaveBeenNthCalledWith(9, ENDPOINTS.CONFIGURATION.CURRENT, {
      environment: "production",
      document: configDocument,
    });
    expect(api.post).toHaveBeenNthCalledWith(10, ENDPOINTS.CONFIGURATION.PREVIEW, {
      environment: "production",
      document: configDocument,
    });
    expect(api.post).toHaveBeenNthCalledWith(11, ENDPOINTS.CONFIGURATION.IMPORT, {
      environment: "production",
      document: configDocument,
    });
    expect(api.get).toHaveBeenNthCalledWith(7, ENDPOINTS.CONFIGURATION.EXPORT);
  });

  it("serializes every delivery filter and redrives only with explicit transition evidence", async () => {
    const delivery = {
      id: "delivery-id",
      webhook_id: "webhook-id",
      webhook_name: "Outbound CRM",
      event: "lead.created",
      status: "dead_letter",
      attempt_count: 5,
      max_attempts: 5,
      next_attempt_at: null,
      response_code: null,
      error_code: "HTTP_503",
      duration_ms: null,
      job_id: "delivery-job",
      correlation_id: "corr-dead",
      delivered_at: null,
      created_at: meta.timestamp,
      updated_at: meta.timestamp,
      payload: { lead: "redacted" },
      payload_hash: "hash",
      idempotency_key: "idem",
      error_message: "provider unavailable",
      transition_history: [],
      attempts: [],
    };
    api.get.mockResolvedValueOnce({ data: [delivery], meta: { ...meta, pagination } });
    api.post.mockResolvedValueOnce({ data: delivery, meta });

    await service.listDeliveries({
      page: 3,
      page_size: 10,
      webhook_id: "webhook-id",
      status: "dead_letter",
      event: "lead.created",
      created_after: "2026-07-22T10:00:00Z",
      created_before: "2026-07-22T11:00:00Z",
    });
    await service.redriveDelivery("delivery-id", { transition_key: "redrive-key" });

    expect(api.get).toHaveBeenCalledWith(
      `${ENDPOINTS.DELIVERIES.LIST}?page=3&page_size=10&webhook_id=webhook-id&status=dead_letter&event=lead.created&created_after=2026-07-22T10%3A00%3A00Z&created_before=2026-07-22T11%3A00%3A00Z`
    );
    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.DELIVERIES.REDRIVE("delivery-id"), {
      transition_key: "redrive-key",
    });
  });
});
