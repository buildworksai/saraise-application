/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method, @typescript-eslint/no-unsafe-assignment -- cohesive catalog page coverage keeps related fixtures and Vitest service-spy assertions local. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type { BackupSchedule } from "../contracts";
import { BackupJobCreatePage } from "../pages/BackupJobCreatePage";
import { BackupJobEditPage } from "../pages/BackupJobEditPage";
import { BackupJobListPage } from "../pages/BackupJobListPage";
import { BackupRecoveryOverviewPage } from "../pages/BackupRecoveryOverviewPage";
import {
  BackupArchiveListPage,
  BackupRetentionPolicyListPage,
  BackupScheduleListPage,
  BackupStorageTargetListPage,
  BackupVerificationListPage,
} from "../pages/CatalogListPages";
import {
  BackupArchiveDetailPage,
  BackupRetentionPolicyDetailPage,
  BackupScheduleDetailPage,
  BackupStorageTargetDetailPage,
  BackupVerificationDetailPage,
} from "../pages/ResourceDetailPages";
import {
  BackupRetentionPolicyCreatePage,
  BackupRetentionPolicyEditPage,
  BackupScheduleCreatePage,
  BackupScheduleEditPage,
  BackupStorageTargetCreatePage,
  BackupStorageTargetEditPage,
} from "../pages/ResourceFormPages";
import { formatBytes, PageHeader } from "../components/BackupRecoveryUI";
import { BackupRecoveryApiError, backupRecoveryService } from "../services/backup-recovery-service";

const pagination = {
  page: 1,
  page_size: 25,
  count: 0,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};
const authUser = {
  id: "user-1",
  email: "admin@example.com",
  username: "admin",
  is_staff: true,
  is_superuser: false,
  tenant_id: "tenant-1",
  platform_role: null,
  tenant_role: "tenant_admin",
};
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>;
}

function requireElement(element: HTMLElement | undefined): HTMLElement {
  expect(element).toBeDefined();
  return element!;
}

function renderPage(ui: ReactNode, route = "/backup-recovery/jobs") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <LocationProbe />
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderRoutedPage(ui: ReactNode, path: string, route: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <LocationProbe />
        <Routes>
          <Route path={path} element={ui} />
          <Route path="*" element={<span />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const allowed = { allowed: true };
const entityBase = {
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
  is_deleted: false,
  deleted_at: null,
};
const target = {
  ...entityBase,
  id: "target-1",
  name: "Immutable vault",
  adapter_key: "s3",
  locator_prefix_ref: "secret://backup/target",
  configuration_ref: "secret://backup/config",
  encryption_key_ref: "secret://backup/key",
  is_default: false,
  is_active: true,
  allowed_commands: { update: allowed, set_default: allowed, probe: allowed, delete: allowed },
};
const policy = {
  ...entityBase,
  id: "policy-1",
  name: "Regulated retention",
  description: "Keep monthly evidence.",
  archive_after_days: 30,
  retention_days: 365,
  keep_last_successful: 3,
  is_active: true,
  allowed_commands: { update: allowed, activate: allowed, delete: allowed },
};
const schedule = {
  ...entityBase,
  id: "schedule-1",
  name: "Nightly financials",
  scope_type: "tenant",
  scope_ref: "tenant-main",
  backup_type: "full",
  frequency: "daily",
  schedule_time: "02:00:00",
  day_of_week: null,
  day_of_month: null,
  timezone: "UTC",
  storage_target: "target-1",
  storage_target_name: "Immutable vault",
  retention_policy: "policy-1",
  retention_policy_name: "Regulated retention",
  is_active: true,
  next_run_at: "2026-07-22T02:00:00Z",
  last_run_at: null,
  description: "Nightly critical ledger capture",
  allowed_commands: { update: allowed, execute: allowed, activate: allowed, delete: allowed },
} satisfies BackupSchedule;
const archive = {
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-07-22T02:00:00Z",
  updated_at: "2026-07-22T02:00:00Z",
  id: "archive-1",
  backup_job: "job-1",
  backup_type: "full",
  lifecycle: "available",
  adapter_key: "s3",
  artifact_locator_ref: "secret://archive/one",
  size_bytes: 0,
  checksum_algorithm: "sha256",
  checksum_digest: "abc123",
  provider_acknowledgement: "ack-1",
  data_cutoff_at: "2026-07-22T01:59:00Z",
  captured_at: "2026-07-22T02:00:00Z",
  expires_at: null,
  archived_at: "2026-07-22T02:00:00Z",
  integrity_status: "verified",
  last_verified_at: null,
  purged_at: null,
  allowed_commands: { verify: allowed },
};
const verification = {
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-07-22T03:00:00Z",
  updated_at: "2026-07-22T03:10:00Z",
  id: "verification-1",
  archive: "archive-1",
  async_job_id: "async-1",
  status: "running",
  idempotency_key: "verify-key",
  requested_at: "2026-07-22T03:00:00Z",
  started_at: "2026-07-22T03:01:00Z",
  completed_at: null,
  checksum_matches: null,
  artifact_available: true,
  encryption_metadata_valid: true,
  provider_acknowledged: true,
  evidence: { adapter: "s3" },
  error_code: "",
  error_message: "",
  correlation_id: "corr-verification",
  allowed_commands: { cancel: allowed },
};
const pendingJob = {
  ...entityBase,
  id: "job-1",
  schedule: "schedule-1",
  schedule_name: "Nightly financials",
  storage_target: "target-1",
  storage_target_name: "Immutable vault",
  retention_policy: "policy-1",
  retention_policy_name: "Regulated retention",
  retry_of: null,
  base_job: null,
  archive: null,
  async_job_id: "async-1",
  scope_type: "tenant",
  scope_ref: "tenant-main",
  backup_type: "full",
  status: "pending",
  idempotency_key: "job-key",
  description: "Original operator context",
  requested_at: "2026-07-22T01:59:00Z",
  started_at: null,
  completed_at: null,
  data_cutoff_at: null,
  size_bytes: null,
  error_code: "",
  error_message: "",
  correlation_id: "corr-job",
  transition_history: [],
  allowed_commands: { update: allowed, cancel: allowed, retry: allowed, delete: allowed },
};

describe("backup recovery governed page states", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.getState().logout();
  });

  it("aggregates overview protection evidence across paged archives and routes metrics", async () => {
    useAuthStore.setState({ user: authUser, isAuthenticated: true, isLoading: false });
    vi.spyOn(backupRecoveryService, "health").mockResolvedValue({
      status: "degraded",
      ready: true,
      checked_at: "2026-07-22T00:00:00Z",
      database: { key: "database", status: "healthy", critical: true },
      async_jobs: { key: "async_jobs", status: "healthy", critical: true },
      outbox: { key: "outbox", status: "degraded", critical: true, detail: "2 events pending" },
      scheduler: { key: "scheduler", status: "healthy", critical: false },
      adapters: [{ key: "local-filesystem", status: "healthy", critical: true }],
      correlation_id: "corr-health",
    });
    const listJobs = vi
      .spyOn(backupRecoveryService, "listBackupJobs")
      .mockImplementation((filters = {}) =>
        Promise.resolve({
          items:
            filters.status === "completed"
              ? [
                  {
                    ...entityBase,
                    id: "job-completed",
                    schedule: "schedule-1",
                    schedule_name: "Nightly financials",
                    storage_target: "target-1",
                    storage_target_name: "Immutable vault",
                    retention_policy: "policy-1",
                    retry_of: null,
                    base_job: null,
                    async_job_id: "async-1",
                    scope_type: "tenant",
                    scope_ref: "tenant-main",
                    backup_type: "full",
                    status: "completed",
                    idempotency_key: "job-key",
                    description: "Nightly tenant capture",
                    requested_at: "2026-07-22T01:59:00Z",
                    started_at: "2026-07-22T02:00:00Z",
                    completed_at: "2026-07-22T02:05:00Z",
                    data_cutoff_at: "2026-07-22T01:59:00Z",
                    size_bytes: 2048,
                    error_code: "",
                    error_message: "",
                    transition_history: [],
                  },
                ]
              : filters.status === "failed"
                ? [
                    {
                      ...entityBase,
                      id: "job-failed",
                      schedule: null,
                      schedule_name: null,
                      storage_target: "target-1",
                      retention_policy: null,
                      retry_of: null,
                      base_job: null,
                      async_job_id: "async-2",
                      scope_type: "database",
                      scope_ref: "ledger",
                      backup_type: "incremental",
                      status: "failed",
                      idempotency_key: "failed-key",
                      description: "Ledger delta",
                      requested_at: "2026-07-22T03:00:00Z",
                      started_at: "2026-07-22T03:00:30Z",
                      completed_at: "2026-07-22T03:05:00Z",
                      data_cutoff_at: null,
                      size_bytes: null,
                      error_code: "PROVIDER_TIMEOUT",
                      error_message: "timed out",
                      transition_history: [],
                    },
                  ]
                : [],
          pagination: {
            ...pagination,
            count: filters.status === "running" ? 2 : filters.status === "failed" ? 1 : 1,
          },
          correlationId: "corr-jobs",
        } as never)
      );
    vi.spyOn(backupRecoveryService, "listBackupSchedules").mockResolvedValue({
      items: [schedule],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-schedules",
    });
    vi.spyOn(backupRecoveryService, "listStorageTargets").mockResolvedValue({
      items: [target],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-targets",
    });
    const listArchives = vi
      .spyOn(backupRecoveryService, "listBackupArchives")
      .mockImplementation((filters = {}) =>
        Promise.resolve({
          items:
            filters.page === 2
              ? [{ ...archive, id: "archive-2", size_bytes: 2048 }]
              : [{ ...archive, id: "archive-1", size_bytes: 1024 }],
          pagination: {
            ...pagination,
            count: 2,
            total_pages: 2,
            page: Number(filters.page ?? 1),
          },
          correlationId: "corr-archives",
        } as never)
      );

    renderPage(<BackupRecoveryOverviewPage />, "/backup-recovery");

    expect(
      await screen.findByRole("heading", { name: "Backup protection posture" })
    ).toBeInTheDocument();
    expect(
      screen.getByText("Provider-backed protection evidence is available")
    ).toBeInTheDocument();
    expect(screen.getByText("Across 2 available artifacts")).toBeInTheDocument();
    expect(screen.getByText("Failures requiring action")).toBeInTheDocument();
    expect(screen.getByText("PROVIDER_TIMEOUT")).toBeInTheDocument();
    expect(listJobs).toHaveBeenCalledWith(expect.objectContaining({ status: "running" }));
    expect(listArchives).toHaveBeenCalledWith(
      expect.objectContaining({ lifecycle: "available", page: 2, page_size: 100 })
    );

    await userEvent.click(screen.getByText("Running now"));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/jobs?status=running"
    );
  });

  it("keeps overview attention state when protection prerequisites are absent", async () => {
    useAuthStore.setState({ user: authUser, isAuthenticated: true, isLoading: false });
    vi.spyOn(backupRecoveryService, "health").mockResolvedValue({
      status: "unavailable",
      ready: false,
      checked_at: "2026-07-22T00:00:00Z",
      database: { key: "database", status: "unavailable", critical: true },
      async_jobs: { key: "async_jobs", status: "unavailable", critical: true },
      outbox: { key: "outbox", status: "unavailable", critical: true },
      scheduler: { key: "scheduler", status: "unavailable", critical: false },
      adapters: [],
      correlation_id: "corr-health",
    });
    vi.spyOn(backupRecoveryService, "listBackupJobs").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-jobs",
    });
    vi.spyOn(backupRecoveryService, "listBackupSchedules").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-schedules",
    });
    vi.spyOn(backupRecoveryService, "listStorageTargets").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-targets",
    });
    vi.spyOn(backupRecoveryService, "listBackupArchives").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-archives",
    });

    renderPage(<BackupRecoveryOverviewPage />, "/backup-recovery");

    expect(await screen.findByText("Protection requires attention")).toBeInTheDocument();
    expect(screen.getByText("No verified completion")).toBeInTheDocument();
    expect(screen.getByText("None scheduled")).toBeInTheDocument();
    expect(screen.getByText("No active backup failures")).toBeInTheDocument();
    expect(
      screen.getByText("No adapter health evidence is available. This is not reported as healthy.")
    ).toBeInTheDocument();
  });

  it("renders an accessible skeleton while initial data is pending", () => {
    vi.spyOn(backupRecoveryService, "listBackupJobs").mockReturnValue(
      new Promise<never>(() => undefined)
    );
    renderPage(<BackupJobListPage />);
    expect(screen.getByLabelText("Loading backup recovery information")).toHaveAttribute(
      "aria-busy",
      "true"
    );
  });

  it("distinguishes true empty and filtered-empty states", async () => {
    vi.spyOn(backupRecoveryService, "listBackupJobs").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr",
    });
    const first = renderPage(<BackupJobListPage />);
    expect(await screen.findByText("No backups requested yet")).toBeInTheDocument();
    first.unmount();
    renderPage(<BackupJobListPage />, "/backup-recovery/jobs?status=failed");
    expect(await screen.findByText("No jobs match these filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset filters" })).toBeEnabled();
  });

  it("renders permission denial and correlation ID from governed errors", async () => {
    vi.spyOn(backupRecoveryService, "listBackupJobs").mockRejectedValue(
      new BackupRecoveryApiError("Denied", 403, "ACCESS_DENIED", "corr-denied")
    );
    renderPage(<BackupJobListPage />);
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Correlation ID: corr-denied/ })).toBeInTheDocument();
  });

  it("retries backup job list failures and preserves explicit filter payloads", async () => {
    const list = vi
      .spyOn(backupRecoveryService, "listBackupJobs")
      .mockRejectedValueOnce(
        new BackupRecoveryApiError("Index unavailable", 503, "INDEX_UNAVAILABLE", "corr-index")
      )
      .mockResolvedValue({
        items: [pendingJob],
        pagination: { ...pagination, count: 1, total_pages: 1 },
        correlationId: "corr-jobs",
      } as never);

    renderPage(
      <BackupJobListPage />,
      "/backup-recovery/jobs?status=pending&backup_type=full&search=ledger"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-index");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(list).toHaveBeenLastCalledWith(
      expect.objectContaining({
        status: "pending",
        backup_type: "full",
        search: "ledger",
        ordering: "-requested_at",
      })
    );
    await userEvent.selectOptions(await screen.findByLabelText("Sort jobs"), "-size_bytes");
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ ordering: "-size_bytes" }))
    );
  });

  it("preserves zero-byte artifact truth and locks duplicate backup submissions", async () => {
    expect(formatBytes(0)).toBe("0 B");
    vi.spyOn(backupRecoveryService, "listStorageTargets").mockResolvedValue({
      items: [{ id: "target", name: "Local", adapter_key: "local-filesystem", is_default: true }],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr",
    } as never);
    vi.spyOn(backupRecoveryService, "listRetentionPolicies").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr",
    });
    vi.spyOn(backupRecoveryService, "createBackupJob").mockReturnValue(
      new Promise<never>(() => undefined)
    );
    renderPage(<BackupJobCreatePage />, "/backup-recovery/jobs/new");
    const submit = await screen.findByRole("button", { name: "Request backup" });
    expect(document.title).toBe("Request backup · SARAISE");
    await userEvent.click(submit);
    expect(await screen.findByRole("button", { name: "Durably queueing…" })).toBeDisabled();
  });

  it("updates the browser title when the shared page header title changes", () => {
    const rendered = render(<PageHeader title="Request backup" />);

    expect(document.title).toBe("Request backup · SARAISE");

    rendered.rerender(<PageHeader title="Add storage target" />);

    expect(document.title).toBe("Add storage target · SARAISE");
  });

  it("filters schedule lists, renders rows, and routes to create and detail pages", async () => {
    const list = vi.spyOn(backupRecoveryService, "listBackupSchedules").mockResolvedValue({
      items: [
        {
          id: "schedule-1",
          name: "Nightly financials",
          description: "Nightly critical ledger capture",
          scope_type: "tenant",
          scope_ref: "tenant-main",
          frequency: "daily",
          cron_expression: "0 2 * * *",
          timezone: "UTC",
          retention_policy: "policy-1",
          storage_target: "target-1",
          storage_target_name: "Immutable vault",
          is_active: true,
          next_run_at: "2026-07-22T02:00:00Z",
          last_run_at: null,
          created_at: "2026-07-20T00:00:00Z",
          updated_at: "2026-07-21T00:00:00Z",
        },
      ],
      pagination: { ...pagination, count: 26, total_pages: 2, has_next: true },
      correlationId: "corr-schedules",
    } as never);
    renderPage(<BackupScheduleListPage />, "/backup-recovery/schedules?search=nightly");

    expect(await screen.findByRole("heading", { name: "Backup schedules" })).toBeInTheDocument();
    expect(list).toHaveBeenLastCalledWith(
      expect.objectContaining({ search: "nightly", ordering: "name" })
    );
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/schedules/new"
    );

    await userEvent.click(screen.getByRole("button", { name: "Nightly financials" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/schedules/schedule-1"
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  });

  it("renders retention policies and resets filtered-empty server state", async () => {
    const list = vi.spyOn(backupRecoveryService, "listRetentionPolicies").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-empty-policies",
    });
    renderPage(
      <BackupRetentionPolicyListPage />,
      "/backup-recovery/retention-policies?is_active=false"
    );

    expect(await screen.findByText("No policies match")).toBeInTheDocument();
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ is_active: false }));
    await userEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/retention-policies"
    );
  });

  it("renders storage target rows without exposing credential values", async () => {
    vi.spyOn(backupRecoveryService, "listStorageTargets").mockResolvedValue({
      items: [
        {
          id: "target-1",
          name: "Immutable vault",
          description: "WORM store",
          adapter_key: "s3",
          locator_prefix_ref: "secret://backup/target",
          credential_ref: "secret://must-not-render",
          configuration: { bucket: "private" },
          is_default: true,
          is_active: true,
          created_at: "2026-07-20T00:00:00Z",
          updated_at: "2026-07-21T00:00:00Z",
        },
      ],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-targets",
    } as never);
    renderPage(<BackupStorageTargetListPage />, "/backup-recovery/storage-targets?adapter_key=s3");

    expect(await screen.findByRole("button", { name: "Immutable vault" })).toBeInTheDocument();
    expect(screen.getByText("secret://backup/target")).toBeInTheDocument();
    expect(screen.queryByText("secret://must-not-render")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Immutable vault" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/storage-targets/target-1"
    );
  });

  it("renders archive and verification evidence states from immutable catalog data", async () => {
    vi.spyOn(backupRecoveryService, "listBackupArchives").mockResolvedValue({
      items: [
        {
          id: "archive-1",
          backup_job: "job-1",
          storage_target: "target-1",
          adapter_key: "s3",
          locator_ref: "secret://archive/one",
          checksum_sha256: "abc123",
          size_bytes: 0,
          lifecycle: "available",
          integrity_status: "verified",
          captured_at: "2026-07-22T02:00:00Z",
          expires_at: null,
          created_at: "2026-07-22T02:00:00Z",
          updated_at: "2026-07-22T02:00:00Z",
        },
      ],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-archives",
    } as never);
    const first = renderPage(<BackupArchiveListPage />, "/backup-recovery/archives");
    expect(await screen.findByText("0 B")).toBeInTheDocument();
    expect(screen.queryByText("secret://archive/one")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /2026/u }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/archives/archive-1"
    );

    first.unmount();
    vi.spyOn(backupRecoveryService, "listBackupVerifications").mockResolvedValue({
      items: [
        {
          id: "verification-1",
          archive: "archive-1",
          status: "failed",
          requested_at: "2026-07-22T03:00:00Z",
          completed_at: "2026-07-22T03:10:00Z",
          checksum_matches: false,
          artifact_available: false,
          error_code: "CHECKSUM_MISMATCH",
          error_message: "mismatch",
          created_at: "2026-07-22T03:00:00Z",
          updated_at: "2026-07-22T03:10:00Z",
        },
      ],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-verifications",
    } as never);
    renderPage(<BackupVerificationListPage />, "/backup-recovery/verifications?status=failed");
    expect(await screen.findByText("Mismatch")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /2026/u }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/verifications/verification-1"
    );
  });

  it("renders retention rows and true-empty catalog actions without server-side defaults", async () => {
    const listPolicies = vi
      .spyOn(backupRecoveryService, "listRetentionPolicies")
      .mockResolvedValue({
        items: [
          {
            ...policy,
            archive_after_days: null,
            keep_last_successful: 5,
            allowed_commands: { update: allowed, activate: allowed, delete: allowed },
          },
        ],
        pagination: { ...pagination, count: 1, total_pages: 1 },
        correlationId: "corr-policies",
      } as never);

    const policies = renderPage(
      <BackupRetentionPolicyListPage />,
      "/backup-recovery/retention-policies"
    );
    expect(await screen.findByRole("button", { name: "Regulated retention" })).toBeInTheDocument();
    expect(screen.getByText("Never")).toBeInTheDocument();
    expect(screen.getByText("Last 5 successful")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Policy state filter"), "true");
    await waitFor(() =>
      expect(listPolicies).toHaveBeenLastCalledWith(expect.objectContaining({ is_active: true }))
    );
    await userEvent.click(screen.getByRole("button", { name: "Regulated retention" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/retention-policies/policy-1"
    );
    policies.unmount();

    vi.spyOn(backupRecoveryService, "listStorageTargets").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-targets",
    });
    const targets = renderPage(<BackupStorageTargetListPage />, "/backup-recovery/storage-targets");
    expect(await screen.findByText("No storage target")).toBeInTheDocument();
    await userEvent.click(requireElement(screen.getAllByRole("button", { name: "Add target" })[1]));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/storage-targets/new"
    );
    targets.unmount();

    vi.spyOn(backupRecoveryService, "listBackupSchedules").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-schedules",
    });
    renderPage(<BackupScheduleListPage />, "/backup-recovery/schedules");
    expect(await screen.findByText("No schedules configured")).toBeInTheDocument();
    await userEvent.click(
      requireElement(screen.getAllByRole("button", { name: "Create schedule" })[1])
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/schedules/new"
    );
  });

  it("resets filtered archive and verification catalogs and preserves pending evidence labels", async () => {
    const listArchives = vi.spyOn(backupRecoveryService, "listBackupArchives").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-archives",
    });
    const archives = renderPage(
      <BackupArchiveListPage />,
      "/backup-recovery/archives?lifecycle=expired&integrity_status=corrupt&search=job-9"
    );
    expect(await screen.findByText("No artifacts match")).toBeInTheDocument();
    expect(listArchives).toHaveBeenLastCalledWith(
      expect.objectContaining({
        lifecycle: "expired",
        integrity_status: "corrupt",
        search: "job-9",
      })
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/backup-recovery/archives");
    archives.unmount();

    const listVerifications = vi
      .spyOn(backupRecoveryService, "listBackupVerifications")
      .mockResolvedValue({
        items: [
          {
            ...verification,
            checksum_matches: null,
            artifact_available: null,
            status: "pending",
          },
          {
            ...verification,
            id: "verification-2",
            checksum_matches: true,
            artifact_available: true,
            status: "passed",
          },
        ],
        pagination: { ...pagination, count: 2, total_pages: 1 },
        correlationId: "corr-verifications",
      } as never);
    renderPage(
      <BackupVerificationListPage />,
      "/backup-recovery/verifications?archive_id=archive-1&status=pending"
    );
    expect(await screen.findByText("Matches")).toBeInTheDocument();
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(screen.getAllByText("Pending")).toHaveLength(3);
    expect(listVerifications).toHaveBeenLastCalledWith(
      expect.objectContaining({ archive_id: "archive-1", status: "pending" })
    );
    await userEvent.click(requireElement(screen.getAllByRole("button", { name: /2026/u })[1]));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/verifications/verification-2"
    );
  });

  it("retries catalog list failures without fabricating successful evidence", async () => {
    const listSchedules = vi
      .spyOn(backupRecoveryService, "listBackupSchedules")
      .mockRejectedValueOnce(
        new BackupRecoveryApiError("Scheduler unavailable", 503, "SCHEDULER_DOWN", "corr-schedule")
      )
      .mockResolvedValue({
        items: [schedule],
        pagination: { ...pagination, count: 1, total_pages: 1 },
        correlationId: "corr-schedules",
      } as never);

    const schedules = renderPage(<BackupScheduleListPage />, "/backup-recovery/schedules");
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-schedule");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(listSchedules).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("button", { name: "Nightly financials" })).toBeInTheDocument();
    schedules.unmount();

    const listTargets = vi
      .spyOn(backupRecoveryService, "listStorageTargets")
      .mockRejectedValueOnce(
        new BackupRecoveryApiError(
          "Vault index unavailable",
          503,
          "TARGET_INDEX_DOWN",
          "corr-target"
        )
      )
      .mockResolvedValue({
        items: [target],
        pagination: { ...pagination, count: 1, total_pages: 1 },
        correlationId: "corr-targets",
      } as never);

    const targets = renderPage(<BackupStorageTargetListPage />, "/backup-recovery/storage-targets");
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-target");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(listTargets).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("button", { name: "Immutable vault" })).toBeInTheDocument();
    targets.unmount();

    const listArchives = vi
      .spyOn(backupRecoveryService, "listBackupArchives")
      .mockRejectedValueOnce(
        new BackupRecoveryApiError("Catalog unavailable", 503, "ARCHIVE_INDEX_DOWN", "corr-archive")
      )
      .mockResolvedValue({
        items: [archive],
        pagination: { ...pagination, count: 1, total_pages: 1 },
        correlationId: "corr-archives",
      } as never);

    renderPage(<BackupArchiveListPage />, "/backup-recovery/archives");
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-archive");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(listArchives).toHaveBeenCalledTimes(2));
    expect(screen.getByText("0 B")).toBeInTheDocument();
  });

  it("runs schedule detail commands through governed service endpoints", async () => {
    vi.spyOn(backupRecoveryService, "getBackupSchedule").mockResolvedValue(schedule as never);
    vi.spyOn(backupRecoveryService, "deactivateBackupSchedule").mockResolvedValue({
      ...schedule,
      is_active: false,
    } as never);
    vi.spyOn(backupRecoveryService, "runBackupScheduleNow").mockResolvedValue({
      job_id: "job-queued",
      async_job_id: "async-queued",
      status: "pending",
      idempotency_key: "key",
    } as never);
    vi.spyOn(backupRecoveryService, "deleteBackupSchedule").mockResolvedValue(undefined as never);

    const first = renderRoutedPage(
      <BackupScheduleDetailPage />,
      "/backup-recovery/schedules/:id",
      "/backup-recovery/schedules/schedule-1"
    );

    expect(await screen.findByRole("heading", { name: "Nightly financials" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(backupRecoveryService.deactivateBackupSchedule).toHaveBeenCalledWith("schedule-1");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete schedule" }));
    expect(backupRecoveryService.deleteBackupSchedule).toHaveBeenCalledWith("schedule-1");
    first.unmount();

    renderRoutedPage(
      <BackupScheduleDetailPage />,
      "/backup-recovery/schedules/:id",
      "/backup-recovery/schedules/schedule-1"
    );
    expect(await screen.findByRole("heading", { name: "Nightly financials" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Run now" }));
    expect(backupRecoveryService.runBackupScheduleNow).toHaveBeenCalledWith(
      "schedule-1",
      expect.objectContaining({ idempotency_key: expect.stringMatching(/^schedule-run:/u) })
    );
  });

  it("renders policy preview and target provider actions without exposing secrets", async () => {
    vi.spyOn(backupRecoveryService, "getRetentionPolicy").mockResolvedValue(policy as never);
    vi.spyOn(backupRecoveryService, "previewRetentionPolicy").mockResolvedValue({
      captured_at: "2026-07-22T02:00:00Z",
      archive_at: "2026-08-21T02:00:00Z",
      expires_at: "2027-07-22T02:00:00Z",
      retention_days: 365,
      archive_after_days: 30,
      keep_last_successful: 3,
    });
    vi.spyOn(backupRecoveryService, "deactivateRetentionPolicy").mockResolvedValue({
      ...policy,
      is_active: false,
    } as never);
    vi.spyOn(backupRecoveryService, "getStorageTarget").mockResolvedValue(target as never);
    vi.spyOn(backupRecoveryService, "setDefaultStorageTarget").mockResolvedValue({
      ...target,
      is_default: true,
    } as never);
    vi.spyOn(backupRecoveryService, "probeStorageTarget").mockResolvedValue({
      healthy: false,
      message: "Provider timeout",
      checked_at: "2026-07-22T02:00:00Z",
      details: {},
      correlation_id: "corr-probe",
    });
    vi.spyOn(backupRecoveryService, "deactivateStorageTarget").mockResolvedValue({
      ...target,
      is_active: false,
    } as never);

    const policyPage = renderRoutedPage(
      <BackupRetentionPolicyDetailPage />,
      "/backup-recovery/retention-policies/:id",
      "/backup-recovery/retention-policies/policy-1"
    );
    expect(await screen.findByText("365 days")).toBeInTheDocument();
    expect(screen.getByText("30 days")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(backupRecoveryService.deactivateRetentionPolicy).toHaveBeenCalledWith("policy-1");
    policyPage.unmount();

    renderRoutedPage(
      <BackupStorageTargetDetailPage />,
      "/backup-recovery/storage-targets/:id",
      "/backup-recovery/storage-targets/target-1"
    );
    expect(await screen.findByText("secret://backup/config")).toBeInTheDocument();
    expect(screen.queryByText("private-access-token")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Set default" }));
    expect(backupRecoveryService.setDefaultStorageTarget).toHaveBeenCalledWith("target-1");
    await userEvent.click(screen.getByRole("button", { name: "Probe provider" }));
    expect(await screen.findByText("Provider timeout")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(backupRecoveryService.deactivateStorageTarget).toHaveBeenCalledWith("target-1");
  });

  it("queues archive verification and cancels running verification with idempotency evidence", async () => {
    vi.spyOn(backupRecoveryService, "getBackupArchive").mockResolvedValue(archive as never);
    vi.spyOn(backupRecoveryService, "requestArchiveVerification").mockResolvedValue({
      ...verification,
      status: "pending",
    } as never);
    vi.spyOn(backupRecoveryService, "getBackupVerification").mockResolvedValue(
      verification as never
    );
    vi.spyOn(backupRecoveryService, "cancelBackupVerification").mockResolvedValue({
      ...verification,
      status: "cancelled",
    } as never);

    const archivePage = renderRoutedPage(
      <BackupArchiveDetailPage />,
      "/backup-recovery/archives/:id",
      "/backup-recovery/archives/archive-1"
    );
    expect(await screen.findByText("abc123")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Verify integrity" }));
    expect(backupRecoveryService.requestArchiveVerification).toHaveBeenCalledWith(
      "archive-1",
      expect.objectContaining({ idempotency_key: expect.stringMatching(/^verify:/u) })
    );
    archivePage.unmount();

    renderRoutedPage(
      <BackupVerificationDetailPage />,
      "/backup-recovery/verifications/:id",
      "/backup-recovery/verifications/verification-1"
    );
    expect(await screen.findByText("corr-verification")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel verification" }));
    expect(backupRecoveryService.cancelBackupVerification).toHaveBeenCalledWith(
      "verification-1",
      expect.objectContaining({ transition_key: expect.stringMatching(/^verification-cancel:/u) })
    );
  });

  it("submits schedule, retention, and target forms with normalized payloads", async () => {
    vi.spyOn(backupRecoveryService, "listStorageTargets").mockResolvedValue({
      items: [target],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-targets",
    } as never);
    vi.spyOn(backupRecoveryService, "listRetentionPolicies").mockResolvedValue({
      items: [policy],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-policies",
    } as never);
    vi.spyOn(backupRecoveryService, "createBackupSchedule").mockResolvedValue(schedule as never);
    vi.spyOn(backupRecoveryService, "createRetentionPolicy").mockResolvedValue(policy as never);
    vi.spyOn(backupRecoveryService, "createStorageTarget").mockResolvedValue(target as never);

    const schedulePage = renderPage(<BackupScheduleCreatePage />, "/backup-recovery/schedules/new");
    await userEvent.type(await screen.findByLabelText("Schedule name"), "Weekly finance");
    await userEvent.selectOptions(screen.getByLabelText("Frequency"), "weekly");
    await userEvent.type(screen.getByLabelText("Scope reference"), "-finance");
    await userEvent.type(screen.getByLabelText("Local run time"), "02:30");
    await userEvent.type(screen.getByLabelText("Day of week (0 Monday–6 Sunday)"), "4");
    await userEvent.click(screen.getByRole("button", { name: "Create schedule" }));
    expect(backupRecoveryService.createBackupSchedule).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Weekly finance",
        frequency: "weekly",
        schedule_time: "02:30",
        day_of_week: 4,
        day_of_month: null,
        storage_target_id: "target-1",
        retention_policy_id: "policy-1",
      })
    );
    schedulePage.unmount();

    const policyPage = renderPage(
      <BackupRetentionPolicyCreatePage />,
      "/backup-recovery/retention-policies/new"
    );
    await userEvent.clear(screen.getByLabelText("Policy name"));
    await userEvent.click(screen.getByRole("button", { name: "Save policy" }));
    expect(screen.getByText("Policy name is required")).toBeInTheDocument();
    expect(backupRecoveryService.createRetentionPolicy).not.toHaveBeenCalled();

    await userEvent.clear(screen.getByLabelText("Policy name"));
    await userEvent.type(screen.getByLabelText("Policy name"), "Quarterly keep");
    await userEvent.clear(screen.getByLabelText("Archive after days (optional)"));
    await userEvent.click(screen.getByRole("button", { name: "Save policy" }));
    expect(backupRecoveryService.createRetentionPolicy).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Quarterly keep",
        retention_days: 30,
        archive_after_days: null,
        keep_last_successful: 3,
      })
    );
    policyPage.unmount();

    renderPage(<BackupStorageTargetCreatePage />, "/backup-recovery/storage-targets/new");
    await userEvent.click(screen.getByRole("button", { name: "Save target" }));
    expect(screen.getByText("Target name is required")).toBeInTheDocument();
    expect(screen.getByText("Locator prefix reference is required")).toBeInTheDocument();
    expect(screen.getByText("Configuration reference is required")).toBeInTheDocument();
    expect(backupRecoveryService.createStorageTarget).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("Target name"), "Vault");
    await userEvent.type(screen.getByLabelText("Locator prefix reference"), "secret://vault");
    await userEvent.type(screen.getByLabelText("Configuration reference"), "secret://config");
    await userEvent.click(screen.getByRole("button", { name: "Save target" }));
    expect(backupRecoveryService.createStorageTarget).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Vault",
        adapter_key: "local-filesystem",
        locator_prefix_ref: "secret://vault",
        configuration_ref: "secret://config",
        encryption_key_ref: undefined,
      })
    );
  });

  it("edits pending job context and fails closed after execution begins", async () => {
    const update = vi
      .spyOn(backupRecoveryService, "updateBackupJob")
      .mockResolvedValue({ ...pendingJob, description: "Updated context" } as never);
    const getJob = vi
      .spyOn(backupRecoveryService, "getBackupJob")
      .mockResolvedValue(pendingJob as never);

    const editable = renderRoutedPage(
      <BackupJobEditPage />,
      "/backup-recovery/jobs/:id/edit",
      "/backup-recovery/jobs/job-1/edit"
    );
    expect(
      await screen.findByRole("heading", { name: "Edit pending request" })
    ).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Operator context"));
    await userEvent.type(screen.getByLabelText("Operator context"), "Updated context");
    await userEvent.click(screen.getByRole("button", { name: "Save description" }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("job-1", { description: "Updated context" })
    );
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/backup-recovery/jobs/job-1");
    editable.unmount();

    getJob.mockResolvedValue({
      ...pendingJob,
      status: "running",
      started_at: "2026-07-22T02:00:00Z",
    } as never);
    renderRoutedPage(
      <BackupJobEditPage />,
      "/backup-recovery/jobs/:id/edit",
      "/backup-recovery/jobs/job-1/edit"
    );
    expect(
      await screen.findByRole("heading", { name: "Job is no longer editable" })
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "This job has crossed the pending boundary."
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Correlation ID: corr-job");
  });

  it("updates schedule edit pages with bounded calendar payloads", async () => {
    vi.spyOn(backupRecoveryService, "getBackupSchedule").mockResolvedValue(schedule as never);
    vi.spyOn(backupRecoveryService, "listStorageTargets").mockResolvedValue({
      items: [target],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-targets",
    } as never);
    vi.spyOn(backupRecoveryService, "listRetentionPolicies").mockResolvedValue({
      items: [policy],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-policies",
    } as never);
    const update = vi
      .spyOn(backupRecoveryService, "updateBackupSchedule")
      .mockResolvedValue({ ...schedule, frequency: "monthly", day_of_month: 28 } as never);

    renderRoutedPage(
      <BackupScheduleEditPage />,
      "/backup-recovery/schedules/:id/edit",
      "/backup-recovery/schedules/schedule-1/edit"
    );

    expect(
      await screen.findByRole("heading", { name: "Edit backup schedule" })
    ).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Schedule name"));
    await userEvent.type(screen.getByLabelText("Schedule name"), "Monthly ledger");
    await userEvent.selectOptions(screen.getByLabelText("Frequency"), "monthly");
    await userEvent.clear(screen.getByLabelText("Day of week (0 Monday–6 Sunday)"));
    await userEvent.clear(screen.getByLabelText("Day of month (1–28)"));
    await userEvent.type(screen.getByLabelText("Day of month (1–28)"), "28");
    await userEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        "schedule-1",
        expect.objectContaining({
          name: "Monthly ledger",
          frequency: "monthly",
          day_of_week: null,
          day_of_month: 28,
          storage_target_id: "target-1",
          retention_policy_id: "policy-1",
        })
      )
    );
  });

  it("updates policy and target edit pages without leaking secret values into payloads", async () => {
    vi.spyOn(backupRecoveryService, "getRetentionPolicy").mockResolvedValue(policy as never);
    vi.spyOn(backupRecoveryService, "getStorageTarget").mockResolvedValue(target as never);
    const updatePolicy = vi
      .spyOn(backupRecoveryService, "updateRetentionPolicy")
      .mockResolvedValue({ ...policy, retention_days: 730 } as never);
    const updateTarget = vi
      .spyOn(backupRecoveryService, "updateStorageTarget")
      .mockResolvedValue({ ...target, adapter_key: "azure-blob" } as never);

    const policyPage = renderRoutedPage(
      <BackupRetentionPolicyEditPage />,
      "/backup-recovery/retention-policies/:id/edit",
      "/backup-recovery/retention-policies/policy-1/edit"
    );
    expect(
      await screen.findByRole("heading", { name: "Edit retention policy" })
    ).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Retention days"));
    await userEvent.type(screen.getByLabelText("Retention days"), "730");
    await userEvent.click(screen.getByRole("button", { name: "Save policy" }));
    await waitFor(() =>
      expect(updatePolicy).toHaveBeenCalledWith(
        "policy-1",
        expect.objectContaining({
          retention_days: 730,
          archive_after_days: 30,
          keep_last_successful: 3,
        })
      )
    );
    policyPage.unmount();

    renderRoutedPage(
      <BackupStorageTargetEditPage />,
      "/backup-recovery/storage-targets/:id/edit",
      "/backup-recovery/storage-targets/target-1/edit"
    );
    expect(await screen.findByRole("heading", { name: "Edit storage target" })).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Adapter key"));
    await userEvent.type(screen.getByLabelText("Adapter key"), "azure-blob");
    await userEvent.clear(screen.getByLabelText("Encryption key reference (optional)"));
    await userEvent.click(screen.getByRole("button", { name: "Save target" }));
    await waitFor(() =>
      expect(updateTarget).toHaveBeenCalledWith(
        "target-1",
        expect.objectContaining({
          adapter_key: "azure-blob",
          encryption_key_ref: undefined,
        })
      )
    );
    expect(updateTarget.mock.calls[0]?.[1]).not.toHaveProperty("credential_ref");
    expect(updateTarget.mock.calls[0]?.[1]).not.toHaveProperty("configuration");
  });
});
