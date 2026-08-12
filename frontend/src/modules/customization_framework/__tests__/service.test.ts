/* eslint-disable max-lines-per-function -- service contract tests intentionally keep endpoint call sequences together. */
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

  it("routes form create, layout, publish, archive, render schema, and delete commands to governed endpoints", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "form-1" }, meta: envelope.meta });
    vi.mocked(apiClient.get).mockResolvedValue({ data: { sections: [] }, meta: envelope.meta });
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await service.createForm({
      key: "asset-intake",
      name: "Asset intake",
      description: "Operator intake",
      owner_module: "fixed_assets",
      target_resource: "asset",
      target_contract_version: "1.0",
    });
    await service.createFormLayout("form-1", {
      layout: {
        schema_version: 1,
        sections: [
          {
            id: "main",
            title: "Main",
            components: [
              {
                id: "delivery-note",
                type: "field",
                field_key: "delivery_note",
                label: "Delivery note",
                accessibility_label: "Delivery note",
                width: 12,
              },
            ],
          },
        ],
      },
      change_summary: "Initial governed layout",
    });
    await service.publishForm("form-1", {
      layout_version_id: "layout-1",
      transition_key: "publish-1",
    });
    await service.archiveForm("form-1", {
      transition_key: "archive-1",
    });
    await service.getRenderSchema("form-1");
    await service.deleteForm("form-1", 9);

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.FORMS.CREATE,
      expect.objectContaining({ key: "asset-intake", target_resource: "asset" }),
      expect.objectContaining({
        headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }),
      })
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.FORMS.LAYOUT_VERSIONS("form-1"),
      expect.objectContaining({ change_summary: "Initial governed layout" }),
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.FORMS.PUBLISH("form-1"),
      expect.objectContaining({ transition_key: "publish-1" }),
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.FORMS.ARCHIVE("form-1"),
      expect.objectContaining({ transition_key: "archive-1" }),
      expect.any(Object)
    );
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.FORMS.RENDER_SCHEMA("form-1"));
    expect(apiClient.delete).toHaveBeenCalledWith(
      `${ENDPOINTS.FORMS.DELETE("form-1")}?expected_lock_version=9`,
      expect.any(Object)
    );
  });

  it("routes rule versioning, publishing, lifecycle, evaluation, impact, and execution queries", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { id: "rule-version-1" },
      meta: envelope.meta,
    });
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: envelope.meta });

    await service.createRule({
      key: "reject-invalid-credit",
      name: "Reject invalid credit",
      description: "Credit guard",
      owner_module: "sales_management",
      target_resource: "sales_order",
      target_contract_version: "1.0",
      trigger: "validate",
      priority: 10,
      stop_on_match: true,
    });
    await service.createRuleVersion("rule-1", {
      condition_ast: { operator: "eq", field: "status", value: "draft" },
      action_ast: [{ type: "reject-with-message", message: "Invalid credit" }],
      change_summary: "Add credit guard",
    });
    await service.publishRule("rule-1", {
      version_id: "rule-version-1",
      transition_key: "publish-rule-1",
    });
    await service.transitionRule("rule-1", "pause", {
      transition_key: "pause-1",
    });
    await service.evaluateRule("rule-1", {
      record: { status: "draft" },
      changed_fields: ["status"],
      idempotency_key: "evaluate-1",
    });
    await service.getRuleImpact("rule-1");
    await service.listRuleVersionCatalog({ status: "candidate", page: 2 });
    await service.listExecutions({ rule_id: "rule-1", status: "rejected", page_size: 10 });

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.RULES.CREATE,
      expect.objectContaining({ key: "reject-invalid-credit", priority: 10 }),
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.RULES.VERSIONS("rule-1"),
      expect.objectContaining({ change_summary: "Add credit guard" }),
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.RULES.PUBLISH("rule-1"),
      expect.objectContaining({ transition_key: "publish-rule-1" }),
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.RULES.PAUSE("rule-1"),
      expect.objectContaining({ transition_key: "pause-1" }),
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(5, ENDPOINTS.RULES.EVALUATE("rule-1"), {
      record: { status: "draft" },
      changed_fields: ["status"],
      idempotency_key: "evaluate-1",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.RULES.IMPACT("rule-1"));
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.RULE_VERSIONS.LIST}?status=candidate&page=2`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.RULE_EXECUTIONS.LIST}?rule_id=rule-1&status=rejected&page_size=10`
    );
  });

  it("routes value mutations and configuration import/export/rollback without losing envelope semantics", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: runtimeConfiguration,
      meta: envelope.meta,
    });
    vi.mocked(apiClient.patch).mockResolvedValue({
      data: runtimeConfiguration,
      meta: envelope.meta,
    });
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { kind: "customization-configuration" },
      meta: envelope.meta,
    });
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await service.createValue({
      definition_id: field.id,
      target_record_id: "sales-order-1",
      value: "handle with care",
      source: "ui",
    });
    await service.updateValue("value-1", {
      value: "fragile",
      expected_lock_version: 2,
    });
    await service.deleteValue("value-1", 3);
    await service.previewConfiguration({
      document: runtimeConfiguration.document,
    });
    await service.updateConfiguration({
      environment: "development",
      document: runtimeConfiguration.document,
      expected_version: 1,
    });
    await service.rollbackConfiguration({ target_version: 1, expected_version: 2 });
    await service.importConfiguration({
      payload: {
        schema: "saraise.customization-framework.configuration",
        tenant_id: runtimeConfiguration.tenant_id,
        version: 1,
        environment: "development",
        document: runtimeConfiguration.document,
      },
      expected_version: 3,
    });
    await service.exportConfiguration();

    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.FIELD_VALUES.CREATE,
      expect.objectContaining({
        definition_id: field.id,
        target_record_id: "sales-order-1",
        value: "handle with care",
      }),
      expect.any(Object)
    );
    expect(apiClient.patch).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.FIELD_VALUES.UPDATE("value-1"),
      expect.objectContaining({ expected_lock_version: 2 }),
      expect.any(Object)
    );
    expect(apiClient.delete).toHaveBeenCalledWith(
      `${ENDPOINTS.FIELD_VALUES.DELETE("value-1")}?expected_lock_version=3`,
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.CONFIGURATION.PREVIEW,
      expect.objectContaining({ document: runtimeConfiguration.document }),
      expect.any(Object)
    );
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.UPDATE,
      expect.objectContaining({ environment: "development", expected_version: 1 }),
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.CONFIGURATION.ROLLBACK,
      { target_version: 1, expected_version: 2 },
      expect.any(Object)
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.CONFIGURATION.IMPORT,
      expect.objectContaining({ expected_version: 3, payload: expect.any(Object) }),
      expect.any(Object)
    );
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.EXPORT);
  });
});
