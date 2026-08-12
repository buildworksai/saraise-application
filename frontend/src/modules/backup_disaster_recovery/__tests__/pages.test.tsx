/* eslint-disable max-lines-per-function -- cohesive page coverage keeps related fixtures and Vitest service-spy assertions local. */
import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  BackupExecutionReceipt,
  BDRConfigurationVersion,
  DRExercise,
  DRStepExecution,
  DRRunbook,
  DurableJobReceipt,
  ReadinessSummary,
  RecoveryPoint,
  RunbookStep,
  RestoreRun,
} from "../contracts";
import {
  BackupDisasterRecoveryError,
  backupDisasterRecoveryService,
} from "../services/backup_disaster_recovery-service";
import { BackupExecutionCreatePage } from "../pages/BackupExecutionCreatePage";
import { DisasterRecoveryDashboardPage } from "../pages/DisasterRecoveryDashboardPage";
import { BackupDisasterRecoveryConfigurationPage } from "../pages/BackupDisasterRecoveryConfigurationPage";
import { DRExerciseCreatePage } from "../pages/DRExerciseCreatePage";
import { DRExerciseDetailPage } from "../pages/DRExerciseDetailPage";
import { DRExerciseEditPage } from "../pages/DRExerciseEditPage";
import { DRExerciseListPage } from "../pages/DRExerciseListPage";
import { DRRunbookCreatePage } from "../pages/DRRunbookCreatePage";
import { DRRunbookDetailPage } from "../pages/DRRunbookDetailPage";
import { DRRunbookEditPage } from "../pages/DRRunbookEditPage";
import { DRRunbookListPage } from "../pages/DRRunbookListPage";
import { RecoveryPointDetailPage } from "../pages/RecoveryPointDetailPage";
import { RecoveryPointListPage } from "../pages/RecoveryPointListPage";
import { RestoreRunCreatePage } from "../pages/RestoreRunCreatePage";
import { RestoreRunDetailPage } from "../pages/RestoreRunDetailPage";
import { RestoreRunListPage } from "../pages/RestoreRunListPage";
import { configurationQueryKey } from "../hooks/useBackupDisasterRecoveryConfiguration";
import { configurationFixture } from "./configuration-fixture";

const readiness: ReadinessSummary = {
  calculated_at: "2026-07-21T00:00:00Z",
  rpo_compliance_percent: 98,
  rto_compliance_percent: 95,
  last_verified_recovery_point: null,
  latest_passed_exercise: null,
  latest_successful_restore: null,
  latest_failed_restore: null,
  next_scheduled_exercise: null,
  stale_runbook_count: 1,
  unpublished_runbook_count: 2,
  current_rpo_breaches: 0,
  current_rto_breaches: 1,
  queue_state: "operational",
  provider_state: "operational",
  provider_message: "Local encrypted storage is operational",
};

const recoveryPoint: RecoveryPoint = {
  id: "point-1",
  scope_type: "tenant",
  scope_ref: "finance-ledger",
  backup_type: "full",
  status: "available",
  data_cutoff_at: "2026-07-20T00:00:00Z",
  captured_at: "2026-07-20T00:01:00Z",
  verified_at: "2026-07-20T00:02:00Z",
  expires_at: null,
  size_bytes: 1536,
  verification_evidence: null,
  created_at: "2026-07-20T00:01:00Z",
  updated_at: "2026-07-20T00:02:00Z",
};

const restoreRun: RestoreRun = {
  id: "restore-1",
  recovery_point_id: "point-1",
  runbook_id: "runbook-1",
  exercise_id: null,
  target_environment: "isolated",
  target_ref: "tenant-restore",
  restore_mode: "selective",
  selected_components: ["ledger"],
  status: "succeeded",
  requested_at: "2026-07-20T00:05:00Z",
  started_at: "2026-07-20T00:06:00Z",
  completed_at: "2026-07-20T00:36:00Z",
  achieved_rpo_seconds: 1800,
  achieved_rto_seconds: null,
  created_at: "2026-07-20T00:05:00Z",
  updated_at: "2026-07-20T00:36:00Z",
};

const readyRestoreRun: RestoreRun = {
  ...restoreRun,
  status: "ready",
  completed_at: null,
  achieved_rpo_seconds: 45,
  achieved_rto_seconds: null,
};

const draftRunbook: DRRunbook = {
  id: "runbook-1",
  name: "Tenant failover",
  slug: "tenant-failover",
  version: 1,
  status: "draft",
  description: "Restore the tenant ledger in order.",
  scope_type: "tenant",
  scope_ref: "tenant-main",
  backup_schedule_id: null,
  rpo_target_seconds: 900,
  rto_target_seconds: 1800,
  supersedes_id: null,
  published_at: null,
  retired_at: null,
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
};

const scheduledExercise: DRExercise = {
  id: "exercise-1",
  name: "Quarterly restore drill",
  runbook_id: "runbook-1",
  recovery_point_id: "point-1",
  exercise_type: "restore",
  environment: "isolated",
  status: "scheduled",
  scheduled_for: "2026-07-21T00:00:00Z",
  started_at: null,
  completed_at: null,
  summary: "Operators validate the finance ledger restore path.",
  observed_rpo_seconds: null,
  observed_rto_seconds: null,
  rpo_met: null,
  rto_met: null,
  failed_step_id: null,
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
};

const validateStep: RunbookStep = {
  id: "step-validate",
  runbook_id: "runbook-1",
  step_key: "validate-artifact",
  position: 1,
  name: "Validate artifact",
  description: "Confirm the artifact before restoring.",
  action_type: "validate_recovery_point",
  extension_action_key: null,
  approval_permission: null,
  parameters: {
    action_type: "validate_recovery_point",
    require_checksum: true,
    require_encryption: true,
  },
  timeout_seconds: 300,
  retry_limit: 1,
  on_failure: "stop",
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
};

const restoreStep: RunbookStep = {
  ...validateStep,
  id: "step-restore",
  step_key: "restore-ledger",
  position: 2,
  name: "Restore ledger",
  description: "Restore the selected ledger components.",
  action_type: "restore",
  parameters: {
    action_type: "restore",
    restore_mode: "selective",
    selected_components: ["ledger"],
  },
};

const stepExecution: DRStepExecution = {
  id: "execution-1",
  exercise_id: "exercise-1",
  runbook_step_id: "step-validate",
  status: "running",
  attempt: 2,
  started_at: "2026-07-21T00:01:00Z",
  completed_at: null,
  created_at: "2026-07-21T00:01:00Z",
  updated_at: "2026-07-21T00:02:00Z",
};

const pagination = {
  page: 1,
  page_size: 25,
  count: 1,
  total_pages: 1,
  has_next: false,
  has_previous: false,
} as const;

const LocationProbe = () => {
  const location = useLocation();
  return <span data-testid="current-path">{location.pathname}</span>;
};

const createTestClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

const renderPage = (
  page: ReactElement,
  initialPath = "/backup-disaster-recovery",
  client = createTestClient()
) => {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="*" element={page} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

const renderRoutedPage = (
  page: ReactElement,
  routePath: string,
  initialPath: string,
  client = createTestClient()
) => {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path={routePath} element={page} />
          <Route path="*" element={<span />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

afterEach(() => vi.restoreAllMocks());

const mockConfiguration = () =>
  vi
    .spyOn(backupDisasterRecoveryService, "getConfiguration")
    .mockResolvedValue(configurationFixture);

const jobReceipt: DurableJobReceipt = {
  async_job_id: "async-job-1",
  status: "queued",
  accepted_at: "2026-07-21T00:00:00Z",
};

describe("DisasterRecoveryDashboardPage", () => {
  it("preserves layout with an accessible skeleton while loading", () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getReadiness").mockReturnValue(
      new Promise<ReadinessSummary>(() => undefined)
    );
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(screen.getByLabelText("Loading disaster recovery data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
  });

  it("renders an actionable domain empty state and compliance metrics", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getReadiness").mockResolvedValue(readiness);
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(
      await screen.findByRole("heading", { name: "Disaster recovery readiness" })
    ).toBeInTheDocument();
    expect(screen.getByText("Establish your recovery baseline")).toBeInTheDocument();
    expect(screen.getByText("98.0%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request your first backup" })).toBeInTheDocument();
    expect(document.title).toBe("Disaster recovery readiness | SARAISE");
  });

  it("announces queue or provider degradation without provider secrets", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getReadiness").mockResolvedValue({
      ...readiness,
      provider_state: "degraded",
      provider_message: "Storage probe timed out",
    });
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Some recovery operations are degraded"
    );
    expect(screen.getAllByText("Storage probe timed out")).toHaveLength(2);
  });

  it("shows a governed correlation ID and retry control", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getReadiness").mockRejectedValue(
      new BackupDisasterRecoveryError("Queue is unavailable", 503, "queue_unavailable", "corr-503")
    );
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-503");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("does not render actions when access is denied", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getReadiness").mockRejectedValue(
      new BackupDisasterRecoveryError("Access denied", 403, "permission_denied", "corr-403")
    );
    renderPage(<DisasterRecoveryDashboardPage />);
    expect(await screen.findByText("Permission required")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /backup/i })).not.toBeInTheDocument();
  });
});

describe("configuration-first UI", () => {
  it("keeps production restore unavailable without collecting step-up proof", () => {
    renderPage(<RestoreRunCreatePage />, "/backup-disaster-recovery/restores/new");
    expect(screen.getByRole("option", { name: "Production (unavailable)" })).toBeDisabled();
    expect(screen.queryByLabelText(/step-up/i)).not.toBeInTheDocument();
  });

  it("marks restore planning fields with browser-native constraints", () => {
    renderPage(<RestoreRunCreatePage />, "/backup-disaster-recovery/restores/new");

    expect(screen.getByLabelText("Recovery point ID")).toBeRequired();
    expect(screen.getByLabelText("Registered target reference")).toBeRequired();
  });

  it("marks runbook identity and objective fields with browser-native constraints", async () => {
    mockConfiguration();
    renderPage(<DRRunbookCreatePage />, "/backup-disaster-recovery/runbooks/new");

    expect(await screen.findByLabelText("Name")).toBeRequired();
    expect(screen.getByLabelText("Slug")).toBeRequired();
    expect(screen.getByLabelText("Slug")).toHaveAttribute("pattern", "[a-z0-9-]+");
    expect(screen.getByLabelText("Scope reference")).toBeRequired();
    expect(screen.getByLabelText("RPO target (seconds)")).toBeRequired();
    expect(screen.getByLabelText("RPO target (seconds)")).toHaveAttribute("min", "1");
    expect(screen.getByLabelText("RTO target (seconds)")).toBeRequired();
    expect(screen.getByLabelText("RTO target (seconds)")).toHaveAttribute("min", "1");
  });

  it("marks exercise schedule fields with browser-native constraints", async () => {
    mockConfiguration();
    renderPage(<DRExerciseCreatePage />, "/backup-disaster-recovery/exercises/new");

    expect(await screen.findByLabelText("Exercise name")).toBeRequired();
    expect(screen.getByLabelText("Scheduled for")).toBeRequired();
    expect(screen.getByLabelText("Published runbook ID")).toBeRequired();
  });

  it("creates runbook drafts with normalized payload boundaries", async () => {
    mockConfiguration();
    const create = vi
      .spyOn(backupDisasterRecoveryService, "createRunbook")
      .mockResolvedValue({ ...draftRunbook, id: "runbook-created" });

    renderPage(<DRRunbookCreatePage />, "/backup-disaster-recovery/runbooks/new");

    await userEvent.type(await screen.findByLabelText("Name"), "  Finance Restore  ");
    await userEvent.type(screen.getByLabelText("Slug"), "finance-restore");
    await userEvent.clear(screen.getByLabelText("Scope reference"));
    await userEvent.type(screen.getByLabelText("Scope reference"), " tenant-ledger ");
    await userEvent.clear(screen.getByLabelText("RPO target (seconds)"));
    await userEvent.type(screen.getByLabelText("RPO target (seconds)"), "900");
    await userEvent.clear(screen.getByLabelText("RTO target (seconds)"));
    await userEvent.type(screen.getByLabelText("RTO target (seconds)"), "1800");
    await userEvent.type(screen.getByLabelText("Backup schedule ID"), " schedule-1 ");
    await userEvent.click(screen.getByRole("button", { name: "Create draft" }));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Finance Restore",
          slug: "finance-restore",
          scope_ref: "tenant-ledger",
          backup_schedule_id: "schedule-1",
          rpo_target_seconds: 900,
          rto_target_seconds: 1800,
        })
      )
    );
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/runbooks/runbook-created/edit"
    );
  });

  it("rejects invalid runbook objective boundaries before mutation", async () => {
    mockConfiguration();
    const create = vi.spyOn(backupDisasterRecoveryService, "createRunbook");

    renderPage(<DRRunbookCreatePage />, "/backup-disaster-recovery/runbooks/new");

    await userEvent.type(await screen.findByLabelText("Name"), "Invalid objectives");
    await userEvent.type(screen.getByLabelText("Slug"), "invalid-objectives");
    const rpo = screen.getByLabelText("RPO target (seconds)");
    await userEvent.clear(rpo);
    await userEvent.type(rpo, "0");
    await userEvent.click(screen.getByRole("button", { name: "Create draft" }));

    expect(rpo).toBeInvalid();
    expect(create).not.toHaveBeenCalled();
  });

  it("edits scheduled exercises with immutable identity fields and bounded payload", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getExercise").mockResolvedValue(scheduledExercise);
    const update = vi
      .spyOn(backupDisasterRecoveryService, "updateExercise")
      .mockResolvedValue({ ...scheduledExercise, name: "Updated drill" });

    renderRoutedPage(
      <DRExerciseEditPage />,
      "/backup-disaster-recovery/exercises/:id/edit",
      "/backup-disaster-recovery/exercises/exercise-1/edit"
    );

    expect(
      await screen.findByRole("heading", { name: "Edit Quarterly restore drill" })
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Published runbook ID")).toBeDisabled();
    expect(screen.getByLabelText("Exercise type")).toBeDisabled();
    expect(screen.getByLabelText("Safe environment")).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Exercise name"));
    await userEvent.type(screen.getByLabelText("Exercise name"), "Updated drill");
    await userEvent.clear(screen.getByLabelText("Recovery point ID"));
    await userEvent.type(screen.getByLabelText("Recovery point ID"), " point-2 ");
    await userEvent.click(screen.getByRole("button", { name: "Save schedule" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        "exercise-1",
        expect.objectContaining({
          name: "Updated drill",
          recovery_point_id: "point-2",
        })
      )
    );
    expect(update.mock.calls[0]?.[1]).not.toHaveProperty("runbook_id");
    expect(update.mock.calls[0]?.[1]).not.toHaveProperty("environment");
  });

  it("fails closed when editing an exercise that has execution evidence", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getExercise").mockResolvedValue({
      ...scheduledExercise,
      status: "running",
      started_at: "2026-07-21T00:01:00Z",
    });
    const update = vi.spyOn(backupDisasterRecoveryService, "updateExercise");

    renderRoutedPage(
      <DRExerciseEditPage />,
      "/backup-disaster-recovery/exercises/:id/edit",
      "/backup-disaster-recovery/exercises/exercise-1/edit"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only scheduled exercises can be edited. Execution evidence is immutable."
    );
    expect(update).not.toHaveBeenCalled();
  });

  it("requires a server preview before applying configuration", async () => {
    vi.spyOn(backupDisasterRecoveryService, "getConfiguration").mockResolvedValue(
      configurationFixture
    );
    vi.spyOn(backupDisasterRecoveryService, "listConfigurationVersions").mockResolvedValue([]);
    const preview = vi
      .spyOn(backupDisasterRecoveryService, "previewConfiguration")
      .mockResolvedValue({ valid: true, changes: [], document: configurationFixture.document });
    renderPage(
      <BackupDisasterRecoveryConfigurationPage />,
      "/backup-disaster-recovery/configuration"
    );
    expect(
      await screen.findByRole("heading", { name: "Disaster recovery configuration" })
    ).toBeInTheDocument();
    const apply = screen.getByRole("button", { name: "Apply configuration" });
    expect(apply).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Preview changes" }));
    await waitFor(() => expect(preview).toHaveBeenCalledTimes(1));
    expect(apply).toBeEnabled();
  });

  it("rejects malformed configuration locally and never calls the server preview", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "listConfigurationVersions").mockResolvedValue([]);
    const preview = vi.spyOn(backupDisasterRecoveryService, "previewConfiguration");

    renderPage(
      <BackupDisasterRecoveryConfigurationPage />,
      "/backup-disaster-recovery/configuration"
    );

    fireEvent.change(await screen.findByLabelText("Policy document"), { target: { value: "{" } });
    await userEvent.click(screen.getByRole("button", { name: "Preview changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Configuration must be valid JSON.");
    expect(preview).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Apply configuration" })).toBeDisabled();
  });

  it("exports immutable configuration and rolls back older versions by API", async () => {
    const version: BDRConfigurationVersion = {
      id: "version-1",
      version: 0,
      actor_id: "operator-1",
      correlation_id: "corr-version",
      prior_value: null,
      new_value: {
        document: configurationFixture.document,
        environment: "previous",
        rollout: { enabled: false, roles: [], cohorts: [] },
      },
      rollback_of: null,
      created_at: "2026-07-22T00:00:00Z",
    };
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "listConfigurationVersions").mockResolvedValue([
      version,
    ]);
    const rollback = vi
      .spyOn(backupDisasterRecoveryService, "rollbackConfiguration")
      .mockResolvedValue(configurationFixture);
    const exportConfiguration = vi
      .spyOn(backupDisasterRecoveryService, "exportConfiguration")
      .mockResolvedValue({
        schema: "saraise.backup-disaster-recovery.configuration/v1",
        version: configurationFixture.version,
        document: configurationFixture.document,
        environment: configurationFixture.environment,
        rollout: configurationFixture.rollout,
      });
    const createObjectUrl = vi.fn(() => "blob:backup-disaster-recovery");
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectUrl,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectUrl,
    });
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);

    renderPage(
      <BackupDisasterRecoveryConfigurationPage />,
      "/backup-disaster-recovery/configuration"
    );

    expect(await screen.findByRole("cell", { name: "corr-version" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(exportConfiguration).toHaveBeenCalledTimes(1));
    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:backup-disaster-recovery");

    await userEvent.click(screen.getByRole("button", { name: "Rollback" }));
    await waitFor(() => expect(rollback).toHaveBeenCalledWith({ version: 0 }));
  });

  it("applies previewed configuration changes and stages imports before import mutation", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "listConfigurationVersions").mockResolvedValue([]);
    const preview = vi
      .spyOn(backupDisasterRecoveryService, "previewConfiguration")
      .mockResolvedValue({
        valid: true,
        changes: [{ path: "environment", before: "test", after: "dr-drill" }],
        document: configurationFixture.document,
      });
    const update = vi
      .spyOn(backupDisasterRecoveryService, "updateConfiguration")
      .mockResolvedValue({ ...configurationFixture, environment: "dr-drill" });
    renderPage(
      <BackupDisasterRecoveryConfigurationPage />,
      "/backup-disaster-recovery/configuration"
    );

    fireEvent.change(await screen.findByLabelText("Environment"), {
      target: { value: "dr-drill" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Preview changes" }));
    expect(await screen.findByText("environment")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Apply configuration" }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        expect.objectContaining({
          environment: "dr-drill",
          document: configurationFixture.document,
        })
      )
    );
    expect(preview).toHaveBeenCalledTimes(1);
  });
});

describe("DRRunbookListPage", () => {
  it("renders runbook rows with configured objectives and explicit filters", async () => {
    mockConfiguration();
    const list = vi
      .spyOn(backupDisasterRecoveryService, "listRunbooks")
      .mockResolvedValue({ items: [draftRunbook], pagination, correlationId: "corr-runbooks" });

    renderPage(<DRRunbookListPage />, "/backup-disaster-recovery/runbooks");

    expect(await screen.findByRole("heading", { name: "DR runbooks" })).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith({
      status: undefined,
      search: undefined,
      ordering: "-updated_at",
    });
    expect(screen.getByRole("button", { name: "Tenant failover" })).toBeInTheDocument();
    expect(screen.getByText("tenant-failover · v1")).toBeInTheDocument();
    expect(screen.getByText("15m")).toBeInTheDocument();
    expect(screen.getByText("30m")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search name or slug…"), {
      target: { value: "tenant" },
    });
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith({
        status: undefined,
        search: "tenant",
        ordering: "-updated_at",
      })
    );
    await userEvent.selectOptions(await screen.findByRole("combobox"), "published");
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith({
        status: "published",
        search: "tenant",
        ordering: "-updated_at",
      })
    );
  });

  it("retries fail-closed list and configuration errors and routes actions", async () => {
    mockConfiguration();
    const list = vi
      .spyOn(backupDisasterRecoveryService, "listRunbooks")
      .mockRejectedValueOnce(
        new BackupDisasterRecoveryError(
          "Runbook catalog unavailable",
          503,
          "catalog_down",
          "corr-runbooks"
        )
      )
      .mockResolvedValue({ items: [], pagination, correlationId: "corr-empty" });

    const first = renderPage(<DRRunbookListPage />, "/backup-disaster-recovery/runbooks");
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-runbooks");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    const createActions = await screen.findAllByRole("button", { name: "Create runbook" });
    const createAction = createActions[0];
    expect(createAction).toBeDefined();
    await userEvent.click(createAction!);
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/runbooks/new"
    );
    first.unmount();

    vi.restoreAllMocks();
    const configuration = vi
      .spyOn(backupDisasterRecoveryService, "getConfiguration")
      .mockRejectedValueOnce(
        new BackupDisasterRecoveryError(
          "Configuration unavailable",
          503,
          "config_down",
          "corr-config"
        )
      )
      .mockResolvedValue(configurationFixture);
    vi.spyOn(backupDisasterRecoveryService, "listRunbooks").mockResolvedValue({
      items: [draftRunbook],
      pagination,
      correlationId: "corr",
    });
    renderPage(<DRRunbookListPage />, "/backup-disaster-recovery/runbooks");
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-config");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(configuration).toHaveBeenCalledTimes(2));
    await userEvent.click(await screen.findByRole("button", { name: "Tenant failover" }));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/runbooks/runbook-1"
    );
  });
});

describe("DRExerciseListPage", () => {
  it("renders exercise rows and sends explicit status filters", async () => {
    mockConfiguration();
    const list = vi.spyOn(backupDisasterRecoveryService, "listExercises").mockResolvedValue({
      items: [scheduledExercise],
      pagination,
      correlationId: "corr-exercises",
    });

    renderPage(<DRExerciseListPage />, "/backup-disaster-recovery/exercises");

    expect(await screen.findByRole("heading", { name: "DR exercises" })).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith({ status: undefined });
    expect(screen.getByRole("button", { name: "Quarterly restore drill" })).toBeInTheDocument();
    expect(screen.getByText("restore")).toBeInTheDocument();
    expect(screen.getByText("isolated")).toBeInTheDocument();
    expect(screen.getByText("Not measured")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Filter by exercise status"), "failed");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ status: "failed" }));
  });

  it("fails closed on exercise index errors and routes empty state commands", async () => {
    mockConfiguration();
    const list = vi
      .spyOn(backupDisasterRecoveryService, "listExercises")
      .mockRejectedValueOnce(
        new BackupDisasterRecoveryError(
          "Exercise index unavailable",
          503,
          "exercise_down",
          "corr-exercises"
        )
      )
      .mockResolvedValue({ items: [], pagination, correlationId: "corr-empty" });

    renderPage(<DRExerciseListPage />, "/backup-disaster-recovery/exercises");

    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-exercises");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("No exercises match")).toBeInTheDocument();
    const scheduleActions = screen.getAllByRole("button", { name: "Schedule exercise" });
    const scheduleAction = scheduleActions.at(-1);
    expect(scheduleAction).toBeDefined();
    await userEvent.click(scheduleAction!);
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/exercises/new"
    );
  });
});

describe("DRExerciseDetailPage", () => {
  it("opens an exercise by UUID when no route parameter is present", async () => {
    renderPage(<DRExerciseDetailPage />, "/backup-disaster-recovery/exercises/open");

    await userEvent.type(screen.getByLabelText("Exercise UUID"), "exercise-1");
    await userEvent.click(screen.getByRole("button", { name: "Open" }));

    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/exercises/exercise-1"
    );
  });

  it("renders scheduled exercise controls and sends governed transition keys", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getExercise").mockResolvedValue(scheduledExercise);
    vi.spyOn(backupDisasterRecoveryService, "listStepExecutions").mockResolvedValue({
      items: [stepExecution],
      pagination,
      correlationId: "corr-executions",
    });
    const start = vi
      .spyOn(backupDisasterRecoveryService, "startExercise")
      .mockResolvedValue(jobReceipt);
    const cancel = vi
      .spyOn(backupDisasterRecoveryService, "cancelExercise")
      .mockResolvedValue({ ...scheduledExercise, status: "cancelled" });

    renderRoutedPage(
      <DRExerciseDetailPage />,
      "/backup-disaster-recovery/exercises/:id",
      "/backup-disaster-recovery/exercises/exercise-1"
    );

    expect(
      await screen.findByRole("heading", { name: "Quarterly restore drill" })
    ).toBeInTheDocument();
    expect(screen.getByText("Step step-val · attempt 2")).toBeInTheDocument();
    expect(screen.getByText("Exercise summary")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Start exercise" }));
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(start.mock.calls[0]?.[0]).toBe("exercise-1");
    expect(start.mock.calls[0]?.[1].idempotency_key).toMatch(/^exercise-start-/);

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledTimes(1));
    expect(cancel.mock.calls[0]?.[0]).toBe("exercise-1");
    expect(cancel.mock.calls[0]?.[1].transition_key).toMatch(/^exercise-cancel-/);

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/exercises/exercise-1/edit"
    );
  });

  it("surfaces exercise step timeline failures with correlation evidence", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getExercise").mockResolvedValue(scheduledExercise);
    vi.spyOn(backupDisasterRecoveryService, "listStepExecutions").mockRejectedValue(
      new BackupDisasterRecoveryError(
        "Step evidence unavailable",
        503,
        "step_evidence_unavailable",
        "corr-steps"
      )
    );

    renderRoutedPage(
      <DRExerciseDetailPage />,
      "/backup-disaster-recovery/exercises/:id",
      "/backup-disaster-recovery/exercises/exercise-1"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-steps");
  });
});

describe("DRRunbookDetailPage", () => {
  it("prevents publishing empty drafts and deletes only after confirmation", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getRunbook").mockResolvedValue(draftRunbook);
    vi.spyOn(backupDisasterRecoveryService, "listRunbookSteps").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-steps",
    });
    const remove = vi
      .spyOn(backupDisasterRecoveryService, "deleteRunbook")
      .mockResolvedValue(undefined);

    renderRoutedPage(
      <DRRunbookDetailPage />,
      "/backup-disaster-recovery/runbooks/:id",
      "/backup-disaster-recovery/runbooks/runbook-1"
    );

    expect(
      await screen.findByRole("heading", { name: "Tenant failover · v1" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();
    expect(
      screen.getByText(
        "This draft has no active steps. Add at least one validated step before publishing."
      )
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete draft" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Soft-delete this draft");
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

    await waitFor(() => expect(remove).toHaveBeenCalledWith("runbook-1"));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/runbooks"
    );
  });

  it("publishes drafts with steps and clones published runbooks into edit mode", async () => {
    mockConfiguration();
    const publishedRunbook = {
      ...draftRunbook,
      status: "published" as const,
      published_at: "2026-07-21T00:00:00Z",
    };
    const getRunbook = vi
      .spyOn(backupDisasterRecoveryService, "getRunbook")
      .mockResolvedValueOnce(draftRunbook)
      .mockResolvedValue(publishedRunbook);
    vi.spyOn(backupDisasterRecoveryService, "listRunbookSteps").mockResolvedValue({
      items: [validateStep],
      pagination,
      correlationId: "corr-steps",
    });
    const publish = vi
      .spyOn(backupDisasterRecoveryService, "publishRunbook")
      .mockResolvedValue(publishedRunbook);

    const { unmount } = renderRoutedPage(
      <DRRunbookDetailPage />,
      "/backup-disaster-recovery/runbooks/:id",
      "/backup-disaster-recovery/runbooks/runbook-1"
    );

    expect(await screen.findByRole("button", { name: "Publish" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    await waitFor(() => expect(publish).toHaveBeenCalledTimes(1));
    expect(publish.mock.calls[0]?.[0]).toBe("runbook-1");
    expect(publish.mock.calls[0]?.[1].transition_key).toMatch(/^publish-/);
    unmount();

    vi.restoreAllMocks();
    mockConfiguration();
    getRunbook.mockRestore();
    vi.spyOn(backupDisasterRecoveryService, "getRunbook").mockResolvedValue(publishedRunbook);
    vi.spyOn(backupDisasterRecoveryService, "listRunbookSteps").mockResolvedValue({
      items: [validateStep],
      pagination,
      correlationId: "corr-steps",
    });
    const clone = vi.spyOn(backupDisasterRecoveryService, "cloneRunbook").mockResolvedValue({
      ...draftRunbook,
      id: "runbook-draft-copy",
    });
    const retire = vi.spyOn(backupDisasterRecoveryService, "retireRunbook").mockResolvedValue({
      ...publishedRunbook,
      status: "retired",
      retired_at: "2026-07-22T00:00:00Z",
    });

    renderRoutedPage(
      <DRRunbookDetailPage />,
      "/backup-disaster-recovery/runbooks/:id",
      "/backup-disaster-recovery/runbooks/runbook-1"
    );

    expect(await screen.findByRole("button", { name: "Clone draft" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retire" }));
    await waitFor(() => expect(retire).toHaveBeenCalledTimes(1));
    expect(retire.mock.calls[0]?.[0]).toBe("runbook-1");
    expect(retire.mock.calls[0]?.[1].transition_key).toMatch(/^retire-/);
    await userEvent.click(screen.getByRole("button", { name: "Clone draft" }));
    await waitFor(() => expect(clone).toHaveBeenCalledWith("runbook-1"));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/runbooks/runbook-draft-copy/edit"
    );
  });
});

describe("RecoveryPointDetailPage", () => {
  it("verifies, expires, and starts restores from governed recovery point evidence", async () => {
    mockConfiguration();
    const expiredAvailablePoint: RecoveryPoint = {
      ...recoveryPoint,
      expires_at: "2000-01-01T00:00:00Z",
      verification_evidence: {
        kind: "artifact_validation",
        checksum_valid: true,
        artifact_available: true,
        encryption_metadata_valid: false,
        provider_acknowledged: true,
        checked_at: "2026-07-20T00:02:00Z",
      },
    };
    vi.spyOn(backupDisasterRecoveryService, "getRecoveryPoint").mockResolvedValue(
      expiredAvailablePoint
    );
    const verify = vi
      .spyOn(backupDisasterRecoveryService, "verifyRecoveryPoint")
      .mockResolvedValue(jobReceipt);
    const expire = vi
      .spyOn(backupDisasterRecoveryService, "expireRecoveryPoint")
      .mockResolvedValue({ ...expiredAvailablePoint, status: "expired" });

    renderRoutedPage(
      <RecoveryPointDetailPage />,
      "/backup-disaster-recovery/recovery-points/:id",
      "/backup-disaster-recovery/recovery-points/point-1"
    );

    expect(await screen.findByRole("heading", { name: "finance-ledger" })).toBeInTheDocument();
    expect(screen.getByText("Encryption metadata")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(verify).toHaveBeenCalledTimes(1));
    expect(verify.mock.calls[0]?.[0]).toBe("point-1");
    expect(verify.mock.calls[0]?.[1].idempotency_key).toMatch(/^verify-/);

    await userEvent.click(screen.getByRole("button", { name: "Mark expired" }));
    await waitFor(() => expect(expire).toHaveBeenCalledTimes(1));
    expect(expire.mock.calls[0]?.[0]).toBe("point-1");
    expect(expire.mock.calls[0]?.[1].transition_key).toMatch(/^expire-/);

    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/restores/new"
    );
  });

  it("reports recovery point load failures without exposing provider internals", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getRecoveryPoint").mockRejectedValue(
      new BackupDisasterRecoveryError(
        "Recovery point unavailable",
        503,
        "provider_timeout",
        "corr-point"
      )
    );

    renderRoutedPage(
      <RecoveryPointDetailPage />,
      "/backup-disaster-recovery/recovery-points/:id",
      "/backup-disaster-recovery/recovery-points/point-1"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-point");
  });
});

describe("RestoreRunDetailPage", () => {
  it("executes and cancels ready restores with idempotent transition payloads", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getRestoreRun").mockResolvedValue(readyRestoreRun);
    const execute = vi
      .spyOn(backupDisasterRecoveryService, "executeRestoreRun")
      .mockResolvedValue(jobReceipt);
    const cancel = vi
      .spyOn(backupDisasterRecoveryService, "cancelRestoreRun")
      .mockResolvedValue({ ...readyRestoreRun, status: "cancelled" });

    renderRoutedPage(
      <RestoreRunDetailPage />,
      "/backup-disaster-recovery/restores/:id",
      "/backup-disaster-recovery/restores/restore-1"
    );

    expect(
      await screen.findByRole("heading", { name: "Restore to tenant-restore" })
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Background operation in progress.");

    await userEvent.click(screen.getByRole("button", { name: "Execute restore" }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    expect(execute.mock.calls[0]?.[0]).toBe("restore-1");
    expect(execute.mock.calls[0]?.[1].idempotency_key).toMatch(/^restore-execute-/);

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledTimes(1));
    expect(cancel.mock.calls[0]?.[0]).toBe("restore-1");
    expect(cancel.mock.calls[0]?.[1].transition_key).toMatch(/^restore-cancel-/);
  });

  it("renders failed restore evidence guidance without lifecycle actions", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getRestoreRun").mockResolvedValue({
      ...restoreRun,
      status: "failed",
      achieved_rto_seconds: 2700,
    });

    renderRoutedPage(
      <RestoreRunDetailPage />,
      "/backup-disaster-recovery/restores/:id",
      "/backup-disaster-recovery/restores/restore-1"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Restore failed");
    expect(screen.getByText("45m")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Execute restore" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });
});

describe("DRRunbookEditPage", () => {
  it("requires a runbook UUID before editing a draft", async () => {
    renderPage(<DRRunbookEditPage />, "/backup-disaster-recovery/runbooks/edit");

    expect(await screen.findByRole("heading", { name: "Edit DR runbook" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Runbook UUID"), "runbook-1");
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/runbooks/runbook-1/edit"
    );
  });

  it("validates and creates configured draft runbook steps", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getRunbook").mockResolvedValue(draftRunbook);
    vi.spyOn(backupDisasterRecoveryService, "listRunbookSteps").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-steps",
    });
    const createStep = vi
      .spyOn(backupDisasterRecoveryService, "createRunbookStep")
      .mockResolvedValue(validateStep);
    vi.spyOn(backupDisasterRecoveryService, "updateRunbook").mockResolvedValue(draftRunbook);

    renderRoutedPage(
      <DRRunbookEditPage />,
      "/backup-disaster-recovery/runbooks/:id/edit",
      "/backup-disaster-recovery/runbooks/runbook-1/edit"
    );

    expect(
      await screen.findByRole("heading", { name: "Edit Tenant failover" })
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add step" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Step name and stable key are required.");

    await userEvent.type(screen.getByLabelText("Step name"), "  Validate evidence  ");
    await userEvent.type(screen.getByLabelText("Stable step key"), " Validate Evidence ");
    await userEvent.type(screen.getByLabelText("Operator instructions"), "Checksum first");
    await userEvent.click(screen.getByRole("button", { name: "Add step" }));

    await waitFor(() =>
      expect(createStep).toHaveBeenCalledWith(
        expect.objectContaining({
          runbook_id: "runbook-1",
          step_key: "validate evidence",
          position: 1,
          name: "Validate evidence",
          description: "Checksum first",
          action_type: "validate_recovery_point",
          parameters: {
            action_type: "validate_recovery_point",
            require_checksum: true,
            require_encryption: true,
          },
          timeout_seconds: configurationFixture.document.steps.default_timeout_seconds,
          retry_limit: configurationFixture.document.steps.default_retry_limit,
          on_failure: configurationFixture.document.steps.default_on_failure,
        })
      )
    );
  });

  it("reorders and confirms deletion of existing draft steps", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getRunbook").mockResolvedValue(draftRunbook);
    vi.spyOn(backupDisasterRecoveryService, "listRunbookSteps").mockResolvedValue({
      items: [restoreStep, validateStep],
      pagination: { ...pagination, count: 2 },
      correlationId: "corr-steps",
    });
    vi.spyOn(backupDisasterRecoveryService, "updateRunbook").mockResolvedValue(draftRunbook);
    const reorder = vi
      .spyOn(backupDisasterRecoveryService, "reorderRunbookSteps")
      .mockResolvedValue({ items: [validateStep, restoreStep] } as never);
    const remove = vi
      .spyOn(backupDisasterRecoveryService, "deleteRunbookStep")
      .mockResolvedValue(undefined);

    renderRoutedPage(
      <DRRunbookEditPage />,
      "/backup-disaster-recovery/runbooks/:id/edit",
      "/backup-disaster-recovery/runbooks/runbook-1/edit"
    );

    expect(await screen.findByText("Restore ledger")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Move Restore ledger up" }));
    await waitFor(() =>
      expect(reorder).toHaveBeenCalledWith("runbook-1", {
        step_ids: ["step-restore", "step-validate"],
      })
    );

    await userEvent.click(screen.getByRole("button", { name: "Delete Restore ledger" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Remove Restore ledger from this draft?");
    await userEvent.click(screen.getByRole("button", { name: "Remove step" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("step-restore"));
  });

  it("fails closed when a runbook is no longer draft", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getRunbook").mockResolvedValue({
      ...draftRunbook,
      status: "published",
      published_at: "2026-07-20T01:00:00Z",
    });
    vi.spyOn(backupDisasterRecoveryService, "listRunbookSteps").mockResolvedValue({
      items: [validateStep],
      pagination,
      correlationId: "corr-steps",
    });

    renderRoutedPage(
      <DRRunbookEditPage />,
      "/backup-disaster-recovery/runbooks/:id/edit",
      "/backup-disaster-recovery/runbooks/runbook-1/edit"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Published and retired runbooks are immutable"
    );
  });

  it("saves draft definition changes with normalized values", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getRunbook").mockResolvedValue(draftRunbook);
    vi.spyOn(backupDisasterRecoveryService, "listRunbookSteps").mockResolvedValue({
      items: [validateStep],
      pagination,
      correlationId: "corr-steps",
    });
    const updateRunbook = vi
      .spyOn(backupDisasterRecoveryService, "updateRunbook")
      .mockResolvedValue({ ...draftRunbook, name: "Tenant failover updated" });

    renderRoutedPage(
      <DRRunbookEditPage />,
      "/backup-disaster-recovery/runbooks/:id/edit",
      "/backup-disaster-recovery/runbooks/runbook-1/edit"
    );

    expect(
      await screen.findByRole("heading", { name: "Edit Tenant failover" })
    ).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Name"));
    await userEvent.type(screen.getByLabelText("Name"), " Tenant failover updated ");
    await userEvent.clear(screen.getByLabelText("Slug"));
    await userEvent.type(screen.getByLabelText("Slug"), "tenant-failover-updated");
    await userEvent.clear(screen.getByLabelText("Backup schedule ID"));
    await userEvent.clear(screen.getByLabelText("RPO target (seconds)"));
    await userEvent.type(screen.getByLabelText("RPO target (seconds)"), "1200");
    await userEvent.clear(screen.getByLabelText("RTO target (seconds)"));
    await userEvent.type(screen.getByLabelText("RTO target (seconds)"), "2400");
    await userEvent.click(screen.getByRole("button", { name: "Save definition" }));

    await waitFor(() =>
      expect(updateRunbook).toHaveBeenCalledWith("runbook-1", {
        name: "Tenant failover updated",
        slug: "tenant-failover-updated",
        description: draftRunbook.description,
        scope_type: "tenant",
        scope_ref: "tenant-main",
        backup_schedule_id: undefined,
        rpo_target_seconds: 1200,
        rto_target_seconds: 2400,
      })
    );
  });

  it("builds the remaining action-specific step payloads from governed controls", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "getRunbook").mockResolvedValue(draftRunbook);
    vi.spyOn(backupDisasterRecoveryService, "listRunbookSteps").mockResolvedValue({
      items: [],
      pagination,
      correlationId: "corr-steps",
    });
    const createStep = vi
      .spyOn(backupDisasterRecoveryService, "createRunbookStep")
      .mockResolvedValue(validateStep);
    vi.spyOn(backupDisasterRecoveryService, "updateRunbook").mockResolvedValue(draftRunbook);

    renderRoutedPage(
      <DRRunbookEditPage />,
      "/backup-disaster-recovery/runbooks/:id/edit",
      "/backup-disaster-recovery/runbooks/runbook-1/edit"
    );

    expect(
      await screen.findByRole("heading", { name: "Edit Tenant failover" })
    ).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Action type"), "restore");
    await userEvent.type(screen.getByLabelText("Step name"), "Restore core systems");
    await userEvent.type(screen.getByLabelText("Stable step key"), "restore-core");
    await userEvent.click(screen.getByRole("button", { name: "Add step" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "This action requires its target, permission, recipient, or extension key."
    );
    await userEvent.type(screen.getByLabelText("Registered restore target"), "warm-standby");
    await userEvent.type(screen.getByLabelText("Selective components"), "ledger, billing");
    await userEvent.click(screen.getByRole("button", { name: "Add step" }));

    await waitFor(() =>
      expect(createStep).toHaveBeenLastCalledWith(
        expect.objectContaining({
          action_type: "restore",
          parameters: {
            action_type: "restore",
            restore_mode: "selective",
            selected_components: ["ledger", "billing"],
          },
        })
      )
    );

    await userEvent.selectOptions(screen.getByLabelText("Action type"), "manual_approval");
    await userEvent.type(screen.getByLabelText("Step name"), "Approve cutover");
    await userEvent.type(screen.getByLabelText("Stable step key"), "approve-cutover");
    await userEvent.type(screen.getByLabelText("Approval permission"), "bdr.approve");
    await userEvent.type(
      screen.getByLabelText("Approval instructions"),
      "Confirm business owner signoff"
    );
    await userEvent.click(screen.getByRole("button", { name: "Add step" }));
    await waitFor(() =>
      expect(createStep).toHaveBeenLastCalledWith(
        expect.objectContaining({
          action_type: "manual_approval",
          approval_permission: "bdr.approve",
          parameters: {
            action_type: "manual_approval",
            instructions: "Confirm business owner signoff",
          },
        })
      )
    );

    await userEvent.selectOptions(screen.getByLabelText("Action type"), "notify");
    await userEvent.type(screen.getByLabelText("Step name"), "Notify stakeholders");
    await userEvent.type(screen.getByLabelText("Stable step key"), "notify-stakeholders");
    await userEvent.type(screen.getByLabelText("Recipient group"), "incident-command");
    await userEvent.type(screen.getByLabelText("Message template"), "restore-complete");
    await userEvent.click(screen.getByRole("button", { name: "Add step" }));
    await waitFor(() =>
      expect(createStep).toHaveBeenLastCalledWith(
        expect.objectContaining({
          action_type: "notify",
          parameters: {
            action_type: "notify",
            channel_ref: "incident-command",
            message_template: "restore-complete",
          },
        })
      )
    );

    await userEvent.selectOptions(screen.getByLabelText("Action type"), "extension");
    await userEvent.type(screen.getByLabelText("Step name"), "Run extension");
    await userEvent.type(screen.getByLabelText("Stable step key"), "run-extension");
    await userEvent.type(
      screen.getByLabelText("Registered extension action"),
      "bdr.extension.verify"
    );
    await userEvent.type(screen.getByLabelText("Configuration reference"), "extension-config-1");
    await userEvent.click(screen.getByRole("button", { name: "Add step" }));
    await waitFor(() =>
      expect(createStep).toHaveBeenLastCalledWith(
        expect.objectContaining({
          action_type: "extension",
          extension_action_key: "bdr.extension.verify",
          parameters: { action_type: "extension", configuration_ref: "extension-config-1" },
        })
      )
    );
  });
});

// eslint-disable-next-line max-lines-per-function -- mutation branch matrix is intentionally local to this page suite.
describe("RecoveryPointListPage", () => {
  it("keeps the recovery point skeleton active while either dependency is loading", () => {
    const client = createTestClient();
    client.setQueryData(configurationQueryKey, configurationFixture);
    vi.spyOn(backupDisasterRecoveryService, "listRecoveryPoints").mockReturnValue(
      new Promise(() => undefined)
    );
    const { unmount } = renderPage(
      <RecoveryPointListPage />,
      "/backup-disaster-recovery/recovery-points",
      client
    );
    expect(screen.getByLabelText("Loading disaster recovery data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    unmount();

    vi.restoreAllMocks();
    vi.spyOn(backupDisasterRecoveryService, "getConfiguration").mockReturnValue(
      new Promise(() => undefined)
    );
    vi.spyOn(backupDisasterRecoveryService, "listRecoveryPoints").mockResolvedValue({
      items: [recoveryPoint],
      pagination,
      correlationId: "corr",
    });
    renderPage(<RecoveryPointListPage />, "/backup-disaster-recovery/recovery-points");
    expect(screen.getByLabelText("Loading disaster recovery data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
  });

  it("surfaces recovery point query and configuration failures with retry controls", async () => {
    mockConfiguration();
    const list = vi
      .spyOn(backupDisasterRecoveryService, "listRecoveryPoints")
      .mockRejectedValueOnce(
        new BackupDisasterRecoveryError(
          "Recovery point index unavailable",
          503,
          "index_unavailable",
          "corr-points"
        )
      )
      .mockResolvedValue({ items: [recoveryPoint], pagination, correlationId: "corr" });

    const { unmount } = renderPage(
      <RecoveryPointListPage />,
      "/backup-disaster-recovery/recovery-points"
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-points");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "Recovery points" })).toBeInTheDocument();
    unmount();

    vi.restoreAllMocks();
    const configuration = vi
      .spyOn(backupDisasterRecoveryService, "getConfiguration")
      .mockRejectedValueOnce(
        new BackupDisasterRecoveryError(
          "Configuration unavailable",
          503,
          "configuration_unavailable",
          "corr-config"
        )
      )
      .mockResolvedValue(configurationFixture);
    vi.spyOn(backupDisasterRecoveryService, "listRecoveryPoints").mockResolvedValue({
      items: [recoveryPoint],
      pagination,
      correlationId: "corr",
    });

    renderPage(<RecoveryPointListPage />, "/backup-disaster-recovery/recovery-points");
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-config");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(configuration).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "Recovery points" })).toBeInTheDocument();
  });

  it("renders configured recovery point rows and keeps API filters explicit", async () => {
    mockConfiguration();
    const list = vi
      .spyOn(backupDisasterRecoveryService, "listRecoveryPoints")
      .mockResolvedValue({ items: [recoveryPoint], pagination, correlationId: "corr" });

    renderPage(<RecoveryPointListPage />, "/backup-disaster-recovery/recovery-points");

    expect(await screen.findByRole("heading", { name: "Recovery points" })).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith({
      status: undefined,
      search: undefined,
      ordering: "-captured_at",
    });
    expect(screen.getByRole("button", { name: "finance-ledger" })).toBeInTheDocument();
    expect(screen.getByText("tenant")).toBeInTheDocument();
    expect(screen.getByText("full")).toBeInTheDocument();
    expect(screen.getAllByText("available")).toHaveLength(2);
    expect(screen.getByText("1.5 KiB")).toBeInTheDocument();
    expect(screen.getByText("Not yet")).toBeInTheDocument();
    expect(screen.getByLabelText("Search recovery points")).toHaveClass("pl-9");
    for (const header of ["Scope", "Backup type", "Status", "Captured", "Expires", "Size"]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    for (const option of [
      "discovered",
      "verifying",
      "available",
      "corrupt",
      "expired",
      "deleted",
    ]) {
      expect(screen.getByRole("option", { name: option })).toHaveValue(option);
    }
    await userEvent.click(screen.getByRole("button", { name: "Request backup" }));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/backups/new"
    );

    await userEvent.selectOptions(screen.getByLabelText("Filter by status"), "corrupt");
    fireEvent.change(screen.getByLabelText("Search recovery points"), {
      target: { value: "finance" },
    });

    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith({
        status: "corrupt",
        search: "finance",
        ordering: "-captured_at",
      })
    );
  });

  it("navigates from recovery point table rows and empty state actions", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "listRecoveryPoints")
      .mockResolvedValueOnce({
        items: [recoveryPoint],
        pagination,
        correlationId: "corr",
      })
      .mockResolvedValue({ items: [], pagination, correlationId: "corr-empty" });

    renderPage(<RecoveryPointListPage />, "/backup-disaster-recovery/recovery-points");

    await userEvent.click(await screen.findByRole("button", { name: "finance-ledger" }));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/recovery-points/point-1"
    );

    await userEvent.selectOptions(screen.getByLabelText("Filter by status"), "deleted");
    expect(await screen.findByText("No recovery points match")).toBeInTheDocument();
    const requestBackupActions = screen.getAllByRole("button", { name: "Request backup" });
    expect(requestBackupActions).toHaveLength(2);
    const emptyStateAction = requestBackupActions[1];
    if (!emptyStateAction) throw new Error("Expected empty-state backup action.");
    await userEvent.click(emptyStateAction);
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/backups/new"
    );
  });
});

// eslint-disable-next-line max-lines-per-function -- mutation branch matrix is intentionally local to this page suite.
describe("RestoreRunListPage", () => {
  it("keeps the restore run skeleton active while either dependency is loading", () => {
    const client = createTestClient();
    client.setQueryData(configurationQueryKey, configurationFixture);
    vi.spyOn(backupDisasterRecoveryService, "listRestoreRuns").mockReturnValue(
      new Promise(() => undefined)
    );
    const { unmount } = renderPage(
      <RestoreRunListPage />,
      "/backup-disaster-recovery/restores",
      client
    );
    expect(screen.getByLabelText("Loading disaster recovery data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    unmount();

    vi.restoreAllMocks();
    vi.spyOn(backupDisasterRecoveryService, "getConfiguration").mockReturnValue(
      new Promise(() => undefined)
    );
    vi.spyOn(backupDisasterRecoveryService, "listRestoreRuns").mockResolvedValue({
      items: [restoreRun],
      pagination,
      correlationId: "corr",
    });
    renderPage(<RestoreRunListPage />, "/backup-disaster-recovery/restores");
    expect(screen.getByLabelText("Loading disaster recovery data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
  });

  it("surfaces restore run query and configuration failures with retry controls", async () => {
    mockConfiguration();
    const list = vi
      .spyOn(backupDisasterRecoveryService, "listRestoreRuns")
      .mockRejectedValueOnce(
        new BackupDisasterRecoveryError(
          "Restore run index unavailable",
          503,
          "restore_index_unavailable",
          "corr-restores"
        )
      )
      .mockResolvedValue({ items: [restoreRun], pagination, correlationId: "corr" });

    const { unmount } = renderPage(<RestoreRunListPage />, "/backup-disaster-recovery/restores");
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-restores");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "Restore runs" })).toBeInTheDocument();
    unmount();

    vi.restoreAllMocks();
    const configuration = vi
      .spyOn(backupDisasterRecoveryService, "getConfiguration")
      .mockRejectedValueOnce(
        new BackupDisasterRecoveryError(
          "Configuration unavailable",
          503,
          "configuration_unavailable",
          "corr-config"
        )
      )
      .mockResolvedValue(configurationFixture);
    vi.spyOn(backupDisasterRecoveryService, "listRestoreRuns").mockResolvedValue({
      items: [restoreRun],
      pagination,
      correlationId: "corr",
    });

    renderPage(<RestoreRunListPage />, "/backup-disaster-recovery/restores");
    expect(await screen.findByRole("alert")).toHaveTextContent("Correlation ID: corr-config");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(configuration).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "Restore runs" })).toBeInTheDocument();
  });

  it("renders restore rows with configured durations and status filters", async () => {
    mockConfiguration();
    const list = vi
      .spyOn(backupDisasterRecoveryService, "listRestoreRuns")
      .mockResolvedValue({ items: [restoreRun], pagination, correlationId: "corr" });

    renderPage(<RestoreRunListPage />, "/backup-disaster-recovery/restores");

    expect(await screen.findByRole("heading", { name: "Restore runs" })).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith({ status: undefined });
    expect(screen.getByRole("button", { name: "tenant-restore" })).toBeInTheDocument();
    expect(screen.getByText("selective restore")).toBeInTheDocument();
    expect(screen.getByText("isolated")).toBeInTheDocument();
    expect(screen.getAllByText("succeeded")).toHaveLength(2);
    expect(screen.getByText("30m")).toBeInTheDocument();
    expect(screen.getByText("Not measured")).toBeInTheDocument();
    for (const header of ["Target", "Environment", "Status", "Requested", "RPO", "RTO"]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeInTheDocument();
    }
    for (const option of [
      "queued",
      "validating",
      "ready",
      "restoring",
      "verifying",
      "succeeded",
      "failed",
      "cancelled",
    ]) {
      expect(screen.getByRole("option", { name: option })).toHaveValue(option);
    }
    await userEvent.click(screen.getByRole("button", { name: "Plan restore" }));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/restores/new"
    );

    await userEvent.selectOptions(screen.getByLabelText("Filter by status"), "failed");

    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ status: "failed" }));
  });

  it("navigates restore row and empty state actions through module paths", async () => {
    mockConfiguration();
    vi.spyOn(backupDisasterRecoveryService, "listRestoreRuns")
      .mockResolvedValueOnce({ items: [restoreRun], pagination, correlationId: "corr" })
      .mockResolvedValue({ items: [], pagination, correlationId: "corr-empty" });

    renderPage(<RestoreRunListPage />, "/backup-disaster-recovery/restores");

    await userEvent.click(await screen.findByRole("button", { name: "tenant-restore" }));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/restores/restore-1"
    );

    await userEvent.selectOptions(screen.getByLabelText("Filter by status"), "cancelled");
    expect(await screen.findByText("No restore runs match")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Plan a restore" }));
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/backup-disaster-recovery/restores/new"
    );
  });
});

describe("BackupExecutionCreatePage", () => {
  it("marks the canonical scope reference as browser-required", () => {
    renderPage(<BackupExecutionCreatePage />, "/backup-disaster-recovery/backups/new");

    expect(screen.getByLabelText("Canonical scope reference")).toBeRequired();
  });

  it("validates the scope before submission", async () => {
    const request = vi.spyOn(backupDisasterRecoveryService, "requestBackup");
    renderPage(<BackupExecutionCreatePage />, "/backup-disaster-recovery/backups/new");
    const input = screen.getByLabelText("Canonical scope reference");
    await userEvent.clear(input);
    await userEvent.click(screen.getByRole("button", { name: "Queue backup" }));
    expect(input).toBeInvalid();
    expect(request).not.toHaveBeenCalled();
  });

  it("prevents duplicate destructive submissions while a request is pending", async () => {
    let finish: ((receipt: BackupExecutionReceipt) => void) | undefined;
    const pending = new Promise<BackupExecutionReceipt>((resolve) => {
      finish = resolve;
    });
    const request = vi
      .spyOn(backupDisasterRecoveryService, "requestBackup")
      .mockReturnValue(pending);
    renderPage(<BackupExecutionCreatePage />, "/backup-disaster-recovery/backups/new");
    const button = screen.getByRole("button", { name: "Queue backup" });
    await userEvent.click(button);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Queuing backup…" })).toBeDisabled();
    await act(async () => {
      finish?.({
        backup_job_id: "job",
        async_job_id: "async",
        status: "queued",
        requested_at: "2026-07-21T00:00:00Z",
      });
      await pending;
    });
  });
});
