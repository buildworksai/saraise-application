/* eslint-disable max-lines-per-function -- mutation-focused service boundary tests intentionally keep endpoint matrices local. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import {
  BackupRecoveryApiError,
  backupRecoveryQueryKeys,
  backupRecoveryService,
  newIdempotencyKey,
  serializeFilters,
} from "../services/backup-recovery-service";

const healthyDependency = (key: string) => ({ key, status: "healthy", critical: true });

const moduleHealth = (overrides: Record<string, unknown> = {}) => ({
  status: "degraded",
  ready: false,
  checked_at: "2026-08-02T10:00:00Z",
  database: healthyDependency("database"),
  async_jobs: healthyDependency("async_jobs"),
  outbox: healthyDependency("outbox"),
  scheduler: { key: "scheduler", status: "degraded", critical: true },
  adapters: [],
  oldest_pending_outbox_seconds: null,
  correlation_id: "corr-health",
  ...overrides,
});

describe("backup recovery governed API service", () => {
  afterEach(() => vi.restoreAllMocks());

  it("serializes normalized server filters with URLSearchParams", () => {
    expect(
      serializeFilters({
        status: "failed",
        page: 2,
        empty: "",
        absent: undefined,
        omitted: null,
        active: false,
        zero: 0,
      })
    ).toBe("active=false&page=2&status=failed&zero=0");
    expect(backupRecoveryQueryKeys.jobs("tenant", { page: 2, status: "failed" })).toEqual([
      "backup-recovery",
      "tenant",
      "jobs",
      { page: "2", status: "failed" },
    ]);
  });

  it("builds tenant-scoped query keys for every governed cache family", () => {
    expect(backupRecoveryQueryKeys.root(null)).toEqual(["backup-recovery", "no-tenant"]);
    expect(backupRecoveryQueryKeys.root("")).toEqual(["backup-recovery", ""]);
    expect(backupRecoveryQueryKeys.health(null)).toEqual([
      "backup-recovery",
      "no-tenant",
      "health",
    ]);
    expect(backupRecoveryQueryKeys.health("tenant")).toEqual([
      "backup-recovery",
      "tenant",
      "health",
    ]);
    expect(backupRecoveryQueryKeys.job("tenant", "job-1")).toEqual([
      "backup-recovery",
      "tenant",
      "job",
      "job-1",
    ]);
    expect(
      backupRecoveryQueryKeys.schedules("tenant", {
        frequency: "daily",
        is_active: false,
        page_size: 50,
      })
    ).toEqual([
      "backup-recovery",
      "tenant",
      "schedules",
      { frequency: "daily", is_active: "false", page_size: "50" },
    ]);
    expect(backupRecoveryQueryKeys.schedule("tenant", "schedule-1")).toEqual([
      "backup-recovery",
      "tenant",
      "schedule",
      "schedule-1",
    ]);
    expect(
      backupRecoveryQueryKeys.policies("tenant", {
        is_active: true,
        ordering: "-retention_days",
      })
    ).toEqual([
      "backup-recovery",
      "tenant",
      "policies",
      { is_active: "true", ordering: "-retention_days" },
    ]);
    expect(backupRecoveryQueryKeys.policy("tenant", "policy-1")).toEqual([
      "backup-recovery",
      "tenant",
      "policy",
      "policy-1",
    ]);
    expect(
      backupRecoveryQueryKeys.policyPreview("tenant", "policy-1", "2026-07-24T00:00:00Z")
    ).toEqual([
      "backup-recovery",
      "tenant",
      "policy",
      "policy-1",
      "preview",
      "2026-07-24T00:00:00Z",
    ]);
    expect(
      backupRecoveryQueryKeys.targets("tenant", {
        adapter_key: "s3",
        is_default: true,
      })
    ).toEqual(["backup-recovery", "tenant", "targets", { adapter_key: "s3", is_default: "true" }]);
    expect(backupRecoveryQueryKeys.target("tenant", "target-1")).toEqual([
      "backup-recovery",
      "tenant",
      "target",
      "target-1",
    ]);
    expect(
      backupRecoveryQueryKeys.archives("tenant", {
        backup_type: "full",
        lifecycle: "available",
      })
    ).toEqual([
      "backup-recovery",
      "tenant",
      "archives",
      { backup_type: "full", lifecycle: "available" },
    ]);
    expect(backupRecoveryQueryKeys.archive("tenant", "archive-1")).toEqual([
      "backup-recovery",
      "tenant",
      "archive",
      "archive-1",
    ]);
    expect(
      backupRecoveryQueryKeys.verifications("tenant", {
        archive_id: "archive-1",
        status: "running",
      })
    ).toEqual([
      "backup-recovery",
      "tenant",
      "verifications",
      { archive_id: "archive-1", status: "running" },
    ]);
    expect(backupRecoveryQueryKeys.verification("tenant", "verification-1")).toEqual([
      "backup-recovery",
      "tenant",
      "verification",
      "verification-1",
    ]);
  });

  it("unwraps a paginated v2 envelope and preserves metadata", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [{ id: "job-1" }],
      meta: {
        correlation_id: "corr-1",
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
    const result = await backupRecoveryService.listBackupJobs({ status: "running", page: 1 });
    expect(get).toHaveBeenCalledWith(`${ENDPOINTS.JOBS.LIST}?page=1&status=running`);
    expect(result.items).toEqual([{ id: "job-1" }]);
    expect(result.correlationId).toBe("corr-1");
    expect(result.pagination.count).toBe(1);
  });

  it("unwraps detail/action envelopes", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { id: "job-1", status: "pending" },
      meta: { correlation_id: "corr-2" },
    });
    await expect(backupRecoveryService.getBackupJob("job-1")).resolves.toMatchObject({
      id: "job-1",
    });
    expect(get).toHaveBeenCalledWith(ENDPOINTS.JOBS.DETAIL("job-1"));
  });

  it("normalizes governed errors, fields, and support correlation ID", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(
      new ApiError("request failed", 400, {
        error: {
          code: "VALIDATION_ERROR",
          detail: "Review the fields.",
          status: 400,
          correlation_id: "corr-error",
          field_errors: { scope_ref: ["This field is required."] },
        },
      })
    );
    const error = await backupRecoveryService
      .createBackupJob({
        backup_type: "full",
        scope_type: "tenant",
        scope_ref: "",
        idempotency_key: "key",
      })
      .catch((failure: unknown) => failure);
    expect(error).toBeInstanceOf(BackupRecoveryApiError);
    expect(error).toMatchObject({
      status: 400,
      code: "VALIDATION_ERROR",
      correlationId: "corr-error",
    });
    expect((error as BackupRecoveryApiError).fieldError("scope_ref")).toBe(
      "This field is required."
    );
    expect((error as BackupRecoveryApiError).permissionDenied).toBe(false);
    expect((error as BackupRecoveryApiError).fieldError("unknown")).toBeUndefined();
    expect((error as BackupRecoveryApiError).name).toBe("BackupRecoveryApiError");
  });

  it("normalizes array field errors and identifies permission denials", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("forbidden", 403, {
        error: {
          code: "FORBIDDEN",
          message: "Missing capability.",
          status: 403,
          correlation_id: "corr-denied",
          field_errors: [{ field: "permission", message: "backup.read is required." }],
        },
      })
    );

    const error = await backupRecoveryService.health().catch((failure: unknown) => failure);

    expect(error).toBeInstanceOf(BackupRecoveryApiError);
    expect(error).toMatchObject({
      status: 403,
      code: "FORBIDDEN",
      correlationId: "corr-denied",
    });
    expect((error as BackupRecoveryApiError).permissionDenied).toBe(true);
    expect((error as BackupRecoveryApiError).fieldError("permission")).toBe(
      "backup.read is required."
    );
  });

  it("uses an immutable empty field-error default for direct service errors", () => {
    const error = new BackupRecoveryApiError("Invalid envelope", 502, "MALFORMED_RESPONSE", null);

    expect(error.name).toBe("BackupRecoveryApiError");
    expect(error.fieldErrors).toEqual([]);
    expect(error.fieldError("anything")).toBeUndefined();
  });

  it("falls back to detail field errors and ApiError defaults when governed fields are absent", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValueOnce(
      new ApiError(
        "request failed",
        422,
        {
          error: {
            code: "VALIDATION_ERROR",
            message: "The request is invalid.",
            detail: {
              scope_ref: ["Detail fallback required."],
              backup_type: [false, "Use a supported backup type."],
              schedule_id: "Scalar detail required.",
            },
          },
        },
        undefined,
        "corr-from-api-error"
      )
    );
    vi.spyOn(apiClient, "get").mockRejectedValueOnce(new ApiError("gateway unavailable", 503));

    const validationError = await backupRecoveryService
      .createBackupJob({
        backup_type: "full",
        scope_type: "tenant",
        scope_ref: "",
        idempotency_key: "key",
      })
      .catch((failure: unknown) => failure);
    const defaultError = await backupRecoveryService.health().catch((failure: unknown) => failure);

    expect(validationError).toMatchObject({
      status: 422,
      code: "VALIDATION_ERROR",
      correlationId: "corr-from-api-error",
      message: "The request is invalid.",
    });
    expect((validationError as BackupRecoveryApiError).fieldError("scope_ref")).toBe(
      "Detail fallback required."
    );
    expect((validationError as BackupRecoveryApiError).fieldError("backup_type")).toBe(
      "Use a supported backup type."
    );
    expect((validationError as BackupRecoveryApiError).fieldError("schedule_id")).toBe(
      "Scalar detail required."
    );
    expect(defaultError).toMatchObject({
      status: 503,
      code: "REQUEST_FAILED",
      correlationId: null,
      message: "gateway unavailable",
    });
    expect((defaultError as BackupRecoveryApiError).fieldErrors).toEqual([]);
  });

  it("does not fabricate field errors from empty or scalar governed error fields", async () => {
    vi.spyOn(apiClient, "post")
      .mockRejectedValueOnce(
        new ApiError("null fields", 400, {
          error: {
            code: "VALIDATION_ERROR",
            message: "Null field errors are empty.",
            detail: null,
          },
        })
      )
      .mockRejectedValueOnce(
        new ApiError("null fields", 400, {
          error: {
            code: "VALIDATION_ERROR",
            message: "Null explicit field errors are empty.",
            detail: undefined,
            field_errors: null,
          },
        })
      )
      .mockRejectedValueOnce(
        new ApiError("scalar fields", 400, {
          error: {
            code: "VALIDATION_ERROR",
            message: "Scalar field errors are empty.",
            field_errors: "scope_ref",
          },
        })
      );

    const nullFields = await backupRecoveryService
      .createBackupJob({
        backup_type: "full",
        scope_type: "tenant",
        scope_ref: "",
        idempotency_key: "key",
      })
      .catch((failure: unknown) => failure);
    const nullExplicitFields = await backupRecoveryService
      .createBackupJob({
        backup_type: "full",
        scope_type: "tenant",
        scope_ref: "",
        idempotency_key: "key-explicit",
      })
      .catch((failure: unknown) => failure);
    const scalarFields = await backupRecoveryService
      .createBackupJob({
        backup_type: "full",
        scope_type: "tenant",
        scope_ref: "",
        idempotency_key: "key-2",
      })
      .catch((failure: unknown) => failure);

    expect((nullFields as BackupRecoveryApiError).fieldErrors).toEqual([]);
    expect((nullExplicitFields as BackupRecoveryApiError).fieldErrors).toEqual([]);
    expect((scalarFields as BackupRecoveryApiError).fieldErrors).toEqual([]);
  });

  it("normalizes malformed governed envelopes without leaking parser failures", async () => {
    vi.spyOn(apiClient, "get")
      .mockRejectedValueOnce(new ApiError("null details", 502, null))
      .mockRejectedValueOnce(new ApiError("scalar details", 503, "offline"))
      .mockRejectedValueOnce(
        new ApiError(
          "plain object",
          502,
          { message: "legacy object without governed error" },
          "BAD_GATEWAY",
          "corr-plain"
        )
      )
      .mockRejectedValueOnce(
        new ApiError("scalar error", 504, {
          error: "not-an-error-object",
        })
      )
      .mockRejectedValueOnce(
        new ApiError("array error", 504, {
          error: [],
        })
      );

    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 502,
      code: "REQUEST_FAILED",
      message: "null details",
      fieldErrors: [],
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 503,
      code: "REQUEST_FAILED",
      message: "scalar details",
      fieldErrors: [],
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 502,
      code: "BAD_GATEWAY",
      correlationId: "corr-plain",
      message: "plain object",
      fieldErrors: [],
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_ERROR_ENVELOPE",
      message: "The server returned a malformed error envelope.",
      fieldErrors: [],
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_ERROR_ENVELOPE",
      message: "The server returned a malformed error envelope.",
      fieldErrors: [],
    });
  });

  it("uses string governed detail as the operator-facing message", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("request failed", 409, {
        error: {
          code: "CONFLICT",
          message: "Fallback message.",
          detail: "Archive verification is already running.",
          status: 409,
          correlation_id: "corr-detail-message",
        },
      })
    );

    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 409,
      code: "CONFLICT",
      correlationId: "corr-detail-message",
      message: "Archive verification is already running.",
      fieldErrors: [],
    });
  });

  it("treats valid unavailable health JSON on 503 as module evidence", async () => {
    const unavailableHealth = {
      status: "unavailable",
      ready: false,
      checked_at: "2026-08-02T10:00:00Z",
      database: { key: "database", status: "healthy", critical: true },
      async_jobs: { key: "async_jobs", status: "healthy", critical: true },
      outbox: { key: "outbox", status: "healthy", critical: true },
      scheduler: {
        key: "scheduler",
        status: "unavailable",
        critical: true,
        detail: "No scheduler scan has completed recently.",
      },
      adapters: [{ key: "local-filesystem", status: "healthy", critical: false }],
      oldest_pending_outbox_seconds: null,
      correlation_id: "corr-health-unavailable",
    } as const;
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("GET /api/v2/backup-recovery/health/ failed: 503", 503, unavailableHealth)
    );

    await expect(backupRecoveryService.health()).resolves.toEqual(unavailableHealth);
  });

  it("accepts every valid raw 503 health status and dependency status", async () => {
    const healthyHealth = moduleHealth({
      status: "healthy",
      ready: true,
      scheduler: { key: "scheduler", status: "healthy", critical: true },
    });
    const degradedHealth = moduleHealth({
      database: { key: "database", status: "degraded", critical: true },
      adapters: [],
    });
    vi.spyOn(apiClient, "get")
      .mockRejectedValueOnce(new ApiError("healthy module", 503, healthyHealth))
      .mockRejectedValueOnce(new ApiError("degraded dependency", 503, degradedHealth));

    await expect(backupRecoveryService.health()).resolves.toBe(healthyHealth);
    await expect(backupRecoveryService.health()).resolves.toBe(degradedHealth);
  });

  it("unwraps valid health envelopes without requiring an error response", async () => {
    const degradedHealth = moduleHealth({
      adapters: [{ key: "s3", status: "unavailable", critical: false }],
    });
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: degradedHealth,
      meta: { correlation_id: "corr-health-envelope" },
    });

    await expect(backupRecoveryService.health()).resolves.toBe(degradedHealth);
    expect(get).toHaveBeenCalledWith(ENDPOINTS.HEALTH);
  });

  it("rejects malformed health JSON on 503 instead of fabricating readiness", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("GET /api/v2/backup-recovery/health/ failed: 503", 503, {
        status: "unavailable",
        ready: false,
        checked_at: "2026-08-02T10:00:00Z",
      })
    );

    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 503,
      code: "REQUEST_FAILED",
      message: "GET /api/v2/backup-recovery/health/ failed: 503",
    });
  });

  it("requires every health dependency field before accepting raw 503 health evidence", async () => {
    vi.spyOn(apiClient, "get")
      .mockRejectedValueOnce(new ApiError("array health", 503, []))
      .mockRejectedValueOnce(
        new ApiError("non-boolean ready", 503, moduleHealth({ ready: "false" }))
      )
      .mockRejectedValueOnce(
        new ApiError("non-string timestamp", 503, moduleHealth({ checked_at: 123 }))
      )
      .mockRejectedValueOnce(new ApiError("dependency null", 503, moduleHealth({ database: null })))
      .mockRejectedValueOnce(
        new ApiError(
          "dependency key missing",
          503,
          moduleHealth({ database: { status: "healthy", critical: true } })
        )
      )
      .mockRejectedValueOnce(
        new ApiError(
          "dependency status invalid",
          503,
          moduleHealth({ async_jobs: { key: "async_jobs", status: "offline", critical: true } })
        )
      )
      .mockRejectedValueOnce(
        new ApiError(
          "dependency critical invalid",
          503,
          moduleHealth({ outbox: { key: "outbox", status: "healthy", critical: "true" } })
        )
      )
      .mockRejectedValueOnce(
        new ApiError("adapters missing", 503, moduleHealth({ adapters: null }))
      )
      .mockRejectedValueOnce(
        new ApiError(
          "adapter malformed",
          503,
          moduleHealth({ adapters: [{ key: "s3", status: "healthy" }] })
        )
      );

    await expect(backupRecoveryService.health()).rejects.toMatchObject({ message: "array health" });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      message: "non-boolean ready",
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      message: "non-string timestamp",
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      message: "dependency null",
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      message: "dependency key missing",
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      message: "dependency status invalid",
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      message: "dependency critical invalid",
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      message: "adapters missing",
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      message: "adapter malformed",
    });
  });

  it("passes non-ApiError failures through unchanged", async () => {
    const failure = new Error("non-api failure");
    vi.spyOn(apiClient, "get").mockRejectedValue(failure);

    await expect(backupRecoveryService.health()).rejects.toBe(failure);
  });

  it("does not treat status-shaped non-ApiError failures as raw health evidence", async () => {
    const failure = { status: 503, details: moduleHealth() };
    vi.spyOn(apiClient, "get").mockRejectedValue(failure);

    await expect(backupRecoveryService.health()).rejects.toBe(failure);
  });

  it("does not treat non-503 ApiError failures as raw health evidence", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(
      new ApiError("forbidden health", 403, moduleHealth())
    );

    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 403,
      code: "REQUEST_FAILED",
      message: "forbidden health",
    });
  });

  it("passes non-ApiError mutation failures through unchanged", async () => {
    const failure = new Error("post failed outside api client");
    vi.spyOn(apiClient, "post").mockRejectedValue(failure);

    await expect(
      backupRecoveryService.createBackupJob({
        backup_type: "full",
        scope_type: "tenant",
        scope_ref: "tenant",
        idempotency_key: "key",
      })
    ).rejects.toBe(failure);
  });

  it("fails closed when singleton and paginated envelopes are malformed", async () => {
    vi.spyOn(apiClient, "get")
      .mockResolvedValueOnce({ meta: { correlation_id: "corr-singleton" } })
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce("not-an-envelope")
      .mockResolvedValueOnce({
        data: {},
        meta: { correlation_id: "corr-page", pagination: { count: 0 } },
      })
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: {} });

    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: null,
      message: "The server returned an invalid response envelope.",
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: null,
      message: "The server returned an invalid response envelope.",
    });
    await expect(backupRecoveryService.health()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: null,
      message: "The server returned an invalid response envelope.",
    });
    await expect(backupRecoveryService.listBackupJobs()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: "corr-page",
      message: "The server returned an invalid paginated response.",
    });
    await expect(backupRecoveryService.listBackupJobs()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: null,
      message: "The server returned an invalid paginated response.",
    });
    await expect(backupRecoveryService.listBackupJobs()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: null,
      message: "The server returned an invalid paginated response.",
    });
    await expect(backupRecoveryService.listBackupJobs()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: null,
      message: "The server returned an invalid paginated response.",
    });
  });

  it("fails closed when non-health singleton envelopes are malformed", async () => {
    vi.spyOn(apiClient, "get")
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce("not-an-envelope")
      .mockResolvedValueOnce({ meta: { correlation_id: "corr-detail" } });

    await expect(backupRecoveryService.getBackupJob("job-null")).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: null,
      message: "The server returned an invalid response envelope.",
    });
    await expect(backupRecoveryService.getBackupJob("job-scalar")).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: null,
      message: "The server returned an invalid response envelope.",
    });
    await expect(backupRecoveryService.getBackupJob("job-missing-data")).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: null,
      message: "The server returned an invalid response envelope.",
    });
  });

  it("sends every mutation to its public endpoint and no worker-only method exists", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ data: { id: "result" }, meta: { correlation_id: "corr" } });
    await expect(
      backupRecoveryService.cancelBackupJob("job", { transition_key: "transition" })
    ).resolves.toEqual({ id: "result" });
    await expect(
      backupRecoveryService.runBackupScheduleNow("schedule", { idempotency_key: "key" })
    ).resolves.toEqual({ id: "result" });
    await expect(backupRecoveryService.probeStorageTarget("target")).resolves.toEqual({
      id: "result",
    });
    await expect(
      backupRecoveryService.requestArchiveVerification("archive", { idempotency_key: "key" })
    ).resolves.toEqual({ id: "result" });
    expect(post.mock.calls.map(([path]) => path)).toEqual([
      ENDPOINTS.JOBS.CANCEL("job"),
      ENDPOINTS.SCHEDULES.RUN_NOW("schedule"),
      ENDPOINTS.STORAGE_TARGETS.PROBE("target"),
      ENDPOINTS.ARCHIVES.VERIFY("archive"),
    ]);
    expect(post.mock.calls.map(([, body]) => body)).toEqual([
      { transition_key: "transition" },
      { idempotency_key: "key" },
      {},
      { idempotency_key: "key" },
    ]);
    expect("completeBackupJob" in backupRecoveryService).toBe(false);
    expect("failBackupJob" in backupRecoveryService).toBe(false);
    expect("purgeBackupArchive" in backupRecoveryService).toBe(false);
  });

  it("preserves backup job request bodies and unwraps response payloads", async () => {
    const createRequest = {
      backup_type: "incremental",
      scope_type: "module",
      scope_ref: "finance",
      idempotency_key: "create-key",
      description: "Nightly finance backup",
    } as const;
    const updateRequest = { description: "Updated description" };
    const receipt = {
      job_id: "job-1",
      async_job_id: "async-1",
      status: "pending",
      idempotency_key: "create-key",
      correlation_id: "corr-create",
    } as const;
    const updatedJob = { id: "job-1", description: "Updated description" };
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ data: receipt, meta: { correlation_id: "corr-create" } });
    const patch = vi
      .spyOn(apiClient, "patch")
      .mockResolvedValue({ data: updatedJob, meta: { correlation_id: "corr-update" } });
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined);

    await expect(backupRecoveryService.createBackupJob(createRequest)).resolves.toBe(receipt);
    await expect(backupRecoveryService.updateBackupJob("job-1", updateRequest)).resolves.toBe(
      updatedJob
    );
    await expect(backupRecoveryService.deleteBackupJob("job-1")).resolves.toBeUndefined();

    expect(post).toHaveBeenCalledWith(ENDPOINTS.JOBS.CREATE, createRequest);
    expect(patch).toHaveBeenCalledWith(ENDPOINTS.JOBS.UPDATE("job-1"), updateRequest);
    expect(del).toHaveBeenCalledWith(ENDPOINTS.JOBS.DELETE("job-1"));
  });

  it("covers the public service endpoint matrix across resources", async () => {
    const page = {
      data: [],
      meta: {
        correlation_id: "corr-page",
        pagination: {
          page: 1,
          page_size: 25,
          count: 0,
          total_pages: 0,
          has_next: false,
          has_previous: false,
        },
      },
    };
    const detail = { data: { id: "entity" }, meta: { correlation_id: "corr-detail" } };
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(page);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(detail);
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue(detail);
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined);

    await backupRecoveryService.health();
    await backupRecoveryService.listBackupSchedules({ is_active: true, page: 1 });
    await backupRecoveryService.getBackupSchedule("schedule");
    await backupRecoveryService.createBackupSchedule({ name: "schedule" } as never);
    await backupRecoveryService.updateBackupSchedule("schedule", { name: "new schedule" });
    await backupRecoveryService.deleteBackupSchedule("schedule");
    await backupRecoveryService.activateBackupSchedule("schedule");
    await backupRecoveryService.deactivateBackupSchedule("schedule");
    await backupRecoveryService.listRetentionPolicies({ page: 1 });
    await backupRecoveryService.getRetentionPolicy("policy");
    await backupRecoveryService.createRetentionPolicy({ name: "policy", retention_days: 30 });
    await backupRecoveryService.updateRetentionPolicy("policy", { retention_days: 60 });
    await backupRecoveryService.deleteRetentionPolicy("policy");
    await backupRecoveryService.activateRetentionPolicy("policy");
    await backupRecoveryService.deactivateRetentionPolicy("policy");
    await backupRecoveryService.previewRetentionPolicy("policy", "2026-07-24T00:00:00Z");
    await backupRecoveryService.listStorageTargets({ page: 1 });
    await backupRecoveryService.getStorageTarget("target");
    await backupRecoveryService.createStorageTarget({ name: "target" } as never);
    await backupRecoveryService.updateStorageTarget("target", { name: "new target" });
    await backupRecoveryService.deleteStorageTarget("target");
    await backupRecoveryService.activateStorageTarget("target");
    await backupRecoveryService.deactivateStorageTarget("target");
    await backupRecoveryService.setDefaultStorageTarget("target");
    await backupRecoveryService.listBackupArchives({ lifecycle: "available", page: 1 });
    await backupRecoveryService.getBackupArchive("archive");
    await backupRecoveryService.listBackupVerifications({ status: "pending", page: 1 });
    await backupRecoveryService.getBackupVerification("verification");
    await backupRecoveryService.cancelBackupVerification("verification", {
      transition_key: "transition",
    });
    await backupRecoveryService.retryBackupJob("job", { idempotency_key: "retry" });

    expect(get.mock.calls.map(([path]) => path)).toEqual([
      ENDPOINTS.HEALTH,
      `${ENDPOINTS.SCHEDULES.LIST}?is_active=true&page=1`,
      ENDPOINTS.SCHEDULES.DETAIL("schedule"),
      ENDPOINTS.RETENTION_POLICIES.LIST + "?page=1",
      ENDPOINTS.RETENTION_POLICIES.DETAIL("policy"),
      `${ENDPOINTS.RETENTION_POLICIES.PREVIEW("policy")}?captured_at=2026-07-24T00%3A00%3A00Z`,
      ENDPOINTS.STORAGE_TARGETS.LIST + "?page=1",
      ENDPOINTS.STORAGE_TARGETS.DETAIL("target"),
      `${ENDPOINTS.ARCHIVES.LIST}?lifecycle=available&page=1`,
      ENDPOINTS.ARCHIVES.DETAIL("archive"),
      `${ENDPOINTS.VERIFICATIONS.LIST}?page=1&status=pending`,
      ENDPOINTS.VERIFICATIONS.DETAIL("verification"),
    ]);
    expect(post.mock.calls.map(([path]) => path)).toEqual([
      ENDPOINTS.SCHEDULES.CREATE,
      ENDPOINTS.SCHEDULES.ACTIVATE("schedule"),
      ENDPOINTS.SCHEDULES.DEACTIVATE("schedule"),
      ENDPOINTS.RETENTION_POLICIES.CREATE,
      ENDPOINTS.RETENTION_POLICIES.ACTIVATE("policy"),
      ENDPOINTS.RETENTION_POLICIES.DEACTIVATE("policy"),
      ENDPOINTS.STORAGE_TARGETS.CREATE,
      ENDPOINTS.STORAGE_TARGETS.ACTIVATE("target"),
      ENDPOINTS.STORAGE_TARGETS.DEACTIVATE("target"),
      ENDPOINTS.STORAGE_TARGETS.SET_DEFAULT("target"),
      ENDPOINTS.VERIFICATIONS.CANCEL("verification"),
      ENDPOINTS.JOBS.RETRY("job"),
    ]);
    expect(patch.mock.calls.map(([path]) => path)).toEqual([
      ENDPOINTS.SCHEDULES.UPDATE("schedule"),
      ENDPOINTS.RETENTION_POLICIES.UPDATE("policy"),
      ENDPOINTS.STORAGE_TARGETS.UPDATE("target"),
    ]);
    expect(del.mock.calls.map(([path]) => path)).toEqual([
      ENDPOINTS.SCHEDULES.DELETE("schedule"),
      ENDPOINTS.RETENTION_POLICIES.DELETE("policy"),
      ENDPOINTS.STORAGE_TARGETS.DELETE("target"),
    ]);
  });

  it("serializes complete list filters and remaining action bodies", async () => {
    const page = {
      data: [],
      meta: {
        correlation_id: "corr-page",
        pagination: {
          page: 1,
          page_size: 25,
          count: 0,
          total_pages: 0,
          has_next: false,
          has_previous: false,
        },
      },
    };
    const detail = { data: { id: "entity" }, meta: { correlation_id: "corr-detail" } };
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(page);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(detail);

    await backupRecoveryService.listBackupJobs({
      backup_type: "incremental",
      ordering: "-completed_at",
      page: 4,
      page_size: 100,
      requested_after: "2026-07-01T00:00:00Z",
      requested_before: "2026-07-31T23:59:59Z",
      schedule_id: "schedule-1",
      scope_ref: "finance",
      scope_type: "module",
      search: "nightly",
      status: "completed",
    });
    await backupRecoveryService.listBackupSchedules({
      backup_type: "full",
      frequency: "weekly",
      is_active: false,
      ordering: "next_run_at",
      page: 2,
      page_size: 50,
      scope_type: "tenant",
      search: "weekly",
      storage_target_id: "target-1",
    });
    await backupRecoveryService.listRetentionPolicies({
      is_active: false,
      ordering: "retention_days",
      page: 3,
      page_size: 75,
      search: "statutory",
    });
    await backupRecoveryService.listStorageTargets({
      adapter_key: "s3",
      is_active: true,
      is_default: false,
      ordering: "-created_at",
      page: 5,
      page_size: 25,
      search: "primary",
    });
    await backupRecoveryService.listBackupArchives({
      backup_job_id: "job-1",
      backup_type: "differential",
      captured_after: "2026-07-01T00:00:00Z",
      expires_before: "2026-12-31T00:00:00Z",
      integrity_status: "verified",
      lifecycle: "available",
      ordering: "expires_at",
      page: 6,
      page_size: 25,
      search: "finance",
    });
    await backupRecoveryService.listBackupVerifications({
      archive_id: "archive-1",
      ordering: "-completed_at",
      page: 7,
      page_size: 25,
      requested_after: "2026-07-01T00:00:00Z",
      requested_before: "2026-07-31T23:59:59Z",
      status: "failed",
    });
    await backupRecoveryService.cancelBackupJob("job-1", { transition_key: "cancel-key" });
    await backupRecoveryService.runBackupScheduleNow("schedule-1", { idempotency_key: "run-key" });
    await backupRecoveryService.requestArchiveVerification("archive-1", {
      idempotency_key: "verify-key",
    });
    await backupRecoveryService.cancelBackupVerification("verification-1", {
      transition_key: "verification-cancel",
    });

    expect(get.mock.calls.map(([path]) => path)).toEqual([
      `${ENDPOINTS.JOBS.LIST}?backup_type=incremental&ordering=-completed_at&page=4&page_size=100&requested_after=2026-07-01T00%3A00%3A00Z&requested_before=2026-07-31T23%3A59%3A59Z&schedule_id=schedule-1&scope_ref=finance&scope_type=module&search=nightly&status=completed`,
      `${ENDPOINTS.SCHEDULES.LIST}?backup_type=full&frequency=weekly&is_active=false&ordering=next_run_at&page=2&page_size=50&scope_type=tenant&search=weekly&storage_target_id=target-1`,
      `${ENDPOINTS.RETENTION_POLICIES.LIST}?is_active=false&ordering=retention_days&page=3&page_size=75&search=statutory`,
      `${ENDPOINTS.STORAGE_TARGETS.LIST}?adapter_key=s3&is_active=true&is_default=false&ordering=-created_at&page=5&page_size=25&search=primary`,
      `${ENDPOINTS.ARCHIVES.LIST}?backup_job_id=job-1&backup_type=differential&captured_after=2026-07-01T00%3A00%3A00Z&expires_before=2026-12-31T00%3A00%3A00Z&integrity_status=verified&lifecycle=available&ordering=expires_at&page=6&page_size=25&search=finance`,
      `${ENDPOINTS.VERIFICATIONS.LIST}?archive_id=archive-1&ordering=-completed_at&page=7&page_size=25&requested_after=2026-07-01T00%3A00%3A00Z&requested_before=2026-07-31T23%3A59%3A59Z&status=failed`,
    ]);
    expect(post.mock.calls.map(([path]) => path)).toEqual([
      ENDPOINTS.JOBS.CANCEL("job-1"),
      ENDPOINTS.SCHEDULES.RUN_NOW("schedule-1"),
      ENDPOINTS.ARCHIVES.VERIFY("archive-1"),
      ENDPOINTS.VERIFICATIONS.CANCEL("verification-1"),
    ]);
    expect(post.mock.calls.map(([, body]) => body)).toEqual([
      { transition_key: "cancel-key" },
      { idempotency_key: "run-key" },
      { idempotency_key: "verify-key" },
      { transition_key: "verification-cancel" },
    ]);
  });

  it("prefixes generated idempotency keys with the operation name", () => {
    const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, "crypto");
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: { randomUUID: vi.fn(() => "uuid") },
    });

    expect(newIdempotencyKey("backup")).toBe("backup:uuid");

    if (cryptoDescriptor) Object.defineProperty(globalThis, "crypto", cryptoDescriptor);
    else delete (globalThis as Partial<typeof globalThis>).crypto;
  });
});
