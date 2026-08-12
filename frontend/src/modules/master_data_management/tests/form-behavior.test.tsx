/* eslint-disable max-lines-per-function, @typescript-eslint/consistent-type-imports, @typescript-eslint/no-unsafe-assignment -- form behavior tests exercise multi-step UI state; asymmetric matcher payloads are intentionally inspected. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  DataQualityRule,
  MasterDataConfiguration,
  MasterDataEntity,
  MasterEntityType,
} from "../contracts";
import { EntityForm } from "../components/EntityForm";
import { EntityTypeForm } from "../components/EntityTypeForm";
import { QualityRuleForm } from "../components/QualityRuleForm";
import { masterDataService } from "../services/master-data-service";

vi.mock("../services/master-data-service", () => ({
  masterDataService: {
    configuration: {
      current: vi.fn(),
    },
    entityTypes: {
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
    },
    entities: {
      create: vi.fn(),
      update: vi.fn(),
    },
    qualityRules: {
      create: vi.fn(),
      update: vi.fn(),
    },
  },
}));

const stamp = "2026-07-22T00:00:00Z";
const entityType: MasterEntityType = {
  id: "entity-type-1",
  tenant_id: "tenant-1",
  key: "customer",
  display_name: "Customer",
  description: "Customer master record",
  json_schema: {
    type: "object",
    properties: {
      external_id: { type: "string", title: "External ID" },
      active: { type: "boolean", title: "Active" },
    },
    required: ["external_id"],
  },
  schema_version: 1,
  required_fields: ["external_id"],
  sensitive_fields: ["external_id"],
  searchable_fields: ["external_id"],
  owner_module: "master_data_management",
  is_system: false,
  is_active: true,
  metadata: {},
  is_deleted: false,
  deleted_at: null,
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: null,
};
const configuration: MasterDataConfiguration = {
  id: "config-1",
  tenant_id: "tenant-1",
  version: 2,
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: null,
  document: {
    environment: "development",
    schema_policy: {
      entity_type_key_pattern: "^[a-z][a-z0-9_]*$",
      entity_type_key_max_length: 64,
      field_path_pattern: "^[a-z][a-z0-9_.]*$",
      allowed_json_schema_keywords: ["type", "properties", "required"],
      max_payload_bytes: 1024,
      builtin_entity_types: [],
    },
    lifecycle: { allow_physical_delete: false, merged_entities_editable: false },
    workflows: { entity: {}, quality_issue: {}, match_candidate: {}, merge: {} },
    limits: {
      display_name_max: 120,
      description_max: 500,
      owner_module_max: 80,
      entity_code_max: 80,
      entity_name_max: 160,
      source_system_max: 80,
      source_record_id_max: 120,
      resolution_max: 500,
      reason_max: 500,
      deduplication_scan_max_entities: 1000,
      merge_min_entities: 2,
      list_page_size: 25,
      selector_page_size: 50,
    },
    quality: {
      missing_values: ["", null],
      rule_schemas: { required: {}, format: {}, range: {}, timeliness: {} },
      referential_target_field_default: "id",
      timeliness_max_age_days_default: 45,
      no_rules_evaluated: true,
      no_rules_score: null,
      no_rules_issue_count: 0,
      score_scale: 100,
      score_decimal_places: 2,
      auto_resolve_passing: true,
      defaults: {
        rule_type: "required",
        dimension: "completeness",
        severity: "warning",
        weight: "1.0",
      },
    },
    matching: {
      algorithms: ["exact", "fuzzy"],
      soundex_mapping: {},
      soundex_output_length: 4,
      weight_sum: "1.0",
      weight_tolerance: "0.01",
      threshold_min: "0.00",
      threshold_max: "1.00",
      missing_value_score: "0.00",
      outcomes: { auto_confirm: "confirmed", review: "pending", no_match: "rejected" },
      strategy_version: 1,
      scan_statuses: ["active"],
      skip_incomplete_blocking_keys: true,
      auto_confirm_enabled: true,
      review_decisions: ["confirm", "reject"],
      defaults: {
        algorithm: "exact",
        review_threshold: "0.80",
        auto_confirm_threshold: "0.95",
      },
    },
    merge: {
      allowed_statuses: ["active"],
      survivorship_order: ["updated_at"],
      reversal_expected_version_increment: 1,
    },
    dashboard: {
      score_buckets: [{ label: "healthy", minimum: 90, maximum: 100 }],
      trend_window_days: 30,
      recent_activity_limit: 5,
      minimum_bar_percent: 3,
    },
    operational: {
      health_check_interval_seconds: 60,
      job_poll_interval_ms: 2000,
      job_poll_statuses: ["queued", "running", "retrying"],
    },
    ui: {
      sidebar_order: 10,
      skeleton_cards: 4,
      quality_issue_default_status: "open",
      status_tokens: { danger: "destructive", success: "success", warning: "warning" },
      list_page_size: 25,
    },
    entity_defaults: { source_system: "ERP" },
    feature_rollout: {
      enabled: true,
      modes: ["development"],
      roles: ["data-steward"],
      cohorts: ["pilot"],
      percentage: 25,
    },
  },
};

function item<T>(data: T) {
  return { data, meta: { correlation_id: "corr-mdm-1", timestamp: stamp } };
}

function list<T>(items: T[]) {
  return {
    items,
    meta: { correlation_id: "corr-mdm-1", timestamp: stamp },
    pagination: {
      page: 1,
      page_size: 25,
      count: items.length,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
  };
}

function renderForm(element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={element} />
          <Route path="*" element={<span>navigated</span>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("master data management form behavior", () => {
  const entityTypesCreate = vi.mocked(masterDataService.entityTypes.create);
  const entityTypesList = vi.mocked(masterDataService.entityTypes.list);
  const entitiesCreate = vi.mocked(masterDataService.entities.create);
  const entitiesUpdate = vi.mocked(masterDataService.entities.update);
  const qualityRulesCreate = vi.mocked(masterDataService.qualityRules.create);

  beforeEach(() => {
    vi.clearAllMocks();
    let sequence = 0;
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => `entity-key-${(sequence += 1)}`) });
    vi.mocked(masterDataService.configuration.current).mockResolvedValue(item(configuration));
    entityTypesList.mockResolvedValue(list([entityType]));
  });

  it("rejects duplicate schema fields before calling the service", async () => {
    const user = userEvent.setup();
    renderForm(<EntityTypeForm />);

    await user.type(screen.getByLabelText("Canonical key"), "customer");
    await user.type(screen.getByLabelText("Display name"), "Customer");
    await user.click(screen.getByRole("button", { name: "Add field" }));
    await user.click(screen.getByRole("button", { name: "Add field" }));
    await user.type(screen.getByLabelText("Field 1 key"), "external_id");
    await user.type(screen.getByLabelText("Field 1 label"), "External ID");
    await user.type(screen.getByLabelText("Field 2 key"), "external_id");
    await user.type(screen.getByLabelText("Field 2 label"), "Duplicate External ID");
    await user.click(screen.getByRole("button", { name: "Create entity type" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Field keys must be unique.");
    expect(entityTypesCreate).not.toHaveBeenCalled();
  });

  it("creates a governed schema from field controls instead of raw JSON", async () => {
    entityTypesCreate.mockResolvedValue({
      data: {
        id: "entity-type-1",
        tenant_id: "tenant-1",
        key: "customer",
        display_name: "Customer",
        description: "Customer master record",
        json_schema: { type: "object", properties: {} },
        schema_version: 1,
        required_fields: [],
        sensitive_fields: [],
        searchable_fields: [],
        owner_module: "master_data_management",
        is_system: false,
        is_active: true,
        metadata: {},
        is_deleted: false,
        deleted_at: null,
        created_at: "2026-07-22T00:00:00Z",
        updated_at: "2026-07-22T00:00:00Z",
        created_by: "user-1",
        updated_by: null,
      },
      meta: { correlation_id: "corr-mdm-1", timestamp: "2026-07-22T00:00:00Z" },
    });
    const user = userEvent.setup();
    renderForm(<EntityTypeForm />);

    await user.type(screen.getByLabelText("Canonical key"), "customer");
    await user.type(screen.getByLabelText("Display name"), "Customer");
    await user.type(screen.getByLabelText("Description"), "Customer master record");
    await user.click(screen.getByRole("button", { name: "Add field" }));
    await user.type(screen.getByLabelText("Field 1 key"), "external_id");
    await user.type(screen.getByLabelText("Field 1 label"), "External ID");
    await user.selectOptions(screen.getByLabelText("Field 1 type"), "integer");
    await user.click(screen.getByLabelText("required"));
    await user.click(screen.getByLabelText("sensitive"));
    await user.click(screen.getByRole("button", { name: "Create entity type" }));

    await waitFor(() => expect(entityTypesCreate).toHaveBeenCalled());
    expect(entityTypesCreate).toHaveBeenCalledWith({
      key: "customer",
      display_name: "Customer",
      description: "Customer master record",
      json_schema: {
        type: "object",
        title: "Customer",
        additionalProperties: false,
        properties: { external_id: { type: "integer", title: "External ID" } },
      },
      required_fields: ["external_id"],
      sensitive_fields: ["external_id"],
      searchable_fields: ["external_id"],
      idempotency_key: "mdm-ui:entity-type-create:entity-key-1",
    });
  });

  it("creates master entities with configured defaults and schema-driven field controls", async () => {
    const created: MasterDataEntity = {
      id: "entity-1",
      tenant_id: "tenant-1",
      entity_type: "entity-type-1",
      entity_type_key: "customer",
      entity_type_display_name: "Customer",
      entity_code: "CUST-001",
      entity_name: "ACME Industries",
      source_system: "ERP",
      source_record_id: "SRC-1",
      status: "active",
      quality_score: "100.00",
      quality_evaluated_at: stamp,
      golden_record: null,
      is_golden: true,
      version: 1,
      data: { external_id: "EXT-1", active: true },
      transition_history: [],
      is_deleted: false,
      deleted_at: null,
      created_at: stamp,
      updated_at: stamp,
      created_by: "user-1",
      updated_by: null,
    };
    entitiesCreate.mockResolvedValue(item(created));
    const user = userEvent.setup();
    renderForm(<EntityForm />);

    expect(await screen.findByLabelText("Entity type")).toHaveValue("entity-type-1");
    expect(screen.getByLabelText("Source system")).toHaveValue("ERP");

    await user.type(screen.getByLabelText("Business code"), "CUST-001");
    await user.type(screen.getByLabelText("Display name"), "ACME Industries");
    await user.type(screen.getByLabelText(/External ID/u), "EXT-1");
    await user.click(screen.getByLabelText(/Active/u));
    await user.click(screen.getByRole("button", { name: "Create entity" }));

    await waitFor(() =>
      expect(entitiesCreate).toHaveBeenCalledWith({
        entity_type_id: "entity-type-1",
        entity_code: "CUST-001",
        entity_name: "ACME Industries",
        data: { external_id: "EXT-1", active: true },
        source_system: "ERP",
        source_record_id: "",
        idempotency_key: "mdm-ui:entity-create:entity-key-1",
      })
    );
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });

  it("updates master entities with expected version and change evidence", async () => {
    const existing: MasterDataEntity = {
      id: "entity-1",
      tenant_id: "tenant-1",
      entity_type: "entity-type-1",
      entity_type_key: "customer",
      entity_type_display_name: "Customer",
      entity_code: "CUST-001",
      entity_name: "ACME Industries",
      source_system: "CRM",
      source_record_id: "SRC-1",
      status: "active",
      quality_score: "95.00",
      quality_evaluated_at: stamp,
      golden_record: null,
      is_golden: true,
      version: 4,
      data: { external_id: "EXT-1", active: false },
      transition_history: [],
      is_deleted: false,
      deleted_at: null,
      created_at: stamp,
      updated_at: stamp,
      created_by: "user-1",
      updated_by: null,
    };
    entitiesUpdate.mockResolvedValue(item({ ...existing, entity_name: "ACME Corp", version: 5 }));
    const user = userEvent.setup();
    renderForm(<EntityForm existing={existing} />);

    expect(await screen.findByLabelText("Entity type")).toBeDisabled();
    await user.clear(screen.getByLabelText("Display name"));
    await user.type(screen.getByLabelText("Display name"), "ACME Corp");
    await user.type(screen.getByLabelText("Reason for change"), "Legal name correction");
    await user.click(screen.getByRole("button", { name: "Save new version" }));

    await waitFor(() =>
      expect(entitiesUpdate).toHaveBeenCalledWith("entity-1", {
        expected_version: 4,
        changes: expect.objectContaining({
          entity_code: "CUST-001",
          entity_name: "ACME Corp",
          source_system: "CRM",
          source_record_id: "SRC-1",
        }),
        reason: "Legal name correction",
        idempotency_key: "mdm-ui:entity-update:entity-key-1",
      })
    );
  });

  it("creates quality rules from tenant defaults and rule-specific configuration", async () => {
    const savedRule: DataQualityRule = {
      id: "rule-1",
      tenant_id: "tenant-1",
      entity_type: "entity-type-1",
      entity_type_key: "customer",
      name: "External ID format",
      field_path: "external_id",
      rule_type: "format",
      configuration: { pattern: "^EXT-[0-9]+$" },
      dimension: "conformity",
      severity: "error",
      weight: "0.75",
      is_active: true,
      is_deleted: false,
      deleted_at: null,
      created_at: stamp,
      updated_at: stamp,
      created_by: "user-1",
      updated_by: null,
    };
    qualityRulesCreate.mockResolvedValue(item(savedRule));
    const user = userEvent.setup();
    renderForm(<QualityRuleForm />);

    expect(await screen.findByLabelText("Rule type")).toHaveValue("required");
    await user.selectOptions(screen.getByLabelText("Entity type"), "entity-type-1");
    await user.type(screen.getByLabelText("Rule name"), "External ID format");
    await user.type(screen.getByLabelText("Field path"), "external_id");
    await user.selectOptions(screen.getByLabelText("Rule type"), "format");
    await user.selectOptions(screen.getByLabelText("Dimension"), "conformity");
    await user.selectOptions(screen.getByLabelText("Severity"), "error");
    await user.clear(screen.getByLabelText("Weight"));
    await user.type(screen.getByLabelText("Weight"), "0.75");
    fireEvent.change(screen.getByLabelText("Regular-expression pattern"), {
      target: { value: "^EXT-[0-9]+$" },
    });
    await user.click(screen.getByRole("button", { name: "Save rule" }));

    await waitFor(() =>
      expect(qualityRulesCreate).toHaveBeenCalledWith({
        entity_type_id: "entity-type-1",
        name: "External ID format",
        field_path: "external_id",
        rule_type: "format",
        configuration: { pattern: "^EXT-[0-9]+$" },
        dimension: "conformity",
        severity: "error",
        weight: "0.75",
        idempotency_key: "mdm-ui:quality-rule-create:entity-key-1",
      })
    );
  });
});
