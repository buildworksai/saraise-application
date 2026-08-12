/* eslint-disable max-lines-per-function -- cohesive workflow coverage intentionally exercises a full governed row-action chain. */
/* eslint-disable @typescript-eslint/consistent-type-imports -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MigrationJob } from "../../contracts";
import { DataMigrationListPage } from "../DataMigrationListPage";
import { dataMigrationService } from "../../services/data-migration-service";

vi.mock("../../services/data-migration-service", async (load) => {
  const actual = await load<typeof import("../../services/data-migration-service")>();
  return {
    ...actual,
    dataMigrationService: {
      ...actual.dataMigrationService,
      jobs: {
        ...actual.dataMigrationService.jobs,
        list: vi.fn(),
        delete: vi.fn(),
        archive: vi.fn(),
        export: vi.fn(),
        import: vi.fn(),
      },
      runs: {
        ...actual.dataMigrationService.runs,
        dryRun: vi.fn(),
        start: vi.fn(),
      },
    },
  };
});

const pagination = {
  count: 2,
  page: 1,
  page_size: 25,
  total_pages: 2,
  has_next: true,
  has_previous: false,
};

function paged<T>(items: readonly T[], overrides = {}) {
  return {
    items,
    pagination: { ...pagination, ...overrides },
    correlationId: "corr-list",
  };
}

function migrationJob(overrides: Partial<MigrationJob> = {}): MigrationJob {
  return {
    id: "job-1",
    name: "Customer import",
    description: "Tenant customer import",
    source_type: "csv",
    source_artifact_id: "artifact-1",
    source_config: { delimiter: ",", encoding: "utf-8", header_row: 1, batch_size: 500 },
    target_adapter: "crm.customer",
    target_entity: "customer",
    write_mode: "create",
    lookup_fields: [],
    status: "ready",
    configuration_version: 3,
    readiness: { ready: true, blockers: [] },
    latest_run: {
      id: "run-latest",
      mode: "dry_run",
      status: "running",
      processed_records: 7,
      total_records: 10,
      succeeded_records: 7,
      failed_records: 0,
      warning_records: 0,
      created_at: "2026-07-22T00:00:00Z",
      completed_at: null,
    },
    allowed_actions: ["update", "delete", "archive", "dry_run", "run", "export"],
    created_at: "2026-07-22T00:00:00Z",
    updated_at: "2026-07-22T00:00:00Z",
    ...overrides,
  };
}

function renderPage(initialEntry = "/data-migration/jobs") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/data-migration/jobs" element={<DataMigrationListPage />} />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

describe("DataMigrationListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "idem-list") });
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("renders an accessible skeleton while the governed page is pending", () => {
    vi.mocked(dataMigrationService.jobs.list).mockImplementation(
      () => new Promise(() => undefined)
    );
    renderPage();
    expect(
      screen.getByRole("status", { name: "Loading migration definitions" })
    ).toBeInTheDocument();
  });

  it("serializes governed filters, pagination, and row navigation through the real query path", async () => {
    vi.mocked(dataMigrationService.jobs.list).mockResolvedValue(paged([migrationJob()]));
    const user = userEvent.setup();

    renderPage();
    await screen.findByRole("button", { name: "Open" });
    await user.type(screen.getByLabelText("Search migrations"), "customer");
    await user.selectOptions(screen.getByLabelText("Filter by status"), "ready");
    await user.selectOptions(screen.getByLabelText("Filter by source type"), "csv");
    await user.selectOptions(screen.getByLabelText("Sort migrations"), "name");
    await user.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() =>
      expect(dataMigrationService.jobs.list).toHaveBeenLastCalledWith(
        expect.objectContaining({
          page: 2,
          page_size: 25,
          search: "customer",
          status: "ready",
          source_type: "csv",
          ordering: "name",
        })
      )
    );

    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByTestId("location")).toHaveTextContent("/data-migration/jobs/job-1");
  });

  it("sends guarded dry-run, commit, archive, delete, and clone operations from row actions", async () => {
    vi.mocked(dataMigrationService.jobs.list).mockResolvedValue(paged([migrationJob()]));
    vi.mocked(dataMigrationService.runs.dryRun).mockResolvedValue({
      id: "run-dry",
      mode: "dry_run",
      status: "queued",
    } as Awaited<ReturnType<typeof dataMigrationService.runs.dryRun>>);
    vi.mocked(dataMigrationService.runs.start).mockResolvedValue({
      id: "run-commit",
      mode: "commit",
      status: "queued",
    } as Awaited<ReturnType<typeof dataMigrationService.runs.start>>);
    vi.mocked(dataMigrationService.jobs.archive).mockResolvedValue(migrationJob());
    vi.mocked(dataMigrationService.jobs.delete).mockResolvedValue(undefined);
    vi.mocked(dataMigrationService.jobs.export).mockResolvedValue({
      schema_version: "2.0",
      checksum: "sha256:definition",
      job: {
        name: "Customer import",
        description: "Tenant customer import",
        source_type: "csv",
        source_artifact_id: "artifact-1",
        source_config: { delimiter: ",", encoding: "utf-8", header_row: 1, batch_size: 500 },
        target_adapter: "crm.customer",
        target_entity: "customer",
        write_mode: "create",
        lookup_fields: [],
      },
      mappings: [],
      rules: [],
    });
    vi.mocked(dataMigrationService.jobs.import).mockResolvedValue({
      job: migrationJob({ id: "job-clone", name: "Customer import copy" }),
      diff: { from_version: null, to_version: null, entries: [], warnings: [] },
      checksum_valid: true,
    });
    const user = userEvent.setup();

    const dryRunRender = renderPage();
    await screen.findByText("Customer import");
    await user.click(screen.getByRole("button", { name: /Dry run/u }));
    await waitFor(() =>
      expect(dataMigrationService.runs.dryRun).toHaveBeenCalledWith("job-1", {
        idempotency_key: "idem-list",
      })
    );
    expect(await screen.findByTestId("location")).toHaveTextContent("/data-migration/runs/run-dry");
    dryRunRender.unmount();

    const commitRender = renderPage();
    await screen.findByText("Customer import");
    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() =>
      expect(dataMigrationService.runs.start).toHaveBeenCalledWith("job-1", {
        idempotency_key: "idem-list",
      })
    );
    commitRender.unmount();

    renderPage();
    await screen.findByText("Customer import");
    await user.click(screen.getByRole("button", { name: "Archive Customer import" }));
    await waitFor(() =>
      expect(dataMigrationService.jobs.archive).toHaveBeenCalledWith("job-1", "idem-list")
    );
    await user.click(screen.getByRole("button", { name: "Delete Customer import" }));
    await waitFor(() => expect(dataMigrationService.jobs.delete).toHaveBeenCalledWith("job-1"));

    await user.click(screen.getByRole("button", { name: /Clone/u }));
    await waitFor(() => expect(dataMigrationService.jobs.import).toHaveBeenCalled());
    const importPayload = vi.mocked(dataMigrationService.jobs.import).mock.calls[0]?.[0];
    expect(importPayload?.preview_only).toBe(false);
    expect(importPayload?.document.job.name).toBe("Customer import copy");
    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/data-migration/jobs/job-clone/edit"
    );
  });
});
