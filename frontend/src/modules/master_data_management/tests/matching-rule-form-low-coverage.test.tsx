/* eslint-disable max-lines-per-function, @typescript-eslint/no-unsafe-assignment -- focused form tests assert service payloads and validation state. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import { MatchingRuleForm } from "../components/MatchingRuleForm";
import type { MasterDataConfiguration, MasterEntityType, MatchingRule } from "../contracts";
import { masterDataService } from "../services/master-data-service";

vi.mock("../services/master-data-service", () => ({
  masterDataService: {
    configuration: { current: vi.fn() },
    entityTypes: { list: vi.fn() },
    matchingRules: { create: vi.fn(), update: vi.fn() },
  },
}));

const stamp = "2026-01-01T00:00:00Z";
const configuration: MasterDataConfiguration = {
  id: "config-1",
  tenant_id: "tenant-1",
  version: 3,
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
      allowed_json_schema_keywords: ["type", "properties"],
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
      rule_schemas: {},
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
      defaults: { algorithm: "exact", review_threshold: "0.80", auto_confirm_threshold: "0.95" },
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
      job_poll_statuses: ["queued"],
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
      roles: ["steward"],
      cohorts: ["pilot"],
      percentage: 25,
    },
  },
};
const entityType: MasterEntityType = {
  id: "customer-type",
  tenant_id: "tenant-1",
  key: "customer",
  display_name: "Customer",
  description: "Customer master",
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
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: null,
};
const existingRule: MatchingRule = {
  id: "rule-1",
  tenant_id: "tenant-1",
  entity_type: "customer-type",
  name: "Customer match",
  algorithm: "fuzzy",
  field_weights: { email: 0.7, phone: 0.3 },
  blocking_fields: ["email"],
  review_threshold: "0.70",
  auto_confirm_threshold: "0.90",
  is_active: true,
  is_deleted: false,
  deleted_at: null,
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: null,
};

function envelope<T>(data: T) {
  return { data, meta: { correlation_id: "corr-mdm", timestamp: stamp } };
}

function list<T>(items: T[]) {
  return {
    items,
    meta: { correlation_id: "corr-mdm", timestamp: stamp },
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
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
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

describe("MatchingRuleForm low coverage behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "idem-mdm-test") });
    vi.mocked(masterDataService.configuration.current).mockResolvedValue(envelope(configuration));
    vi.mocked(masterDataService.entityTypes.list).mockResolvedValue(list([entityType]));
    vi.mocked(masterDataService.matchingRules.create).mockResolvedValue(envelope(existingRule));
    vi.mocked(masterDataService.matchingRules.update).mockResolvedValue(envelope(existingRule));
  });

  it("blocks invalid weight and threshold combinations before create", async () => {
    const user = userEvent.setup();
    renderForm(<MatchingRuleForm />);

    await screen.findByRole("heading", { name: "Create matching rule" });
    await user.selectOptions(screen.getByLabelText("Entity type"), "customer-type");
    await user.type(screen.getByLabelText("Rule name"), "Customer match");
    await user.clear(screen.getByLabelText("Review threshold"));
    await user.type(screen.getByLabelText("Review threshold"), "0.99");
    await user.click(screen.getByRole("button", { name: "Add field" }));
    await user.type(screen.getByLabelText("Matching field 1"), "email");
    await user.type(screen.getByLabelText("Weight 1"), "0.50");
    await user.click(screen.getByRole("button", { name: "Save rule" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Weights must sum to 1.0");
    expect(masterDataService.matchingRules.create).not.toHaveBeenCalled();
  });

  it("creates a matching rule with weighted and blocking fields", async () => {
    const user = userEvent.setup();
    renderForm(<MatchingRuleForm />);

    await screen.findByRole("heading", { name: "Create matching rule" });
    await user.selectOptions(screen.getByLabelText("Entity type"), "customer-type");
    await user.type(screen.getByLabelText("Rule name"), "Customer match");
    await user.click(screen.getByRole("button", { name: "Add field" }));
    await user.type(screen.getByLabelText("Matching field 1"), "email");
    await user.type(screen.getByLabelText("Weight 1"), "1.0");
    await user.click(screen.getByLabelText("Blocking field"));
    await user.click(screen.getByRole("button", { name: "Save rule" }));

    await waitFor(() =>
      expect(masterDataService.matchingRules.create).toHaveBeenCalledWith(
        expect.objectContaining({
          entity_type_id: "customer-type",
          name: "Customer match",
          algorithm: "exact",
          field_weights: { email: 1 },
          blocking_fields: ["email"],
          review_threshold: 0.8,
          auto_confirm_threshold: 0.95,
          idempotency_key: "mdm-ui:matching-rule-create:idem-mdm-test",
        })
      )
    );
    expect(await screen.findByText("navigated")).toBeVisible();
  });

  it("updates an existing rule and exposes mutation failures", async () => {
    vi.mocked(masterDataService.matchingRules.update).mockRejectedValue(
      new ApiError("Version conflict", 409, undefined, "VERSION_CONFLICT", "corr-conflict")
    );
    const user = userEvent.setup();
    renderForm(<MatchingRuleForm existing={existingRule} />);

    await screen.findByRole("heading", { name: "Edit matching rule" });
    expect(screen.getByLabelText("Entity type")).toBeDisabled();
    await user.clear(screen.getByLabelText("Rule name"));
    await user.type(screen.getByLabelText("Rule name"), "Updated customer match");
    await user.click(screen.getByRole("button", { name: "Remove field 2" }));
    await user.clear(screen.getByLabelText("Weight 1"));
    await user.type(screen.getByLabelText("Weight 1"), "1.0");
    await user.click(screen.getByRole("button", { name: "Save rule" }));

    await waitFor(() =>
      expect(masterDataService.matchingRules.update).toHaveBeenCalledWith("rule-1", {
        changes: expect.objectContaining({
          name: "Updated customer match",
          algorithm: "fuzzy",
          field_weights: { email: 1 },
          blocking_fields: ["email"],
        }),
        idempotency_key: "mdm-ui:matching-rule-update:idem-mdm-test",
      })
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Concurrent change detected");
    expect(screen.getByRole("alert")).toHaveTextContent("corr-conflict");
  });
});
