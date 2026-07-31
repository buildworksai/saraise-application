/* eslint-disable max-lines-per-function, @typescript-eslint/no-unsafe-assignment, @typescript-eslint/unbound-method -- Broad builder flows intentionally exercise governed UI behavior end to end; Vitest matchers and spies intentionally compose dynamic assertions. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ConditionDescriptorDTO,
  HandlerDescriptorDTO,
  WorkflowConfigurationDTO,
  WorkflowCreateDTO,
  WorkflowDetailDTO,
} from "../contracts";
import { workflowService } from "../services/workflow-service";
import {
  WORKFLOW_CATALOG_ACTIONS_QUERY_KEY,
  WORKFLOW_CATALOG_ASSIGNEES_QUERY_KEY,
  WORKFLOW_CATALOG_CONDITIONS_QUERY_KEY,
} from "./workflow-builder-utils";
import { WorkflowBuilder } from "./WorkflowBuilder";

const configuration: WorkflowConfigurationDTO = {
  id: "configuration-1",
  tenant_id: "tenant-1",
  environment: "production",
  version: 1,
  updated_by: "user-1",
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  document: {
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
      workflow_types: ["approval", "parallel"],
      trigger_types: ["manual", "event", "scheduled"],
      definition_statuses: ["draft", "published", "archived"],
      step_types: ["action", "approval", "notification", "decision"],
      timeout_actions: ["fail", "notify", "escalate", "cancel"],
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
    feature_flags: {},
  },
};

const action: HandlerDescriptorDTO = {
  key: "core.project_context",
  display_name: "Project context",
  description: "Projects context safely",
  category: "Core",
  owning_module: "workflow_automation",
  schema_version: "1.0",
  descriptor_fingerprint: "sha256:action",
  required_permission: "workflow_automation.workflow:create",
  required_entitlement: "module.workflow_automation",
  availability: "available",
  reason: null,
  input_schema: {},
  output_schema: {},
  idempotent: true,
  network_access: false,
  ui_schema: [
    { kind: "text", key: "path", label: "Context path", required: true },
    { kind: "number", key: "limit", label: "Limit", required: true, minimum: 1, maximum: 10 },
    { kind: "boolean", key: "enabled", label: "Enabled", required: false },
    {
      kind: "select",
      key: "mode",
      label: "Mode",
      required: true,
      options: [{ value: "strict", label: "Strict" }],
    },
    { kind: "lookup", key: "target", label: "Target", required: true, lookup_key: "targets" },
  ],
};
const condition: ConditionDescriptorDTO = {
  key: "core.amount_gt",
  display_name: "Amount greater than",
  description: "Compares amount",
  owning_module: "workflow_automation",
  schema_version: "1.0",
  descriptor_fingerprint: "sha256:condition",
  availability: "available",
  reason: null,
  ui_schema: [{ kind: "number", key: "minimum", label: "Minimum", required: true, minimum: 1 }],
};
const lockedAction: HandlerDescriptorDTO = {
  ...action,
  key: "core.locked_action",
  display_name: "Locked action",
  availability: "locked",
  reason: "Tenant entitlement is missing.",
};
const setupRequiredCondition: ConditionDescriptorDTO = {
  ...condition,
  key: "core.setup_required_condition",
  display_name: "Setup required condition",
  availability: "setup_required",
  reason: "Connection setup is incomplete.",
};
const initial: WorkflowDetailDTO = {
  id: "workflow-1",
  key: "purchase_approval",
  version: 2,
  name: "Purchase approval",
  description: "Govern purchasing",
  workflow_type: "approval",
  trigger_type: "manual",
  trigger_config: {},
  status: "draft",
  created_by_name: "Asha",
  published_at: null,
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  allowed_actions: ["view", "edit", "publish", "delete"],
  required_context_schema: {},
  transition_history: [],
  versions: [],
  execution_statistics: { total: 0, active: 0, completed: 0, failed: 0, completion_rate: null },
  handler_health: [],
  steps: [
    {
      id: "step-1",
      key: "project",
      name: "Project context",
      step_type: "action",
      order: 1,
      config: {
        handler: "core.project_context",
        schema_version: "1.0",
        input_mapping: {},
        configuration: {
          path: "amount",
          limit: 2,
          enabled: true,
          mode: "strict",
          target: "role-1",
        },
      },
      timeout_seconds: 300,
      timeout_action: "notify",
      is_terminal: false,
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    },
    {
      id: "step-2",
      key: "approve",
      name: "Manager approval",
      step_type: "approval",
      order: 2,
      config: {
        assignment_kind: "role",
        assignee_id: "role-1",
        due_in_seconds: 7200,
        rejection_behavior: "goto",
        reject_step_key: "notify",
      },
      timeout_seconds: null,
      timeout_action: null,
      is_terminal: false,
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    },
    {
      id: "step-3",
      key: "notify",
      name: "Notify requester",
      step_type: "notification",
      order: 3,
      config: {
        channel: "in_app",
        recipient_mapping: { recipient_id: "actor.id" },
        template_key: "workflow.task.created",
      },
      timeout_seconds: null,
      timeout_action: null,
      is_terminal: false,
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    },
    {
      id: "step-4",
      key: "route",
      name: "Route decision",
      step_type: "decision",
      order: 4,
      config: {
        condition: { handler: "core.amount_gt", minimum: 1000 },
        true_step_key: "approve",
        false_step_key: "notify",
      },
      timeout_seconds: null,
      timeout_action: null,
      is_terminal: true,
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
    },
  ],
};

function renderBuilder(
  overrides: Partial<React.ComponentProps<typeof WorkflowBuilder>> = {},
  options: { seedGovernedQueries?: boolean } = {}
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (options.seedGovernedQueries) {
    client.setQueryData(["workflow-automation", "configuration", "production"], configuration);
    client.setQueryData(WORKFLOW_CATALOG_ACTIONS_QUERY_KEY, [action]);
    client.setQueryData(WORKFLOW_CATALOG_CONDITIONS_QUERY_KEY, [condition]);
    client.setQueryData(WORKFLOW_CATALOG_ASSIGNEES_QUERY_KEY, [
      { id: "role-1", label: "Purchasing managers", description: null, kind: "role" },
      { id: "user-1", label: "Asha", description: null, kind: "user" },
    ]);
  }
  const props: React.ComponentProps<typeof WorkflowBuilder> = {
    initial,
    submitting: false,
    submitLabel: "Save changes",
    onSubmit: vi.fn<(payload: WorkflowCreateDTO) => Promise<void>>(() => Promise.resolve()),
    onCancel: vi.fn(),
    ...overrides,
  };
  const view = render(
    <QueryClientProvider client={client}>
      <WorkflowBuilder {...props} />
    </QueryClientProvider>
  );
  return { ...view, props };
}

describe("WorkflowBuilder", () => {
  beforeEach(() => {
    vi.spyOn(workflowService.configuration, "get").mockResolvedValue(configuration);
    vi.spyOn(workflowService.catalog, "actions").mockResolvedValue([action]);
    vi.spyOn(workflowService.catalog, "conditions").mockResolvedValue([condition]);
    vi.spyOn(workflowService.catalog, "assignees").mockResolvedValue([
      { id: "role-1", label: "Purchasing managers", description: null, kind: "role" },
      { id: "user-1", label: "Asha", description: null, kind: "user" },
    ]);
    vi.spyOn(workflowService.catalog, "lookup").mockResolvedValue([
      { id: "role-1", label: "Purchasing managers", description: null, kind: "role" },
    ]);
    vi.spyOn(workflowService.workflows, "validate").mockResolvedValue({
      valid: true,
      issues: [],
      warnings: [
        {
          code: "late_step",
          severity: "warning",
          message: "Review due date",
          step_key: "approve",
          pointer: "/steps/1",
          remediation: null,
        },
      ],
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("edits every governed step type, validates, submits, reorders, removes, and navigates", async () => {
    const { props } = renderBuilder({}, { seedGovernedQueries: true });

    expect(await screen.findByText("Step palette")).toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toHaveValue("Govern purchasing");
    expect(screen.getByLabelText("Workflow type")).toHaveClass("rounded-md");
    expect(screen.getByLabelText("Trigger")).toHaveClass("rounded-md");
    expect(screen.getByLabelText("Registered action")).toHaveClass("rounded-md");
    expect(screen.getByLabelText("Assignment")).toHaveClass("rounded-md");
    expect(screen.getByLabelText("On rejection")).toHaveClass("rounded-md");
    expect(screen.getByLabelText("Rejection branch")).toHaveClass("rounded-md");
    expect(screen.getByLabelText("Channel")).toHaveClass("rounded-md");
    expect(screen.getByLabelText("Condition")).toHaveClass("rounded-md");
    expect(screen.getByLabelText("True branch")).toHaveClass("rounded-md");
    expect(screen.getByLabelText("False branch")).toHaveClass("rounded-md");
    fireEvent.change(screen.getByLabelText("Registered action"), {
      target: { value: "core.project_context" },
    });
    fireEvent.change(screen.getByLabelText("Context path"), { target: { value: "total" } });
    fireEvent.change(screen.getByLabelText("Limit"), { target: { value: "3" } });
    fireEvent.click(screen.getByLabelText("Enabled"));
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "strict" } });
    fireEvent.change(screen.getByLabelText("Target"), { target: { value: "role-1" } });

    fireEvent.change(screen.getByLabelText("On rejection"), { target: { value: "fail" } });
    fireEvent.change(screen.getByLabelText("Channel"), { target: { value: "email" } });
    expect(screen.getByDisplayValue("actor.email")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Condition"), { target: { value: "core.amount_gt" } });
    fireEvent.change(screen.getByLabelText("Minimum"), { target: { value: "2500" } });

    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("Definition is publishable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(props.onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Purchase approval" })
      )
    );
    const saved = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!saved) throw new Error("Edited workflow payload was not submitted.");
    expect(saved.steps).toEqual([
      expect.objectContaining({
        key: "project",
        order: 1,
        step_type: "action",
        config: expect.objectContaining({
          handler: "core.project_context",
          schema_version: "1.0",
          configuration: {
            enabled: true,
            limit: 3,
            mode: "strict",
            path: "total",
            target: "role-1",
          },
        }),
      }),
      expect.objectContaining({
        key: "approve",
        order: 2,
        step_type: "approval",
        config: expect.objectContaining({
          assignee_id: "role-1",
          assignment_kind: "role",
          due_in_seconds: 7200,
          rejection_behavior: "fail",
          reject_step_key: null,
        }),
      }),
      expect.objectContaining({
        key: "notify",
        order: 3,
        step_type: "notification",
        config: expect.objectContaining({
          channel: "email",
          recipient_mapping: { recipient_email: "actor.email" },
          template_key: "workflow.task.created",
        }),
      }),
      expect.objectContaining({
        key: "route",
        order: 4,
        step_type: "decision",
        config: expect.objectContaining({
          condition: { handler: "core.amount_gt", minimum: 2500 },
          true_step_key: "approve",
          false_step_key: "notify",
        }),
      }),
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Move Manager approval up" }));
    expect(screen.getByRole("button", { name: "Move Manager approval up" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Move Project context down" }));
    expect(
      screen.getAllByLabelText(/Step \d name/u).map((input) => input.getAttribute("value"))
    ).toEqual(["Manager approval", "Notify requester", "Project context", "Route decision"]);
    expect(screen.getByRole("button", { name: "Move Route decision down" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Remove Notify requester" }));
    expect(screen.queryByDisplayValue("Notify requester")).not.toBeInTheDocument();
    expect(screen.getByText("Route decision: select a valid false branch.")).toBeInTheDocument();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(props.onCancel).toHaveBeenCalledWith("/workflow-automation/workflows/workflow-1");
  }, 15_000);

  it("clears timeout values, restores governed defaults, and toggles terminal steps", async () => {
    const { props } = renderBuilder({}, { seedGovernedQueries: true });

    await screen.findByText("Step palette");
    const timeoutInputs = screen.getAllByLabelText("Timeout seconds");
    const firstTimeout = timeoutInputs.at(0);
    const firstTerminal = screen.getAllByLabelText("Terminal step").at(0);
    if (!firstTimeout || !firstTerminal)
      throw new Error("Project step controls were not rendered.");
    fireEvent.change(firstTimeout, { target: { value: "45" } });
    fireEvent.click(firstTerminal);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalled());
    const submitted = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!submitted) throw new Error("Workflow draft payload was not submitted.");
    expect(submitted.steps).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          key: "project",
          is_terminal: true,
          timeout_action: "notify",
          timeout_seconds: 45,
        }),
      ])
    );
  });

  it("keeps unsaved changes after a rejected save and allows retry", async () => {
    const onSubmit = vi
      .fn<(payload: WorkflowCreateDTO) => Promise<void>>()
      .mockRejectedValueOnce(new Error("Save failed"))
      .mockResolvedValueOnce(undefined);
    const { props } = renderBuilder({ onSubmit }, { seedGovernedQueries: true });

    await screen.findByText("Step palette");
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Purchase approval revised" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(confirm).toHaveBeenCalledWith("Discard unsaved workflow changes?");
    expect(props.onCancel).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
    expect(onSubmit).toHaveBeenLastCalledWith(
      expect.objectContaining({ name: "Purchase approval revised" })
    );
  });

  it("submits edited workflow metadata and preserves immutable existing keys", async () => {
    const nonDefaultInitial: WorkflowDetailDTO = {
      ...initial,
      description: "",
      workflow_type: "parallel",
      trigger_type: "event",
    };
    const { props } = renderBuilder({ initial: nonDefaultInitial }, { seedGovernedQueries: true });

    await screen.findByText("Step palette");

    expect(screen.getByLabelText("Name")).toHaveValue("Purchase approval");
    expect(screen.getByLabelText("Stable key")).toHaveValue("purchase_approval");
    expect(screen.getByLabelText("Stable key")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Description")).toHaveValue("");
    expect(screen.getByLabelText("Workflow type")).toHaveValue("parallel");
    expect(screen.getByLabelText("Trigger")).toHaveValue("event");

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Purchase approval revised" },
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Controls ERP purchasing changes" },
    });
    fireEvent.change(screen.getByLabelText("Workflow type"), { target: { value: "parallel" } });
    fireEvent.change(screen.getByLabelText("Trigger"), { target: { value: "event" } });

    expect(screen.getByLabelText("Stable key")).toHaveValue("purchase_approval");

    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toBeEnabled();
    act(() => {
      fireEvent.click(save);
    });

    expect(props.onSubmit).toHaveBeenCalled();
    expect(props.onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        key: "purchase_approval",
        name: "Purchase approval revised",
        description: "Controls ERP purchasing changes",
        workflow_type: "parallel",
        trigger_type: "event",
      })
    );
  });

  it("normalizes new workflow names and stable keys through governed slug rules", async () => {
    const user = userEvent.setup();
    const { props } = renderBuilder({ initial: undefined, submitLabel: "Create workflow" });

    await screen.findByText("Step palette");

    await user.type(screen.getByLabelText("Name"), "  Emergency PO Approval!!!  ");
    expect(screen.getByLabelText("Stable key")).toHaveValue("emergency_po_approval");
    expect(screen.getByLabelText("Description")).toHaveValue("");

    await user.clear(screen.getByLabelText("Stable key"));
    fireEvent.change(screen.getByLabelText("Stable key"), {
      target: { value: "Manual Key / 2026" },
    });
    expect(screen.getByLabelText("Stable key")).toHaveValue("manual_key_2026");

    await user.selectOptions(screen.getByLabelText("Workflow type"), "parallel");
    await user.selectOptions(screen.getByLabelText("Trigger"), "scheduled");
    await user.click(screen.getByRole("button", { name: "Add notification" }));
    const terminal = screen.getByLabelText("Terminal step");
    await user.click(terminal);

    await user.click(screen.getByRole("button", { name: "Create workflow" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalled());
    expect(props.onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        key: "manual_key_2026",
        name: "  Emergency PO Approval!!!  ",
        workflow_type: "parallel",
        trigger_type: "scheduled",
        steps: [
          expect.objectContaining({
            step_type: "notification",
            is_terminal: true,
          }),
        ],
      })
    );
  });

  it("renders the empty builder state and blocks submit until a terminal step exists", async () => {
    const user = userEvent.setup();
    const { props } = renderBuilder({ initial: undefined, submitLabel: "Create workflow" });

    await screen.findByText("Design the first step");

    expect(screen.getByText("Workflow key is required.")).toBeInTheDocument();
    expect(screen.getByText("Workflow name is required.")).toBeInTheDocument();
    expect(screen.getByText("Add at least one step.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create workflow" })).toBeDisabled();

    await user.type(screen.getByLabelText("Name"), "Single notice");
    await user.click(screen.getByRole("button", { name: "Add notification" }));

    expect(screen.queryByText("Design the first step")).not.toBeInTheDocument();
    expect(screen.getByText("Mark at least one step as terminal.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create workflow" })).toBeDisabled();
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("surfaces extension catalog failures and blocks action and decision saves", async () => {
    vi.mocked(workflowService.catalog.actions).mockRejectedValueOnce(new Error("Actions failed"));
    vi.mocked(workflowService.catalog.conditions).mockRejectedValueOnce(
      new Error("Conditions failed")
    );
    const { props } = renderBuilder();

    await screen.findByText(
      "Extension catalog unavailable. Saving action or decision steps is blocked."
    );

    expect(screen.getByLabelText("Registered action")).toHaveTextContent(
      "Select an available action"
    );
    expect(screen.getByLabelText("Condition")).toHaveTextContent("Choose a safe condition");
    expect(screen.getByText("Action catalog is unavailable.")).toBeInTheDocument();
    expect(screen.getByText("Condition catalog is unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("fails closed when only one extension catalog is unavailable", async () => {
    vi.mocked(workflowService.catalog.actions).mockRejectedValueOnce(new Error("Actions failed"));
    const actionOnly = renderBuilder();

    expect(await screen.findByText("Action catalog is unavailable.")).toBeInTheDocument();
    expect(
      screen.getByText("Extension catalog unavailable. Saving action or decision steps is blocked.")
    ).toBeInTheDocument();
    expect(screen.queryByText("Condition catalog is unavailable.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    actionOnly.unmount();

    vi.mocked(workflowService.catalog.conditions).mockRejectedValueOnce(
      new Error("Conditions failed")
    );
    renderBuilder();

    expect(await screen.findByText("Condition catalog is unavailable.")).toBeInTheDocument();
    expect(
      screen.getByText("Extension catalog unavailable. Saving action or decision steps is blocked.")
    ).toBeInTheDocument();
    expect(screen.queryByText("Action catalog is unavailable.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("shows saving state and routes clean create cancellations without confirmation", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const { props } = renderBuilder({
      initial: undefined,
      submitLabel: "Create workflow",
      submitting: true,
    });

    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(confirm).not.toHaveBeenCalled();
    expect(props.onCancel).toHaveBeenCalledWith("/workflow-automation/workflows");
  });

  it("prevents browser unload only after local edits make the draft dirty", async () => {
    const user = userEvent.setup();
    renderBuilder();

    await screen.findByText("Step palette");

    const cleanUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(cleanUnload);
    expect(cleanUnload.defaultPrevented).toBe(false);

    await user.clear(screen.getByLabelText("Description"));
    await user.type(screen.getByLabelText("Description"), "Dirty draft");

    const dirtyUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyUnload);
    expect(dirtyUnload.defaultPrevented).toBe(true);
  });

  it("keeps generated step keys stable when a step name is temporarily blank", async () => {
    const user = userEvent.setup();
    const { props } = renderBuilder();

    await screen.findByText("Step palette");

    const firstStepName = screen.getByLabelText("Step 1 name");
    const firstStepKey = screen.getAllByLabelText("Step key").at(0);
    if (!firstStepKey) throw new Error("First step key input was not rendered.");

    await user.clear(firstStepName);
    expect(firstStepKey).toHaveValue("project");
    expect(screen.getByText("Step 1 needs a name.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

    fireEvent.change(firstStepName, { target: { value: "ERP Context!" } });
    expect(screen.getAllByLabelText("Step key").at(0)).toHaveValue("erp_context");

    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalled());
    expect(props.onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        steps: expect.arrayContaining([
          expect.objectContaining({ key: "erp_context", name: "ERP Context!" }),
        ]),
      })
    );
  });

  it("persists user assignees, move ordering, and remove operations in the submitted payload", async () => {
    const user = userEvent.setup();
    const { props } = renderBuilder();

    await screen.findByText("Step palette");

    await user.selectOptions(screen.getByLabelText("Assignment"), "user-1");
    await user.click(screen.getByRole("button", { name: "Move Manager approval up" }));
    await user.click(screen.getByRole("button", { name: "Remove Project context" }));

    expect(screen.queryByDisplayValue("Project context")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move Manager approval up" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalled());
    const submitted = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!submitted) throw new Error("Workflow draft payload was not submitted.");
    expect(submitted.steps).toHaveLength(3);
    expect(submitted.steps[0]).toEqual(
      expect.objectContaining({
        key: "approve",
        order: 1,
        config: expect.objectContaining({ assignment_kind: "user", assignee_id: "user-1" }),
      })
    );
    expect(submitted.steps.map((step) => step.order)).toEqual([1, 2, 3]);
    expect(submitted.steps.map((step) => step.key)).not.toContain("project");
  });

  it("blocks submit and validation when local graph rules fail", async () => {
    const user = userEvent.setup();
    const withoutTerminal: WorkflowDetailDTO = {
      ...initial,
      steps: initial.steps.map((step) => ({ ...step, is_terminal: false })),
    };
    const { props } = renderBuilder({ initial: withoutTerminal });

    await screen.findByText("Definition needs attention");

    expect(screen.getByText("Mark at least one step as terminal.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await user.click(screen.getByRole("button", { name: "Validate" }));

    expect(props.onSubmit).not.toHaveBeenCalled();
    expect(workflowService.workflows.validate).not.toHaveBeenCalled();
  });

  it("detects duplicate and blank step keys before submit", async () => {
    const user = userEvent.setup();
    const duplicateKeys: WorkflowDetailDTO = {
      ...initial,
      steps: initial.steps.map((step, index) =>
        index === 1 ? { ...step, key: initial.steps[0]?.key ?? step.key } : step
      ),
    };
    const { props } = renderBuilder({ initial: duplicateKeys });

    await screen.findByText("Definition needs attention");

    expect(screen.getByText("Step 2 needs a unique key.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

    const firstStepKey = screen.getAllByLabelText("Step key").at(0);
    if (!firstStepKey) throw new Error("First step key input was not rendered.");
    await user.clear(firstStepKey);

    expect(screen.getByText("Step 1 needs a unique key.")).toBeInTheDocument();
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("requires decision true and false branches to target existing non-self steps", async () => {
    const user = userEvent.setup();
    const { props } = renderBuilder();

    await screen.findByText("Step palette");
    const trueBranch = screen.getByLabelText("True branch");
    const falseBranch = screen.getByLabelText("False branch");

    expect(trueBranch).not.toHaveTextContent("Route decision");
    expect(falseBranch).not.toHaveTextContent("Route decision");
    expect(trueBranch).toHaveTextContent("Manager approval");
    expect(falseBranch).toHaveTextContent("Notify requester");

    await user.selectOptions(screen.getByLabelText("True branch"), "");
    await user.selectOptions(screen.getByLabelText("False branch"), "");

    expect(screen.getByText("Route decision: select a valid true branch.")).toBeInTheDocument();
    expect(screen.getByText("Route decision: select a valid false branch.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("creates governed default steps from the palette and enforces edge move controls", async () => {
    const { props } = renderBuilder(
      { initial: undefined, submitLabel: "Create workflow" },
      { seedGovernedQueries: true }
    );

    await screen.findByText("Step palette");

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Emergency review" },
    });
    expect(screen.getByLabelText("Stable key")).toHaveValue("emergency_review");

    fireEvent.click(screen.getByRole("button", { name: "Add action" }));
    fireEvent.click(screen.getByRole("button", { name: "Add approval" }));
    fireEvent.click(screen.getByRole("button", { name: "Add notification" }));
    fireEvent.click(screen.getByRole("button", { name: "Add decision" }));

    expect(screen.getByDisplayValue("Action 1")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Approval 2")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Notification 3")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Decision 4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move Action 1 up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Approval 2 up" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Move Approval 2 down" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Move Decision 4 down" })).toBeDisabled();
    expect(screen.getByDisplayValue("actor.id")).toBeInTheDocument();
    expect(screen.getByText("Approval 2: choose an assignee.")).toBeInTheDocument();
    expect(screen.getByText("Action 1: choose an available action.")).toBeInTheDocument();
    expect(screen.getByText("Decision 4: choose a condition.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Registered action"), {
      target: { value: "core.project_context" },
    });
    fireEvent.change(screen.getByLabelText("Context path"), {
      target: { value: "subject.amount" },
    });
    fireEvent.change(screen.getByLabelText("Limit"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "strict" } });
    fireEvent.change(screen.getByLabelText("Target"), { target: { value: "role-1" } });
    fireEvent.change(screen.getByLabelText("Assignment"), { target: { value: "role-1" } });
    fireEvent.change(screen.getByLabelText("Condition"), {
      target: { value: "core.amount_gt" },
    });
    fireEvent.change(screen.getByLabelText("Minimum"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("True branch"), { target: { value: "step_2" } });
    fireEvent.change(screen.getByLabelText("False branch"), { target: { value: "step_3" } });
    const decisionTerminal = screen.getAllByLabelText("Terminal step").at(3);
    if (!decisionTerminal) throw new Error("Decision terminal control was not rendered.");
    expect(decisionTerminal).not.toBeChecked();
    fireEvent.click(decisionTerminal);
    expect(decisionTerminal).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Create workflow" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalled());
    const submitted = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!submitted) throw new Error("Created workflow payload was not submitted.");
    expect(submitted).toEqual(
      expect.objectContaining({
        key: "emergency_review",
        workflow_type: "approval",
        trigger_type: "manual",
      })
    );
    expect(submitted.steps).toEqual([
      expect.objectContaining({
        key: "step_1",
        step_type: "action",
        config: expect.objectContaining({ handler: "core.project_context" }),
      }),
      expect.objectContaining({
        key: "step_2",
        step_type: "approval",
        config: expect.objectContaining({
          assignment_kind: "role",
          assignee_id: "role-1",
          due_in_seconds: configuration.document.defaults.approval_due_seconds,
          rejection_behavior: configuration.document.defaults.approval_rejection_behavior,
        }),
      }),
      expect.objectContaining({
        key: "step_3",
        step_type: "notification",
        config: expect.objectContaining({
          channel: "in_app",
          recipient_mapping: { recipient_id: "actor.id" },
          template_key: "workflow.task.created",
        }),
      }),
      expect.objectContaining({
        key: "step_4",
        step_type: "decision",
        is_terminal: true,
        config: expect.objectContaining({
          true_step_key: "step_2",
          false_step_key: "step_3",
        }),
      }),
    ]);
  }, 10_000);

  it("preserves the selected descriptors when unavailable catalog entries are chosen", async () => {
    vi.mocked(workflowService.catalog.actions).mockResolvedValueOnce([action, lockedAction]);
    vi.mocked(workflowService.catalog.conditions).mockResolvedValueOnce([
      condition,
      setupRequiredCondition,
    ]);
    const user = userEvent.setup();
    const { props } = renderBuilder();

    await screen.findByText("Step palette");
    expect(screen.getAllByText("workflow_automation · 1.0")).toHaveLength(2);

    const actionSelect = screen.getByLabelText("Registered action");
    expect(actionSelect).toHaveTextContent("Locked action — locked");
    expect(screen.getByRole("option", { name: "Locked action — locked" })).toBeDisabled();
    fireEvent.change(actionSelect, { target: { value: "core.locked_action" } });
    expect(actionSelect).toHaveValue("core.project_context");
    expect(screen.getByLabelText("Context path")).toHaveValue("amount");

    const conditionSelect = screen.getByLabelText("Condition");
    expect(conditionSelect).toHaveTextContent("Setup required condition — setup required");
    expect(
      screen.getByRole("option", { name: "Setup required condition — setup required" })
    ).toBeDisabled();
    fireEvent.change(conditionSelect, { target: { value: "core.setup_required_condition" } });
    expect(conditionSelect).toHaveValue("core.amount_gt");
    expect(screen.getByLabelText("Minimum")).toHaveValue(1000);

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(props.onSubmit).toHaveBeenCalled());

    const submitted = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!submitted) throw new Error("Workflow draft payload was not submitted.");
    expect(submitted.steps[0]?.config).toEqual(
      expect.objectContaining({ handler: "core.project_context" })
    );
    expect(submitted.steps[3]?.config).toEqual(
      expect.objectContaining({
        condition: expect.objectContaining({ handler: "core.amount_gt" }),
      })
    );
  });

  it("resolves selected descriptors by key when unavailable catalog entries are returned first", async () => {
    vi.mocked(workflowService.catalog.actions).mockResolvedValueOnce([lockedAction, action]);
    vi.mocked(workflowService.catalog.conditions).mockResolvedValueOnce([
      setupRequiredCondition,
      condition,
    ]);
    renderBuilder();

    await screen.findByText("Step palette");

    expect(screen.getByLabelText("Registered action")).toHaveValue("core.project_context");
    expect(screen.getByLabelText("Condition")).toHaveValue("core.amount_gt");
    expect(screen.getAllByText("workflow_automation · 1.0")).toHaveLength(2);
    expect(screen.getAllByText("available")).toHaveLength(2);
    expect(screen.getByDisplayValue("amount")).toBeInTheDocument();
    expect(screen.getByDisplayValue(1000)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Locked action — locked" })).toBeDisabled();
    expect(
      screen.getByRole("option", { name: "Setup required condition — setup required" })
    ).toBeDisabled();
  });

  it("renders lookup outage states without accepting unavailable lookup values", async () => {
    vi.mocked(workflowService.catalog.lookup).mockRejectedValueOnce(new Error("Lookup failed"));
    const user = userEvent.setup();
    const { props } = renderBuilder();

    await screen.findByText("Step palette");

    const target = await screen.findByLabelText("Target");
    await waitFor(() => expect(target).toBeDisabled());
    expect(target).toHaveTextContent("Lookup unavailable");

    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalled());
    const submitted = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!submitted) throw new Error("Workflow draft payload was not submitted.");
    expect(submitted.steps[0]?.config).toEqual(
      expect.objectContaining({
        configuration: expect.objectContaining({ target: "role-1" }),
      })
    );
  });

  it("clears timeout policy and restores the governed default only after a timeout returns", async () => {
    const user = userEvent.setup();
    const { props } = renderBuilder();

    await screen.findByText("Step palette");
    const timeoutInput = screen.getAllByLabelText("Timeout seconds").at(0);
    if (!timeoutInput) throw new Error("Project timeout control was not rendered.");

    await user.clear(timeoutInput);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(1));
    let submitted = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!submitted) throw new Error("Workflow draft payload was not submitted.");
    expect(submitted.steps.find((step) => step.key === "project")).toEqual(
      expect.objectContaining({ timeout_action: null, timeout_seconds: null })
    );

    fireEvent.change(timeoutInput, { target: { value: "45" } });
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(2));
    submitted = vi.mocked(props.onSubmit).mock.calls[1]?.[0];
    if (!submitted) throw new Error("Workflow draft payload retry was not submitted.");
    expect(submitted.steps.find((step) => step.key === "project")).toEqual(
      expect.objectContaining({ timeout_action: "notify", timeout_seconds: 45 })
    );
  });

  it("surfaces server validation defects without submitting the draft", async () => {
    vi.mocked(workflowService.workflows.validate).mockResolvedValueOnce({
      valid: false,
      issues: [
        {
          code: "missing_assignee",
          severity: "error",
          message: "Approval step requires an assignee.",
          step_key: "approve",
          pointer: "/steps/1/config/assignee_id",
          remediation: "Select an assignee before publishing.",
        },
      ],
      warnings: [],
    });
    const user = userEvent.setup();
    const { props } = renderBuilder();

    await screen.findByText("Step palette");
    await user.click(screen.getByRole("button", { name: "Validate" }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Server validation found issues");
    expect(status).toHaveClass("border-destructive/40");
    expect(status).toHaveTextContent("missing_assignee");
    expect(status).toHaveTextContent("Approval step requires an assignee.");
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("clears server validation output when the local draft changes", async () => {
    renderBuilder({}, { seedGovernedQueries: true });

    await screen.findByText("Step palette");
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(await screen.findByText("Definition is publishable")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveClass("border-emerald-500/40");
    expect(screen.getByText("late_step")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Updated after validation" },
    });

    expect(screen.queryByText("Definition is publishable")).not.toBeInTheDocument();
    expect(screen.queryByText("late_step")).not.toBeInTheDocument();
  }, 10_000);

  it("keeps validation disabled while server validation is pending", async () => {
    let resolveValidation: (
      value: Awaited<ReturnType<typeof workflowService.workflows.validate>>
    ) => void = () => undefined;
    vi.mocked(workflowService.workflows.validate).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveValidation = resolve;
      })
    );
    const user = userEvent.setup();
    renderBuilder();

    await screen.findByText("Step palette");
    const validate = screen.getByRole("button", { name: "Validate" });
    await user.click(validate);

    await waitFor(() => expect(validate).toBeDisabled());
    expect(workflowService.workflows.validate).toHaveBeenCalledTimes(1);

    resolveValidation({ valid: true, issues: [], warnings: [] });
    expect(await screen.findByText("Definition is publishable")).toBeInTheDocument();
    await waitFor(() => expect(validate).not.toBeDisabled());
  });

  it("renders loaded server errors and blocks only through explicit disabled states", async () => {
    const { props } = renderBuilder(
      { serverError: new Error("Save failed") },
      { seedGovernedQueries: true }
    );

    expect(await screen.findByRole("alert", { name: "" })).toHaveTextContent("Save failed");

    const callsBeforeSave = vi.mocked(props.onSubmit).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(callsBeforeSave + 1));
  });

  it("renders assignee directory outages as disabled approval controls", async () => {
    vi.mocked(workflowService.catalog.assignees).mockRejectedValueOnce(
      new Error("Directory failed")
    );
    const user = userEvent.setup();
    const { props } = renderBuilder();

    await screen.findByText("Step palette");
    const assignment = screen.getByLabelText("Assignment");

    await waitFor(() => expect(assignment).toBeDisabled());
    expect(assignment).toHaveTextContent("Assignee directory unavailable");

    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalled());
    const submitted = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!submitted) throw new Error("Workflow draft payload was not submitted.");
    expect(submitted.steps[1]?.config).toEqual(
      expect.objectContaining({ assignment_kind: "role", assignee_id: "role-1" })
    );
  });

  it("persists approval due units and rejection branch rewiring", async () => {
    const { props } = renderBuilder({}, { seedGovernedQueries: true });

    await screen.findByText("Step palette");

    const dueTimeUnits = screen.getAllByDisplayValue(2).at(1);
    if (!dueTimeUnits) throw new Error("Approval due time control was not rendered.");
    fireEvent.change(dueTimeUnits, { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Rejection branch"), { target: { value: "project" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(1));
    let submitted = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!submitted) throw new Error("Workflow draft payload was not submitted.");
    expect(submitted.steps[1]?.config).toEqual(
      expect.objectContaining({
        due_in_seconds: 18000,
        rejection_behavior: "goto",
        reject_step_key: "project",
      })
    );

    fireEvent.change(screen.getByLabelText("On rejection"), { target: { value: "cancel" } });
    expect(screen.queryByLabelText("Rejection branch")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(2));
    submitted = vi.mocked(props.onSubmit).mock.calls[1]?.[0];
    if (!submitted) throw new Error("Workflow draft payload retry was not submitted.");
    expect(submitted.steps[1]?.config).toEqual(
      expect.objectContaining({
        rejection_behavior: "cancel",
        reject_step_key: null,
      })
    );
  }, 10_000);

  it("persists notification recipient and template edits for both delivery channels", async () => {
    const { props } = renderBuilder({}, { seedGovernedQueries: true });

    await screen.findByText("Step palette");

    const inAppRecipient = screen.getByDisplayValue("actor.id");
    const template = screen.getByDisplayValue("workflow.task.created");
    fireEvent.change(inAppRecipient, { target: { value: "requester.id" } });
    fireEvent.change(template, { target: { value: "workflow.custom.in_app" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(1));
    let submitted = vi.mocked(props.onSubmit).mock.calls[0]?.[0];
    if (!submitted) throw new Error("Workflow draft payload was not submitted.");
    expect(submitted.steps[2]?.config).toEqual(
      expect.objectContaining({
        channel: "in_app",
        recipient_mapping: { recipient_id: "requester.id" },
        template_key: "workflow.custom.in_app",
      })
    );

    fireEvent.change(screen.getByLabelText("Channel"), { target: { value: "email" } });
    const emailRecipient = screen.getByDisplayValue("actor.email");
    fireEvent.change(emailRecipient, { target: { value: "requester.email" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(2));
    submitted = vi.mocked(props.onSubmit).mock.calls[1]?.[0];
    if (!submitted) throw new Error("Workflow draft payload retry was not submitted.");
    expect(submitted.steps[2]?.config).toEqual(
      expect.objectContaining({
        channel: "email",
        recipient_mapping: { recipient_email: "requester.email" },
        template_key: "workflow.custom.in_app",
      })
    );
  });

  it("shows empty-state guardrails after all steps are removed", async () => {
    const user = userEvent.setup();
    const { props } = renderBuilder();

    await screen.findByText("Step palette");

    for (const label of [
      "Remove Project context",
      "Remove Manager approval",
      "Remove Notify requester",
      "Remove Route decision",
    ]) {
      await user.click(screen.getByRole("button", { name: label }));
    }

    expect(screen.getByText("Design the first step")).toBeInTheDocument();
    expect(screen.getByText("Add at least one step.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("routes away without confirmation after a successful save clears dirty state", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const { props } = renderBuilder();

    await screen.findByText("Step palette");
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Ready to leave after save" },
    });
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    });

    await waitFor(() => expect(props.onSubmit).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(confirm).not.toHaveBeenCalled();
    expect(props.onCancel).toHaveBeenCalledWith("/workflow-automation/workflows/workflow-1");
  });

  it("shows unavailable configuration and server errors without submitting", async () => {
    vi.mocked(workflowService.configuration.get).mockRejectedValue(new Error("No config"));
    const { props } = renderBuilder({ initial: undefined, serverError: new Error("Save failed") });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Loading governed workflow configuration"
    );
    expect(props.onSubmit).not.toHaveBeenCalled();
  });
});
