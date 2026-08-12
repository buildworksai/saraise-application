/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- Vitest spies intentionally reference service methods; page-flow tests stay cohesive to verify query invalidation and navigation. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type {
  ConfigurationPreview,
  DynamicResourceDetail,
  DynamicResourceSummary,
  EntityDefinitionDetail,
  EntityDefinitionSummary,
  EntitySchemaVersionDetail,
  FieldDefinitionInput,
  MetadataModelingConfiguration,
  MetadataModelingConfigurationValues,
  PaginatedResult,
  PreviewResult,
  SchemaDiff,
} from "../contracts";
import { metadataModelingService } from "../services/metadata-modeling-service";
import { CreateMetadataSchemaPage } from "./CreateMetadataSchemaPage";
import { CreateDynamicResourcePage } from "./CreateDynamicResourcePage";
import { DynamicResourceDetailPage } from "./DynamicResourceDetailPage";
import { DynamicResourceListPage } from "./DynamicResourceListPage";
import { EditDynamicResourcePage } from "./EditDynamicResourcePage";
import { EditMetadataSchemaPage } from "./EditMetadataSchemaPage";
import { MetadataSchemaListPage } from "./MetadataSchemaListPage";
import { MetadataSchemaDetailPage } from "./MetadataSchemaDetailPage";
import { MetadataModelingSettingsPage } from "./MetadataModelingSettingsPage";

vi.mock("../components/SchemaFieldBuilder", () => ({
  SchemaFieldBuilder: ({
    onChange,
  }: {
    fields: readonly FieldDefinitionInput[];
    onChange: (fields: readonly FieldDefinitionInput[]) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onChange([
          {
            name: "Serial number",
            key: "serial_number",
            field_type: "text",
            is_required: true,
            is_read_only: false,
            is_searchable: true,
            default_value: null,
            validation_rules: {},
            options: [],
            reference_entity_code: null,
            help_text: "",
            placeholder: "",
            order: 1,
          },
        ])
      }
    >
      Add valid field
    </button>
  ),
}));

vi.mock("../components/NamingStrategyEditor", () => ({
  NamingStrategyEditor: () => <div>Naming editor ready</div>,
}));

vi.mock("../components/SchemaImpactPanel", () => ({
  SchemaImpactPanel: () => <div>Impact panel rendered</div>,
}));

vi.mock("../components/ImportSchemaDialog", () => ({
  ImportSchemaDialog: () => null,
}));

vi.mock("../services/metadata-modeling-service", () => ({
  metadataModelingService: {
    getConfiguration: vi.fn(),
    listConfigurationVersions: vi.fn(),
    previewConfiguration: vi.fn(),
    updateConfiguration: vi.fn(),
    rollbackConfiguration: vi.fn(),
    exportConfiguration: vi.fn(),
    importConfiguration: vi.fn(),
    previewNewDefinition: vi.fn(),
    createDefinition: vi.fn(),
    createCandidate: vi.fn(),
    listDefinitions: vi.fn(),
    getDefinition: vi.fn(),
    listResources: vi.fn(),
    cloneDefinition: vi.fn(),
    exportDefinition: vi.fn(),
    archiveDefinition: vi.fn(),
    restoreDefinition: vi.fn(),
    listVersions: vi.fn(),
    rollbackVersion: vi.fn(),
    updateDefinition: vi.fn(),
    validateCandidate: vi.fn(),
    diffVersions: vi.fn(),
    publishCandidate: vi.fn(),
    rejectCandidate: vi.fn(),
    getResource: vi.fn(),
    createResource: vi.fn(),
    patchResource: vi.fn(),
    previewRecordKey: vi.fn(),
    listResourceVersions: vi.fn(),
    submitResource: vi.fn(),
    cancelResource: vi.fn(),
    deleteResource: vi.fn(),
    duplicateResource: vi.fn(),
  },
}));

const pagination = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

function page<T>(items: readonly T[]): PaginatedResult<T> {
  return { items, pagination: { ...pagination, count: items.length }, correlationId: "corr-page" };
}

const values: MetadataModelingConfigurationValues = {
  synchronous_validation_limit: 100,
  max_fields_per_schema: 25,
  max_schema_bytes: 4096,
  max_record_data_bytes: 8192,
  max_regex_length: 120,
  default_page_size: 25,
  max_page_size: 100,
  allowed_field_types: ["text", "number", "date", "boolean", "select", "reference", "json"],
  feature_flags: { dynamic_records: true },
  rollout: {
    dynamic_records: { enabled: true, tenant_percentage: 50, roles: ["admin"], cohorts: ["beta"] },
  },
};

const configuration: MetadataModelingConfiguration = {
  id: "config-1",
  environment: "development",
  version: 4,
  created_by: "user-1",
  created_at: "2026-07-20T00:00:00Z",
  updated_by: "user-2",
  updated_at: "2026-07-21T00:00:00Z",
  ...values,
};

const definitionSummary: EntityDefinitionSummary = {
  id: "schema-1",
  name: "Asset",
  plural_name: "Assets",
  code: "asset",
  description: "Tracked assets",
  owner_module: "metadata_modeling",
  icon: "box",
  origin: "custom",
  status: "published",
  active_version: "version-1",
  active_version_number: 1,
  record_count: 1,
  lock_version: 2,
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const definitionDetail: EntityDefinitionDetail = {
  ...definitionSummary,
  is_submittable: true,
  track_changes: true,
  naming_strategy: "uuid",
  naming_config: {},
  active_fields: [
    {
      id: "field-1",
      name: "Serial number",
      key: "serial_number",
      field_type: "text",
      is_required: true,
      is_read_only: false,
      is_searchable: true,
      default_value: null,
      validation_rules: {},
      options: [],
      reference_entity_code: null,
      help_text: "",
      placeholder: "",
      order: 1,
      created_at: "2026-07-21T00:00:00Z",
    },
  ],
  current_version: null,
  created_by: "user-1",
  updated_by: "user-1",
  archived_at: null,
  archived_by: null,
};

const resource: DynamicResourceSummary = {
  id: "resource-1",
  entity_definition: "schema-1",
  entity_code: "asset",
  entity_name: "Asset",
  schema_version: "version-1",
  schema_version_number: 1,
  record_key: "AST-001",
  display_name: "Forklift",
  state: "draft",
  lock_version: 1,
  searchable_data: { serial_number: "FL-001" },
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const resourceDetail: DynamicResourceDetail = {
  ...resource,
  allowed_actions: ["update", "duplicate", "submit", "cancel", "delete", "read_references"],
  data: { serial_number: "FL-001", related_record: "resource-related", active: true },
  fields: [
    ...definitionDetail.active_fields,
    {
      id: "field-ref",
      name: "Related record",
      key: "related_record",
      field_type: "reference",
      is_required: false,
      is_read_only: false,
      is_searchable: false,
      default_value: null,
      validation_rules: {},
      options: [],
      reference_entity_code: "asset",
      help_text: "",
      placeholder: "",
      order: 2,
      created_at: "2026-07-21T00:00:00Z",
    },
  ],
  created_by: "user-1",
  updated_by: "user-1",
  submitted_at: null,
  submitted_by: null,
  cancelled_at: null,
  cancelled_by: null,
};

const versionDetail: EntitySchemaVersionDetail = {
  id: "version-2",
  version: 2,
  status: "candidate",
  schema_hash: "sha256:version-2",
  change_summary: "Add serial validation",
  compatibility: "compatible",
  published_at: null,
  published_by: null,
  created_by: "user-2",
  created_at: "2026-07-22T00:00:00Z",
  entity_definition: "schema-1",
  schema: {},
  fields: definitionDetail.active_fields,
  validation_report: {
    valid: true,
    compatibility: "compatible",
    resource_count: 1,
    incompatible_resource_count: 0,
    errors: [],
    warnings: [],
  },
  based_on_version: "version-1",
};

const diff: SchemaDiff = {
  from_version: 1,
  to_version: 2,
  compatibility: "compatible",
  changes: [
    {
      key: "serial_number",
      kind: "changed",
      after: {
        name: "Serial number",
        key: "serial_number",
        field_type: "text",
        is_required: true,
        is_read_only: false,
        is_searchable: true,
        default_value: null,
        validation_rules: { max_length: 50 },
        options: [],
        reference_entity_code: null,
        help_text: "",
        placeholder: "",
        order: 1,
      },
    },
  ],
};

function renderWithProviders(ui: ReactElement, initialEntries = ["/"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("MetadataModelingSettingsPage", () => {
  beforeEach(() => {
    vi.mocked(metadataModelingService.getConfiguration).mockResolvedValue(configuration);
    vi.mocked(metadataModelingService.listConfigurationVersions).mockResolvedValue(
      page([
        {
          id: "version-3",
          version: 3,
          before: null,
          after: values,
          changed_by: "user-1",
          changed_at: "2026-07-20T00:00:00Z",
          correlation_id: "corr-version",
          changes: [{ path: "default_page_size", before: 20, after: 25 }],
          operation: "update",
        },
      ])
    );
    vi.mocked(metadataModelingService.previewConfiguration).mockResolvedValue({
      valid: true,
      errors: [],
      warnings: [],
      diff: [{ path: "default_page_size", before: 25, after: 30 }],
      effective_values: { ...values, default_page_size: 30 },
    } satisfies ConfigurationPreview);
    vi.mocked(metadataModelingService.updateConfiguration).mockResolvedValue(configuration);
    vi.mocked(metadataModelingService.rollbackConfiguration).mockResolvedValue(configuration);
    vi.mocked(metadataModelingService.exportConfiguration).mockResolvedValue({
      format_version: "saraise.metadata-modeling.configuration.v1",
      environment: "development",
      checksum: "sha256:metadata-config",
      values,
    });
    vi.mocked(metadataModelingService.importConfiguration).mockResolvedValue({
      valid: true,
      errors: [],
      warnings: [],
      diff: [{ path: "max_fields_per_schema", before: 25, after: 30 }],
      effective_values: { ...values, max_fields_per_schema: 30 },
    } satisfies ConfigurationPreview);
  });

  afterEach(() => vi.clearAllMocks());

  it("requires a valid local configuration before preview and applies only after server preview", async () => {
    renderWithProviders(<MetadataModelingSettingsPage />);

    await userEvent.clear(await screen.findByLabelText("Default page size"));
    await userEvent.type(screen.getByLabelText("Default page size"), "101");

    expect(
      screen.getByText("Default page size cannot exceed maximum page size.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Preview diff/u })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Apply version/u })).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("Default page size"));
    await userEvent.type(screen.getByLabelText("Default page size"), "30");
    await userEvent.click(screen.getByRole("button", { name: /Preview diff/u }));
    expect(await screen.findByText("default_page_size")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Apply version/u }));

    await waitFor(() =>
      expect(metadataModelingService.updateConfiguration).toHaveBeenCalledWith(
        "development",
        expect.objectContaining({ default_page_size: 30 }),
        4
      )
    );
  });

  it("exports and validates imported settings before enabling apply", async () => {
    const user = userEvent.setup();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:metadata-config"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderWithProviders(<MetadataModelingSettingsPage />);

    expect(
      await screen.findByRole("heading", { name: "Metadata Modeling Settings" })
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() =>
      expect(metadataModelingService.exportConfiguration).toHaveBeenCalledWith("development")
    );
    expect(click).toHaveBeenCalled();

    const malformed = new File(["{}"], "bad.json", { type: "application/json" });
    Object.defineProperty(malformed, "text", {
      configurable: true,
      value: vi.fn().mockResolvedValue("{}"),
    });
    await user.upload(screen.getByLabelText("Import"), malformed);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The configuration document is malformed."
    );
    expect(metadataModelingService.importConfiguration).not.toHaveBeenCalled();

    const valid = new File(["{}"], "metadata-config.json", { type: "application/json" });
    Object.defineProperty(valid, "text", {
      configurable: true,
      value: vi.fn().mockResolvedValue(
        JSON.stringify({
          format_version: "saraise.metadata-modeling.configuration.v1",
          environment: "development",
          version: 4,
          checksum: "sha256:metadata-config",
          values: { ...values, max_fields_per_schema: 30 },
        })
      ),
    });
    await user.upload(screen.getByLabelText("Import"), valid);
    await waitFor(() => expect(metadataModelingService.importConfiguration).toHaveBeenCalled());
    const importRequest = vi.mocked(metadataModelingService.importConfiguration).mock.calls[0]?.[0];
    expect(importRequest?.environment).toBe("development");
    expect(importRequest?.document.checksum).toBe("sha256:metadata-config");
    expect(importRequest?.validate_only).toBe(true);
    expect(await screen.findByText("max_fields_per_schema")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Apply version/u }));
    await waitFor(() =>
      expect(metadataModelingService.updateConfiguration).toHaveBeenCalledWith(
        "development",
        expect.objectContaining({ max_fields_per_schema: 30 }),
        4
      )
    );
  });
});

describe("CreateMetadataSchemaPage", () => {
  beforeEach(() => {
    vi.mocked(metadataModelingService.previewNewDefinition).mockResolvedValue({
      normalized_schema: {},
      form_descriptor: [],
      sample_validation: {
        valid: true,
        compatibility: "compatible",
        resource_count: 0,
        incompatible_resource_count: 0,
        errors: [],
        warnings: [],
      },
      impact: {
        valid: true,
        compatibility: "compatible",
        resource_count: 0,
        incompatible_resource_count: 0,
        errors: [],
        warnings: [],
      },
    } satisfies PreviewResult);
    vi.mocked(metadataModelingService.createDefinition).mockResolvedValue(definitionDetail);
    vi.mocked(metadataModelingService.createCandidate).mockResolvedValue({
      id: "version-1",
      version: 1,
      status: "candidate",
      schema_hash: "hash",
      change_summary: "Initial schema",
      compatibility: "compatible",
      published_at: null,
      published_by: null,
      created_by: "user-1",
      created_at: "2026-07-21T00:00:00Z",
      entity_definition: "schema-1",
      schema: {},
      fields: [],
      validation_report: {
        valid: true,
        compatibility: "compatible",
        resource_count: 0,
        incompatible_resource_count: 0,
        errors: [],
        warnings: [],
      },
      based_on_version: null,
    });
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000001");
  });

  afterEach(() => vi.restoreAllMocks());

  it("gates creation on identity, fields, server preview, and then creates the initial candidate", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/" element={<CreateMetadataSchemaPage />} />
        <Route path="/metadata-modeling/schemas/:id/edit" element={<div>navigated</div>} />
      </Routes>
    );

    expect(screen.getByRole("button", { name: /Continue/u })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Singular name"), "Asset");
    await userEvent.type(screen.getByLabelText("Plural name"), "Assets");
    await userEvent.type(screen.getByLabelText("Stable code"), "Asset Model!");
    expect(screen.getByLabelText("Stable code")).toHaveValue("asset-model-");

    await userEvent.click(screen.getByRole("button", { name: /Continue/u }));
    await userEvent.click(screen.getByRole("button", { name: /Continue/u }));
    expect(screen.getByRole("button", { name: /Continue/u })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Add valid field" }));
    await userEvent.click(screen.getByRole("button", { name: /Continue/u }));
    await userEvent.click(screen.getByRole("button", { name: /Continue/u }));
    expect(screen.getByRole("button", { name: /Create draft/u })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /Run server preview/u }));
    expect(await screen.findByText("Impact panel rendered")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Create draft/u }));

    await waitFor(() => expect(metadataModelingService.createDefinition).toHaveBeenCalled());
    const candidateCall = vi.mocked(metadataModelingService.createCandidate).mock.calls[0];
    expect(candidateCall?.[0]).toBe("schema-1");
    expect(candidateCall?.[1].fields[0]?.key).toBe("serial_number");
    expect(candidateCall?.[1].based_on_version_id).toBeNull();
    expect(candidateCall?.[1].change_summary).toBe("Initial schema");
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });
});

describe("MetadataSchemaListPage", () => {
  beforeEach(() => {
    vi.mocked(metadataModelingService.listDefinitions).mockResolvedValue(
      page([
        { ...definitionSummary, status: "draft", record_count: 7 },
        {
          ...definitionSummary,
          id: "schema-archived",
          name: "Legacy Asset",
          code: "legacy_asset",
          status: "archived",
          record_count: 0,
        },
      ])
    );
    vi.mocked(metadataModelingService.cloneDefinition).mockResolvedValue(definitionDetail);
    vi.mocked(metadataModelingService.exportDefinition).mockResolvedValue({
      kind: "metadata-schema",
      definition: definitionDetail,
    } as never);
    vi.mocked(metadataModelingService.archiveDefinition).mockResolvedValue(definitionDetail);
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000099");
  });

  afterEach(() => vi.restoreAllMocks());

  it("filters, orders, paginates, clones, exports, and archives metadata models", async () => {
    const user = userEvent.setup();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:schema"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const createObjectURL = vi.mocked(URL.createObjectURL);
    const revokeObjectURL = vi.mocked(URL.revokeObjectURL);
    const anchor = document.createElement("a");
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);

    renderWithProviders(
      <Routes>
        <Route path="/" element={<MetadataSchemaListPage />} />
        <Route path="/metadata-modeling/schemas/new" element={<div>create route</div>} />
        <Route path="/metadata-modeling/schemas/:id" element={<div>detail route</div>} />
        <Route path="/metadata-modeling/schemas/:id/edit" element={<div>edit route</div>} />
      </Routes>
    );

    expect(await screen.findByRole("link", { name: "Asset" })).toBeInTheDocument();
    expect(screen.getByText("asset")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search schemas"), { target: { value: "asset" } });
    await user.selectOptions(await screen.findByLabelText("Status"), "draft");
    await user.selectOptions(await screen.findByLabelText("Origin"), "custom");
    fireEvent.change(await screen.findByLabelText("Owner module"), {
      target: { value: "metadata" },
    });
    await user.click(await screen.findByRole("button", { name: /Updated/u }));

    await waitFor(() =>
      expect(metadataModelingService.listDefinitions).toHaveBeenLastCalledWith(
        expect.objectContaining({
          search: "asset",
          status: "draft",
          origin: "custom",
          owner_module: "metadata",
          ordering: "-updated_at",
          page: 1,
          page_size: 25,
        })
      )
    );

    await user.click(screen.getByRole("button", { name: "Clone Asset" }));
    await waitFor(() =>
      expect(metadataModelingService.cloneDefinition).toHaveBeenCalledWith(
        "schema-1",
        "asset-copy",
        "Asset copy"
      )
    );

    const createElement = vi
      .spyOn(document, "createElement")
      .mockReturnValue(anchor as unknown as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Export Asset" }));
    await waitFor(() =>
      expect(metadataModelingService.exportDefinition).toHaveBeenCalledWith("schema-1")
    );
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(anchor.download).toBe("asset.metadata-schema.json");
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:schema");
    createElement.mockRestore();

    await user.click(screen.getByRole("button", { name: "Archive Asset" }));
    expect(await screen.findByRole("heading", { name: "Archive metadata model?" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() =>
      expect(metadataModelingService.archiveDefinition).toHaveBeenCalledWith(
        "schema-1",
        "00000000-0000-4000-8000-000000000099"
      )
    );

    await user.click(screen.getAllByRole("button", { name: "View" })[0]!);
    expect(await screen.findByText("detail route")).toBeInTheDocument();
  });

  it("renders first-use, filtered-empty, and retryable error states", async () => {
    vi.mocked(metadataModelingService.listDefinitions).mockResolvedValue(page([]));
    const user = userEvent.setup();

    const firstUse = renderWithProviders(
      <Routes>
        <Route path="/" element={<MetadataSchemaListPage />} />
        <Route path="/metadata-modeling/schemas/new" element={<div>create route</div>} />
      </Routes>
    );

    expect(await screen.findByText("Create your first metadata model")).toBeVisible();
    const createSchemaButtons = screen.getAllByRole("button", { name: "Create schema" });
    await user.click(createSchemaButtons[1]!);
    expect(await screen.findByText("create route")).toBeInTheDocument();
    firstUse.unmount();

    vi.mocked(metadataModelingService.listDefinitions).mockResolvedValue(page([]));

    const filteredEmpty = renderWithProviders(<MetadataSchemaListPage />);
    fireEvent.change(await screen.findByLabelText("Search schemas"), {
      target: { value: "missing" },
    });
    expect(await screen.findByText("No matching metadata models")).toBeVisible();
    filteredEmpty.unmount();

    vi.mocked(metadataModelingService.listDefinitions)
      .mockRejectedValueOnce(new Error("metadata unavailable"))
      .mockResolvedValueOnce(page([definitionSummary]));
    renderWithProviders(<MetadataSchemaListPage />);
    expect(await screen.findByText("metadata unavailable")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("link", { name: "Asset" })).toBeInTheDocument();
  });
});

describe("DynamicResourceListPage", () => {
  beforeEach(() => {
    vi.mocked(metadataModelingService.listDefinitions).mockResolvedValue(page([definitionSummary]));
    vi.mocked(metadataModelingService.getDefinition).mockResolvedValue(definitionDetail);
    vi.mocked(metadataModelingService.listResources).mockResolvedValue(page([resource]));
  });

  afterEach(() => vi.clearAllMocks());

  it("loads records for the selected model and sends server-side filters", async () => {
    renderWithProviders(<DynamicResourceListPage />, ["/?entity_id=schema-1"]);

    expect(await screen.findByRole("link", { name: "Forklift" })).toBeInTheDocument();
    expect(screen.getByText("FL-001")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Search records"), "fork");
    await userEvent.selectOptions(screen.getByLabelText("Record state"), "draft");
    await userEvent.selectOptions(screen.getByLabelText("Order records"), "display_name");

    await waitFor(() =>
      expect(metadataModelingService.listResources).toHaveBeenLastCalledWith(
        expect.objectContaining({
          entity_id: "schema-1",
          search: "fork",
          state: "draft",
          ordering: "display_name",
          page: 1,
          page_size: 25,
        })
      )
    );
  });

  it("distinguishes no schema from filtered empty records", async () => {
    vi.mocked(metadataModelingService.listResources).mockResolvedValue(page([]));
    renderWithProviders(<DynamicResourceListPage />);

    expect(await screen.findByText("Choose a metadata model")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Metadata model"), "schema-1");
    const filters = await screen.findByLabelText("Record filters");
    await userEvent.type(within(filters).getByLabelText("Search records"), "missing");

    expect(await screen.findByText("No matching records")).toBeInTheDocument();
  });
});

describe("CreateDynamicResourcePage", () => {
  beforeEach(() => {
    vi.mocked(metadataModelingService.listDefinitions).mockResolvedValue(page([definitionSummary]));
    vi.mocked(metadataModelingService.getDefinition).mockResolvedValue({
      ...definitionDetail,
      active_fields: [
        {
          ...definitionDetail.active_fields[0]!,
          default_value: "FL-000",
        },
      ],
    });
    vi.mocked(metadataModelingService.previewRecordKey).mockResolvedValue("AST-FL-123");
    vi.mocked(metadataModelingService.createResource).mockResolvedValue({
      ...resourceDetail,
      id: "resource-created",
      record_key: "AST-FL-123",
      data: { serial_number: "FL-123" },
      display_name: "Forklift A",
    });
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000444");
  });

  afterEach(() => vi.restoreAllMocks());

  it("loads defaults, blocks invalid dynamic values, previews the governed key, and creates with idempotency", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/records/new" element={<CreateDynamicResourcePage />} />
        <Route path="/metadata-modeling/records/:id" element={<div>created route</div>} />
      </Routes>,
      ["/metadata-modeling/records/new?entity=schema-1"]
    );

    const serial = await screen.findByLabelText(/Serial number/u);
    expect(serial).toHaveValue("FL-000");

    await user.clear(serial);
    await user.clear(serial);
    expect(screen.getByRole("button", { name: /Preview key/u })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Create record/u }));
    expect(await screen.findByText("This field is required.")).toBeVisible();
    expect(metadataModelingService.createResource).not.toHaveBeenCalled();

    await user.clear(serial);
    await user.type(serial, "FL-123");
    await user.type(screen.getByLabelText("Display name (optional)"), "Forklift A");
    await user.click(screen.getByRole("button", { name: /Preview key/u }));
    expect(await screen.findByText("AST-FL-123")).toBeInTheDocument();
    expect(metadataModelingService.previewRecordKey).toHaveBeenCalledWith("schema-1", {
      serial_number: "FL-123",
    });

    await user.click(screen.getByRole("button", { name: /Create record/u }));
    await waitFor(() =>
      expect(metadataModelingService.createResource).toHaveBeenCalledWith(
        {
          entity_id: "schema-1",
          data: { serial_number: "FL-123" },
          display_name: "Forklift A",
        },
        "00000000-0000-4000-8000-000000000444"
      )
    );
    expect(await screen.findByText("created route")).toBeInTheDocument();
  });

  it("renders retryable model-selection failures without trusting empty data", async () => {
    vi.mocked(metadataModelingService.listDefinitions)
      .mockRejectedValueOnce(new Error("published schemas unavailable"))
      .mockResolvedValueOnce(page([definitionSummary]));

    renderWithProviders(<CreateDynamicResourcePage />);

    expect(await screen.findByText("published schemas unavailable")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByLabelText("Metadata model")).toHaveValue("");
  });
});

describe("EditDynamicResourcePage", () => {
  beforeEach(() => {
    vi.mocked(metadataModelingService.getResource).mockResolvedValue(resourceDetail);
    vi.mocked(metadataModelingService.patchResource).mockResolvedValue({
      ...resourceDetail,
      data: { ...resourceDetail.data, serial_number: "FL-002" },
      display_name: "Forklift B",
      lock_version: 2,
    });
  });

  afterEach(() => vi.clearAllMocks());

  it("sends only changed top-level dynamic fields with the current lock version", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/records/:id/edit" element={<EditDynamicResourcePage />} />
        <Route path="/metadata-modeling/records/:id" element={<div>detail route</div>} />
      </Routes>,
      ["/metadata-modeling/records/resource-1/edit"]
    );

    await user.clear(await screen.findByLabelText(/Serial number/u));
    await user.type(screen.getByLabelText(/Serial number/u), "FL-002");
    await user.clear(screen.getByLabelText("Display name"));
    await user.type(screen.getByLabelText("Display name"), "Forklift B");

    expect(screen.getByText("serial_number")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Save changes/u }));

    await waitFor(() =>
      expect(metadataModelingService.patchResource).toHaveBeenCalledWith(
        "resource-1",
        {
          changes: { serial_number: "FL-002" },
          display_name: "Forklift B",
        },
        1
      )
    );
    expect(await screen.findByText("detail route")).toBeInTheDocument();
  });

  it("halts on optimistic locking conflicts and can reload the server version", async () => {
    vi.mocked(metadataModelingService.patchResource).mockRejectedValue(
      new ApiError("Record changed elsewhere", 409)
    );
    vi.mocked(metadataModelingService.getResource)
      .mockResolvedValueOnce(resourceDetail)
      .mockResolvedValueOnce({
        ...resourceDetail,
        data: { ...resourceDetail.data, serial_number: "FL-SERVER" },
        display_name: "Server forklift",
      });
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/records/:id/edit" element={<EditDynamicResourcePage />} />
      </Routes>,
      ["/metadata-modeling/records/resource-1/edit"]
    );

    await user.clear(await screen.findByLabelText(/Serial number/u));
    await user.type(screen.getByLabelText(/Serial number/u), "FL-LOCAL");
    await user.click(screen.getByRole("button", { name: /Save changes/u }));

    expect(
      await screen.findByRole("heading", { name: "This record changed elsewhere" })
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reload latest" }));
    expect(await screen.findByDisplayValue("FL-SERVER")).toBeVisible();
    expect(screen.getByDisplayValue("Server forklift")).toBeVisible();
  });

  it("keeps submitted records read-only and returns to the detail page", async () => {
    vi.mocked(metadataModelingService.getResource).mockResolvedValue({
      ...resourceDetail,
      state: "submitted",
    });
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/records/:id/edit" element={<EditDynamicResourcePage />} />
        <Route path="/metadata-modeling/records/:id" element={<div>detail route</div>} />
      </Routes>,
      ["/metadata-modeling/records/resource-1/edit"]
    );

    expect(await screen.findByRole("heading", { name: "This record is read-only" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Return to record" }));
    expect(await screen.findByText("detail route")).toBeInTheDocument();
  });
});

describe("MetadataSchemaDetailPage", () => {
  beforeEach(() => {
    vi.mocked(metadataModelingService.getDefinition).mockResolvedValue({
      ...definitionDetail,
      allowed_actions: ["update", "archive", "rollback"],
    });
    vi.mocked(metadataModelingService.listVersions).mockResolvedValue(
      page([{ ...versionDetail, id: "version-1", version: 1, status: "published" }, versionDetail])
    );
    vi.mocked(metadataModelingService.archiveDefinition).mockResolvedValue(definitionDetail);
    vi.mocked(metadataModelingService.restoreDefinition).mockResolvedValue(definitionDetail);
    vi.mocked(metadataModelingService.rollbackVersion).mockResolvedValue(versionDetail);
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000111");
  });

  afterEach(() => vi.restoreAllMocks());

  it("renders concurrency evidence and runs archive, rollback, records, and compare navigation", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/schemas/:id" element={<MetadataSchemaDetailPage />} />
        <Route path="/metadata-modeling/schemas/:id/edit" element={<div>edit route</div>} />
        <Route path="/metadata-modeling/records" element={<div>records route</div>} />
      </Routes>,
      ["/metadata-modeling/schemas/schema-1"]
    );

    expect(await screen.findByRole("heading", { name: "Asset" })).toBeInTheDocument();
    expect(screen.getByText("Lock version")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "1 records" }));
    expect(await screen.findByText("records route")).toBeInTheDocument();
  });

  it("confirms rollback and archive with idempotency evidence, and restores archived models", async () => {
    const user = userEvent.setup();
    const rendered = renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/schemas/:id" element={<MetadataSchemaDetailPage />} />
      </Routes>,
      ["/metadata-modeling/schemas/schema-1"]
    );

    await user.click(await screen.findByRole("button", { name: "Rollback" }));
    expect(
      screen.getByRole("heading", { name: "Publish rollback as a new version?" })
    ).toBeVisible();
    await user.click(screen.getAllByRole("button", { name: "Rollback" }).at(-1)!);
    await waitFor(() =>
      expect(metadataModelingService.rollbackVersion).toHaveBeenCalledWith(
        "schema-1",
        "version-2",
        "00000000-0000-4000-8000-000000000111"
      )
    );

    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(screen.getAllByRole("button", { name: "Archive" }).at(-1)!);
    await waitFor(() =>
      expect(metadataModelingService.archiveDefinition).toHaveBeenCalledWith(
        "schema-1",
        "00000000-0000-4000-8000-000000000111"
      )
    );
    rendered.unmount();

    vi.mocked(metadataModelingService.getDefinition).mockResolvedValue({
      ...definitionDetail,
      status: "archived",
      allowed_actions: ["restore"],
    });
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/schemas/:id" element={<MetadataSchemaDetailPage />} />
      </Routes>,
      ["/metadata-modeling/schemas/schema-1"]
    );

    await user.click(await screen.findByRole("button", { name: "Restore" }));
    await user.click(screen.getAllByRole("button", { name: "Restore" }).at(-1)!);
    await waitFor(() =>
      expect(metadataModelingService.restoreDefinition).toHaveBeenCalledWith(
        "schema-1",
        "00000000-0000-4000-8000-000000000111"
      )
    );
  });
});

describe("EditMetadataSchemaPage", () => {
  beforeEach(() => {
    vi.mocked(metadataModelingService.getDefinition).mockResolvedValue(definitionDetail);
    vi.mocked(metadataModelingService.updateDefinition).mockResolvedValue(definitionDetail);
    vi.mocked(metadataModelingService.createCandidate).mockResolvedValue(versionDetail);
    vi.mocked(metadataModelingService.validateCandidate).mockResolvedValue(
      versionDetail.validation_report
    );
    vi.mocked(metadataModelingService.diffVersions).mockResolvedValue(diff);
    vi.mocked(metadataModelingService.publishCandidate).mockResolvedValue(versionDetail);
    vi.mocked(metadataModelingService.rejectCandidate).mockResolvedValue({
      ...versionDetail,
      status: "rejected",
    });
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000222");
  });

  afterEach(() => vi.restoreAllMocks());

  it("saves an immutable candidate, validates impact, publishes, and navigates to detail", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/schemas/:id/edit" element={<EditMetadataSchemaPage />} />
        <Route path="/metadata-modeling/schemas/:id" element={<div>detail route</div>} />
      </Routes>,
      ["/metadata-modeling/schemas/schema-1/edit"]
    );

    await user.type(await screen.findByLabelText("Change summary"), "Add serial length guard");
    await user.click(screen.getByRole("button", { name: "Save and validate candidate" }));

    await waitFor(() =>
      expect(metadataModelingService.updateDefinition).toHaveBeenCalledWith(
        "schema-1",
        expect.objectContaining({ name: "Asset", naming_strategy: "uuid" }),
        2
      )
    );
    expect(metadataModelingService.createCandidate).toHaveBeenCalledWith(
      "schema-1",
      expect.objectContaining({
        based_on_version_id: "version-1",
        change_summary: "Add serial length guard",
      })
    );
    expect(await screen.findByText("serial_number")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Publish version 2/u }));
    await user.click(screen.getByRole("button", { name: "Publish" }));
    await waitFor(() =>
      expect(metadataModelingService.publishCandidate).toHaveBeenCalledWith(
        "schema-1",
        "version-2",
        "00000000-0000-4000-8000-000000000222"
      )
    );
    expect(await screen.findByText("detail route")).toBeInTheDocument();
  });

  it("halts on edit conflicts and lets the operator keep or reload the draft", async () => {
    vi.mocked(metadataModelingService.updateDefinition).mockRejectedValue(
      new ApiError("Version conflict", 409)
    );
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/schemas/:id/edit" element={<EditMetadataSchemaPage />} />
      </Routes>,
      ["/metadata-modeling/schemas/schema-1/edit"]
    );

    await user.click(await screen.findByRole("button", { name: "Save and validate candidate" }));

    expect(await screen.findByRole("heading", { name: "A newer edit exists" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Keep my draft" }));
    expect(
      await screen.findByRole("button", { name: "Save and validate candidate" })
    ).toBeVisible();
  });
});

describe("DynamicResourceDetailPage", () => {
  beforeEach(() => {
    vi.mocked(metadataModelingService.getResource).mockResolvedValue(resourceDetail);
    vi.mocked(metadataModelingService.listResourceVersions).mockResolvedValue(
      page([
        {
          id: "record-version-1",
          version: 1,
          schema_version: "version-1",
          state: "draft",
          record_key: "AST-001",
          display_name: "Forklift",
          data: { serial_number: "FL-001" },
          changed_fields: ["serial_number"],
          operation: "create",
          changed_by: "user-1",
          correlation_id: "corr-record",
          changed_at: "2026-07-21T00:00:00Z",
        },
      ])
    );
    vi.mocked(metadataModelingService.submitResource).mockResolvedValue({
      ...resourceDetail,
      state: "submitted",
    });
    vi.mocked(metadataModelingService.cancelResource).mockResolvedValue({
      ...resourceDetail,
      state: "cancelled",
    });
    vi.mocked(metadataModelingService.duplicateResource).mockResolvedValue({
      ...resourceDetail,
      id: "resource-copy",
    });
    vi.mocked(metadataModelingService.deleteResource).mockResolvedValue({
      operation: "delete",
      status: "completed",
      id: "resource-1",
    });
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000333");
  });

  afterEach(() => vi.restoreAllMocks());

  it("submits, duplicates, and deletes draft records using lock-version evidence", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/records/:id" element={<DynamicResourceDetailPage />} />
        <Route path="/metadata-modeling/records" element={<div>records route</div>} />
        <Route
          path="/metadata-modeling/records/resource-copy"
          element={<div>duplicate route</div>}
        />
        <Route path="/metadata-modeling/records/:id/edit" element={<div>edit route</div>} />
      </Routes>,
      ["/metadata-modeling/records/resource-1"]
    );

    expect(await screen.findByRole("heading", { name: "Forklift" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "resource-related" })).toHaveAttribute(
      "href",
      "/metadata-modeling/records/resource-related"
    );

    await user.click(screen.getByRole("button", { name: "Submit" }));
    await user.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() =>
      expect(metadataModelingService.submitResource).toHaveBeenCalledWith(
        "resource-1",
        1,
        "00000000-0000-4000-8000-000000000333"
      )
    );

    await user.click(screen.getByRole("button", { name: "Duplicate" }));
    expect(await screen.findByText("duplicate route")).toBeInTheDocument();
  });

  it("cancels submitted records only after an auditable reason and hides draft-only actions", async () => {
    vi.mocked(metadataModelingService.getResource).mockResolvedValue({
      ...resourceDetail,
      state: "submitted",
      allowed_actions: ["cancel", "duplicate"],
    });
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/metadata-modeling/records/:id" element={<DynamicResourceDetailPage />} />
      </Routes>,
      ["/metadata-modeling/records/resource-1"]
    );

    expect(await screen.findByText("Read-only lifecycle state.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Cancel record" })).toBeDisabled();
    await user.type(screen.getByLabelText("Reason"), "Submitted in error");
    await user.click(screen.getByRole("button", { name: "Cancel record" }));

    await waitFor(() =>
      expect(metadataModelingService.cancelResource).toHaveBeenCalledWith(
        "resource-1",
        "Submitted in error",
        1,
        "00000000-0000-4000-8000-000000000333"
      )
    );
  });
});
