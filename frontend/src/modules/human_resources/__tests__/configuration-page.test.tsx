/* eslint-disable max-lines-per-function -- configuration-page coverage keeps behavior fixtures local to this suite. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ConfigurationAuditRecord,
  ConfigurationPreview,
  ConfigurationPreviewRequest,
  ConfigurationVersion,
  ConfigurationWrite,
  HumanResourcesConfiguration,
  HumanResourcesConfigurationDocument,
  PageResult,
} from "../contracts";
import { HumanResourcesConfigurationPage } from "../pages/HumanResourcesConfigurationPage";
import { HrApiError, hrService } from "../services/hr-service";

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));

type ConfigurationDocumentOverrides = Partial<
  Omit<
    HumanResourcesConfigurationDocument,
    | "allowed_values"
    | "limits"
    | "defaults"
    | "policies"
    | "workflows"
    | "feature_rollout"
    | "visual"
    | "operations"
  >
> & {
  allowed_values?: Partial<HumanResourcesConfigurationDocument["allowed_values"]>;
  limits?: Partial<HumanResourcesConfigurationDocument["limits"]>;
  defaults?: Partial<HumanResourcesConfigurationDocument["defaults"]>;
  policies?: Partial<HumanResourcesConfigurationDocument["policies"]>;
  workflows?: Partial<HumanResourcesConfigurationDocument["workflows"]>;
  feature_rollout?: Partial<HumanResourcesConfigurationDocument["feature_rollout"]>;
  visual?: Partial<HumanResourcesConfigurationDocument["visual"]>;
  operations?: Partial<HumanResourcesConfigurationDocument["operations"]>;
};

const pagination = {
  count: 0,
  page: 1,
  page_size: 25,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};

const documentFixture: HumanResourcesConfigurationDocument = {
  schema_version: 1,
  allowed_values: {
    employment_types: ["full_time", "part_time", "contractor", "temporary"],
    employment_statuses: ["active", "on_leave", "inactive", "terminated"],
    attendance_statuses: ["present", "absent", "late", "half_day", "on_leave"],
    attendance_sources: ["manual", "clock", "import"],
    leave_types: ["annual", "sick", "personal", "maternity", "paternity", "unpaid"],
    leave_states: ["pending", "approved", "rejected", "cancelled"],
    leave_scopes: ["all", "self", "team", "approval_queue"],
  },
  limits: {
    actor_identifier_max_length: 255,
    idempotency_key_max_length: 255,
    department_code_max_length: 50,
    department_name_max_length: 255,
    employee_number_max_length: 50,
    employee_name_max_length: 100,
    employee_email_max_length: 255,
    employee_phone_max_length: 50,
    employee_position_max_length: 100,
    hierarchy_max_depth: 100,
    reporting_tree_default_depth: 5,
    reporting_tree_max_depth: 20,
    department_tree_max_nodes: 500,
    max_hours_per_day: "24.00",
    leave_amount_minimum: "0.01",
    list_page_size: 25,
    lookup_page_size: 100,
    leave_input_minimum: "0.00",
    leave_input_step: "0.25",
    decimal_quantum: "0.01",
  },
  defaults: {
    department_active: true,
    employment_type: "full_time",
    employment_status: "active",
    attendance_hours: "0.00",
    attendance_status: "present",
    attendance_source: "manual",
    leave_type: "annual",
    leave_request_status: "pending",
    leave_entitled_days: "0.00",
    leave_carried_days: "0.00",
    leave_adjustment_version: 1,
    leave_adjustment_note: "Initial allocation",
    leave_scope: "all",
    department_ordering: "department_code",
    event_schema_version: 1,
  },
  policies: {
    manager_eligible_statuses: ["active", "on_leave"],
    employee_active_statuses: ["active", "on_leave"],
    attendance_eligible_statuses: ["active", "on_leave"],
    clock_in_eligible_statuses: ["active"],
    leave_eligible_statuses: ["active", "on_leave"],
    attendance_zero_work_statuses: ["absent", "on_leave"],
    leave_overlap_blocking_statuses: ["pending", "approved"],
    department_deactivation_blocks_active_children: true,
    department_deactivation_blocks_active_employees: true,
    employee_inactivation_requires_no_managed_departments: true,
    employee_archive_statuses: ["terminated"],
    employee_archive_blocks_pending_leave: true,
    leave_balance_enforce_capacity: true,
    leave_submission_blocks_insufficient_balance: true,
    allow_future_employee_transitions: false,
    approved_leave_cancel_before_start_only: true,
    leave_duration_calendar: "inclusive",
    one_attendance_per_employee_date: true,
  },
  workflows: {
    employee_terminal_states: ["terminated"],
    employee_transitions: [
      ["place_on_leave", "active", "on_leave"],
      ["return_from_leave", "on_leave", "active"],
      ["deactivate", "active", "inactive"],
      ["activate", "inactive", "active"],
      ["terminate", "active", "terminated"],
    ],
    leave_terminal_states: ["rejected", "cancelled"],
    leave_transitions: [
      ["approve", "pending", "approved"],
      ["reject", "pending", "rejected"],
      ["cancel", "pending", "cancelled"],
    ],
  },
  feature_rollout: { enabled: true, percentage: 100, roles: [], cohorts: [] },
  visual: { positive_status_token: "status-positive", warning_status_token: "status-warning" },
  operations: { health_staleness_seconds: 30 },
};

function cloneDocument(
  overrides: ConfigurationDocumentOverrides = {}
): HumanResourcesConfigurationDocument {
  return {
    ...documentFixture,
    ...overrides,
    allowed_values: { ...documentFixture.allowed_values, ...overrides.allowed_values },
    limits: { ...documentFixture.limits, ...overrides.limits },
    defaults: { ...documentFixture.defaults, ...overrides.defaults },
    policies: { ...documentFixture.policies, ...overrides.policies },
    workflows: { ...documentFixture.workflows, ...overrides.workflows },
    feature_rollout: { ...documentFixture.feature_rollout, ...overrides.feature_rollout },
    visual: { ...documentFixture.visual, ...overrides.visual },
    operations: { ...documentFixture.operations, ...overrides.operations },
  };
}

function configuration(
  overrides: Partial<HumanResourcesConfiguration> = {}
): HumanResourcesConfiguration {
  return {
    id: "config-1",
    environment: "default",
    version: 3,
    updated_at: "2026-01-05T00:00:00Z",
    document: cloneDocument(),
    ...overrides,
  };
}

function page<T>(items: readonly T[]): PageResult<T> {
  return {
    items,
    pagination: { ...pagination, count: items.length, total_pages: items.length ? 1 : 0 },
    correlationId: "corr-page",
    capabilities: [],
  };
}

function version(versionNumber: number): ConfigurationVersion {
  return {
    id: `version-${versionNumber}`,
    version: versionNumber,
    environment: "default",
    document: cloneDocument({ limits: { list_page_size: 10 + versionNumber } }),
    created_by: "hr-admin",
    correlation_id: `corr-version-${versionNumber}`,
    created_at: "2026-01-04T00:00:00Z",
    change_reason: `Version ${versionNumber} change`,
    rolled_back_from_version: null,
  };
}

function auditRecord(): ConfigurationAuditRecord {
  return {
    id: "audit-1",
    environment: "default",
    version: 3,
    action: "update",
    actor_id: "hr-admin",
    correlation_id: "corr-audit-1",
    created_at: "2026-01-05T00:00:00Z",
    change_reason: "Enable governed rollout",
    before_document: cloneDocument({ feature_rollout: { enabled: false, percentage: 0 } }),
    after_document: cloneDocument(),
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <HumanResourcesConfigurationPage />
    </QueryClientProvider>
  );
}

function mockConfigurationQueries({
  current = configuration(),
  versions = [version(3), version(2)],
  audits = [auditRecord()],
}: {
  current?: HumanResourcesConfiguration;
  versions?: readonly ConfigurationVersion[];
  audits?: readonly ConfigurationAuditRecord[];
} = {}) {
  vi.spyOn(hrService, "getConfiguration").mockResolvedValue({
    data: current,
    correlationId: "corr-config",
    capabilities: ["hr.configuration:read"],
  });
  vi.spyOn(hrService, "getConfigurationHistory").mockResolvedValue(page(versions));
  vi.spyOn(hrService, "getConfigurationAudit").mockResolvedValue(page(audits));
}

async function loadReadyPage() {
  renderPage();
  await screen.findByRole("heading", { name: "Human Resources configuration" });
}

describe("Human Resources configuration page", () => {
  beforeEach(() => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-key-1") });
    vi.mocked(toast.success).mockClear();
    mockConfigurationQueries();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows a loading shell and then renders empty history and audit states", async () => {
    mockConfigurationQueries({ versions: [], audits: [] });

    renderPage();

    expect(screen.getByRole("status", { name: "Loading Human Resources" })).toBeInTheDocument();
    expect(await screen.findByText("No prior versions.")).toBeInTheDocument();
    expect(screen.getByText("No configuration changes recorded.")).toBeInTheDocument();
    expect(screen.getByText("Current version")).toHaveTextContent("3");
  });

  it("renders governed errors with correlation evidence and retries all configuration queries", async () => {
    const getConfiguration = vi
      .spyOn(hrService, "getConfiguration")
      .mockRejectedValueOnce(
        new HrApiError(
          "Configuration unavailable",
          "unavailable",
          503,
          "hr_configuration_unavailable",
          "corr-config-down"
        )
      )
      .mockResolvedValueOnce({
        data: configuration(),
        correlationId: "corr-config",
        capabilities: ["hr.configuration:read"],
      });
    const getHistory = vi.spyOn(hrService, "getConfigurationHistory").mockResolvedValue(page([]));
    const getAudit = vi.spyOn(hrService, "getConfigurationAudit").mockResolvedValue(page([]));

    renderPage();

    expect(await screen.findByText(/corr-config-down/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => expect(screen.getByText("No prior versions.")).toBeInTheDocument());
    expect(getConfiguration).toHaveBeenCalledTimes(2);
    expect(getHistory).toHaveBeenCalledTimes(2);
    expect(getAudit).toHaveBeenCalledTimes(2);
  });

  it("blocks preview and save when safe-limit validation fails", async () => {
    const preview = vi.spyOn(hrService, "previewConfiguration");
    const save = vi.spyOn(hrService, "updateConfiguration");
    const user = userEvent.setup();

    await loadReadyPage();

    await user.clear(screen.getByLabelText(/list page size/i));
    await user.type(screen.getByLabelText(/list page size/i), "101");

    expect(screen.getByRole("alert")).toHaveTextContent(
      "List page size must be between 1 and 100."
    );
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save version" })).toBeDisabled();
    expect(preview).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
  });

  it("requires rollout allow-lists before role-targeted activation can be previewed", async () => {
    const user = userEvent.setup();

    await loadReadyPage();

    await user.selectOptions(screen.getByLabelText(/rollout target/i), "role");

    expect(screen.getByLabelText(/roles/i)).toBeEnabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Role rollout requires at least one role.");
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();

    await user.type(screen.getByLabelText(/roles/i), "hr-admin, people-ops");

    expect(screen.queryByText("Role rollout requires at least one role.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toBeEnabled();
  });

  it("previews a draft before save and sends idempotency only on the write payload", async () => {
    const previewData: ConfigurationPreview = {
      valid: true,
      normalized_document: cloneDocument({ limits: { list_page_size: 50 } }),
      changes: [{ path: "limits.list_page_size", before: 25, after: 50 }],
    };
    const preview = vi.spyOn(hrService, "previewConfiguration").mockResolvedValue({
      data: previewData,
      correlationId: "corr-preview",
      capabilities: [],
    });
    const save = vi.spyOn(hrService, "updateConfiguration").mockResolvedValue({
      data: configuration({
        version: 4,
        document: cloneDocument({ limits: { list_page_size: 50 } }),
      }),
      correlationId: "corr-save",
      capabilities: [],
    });
    const user = userEvent.setup();

    await loadReadyPage();

    await user.clear(screen.getByLabelText(/list page size/i));
    await user.type(screen.getByLabelText(/list page size/i), "50");
    await user.type(screen.getByLabelText(/change reason/i), "Increase HR list size");
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(preview).toHaveBeenCalledTimes(1));
    const previewPayload: ConfigurationPreviewRequest | undefined = preview.mock.calls[0]?.[0];

    expect(previewPayload).toBeDefined();
    if (!previewPayload) throw new Error("Preview payload was not captured.");
    expect(previewPayload.environment).toBe("default");
    expect(previewPayload.document.limits.list_page_size).toBe(50);
    expect(previewPayload.change_reason).toBe("Increase HR list size");
    expect(previewPayload).not.toHaveProperty("idempotency_key");
    expect(await screen.findByText("limits.list_page_size")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save version" }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    const savePayload: ConfigurationWrite | undefined = save.mock.calls[0]?.[0];

    expect(savePayload).toBeDefined();
    if (!savePayload) throw new Error("Save payload was not captured.");
    expect(savePayload.environment).toBe("default");
    expect(savePayload.document.limits.list_page_size).toBe(50);
    expect(savePayload.change_reason).toBe("Increase HR list size");
    expect(savePayload.idempotency_key).toBe("intent-key-1");
    expect(toast.success).toHaveBeenCalledWith("Configuration version saved with audit evidence.");
  });

  it("exports the active environment as a versioned JSON download", async () => {
    const createObjectUrl = vi.fn(() => "blob:hr-config");
    const revokeObjectUrl = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    vi.stubGlobal("URL", { createObjectURL: createObjectUrl, revokeObjectURL: revokeObjectUrl });
    const exported = {
      schema: "saraise.human_resources.configuration" as const,
      environment: "default" as const,
      version: 3,
      document: cloneDocument(),
    };
    const exportConfiguration = vi.spyOn(hrService, "exportConfiguration").mockResolvedValue({
      data: exported,
      correlationId: "corr-export",
      capabilities: [],
    });

    await loadReadyPage();
    await userEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() => expect(exportConfiguration).toHaveBeenCalledWith("default"));
    expect(createObjectUrl).toHaveBeenCalledWith(expect.any(Blob));
    expect(click).toHaveBeenCalled();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:hr-config");
  });

  it("validates import JSON locally and imports a governed document with idempotency", async () => {
    const importedDocument = cloneDocument({ defaults: { leave_type: "sick" } });
    const importConfiguration = vi.spyOn(hrService, "importConfiguration").mockResolvedValue({
      data: configuration({ version: 4, document: importedDocument }),
      correlationId: "corr-import",
      capabilities: [],
    });
    const user = userEvent.setup();

    await loadReadyPage();

    await user.type(screen.getByLabelText(/change reason/i), "Promote reviewed HR config");
    fireEvent.change(screen.getByPlaceholderText('{"schema_version": 1, "...": "..."}'), {
      target: { value: "{bad" },
    });
    await user.click(screen.getByRole("button", { name: "Import as new version" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Expected property name");
    expect(importConfiguration).not.toHaveBeenCalled();

    fireEvent.change(screen.getByPlaceholderText('{"schema_version": 1, "...": "..."}'), {
      target: { value: JSON.stringify(importedDocument) },
    });
    await user.click(screen.getByRole("button", { name: "Import as new version" }));

    await waitFor(() =>
      expect(importConfiguration).toHaveBeenCalledWith({
        environment: "default",
        document: importedDocument,
        change_reason: "Promote reviewed HR config",
        idempotency_key: "intent-key-1",
      })
    );
    expect(toast.success).toHaveBeenCalledWith("Configuration imported and versioned.");
  });

  it("rolls back a prior version only after an audited change reason is entered", async () => {
    const rollback = vi.spyOn(hrService, "rollbackConfiguration").mockResolvedValue({
      data: configuration({ version: 4 }),
      correlationId: "corr-rollback",
      capabilities: [],
    });
    const user = userEvent.setup();

    await loadReadyPage();

    const currentVersion = screen.getByText("Version 3").closest("li");
    const priorVersion = screen.getByText("Version 2").closest("li");

    expect(currentVersion).not.toBeNull();
    expect(priorVersion).not.toBeNull();
    expect(
      within(currentVersion as HTMLElement).getByRole("button", { name: "Rollback" })
    ).toBeDisabled();
    expect(
      within(priorVersion as HTMLElement).getByRole("button", { name: "Rollback" })
    ).toBeDisabled();

    await user.type(screen.getByLabelText(/change reason/i), "Rollback unsafe rollout");
    await user.click(within(priorVersion as HTMLElement).getByRole("button", { name: "Rollback" }));

    await waitFor(() =>
      expect(rollback).toHaveBeenCalledWith({
        environment: "default",
        version: 2,
        change_reason: "Rollback unsafe rollout",
        idempotency_key: "intent-key-1",
      })
    );
    expect(toast.success).toHaveBeenCalledWith("Rollback created a new configuration version.");
    expect(screen.getByText("corr-audit-1")).toBeInTheDocument();
  });

  it("applies advanced drafts and shows no-change preview output", async () => {
    const preview = vi.spyOn(hrService, "previewConfiguration").mockResolvedValue({
      data: { valid: true, normalized_document: cloneDocument(), changes: [] },
      correlationId: "corr-preview-empty",
      capabilities: [],
    });
    const user = userEvent.setup();

    await loadReadyPage();

    const advancedDocument = screen.getAllByRole("textbox", { name: "" })[0];
    if (!advancedDocument)
      throw new Error("Advanced configuration document editor was not rendered.");

    await waitFor(() =>
      expect((advancedDocument as HTMLTextAreaElement).value).toContain('"schema_version": 1')
    );
    fireEvent.change(advancedDocument, { target: { value: '{"schema_version":1}' } });
    await user.click(screen.getByRole("button", { name: "Apply advanced draft" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Top-level fields must exactly match the governed HR configuration contract."
    );

    fireEvent.change(advancedDocument, { target: { value: JSON.stringify(cloneDocument()) } });
    await user.click(screen.getByRole("button", { name: "Apply advanced draft" }));
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(preview).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("No changes from the active version.")).toBeInTheDocument();
  });
});
