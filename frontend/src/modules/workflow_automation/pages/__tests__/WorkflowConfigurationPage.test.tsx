/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method -- Workflow configuration scenarios intentionally exercise broad UI flows with service spies. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WorkflowConfigurationDocument, WorkflowConfigurationDTO } from "../../contracts";
import { WorkflowApiError, workflowService } from "../../services/workflow-service";
import { WorkflowConfigurationPage } from "../WorkflowConfigurationPage";

const documentFixture: WorkflowConfigurationDocument = {
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
    execution_priority_max: 9,
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
    workflow_types: ["approval", "parallel"],
    trigger_types: ["manual", "event", "scheduled"],
    definition_statuses: ["draft", "published", "archived"],
    step_types: ["action", "approval", "notification", "decision"],
    timeout_actions: ["fail", "notify"],
    approval_rejection_behaviors: ["fail", "goto", "cancel"],
    approval_completion_rules: ["any", "all"],
    notification_channels: ["in_app", "email"],
    catalog_orderings: ["key", "display_name"],
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
  feature_flags: {
    event_triggers: { enabled: false, roles: ["workflow-admin"], cohorts: ["pilot"] },
    scheduled_triggers: { enabled: false, roles: [], cohorts: [] },
    parallel_workflows: { enabled: false, roles: [], cohorts: [] },
    timeout_notifications: { enabled: true, roles: [], cohorts: [] },
    unavailable_extension: { enabled: false, roles: [], cohorts: [] },
  },
};

const configuration: WorkflowConfigurationDTO = {
  id: "configuration-1",
  tenant_id: "tenant-1",
  environment: "production",
  version: 3,
  document: documentFixture,
  updated_by: "user-1",
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <WorkflowConfigurationPage />
    </QueryClientProvider>
  );
}

describe("WorkflowConfigurationPage", () => {
  beforeEach(() => {
    vi.spyOn(workflowService.configuration, "get").mockResolvedValue(configuration);
    vi.spyOn(workflowService.configuration, "history").mockResolvedValue([
      {
        id: "revision-2",
        version: 2,
        previous_document: {},
        document: documentFixture,
        actor_id: null,
        correlation_id: "corr-config",
        change_reason: "bootstrap",
        created_at: "2026-07-22T00:00:00Z",
      },
      {
        id: "revision-3",
        version: 3,
        previous_document: documentFixture,
        document: documentFixture,
        actor_id: "user-1",
        correlation_id: "corr-current",
        change_reason: "operator-policy-change",
        created_at: "2026-07-23T00:00:00Z",
      },
    ]);
    vi.spyOn(workflowService.configuration, "preview").mockResolvedValue({
      valid: true,
      current_version: 3,
      changed_sections: ["limits", "feature_flags"],
      restart_required: false,
    });
    vi.spyOn(workflowService.configuration, "update").mockResolvedValue(configuration);
    vi.spyOn(workflowService.configuration, "rollback").mockResolvedValue(configuration);
    vi.spyOn(workflowService.configuration, "exportDocument").mockResolvedValue({
      schema: "saraise.workflow-automation.configuration/v1",
      environment: "production",
      version: 3,
      document: documentFixture,
    });
    vi.spyOn(workflowService.configuration, "importDocument").mockResolvedValue(configuration);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:workflow-config"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => vi.restoreAllMocks());

  it("edits guarded values, previews, saves, rolls back, exports, and imports", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Workflow configuration" })
    ).toBeInTheDocument();
    const priorityMinimum = screen.getAllByRole("spinbutton").at(2);
    if (!priorityMinimum) throw new Error("Priority minimum input was not rendered.");
    await user.clear(priorityMinimum);
    await user.type(priorityMinimum, "2");
    await user.click(screen.getByRole("checkbox", { name: /event triggers/u }));
    const roleInputs = screen.getAllByDisplayValue("workflow-admin");
    const roleInput = roleInputs.at(0);
    if (!roleInput) throw new Error("Role rollout input was not rendered.");
    await user.clear(roleInput);
    await user.type(roleInput, "finance-admin,ops-lead");
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText(/Changed sections: limits, feature_flags/u)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Apply version" }));
    await waitFor(() =>
      expect(workflowService.configuration.update).toHaveBeenCalledWith(
        expect.objectContaining({
          environment: "production",
          expected_version: 3,
          change_reason: "operator-policy-change",
        })
      )
    );

    const rollbackButton = screen.getAllByRole("button", { name: "Rollback" }).at(0);
    if (!rollbackButton) throw new Error("Rollback button was not rendered.");
    await user.click(rollbackButton);
    expect(workflowService.configuration.rollback).toHaveBeenCalledWith("production", 3, 2);

    const clickedAnchors: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click(
      this: HTMLAnchorElement
    ) {
      clickedAnchors.push(this.download);
    });
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    expect(clickedAnchors).toEqual(["workflow-automation-production-v3.json"]);

    const file = new File(
      [
        JSON.stringify({
          schema: "saraise.workflow-automation.configuration/v1",
          environment: "staging",
          version: 4,
          document: documentFixture,
        }),
      ],
      "workflow-automation-staging.json",
      { type: "application/json" }
    );
    Object.defineProperty(file, "text", {
      configurable: true,
      value: vi.fn(() =>
        Promise.resolve(
          JSON.stringify({
            schema: "saraise.workflow-automation.configuration/v1",
            environment: "staging",
            version: 4,
            document: documentFixture,
          })
        )
      ),
    });
    await user.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, file);
    await waitFor(() =>
      expect(workflowService.configuration.importDocument).toHaveBeenCalledWith(
        expect.objectContaining({
          environment: "staging",
          expected_version: 3,
          change_reason: "configuration-import",
        })
      )
    );
  });

  it("rejects malformed JSON and invalid import documents without saving", async () => {
    const user = userEvent.setup();
    renderPage();

    const policyText = await screen.findByLabelText("Complete workflow configuration document");
    await user.clear(policyText);
    fireEvent.change(policyText, { target: { value: "[]" } });
    await user.click(screen.getByRole("button", { name: "Validate JSON locally" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Document must be an object.");

    const file = new File([JSON.stringify({ schema: "wrong" })], "bad.json", {
      type: "application/json",
    });
    Object.defineProperty(file, "text", {
      configurable: true,
      value: vi.fn(() => Promise.resolve(JSON.stringify({ schema: "wrong" }))),
    });
    await user.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, file);
    expect(
      await screen.findByText("This is not a workflow automation configuration export.")
    ).toBeInTheDocument();
    expect(workflowService.configuration.importDocument).not.toHaveBeenCalled();
  });

  it("fails closed on rejected configuration fetches and array-shaped import documents", async () => {
    vi.mocked(workflowService.configuration.get).mockRejectedValueOnce(
      new WorkflowApiError("Configuration service down", 503, "down", "corr-config-down", [], true)
    );
    const rejected = renderPage();

    expect(await screen.findByText("Workflow capability unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-config-down/u)).toBeInTheDocument();
    expect(screen.queryByLabelText("Loading workflow configuration")).not.toBeInTheDocument();

    rejected.unmount();
    vi.mocked(workflowService.configuration.get).mockResolvedValueOnce(configuration);
    const user = userEvent.setup();
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Workflow configuration" })
    ).toBeInTheDocument();
    const file = new File(
      [
        JSON.stringify({
          schema: "saraise.workflow-automation.configuration/v1",
          environment: "production",
          version: 3,
          document: [],
        }),
      ],
      "array-document.json",
      { type: "application/json" }
    );
    Object.defineProperty(file, "text", {
      configurable: true,
      value: vi.fn(() =>
        Promise.resolve(
          JSON.stringify({
            schema: "saraise.workflow-automation.configuration/v1",
            environment: "production",
            version: 3,
            document: [],
          })
        )
      ),
    });

    await user.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, file);

    expect(
      await screen.findByText("This is not a workflow automation configuration export.")
    ).toBeInTheDocument();
    expect(workflowService.configuration.importDocument).not.toHaveBeenCalled();
  });

  it("renders an explicit empty audit history state", async () => {
    vi.mocked(workflowService.configuration.history).mockResolvedValueOnce([]);

    renderPage();

    expect(await screen.findByText("No history is available.")).toBeInTheDocument();
  });
});
