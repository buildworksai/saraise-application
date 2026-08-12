/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method -- mocked API methods are assertion targets. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import { ENDPOINTS, type ApiEnvelope } from "../contracts";
import { dataMigrationService, type DataMigrationApiError } from "./data-migration-service";

vi.mock("@/services/api-client", () => {
  class MockApiError extends Error {
    constructor(
      message: string,
      readonly status: number,
      readonly details?: unknown,
      readonly code?: string,
      readonly correlationId?: string
    ) {
      super(message);
      this.name = "ApiError";
    }
  }
  return {
    ApiError: MockApiError,
    apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const meta = { correlation_id: "corr-dm-1", timestamp: "2026-07-22T00:00:00Z" };
const pagination = {
  count: 2,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

function envelope<T>(data: T): ApiEnvelope<T> {
  return { data, meta };
}

function pageEnvelope<T>(data: readonly T[]): ApiEnvelope<readonly T[]> {
  return { data, meta: { ...meta, pagination } };
}

describe("data migration v2 service", () => {
  const api = vi.mocked(apiClient);

  beforeEach(() => vi.clearAllMocks());

  it("serializes list filters and preserves pagination evidence", async () => {
    api.get.mockResolvedValueOnce(pageEnvelope([{ id: "job-1" }]));

    await expect(
      dataMigrationService.jobs.list({ search: "Customer import", status: "ready", page: 2 })
    ).resolves.toEqual({
      items: [{ id: "job-1" }],
      pagination,
      correlationId: meta.correlation_id,
    });

    expect(api.get).toHaveBeenCalledWith(
      `${ENDPOINTS.JOBS.LIST}?search=Customer+import&status=ready&page=2`
    );
  });

  it("omits empty filters while preserving explicit zero-like values in issue queries", async () => {
    api.get.mockResolvedValueOnce(pageEnvelope([{ id: "issue-1" }]));

    await dataMigrationService.runs.issues("run-1", {
      page: 1,
      page_size: 25,
      severity: undefined,
      stage: undefined,
      code: "",
      row_number: 0,
    } as Parameters<typeof dataMigrationService.runs.issues>[1]);

    expect(api.get).toHaveBeenCalledWith(
      `${ENDPOINTS.RUNS.ISSUES("run-1")}?page=1&page_size=25&row_number=0`
    );
  });

  it("fails closed when paginated endpoints omit governed pagination metadata", async () => {
    api.get.mockResolvedValueOnce(envelope([]));

    await expect(dataMigrationService.connections.list()).rejects.toMatchObject({
      status: 502,
      code: "invalid_response",
      correlationId: meta.correlation_id,
      retryable: false,
    });
  });

  it("fails closed when malformed envelopes omit data for non-paginated requests", async () => {
    api.get.mockResolvedValueOnce({ meta });

    await expect(dataMigrationService.jobs.get("job-1")).rejects.toMatchObject({
      status: 502,
      code: "invalid_response",
      correlationId: meta.correlation_id,
      retryable: false,
    });
    expect(api.get).toHaveBeenCalledWith(ENDPOINTS.JOBS.DETAIL("job-1"));
  });

  it("wraps API errors with retryability and correlation evidence", async () => {
    api.get.mockRejectedValueOnce(
      new ApiError("Gateway timeout", 504, undefined, "upstream", "c-9")
    );

    await expect(dataMigrationService.jobs.get("job-1")).rejects.toMatchObject({
      name: "DataMigrationApiError",
      message: "Gateway timeout",
      status: 504,
      code: "upstream",
      correlationId: "c-9",
      retryable: true,
    } satisfies Partial<DataMigrationApiError>);
  });

  it("uses idempotency headers for accepted async run operations", async () => {
    api.post.mockResolvedValue(envelope({ id: "run-1" }));

    await dataMigrationService.jobs.inspect("job-1", { idempotency_key: "inspect-1" });
    await dataMigrationService.runs.start("job-1", { idempotency_key: "run-1" });
    await dataMigrationService.runs.dryRun("job-1", { idempotency_key: "dry-1" });
    await dataMigrationService.rollbacks.request("run-1", { idempotency_key: "rollback-1" });

    expect(api.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.JOBS.INSPECT("job-1"),
      {},
      {
        headers: { "Idempotency-Key": "inspect-1" },
      }
    );
    expect(api.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.JOBS.RUNS("job-1"),
      {},
      {
        headers: { "Idempotency-Key": "run-1" },
      }
    );
    expect(api.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.JOBS.DRY_RUNS("job-1"),
      {},
      {
        headers: { "Idempotency-Key": "dry-1" },
      }
    );
    expect(api.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.RUNS.ROLLBACK("run-1"),
      {},
      {
        headers: { "Idempotency-Key": "rollback-1" },
      }
    );
  });

  it("sends destructive and source mutation commands to explicit transition endpoints", async () => {
    api.delete.mockResolvedValueOnce(undefined);
    api.post.mockResolvedValue(envelope({ id: "job-1" }));

    await dataMigrationService.jobs.delete("job-1");
    await dataMigrationService.jobs.archive("job-1", "transition-1");
    await dataMigrationService.jobs.restore("job-1");
    await dataMigrationService.jobs.attachSource("job-1", "artifact-v2", 6);

    expect(api.delete).toHaveBeenCalledWith(ENDPOINTS.JOBS.DETAIL("job-1"));
    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.JOBS.ARCHIVE("job-1"), {
      transition_key: "transition-1",
    });
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.JOBS.RESTORE("job-1"));
    expect(api.post).toHaveBeenNthCalledWith(3, ENDPOINTS.JOBS.SOURCE("job-1"), {
      source_artifact_id: "artifact-v2",
      expected_version: 6,
    });
  });

  it("targets mapping, rule, and version transition endpoints with guarded payloads", async () => {
    api.post.mockResolvedValue(envelope({ id: "job-1" }));
    api.patch.mockResolvedValue(envelope({ id: "mapping-1" }));
    api.delete.mockResolvedValue(undefined);

    await dataMigrationService.mappings.reorder("job-1", {
      ordered_ids: ["mapping-2", "mapping-1"],
      expected_version: 8,
    });
    await dataMigrationService.rules.reorder("job-1", {
      ordered_ids: ["rule-1"],
      expected_version: 8,
    });
    await dataMigrationService.jobs.restoreVersion("job-1", 7, {
      expected_version: 8,
      change_summary: "Rollback bad adapter mapping",
    });
    await dataMigrationService.mappings.update("mapping-1", {
      target_field: "external_id",
      is_required: true,
    });
    await dataMigrationService.rules.delete("rule-1");

    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.JOBS.MAPPINGS("job-1"), {
      action: "reorder",
      ordered_ids: ["mapping-2", "mapping-1"],
      expected_version: 8,
    });
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.JOBS.RULES("job-1"), {
      action: "reorder",
      ordered_ids: ["rule-1"],
      expected_version: 8,
    });
    expect(api.post).toHaveBeenNthCalledWith(3, ENDPOINTS.JOBS.RESTORE_VERSION("job-1", 7), {
      expected_version: 8,
      change_summary: "Rollback bad adapter mapping",
    });
    expect(api.patch).toHaveBeenCalledWith(ENDPOINTS.MAPPINGS.DETAIL("mapping-1"), {
      target_field: "external_id",
      is_required: true,
    });
    expect(api.delete).toHaveBeenCalledWith(ENDPOINTS.RULES.DETAIL("rule-1"));
  });

  it("creates and updates mappings and rules without constructing ad hoc URLs", async () => {
    api.get.mockResolvedValue(envelope({ id: "mapping-1" }));
    api.post.mockResolvedValue(envelope({ id: "created" }));
    api.patch.mockResolvedValue(envelope({ id: "updated" }));

    await dataMigrationService.mappings.get("mapping-1");
    await dataMigrationService.rules.get("rule-1");
    await dataMigrationService.mappings.create("job-1", {
      source_field: "Customer ID",
      target_field: "external_id",
      position: 1,
      transform_config: { transform_type: "identity" },
      is_required: true,
    });
    await dataMigrationService.rules.create("job-1", {
      field_name: "external_id",
      rule_config: { rule_type: "required", trim: true },
      error_message: "External id is required",
      severity: "error",
      position: 1,
      is_active: true,
    });
    await dataMigrationService.rules.update("rule-1", { is_active: false });

    expect(api.get).toHaveBeenNthCalledWith(1, ENDPOINTS.MAPPINGS.DETAIL("mapping-1"));
    expect(api.get).toHaveBeenNthCalledWith(2, ENDPOINTS.RULES.DETAIL("rule-1"));
    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.JOBS.MAPPINGS("job-1"), {
      source_field: "Customer ID",
      target_field: "external_id",
      position: 1,
      transform_config: { transform_type: "identity" },
      is_required: true,
    });
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.JOBS.RULES("job-1"), {
      field_name: "external_id",
      rule_config: { rule_type: "required", trim: true },
      error_message: "External id is required",
      severity: "error",
      position: 1,
      is_active: true,
    });
    expect(api.patch).toHaveBeenCalledWith(ENDPOINTS.RULES.DETAIL("rule-1"), {
      is_active: false,
    });
  });

  it("keeps connection and configuration import/export endpoints semantically separated", async () => {
    api.get.mockResolvedValueOnce(envelope({ schema_version: 1, checksum: "sha256:config" }));
    api.post.mockResolvedValue(envelope({ id: "conn-1" }));
    api.patch.mockResolvedValue(envelope({ id: "conn-1" }));

    await dataMigrationService.configuration.export();
    await dataMigrationService.configuration.import({
      schema_version: 1,
      checksum: "sha256:config",
      configuration: {
        source_row_limit: 1000,
        batch_size: 100,
        connect_timeout_seconds: 5,
        read_timeout_seconds: 30,
        retry_count: 2,
        issue_sample_limit: 20,
        preview_row_limit: 10,
        retention_days: 90,
        allowed_target_adapters: ["crm.customer"],
        enabled_roles: ["operator"],
        rollout_percentage: 100,
        enabled: true,
      },
      expected_version: 4,
    });
    await dataMigrationService.connections.rotateCredential("conn-1", "secret://rotated");
    await dataMigrationService.connections.deactivate("conn-1");
    await dataMigrationService.connections.test("conn-1");

    expect(api.get).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.EXPORT);
    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.CONFIGURATION.IMPORT, {
      schema_version: 1,
      checksum: "sha256:config",
      configuration: {
        source_row_limit: 1000,
        batch_size: 100,
        connect_timeout_seconds: 5,
        read_timeout_seconds: 30,
        retry_count: 2,
        issue_sample_limit: 20,
        preview_row_limit: 10,
        retention_days: 90,
        allowed_target_adapters: ["crm.customer"],
        enabled_roles: ["operator"],
        rollout_percentage: 100,
        enabled: true,
      },
      expected_version: 4,
    });
    expect(api.patch).toHaveBeenCalledWith(ENDPOINTS.CONNECTIONS.DETAIL("conn-1"), {
      credential_ref: "secret://rotated",
    });
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.CONNECTIONS.DEACTIVATE("conn-1"));
    expect(api.post).toHaveBeenNthCalledWith(3, ENDPOINTS.CONNECTIONS.TEST("conn-1"));
  });

  it("previews configuration without leaking expected version into semantic diff requests", async () => {
    api.post.mockResolvedValueOnce(envelope({ changes: [], warnings: [] }));

    await dataMigrationService.configuration.preview({
      source_row_limit: 1000,
      batch_size: 100,
      connect_timeout_seconds: 5,
      read_timeout_seconds: 30,
      retry_count: 2,
      issue_sample_limit: 25,
      preview_row_limit: 10,
      retention_days: 30,
      allowed_target_adapters: ["crm.customer"],
      enabled_roles: ["operator"],
      rollout_percentage: 50,
      enabled: true,
      expected_version: 7,
    });

    const [, body] = api.post.mock.calls[0] ?? [];
    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.PREVIEW, body);
    expect(body).not.toHaveProperty("expected_version");
  });

  it("exports and imports complete migration definitions without confusing them with configuration documents", async () => {
    const definition = {
      schema_version: "2.0",
      checksum: "sha256:def",
      job: {
        name: "Customer import",
        description: "Governed customer load",
        source_type: "csv",
        source_config: { delimiter: ",", encoding: "utf-8", header_row: 1, batch_size: 500 },
        target_adapter: "crm",
        target_entity: "customer",
        write_mode: "upsert",
        lookup_fields: ["external_id"],
      },
      mappings: [
        {
          source_field: "Customer ID",
          target_field: "external_id",
          position: 1,
          transform_config: { transform_type: "identity" },
          is_required: true,
        },
      ],
      rules: [
        {
          field_name: "external_id",
          rule_config: { rule_type: "required", trim: true },
          error_message: "External ID is required",
          severity: "error",
          position: 1,
          is_active: true,
        },
      ],
    } satisfies Awaited<ReturnType<typeof dataMigrationService.jobs.export>>;
    api.get.mockResolvedValueOnce(envelope(definition));
    api.post.mockResolvedValueOnce(
      envelope({
        job: null,
        diff: { from_version: null, to_version: null, entries: [], warnings: [] },
        checksum_valid: true,
      })
    );

    await expect(dataMigrationService.jobs.export("job-1")).resolves.toBe(definition);
    await dataMigrationService.jobs.import({ document: definition, preview_only: true });

    expect(api.get).toHaveBeenCalledWith(ENDPOINTS.JOBS.EXPORT("job-1"));
    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.JOBS.IMPORT, {
      document: definition,
      preview_only: true,
    });
  });

  it("does not normalize non-ApiError failures into governed retryable errors", async () => {
    const syntaxFailure = new SyntaxError("Malformed JSON");
    api.get.mockRejectedValueOnce(syntaxFailure);

    await expect(dataMigrationService.jobs.get("job-1")).rejects.toBe(syntaxFailure);
  });

  it("computes definition diffs for checksum, target, mapping, and rule changes", () => {
    const current = {
      checksum: "old",
      job: { name: "Old job", target_adapter: "crm.customer" },
      mappings: [{ id: "m1" }],
      rules: [],
    };
    const proposed = {
      checksum: "new",
      job: { name: "New job", target_adapter: "erp.vendor" },
      mappings: [{ id: "m1" }, { id: "m2" }],
      rules: [{ id: "r1" }],
    };

    expect(
      dataMigrationService.definitionDiff(
        current as unknown as Parameters<typeof dataMigrationService.definitionDiff>[0],
        proposed as unknown as Parameters<typeof dataMigrationService.definitionDiff>[1]
      ).entries
    ).toEqual([
      expect.objectContaining({ path: "checksum", before: "old", after: "new" }),
      expect.objectContaining({ path: "job.name", before: "Old job", after: "New job" }),
      expect.objectContaining({
        path: "job.target_adapter",
        before: "crm.customer",
        after: "erp.vendor",
      }),
      expect.objectContaining({ path: "mappings", before: 1, after: 2 }),
      expect.objectContaining({ path: "rules", before: 0, after: 1 }),
    ]);
  });
});
