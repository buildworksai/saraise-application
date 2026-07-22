import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BackupJobCreatePage } from "../pages/BackupJobCreatePage";
import { BackupJobListPage } from "../pages/BackupJobListPage";
import { formatBytes } from "../components/BackupRecoveryUI";
import { BackupRecoveryApiError, backupRecoveryService } from "../services/backup-recovery-service";

const pagination = {
  page: 1,
  page_size: 25,
  count: 0,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};
function renderPage(ui: ReactNode, route = "/backup-recovery/jobs") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("backup recovery governed page states", () => {
  afterEach(() => vi.restoreAllMocks());

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
    await userEvent.click(submit);
    expect(await screen.findByRole("button", { name: "Durably queueing…" })).toBeDisabled();
  });
});
