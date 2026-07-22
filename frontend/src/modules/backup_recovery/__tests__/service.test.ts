import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import {
  BackupRecoveryApiError,
  backupRecoveryQueryKeys,
  backupRecoveryService,
  serializeFilters,
} from "../services/backup-recovery-service";

describe("backup recovery governed API service", () => {
  afterEach(() => vi.restoreAllMocks());

  it("serializes normalized server filters with URLSearchParams", () => {
    expect(
      serializeFilters({ status: "failed", page: 2, empty: "", absent: undefined, active: false })
    ).toBe("active=false&page=2&status=failed");
    expect(backupRecoveryQueryKeys.jobs("tenant", { page: 2, status: "failed" })).toEqual([
      "backup-recovery",
      "tenant",
      "jobs",
      { page: "2", status: "failed" },
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
  });

  it("sends every mutation to its public endpoint and no worker-only method exists", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ data: { id: "result" }, meta: { correlation_id: "corr" } });
    await backupRecoveryService.cancelBackupJob("job", { transition_key: "transition" });
    await backupRecoveryService.runBackupScheduleNow("schedule", { idempotency_key: "key" });
    await backupRecoveryService.probeStorageTarget("target");
    await backupRecoveryService.requestArchiveVerification("archive", { idempotency_key: "key" });
    expect(post.mock.calls.map(([path]) => path)).toEqual([
      ENDPOINTS.JOBS.CANCEL("job"),
      ENDPOINTS.SCHEDULES.RUN_NOW("schedule"),
      ENDPOINTS.STORAGE_TARGETS.PROBE("target"),
      ENDPOINTS.ARCHIVES.VERIFY("archive"),
    ]);
    expect("completeBackupJob" in backupRecoveryService).toBe(false);
    expect("failBackupJob" in backupRecoveryService).toBe(false);
    expect("purgeBackupArchive" in backupRecoveryService).toBe(false);
  });
});
