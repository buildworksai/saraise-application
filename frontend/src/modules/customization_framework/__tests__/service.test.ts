/* eslint-disable @typescript-eslint/no-unsafe-assignment -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
/* eslint-disable @typescript-eslint/unbound-method -- assertions intentionally reference mocked client methods. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type ApiV2Envelope,
  type CustomFieldDefinition,
  type RuntimeConfiguration,
} from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

vi.mock("@/services/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const field: CustomFieldDefinition = {
  id: "00000000-0000-4000-8000-000000000001",
  tenant_id: "00000000-0000-4000-8000-000000000002",
  key: "delivery-note",
  label: "Delivery note",
  description: "",
  owner_module: "sales_management",
  target_resource: "sales_order",
  target_contract_version: "1.0",
  data_type: "text",
  required: false,
  searchable: true,
  default_value: null,
  validation_schema: { maxLength: 160 },
  presentation_schema: { label: "Delivery note" },
  status: "active",
  activated_at: "2026-07-22T00:00:00Z",
  deprecated_at: null,
  retired_at: null,
  transition_history: [],
  dependency_count: 2,
  value_count: 5,
  capability_state: "available",
  created_by: "00000000-0000-4000-8000-000000000003",
  updated_by: "00000000-0000-4000-8000-000000000003",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  deleted_at: null,
  deleted_by: null,
  lock_version: 3,
};
const envelope: ApiV2Envelope<readonly CustomFieldDefinition[]> = {
  data: [field],
  meta: {
    correlation_id: "00000000-0000-4000-8000-000000000004",
    timestamp: "2026-07-22T00:00:00Z",
    pagination: {
      count: 1,
      page: 2,
      page_size: 25,
      total_pages: 2,
      has_next: false,
      has_previous: true,
    },
  },
};
const runtimeConfiguration: RuntimeConfiguration = {
  id: "00000000-0000-4000-8000-000000000010",
  tenant_id: "00000000-0000-4000-8000-000000000002",
  version: 1,
  environment: "default",
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
  updated_by: "00000000-0000-4000-8000-000000000003",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
};

describe("customization framework service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("preserves governed envelopes and emits typed server query state", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope);
    await expect(
      service.listFields({ status: "active", search: "delivery", ordering: "label", page: 2 })
    ).resolves.toEqual(envelope);
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.FIELD_DEFINITIONS.LIST}?status=active&search=delivery&ordering=label&page=2`
    );
  });

  it("uses PATCH with optimistic-lock payloads", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ data: field, meta: envelope.meta });
    await service.updateField(field.id, { label: "Dispatch note", expected_lock_version: 3 });
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.FIELD_DEFINITIONS.UPDATE(field.id),
      { label: "Dispatch note", expected_lock_version: 3 },
      expect.objectContaining({
        headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }),
      })
    );
  });

  it("unwraps singleton configuration envelopes before page rendering", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: runtimeConfiguration,
      meta: envelope.meta,
    });

    await expect(service.getConfiguration()).resolves.toEqual(runtimeConfiguration);
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.DETAIL);
  });

  it("targets exact lifecycle and non-persisting validation endpoints", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: field, meta: envelope.meta });
    await service.transitionField(field.id, "deprecate", { transition_key: "transition-1" });
    await service.validateValue(field.id, { value: "safe" });
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.FIELD_DEFINITIONS.DEPRECATE(field.id),
      { transition_key: "transition-1" },
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.FIELD_DEFINITIONS.VALIDATE_VALUE(field.id),
      { value: "safe" }
    );
  });

  it("does not fabricate execution deletion or mutation methods", () => {
    expect("deleteExecution" in service).toBe(false);
    expect("updateExecution" in service).toBe(false);
  });
});
