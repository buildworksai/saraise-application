/* eslint-disable max-lines-per-function, @typescript-eslint/consistent-type-imports -- behavior coverage spans multiple governed pages. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CreateDataMigrationJobPage } from "../CreateDataMigrationJobPage";
import { DataMigrationDetailPage } from "../DataMigrationDetailPage";
import { EditDataMigrationJobPage } from "../EditDataMigrationJobPage";
import { ExternalConnectionsPage } from "../ExternalConnectionsPage";
import { MigrationRunDetailPage } from "../MigrationRunDetailPage";
import { dataMigrationService } from "../../services/data-migration-service";

const authState = vi.hoisted(() => ({
  user: { is_staff: true, is_superuser: false, platform_role: "operator" },
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock("sonner", () => ({ toast }));
vi.mock("@/stores/auth-store", () => ({
  useAuthStore: <T,>(selector: (state: typeof authState) => T) => selector(authState),
}));
vi.mock("../../services/data-migration-service", () => {
  class MockDataMigrationApiError extends Error {
    constructor(readonly status: number) {
      super("request failed");
      this.name = "DataMigrationApiError";
    }
  }
  return {
    DataMigrationApiError: MockDataMigrationApiError,
    dataMigrationService: {
      jobs: {
        get: vi.fn(),
        create: vi.fn(),
        update: vi.fn(),
        validate: vi.fn(),
        inspect: vi.fn(),
        export: vi.fn(),
        import: vi.fn(),
        versions: vi.fn(),
        preview: vi.fn(),
      },
      mappings: { list: vi.fn(), suggest: vi.fn(), apply: vi.fn() },
      rules: { list: vi.fn() },
      runs: {
        list: vi.fn(),
        get: vi.fn(),
        start: vi.fn(),
        dryRun: vi.fn(),
        cancel: vi.fn(),
        issues: vi.fn(),
        exportIssuesUrl: vi.fn((id: string) => `/issues/${id}.csv`),
      },
      rollbacks: { request: vi.fn() },
      connections: {
        list: vi.fn(),
        create: vi.fn(),
        test: vi.fn(),
        rotateCredential: vi.fn(),
        deactivate: vi.fn(),
      },
      configuration: {
        get: vi.fn(),
        update: vi.fn(),
        preview: vi.fn(),
        versions: vi.fn(),
        restore: vi.fn(),
        export: vi.fn(),
        import: vi.fn(),
      },
    },
  };
});

const pagination = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

function paged<T>(items: readonly T[]) {
  return { items, pagination, correlationId: "corr-dm-test" };
}

function renderRoute(element: ReactElement, path = "/", initialEntry = path) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path={path} element={element} />
          <Route path="*" element={<span>navigated</span>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function inputForLabel(label: string, index = 0) {
  const labelNode = screen.getAllByText(label)[index];
  if (!labelNode) throw new Error(`Label ${label} was not rendered.`);
  const node = labelNode.closest("label")?.querySelector("input");
  if (!node) throw new Error(`Input for ${label} was not rendered.`);
  return node;
}

function migrationJob(
  overrides: Partial<Awaited<ReturnType<typeof dataMigrationService.jobs.get>>> = {}
) {
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
    latest_run: null,
    allowed_actions: ["update", "dry_run", "run", "export"],
    created_at: "2026-07-22T00:00:00Z",
    updated_at: "2026-07-22T00:00:00Z",
    ...overrides,
  } as Awaited<ReturnType<typeof dataMigrationService.jobs.get>>;
}

function configuration() {
  return {
    version: 4,
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
    updated_at: "2026-07-22T00:00:00Z",
  } as Awaited<ReturnType<typeof dataMigrationService.configuration.get>>;
}

function configurationValues() {
  const { version: _version, updated_at: _updatedAt, ...values } = configuration();
  void _version;
  void _updatedAt;
  return values;
}

function migrationRun(
  overrides: Partial<Awaited<ReturnType<typeof dataMigrationService.runs.get>>> = {}
) {
  return {
    id: "run-1",
    job: "job-1",
    job_version: "3",
    mode: "commit",
    status: "succeeded",
    source_checksum: "sha256:source",
    processed_records: 10,
    total_records: 10,
    succeeded_records: 8,
    failed_records: 1,
    warning_records: 1,
    started_at: "2026-07-22T00:00:00Z",
    completed_at: "2026-07-22T00:00:10Z",
    cancel_requested_at: null,
    correlation_id: "corr-run-1",
    rollback_eligible: true,
    allowed_actions: ["cancel", "rollback", "export_issues"],
    created_at: "2026-07-22T00:00:00Z",
    updated_at: "2026-07-22T00:00:10Z",
    ...overrides,
  } as Awaited<ReturnType<typeof dataMigrationService.runs.get>>;
}

describe("data migration workflow pages", () => {
  const jobsGet = vi.mocked(dataMigrationService.jobs.get);
  const jobsCreate = vi.mocked(dataMigrationService.jobs.create);
  const jobsUpdate = vi.mocked(dataMigrationService.jobs.update);
  const jobsInspect = vi.mocked(dataMigrationService.jobs.inspect);
  const jobsVersions = vi.mocked(dataMigrationService.jobs.versions);
  const jobsPreview = vi.mocked(dataMigrationService.jobs.preview);
  const mappingsList = vi.mocked(dataMigrationService.mappings.list);
  const mappingsSuggest = vi.mocked(dataMigrationService.mappings.suggest);
  const mappingsApply = vi.mocked(dataMigrationService.mappings.apply);
  const rulesList = vi.mocked(dataMigrationService.rules.list);
  const runsList = vi.mocked(dataMigrationService.runs.list);
  const runsGet = vi.mocked(dataMigrationService.runs.get);
  const runsStart = vi.mocked(dataMigrationService.runs.start);
  const runsDryRun = vi.mocked(dataMigrationService.runs.dryRun);
  const runsCancel = vi.mocked(dataMigrationService.runs.cancel);
  const runsIssues = vi.mocked(dataMigrationService.runs.issues);
  const rollbacksRequest = vi.mocked(dataMigrationService.rollbacks.request);
  const connectionsList = vi.mocked(dataMigrationService.connections.list);
  const connectionsCreate = vi.mocked(dataMigrationService.connections.create);
  const connectionsTest = vi.mocked(dataMigrationService.connections.test);
  const connectionsRotateCredential = vi.mocked(dataMigrationService.connections.rotateCredential);
  const connectionsDeactivate = vi.mocked(dataMigrationService.connections.deactivate);
  const configurationGet = vi.mocked(dataMigrationService.configuration.get);
  const configurationUpdate = vi.mocked(dataMigrationService.configuration.update);
  const configurationPreview = vi.mocked(dataMigrationService.configuration.preview);
  const configurationVersions = vi.mocked(dataMigrationService.configuration.versions);
  const configurationExport = vi.mocked(dataMigrationService.configuration.export);
  const configurationImport = vi.mocked(dataMigrationService.configuration.import);

  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = { is_staff: true, is_superuser: false, platform_role: "operator" };
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "idem-1") });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    connectionsList.mockResolvedValue(paged([]));
    configurationGet.mockResolvedValue(configuration());
    configurationVersions.mockResolvedValue(paged([]));
  });

  it("registers HTTPS connections with write-only credential references and safe runtime defaults", async () => {
    connectionsCreate.mockResolvedValue({
      id: "conn-1",
      name: "Partner API",
      kind: "http",
      is_active: true,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    });
    const user = userEvent.setup();

    renderRoute(<ExternalConnectionsPage />);
    await user.click(await screen.findByRole("button", { name: /Register connection/u }));
    await user.type(inputForLabel("Name"), "Partner API");
    await user.selectOptions(screen.getByLabelText("Provider"), "http");
    await user.clear(inputForLabel("HTTPS base URL"));
    await user.type(inputForLabel("HTTPS base URL"), "https://partner.example");
    await user.type(inputForLabel("Credential secret reference"), "secret://partner");
    await user.click(screen.getAllByRole("button", { name: "Register connection" }).at(-1)!);

    await waitFor(() => expect(connectionsCreate).toHaveBeenCalled());
    expect(connectionsCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Partner API",
        kind: "http",
        base_url: "https://partner.example",
        credential_ref: "secret://partner",
        tls_mode: "verify-full",
        public_options: { connect_timeout_seconds: 5, read_timeout_seconds: 30 },
      })
    );
    expect(connectionsCreate.mock.calls[0]?.[0]).toMatchObject({
      host: undefined,
      port: undefined,
      database: undefined,
      username: undefined,
    });
  });

  it("previews configuration changes before enabling save", async () => {
    configurationPreview.mockResolvedValue({
      from_version: 4,
      changes: [{ field: "batch_size", before: 100, after: 250 }],
    });
    configurationUpdate.mockResolvedValue({ ...configuration(), version: 5 });
    const user = userEvent.setup();

    renderRoute(<ExternalConnectionsPage />);
    await screen.findByText("Runtime configuration");
    await user.clear(inputForLabel("Batch size"));
    await user.type(inputForLabel("Batch size"), "250");
    expect(screen.getByRole("button", { name: "Apply configuration" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Preview semantic diff" }));
    expect(await screen.findByText("batch_size: 100 → 250")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply configuration" }));

    await waitFor(() => expect(configurationUpdate).toHaveBeenCalled());
    expect(configurationUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ batch_size: 250, expected_version: 4 })
    );
  });

  it("tests, rotates, deactivates, exports, and imports governed external connection settings", async () => {
    connectionsList.mockResolvedValue(
      paged([
        {
          id: "conn-1",
          name: "Warehouse replica",
          kind: "postgresql",
          is_active: true,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
        },
      ])
    );
    connectionsTest.mockResolvedValue({
      verified: true,
      outcome: "success",
      checked_at: "2026-07-22T00:00:00Z",
      latency_ms: 42,
      code: "OK",
      message: "Connected",
    });
    connectionsRotateCredential.mockResolvedValue({
      id: "conn-1",
      name: "Warehouse replica",
      kind: "postgresql",
      is_active: true,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    });
    connectionsDeactivate.mockResolvedValue({
      id: "conn-1",
      name: "Warehouse replica",
      kind: "postgresql",
      is_active: false,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    });
    configurationExport.mockResolvedValue({
      schema_version: 1,
      checksum: "sha256:config",
      configuration: configurationValues(),
    });
    configurationImport.mockResolvedValue({ ...configuration(), version: 5 });
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:data-migration-config"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:data-migration-config");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(window, "prompt").mockReturnValue("secret://warehouse-rotated");
    const user = userEvent.setup();

    renderRoute(<ExternalConnectionsPage />);
    expect(await screen.findByText("Warehouse replica")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Test/u }));
    await waitFor(() => expect(connectionsTest).toHaveBeenCalledWith("conn-1"));
    await user.click(screen.getByRole("button", { name: "Rotate credential" }));
    await waitFor(() =>
      expect(connectionsRotateCredential).toHaveBeenCalledWith(
        "conn-1",
        "secret://warehouse-rotated"
      )
    );
    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() => expect(connectionsDeactivate).toHaveBeenCalledWith("conn-1"));

    await user.click(screen.getByRole("button", { name: "Export config" }));
    await waitFor(() => expect(configurationExport).toHaveBeenCalled());
    expect(clickSpy).toHaveBeenCalled();

    const importFile = new File(["{}"], "data-migration-configuration.json", {
      type: "application/json",
    });
    Object.defineProperty(importFile, "text", {
      configurable: true,
      value: vi.fn().mockResolvedValue(
        JSON.stringify({
          schema_version: 1,
          checksum: "sha256:config",
          configuration: configurationValues(),
        })
      ),
    });
    await user.upload(screen.getByLabelText("Import config"), importFile);
    await waitFor(() =>
      expect(configurationImport).toHaveBeenCalledWith(
        expect.objectContaining({ checksum: "sha256:config", expected_version: 4 })
      )
    );
  });

  it("hides operator-only settings and secret fields from non-operator users", async () => {
    authState.user = { is_staff: false, is_superuser: false, platform_role: "" };
    connectionsList.mockResolvedValue(
      paged([
        {
          id: "conn-1",
          name: "Warehouse replica",
          kind: "postgresql",
          is_active: true,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
        },
      ])
    );

    renderRoute(<ExternalConnectionsPage />);

    expect(await screen.findByText("Warehouse replica")).toBeInTheDocument();
    expect(screen.getByText(/read-only access to safe connection references/u)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Register connection" })).not.toBeInTheDocument();
    expect(screen.queryByText("Runtime configuration")).not.toBeInTheDocument();
    expect(configurationGet).not.toHaveBeenCalled();
  });

  it("runs definition tabs from overview blockers through source preview and dry-run acceptance", async () => {
    jobsGet.mockResolvedValue(
      migrationJob({
        readiness: {
          ready: false,
          blockers: [
            { code: "source_missing", message: "Inspect source first", section: "source" },
          ],
        },
      })
    );
    jobsPreview.mockResolvedValue({
      records: [{ fields: [{ name: "external_id", value: 1, redacted: false }] }],
      source_checksum: "sha256:abc",
      truncated: true,
    });
    runsDryRun.mockResolvedValue(migrationRun({ mode: "dry_run" }));
    const user = userEvent.setup();

    renderRoute(
      <DataMigrationDetailPage />,
      "/data-migration/jobs/:id",
      "/data-migration/jobs/job-1"
    );
    await user.click(await screen.findByRole("button", { name: /Inspect source first/u }));
    expect(await screen.findByText(/1 bounded preview rows/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Dry run/u }));

    await waitFor(() =>
      expect(runsDryRun).toHaveBeenCalledWith("job-1", {
        idempotency_key: "idem-1",
      })
    );
  });

  it("loads detail tabs on demand and keeps commit runs behind confirmation", async () => {
    jobsGet.mockResolvedValue(migrationJob());
    mappingsList.mockResolvedValue(
      paged([
        {
          id: "mapping-1",
          job: "job-1",
          source_field: "external_id",
          target_field: "externalId",
          position: 1,
          transform_type: "identity",
          transform_config: { transform_type: "identity" },
          origin: "manual",
          confidence: "0.87",
          is_required: true,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
        },
      ])
    );
    rulesList.mockResolvedValue(
      paged([
        {
          id: "rule-1",
          job: "job-1",
          field_name: "external_id",
          rule_type: "required",
          rule_config: { rule_type: "required", trim: true },
          severity: "error",
          error_message: "External id is required",
          position: 1,
          is_active: true,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
        },
      ])
    );
    runsList.mockResolvedValue(paged([migrationRun({ mode: "commit" })]));
    jobsVersions.mockResolvedValue(
      paged([
        {
          id: "version-2",
          job: "job-1",
          version: 2,
          snapshot: {
            schema_version: "2.0",
            checksum: "sha256:version-2",
            job: {
              name: "Customer import",
              description: "Import external customer identifiers.",
              source_type: "csv",
              source_config: { delimiter: ",", encoding: "utf-8", header_row: 1, batch_size: 100 },
              target_adapter: "crm",
              target_entity: "customer",
              write_mode: "upsert",
              lookup_fields: ["external_id"],
            },
            mappings: [],
            rules: [],
          },
          change_summary: "Validated target mapping.",
          correlation_id: "corr-version-2",
          created_at: "2026-07-22T00:00:00Z",
          created_by: "operator-1",
        },
      ])
    );
    runsStart.mockResolvedValue(migrationRun({ mode: "commit" }));
    const confirm = vi.spyOn(window, "confirm");
    confirm.mockReturnValueOnce(false).mockReturnValueOnce(true);
    const user = userEvent.setup();

    renderRoute(
      <DataMigrationDetailPage />,
      "/data-migration/jobs/:id",
      "/data-migration/jobs/job-1"
    );

    await user.click(await screen.findByRole("button", { name: "mappings" }));
    expect(await screen.findByText("external_id")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "validation rules" }));
    expect(await screen.findByText("External id is required")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "runs" }));
    expect(await screen.findByText("commit")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "configuration history" }));
    expect(await screen.findByText("Validated target mapping.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Commit run/u }));
    expect(runsStart).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /Commit run/u }));
    await waitFor(() =>
      expect(runsStart).toHaveBeenCalledWith("job-1", { idempotency_key: "idem-1" })
    );
  });

  it("creates a job, inspects the source, and applies only non-PII mapping suggestions", async () => {
    jobsCreate.mockResolvedValue(migrationJob({ id: "job-created" }));
    jobsInspect.mockResolvedValue({ async_job_id: "inspect-job-1", status: "queued" });
    mappingsSuggest.mockResolvedValue([
      {
        id: "safe-1",
        source_field: "external_id",
        target_field: "externalId",
        confidence: 0.91,
        pii: false,
        origin: "deterministic",
      },
      {
        id: "pii-1",
        source_field: "email",
        target_field: "email",
        confidence: 0.99,
        pii: true,
        origin: "deterministic",
      },
    ]);
    mappingsApply.mockResolvedValue([]);
    const user = userEvent.setup();

    renderRoute(<CreateDataMigrationJobPage />);
    await user.type(screen.getByLabelText("Name"), "Customer import");
    await user.type(screen.getByLabelText("DMS artifact version ID"), "artifact-1");
    await user.click(screen.getByRole("button", { name: /Target/u }));
    await user.type(screen.getByLabelText("Registered target adapter"), "crm.customer");
    await user.type(screen.getByLabelText("Target entity"), "customer");
    await user.selectOptions(screen.getByLabelText("Write mode"), "upsert");
    await user.type(screen.getByLabelText("Lookup fields"), "external_id, region");
    await user.click(screen.getByRole("button", { name: /Save draft and inspect/u }));
    await user.click(await screen.findByRole("button", { name: "Inspect source" }));
    await user.click(await screen.findByRole("button", { name: /Map fields/u }));
    await user.click(screen.getByRole("button", { name: "Generate suggestions" }));
    expect(await screen.findByText("Manual review required")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply safe suggestions" }));

    expect(jobsCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Customer import",
        source_type: "csv",
        source_artifact_id: "artifact-1",
        lookup_fields: ["external_id", "region"],
      })
    );
    await waitFor(() => expect(mappingsApply).toHaveBeenCalledWith("job-created", ["safe-1"]));
  });

  it("fails closed in the create wizard until source and upsert identity are complete", async () => {
    const user = userEvent.setup();

    renderRoute(<CreateDataMigrationJobPage />);

    expect(screen.getByRole("button", { name: /Target/u })).toBeDisabled();
    await user.type(screen.getByLabelText("Name"), "Unsafe API import");
    await user.selectOptions(screen.getByLabelText("Source type"), "HTTP API");
    expect(screen.getByRole("button", { name: /Target/u })).toBeDisabled();
    await user.clear(screen.getByLabelText("Relative path"));
    await user.type(screen.getByLabelText("Relative path"), "https://evil.example/customers");
    expect(screen.getByRole("button", { name: /Target/u })).toBeDisabled();
    expect(jobsCreate).not.toHaveBeenCalled();
  });

  it("creates API jobs only from active HTTP connections with safe relative source config", async () => {
    connectionsList.mockResolvedValue(
      paged([
        {
          id: "conn-http",
          name: "Partner HTTP",
          kind: "http",
          is_active: true,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
        },
        {
          id: "conn-db",
          name: "Warehouse DB",
          kind: "postgresql",
          is_active: true,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
        },
      ])
    );
    jobsCreate.mockResolvedValue(migrationJob({ id: "job-api", source_type: "api" }));
    const user = userEvent.setup();

    renderRoute(<CreateDataMigrationJobPage />);
    await user.type(screen.getByLabelText("Name"), "Partner API import");
    await user.selectOptions(screen.getByLabelText("Source type"), "HTTP API");
    await user.selectOptions(await screen.findByLabelText("Named connection"), "conn-http");
    expect(screen.queryByRole("option", { name: "Warehouse DB" })).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("Relative path"));
    await user.type(screen.getByLabelText("Relative path"), "/customers");
    await user.click(screen.getByRole("button", { name: /Target/u }));
    await user.type(screen.getByLabelText("Registered target adapter"), "crm.customer");
    await user.type(screen.getByLabelText("Target entity"), "customer");
    await user.selectOptions(screen.getByLabelText("Write mode"), "upsert");
    expect(screen.getByRole("button", { name: /Save draft and inspect/u })).toBeDisabled();
    await user.type(screen.getByLabelText("Lookup fields"), "external_id");
    await user.click(screen.getByRole("button", { name: /Save draft and inspect/u }));

    await waitFor(() => expect(jobsCreate).toHaveBeenCalled());
    const [payload] = jobsCreate.mock.calls[0] ?? [];
    expect(jobsCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        source_type: "api",
        source_artifact_id: null,
        write_mode: "upsert",
        lookup_fields: ["external_id"],
      })
    );
    expect(payload?.source_config).toEqual(
      expect.objectContaining({
        connection_id: "conn-http",
        relative_path: "/customers",
        method: "GET",
        page_size: 500,
      })
    );
  });

  it("edits a definition only after showing the semantic diff", async () => {
    jobsGet.mockResolvedValue(migrationJob());
    jobsVersions.mockResolvedValue(paged([]));
    jobsUpdate.mockResolvedValue(migrationJob({ configuration_version: 4 }));
    const user = userEvent.setup();

    renderRoute(
      <EditDataMigrationJobPage />,
      "/data-migration/jobs/:id/edit",
      "/data-migration/jobs/job-1/edit"
    );
    await user.clear(await screen.findByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Customer import v2");
    await user.click(screen.getByRole("button", { name: "Preview changes" }));
    expect(screen.getByText(/Name: Customer import/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply versioned changes" }));

    await waitFor(() =>
      expect(jobsUpdate).toHaveBeenCalledWith("job-1", {
        name: "Customer import v2",
        description: "Tenant customer import",
        target_adapter: "crm.customer",
        target_entity: "customer",
        expected_version: 3,
      })
    );
  });

  it("exports edit definitions, rejects malformed imports, and previews valid imports without applying", async () => {
    jobsGet.mockResolvedValue(migrationJob());
    jobsVersions.mockResolvedValue(paged([]));
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
      job: null,
      checksum_valid: true,
      diff: {
        from_version: 3,
        to_version: null,
        entries: [{ path: "job.name", operation: "replace", before: "Old", after: "New" }],
        warnings: [],
      },
    });
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:migration-definition");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const user = userEvent.setup();

    renderRoute(
      <EditDataMigrationJobPage />,
      "/data-migration/jobs/:id/edit",
      "/data-migration/jobs/job-1/edit"
    );

    await user.click(await screen.findByRole("button", { name: "Export" }));
    await waitFor(() => expect(dataMigrationService.jobs.export).toHaveBeenCalledWith("job-1"));
    expect(clickSpy).toHaveBeenCalled();

    const invalidFile = new File(["{}"], "invalid.json", { type: "application/json" });
    Object.defineProperty(invalidFile, "text", {
      configurable: true,
      value: vi.fn().mockResolvedValue("{"),
    });
    await user.upload(screen.getByLabelText("Choose JSON"), invalidFile);
    expect(toast.error).toHaveBeenCalledWith("This is not a valid versioned migration document.");

    const validFile = new File(["{}"], "definition.json", { type: "application/json" });
    Object.defineProperty(validFile, "text", {
      configurable: true,
      value: vi.fn().mockResolvedValue(
        JSON.stringify({
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
        })
      ),
    });
    await user.upload(screen.getByLabelText("Choose JSON"), validFile);
    await user.click(await screen.findByRole("button", { name: "Preview import" }));

    await waitFor(() =>
      expect(dataMigrationService.jobs.import).toHaveBeenCalledWith(
        expect.objectContaining({ preview_only: true })
      )
    );
    expect(toast.success).toHaveBeenCalledWith(
      "1 semantic changes detected. Import preview is ready for review."
    );
  });

  it("shows detail fail-closed source preview errors and export errors without starting runs", async () => {
    jobsGet.mockResolvedValue(migrationJob({ allowed_actions: ["export", "dry_run", "run"] }));
    jobsPreview.mockRejectedValue(new Error("Preview blocked by source policy"));
    vi.mocked(dataMigrationService.jobs.export).mockRejectedValue(new Error("Export blocked"));
    const user = userEvent.setup();

    renderRoute(
      <DataMigrationDetailPage />,
      "/data-migration/jobs/:id",
      "/data-migration/jobs/job-1"
    );
    await user.click(await screen.findByRole("button", { name: "source profile" }));
    expect(await screen.findByText("Preview blocked by source policy")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Export failed."));
    expect(runsStart).not.toHaveBeenCalled();
    expect(runsDryRun).not.toHaveBeenCalled();
  });

  it("filters run issues and sends guarded cancellation and rollback requests", async () => {
    runsGet.mockResolvedValue(migrationRun());
    runsIssues.mockResolvedValue(
      paged([
        {
          id: "issue-1",
          run: "run-1",
          row_number: 7,
          field_name: "email",
          stage: "validation",
          severity: "error",
          code: "required",
          message: "Email is required",
          redacted_sample: { fields: [{ name: "email", value: null, redacted: true }] },
          created_at: "2026-07-22T00:00:00Z",
        },
      ])
    );
    runsCancel.mockResolvedValue(migrationRun({ cancel_requested_at: "2026-07-22T00:00:11Z" }));
    rollbacksRequest.mockResolvedValue({
      id: "rollback-1",
      run: "run-1",
      status: "queued",
      records_total: 10,
      records_reversed: 0,
      records_failed: 0,
      failure_summary: "",
      started_at: null,
      completed_at: null,
      correlation_id: "corr-rollback-1",
      created_at: "2026-07-22T00:00:11Z",
      updated_at: "2026-07-22T00:00:11Z",
    });
    const user = userEvent.setup();

    renderRoute(
      <MigrationRunDetailPage />,
      "/data-migration/runs/:id",
      "/data-migration/runs/run-1"
    );
    await screen.findByText("Email is required");
    await user.selectOptions(screen.getByLabelText("Severity"), "error");
    await user.type(screen.getByLabelText("Issue code"), "required");
    await user.click(screen.getByRole("button", { name: /Cancel/u }));
    await user.click(screen.getByRole("button", { name: /Rollback/u }));

    await waitFor(() =>
      expect(runsIssues).toHaveBeenLastCalledWith("run-1", {
        page: 1,
        page_size: 25,
        severity: "error",
        stage: undefined,
        code: "required",
      })
    );
    expect(runsCancel).toHaveBeenCalledWith("run-1", { transition_key: "idem-1" });
    expect(rollbacksRequest).toHaveBeenCalledWith("run-1", { idempotency_key: "idem-1" });
    expect(screen.getByRole("link", { name: /Export issues/u })).toHaveAttribute(
      "href",
      "/issues/run-1.csv"
    );
  });
});
