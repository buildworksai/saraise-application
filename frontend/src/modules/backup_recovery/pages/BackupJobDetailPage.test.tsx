/* eslint-disable max-lines-per-function -- detail-page command coverage keeps backup fixtures local. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type { BackupJob } from "../contracts";
import { BackupRecoveryApiError, backupRecoveryService } from "../services/backup-recovery-service";
import { BackupJobDetailPage } from "./BackupJobDetailPage";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

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

function renderJobDetail(ui: ReactElement, route = "/backup-recovery/jobs/job-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <LocationProbe />
        <Routes>
          <Route path="/backup-recovery/jobs/:id" element={ui} />
          <Route path="*" element={<span />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const allowed = { allowed: true };
const denied = { allowed: false, reason: "Server policy denied this transition." };

function jobFixture(overrides: Partial<BackupJob> = {}): BackupJob {
  return {
    id: "job-1",
    created_by: "user-1",
    updated_by: "user-1",
    created_at: "2026-07-22T01:55:00Z",
    updated_at: "2026-07-22T02:05:00Z",
    is_deleted: false,
    deleted_at: null,
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
    idempotency_key: "request-key",
    description: "Nightly tenant capture",
    requested_at: "2026-07-22T01:55:00Z",
    started_at: "2026-07-22T02:00:00Z",
    completed_at: "2026-07-22T02:05:00Z",
    data_cutoff_at: "2026-07-22T01:59:00Z",
    size_bytes: 2048,
    error_code: "",
    error_message: "",
    transition_history: [
      {
        command: "complete",
        from: "running",
        to: "completed",
        at: "2026-07-22T02:05:00Z",
        correlation_id: "corr-transition",
      },
    ],
    archive: {
      id: "archive-1",
      lifecycle: "available",
      checksum_algorithm: "sha256",
      checksum_digest: "abc123",
      integrity_status: "verified",
    },
    correlation_id: "corr-job",
    allowed_commands: {
      update: allowed,
      cancel: denied,
      retry: allowed,
      delete: allowed,
    },
    ...overrides,
  };
}

describe("BackupJobDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.getState().logout();
  });

  it("renders job evidence, command authorization, and routes linked records", async () => {
    useAuthStore.setState({ user: authUser, isAuthenticated: true, isLoading: false });
    vi.spyOn(backupRecoveryService, "getBackupJob").mockResolvedValue(
      jobFixture({ base_job: "job-base", retry_of: "job-original" })
    );
    const retryBackupJob = vi.spyOn(backupRecoveryService, "retryBackupJob").mockResolvedValue({
      job_id: "job-retry",
      async_job_id: "async-retry",
      status: "pending",
      idempotency_key: "retry-key",
    });

    renderJobDetail(<BackupJobDetailPage />);

    expect(await screen.findByRole("heading", { name: "Full backup" })).toBeInTheDocument();
    expect(screen.getByText("Immutable vault")).toBeInTheDocument();
    expect(screen.getByText("sha256:abc123")).toBeInTheDocument();
    expect(screen.getByText("corr-transition")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(retryBackupJob).toHaveBeenCalled());
    const retryCall = retryBackupJob.mock.calls.at(0);
    expect(retryCall?.[0]).toBe("job-1");
    expect(retryCall?.[1].idempotency_key).toMatch(/^retry:/u);
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/jobs/job-retry"
    );
  });

  it("routes update actions to the edit context page", async () => {
    useAuthStore.setState({ user: authUser, isAuthenticated: true, isLoading: false });
    vi.spyOn(backupRecoveryService, "getBackupJob").mockResolvedValue(jobFixture());

    renderJobDetail(<BackupJobDetailPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Edit context" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      "/backup-recovery/jobs/job-1/edit"
    );
  });

  it("requires confirmation before cancellation or removal and sends governed commands", async () => {
    useAuthStore.setState({ user: authUser, isAuthenticated: true, isLoading: false });
    vi.spyOn(backupRecoveryService, "getBackupJob").mockResolvedValue(
      jobFixture({
        status: "running",
        completed_at: null,
        archive: null,
        allowed_commands: { update: allowed, cancel: allowed, retry: denied, delete: allowed },
      })
    );
    const cancelBackupJob = vi.spyOn(backupRecoveryService, "cancelBackupJob").mockResolvedValue({
      ...jobFixture(),
      status: "cancelled",
    });
    const deleteBackupJob = vi
      .spyOn(backupRecoveryService, "deleteBackupJob")
      .mockResolvedValue(undefined);

    renderJobDetail(<BackupJobDetailPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("heading", { name: "Cancel backup operation?" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Keep job" }));
    expect(cancelBackupJob).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Request cancellation" }));
    await waitFor(() => expect(cancelBackupJob).toHaveBeenCalled());
    const cancelCall = cancelBackupJob.mock.calls.at(0);
    expect(cancelCall?.[0]).toBe("job-1");
    expect(cancelCall?.[1].transition_key).toMatch(/^cancel:/u);

    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(
      screen.getByRole("heading", { name: "Remove job from the active catalog?" })
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove safely" }));
    await waitFor(() => expect(deleteBackupJob).toHaveBeenCalledWith("job-1"));
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/backup-recovery/jobs");
  });

  it("shows provider failure details and fail-closed retry for unavailable records", async () => {
    useAuthStore.setState({ user: authUser, isAuthenticated: true, isLoading: false });
    const getBackupJob = vi
      .spyOn(backupRecoveryService, "getBackupJob")
      .mockRejectedValueOnce(
        new BackupRecoveryApiError("Backend unavailable", 503, "BACKUP_DOWN", "corr-down")
      )
      .mockResolvedValue(
        jobFixture({
          status: "failed",
          archive: null,
          error_code: "PROVIDER_TIMEOUT",
          error_message: "Provider did not acknowledge completion.",
          transition_history: [],
        })
      );

    renderJobDetail(<BackupJobDetailPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Backend unavailable");
    expect(screen.getByRole("button", { name: /Correlation ID: corr-down/u })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("PROVIDER_TIMEOUT")).toBeInTheDocument();
    expect(screen.getByText("Provider did not acknowledge completion.")).toBeInTheDocument();
    expect(screen.getByText(/No artifact evidence exists/u)).toBeInTheDocument();
    expect(getBackupJob).toHaveBeenCalledTimes(2);
  });
});
