/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method -- Service contract coverage intentionally exercises the full method surface with mocks. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type GovernedEnvelope,
  type WorkflowConfigurationDocument,
  type WorkflowListDTO,
} from "../contracts";
import { WorkflowApiError, workflowService } from "./workflow-service";

vi.mock("@/services/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      readonly status: number,
      readonly details?: unknown,
      readonly code?: string,
      readonly correlationId?: string
    ) {
      super(message);
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), put: vi.fn() },
}));

const workflow: WorkflowListDTO = {
  id: "workflow-1",
  key: "purchase_approval",
  version: 2,
  name: "Purchase approval",
  description: "Govern purchasing",
  workflow_type: "approval",
  trigger_type: "manual",
  trigger_config: {},
  status: "published",
  step_count: 2,
  created_by_name: "Asha",
  published_at: "2026-07-22T00:00:00Z",
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  allowed_actions: ["view", "clone", "start"],
};
const envelope: GovernedEnvelope<readonly WorkflowListDTO[]> = {
  data: [workflow],
  meta: {
    correlation_id: "corr-list",
    timestamp: "2026-07-22T00:00:00Z",
    pagination: {
      count: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
  },
};

describe("workflow service governed contract", () => {
  beforeEach(() => vi.clearAllMocks());
  it("unwraps list evidence and sends server-side filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope);
    const result = await workflowService.workflows.list({ status: "published", page: 2 });
    expect(result.items).toEqual([workflow]);
    expect(result.correlationId).toBe("corr-list");
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.WORKFLOWS.LIST}?status=published&page=2`
    );
  });
  it("omits empty query strings while preserving configuration environment defaults", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: envelope.meta });

    await workflowService.workflows.list();
    await workflowService.instances.list({ search: "", page_size: undefined });
    await workflowService.tasks.list({});
    await workflowService.catalog.assignees();
    await workflowService.catalog.lookup("manufacturing.work-centres");
    await workflowService.configuration.get();
    await workflowService.configuration.history();
    await workflowService.configuration.exportDocument();

    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.WORKFLOWS.LIST);
    expect(apiClient.get).toHaveBeenNthCalledWith(2, ENDPOINTS.INSTANCES.LIST);
    expect(apiClient.get).toHaveBeenNthCalledWith(3, ENDPOINTS.TASKS.LIST);
    expect(apiClient.get).toHaveBeenNthCalledWith(4, ENDPOINTS.CATALOG.ASSIGNEES);
    expect(apiClient.get).toHaveBeenNthCalledWith(
      5,
      ENDPOINTS.CATALOG.LOOKUP("manufacturing.work-centres")
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      6,
      `${ENDPOINTS.CONFIGURATION.GET}?environment=production`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      7,
      `${ENDPOINTS.CONFIGURATION.HISTORY}?environment=production`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(
      8,
      `${ENDPOINTS.CONFIGURATION.EXPORT}?environment=production`
    );
  });
  it("fails explicitly when pagination evidence is missing", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [],
      meta: { correlation_id: "corr-bad", timestamp: "2026-07-22T00:00:00Z" },
    });
    await expect(workflowService.tasks.list()).rejects.toMatchObject({
      name: "WorkflowApiError",
      code: "invalid_response",
      correlationId: "corr-bad",
      fieldErrors: [],
      message: "The API response omitted pagination evidence.",
      retryable: false,
      status: 502,
    });
  });
  it("preserves stable correlation and field errors", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(
      new ApiError("failed", 409, {
        error: {
          code: "edit_conflict",
          message: "Newer revision",
          detail: {
            field_errors: [{ field: "expected_updated_at", code: "stale", message: "Reload" }],
          },
          correlation_id: "corr-conflict",
        },
      })
    );
    const failure = await workflowService.workflows
      .clone("workflow-1")
      .catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(WorkflowApiError);
    expect(failure).toMatchObject({
      name: "WorkflowApiError",
      status: 409,
      code: "edit_conflict",
      correlationId: "corr-conflict",
      retryable: false,
      fieldErrors: [{ field: "expected_updated_at", code: "stale", message: "Reload" }],
    });
  });
  it("drops malformed governed field errors while preserving retryable conflicts", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(
      new ApiError("failed", 503, {
        error: {
          code: "capacity_guard",
          message: "External capacity guard rejected the request.",
          detail: {
            field_errors: [
              null,
              [],
              { field: "handler", code: "missing", message: "Choose a handler." },
              { field: "timeout", code: "invalid" },
              { field: 42, code: "invalid", message: "Wrong field type." },
              { field: "retry", code: 42, message: "Wrong code type." },
            ],
            retryable: true,
          },
          correlation_id: "corr-capacity",
        },
      })
    );

    await expect(workflowService.workflows.clone("workflow-1")).rejects.toMatchObject({
      status: 503,
      code: "capacity_guard",
      correlationId: "corr-capacity",
      retryable: true,
      fieldErrors: [{ field: "handler", code: "missing", message: "Choose a handler." }],
    });
  });
  it("fails closed to fallback API errors for malformed governed error shapes", async () => {
    const malformedDetails = [
      null,
      [],
      { error: [] },
      { error: { code: 404, message: "Bad code", correlation_id: "corr-bad-code" } },
      { error: { code: "missing_message", correlation_id: "corr-missing-message" } },
      { error: { code: "missing_correlation", message: "Missing correlation" } },
    ];

    for (const details of malformedDetails) {
      vi.mocked(apiClient.post).mockRejectedValueOnce(
        new ApiError("gateway failure", 500, details, undefined, "corr-fallback")
      );

      await expect(workflowService.workflows.clone("workflow-1")).rejects.toMatchObject({
        code: "request_failed",
        correlationId: "corr-fallback",
        fieldErrors: [],
        message: "gateway failure",
        retryable: true,
        status: 500,
      });
    }
  });
  it("does not mark non-retryable client failures as retryable when fallback metadata is used", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(
      new ApiError("bad request", 400, { error: [] }, "invalid_request", "corr-client")
    );

    await expect(workflowService.workflows.clone("workflow-1")).rejects.toMatchObject({
      code: "invalid_request",
      correlationId: "corr-client",
      retryable: false,
      status: 400,
    });
  });
  it("falls back safely for malformed governed and ungoverned API failures", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(
      new ApiError(
        "bad gateway",
        502,
        { error: { code: 404, message: null, correlation_id: "corr-invalid" } },
        undefined,
        "corr-fallback"
      )
    );
    await expect(workflowService.workflows.clone("workflow-1")).rejects.toMatchObject({
      code: "request_failed",
      correlationId: "corr-fallback",
      message: "bad gateway",
      retryable: true,
    });
    vi.mocked(apiClient.post).mockRejectedValueOnce(new Error("socket closed"));
    await expect(workflowService.workflows.clone("workflow-1")).rejects.toThrow("socket closed");
  });
  it("propagates governed configuration rollback failures with retry evidence", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(
      new ApiError("rollback failed", 412, {
        error: {
          code: "configuration_version_conflict",
          message: "Configuration changed before rollback.",
          detail: {
            field_errors: [
              { field: "expected_version", code: "stale", message: "Reload configuration." },
            ],
            retryable: false,
          },
          correlation_id: "corr-rollback",
        },
      })
    );

    await expect(workflowService.configuration.rollback("production", 5, 3)).rejects.toMatchObject({
      status: 412,
      code: "configuration_version_conflict",
      correlationId: "corr-rollback",
      retryable: false,
      fieldErrors: [{ field: "expected_version", code: "stale", message: "Reload configuration." }],
    });
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.ROLLBACK, {
      environment: "production",
      expected_version: 5,
      target_version: 3,
    });
  });
  it("uses the governed catalog for paid extension discovery", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: envelope.meta });
    await workflowService.catalog.actions();
    await workflowService.catalog.lookup("manufacturing.work-centres", "line");
    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.CATALOG.ACTIONS);
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.CATALOG.LOOKUP("manufacturing.work-centres")}?search=line`
    );
  });
  it("maps workflow lifecycle methods to governed endpoints", async () => {
    const detailEnvelope = { data: { ...workflow, step_count: undefined }, meta: envelope.meta };
    vi.mocked(apiClient.get).mockResolvedValue(detailEnvelope);
    vi.mocked(apiClient.post).mockResolvedValue(detailEnvelope);
    vi.mocked(apiClient.patch).mockResolvedValue(detailEnvelope);
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await workflowService.workflows.get("workflow-1");
    await workflowService.workflows.create({
      key: "purchase_approval",
      name: "Purchase approval",
      workflow_type: "approval",
      trigger_type: "manual",
      trigger_config: {},
      steps: [],
    });
    await workflowService.workflows.update("workflow-1", {
      expected_updated_at: workflow.updated_at,
      name: "Purchase approval v3",
    });
    await workflowService.workflows.validate({
      key: "purchase_approval",
      name: "Purchase approval",
      workflow_type: "approval",
      trigger_type: "manual",
      trigger_config: {},
      steps: [],
    });
    await workflowService.workflows.publish("workflow-1", { transition_key: "publish-1" });
    await workflowService.workflows.archive("workflow-1", { transition_key: "archive-1" });
    await workflowService.workflows.clone("workflow-1", { name: "Copy" });
    await workflowService.workflows.delete("workflow-1");

    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.WORKFLOWS.DETAIL("workflow-1"));
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.WORKFLOWS.CREATE, expect.any(Object));
    expect(apiClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.WORKFLOWS.UPDATE("workflow-1"),
      expect.objectContaining({ name: "Purchase approval v3" })
    );
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.WORKFLOWS.VALIDATE, expect.any(Object));
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.WORKFLOWS.PUBLISH("workflow-1"), {
      transition_key: "publish-1",
    });
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.WORKFLOWS.ARCHIVE("workflow-1"), {
      transition_key: "archive-1",
    });
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.WORKFLOWS.CLONE("workflow-1"), {
      name: "Copy",
    });
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.WORKFLOWS.DELETE("workflow-1"));
  });
  it("maps instance and task command methods to idempotent endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: envelope.meta });
    vi.mocked(apiClient.post).mockResolvedValue({ data: {}, meta: envelope.meta });

    await workflowService.instances.list({ state: "waiting", page: 2 });
    await workflowService.instances.get("instance-1");
    await workflowService.instances.start({
      workflow_id: "workflow-1",
      context_data: {},
      idempotency_key: "idem-1",
      priority: 5,
    });
    await workflowService.instances.cancel("instance-1", {
      transition_key: "cancel-1",
      reason: "operator",
    });
    await workflowService.tasks.list({ scope: "mine", overdue: true });
    await workflowService.tasks.get("task-1");
    await workflowService.tasks.complete("task-1", {
      meta_data: {},
      transition_key: "complete-1",
    });
    await workflowService.tasks.reject("task-1", {
      reason: "policy",
      meta_data: {},
      transition_key: "reject-1",
    });

    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.INSTANCES.LIST}?state=waiting&page=2`);
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.INSTANCES.DETAIL("instance-1"));
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.INSTANCES.START, {
      workflow_id: "workflow-1",
      context_data: {},
      idempotency_key: "idem-1",
      priority: 5,
    });
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.INSTANCES.CANCEL("instance-1"), {
      transition_key: "cancel-1",
      reason: "operator",
    });
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.TASKS.LIST}?scope=mine&overdue=true`);
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.TASKS.DETAIL("task-1"));
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.TASKS.COMPLETE("task-1"), {
      meta_data: {},
      transition_key: "complete-1",
    });
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.TASKS.REJECT("task-1"), {
      reason: "policy",
      meta_data: {},
      transition_key: "reject-1",
    });
  });
  it("maps catalog and configuration operations to governed endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: envelope.meta });
    vi.mocked(apiClient.post).mockResolvedValue({ data: {}, meta: envelope.meta });
    vi.mocked(apiClient.put).mockResolvedValue({ data: {}, meta: envelope.meta });
    const document: WorkflowConfigurationDocument = {
      defaults: {
        workflow_version: 1,
        workflow_type: "approval",
        trigger_type: "manual",
        definition_status: "draft",
        execution_priority: 5,
        step_execution_attempt: 1,
        approval_assignment_kind: "role",
        approval_due_seconds: 86400,
        approval_rejection_behavior: "fail",
        approval_completion_rule: "any",
        timeout_action: "notify",
        cancellation_reason: "No longer required",
        task_status: "pending",
        task_ordering: "due_date",
        task_scope: "mine",
      },
      limits: {
        execution_priority_min: 1,
        execution_priority_max: 10,
        json_max_depth: 8,
        json_max_items: 100,
        json_max_string_length: 500,
        reject_reason_max_length: 250,
        duration_max_seconds: 2592000,
        transition_key_max_length: 120,
        failure_message_max_length: 500,
        cancellation_reason_max_length: 250,
        catalog_default_limit: 20,
        catalog_max_limit: 100,
        catalog_search_max_length: 120,
        assignee_result_limit: 25,
        email_template_key_max_length: 120,
        email_recipient_max_length: 200,
        generated_step_key_max_length: 64,
        workflow_page_size: 20,
        execution_step_multiplier: 3,
      },
      allowed_values: {
        workflow_types: ["approval"],
        trigger_types: ["manual"],
        definition_statuses: ["draft", "published", "archived"],
        step_types: ["approval"],
        timeout_actions: ["notify"],
        approval_rejection_behaviors: ["fail"],
        approval_completion_rules: ["any"],
        notification_channels: ["in_app"],
        catalog_orderings: ["key"],
      },
      trigger_schemas: {},
      step_schemas: {},
      notification_handlers: {},
      step_handlers: {},
      condition_input_mappings: {},
      lifecycle: {},
      allowed_actions: {},
      action_quota_costs: {},
      operational: {
        api_quota_cost: 1,
        v1_sunset: "2027-01-01T00:00:00Z",
        outbox_stale_seconds: 300,
        health_staleness_seconds: 300,
        email_timeout_seconds: 15,
        email_retry_attempts: 3,
        email_retry_base_ms: 250,
        email_circuit_failure_threshold: 5,
        email_circuit_reset_seconds: 60,
        execution_poll_interval_ms: 30000,
        execution_detail_poll_interval_ms: 10000,
      },
      ui: {
        sidebar_orders: { workflows: 80, instances: 81, tasks: 82, configuration: 83 },
        duration_display_threshold_ms: 1000,
        due_time_unit_seconds: 3600,
        minimum_due_time_units: 1,
        reject_reason_max_length: 250,
      },
      feature_flags: {},
    };

    await workflowService.catalog.conditions();
    await workflowService.catalog.subjects();
    await workflowService.catalog.assignees("asha");
    await workflowService.configuration.get("staging");
    await workflowService.configuration.update({
      environment: "staging",
      expected_version: 3,
      change_reason: "test",
      document,
    });
    await workflowService.configuration.preview({ environment: "staging", document });
    await workflowService.configuration.history("staging");
    await workflowService.configuration.rollback("staging", 3, 2);
    await workflowService.configuration.importDocument({
      environment: "staging",
      expected_version: 3,
      change_reason: "import",
      document,
    });
    await workflowService.configuration.exportDocument("staging");

    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.CATALOG.CONDITIONS);
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.CATALOG.SUBJECTS);
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.CATALOG.ASSIGNEES}?search=asha`);
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.GET}?environment=staging`
    );
    expect(apiClient.put).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.UPDATE,
      expect.objectContaining({ change_reason: "test" })
    );
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.PREVIEW, {
      environment: "staging",
      document,
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.HISTORY}?environment=staging`
    );
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.ROLLBACK, {
      environment: "staging",
      expected_version: 3,
      target_version: 2,
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.IMPORT,
      expect.objectContaining({ change_reason: "import" })
    );
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.EXPORT}?environment=staging`
    );
  });
});
