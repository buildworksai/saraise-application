/* eslint-disable max-lines-per-function -- mutation-focused service boundary tests intentionally keep endpoint matrices local. */
import React, { type ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiV2Envelope,
  type ApiV2Page,
  type GovernedErrorDTO,
  type ObjectiveReport,
  type RecoveryPoint,
} from "../contracts";
import { RecoveryObjectivesReportPage } from "../pages/RecoveryObjectivesReportPage";
import {
  BackupDisasterRecoveryError,
  backupDisasterRecoveryService,
} from "../services/backup_disaster_recovery-service";
import { configurationFixture } from "./configuration-fixture";

const pagination = {
  page: 2,
  page_size: 25,
  count: 26,
  total_pages: 2,
  has_next: false,
  has_previous: true,
} as const;
const meta = {
  correlation_id: "corr-list",
  timestamp: "2026-07-21T00:00:00Z",
  pagination,
} as const;
const point: RecoveryPoint = {
  id: "point-1",
  scope_type: "tenant",
  scope_ref: "tenant",
  backup_type: "full",
  status: "available",
  data_cutoff_at: "2026-07-20T00:00:00Z",
  captured_at: "2026-07-20T00:01:00Z",
  verified_at: "2026-07-20T00:02:00Z",
  expires_at: null,
  size_bytes: 100,
  verification_evidence: null,
  created_at: "2026-07-20T00:01:00Z",
  updated_at: "2026-07-20T00:02:00Z",
};
const envelope = <T>(data: T): ApiV2Envelope<T> => ({
  data,
  meta: { correlation_id: "corr-envelope", timestamp: "2026-07-21T00:00:00Z" },
});
const page = <T>(data: readonly T[]): ApiV2Page<T> => ({ data, meta });
const objectiveReport: ObjectiveReport = {
  from: "2026-08-01T00:00:00Z",
  to: "2026-09-01T00:00:00Z",
  bucket: "month",
  total_restores: 2,
  failed_restores: 1,
  rpo_compliance_percent: 97.5,
  rto_compliance_percent: 88.5,
  buckets: [
    {
      period_start: "2026-08-01T00:00:00Z",
      period_end: "2026-09-01T00:00:00Z",
      runbook_id: "runbook-1",
      runbook_name: "Quarter close",
      runbook_version: 3,
      restore_count: 2,
      failed_restore_count: 1,
      rpo_compliance_percent: 97.5,
      rto_compliance_percent: 88.5,
      measurements: [],
    },
    {
      period_start: "2026-08-01T00:00:00Z",
      period_end: "2026-09-01T00:00:00Z",
      runbook_id: "runbook-2",
      runbook_name: "Ledger archive",
      runbook_version: 1,
      restore_count: 1,
      failed_restore_count: 0,
      rpo_compliance_percent: 99.1,
      rto_compliance_percent: 91.2,
      measurements: [],
    },
  ],
};

const expectedDefaultObjectiveFilters = () => {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(
    start.getUTCDate() - configurationFixture.document.reports.default_interval_days
  );
  const startDate = start.toISOString().slice(0, 10);
  const endDate = end.toISOString().slice(0, 10);
  const utcBoundary = (date: string, hour: 0 | 24) => {
    const [year, month, day] = date.split("-").map(Number) as [number, number, number];
    return new Date(Date.UTC(year, month - 1, day, hour, 0, 0)).toISOString().replace(".000Z", "Z");
  };
  return {
    filters: {
      from: utcBoundary(startDate, 0),
      to: utcBoundary(endDate, 24),
      bucket: configurationFixture.document.reports.default_bucket,
    },
    startDate,
    endDate,
  } as const;
};

const renderObjectivesReportPage = (
  pageElement: ReactElement = React.createElement(RecoveryObjectivesReportPage),
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
) => {
  return render(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(
        MemoryRouter,
        { initialEntries: ["/backup-disaster-recovery/reports/objectives"] },
        React.createElement(
          Routes,
          null,
          React.createElement(Route, { path: "*", element: pageElement })
        )
      )
    )
  );
};

const readBlob = (blob: Blob): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Unable to read blob."));
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("Expected blob text result."));
        return;
      }
      resolve(reader.result);
    };
    reader.readAsText(blob);
  });

describe("backupDisasterRecoveryService", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("unwraps governed data and preserves pagination metadata", async () => {
    const envelope: ApiV2Page<RecoveryPoint> = { data: [point], meta };
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(envelope);
    await expect(
      backupDisasterRecoveryService.listRecoveryPoints({ status: "available", page: 2 })
    ).resolves.toEqual({ items: [point], pagination, correlationId: "corr-list" });
    expect(get).toHaveBeenCalledWith(expect.stringContaining("status=available"));
    expect(get).toHaveBeenCalledWith(expect.stringContaining("page=2"));
  });

  it("unwraps a detail envelope", async () => {
    const envelope: ApiV2Envelope<RecoveryPoint> = {
      data: point,
      meta: { correlation_id: "corr-detail", timestamp: "2026-07-21T00:00:00Z" },
    };
    vi.spyOn(apiClient, "get").mockResolvedValue(envelope);
    await expect(backupDisasterRecoveryService.getRecoveryPoint(point.id)).resolves.toBe(point);
  });

  it("maps governed failures to a typed error with field errors and correlation ID", async () => {
    const governed: GovernedErrorDTO = {
      error: {
        code: "invalid_scope",
        message: "Scope is not registered",
        detail: { scope_ref: ["Choose a registered scope"] },
        correlation_id: "corr-error",
      },
    };
    vi.spyOn(apiClient, "post").mockRejectedValue(
      new ApiError("Transport fallback must not replace governed message", 422, governed)
    );
    const promise = backupDisasterRecoveryService.requestBackup({
      backup_type: "full",
      scope_type: "tenant",
      scope_ref: "tenant",
      idempotency_key: "key",
    });
    await expect(promise).rejects.toMatchObject({
      status: 422,
      code: "invalid_scope",
      correlationId: "corr-error",
      message: "Scope is not registered",
      fieldErrors: [{ field: "scope_ref", code: "invalid", message: "Choose a registered scope" }],
    });
  });

  it("uses the governed configuration endpoints and unwraps previews", async () => {
    const preview = { valid: true, changes: [], document: configurationFixture.document } as const;
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: configurationFixture,
      meta: { correlation_id: "corr-config", timestamp: "2026-07-23T00:00:00Z" },
    });
    await expect(backupDisasterRecoveryService.getConfiguration()).resolves.toEqual(
      configurationFixture
    );
    expect(get).toHaveBeenCalledWith("/api/v2/backup-disaster-recovery/configurations/current/");
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: preview,
      meta: { correlation_id: "corr-preview", timestamp: "2026-07-23T00:00:00Z" },
    });
    await expect(
      backupDisasterRecoveryService.previewConfiguration({
        document: configurationFixture.document,
      })
    ).resolves.toEqual(preview);
    expect(post).toHaveBeenCalledWith("/api/v2/backup-disaster-recovery/configurations/preview/", {
      document: configurationFixture.document,
    });
  });

  it("serializes all recovery point filters and omits empty values", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(page([point]));

    await backupDisasterRecoveryService.listRecoveryPoints({
      status: "available",
      scope_type: "tenant",
      scope_ref: "tenant-a",
      captured_after: "2026-07-01T00:00:00Z",
      captured_before: "2026-07-31T23:59:59Z",
      search: "finance",
      ordering: "-captured_at",
      page: 3,
      page_size: 50,
    });
    await backupDisasterRecoveryService.listRecoveryPoints({ search: "" });

    expect(get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.RECOVERY_POINTS.LIST}?status=available&scope_type=tenant&scope_ref=tenant-a&captured_after=2026-07-01T00%3A00%3A00Z&captured_before=2026-07-31T23%3A59%3A59Z&search=finance&ordering=-captured_at&page=3&page_size=50`
    );
    expect(get).toHaveBeenNthCalledWith(2, ENDPOINTS.RECOVERY_POINTS.LIST);
  });

  it("normalizes malformed governed and network failures without fabricating fields", async () => {
    vi.spyOn(apiClient, "post")
      .mockRejectedValueOnce(
        new ApiError("plain failure", 500, {
          error: {
            code: "server_error",
            message: "Plain failure",
            detail: {
              scope_ref: ["Use a registered scope."],
              backup_type: ["Use a supported type.", 7],
              capability: "backup_disaster_recovery.execute",
            },
            correlation_id: "corr-plain",
          },
        })
      )
      .mockRejectedValueOnce(new ApiError("gateway unavailable", 503))
      .mockRejectedValueOnce("offline");

    const validationError = await backupDisasterRecoveryService
      .requestBackup({
        backup_type: "full",
        scope_type: "tenant",
        scope_ref: "",
        idempotency_key: "key-validation",
      })
      .catch((failure: unknown) => failure);
    const apiError = await backupDisasterRecoveryService
      .requestBackup({
        backup_type: "full",
        scope_type: "tenant",
        scope_ref: "tenant",
        idempotency_key: "key-api",
      })
      .catch((failure: unknown) => failure);
    const networkError = await backupDisasterRecoveryService
      .requestBackup({
        backup_type: "full",
        scope_type: "tenant",
        scope_ref: "tenant",
        idempotency_key: "key-network",
      })
      .catch((failure: unknown) => failure);

    expect(validationError).toMatchObject({
      name: "BackupDisasterRecoveryError",
      status: 500,
      code: "server_error",
      correlationId: "corr-plain",
      fieldErrors: [{ field: "scope_ref", code: "invalid", message: "Use a registered scope." }],
    });
    expect(apiError).toMatchObject({
      status: 503,
      code: "request_failed",
      correlationId: null,
      fieldErrors: [],
    });
    expect(networkError).toMatchObject({
      status: 0,
      code: "network_error",
      correlationId: null,
      fieldErrors: [],
      message: "Request failed",
    });
  });

  it("keeps typed module errors intact and normalizes paginated and delete failures", async () => {
    const typedError = new BackupDisasterRecoveryError(
      "Access denied",
      403,
      "forbidden",
      "corr-denied"
    );
    vi.spyOn(apiClient, "get")
      .mockRejectedValueOnce(typedError)
      .mockRejectedValueOnce("offline-page");
    vi.spyOn(apiClient, "delete")
      .mockRejectedValueOnce("offline-delete-runbook")
      .mockRejectedValueOnce(new Error("step delete failed"))
      .mockRejectedValueOnce("offline-delete-step");

    await expect(backupDisasterRecoveryService.getRecoveryPoint("point-denied")).rejects.toBe(
      typedError
    );
    await expect(backupDisasterRecoveryService.listRecoveryPoints()).rejects.toMatchObject({
      status: 0,
      code: "network_error",
      message: "Request failed",
    });
    await expect(backupDisasterRecoveryService.deleteRunbook("runbook-1")).rejects.toMatchObject({
      status: 0,
      code: "network_error",
      message: "Request failed",
    });
    await expect(backupDisasterRecoveryService.deleteRunbookStep("step-1")).rejects.toMatchObject({
      status: 0,
      code: "network_error",
      message: "step delete failed",
    });
    await expect(backupDisasterRecoveryService.deleteRunbookStep("step-2")).rejects.toMatchObject({
      status: 0,
      code: "network_error",
      message: "Request failed",
    });
  });

  it("passes the public endpoint matrix through the governed API client", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(envelope({ id: "entity-1" }));
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(envelope({ id: "entity-1" }));
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue(envelope({ id: "entity-1" }));
    const remove = vi.spyOn(apiClient, "delete").mockResolvedValue(undefined);

    await backupDisasterRecoveryService.getBackupStatus("backup-job-1");
    await backupDisasterRecoveryService.verifyRecoveryPoint("point-1", {
      idempotency_key: "verify-key",
    });
    await backupDisasterRecoveryService.expireRecoveryPoint("point-1", {
      transition_key: "expire-key",
    });
    await backupDisasterRecoveryService.listRestoreRuns({
      status: "ready",
      target_environment: "isolated",
      recovery_point: "point-1",
      requested_after: "2026-07-01T00:00:00Z",
      requested_before: "2026-07-31T00:00:00Z",
      page: 2,
      page_size: 10,
    });
    await backupDisasterRecoveryService.getRestoreRun("restore-1");
    await expect(
      backupDisasterRecoveryService.createRestoreRun({
        recovery_point_id: "point-1",
        target_environment: "isolated",
        target_ref: "tenant-restore",
        restore_mode: "selective",
        selected_components: ["ledger"],
        idempotency_key: "restore-key",
      })
    ).resolves.toEqual({ id: "entity-1" });
    await backupDisasterRecoveryService.executeRestoreRun("restore-1", {
      idempotency_key: "execute-key",
    });
    await backupDisasterRecoveryService.cancelRestoreRun("restore-1", {
      transition_key: "cancel-key",
    });
    await backupDisasterRecoveryService.listRunbooks({
      status: "draft",
      scope_type: "tenant",
      owner_id: "owner-1",
      search: "quarter",
      ordering: "-updated_at",
      page: 4,
      page_size: 20,
    });
    await expect(backupDisasterRecoveryService.getRunbook("runbook-1")).resolves.toEqual({
      id: "entity-1",
    });
    await expect(
      backupDisasterRecoveryService.createRunbook({
        name: "Quarter close",
        slug: "quarter-close",
        description: "Recover quarter close",
        scope_type: "tenant",
        scope_ref: "tenant",
        rpo_target_seconds: 900,
        rto_target_seconds: 1800,
      })
    ).resolves.toEqual({ id: "entity-1" });
    await backupDisasterRecoveryService.updateRunbook("runbook-1", {
      description: "Updated",
    });
    await backupDisasterRecoveryService.deleteRunbook("runbook-1");
    await expect(backupDisasterRecoveryService.cloneRunbook("runbook-1")).resolves.toEqual({
      id: "entity-1",
    });
    await expect(
      backupDisasterRecoveryService.publishRunbook("runbook-1", {
        transition_key: "publish-key",
      })
    ).resolves.toEqual({ id: "entity-1" });
    await expect(
      backupDisasterRecoveryService.retireRunbook("runbook-1", {
        transition_key: "retire-key",
      })
    ).resolves.toEqual({ id: "entity-1" });
    await backupDisasterRecoveryService.reorderRunbookSteps("runbook-1", {
      step_ids: ["step-2", "step-1"],
    });
    await backupDisasterRecoveryService.listRunbookSteps("runbook-1");
    await expect(backupDisasterRecoveryService.getRunbookStep("step-1")).resolves.toEqual({
      id: "entity-1",
    });
    await backupDisasterRecoveryService.createRunbookStep({
      runbook_id: "runbook-1",
      step_key: "validate",
      position: 1,
      name: "Validate",
      description: "Validate recovery point",
      action_type: "validate_recovery_point",
      parameters: {
        action_type: "validate_recovery_point",
        require_checksum: true,
        require_encryption: true,
      },
      timeout_seconds: 300,
      retry_limit: 2,
      on_failure: "stop",
    });
    await backupDisasterRecoveryService.updateRunbookStep("step-1", { name: "Validate point" });
    await backupDisasterRecoveryService.deleteRunbookStep("step-1");
    await backupDisasterRecoveryService.listExercises({
      status: "scheduled",
      exercise_type: "restore",
      runbook: "runbook-1",
      scheduled_after: "2026-08-01T00:00:00Z",
      scheduled_before: "2026-08-31T00:00:00Z",
      page: 5,
      page_size: 15,
    });
    await backupDisasterRecoveryService.getExercise("exercise-1");
    await backupDisasterRecoveryService.createExercise({
      name: "Restore exercise",
      runbook_id: "runbook-1",
      exercise_type: "restore",
      environment: "isolated",
      scheduled_for: "2026-08-15T00:00:00Z",
      idempotency_key: "exercise-key",
    });
    await backupDisasterRecoveryService.updateExercise("exercise-1", {
      name: "Updated restore exercise",
      scheduled_for: "2026-08-16T00:00:00Z",
    });
    await backupDisasterRecoveryService.startExercise("exercise-1", {
      idempotency_key: "start-key",
    });
    await backupDisasterRecoveryService.cancelExercise("exercise-1", {
      transition_key: "cancel-exercise",
    });
    await backupDisasterRecoveryService.listStepExecutions({
      exercise: "exercise-1",
      runbook_step: "step-1",
      status: "passed",
      page: 1,
      page_size: 25,
    });
    await backupDisasterRecoveryService.getStepExecution("execution-1");
    await backupDisasterRecoveryService.getReadiness();
    await backupDisasterRecoveryService.getObjectiveReport({
      runbook_id: "runbook-1",
      from: "2026-08-01T00:00:00Z",
      to: "2026-08-31T00:00:00Z",
      bucket: "week",
    });
    await backupDisasterRecoveryService.updateConfiguration({
      document: configurationFixture.document,
    });
    await backupDisasterRecoveryService.listConfigurationVersions();
    await backupDisasterRecoveryService.rollbackConfiguration({ version: 2 });
    await backupDisasterRecoveryService.importConfiguration({
      document: configurationFixture.document,
    });
    await backupDisasterRecoveryService.exportConfiguration();

    expect(get).toHaveBeenCalledWith(ENDPOINTS.BACKUP_EXECUTIONS.DETAIL("backup-job-1"));
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.RESTORE_RUNS.LIST}?status=ready&target_environment=isolated&recovery_point=point-1&requested_after=2026-07-01T00%3A00%3A00Z&requested_before=2026-07-31T00%3A00%3A00Z&page=2&page_size=10`
    );
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.RUNBOOKS.LIST}?status=draft&scope_type=tenant&owner_id=owner-1&search=quarter&ordering=-updated_at&page=4&page_size=20`
    );
    expect(get).toHaveBeenCalledWith(`${ENDPOINTS.RUNBOOK_STEPS.LIST}?runbook_id=runbook-1`);
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.EXERCISES.LIST}?status=scheduled&exercise_type=restore&runbook=runbook-1&scheduled_after=2026-08-01T00%3A00%3A00Z&scheduled_before=2026-08-31T00%3A00%3A00Z&page=5&page_size=15`
    );
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.STEP_EXECUTIONS.LIST}?exercise=exercise-1&runbook_step=step-1&status=passed&page=1&page_size=25`
    );
    expect(get).toHaveBeenCalledWith(
      `${ENDPOINTS.REPORTS.OBJECTIVES}?runbook_id=runbook-1&from=2026-08-01T00%3A00%3A00Z&to=2026-08-31T00%3A00%3A00Z&bucket=week`
    );
    expect(get).toHaveBeenCalledWith(ENDPOINTS.READINESS);
    expect(get).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATIONS.VERSIONS);
    expect(get).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATIONS.EXPORT);
    expect(post).toHaveBeenCalledWith(ENDPOINTS.RECOVERY_POINTS.VERIFY("point-1"), {
      idempotency_key: "verify-key",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.RECOVERY_POINTS.EXPIRE("point-1"), {
      transition_key: "expire-key",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.RESTORE_RUNS.EXECUTE("restore-1"), {
      idempotency_key: "execute-key",
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.RUNBOOKS.REORDER_STEPS("runbook-1"), {
      step_ids: ["step-2", "step-1"],
    });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATIONS.ROLLBACK, { version: 2 });
    expect(post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATIONS.IMPORT, {
      document: configurationFixture.document,
    });
    expect(patch).toHaveBeenCalledWith(ENDPOINTS.RUNBOOKS.UPDATE("runbook-1"), {
      description: "Updated",
    });
    expect(patch).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATIONS.CURRENT, {
      document: configurationFixture.document,
    });
    expect(remove).toHaveBeenCalledWith(ENDPOINTS.RUNBOOKS.DELETE("runbook-1"));
    expect(remove).toHaveBeenCalledWith(ENDPOINTS.RUNBOOK_STEPS.DELETE("step-1"));
  });
});

describe("RecoveryObjectivesReportPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("loads the default report with UTC day boundaries and renders objective evidence", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const expected = expectedDefaultObjectiveFilters();
    const getConfiguration = vi
      .spyOn(backupDisasterRecoveryService, "getConfiguration")
      .mockResolvedValue(configurationFixture);
    const getObjectiveReport = vi
      .spyOn(backupDisasterRecoveryService, "getObjectiveReport")
      .mockResolvedValue(objectiveReport);
    const createObjectUrl = vi.fn<(blob: Blob) => string>().mockReturnValue("blob:report");
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });
    const click = vi.fn();
    const anchor = document.createElement("a");
    anchor.click = click;
    const createElement = vi.spyOn(document, "createElement");
    createElement.mockImplementation(((tagName: string, options?: ElementCreationOptions) =>
      tagName === "a"
        ? anchor
        : Document.prototype.createElement.call(
            document,
            tagName,
            options
          )) as typeof document.createElement);

    renderObjectivesReportPage();

    expect(await screen.findByRole("heading", { name: "Recovery objectives" })).toBeInTheDocument();
    expect(getConfiguration).toHaveBeenCalledTimes(1);
    expect(getObjectiveReport).toHaveBeenCalledWith(expected.filters);
    expect(screen.getAllByText("97.5%")).toHaveLength(2);
    expect(screen.getAllByText("88.5%")).toHaveLength(2);
    expect(screen.getByText("Quarter close · v3")).toBeInTheDocument();
    expect(screen.getByText("Ledger archive · v1")).toBeInTheDocument();
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.stringContaining("Encountered two children with the same key"),
      expect.anything(),
      expect.anything()
    );
    expect(
      screen.getByText("Failures remain in compliance totals").closest(".rounded-lg")
    ).toHaveClass("border-destructive/50");
    const formattedFrom = new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(objectiveReport.from));
    const formattedTo = new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(objectiveReport.to));
    expect(screen.getByText(`${formattedFrom} to ${formattedTo}`)).toBeInTheDocument();
    for (const column of [
      "Period",
      "Runbook version",
      "Restores",
      "Failures",
      "RPO compliance",
      "RTO compliance",
    ]) {
      expect(screen.getByRole("columnheader", { name: column })).toBeInTheDocument();
    }

    await userEvent.click(screen.getByRole("button", { name: "Download JSON" }));

    const downloadedBlob = createObjectUrl.mock.calls[0]![0];
    await expect(readBlob(downloadedBlob)).resolves.toBe(JSON.stringify(objectiveReport, null, 2));
    expect(downloadedBlob.type).toBe("application/json");
    expect(createObjectUrl).toHaveBeenCalledWith(expect.any(Blob));
    expect(anchor.download).toBe(
      `disaster-recovery-objectives-${expected.startDate}-${expected.endDate}.json`
    );
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:report");
  });

  it("isolates the objective report query key from unrelated cached reports", async () => {
    const expected = expectedDefaultObjectiveFilters();
    const poisonedReport = {
      ...objectiveReport,
      total_restores: 99,
      rpo_compliance_percent: 1,
      rto_compliance_percent: 2,
      buckets: [],
    };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    client.setQueryData(["", "objectives", expected.filters], poisonedReport);
    client.setQueryData(["bdr", "", expected.filters], poisonedReport);
    vi.spyOn(backupDisasterRecoveryService, "getConfiguration").mockResolvedValue(
      configurationFixture
    );
    const getObjectiveReport = vi
      .spyOn(backupDisasterRecoveryService, "getObjectiveReport")
      .mockResolvedValue(objectiveReport);

    renderObjectivesReportPage(React.createElement(RecoveryObjectivesReportPage), client);

    expect(await screen.findByRole("heading", { name: "Recovery objectives" })).toBeInTheDocument();
    expect(screen.getAllByText("97.5%")).toHaveLength(2);
    expect(screen.queryByText("99")).not.toBeInTheDocument();
    expect(getObjectiveReport).toHaveBeenCalledWith(expected.filters);
  });

  it("validates and applies operator report filters without preserving whitespace", async () => {
    vi.spyOn(backupDisasterRecoveryService, "getConfiguration").mockResolvedValue(
      configurationFixture
    );
    const getObjectiveReport = vi
      .spyOn(backupDisasterRecoveryService, "getObjectiveReport")
      .mockResolvedValue(objectiveReport);

    renderObjectivesReportPage();

    expect(await screen.findByRole("heading", { name: "Recovery objectives" })).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("From"));
    await userEvent.type(screen.getByLabelText("From"), "2026-09-02");
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose a valid date range and configured bucket with From before To."
    );
    expect(getObjectiveReport).toHaveBeenCalledTimes(1);

    await userEvent.clear(screen.getByLabelText("From"));
    await userEvent.type(screen.getByLabelText("From"), "2026-08-01");
    await userEvent.clear(screen.getByLabelText("To"));
    await userEvent.type(screen.getByLabelText("To"), "2026-08-31");
    await userEvent.selectOptions(screen.getByLabelText("Bucket"), "week");
    await userEvent.type(screen.getByLabelText("Runbook ID"), " runbook-42 ");
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => expect(getObjectiveReport).toHaveBeenCalledTimes(2));
    expect(getObjectiveReport).toHaveBeenLastCalledWith({
      runbook_id: "runbook-42",
      from: "2026-08-01T00:00:00Z",
      to: "2026-09-01T00:00:00Z",
      bucket: "week",
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rejects incomplete report filters and accepts equal UTC day boundaries", async () => {
    vi.spyOn(backupDisasterRecoveryService, "getConfiguration").mockResolvedValue(
      configurationFixture
    );
    const getObjectiveReport = vi
      .spyOn(backupDisasterRecoveryService, "getObjectiveReport")
      .mockResolvedValue(objectiveReport);

    renderObjectivesReportPage();

    expect(await screen.findByRole("heading", { name: "Recovery objectives" })).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("From"));
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose a valid date range and configured bucket with From before To."
    );
    await userEvent.type(screen.getByLabelText("From"), "2026-08-15");
    await userEvent.clear(screen.getByLabelText("To"));
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose a valid date range and configured bucket with From before To."
    );
    await userEvent.type(screen.getByLabelText("To"), "2026-08-15");
    fireEvent.change(screen.getByLabelText("Bucket"), { target: { value: "" } });
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose a valid date range and configured bucket with From before To."
    );

    await userEvent.selectOptions(screen.getByLabelText("Bucket"), "day");
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => expect(getObjectiveReport).toHaveBeenCalledTimes(2));
    expect(getObjectiveReport).toHaveBeenLastCalledWith({
      from: "2026-08-15T00:00:00Z",
      to: "2026-08-16T00:00:00Z",
      bucket: "day",
    });
  });

  it("shows empty objective evidence when the report has no buckets", async () => {
    vi.spyOn(backupDisasterRecoveryService, "getConfiguration").mockResolvedValue(
      configurationFixture
    );
    vi.spyOn(backupDisasterRecoveryService, "getObjectiveReport").mockResolvedValue({
      ...objectiveReport,
      buckets: [],
      total_restores: 0,
      failed_restores: 0,
    });

    renderObjectivesReportPage();

    expect(await screen.findByText("No objective measurements")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download JSON" })).toBeEnabled();
    expect(
      screen.getByText("Failures remain in compliance totals").closest(".rounded-lg")
    ).not.toHaveClass("border-destructive/50");
  });

  it("shows retryable errors for configuration and report failures", async () => {
    const getConfiguration = vi
      .spyOn(backupDisasterRecoveryService, "getConfiguration")
      .mockRejectedValueOnce(
        new BackupDisasterRecoveryError("Configuration unavailable", 503, "unavailable", "corr-cfg")
      )
      .mockResolvedValue(configurationFixture);
    const getObjectiveReport = vi
      .spyOn(backupDisasterRecoveryService, "getObjectiveReport")
      .mockRejectedValueOnce(
        new BackupDisasterRecoveryError("Report unavailable", 503, "unavailable", "corr-report")
      )
      .mockResolvedValue(objectiveReport);

    renderObjectivesReportPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-cfg");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(getConfiguration).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-report");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(getObjectiveReport).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "Recovery objectives" })).toBeInTheDocument();
  });

  it("keeps the report query disabled until governed configuration supplies defaults", async () => {
    vi.spyOn(backupDisasterRecoveryService, "getConfiguration").mockResolvedValue(null as never);
    const getObjectiveReport = vi.spyOn(backupDisasterRecoveryService, "getObjectiveReport");

    renderObjectivesReportPage();

    expect(await screen.findByLabelText("Loading disaster recovery data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    expect(getObjectiveReport).not.toHaveBeenCalled();
  });
});
