/* eslint-disable max-lines-per-function -- mutation-focused page-family tests keep the governed setup and assertions local. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import { GovernedError } from "../components/CustomizationUI";
import { FieldDefinitionListPage } from "../pages/FieldDefinitionListPage";
import { FormListPage } from "../pages/FormListPage";
import { RuleExecutionListPage } from "../pages/RuleExecutionListPage";
import { RuleListPage } from "../pages/RuleListPage";
import { CreateFieldDefinitionPage } from "../pages/CreateFieldDefinitionPage";
import { CreateFormPage } from "../pages/CreateFormPage";
import { CreateRulePage } from "../pages/CreateRulePage";
import { EditFormPage } from "../pages/EditFormPage";
import { EditFieldDefinitionPage } from "../pages/EditFieldDefinitionPage";
import { EditRulePage } from "../pages/EditRulePage";
import { FieldDefinitionDetailPage } from "../pages/FieldDefinitionDetailPage";
import { FormDetailPage } from "../pages/FormDetailPage";
import { FieldImpactPage } from "../pages/ImpactPage";
import { RuleDetailPage } from "../pages/RuleDetailPage";
import { RuntimeConfigurationPage } from "../pages/RuntimeConfigurationPage";
import {
  CreateFieldValuePage,
  EditFieldValuePage,
  FieldValueDetailPage,
  FieldValueListPage,
} from "../pages/FieldValuePages";
import { jsonErrorMessage } from "../components/customization-utils";
import { customizationFrameworkService as service } from "../services/customization-framework-service";
import type { RuntimeConfiguration } from "../contracts";

vi.mock("../services/customization-framework-service", () => ({
  customizationFrameworkService: {
    getConfiguration: vi.fn(),
    listFields: vi.fn(),
    listForms: vi.fn(),
    listRules: vi.fn(),
    listExecutions: vi.fn(),
    listValues: vi.fn(),
    listResourceContracts: vi.fn(),
    getField: vi.fn(),
    createField: vi.fn(),
    transitionField: vi.fn(),
    rollbackField: vi.fn(),
    getFieldImpact: vi.fn(),
    listFieldVersions: vi.fn(),
    getForm: vi.fn(),
    createForm: vi.fn(),
    listFormLayouts: vi.fn(),
    createFormLayout: vi.fn(),
    publishForm: vi.fn(),
    archiveForm: vi.fn(),
    getRenderSchema: vi.fn(),
    getRule: vi.fn(),
    createRule: vi.fn(),
    transitionRule: vi.fn(),
    getRuleImpact: vi.fn(),
    listRuleVersions: vi.fn(),
    createRuleVersion: vi.fn(),
    publishRule: vi.fn(),
    evaluateRule: vi.fn(),
    listConfigurationVersions: vi.fn(),
    listConfigurationAudit: vi.fn(),
    previewConfiguration: vi.fn(),
    updateConfiguration: vi.fn(),
    importConfiguration: vi.fn(),
    exportConfiguration: vi.fn(),
    rollbackConfiguration: vi.fn(),
    getValue: vi.fn(),
    createValue: vi.fn(),
    updateValue: vi.fn(),
    deleteValue: vi.fn(),
    updateField: vi.fn(),
  },
}));
const meta = {
  correlation_id: "00000000-0000-4000-8000-000000000099",
  timestamp: "2026-07-22T00:00:00Z",
  pagination: {
    count: 0,
    page: 1,
    page_size: 25,
    total_pages: 0,
    has_next: false,
    has_previous: false,
  },
} as const;
const runtimeConfiguration = {
  id: "00000000-0000-4000-8000-000000000010",
  tenant_id: "00000000-0000-4000-8000-000000000011",
  version: 1,
  environment: "test",
  document: {
    limits: {
      json_bytes: 65536,
      ast_nodes: 256,
      ast_depth: 16,
      evaluation_ms: 50,
      field_key_length: 100,
      field_label_length: 160,
      resource_key_length: 120,
      contract_version_length: 32,
      form_key_length: 100,
      form_name_length: 160,
      change_summary_length: 500,
      idempotency_key_length: 128,
      rule_priority_min: 1,
      rule_priority_max: 1000,
    },
    policies: {
      slug_pattern: "^[a-z][a-z0-9-]*$",
      field_types: ["text"],
      rule_triggers: ["validate"],
      condition_operators: ["eq"],
      action_types: ["reject-with-message"],
      value_sources: ["ui"],
      value_allowed_statuses: ["active"],
      field_delete_statuses: ["draft"],
      form_delete_statuses: ["draft"],
      field_transitions: {},
      form_transitions: {},
      rule_transitions: {},
    },
    defaults: {
      field_required: false,
      field_searchable: false,
      field_status: "draft",
      form_status: "draft",
      layout_schema_version: 1,
      layout_status: "candidate",
      form_surface: "default",
      form_layout: { schema_version: 1, sections: [] },
      rule_priority: 100,
      rule_stop_on_match: false,
      rule_status: "draft",
      rule_language_version: 1,
      rule_version_status: "candidate",
      contract_version: "1.0",
    },
    list_preferences: {
      page_size: 25,
      field_ordering: "key",
      form_ordering: "key",
      rule_ordering: "priority",
      execution_ordering: "-executed_at",
    },
    navigation: {
      fields_order: 70,
      field_values_order: 71,
      forms_order: 72,
      rules_order: 73,
      executions_order: 74,
      configuration_order: 75,
    },
    rollout: { enabled: true, roles: [], cohorts: [] },
    rbac: { action_access: {}, sod_actions: [] },
  },
  updated_by: "00000000-0000-4000-8000-000000000012",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
} as const satisfies RuntimeConfiguration;
const fieldValue = {
  id: "00000000-0000-4000-8000-000000000030",
  tenant_id: "00000000-0000-4000-8000-000000000011",
  definition_id: "00000000-0000-4000-8000-000000000020",
  definition_key: "customer-tier",
  target_record_id: "00000000-0000-4000-8000-000000000040",
  value: "gold",
  definition_revision: 3,
  source: "ui",
  created_by: "00000000-0000-4000-8000-000000000012",
  updated_by: "00000000-0000-4000-8000-000000000012",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
  deleted_at: null,
  deleted_by: null,
  lock_version: 1,
} as const;
const fieldDefinition = {
  id: "00000000-0000-4000-8000-000000000020",
  tenant_id: "00000000-0000-4000-8000-000000000011",
  key: "customer-tier",
  label: "Customer tier",
  description: "Lifecycle tier",
  owner_module: "crm",
  target_resource: "customer",
  target_contract_version: "1.0",
  data_type: "text",
  required: false,
  searchable: true,
  default_value: null,
  validation_schema: {},
  presentation_schema: {},
  status: "active",
  activated_at: "2026-07-22T00:00:00Z",
  deprecated_at: null,
  retired_at: null,
  transition_history: [],
  created_by: "00000000-0000-4000-8000-000000000012",
  updated_by: "00000000-0000-4000-8000-000000000012",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
  deleted_at: null,
  deleted_by: null,
  lock_version: 1,
} as const;
const resourceContract = {
  module: "crm",
  resource: "lead",
  version: "1.0",
  available: true,
  display_name: "CRM lead",
  capability_state: "available",
  custom_field_types: ["text"],
  form_surfaces: ["default"],
  rule_triggers: ["validate"],
  entitlement_keys: [],
  discovery: {},
  fields: {
    last_name: {
      label: "Last name",
      width: 6,
      accessibility_label: "Lead last name",
    },
    ignored: {
      label: "Ignored",
    },
  },
} as const;
const formDefinition = {
  id: "00000000-0000-4000-8000-000000000050",
  tenant_id: "00000000-0000-4000-8000-000000000011",
  key: "lead-intake",
  name: "Lead intake",
  description: "Lead intake form",
  owner_module: "crm",
  target_resource: "lead",
  target_contract_version: "1.0",
  surface: "default",
  status: "draft",
  published_version: null,
  published_layout_version_id: null,
  published_at: null,
  published_by: null,
  archived_at: null,
  transition_history: [],
  capability_state: "available",
  created_by: "00000000-0000-4000-8000-000000000012",
  updated_by: "00000000-0000-4000-8000-000000000012",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  deleted_at: null,
  deleted_by: null,
  lock_version: 4,
} as const;
const formLayout = {
  schema_version: 1,
  sections: [
    {
      id: "section-1",
      title: "Lead",
      components: [],
    },
  ],
} as const;
const ruleDefinition = {
  id: "00000000-0000-4000-8000-000000000060",
  tenant_id: "00000000-0000-4000-8000-000000000011",
  key: "require-contact",
  name: "Require contact",
  description: "Reject uncontactable records",
  owner_module: "crm",
  target_resource: "lead",
  target_contract_version: "1.0",
  trigger: "validate",
  priority: 100,
  stop_on_match: false,
  status: "draft",
  published_version: null,
  published_version_id: null,
  published_at: null,
  published_by: null,
  transition_history: [],
  capability_state: "available",
  created_by: "00000000-0000-4000-8000-000000000012",
  updated_by: "00000000-0000-4000-8000-000000000012",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  deleted_at: null,
  deleted_by: null,
  lock_version: 2,
} as const;
const versionMeta = {
  id: "00000000-0000-4000-8000-000000000070",
  tenant_id: "00000000-0000-4000-8000-000000000011",
  definition_id: "00000000-0000-4000-8000-000000000020",
  document: {},
  actor_id: "00000000-0000-4000-8000-000000000012",
  form: "00000000-0000-4000-8000-000000000050",
  version: 2,
  schema_version: 1,
  layout: formLayout,
  change_summary: "Initial candidate version.",
  validation_errors: [],
  rule: "00000000-0000-4000-8000-000000000060",
  language_version: 1,
  condition_ast: { operator: "eq", field: "score", value: 70 },
  action_ast: [],
  dependencies: [],
  status: "candidate",
  content_hash: "sha256:version",
  correlation_id: "00000000-0000-4000-8000-000000000098",
  created_by: "00000000-0000-4000-8000-000000000012",
  created_at: "2026-07-22T00:00:00Z",
  published_at: null,
  published_by: null,
} as const;
function LocationSearchProbe() {
  const location = useLocation();
  return (
    <>
      <output aria-label="location-pathname">{location.pathname}</output>
      <output aria-label="location-search">{location.search}</output>
    </>
  );
}

function renderPage(page: React.ReactElement, initial = "/", client?: QueryClient) {
  const queryClient = client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initial]}>
        {page}
        <LocationSearchProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderRoutedPage(
  path: string,
  routePath: string,
  page: React.ReactElement,
  client?: QueryClient
) {
  const queryClient = client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={page} />
          <Route path="*" element={null} />
        </Routes>
        <LocationSearchProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("customization page families", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(service.getConfiguration).mockResolvedValue(runtimeConfiguration);
    vi.mocked(service.listFields).mockResolvedValue({ data: [], meta });
    vi.mocked(service.listForms).mockResolvedValue({ data: [], meta });
    vi.mocked(service.listRules).mockResolvedValue({ data: [], meta });
    vi.mocked(service.listExecutions).mockResolvedValue({ data: [], meta });
    vi.mocked(service.listValues).mockResolvedValue({ data: [], meta });
  });

  it.each([
    ["fields", <FieldDefinitionListPage />, "No fields yet"],
    ["forms", <FormListPage />, "No forms yet"],
    ["rules", <RuleListPage />, "No rules yet"],
    ["executions", <RuleExecutionListPage />, "No executions yet"],
  ])("renders distinct empty state for %s", async (_name, page, heading) => {
    renderPage(page);
    expect(await screen.findByText(heading)).toBeInTheDocument();
  });

  it("renders a distinct zero-results state from URL-backed server filters", async () => {
    renderPage(<FieldDefinitionListPage />, "/?search=missing");
    expect(await screen.findByText("No fields match")).toBeInTheDocument();
    expect(service.listFields).toHaveBeenCalledWith(expect.objectContaining({ search: "missing" }));
  });

  it("creates a governed field definition only after contract and tenant policy validation pass", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listResourceContracts).mockResolvedValue({ data: [resourceContract], meta });
    vi.mocked(service.createField).mockResolvedValue({
      data: { ...fieldDefinition, id: "00000000-0000-4000-8000-000000000021" },
      meta,
    });
    renderRoutedPage(
      "/customization-framework/fields/new",
      "/customization-framework/fields/new",
      <CreateFieldDefinitionPage />
    );

    expect(await screen.findByRole("heading", { name: "Create custom field" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Complete every field using the tenant policy and selected contract."
    );

    await user.click(screen.getByRole("button", { name: /Target/u }));
    await user.selectOptions(screen.getByLabelText("Registered target contract"), "crm/lead@1.0");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.change(screen.getByLabelText(/^Label/u), { target: { value: "Lead priority" } });
    expect(screen.getByLabelText(/^Stable key/u)).toHaveValue("lead-priority");
    fireEvent.change(screen.getByLabelText("Validation schema"), {
      target: { value: '{"maxLength":80}' },
    });
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Review contract")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create field" }));

    expect(service.createField).toHaveBeenCalledWith({
      key: "lead-priority",
      label: "Lead priority",
      description: "",
      owner_module: "crm",
      target_resource: "lead",
      target_contract_version: "1.0",
      data_type: "text",
      required: false,
      searchable: false,
      validation_schema: { maxLength: 80 },
      presentation_schema: { label: "Lead priority" },
    });
    expect(await screen.findByLabelText("location-pathname")).toHaveTextContent(
      "/customization-framework/fields/00000000-0000-4000-8000-000000000021"
    );
  });

  it("keeps invalid field-definition JSON local and never calls create", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listResourceContracts).mockResolvedValue({ data: [resourceContract], meta });
    renderRoutedPage(
      "/customization-framework/fields/new",
      "/customization-framework/fields/new",
      <CreateFieldDefinitionPage />
    );

    await user.selectOptions(
      await screen.findByLabelText("Registered target contract"),
      "crm/lead@1.0"
    );
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(screen.getByLabelText(/^Label/u), "Lead priority");
    fireEvent.change(screen.getByLabelText("Validation schema"), { target: { value: "{" } });
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Expected property name");
    expect(service.createField).not.toHaveBeenCalled();
  });

  it("previews runtime configuration before saving exact versioned payloads", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listConfigurationVersions).mockResolvedValue({ data: [], meta });
    vi.mocked(service.listConfigurationAudit).mockResolvedValue({ data: [], meta });
    vi.mocked(service.previewConfiguration).mockResolvedValue({
      valid: true,
      document: runtimeConfiguration.document,
      changes: { rollout: "changed" },
      requires_restart: false,
    });
    vi.mocked(service.updateConfiguration).mockResolvedValue({
      ...runtimeConfiguration,
      version: 2,
      environment: "staging",
    });
    renderRoutedPage(
      "/customization-framework/configuration",
      "/customization-framework/configuration",
      <RuntimeConfigurationPage />
    );

    expect(
      await screen.findByRole("heading", { name: "Customization configuration" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply configuration" })).toBeDisabled();
    await user.clear(screen.getByLabelText("Environment"));
    await user.type(screen.getByLabelText("Environment"), "staging");
    await user.click(screen.getByRole("button", { name: "Preview changes" }));

    await waitFor(() => expect(service.previewConfiguration).toHaveBeenCalled());
    const previewRequest = vi.mocked(service.previewConfiguration).mock.calls[0]?.[0];
    expect(previewRequest?.document.limits).toEqual(expect.any(Object));
    expect(previewRequest?.document.rollout).toEqual({ enabled: true, roles: [], cohorts: [] });
    await user.click(screen.getByRole("button", { name: "Apply configuration" }));
    const updateRequest = vi.mocked(service.updateConfiguration).mock.calls[0]?.[0];
    expect(updateRequest?.environment).toBe("staging");
    expect(updateRequest?.expected_version).toBe(1);
    expect(updateRequest?.document.defaults).toEqual(expect.any(Object));
  });

  it("imports, exports, and rolls back runtime configuration with version evidence", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listConfigurationVersions).mockResolvedValue({
      data: [
        {
          id: "00000000-0000-4000-8000-000000000090",
          version: 0,
          environment: "test",
          document: runtimeConfiguration.document,
          actor_id: runtimeConfiguration.updated_by,
          correlation_id: "corr-customization-v1",
          created_at: "2026-07-22T00:00:00Z",
        },
      ],
      meta,
    });
    vi.mocked(service.listConfigurationAudit).mockResolvedValue({
      data: [
        {
          id: "00000000-0000-4000-8000-000000000091",
          version: 1,
          action: "update",
          before: null,
          after: runtimeConfiguration.document,
          actor_id: runtimeConfiguration.updated_by,
          correlation_id: "corr-customization-audit",
          created_at: "2026-07-22T00:00:00Z",
        },
      ],
      meta,
    });
    vi.mocked(service.previewConfiguration).mockResolvedValue({
      valid: true,
      document: runtimeConfiguration.document,
      changes: { import: "validated" },
      requires_restart: true,
    });
    vi.mocked(service.importConfiguration).mockResolvedValue({
      ...runtimeConfiguration,
      version: 2,
    });
    vi.mocked(service.exportConfiguration).mockResolvedValue({
      schema: "saraise.customization.configuration.v1",
      tenant_id: runtimeConfiguration.tenant_id,
      version: 1,
      environment: "test",
      document: runtimeConfiguration.document,
    });
    vi.mocked(service.rollbackConfiguration).mockResolvedValue({
      ...runtimeConfiguration,
      version: 3,
    });
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:customization-config"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const rendered = renderRoutedPage(
      "/customization-framework/configuration",
      "/customization-framework/configuration",
      <RuntimeConfigurationPage />
    );

    expect(await screen.findByText("Version 0 · test")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(service.exportConfiguration).toHaveBeenCalled());
    expect(clickSpy).toHaveBeenCalled();

    const file = new File(["{}"], "customization-config.json", { type: "application/json" });
    Object.defineProperty(file, "text", {
      configurable: true,
      value: vi.fn().mockResolvedValue(
        JSON.stringify({
          schema: "saraise.customization.configuration.v1",
          tenant_id: runtimeConfiguration.tenant_id,
          version: 1,
          environment: "production",
          document: runtimeConfiguration.document,
        })
      ),
    });
    const fileInput = rendered.container.querySelector('input[type="file"]');
    expect(fileInput).toBeInstanceOf(HTMLInputElement);
    await user.upload(fileInput as HTMLInputElement, file);
    await user.click(screen.getByRole("button", { name: "Preview changes" }));
    expect(await screen.findByText("Applying this change requires a restart.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Import configuration" }));
    await waitFor(() => expect(service.importConfiguration).toHaveBeenCalled());
    const importRequest = vi.mocked(service.importConfiguration).mock.calls[0]?.[0];
    expect(importRequest?.payload.environment).toBe("production");
    expect(importRequest?.expected_version).toBe(1);

    await user.click(screen.getByRole("button", { name: "Rollback" }));
    expect(screen.getByRole("heading", { name: "Rollback to version 0?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create rollback version" }));
    await waitFor(() =>
      expect(service.rollbackConfiguration).toHaveBeenCalledWith({
        target_version: 0,
        expected_version: 1,
      })
    );
  });

  it("renders blocking impact evidence and unavailable capability warnings", async () => {
    vi.mocked(service.getFieldImpact).mockResolvedValue({
      data: {
        entity_type: "field",
        entity_id: fieldDefinition.id,
        dependency_count: 2,
        blocking: true,
        blocking_count: 1,
        capability_unavailable: true,
        forms: [{ version_id: "form-version-1", status: "published" }],
        rules: [{ version_id: "rule-version-1", status: "candidate" }],
        field_references: ["customer-tier"],
      },
      meta,
    });
    renderRoutedPage(
      `/customization-framework/fields/${fieldDefinition.id}/impact`,
      "/customization-framework/fields/:id/impact",
      <FieldImpactPage />
    );

    expect(
      await screen.findByRole("heading", { name: "Field dependency impact" })
    ).toBeInTheDocument();
    expect(screen.getByText("Resolve blocking dependencies first")).toBeInTheDocument();
    expect(screen.getByText(/referenced module is unavailable/u)).toBeInTheDocument();
    expect(screen.getByText("form-version-1")).toBeInTheDocument();
    expect(screen.getByText("rule-version-1")).toBeInTheDocument();
    expect(screen.getByText("customer-tier")).toBeInTheDocument();
  });

  it("creates form and rule wrappers only after target contract and policy validation", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listResourceContracts).mockResolvedValue({ data: [resourceContract], meta });
    vi.mocked(service.createForm).mockResolvedValue({
      data: { ...formDefinition, id: "00000000-0000-4000-8000-000000000051" },
      meta,
    });
    vi.mocked(service.createRule).mockResolvedValue({
      data: { ...ruleDefinition, id: "00000000-0000-4000-8000-000000000061" },
      meta,
    });

    const formClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderRoutedPage(
      "/customization-framework/forms/new",
      "/customization-framework/forms/new",
      <CreateFormPage />,
      formClient
    );
    await screen.findByRole("button", { name: "Create and design" });
    await user.selectOptions(screen.getByLabelText("Registered target contract"), "crm/lead@1.0");
    await user.type(screen.getByLabelText("Name"), "Lead Intake");
    fireEvent.change(screen.getByLabelText("Stable key"), { target: { value: "Invalid Key" } });
    const formSubmit = screen.getByRole("button", { name: "Create and design" }).closest("form");
    expect(formSubmit).not.toBeNull();
    fireEvent.submit(formSubmit!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Name, governed key, module, resource, and contract version are required."
    );
    expect(service.createForm).not.toHaveBeenCalled();

    cleanup();
    const validFormClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderRoutedPage(
      "/customization-framework/forms/new",
      "/customization-framework/forms/new",
      <CreateFormPage />,
      validFormClient
    );
    await user.selectOptions(
      await screen.findByLabelText("Registered target contract"),
      "crm/lead@1.0"
    );
    await user.type(screen.getByLabelText("Name"), "Lead Intake");
    fireEvent.change(screen.getByLabelText("Stable key"), { target: { value: "lead-intake" } });
    await user.type(screen.getByLabelText("Description"), "Configurable intake form");
    await user.click(screen.getByRole("button", { name: "Create and design" }));
    await waitFor(() =>
      expect(service.createForm).toHaveBeenCalledWith({
        key: "lead-intake",
        name: "Lead Intake",
        description: "Configurable intake form",
        owner_module: "crm",
        target_resource: "lead",
        target_contract_version: "1.0",
      })
    );

    cleanup();
    const ruleClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderRoutedPage(
      "/customization-framework/rules/new",
      "/customization-framework/rules/new",
      <CreateRulePage />,
      ruleClient
    );
    await user.selectOptions(
      await screen.findByLabelText("Registered target contract"),
      "crm/lead@1.0"
    );
    await user.type(screen.getByLabelText("Name"), "Require contact");
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "1001" } });
    const ruleSubmit = screen.getByRole("button", { name: "Create and build" }).closest("form");
    expect(ruleSubmit).not.toBeNull();
    fireEvent.submit(ruleSubmit!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Complete every field within the configured rule policy."
    );

    cleanup();
    const validRuleClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderRoutedPage(
      "/customization-framework/rules/new",
      "/customization-framework/rules/new",
      <CreateRulePage />,
      validRuleClient
    );
    await user.selectOptions(
      await screen.findByLabelText("Registered target contract"),
      "crm/lead@1.0"
    );
    await user.type(screen.getByLabelText("Name"), "Require contact");
    fireEvent.change(screen.getByLabelText("Stable key"), { target: { value: "require-contact" } });
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "25" } });
    await user.click(screen.getByRole("button", { name: "Create and build" }));
    await waitFor(() =>
      expect(service.createRule).toHaveBeenCalledWith({
        key: "require-contact",
        name: "Require contact",
        description: "",
        owner_module: "crm",
        target_resource: "lead",
        target_contract_version: "1.0",
        trigger: "validate",
        priority: 25,
        stop_on_match: false,
      })
    );
  });

  it("updates field revisions locally validates JSON before optimistic writes", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getField).mockResolvedValue({ data: fieldDefinition, meta });
    vi.mocked(service.updateField).mockResolvedValue({
      data: { ...fieldDefinition, label: "Customer tier label" },
      meta,
    });
    renderRoutedPage(
      `/customization-framework/fields/${fieldDefinition.id}/edit`,
      "/customization-framework/fields/:id/edit",
      <EditFieldDefinitionPage />
    );

    expect(await screen.findByRole("heading", { name: "Edit Customer tier" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Validation schema"), { target: { value: "{" } });
    await user.click(screen.getByRole("button", { name: "Save revision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Expected property name");
    expect(service.updateField).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Label"));
    await user.type(screen.getByLabelText("Label"), "Customer tier label");
    fireEvent.change(screen.getByLabelText("Validation schema"), {
      target: { value: '{"maxLength":120}' },
    });
    await user.click(screen.getByRole("button", { name: "Save revision" }));
    expect(service.updateField).toHaveBeenCalledWith(fieldDefinition.id, {
      label: "Customer tier label",
      description: fieldDefinition.description,
      validation_schema: { maxLength: 120 },
      expected_lock_version: fieldDefinition.lock_version,
    });
  });

  it("renders form and rule detail lifecycle commands with audited transition keys", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "customization-command-key") });
    vi.mocked(service.getForm).mockResolvedValue({
      data: { ...formDefinition, status: "published", published_version: 2 },
      meta,
    });
    vi.mocked(service.listFormLayouts).mockResolvedValue({
      data: [{ ...versionMeta, id: "layout-v2", status: "published", layout: formLayout }],
      meta,
    });
    vi.mocked(service.getRenderSchema).mockResolvedValue({
      data: {
        form_id: formDefinition.id,
        form_key: formDefinition.key,
        version: 2,
        contract_version: "2026-08-01",
        layout: formLayout,
        fields: [],
        content_hash: "sha256:published-render-contract",
      },
      meta,
    });
    vi.mocked(service.archiveForm).mockResolvedValue({
      data: { ...formDefinition, status: "archived" },
      meta,
    });
    renderRoutedPage(
      `/customization-framework/forms/${formDefinition.id}`,
      "/customization-framework/forms/:id",
      <FormDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "Lead intake" })).toBeInTheDocument();
    expect(await screen.findByText(/1 sections/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(screen.getByRole("button", { name: "Archive form" }));
    expect(service.archiveForm).toHaveBeenCalledWith(formDefinition.id, {
      transition_key: "customization-command-key",
    });

    cleanup();
    vi.mocked(service.getRule).mockResolvedValue({
      data: {
        ...ruleDefinition,
        status: "published",
        published_version: 2,
        execution_count: 9,
        diagnostic_count: 3,
      },
      meta,
    });
    vi.mocked(service.listRuleVersions).mockResolvedValue({
      data: [
        {
          ...versionMeta,
          id: "rule-v2",
          status: "published",
          condition_ast: { operator: "gte", field: "score", value: 70 },
          action_ast: [{ type: "reject-with-message", field: "email", message: "Email required" }],
        },
      ],
      meta,
    });
    vi.mocked(service.getRuleImpact).mockResolvedValue({
      data: {
        entity_type: "rule",
        entity_id: ruleDefinition.id,
        dependency_count: 4,
        blocking: true,
        blocking_count: 1,
        capability_unavailable: false,
      },
      meta,
    });
    vi.mocked(service.transitionRule).mockResolvedValue({
      data: { ...ruleDefinition, status: "paused" },
      meta,
    });
    renderRoutedPage(
      `/customization-framework/rules/${ruleDefinition.id}`,
      "/customization-framework/rules/:id",
      <RuleDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "Require contact" })).toBeInTheDocument();
    expect(
      await screen.findByText((_content, element) =>
        Boolean(element?.tagName === "LI" && element.textContent?.includes("Email required"))
      )
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "pause" }));
    await user.click(screen.getByRole("button", { name: "pause" }));
    expect(service.transitionRule).toHaveBeenCalledWith(ruleDefinition.id, "pause", {
      transition_key: "customization-command-key",
    });
  });

  it("saves and publishes form-layout versions from the active designer layout", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getForm).mockResolvedValue({ data: formDefinition, meta });
    vi.mocked(service.listFormLayouts).mockResolvedValue({
      data: [{ ...versionMeta, id: "layout-v1", layout: formLayout }],
      meta,
    });
    vi.mocked(service.listResourceContracts).mockResolvedValue({ data: [resourceContract], meta });
    vi.mocked(service.listFields).mockResolvedValue({ data: [], meta });
    vi.mocked(service.createFormLayout).mockResolvedValue({
      data: { ...versionMeta, id: "layout-v2", layout: formLayout },
      meta,
    });
    vi.mocked(service.publishForm).mockResolvedValue({
      data: { ...versionMeta, id: "layout-v2", layout: formLayout },
      meta,
    });
    renderRoutedPage(
      `/customization-framework/forms/${formDefinition.id}/edit`,
      "/customization-framework/forms/:id/edit",
      <EditFormPage />
    );

    expect(
      await screen.findByRole("heading", { name: "Lead intake designer" })
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Last name" }));
    await user.type(screen.getByLabelText("Change summary"), "Add lead last name to intake.");
    await user.click(screen.getByRole("button", { name: "Save new version" }));

    const createLayoutCall = vi.mocked(service.createFormLayout).mock.calls[0];
    expect(createLayoutCall?.[0]).toBe(formDefinition.id);
    expect(createLayoutCall?.[1].change_summary).toBe("Add lead last name to intake.");
    expect(createLayoutCall?.[1].layout.sections[0]?.components[0]).toMatchObject({
      field_key: "last_name",
      label: "Last name",
      width: 6,
    });
    await user.click(await screen.findByRole("button", { name: "Publish version" }));
    const publishLayoutCall = vi.mocked(service.publishForm).mock.calls[0];
    expect(publishLayoutCall?.[0]).toBe(formDefinition.id);
    expect(publishLayoutCall?.[1].layout_version_id).toBe("layout-v2");
    expect(publishLayoutCall?.[1].transition_key).toEqual(expect.any(String));
  });

  it("evaluates, versions, and publishes rule payloads with parsed primitive values", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getRule).mockResolvedValue({ data: ruleDefinition, meta });
    vi.mocked(service.listRuleVersions).mockResolvedValue({ data: [], meta });
    vi.mocked(service.evaluateRule).mockResolvedValue({
      data: {
        id: "execution-1",
        rule_id: ruleDefinition.id,
        rule_name: ruleDefinition.name,
        rule_version_id: "00000000-0000-4000-8000-000000000070",
        target_record_id: null,
        trigger: "validate",
        status: "matched",
        result: {},
        duration_ms: 12,
        diagnostics: [{ code: "required", message: "Email is required.", severity: "error" }],
        correlation_id: "00000000-0000-4000-8000-000000000097",
        executed_at: "2026-07-22T00:00:00Z",
      },
      meta,
    });
    vi.mocked(service.createRuleVersion).mockResolvedValue({
      data: { ...versionMeta, id: "rule-v2" },
      meta,
    });
    vi.mocked(service.publishRule).mockResolvedValue({
      data: { ...versionMeta, id: "rule-v2" },
      meta,
    });
    renderRoutedPage(
      `/customization-framework/rules/${ruleDefinition.id}/edit`,
      "/customization-framework/rules/:id/edit",
      <EditRulePage />
    );

    expect(
      await screen.findByRole("heading", { name: "Require contact builder" })
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Condition field"), "score");
    await user.selectOptions(screen.getByLabelText("Condition operator"), "gte");
    await user.type(screen.getByLabelText("Comparison value"), "70");
    await user.selectOptions(screen.getByLabelText("Action type"), "set-required");
    await user.type(screen.getByLabelText("Action field"), "email");
    await user.type(screen.getByLabelText("Action value or message"), "true");
    await user.click(screen.getByRole("button", { name: "Add action" }));
    await user.click(screen.getByRole("button", { name: "Evaluate sample" }));
    await screen.findByText("Email is required.");
    const evaluateCall = vi.mocked(service.evaluateRule).mock.calls[0];
    expect(evaluateCall?.[0]).toBe(ruleDefinition.id);
    expect(evaluateCall?.[1].record).toEqual({ score: 70 });
    expect(evaluateCall?.[1].changed_fields).toEqual(["score"]);
    expect(evaluateCall?.[1].idempotency_key).toEqual(expect.any(String));

    await user.type(screen.getByLabelText("Change summary"), "Require email for qualified score.");
    await user.click(screen.getByRole("button", { name: "Save candidate version" }));
    expect(service.createRuleVersion).toHaveBeenCalledWith(ruleDefinition.id, {
      condition_ast: { operator: "gte", field: "score", value: 70 },
      action_ast: [{ type: "set-required", field: "email", message: "true", value: undefined }],
      change_summary: "Require email for qualified score.",
    });
    await user.click(await screen.findByRole("button", { name: "Publish rule" }));
    const publishRuleCall = vi.mocked(service.publishRule).mock.calls[0];
    expect(publishRuleCall?.[0]).toBe(ruleDefinition.id);
    expect(publishRuleCall?.[1].version_id).toBe("rule-v2");
    expect(publishRuleCall?.[1].transition_key).toEqual(expect.any(String));
  });

  it("transitions and rolls back field definitions with lock-aware payloads", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getField).mockResolvedValue({ data: fieldDefinition, meta });
    vi.mocked(service.getFieldImpact).mockResolvedValue({
      data: {
        entity_type: "field",
        entity_id: fieldDefinition.id,
        value_count: 5,
        dependency_count: 2,
        blocking: false,
        capability_unavailable: false,
      },
      meta,
    });
    vi.mocked(service.listFieldVersions).mockResolvedValue({
      data: [{ ...versionMeta, id: "field-version-2" }],
      meta,
    });
    vi.mocked(service.transitionField).mockResolvedValue({
      data: { ...fieldDefinition, status: "deprecated" },
      meta,
    });
    vi.mocked(service.rollbackField).mockResolvedValue({ data: fieldDefinition, meta });
    renderRoutedPage(
      `/customization-framework/fields/${fieldDefinition.id}`,
      "/customization-framework/fields/:id",
      <FieldDefinitionDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "Customer tier" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "deprecate" }));
    await user.click(await screen.findByRole("button", { name: "deprecate" }));
    const transitionCall = vi.mocked(service.transitionField).mock.calls[0];
    expect(transitionCall?.[0]).toBe(fieldDefinition.id);
    expect(transitionCall?.[1]).toBe("deprecate");
    expect(transitionCall?.[2].transition_key).toEqual(expect.any(String));

    await user.click(screen.getByRole("button", { name: "Rollback" }));
    await user.click(await screen.findByRole("button", { name: "Create rollback version" }));
    expect(service.rollbackField).toHaveBeenCalledWith(fieldDefinition.id, {
      target_version: 2,
      expected_lock_version: 1,
    });
  });

  it("requires an explicit field-value scope before calling the scoped list API", async () => {
    const user = userEvent.setup();
    renderPage(<FieldValueListPage />);

    expect(await screen.findByText("Custom field values")).toBeInTheDocument();
    expect(
      screen.getByText(/require a definition UUID or target record UUID/u)
    ).toBeInTheDocument();
    expect(service.listValues).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Create value" }));
    await waitFor(() =>
      expect(screen.getByLabelText("location-pathname")).toHaveTextContent(
        /^\/customization-framework\/field-values\/new$/u
      )
    );
  });

  it("lists field values once the URL supplies a governed scope", async () => {
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020"
    );

    expect(await screen.findByText("No field values yet")).toBeInTheDocument();
    expect(service.listValues).toHaveBeenCalledWith(
      expect.objectContaining({
        definition_id: "00000000-0000-4000-8000-000000000020",
        target_record_id: undefined,
        source: undefined,
        page: 1,
        page_size: 25,
      })
    );
  });

  it("uses a field-value query key isolated from unrelated customization cache entries", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const poison = {
      ...fieldValue,
      id: "00000000-0000-4000-8000-000000000031",
      definition_key: "poison-cache-entry",
    };
    const mutantKeys = [
      ["", "field-values", 1, 25, "00000000-0000-4000-8000-000000000020", "", ""],
      ["customization", "", 1, 25, "00000000-0000-4000-8000-000000000020", "", ""],
    ] as const;
    for (const key of mutantKeys) {
      client.setQueryDefaults(key, { staleTime: Infinity });
      client.setQueryData(key, { data: [poison], meta });
    }
    vi.mocked(service.listValues).mockResolvedValue({ data: [fieldValue], meta });

    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020",
      client
    );

    expect(await screen.findByRole("button", { name: "customer-tier" })).toBeInTheDocument();
    expect(screen.queryByText("poison-cache-entry")).not.toBeInTheDocument();
    expect(service.listValues).toHaveBeenCalledTimes(1);
  });

  it("applies target-record and source scope from governed controls", async () => {
    const user = userEvent.setup();
    renderPage(<FieldValueListPage />, "/customization-framework/field-values?page=3");

    await screen.findByText("Custom field values");
    await user.type(
      screen.getByLabelText("Definition UUID"),
      "00000000-0000-4000-8000-000000000020"
    );
    await user.type(
      screen.getByLabelText("Target record UUID"),
      "00000000-0000-4000-8000-000000000040"
    );
    await user.selectOptions(screen.getByLabelText("Source"), "ui");
    await user.click(screen.getByRole("button", { name: "Apply scope" }));

    expect(await screen.findByText("No field values yet")).toBeInTheDocument();
    await waitFor(() => {
      const updatedSearch = new URLSearchParams(
        screen.getByLabelText("location-search").textContent ?? ""
      );
      expect(updatedSearch.get("page")).toBe("1");
      expect(updatedSearch.get("definition_id")).toBe("00000000-0000-4000-8000-000000000020");
      expect(updatedSearch.get("target_record_id")).toBe("00000000-0000-4000-8000-000000000040");
      expect(updatedSearch.get("source")).toBe("ui");
    });
    expect(service.listValues).toHaveBeenCalledWith(
      expect.objectContaining({
        page: 1,
        page_size: 25,
        definition_id: "00000000-0000-4000-8000-000000000020",
        target_record_id: "00000000-0000-4000-8000-000000000040",
        source: "ui",
      })
    );
  });

  it("removes blank field-value scope controls before applying URL filters", async () => {
    const user = userEvent.setup();
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020&target_record_id=00000000-0000-4000-8000-000000000040&source=ui"
    );

    await screen.findByText("No field values yet");
    await user.clear(screen.getByLabelText("Definition UUID"));
    await user.selectOptions(screen.getByLabelText("Source"), "");
    await user.click(screen.getByRole("button", { name: "Apply scope" }));

    expect(await screen.findByText("No field values yet")).toBeInTheDocument();
    await waitFor(() => {
      const updatedSearch = new URLSearchParams(
        screen.getByLabelText("location-search").textContent ?? ""
      );
      expect(updatedSearch.get("page")).toBe("1");
      expect(updatedSearch.get("target_record_id")).toBe("00000000-0000-4000-8000-000000000040");
      expect(updatedSearch.has("definition_id")).toBe(false);
      expect(updatedSearch.has("source")).toBe(false);
    });
    expect(service.listValues).toHaveBeenLastCalledWith(
      expect.objectContaining({
        page: 1,
        definition_id: undefined,
        target_record_id: "00000000-0000-4000-8000-000000000040",
        source: undefined,
      })
    );
  });

  it("passes definition, target, source, and page filters from the URL", async () => {
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?page=2&definition_id=00000000-0000-4000-8000-000000000020&target_record_id=00000000-0000-4000-8000-000000000040&source=ui"
    );

    expect(await screen.findByText("No field values yet")).toBeInTheDocument();
    expect(screen.getByLabelText("Definition UUID")).toHaveValue(
      "00000000-0000-4000-8000-000000000020"
    );
    expect(screen.getByLabelText("Target record UUID")).toHaveValue(
      "00000000-0000-4000-8000-000000000040"
    );
    expect(screen.getByLabelText("Source")).toHaveValue("ui");
    expect(screen.getByRole("option", { name: "All sources" })).toHaveValue("");
    expect(screen.getByRole("option", { name: "ui" })).toHaveValue("ui");
    expect(service.listValues).toHaveBeenCalledWith(
      expect.objectContaining({
        page: 2,
        page_size: 25,
        definition_id: "00000000-0000-4000-8000-000000000020",
        target_record_id: "00000000-0000-4000-8000-000000000040",
        source: "ui",
      })
    );
  });

  it("renders scoped field values and preserves URL scope while paging", async () => {
    const pagedMeta = {
      ...meta,
      pagination: { ...meta.pagination, count: 26, page: 1, total_pages: 2, has_next: true },
    };
    vi.mocked(service.listValues).mockResolvedValue({ data: [fieldValue], meta: pagedMeta });
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020"
    );

    expect(await screen.findByRole("button", { name: "customer-tier" })).toBeInTheDocument();
    expect(screen.getByText("00000000-0000-4000-8000-000000000040")).toBeInTheDocument();
    expect(screen.getAllByText("ui")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Custom field values")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByLabelText("location-search")).toHaveTextContent("page=2")
    );
    expect(service.listValues).toHaveBeenLastCalledWith(
      expect.objectContaining({
        page: 2,
        definition_id: "00000000-0000-4000-8000-000000000020",
      })
    );
  });

  it("navigates from a scoped field value row to its detail route", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listValues).mockResolvedValue({ data: [fieldValue], meta });
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020"
    );

    await user.click(await screen.findByRole("button", { name: "customer-tier" }));

    await waitFor(() =>
      expect(screen.getByLabelText("location-pathname")).toHaveTextContent(
        new RegExp(`^/customization-framework/field-values/${fieldValue.id}$`, "u")
      )
    );
  });

  it("creates a field value from active field definitions", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listFields).mockResolvedValue({ data: [fieldDefinition], meta });
    vi.mocked(service.createValue).mockResolvedValue({ data: fieldValue, meta });
    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    expect(service.listFields).toHaveBeenCalledWith({
      status: "active",
      page_size: runtimeConfiguration.document.list_preferences.page_size,
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Source")).toHaveValue("ui");
    expect(screen.getByLabelText("JSON value")).toHaveValue("null");
    await user.selectOptions(screen.getByLabelText("Active field"), fieldDefinition.id);
    await user.type(
      screen.getByLabelText("Target record UUID"),
      "00000000-0000-4000-8000-000000000040"
    );
    fireEvent.change(screen.getByLabelText("JSON value"), { target: { value: '"platinum"' } });
    await user.click(screen.getByRole("button", { name: "Create value" }));

    expect(service.createValue).toHaveBeenCalledWith({
      definition_id: fieldDefinition.id,
      target_record_id: "00000000-0000-4000-8000-000000000040",
      source: "ui",
      value: "platinum",
    });
    expect(await screen.findByLabelText("location-pathname")).toHaveTextContent(
      `/customization-framework/field-values/${fieldValue.id}`
    );
  });

  it("uses an active-field query key isolated from unrelated customization cache entries", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const poisonField = {
      ...fieldDefinition,
      id: "00000000-0000-4000-8000-000000000021",
      key: "poison-field",
      label: "Poison field",
    };
    const pageSize = runtimeConfiguration.document.list_preferences.page_size;
    const mutantKeys = [
      [],
      ["", "active-fields-for-values", pageSize],
      ["customization", "", pageSize],
    ] as const;
    for (const key of mutantKeys) {
      client.setQueryDefaults(key, { staleTime: Infinity });
      client.setQueryData(key, { data: [poisonField], meta });
    }
    vi.mocked(service.listFields).mockResolvedValue({ data: [fieldDefinition], meta });

    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />,
      client
    );

    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Customer tier (customer-tier)" })).toHaveValue(
      fieldDefinition.id
    );
    expect(
      screen.queryByRole("option", { name: "Poison field (poison-field)" })
    ).not.toBeInTheDocument();
    expect(service.listFields).toHaveBeenCalledTimes(1);
  });

  it("rejects missing create field-value requirements when native validation is bypassed", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getConfiguration).mockResolvedValue({
      ...runtimeConfiguration,
      document: {
        ...runtimeConfiguration.document,
        policies: {
          ...runtimeConfiguration.document.policies,
          value_sources: [],
        },
      },
    });
    vi.mocked(service.listFields).mockResolvedValue({ data: [fieldDefinition], meta });
    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Active field"), fieldDefinition.id);
    await user.type(
      screen.getByLabelText("Target record UUID"),
      "00000000-0000-4000-8000-000000000040"
    );
    fireEvent.submit(screen.getByRole("button", { name: "Create value" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Field, target record, and governed source are required."
    );
    expect(service.createValue).not.toHaveBeenCalled();
  });

  it("validates missing create field-value definition and target independently", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listFields).mockResolvedValue({ data: [fieldDefinition], meta });
    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Target record UUID"),
      "00000000-0000-4000-8000-000000000040"
    );
    fireEvent.submit(screen.getByRole("button", { name: "Create value" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Field, target record, and governed source are required."
    );
    expect(service.createValue).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByLabelText("Active field"), fieldDefinition.id);
    await user.clear(screen.getByLabelText("Target record UUID"));
    fireEvent.submit(screen.getByRole("button", { name: "Create value" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Field, target record, and governed source are required."
    );
    expect(service.createValue).not.toHaveBeenCalled();
  });

  it("uses an operator-selected governed source when creating a field value", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getConfiguration).mockResolvedValue({
      ...runtimeConfiguration,
      document: {
        ...runtimeConfiguration.document,
        policies: {
          ...runtimeConfiguration.document.policies,
          value_sources: ["ui", "api"],
        },
      },
    });
    vi.mocked(service.listFields).mockResolvedValue({ data: [fieldDefinition], meta });
    vi.mocked(service.createValue).mockResolvedValue({ data: fieldValue, meta });
    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Active field"), fieldDefinition.id);
    await user.type(
      screen.getByLabelText("Target record UUID"),
      "00000000-0000-4000-8000-000000000040"
    );
    await user.selectOptions(screen.getByLabelText("Source"), "api");
    fireEvent.change(screen.getByLabelText("JSON value"), { target: { value: '"platinum"' } });
    await user.click(screen.getByRole("button", { name: "Create value" }));

    await waitFor(() =>
      expect(service.createValue).toHaveBeenCalledWith(
        expect.objectContaining({
          source: "api",
        })
      )
    );
  });

  it("shows pending create progress without losing the guarded form state", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listFields).mockResolvedValue({ data: [fieldDefinition], meta });
    vi.mocked(service.createValue).mockReturnValue(new Promise(() => undefined));
    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Active field"), fieldDefinition.id);
    await user.type(
      screen.getByLabelText("Target record UUID"),
      "00000000-0000-4000-8000-000000000040"
    );
    fireEvent.change(screen.getByLabelText("JSON value"), { target: { value: '"platinum"' } });
    await user.click(screen.getByRole("button", { name: "Create value" }));

    expect(await screen.findByRole("button", { name: "Creating…" })).toBeDisabled();
  });

  it("keeps invalid create field-value submissions local", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listFields).mockResolvedValue({ data: [fieldDefinition], meta });
    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Active field"), fieldDefinition.id);
    await user.type(
      screen.getByLabelText("Target record UUID"),
      "00000000-0000-4000-8000-000000000040"
    );
    fireEvent.change(screen.getByLabelText("JSON value"), { target: { value: "{" } });
    await user.click(screen.getByRole("button", { name: "Create value" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Expected property name");
    expect(service.createValue).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.getByLabelText("location-pathname")).toHaveTextContent(
        /^\/customization-framework\/field-values$/u
      )
    );
  });

  it("clears stale create field-value validation errors before a valid guarded submit", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listFields).mockResolvedValue({ data: [fieldDefinition], meta });
    vi.mocked(service.createValue).mockReturnValue(new Promise(() => undefined));
    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Active field"), fieldDefinition.id);
    await user.type(
      screen.getByLabelText("Target record UUID"),
      "00000000-0000-4000-8000-000000000040"
    );
    fireEvent.change(screen.getByLabelText("JSON value"), { target: { value: "{" } });
    await user.click(screen.getByRole("button", { name: "Create value" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Expected property name");

    fireEvent.change(screen.getByLabelText("JSON value"), { target: { value: '"platinum"' } });
    await user.click(screen.getByRole("button", { name: "Create value" }));

    expect(await screen.findByRole("button", { name: "Creating…" })).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders create field-value loading and configuration failure states", async () => {
    vi.mocked(service.getConfiguration).mockReturnValue(new Promise(() => undefined));
    const loadingConfiguration = renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );
    expect(screen.getByLabelText("Loading customization data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    loadingConfiguration.unmount();

    vi.mocked(service.getConfiguration).mockResolvedValue(runtimeConfiguration);
    vi.mocked(service.listFields).mockReturnValue(new Promise(() => undefined));
    const loadingDefinitions = renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );
    expect(screen.getByLabelText("Loading customization data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    loadingDefinitions.unmount();

    vi.clearAllMocks();
    vi.mocked(service.getConfiguration)
      .mockRejectedValueOnce(new Error("create configuration unavailable"))
      .mockResolvedValueOnce(runtimeConfiguration);
    vi.mocked(service.listFields).mockResolvedValue({ data: [fieldDefinition], meta });
    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("create configuration unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    expect(service.getConfiguration).toHaveBeenCalledTimes(2);
  });

  it("renders create field-value dependency failure states", async () => {
    vi.mocked(service.listFields).mockRejectedValueOnce(new Error("active fields unavailable"));
    const failedDefinitions = renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("active fields unavailable");
    vi.mocked(service.listFields).mockResolvedValueOnce({ data: [fieldDefinition], meta });
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(
      await screen.findByRole("heading", { name: "Create custom field value" })
    ).toBeInTheDocument();
    failedDefinitions.unmount();

    vi.mocked(service.listFields).mockResolvedValueOnce(null as never);
    renderRoutedPage(
      "/customization-framework/field-values/new",
      "/customization-framework/field-values/new",
      <CreateFieldValuePage />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Field-value dependencies were not returned."
    );
  });

  it("navigates from the empty scoped list create affordance", async () => {
    const user = userEvent.setup();
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020"
    );

    expect(await screen.findByText("No field values yet")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create field value" }));

    await waitFor(() =>
      expect(screen.getByLabelText("location-pathname")).toHaveTextContent(
        /^\/customization-framework\/field-values\/new$/u
      )
    );
  });

  it("navigates from field-value detail to the edit route", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getValue).mockResolvedValue({ data: fieldValue, meta });
    renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}`,
      "/customization-framework/field-values/:id",
      <FieldValueDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "customer-tier" })).toBeInTheDocument();
    expect(screen.getByText("Definition revision")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() =>
      expect(screen.getByLabelText("location-pathname")).toHaveTextContent(
        new RegExp(`^/customization-framework/field-values/${fieldValue.id}/edit$`, "u")
      )
    );
  });

  it("renders field-value detail loading, retry, and missing-payload states", async () => {
    vi.mocked(service.getValue).mockReturnValue(new Promise(() => undefined));
    const loading = renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}`,
      "/customization-framework/field-values/:id",
      <FieldValueDetailPage />
    );
    expect(screen.getByLabelText("Loading customization data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    loading.unmount();

    vi.mocked(service.getValue)
      .mockRejectedValueOnce(new Error("field value detail unavailable"))
      .mockResolvedValueOnce({ data: fieldValue, meta });
    const failed = renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}`,
      "/customization-framework/field-values/:id",
      <FieldValueDetailPage />
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("field value detail unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "customer-tier" })).toBeInTheDocument();
    failed.unmount();

    vi.mocked(service.getValue).mockResolvedValueOnce(null as never);
    renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}`,
      "/customization-framework/field-values/:id",
      <FieldValueDetailPage />
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Field value not found.");
  });

  it("fails closed when a field-value detail route has no value identifier", async () => {
    renderRoutedPage(
      "/customization-framework/field-values/",
      "/customization-framework/field-values/",
      <FieldValueDetailPage />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Field value not found.");
    expect(service.getValue).not.toHaveBeenCalled();
  });

  it("uses isolated cache keys for field-value detail lookups", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const poison = { data: { ...fieldValue, definition_key: "poison-detail" }, meta };
    const mutantKeys = [
      [],
      ["", "field-value", fieldValue.id],
      ["customization", "", fieldValue.id],
    ] as const;
    for (const key of mutantKeys) {
      client.setQueryDefaults(key, { staleTime: Infinity });
      client.setQueryData(key, poison);
    }
    vi.mocked(service.getValue).mockResolvedValue({ data: fieldValue, meta });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`/customization-framework/field-values/${fieldValue.id}`]}>
          <Routes>
            <Route
              path="/customization-framework/field-values/:id"
              element={<FieldValueDetailPage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByRole("heading", { name: "customer-tier" })).toBeInTheDocument();
    expect(screen.queryByText("poison-detail")).not.toBeInTheDocument();
    expect(service.getValue).toHaveBeenCalledWith(fieldValue.id);
  });

  it("deletes a field value with governed optimistic-lock evidence", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getValue).mockResolvedValue({ data: fieldValue, meta });
    vi.mocked(service.deleteValue).mockResolvedValue(undefined);
    renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}`,
      "/customization-framework/field-values/:id",
      <FieldValueDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "customer-tier" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete value" }));

    await waitFor(() =>
      expect(service.deleteValue).toHaveBeenCalledWith(fieldValue.id, fieldValue.lock_version)
    );
    await waitFor(() =>
      expect(screen.getByLabelText("location-pathname")).toHaveTextContent(
        /^\/customization-framework\/field-values$/u
      )
    );
  });

  it("edits a field value through the active revision and supports cancellation", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateQueries = vi.spyOn(client, "invalidateQueries");
    vi.mocked(service.getValue).mockResolvedValue({ data: fieldValue, meta });
    vi.mocked(service.updateValue).mockResolvedValue({
      data: { ...fieldValue, value: { tier: "platinum" }, lock_version: 2 },
      meta,
    });
    renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}/edit`,
      "/customization-framework/field-values/:id/edit",
      <EditFieldValuePage />,
      client
    );

    expect(await screen.findByRole("heading", { name: "Edit customer-tier" })).toBeInTheDocument();
    expect(screen.getByLabelText("JSON value")).toHaveValue('"gold"');
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save value" })).toBeEnabled();
    await user.clear(screen.getByLabelText("JSON value"));
    fireEvent.change(screen.getByLabelText("JSON value"), {
      target: { value: '{"tier":"platinum"}' },
    });
    await user.click(screen.getByRole("button", { name: "Save value" }));

    await waitFor(() =>
      expect(service.updateValue).toHaveBeenCalledWith(fieldValue.id, {
        value: { tier: "platinum" },
        expected_lock_version: fieldValue.lock_version,
      })
    );
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["customization", "field-value", fieldValue.id],
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByLabelText("location-pathname")).toHaveTextContent(
        new RegExp(`^/customization-framework/field-values/${fieldValue.id}$`, "u")
      )
    );
  });

  it("renders field-value edit loading, retry, and missing-payload states", async () => {
    vi.mocked(service.getValue).mockReturnValue(new Promise(() => undefined));
    const loading = renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}/edit`,
      "/customization-framework/field-values/:id/edit",
      <EditFieldValuePage />
    );
    expect(screen.getByLabelText("Loading customization data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    loading.unmount();

    vi.mocked(service.getValue)
      .mockRejectedValueOnce(new Error("field value edit unavailable"))
      .mockResolvedValueOnce({ data: fieldValue, meta });
    const failed = renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}/edit`,
      "/customization-framework/field-values/:id/edit",
      <EditFieldValuePage />
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("field value edit unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Edit customer-tier" })).toBeInTheDocument();
    failed.unmount();

    vi.mocked(service.getValue).mockResolvedValueOnce(null as never);
    renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}/edit`,
      "/customization-framework/field-values/:id/edit",
      <EditFieldValuePage />
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Field value not found.");
  });

  it("fails closed when a field-value edit route has no value identifier", async () => {
    renderRoutedPage(
      "/customization-framework/field-values/edit",
      "/customization-framework/field-values/edit",
      <EditFieldValuePage />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Field value not found.");
    expect(service.getValue).not.toHaveBeenCalled();
  });

  it("uses isolated cache keys for field-value edit lookups", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const poison = { data: { ...fieldValue, definition_key: "poison-edit", value: "stale" }, meta };
    const mutantKeys = [
      [],
      ["", "field-value", fieldValue.id],
      ["customization", "", fieldValue.id],
    ] as const;
    for (const key of mutantKeys) {
      client.setQueryDefaults(key, { staleTime: Infinity });
      client.setQueryData(key, poison);
    }
    vi.mocked(service.getValue).mockResolvedValue({ data: fieldValue, meta });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter
          initialEntries={[`/customization-framework/field-values/${fieldValue.id}/edit`]}
        >
          <Routes>
            <Route
              path="/customization-framework/field-values/:id/edit"
              element={<EditFieldValuePage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByRole("heading", { name: "Edit customer-tier" })).toBeInTheDocument();
    expect(screen.queryByText("Edit poison-edit")).not.toBeInTheDocument();
    expect(service.getValue).toHaveBeenCalledWith(fieldValue.id);
  });

  it("shows pending edit progress without surfacing stale local errors", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getValue).mockResolvedValue({ data: fieldValue, meta });
    vi.mocked(service.updateValue).mockReturnValue(new Promise(() => undefined));
    renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}/edit`,
      "/customization-framework/field-values/:id/edit",
      <EditFieldValuePage />
    );

    expect(await screen.findByRole("heading", { name: "Edit customer-tier" })).toBeInTheDocument();
    await user.clear(screen.getByLabelText("JSON value"));
    fireEvent.change(screen.getByLabelText("JSON value"), {
      target: { value: '{"tier":"platinum"}' },
    });
    await user.click(screen.getByRole("button", { name: "Save value" }));

    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps invalid field-value edits local and cancels back to detail", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getValue).mockResolvedValue({ data: fieldValue, meta });
    renderRoutedPage(
      `/customization-framework/field-values/${fieldValue.id}/edit`,
      "/customization-framework/field-values/:id/edit",
      <EditFieldValuePage />
    );

    expect(await screen.findByRole("heading", { name: "Edit customer-tier" })).toBeInTheDocument();
    await user.clear(screen.getByLabelText("JSON value"));
    fireEvent.change(screen.getByLabelText("JSON value"), { target: { value: "{" } });
    await user.click(screen.getByRole("button", { name: "Save value" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Expected property name");
    expect(service.updateValue).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.getByLabelText("location-pathname")).toHaveTextContent(
        new RegExp(`^/customization-framework/field-values/${fieldValue.id}$`, "u")
      )
    );
  });

  it("renders field-value loading and governed error states only when scoped", async () => {
    vi.mocked(service.getConfiguration).mockReturnValue(new Promise(() => undefined));
    const loading = renderPage(<FieldValueListPage />);
    expect(screen.getByLabelText("Loading customization data")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    loading.unmount();

    vi.mocked(service.getConfiguration).mockResolvedValue(runtimeConfiguration);
    vi.mocked(service.listValues).mockRejectedValue(new Error("scope failed"));
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020"
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("scope failed");
  });

  it("retries configuration errors and handles missing scoped payloads without unsafe fallbacks", async () => {
    const user = userEvent.setup();
    vi.mocked(service.getConfiguration)
      .mockRejectedValueOnce(new Error("configuration failed"))
      .mockResolvedValueOnce(runtimeConfiguration);
    const configurationError = renderPage(<FieldValueListPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("configuration failed");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Custom field values")).toBeInTheDocument();
    expect(service.getConfiguration).toHaveBeenCalledTimes(2);
    configurationError.unmount();

    vi.mocked(service.getConfiguration).mockResolvedValue(runtimeConfiguration);
    vi.mocked(service.listValues).mockRejectedValue(new Error("field-value payload missing"));
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020"
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("field-value payload missing");
  });

  it("fails closed when the configuration query resolves without a document", async () => {
    vi.mocked(service.getConfiguration).mockResolvedValue(null as never);

    renderPage(<FieldValueListPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No governed customization configuration was received."
    );
    expect(service.listValues).not.toHaveBeenCalled();
  });

  it("keeps the scoped list API disabled when runtime page size is unavailable", async () => {
    vi.mocked(service.getConfiguration).mockResolvedValue({
      ...runtimeConfiguration,
      document: {
        ...runtimeConfiguration.document,
        list_preferences: {
          ...runtimeConfiguration.document.list_preferences,
          page_size: undefined as never,
        },
      },
    });
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No governed field-value response was received."
    );
    expect(service.listValues).not.toHaveBeenCalled();
  });

  it("retries scoped field-value errors through the governed retry action", async () => {
    const user = userEvent.setup();
    vi.mocked(service.listValues)
      .mockRejectedValueOnce(new Error("scope failed"))
      .mockResolvedValueOnce({ data: [], meta });
    renderPage(
      <FieldValueListPage />,
      "/customization-framework/field-values?definition_id=00000000-0000-4000-8000-000000000020"
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("scope failed");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No field values yet")).toBeInTheDocument();
    expect(service.listValues).toHaveBeenCalledTimes(2);
  });

  it("shows safe denied and capability-unavailable states with correlation IDs", () => {
    const { rerender } = render(
      <GovernedError
        error={new ApiError("hidden", 403, undefined, "permission_denied", "corr-denied")}
      />
    );
    expect(screen.getByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText(/corr-denied/u)).toBeInTheDocument();
    rerender(
      <GovernedError
        error={new ApiError("offline", 503, undefined, "capability_unavailable", "corr-down")}
      />
    );
    expect(screen.getByText("Capability unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-down/u)).toBeInTheDocument();
  });

  it("normalizes field-value JSON parsing failures from Error and unknown throws", () => {
    expect(jsonErrorMessage(new Error("Expected property name"))).toBe("Expected property name");
    expect(jsonErrorMessage("not an error")).toBe("Value must be valid JSON.");
  });
});
