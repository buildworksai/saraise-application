/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method -- This smoke file intentionally covers end-to-end page flows; Vitest spies intentionally reference service methods. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  HandlerDescriptorDTO,
  PaginatedResult,
  WorkflowConfigurationDTO,
  WorkflowDetailDTO,
  WorkflowInstanceDetailDTO,
  WorkflowInstanceListDTO,
  WorkflowListDTO,
  WorkflowTaskDetailDTO,
  WorkflowTaskListDTO,
} from "../../contracts";
import { WorkflowApiError, workflowService } from "../../services/workflow-service";
import { TaskInboxPage } from "../TaskInboxPage";
import { WorkflowCreatePage } from "../WorkflowCreatePage";
import { WorkflowDetailPage } from "../WorkflowDetailPage";
import { WorkflowEditPage } from "../WorkflowEditPage";
import { WorkflowInstanceDetailPage } from "../WorkflowInstanceDetailPage";
import { WorkflowInstanceListPage } from "../WorkflowInstanceListPage";
import { WorkflowTaskDetailPage } from "../WorkflowTaskDetailPage";
import { WorkflowListPage } from "../WorkflowListPage";

const pagination = {
  count: 1,
  page: 1,
  page_size: 20,
  total_pages: 1,
  has_next: false,
  has_previous: false,
} as const;
const transition = {
  transition_key: "transition-1",
  command: "publish",
  from_state: "draft",
  to_state: "published",
  actor_id: "user-1",
  occurred_at: "2026-07-22T00:00:00Z",
  correlation_id: "corr-1",
} as const;
const step = {
  id: "step-1",
  key: "approve",
  name: "Manager approval",
  step_type: "approval",
  order: 1,
  config: {
    assignment_kind: "role",
    assignee_id: "role-1",
    due_in_seconds: 86400,
    rejection_behavior: "fail",
    reject_step_key: null,
  },
  timeout_seconds: 86400,
  timeout_action: "fail",
  is_terminal: true,
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
} as const;
const definition: WorkflowDetailDTO = {
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
  transition_history: [transition],
  steps: [step],
  versions: [{ id: "workflow-1", version: 2, status: "draft", updated_at: "2026-07-22T00:00:00Z" }],
  execution_statistics: { total: 4, active: 1, completed: 2, failed: 1, completion_rate: 0.5 },
  handler_health: [],
};
const task: WorkflowTaskDetailDTO = {
  id: "task-1",
  instance_id: "instance-1",
  workflow_id: "workflow-1",
  workflow_name: "Purchase approval",
  workflow_version: 2,
  step_id: "step-1",
  step_name: "Manager approval",
  assignment_kind: "role",
  assignment_label: "Purchasing managers",
  subject: "PO-1042",
  status: "pending",
  due_date: "2026-07-23T00:00:00Z",
  created_at: "2026-07-22T00:00:00Z",
  completed_at: null,
  correlation_id: "corr-task",
  allowed_actions: ["view", "complete", "reject"],
  safe_context: { amount: 1250, supplier: "Acme" },
  meta_data: {},
  transition_history: [],
  completed_by_name: null,
};
const instance: WorkflowInstanceDetailDTO = {
  id: "instance-1",
  workflow_id: "workflow-1",
  workflow_name: "Purchase approval",
  workflow_version: 2,
  state: "waiting",
  current_step_name: "Manager approval",
  entity_type: "purchase_order",
  entity_id: "entity-1",
  subject: "PO-1042",
  priority: 7,
  correlation_id: "corr-instance",
  started_by_name: "Asha",
  started_at: "2026-07-22T00:00:00Z",
  completed_at: null,
  created_at: "2026-07-22T00:00:00Z",
  failure_code: "",
  failure_message: "",
  allowed_actions: ["view", "cancel"],
  context_data: { amount: 1250 },
  result_data: {},
  current_step: step,
  transition_history: [transition],
  tasks: [task],
};
const descriptor: HandlerDescriptorDTO = {
  key: "core.context_projection.v1",
  display_name: "Project context",
  description: "Safely projects context",
  category: "Core",
  owning_module: "workflow_automation",
  schema_version: "1.0",
  descriptor_fingerprint: "sha256:test",
  required_permission: "workflow_automation.workflow:create",
  required_entitlement: "module.workflow_automation",
  availability: "available",
  reason: null,
  ui_schema: [{ kind: "text", key: "path", label: "Context path", required: true }],
  input_schema: {},
  output_schema: {},
  idempotent: true,
  network_access: false,
};
const configuration: WorkflowConfigurationDTO = {
  id: "configuration-1",
  tenant_id: "tenant-1",
  environment: "production",
  version: 1,
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  updated_by: "user-1",
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
      timeout_action: "fail",
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
      workflow_types: ["approval", "state_machine", "sequential", "parallel", "conditional"],
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
function page<T>(items: readonly T[]): PaginatedResult<T> {
  return {
    items,
    pagination: { ...pagination, count: items.length, total_pages: items.length ? 1 : 0 },
    correlationId: "corr-list",
    receivedAt: "2026-07-22T00:00:00Z",
  };
}
function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
function renderRoute(
  path: string,
  route: string,
  pageElement: React.ReactElement,
  options: { configuration?: WorkflowConfigurationDTO } = {}
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  if (options.configuration)
    client.setQueryData(
      ["workflow-automation", "configuration", "production"],
      options.configuration
    );
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={pageElement} />
          <Route path="/workflow-automation/instances/:id" element={<div>Execution route</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("workflow contextual pages", () => {
  beforeEach(() => {
    vi.spyOn(workflowService.configuration, "get").mockResolvedValue(configuration);
    vi.spyOn(workflowService.workflows, "get").mockResolvedValue(definition);
    vi.spyOn(workflowService.catalog, "actions").mockResolvedValue([descriptor]);
    vi.spyOn(workflowService.catalog, "conditions").mockResolvedValue([]);
    vi.spyOn(workflowService.catalog, "assignees").mockResolvedValue([
      { id: "role-1", label: "Purchasing managers", description: null, kind: "role" },
    ]);
    vi.spyOn(workflowService.instances, "list").mockResolvedValue(
      page<WorkflowInstanceListDTO>([instance])
    );
    vi.spyOn(workflowService.instances, "get").mockResolvedValue(instance);
    vi.spyOn(workflowService.tasks, "list").mockResolvedValue(page<WorkflowTaskListDTO>([task]));
    vi.spyOn(workflowService.tasks, "get").mockResolvedValue(task);
  });
  afterEach(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    vi.restoreAllMocks();
  });

  it("renders workflow definition evidence and lifecycle actions", async () => {
    renderRoute(
      "/workflow-automation/workflows/workflow-1",
      "/workflow-automation/workflows/:id",
      <WorkflowDetailPage />
    );
    expect(await screen.findByText("Purchase approval")).toBeInTheDocument();
    expect(screen.getByText("Step graph")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publish/u })).toBeInTheDocument();
  });
  it("executes workflow detail lifecycle callbacks from allowed actions", async () => {
    const publish = vi.spyOn(workflowService.workflows, "publish").mockResolvedValue(definition);
    const archive = vi.spyOn(workflowService.workflows, "archive").mockResolvedValue(definition);
    const start = vi.spyOn(workflowService.instances, "start").mockResolvedValue(instance);
    vi.mocked(workflowService.workflows.get).mockResolvedValue({
      ...definition,
      allowed_actions: ["view", "publish", "archive", "start", "clone"],
      status: "published",
    });
    const user = userEvent.setup();
    renderRoute(
      "/workflow-automation/workflows/workflow-1",
      "/workflow-automation/workflows/:id",
      <WorkflowDetailPage />
    );
    await user.click(await screen.findByRole("button", { name: "Publish" }));
    await user.click(screen.getByRole("button", { name: /Version 2/u }));
    await waitFor(() => expect(publish).toHaveBeenCalledWith("workflow-1", expect.any(Object)));
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith("workflow-1", expect.any(Object)));
    expect(start).toHaveBeenCalledWith(expect.objectContaining({ workflow_id: "workflow-1" }));
  });
  it("renders the schema-driven create designer without raw identifiers", async () => {
    renderRoute(
      "/workflow-automation/workflows/new",
      "/workflow-automation/workflows/new",
      <WorkflowCreatePage />
    );
    expect(await screen.findByText("Step palette")).toBeInTheDocument();
    expect(screen.queryByText(/UUID/u)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add approval" })).toBeInTheDocument();
  });
  it("initializes the edit designer from a draft", async () => {
    renderRoute(
      "/workflow-automation/workflows/workflow-1/edit",
      "/workflow-automation/workflows/:id/edit",
      <WorkflowEditPage />
    );
    expect(await screen.findByDisplayValue("Purchase approval")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Manager approval")).toBeInTheDocument();
  });
  it("stops stale draft edits and reloads the latest revision", async () => {
    const update = vi
      .spyOn(workflowService.workflows, "update")
      .mockRejectedValueOnce(
        new WorkflowApiError("Stale draft", 409, "stale_workflow", "corr-stale", [], true)
      );
    const user = userEvent.setup();
    renderRoute(
      "/workflow-automation/workflows/workflow-1/edit",
      "/workflow-automation/workflows/:id/edit",
      <WorkflowEditPage />
    );

    expect(await screen.findByDisplayValue("Purchase approval")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        "workflow-1",
        expect.objectContaining({ expected_updated_at: definition.updated_at })
      )
    );
    expect(await screen.findByText("A newer draft revision exists")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reload latest revision" }));
    expect(await screen.findByDisplayValue("Purchase approval")).toBeInTheDocument();
  });
  it("guards workflow edit loading, unavailable, missing, and immutable states", async () => {
    vi.mocked(workflowService.workflows.get).mockReturnValueOnce(new Promise(() => undefined));
    const loading = renderRoute(
      "/workflow-automation/workflows/workflow-1/edit",
      "/workflow-automation/workflows/:id/edit",
      <WorkflowEditPage />
    );
    expect(await screen.findByLabelText("Loading workflow draft")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    loading.unmount();
    vi.mocked(workflowService.workflows.get).mockRejectedValueOnce(
      new WorkflowApiError("Edit denied", 403, "denied", "corr-edit", [], false)
    );
    const denied = renderRoute(
      "/workflow-automation/workflows/workflow-1/edit",
      "/workflow-automation/workflows/:id/edit",
      <WorkflowEditPage />
    );
    expect(await screen.findByText("Permission required")).toBeInTheDocument();
    denied.unmount();
    vi.mocked(workflowService.workflows.get).mockResolvedValueOnce(
      null as unknown as typeof definition
    );
    const missing = renderRoute(
      "/workflow-automation/workflows/workflow-1/edit",
      "/workflow-automation/workflows/:id/edit",
      <WorkflowEditPage />
    );
    expect(await screen.findByText("Workflow not found")).toBeInTheDocument();
    missing.unmount();
    vi.mocked(workflowService.workflows.get).mockResolvedValueOnce({
      ...definition,
      status: "published",
    });
    renderRoute(
      "/workflow-automation/workflows/workflow-1/edit",
      "/workflow-automation/workflows/:id/edit",
      <WorkflowEditPage />
    );
    expect(await screen.findByText("This version is immutable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View version and clone" })).toBeInTheDocument();
  });
  it("renders server-paginated execution monitoring", async () => {
    renderRoute(
      "/workflow-automation/instances",
      "/workflow-automation/instances",
      <WorkflowInstanceListPage />
    );
    expect(
      await screen.findByRole("button", { name: "Purchase approval · v2" })
    ).toBeInTheDocument();
    expect(screen.getAllByText("waiting")).toHaveLength(2);
  });
  it("polls visible execution lists and suppresses polling while hidden", async () => {
    const fastPolicy: WorkflowConfigurationDTO = {
      ...configuration,
      document: {
        ...configuration.document,
        operational: {
          ...configuration.document.operational,
          execution_poll_interval_ms: 10,
        },
      },
    };
    vi.mocked(workflowService.configuration.get).mockResolvedValue(fastPolicy);
    const visibleList = vi
      .spyOn(workflowService.instances, "list")
      .mockResolvedValue(page<WorkflowInstanceListDTO>([instance]));
    const visible = renderRoute(
      "/workflow-automation/instances",
      "/workflow-automation/instances",
      <WorkflowInstanceListPage />
    );
    expect(
      await screen.findByRole("button", { name: "Purchase approval · v2" })
    ).toBeInTheDocument();
    await waitFor(() => expect(visibleList.mock.calls.length).toBeGreaterThan(1), {
      timeout: 500,
    });
    visible.unmount();

    vi.clearAllMocks();
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    vi.mocked(workflowService.configuration.get).mockResolvedValue(fastPolicy);
    const hiddenList = vi
      .spyOn(workflowService.instances, "list")
      .mockResolvedValue(page<WorkflowInstanceListDTO>([instance]));
    const hidden = renderRoute(
      "/workflow-automation/instances",
      "/workflow-automation/instances",
      <WorkflowInstanceListPage />
    );
    expect(
      await screen.findByRole("button", { name: "Purchase approval · v2" })
    ).toBeInTheDocument();
    await wait(40);
    expect(hiddenList).toHaveBeenCalledTimes(1);
    hidden.unmount();
  });
  it("filters empty execution searches and fails closed on list errors", async () => {
    vi.mocked(workflowService.instances.list).mockResolvedValue(page<WorkflowInstanceListDTO>([]));
    const user = userEvent.setup();
    const empty = renderRoute(
      "/workflow-automation/instances",
      "/workflow-automation/instances",
      <WorkflowInstanceListPage />
    );
    expect(await screen.findByText("No executions found")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Search executions"), "missing execution");
    await user.selectOptions(screen.getByLabelText("Filter state"), "failed");
    await user.type(screen.getByLabelText("Filter entity type"), "purchase_order");
    await user.selectOptions(screen.getByLabelText("Order executions"), "completed_at");
    await waitFor(() =>
      expect(workflowService.instances.list).toHaveBeenLastCalledWith(
        expect.objectContaining({
          entity_type: "p",
          ordering: "completed_at",
          search: "m",
          state: "failed",
        })
      )
    );
    empty.unmount();
    vi.mocked(workflowService.instances.list).mockRejectedValueOnce(
      new WorkflowApiError("Execution service down", 503, "down", "corr-exec", [], true)
    );
    renderRoute(
      "/workflow-automation/instances",
      "/workflow-automation/instances",
      <WorkflowInstanceListPage />
    );
    expect(await screen.findByText("Workflow capability unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-exec/u)).toBeInTheDocument();
  });
  it("renders execution list fallbacks for manual subjects, step names, failures, and pagination", async () => {
    vi.mocked(workflowService.instances.list).mockResolvedValue(
      page<WorkflowInstanceListDTO>([
        {
          ...instance,
          id: "instance-manual",
          subject: null,
          entity_type: "",
          current_step_name: null,
          failure_code: "",
        },
      ])
    );

    renderRoute(
      "/workflow-automation/instances",
      "/workflow-automation/instances",
      <WorkflowInstanceListPage />
    );

    expect(await screen.findByText("Manual execution")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Page 1 of 1")).toBeInTheDocument();
  });
  it("renders live execution evidence, tasks, and correlation", async () => {
    renderRoute(
      "/workflow-automation/instances/instance-1",
      "/workflow-automation/instances/:id",
      <WorkflowInstanceDetailPage />
    );
    expect(await screen.findByText("Immutable transition timeline")).toBeInTheDocument();
    expect(screen.getByText("corr-instance")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cancel execution/u })).toBeInTheDocument();
  });
  it("does not poll terminal execution details and fails closed on missing executions", async () => {
    const fastPolicy: WorkflowConfigurationDTO = {
      ...configuration,
      document: {
        ...configuration.document,
        operational: {
          ...configuration.document.operational,
          execution_detail_poll_interval_ms: 10,
        },
      },
    };
    vi.mocked(workflowService.configuration.get).mockResolvedValue(fastPolicy);
    const get = vi.spyOn(workflowService.instances, "get").mockResolvedValue({
      ...instance,
      state: "completed",
      allowed_actions: ["view"],
      completed_at: "2026-07-22T01:00:00Z",
    });
    const terminalDetail = renderRoute(
      "/workflow-automation/instances/instance-1",
      "/workflow-automation/instances/:id",
      <WorkflowInstanceDetailPage />
    );

    expect(await screen.findByText("completed")).toBeInTheDocument();
    await wait(40);
    expect(get).toHaveBeenCalledTimes(1);
    terminalDetail.unmount();

    vi.mocked(workflowService.instances.get).mockResolvedValueOnce(
      null as unknown as typeof instance
    );
    renderRoute(
      "/workflow-automation/instances/instance-1",
      "/workflow-automation/instances/:id",
      <WorkflowInstanceDetailPage />
    );
    expect(await screen.findByText("Execution not found")).toBeInTheDocument();
  });
  it("fails closed when workflow configuration fetches are rejected by guarded pages", async () => {
    vi.mocked(workflowService.configuration.get).mockRejectedValueOnce(
      new WorkflowApiError("Configuration unavailable", 503, "down", "corr-config-page", [], true)
    );
    const rejectedList = renderRoute(
      "/workflow-automation/workflows",
      "/workflow-automation/workflows",
      <WorkflowListPage />
    );

    expect(await screen.findByText("Workflow capability unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-config-page/u)).toBeInTheDocument();
    rejectedList.unmount();

    vi.mocked(workflowService.configuration.get).mockRejectedValueOnce(
      new WorkflowApiError("Configuration unavailable", 503, "down", "corr-config-task", [], true)
    );
    renderRoute("/workflow-automation/tasks", "/workflow-automation/tasks", <TaskInboxPage />);

    expect(await screen.findByText("Workflow capability unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-config-task/u)).toBeInTheDocument();
  });
  it("renders the personal task inbox with safe decision actions", async () => {
    renderRoute("/workflow-automation/tasks", "/workflow-automation/tasks", <TaskInboxPage />);
    expect(await screen.findByRole("button", { name: "Manager approval" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/u })).toBeInTheDocument();
  });
  it("renders read-only task rows without decision actions", async () => {
    vi.mocked(workflowService.tasks.list).mockResolvedValueOnce(
      page<WorkflowTaskListDTO>([
        {
          ...task,
          allowed_actions: ["view"],
          due_date: null,
          subject: null,
          status: "completed",
        },
      ])
    );

    renderRoute("/workflow-automation/tasks", "/workflow-automation/tasks", <TaskInboxPage />, {
      configuration,
    });

    expect(await screen.findByText("Workflow decision")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Manager approval" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reject/u })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve \/ complete/u })).not.toBeInTheDocument();
  });
  it("renders only permitted task context and immutable history", async () => {
    renderRoute(
      "/workflow-automation/tasks/task-1",
      "/workflow-automation/tasks/:id",
      <WorkflowTaskDetailPage />
    );
    expect(await screen.findByText("Permitted business context")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("corr-task")).toBeInTheDocument();
  });
  it("fails closed when a task detail response is empty", async () => {
    vi.mocked(workflowService.tasks.get).mockResolvedValueOnce(null as unknown as typeof task);

    renderRoute(
      "/workflow-automation/tasks/task-1",
      "/workflow-automation/tasks/:id",
      <WorkflowTaskDetailPage />
    );

    expect(await screen.findByText("Task not found")).toBeInTheDocument();
  });
  it("renders task completion evidence and hides structured resolver values", async () => {
    vi.mocked(workflowService.tasks.get).mockResolvedValueOnce({
      ...task,
      completed_by_name: "Nila",
      completed_at: "2026-07-22T01:00:00Z",
      safe_context: { amount: null, audit: { hidden: true } },
      transition_history: [transition],
    });
    renderRoute(
      "/workflow-automation/tasks/task-1",
      "/workflow-automation/tasks/:id",
      <WorkflowTaskDetailPage />
    );
    expect(await screen.findByText("Structured value hidden")).toBeInTheDocument();
    expect(screen.getByText("Completed by Nila at Jul 22, 2026, 6:30 AM")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
  it("renders scalar task context while hiding object and array resolver values", async () => {
    vi.mocked(workflowService.tasks.get).mockResolvedValueOnce({
      ...task,
      safe_context: {
        approved: false,
        amount: 0,
        supplier: "",
        audit: { hidden: true },
        approvals: ["manager"],
      },
    });

    renderRoute(
      "/workflow-automation/tasks/task-1",
      "/workflow-automation/tasks/:id",
      <WorkflowTaskDetailPage />
    );

    expect(await screen.findByText("false")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getAllByText("Structured value hidden")).toHaveLength(2);
  });
  it("records task detail decisions and surfaces stale duplicate protection", async () => {
    const complete = vi
      .spyOn(workflowService.tasks, "complete")
      .mockResolvedValue({ ...task, status: "completed", completed_at: "2026-07-22T01:00:00Z" });
    const reject = vi
      .spyOn(workflowService.tasks, "reject")
      .mockRejectedValue(
        new WorkflowApiError("Already decided", 409, "stale_task", "corr-task-stale", [], true)
      );
    const user = userEvent.setup();
    const rendered = renderRoute(
      "/workflow-automation/tasks/task-1",
      "/workflow-automation/tasks/:id",
      <WorkflowTaskDetailPage />
    );
    await user.click(await screen.findByRole("button", { name: /Approve \/ complete/u }));
    await user.click(screen.getByRole("button", { name: "Complete task" }));
    await waitFor(() => expect(complete).toHaveBeenCalledWith("task-1", expect.any(Object)));
    expect(await screen.findByRole("status")).toHaveTextContent("completed");
    rendered.unmount();
    renderRoute(
      "/workflow-automation/tasks/task-1",
      "/workflow-automation/tasks/:id",
      <WorkflowTaskDetailPage />
    );
    await user.click(await screen.findByRole("button", { name: "Reject" }));
    await user.type(screen.getByRole("textbox"), "Duplicate evidence");
    await user.click(screen.getByRole("button", { name: "Reject task" }));
    await waitFor(() => expect(reject).toHaveBeenCalled());
    expect(await screen.findByText(/duplicate decision was not applied/u)).toBeInTheDocument();
  });
  it("cancels non-terminal executions and renders failed execution fallbacks", async () => {
    const cancel = vi.spyOn(workflowService.instances, "cancel").mockResolvedValue({
      ...instance,
      state: "cancelled",
    });
    const user = userEvent.setup();
    const rendered = renderRoute(
      "/workflow-automation/instances/instance-1",
      "/workflow-automation/instances/:id",
      <WorkflowInstanceDetailPage />
    );
    await user.click(await screen.findByRole("button", { name: /Cancel execution/u }));
    await user.click(screen.getByRole("button", { name: "Cancel execution" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("instance-1", expect.any(Object)));
    rendered.unmount();
    vi.mocked(workflowService.instances.get).mockResolvedValue({
      ...instance,
      state: "failed",
      current_step_name: null,
      failure_code: "handler_failed",
      failure_message: "",
      allowed_actions: ["view"],
      tasks: [],
    });
    renderRoute(
      "/workflow-automation/instances/instance-1",
      "/workflow-automation/instances/:id",
      <WorkflowInstanceDetailPage />
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("handler_failed");
    expect(screen.getByText("No human tasks were created.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cancel execution/u })).not.toBeInTheDocument();
  });
  it("blocks degraded workflow actions and renders read-only version evidence", async () => {
    vi.mocked(workflowService.workflows.get).mockResolvedValueOnce({
      ...definition,
      description: "",
      status: "published",
      allowed_actions: ["view", "publish", "start", "archive", "clone"],
      execution_statistics: { total: 0, active: 0, completed: 0, failed: 0, completion_rate: null },
      handler_health: [
        {
          ...descriptor,
          availability: "setup_required",
          reason: "Connector credentials missing",
        },
      ],
      steps: [{ ...step, timeout_seconds: null, is_terminal: false }],
    });
    renderRoute(
      "/workflow-automation/workflows/workflow-1",
      "/workflow-automation/workflows/:id",
      <WorkflowDetailPage />
    );
    expect(await screen.findByText("No description provided.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Connector credentials missing");
    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
    expect(screen.getByText(/Published and archived versions are read-only/u)).toBeInTheDocument();
  });
  it("records task approvals with immutable success evidence", async () => {
    const complete = vi
      .spyOn(workflowService.tasks, "complete")
      .mockResolvedValue({ ...task, status: "completed", completed_at: "2026-07-22T01:00:00Z" });
    renderRoute("/workflow-automation/tasks", "/workflow-automation/tasks", <TaskInboxPage />, {
      configuration,
    });
    fireEvent.click(await screen.findByRole("button", { name: /Approve \/ complete/u }));
    fireEvent.click(screen.getByRole("button", { name: "Complete task" }));
    await waitFor(() => expect(complete).toHaveBeenCalledWith("task-1", expect.any(Object)));
    expect(await screen.findByRole("status")).toHaveTextContent("completed");
  });
  it("rejects tasks with evidence and refreshes stale conflicts", async () => {
    const reject = vi
      .spyOn(workflowService.tasks, "reject")
      .mockRejectedValueOnce(
        new WorkflowApiError("Version conflict", 409, "stale_task", "corr-stale", [], true)
      )
      .mockResolvedValue({ ...task, status: "rejected", completed_at: "2026-07-22T01:05:00Z" });
    renderRoute("/workflow-automation/tasks", "/workflow-automation/tasks", <TaskInboxPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Reject/u }));
    expect(screen.getByRole("button", { name: "Reject task" })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Insufficient evidence" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject task" }));
    expect(await screen.findByText(/No duplicate decision/u)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh task state" }));
    fireEvent.click(screen.getByRole("button", { name: /Reject/u }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Still blocked" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject task" }));
    await waitFor(() => expect(reject).toHaveBeenCalledTimes(2));
  });
  it("applies task filters and clears filtered empty state", async () => {
    vi.spyOn(workflowService.tasks, "list").mockResolvedValue(page<WorkflowTaskListDTO>([]));
    const user = userEvent.setup();
    renderRoute("/workflow-automation/tasks", "/workflow-automation/tasks", <TaskInboxPage />);
    expect(await screen.findByText("All caught up")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Filter task status"), "completed");
    expect(await screen.findByText("No tasks match these filters")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(screen.getByLabelText("Filter task status")).toHaveValue("pending"));
  });
  it("runs governed workflow list lifecycle actions from permitted rows", async () => {
    const row: WorkflowListDTO = {
      ...definition,
      step_count: definition.steps.length,
      allowed_actions: ["view", "edit", "publish", "clone", "archive", "delete"],
    };
    vi.spyOn(workflowService.workflows, "list").mockResolvedValue(page([row]));
    const publish = vi.spyOn(workflowService.workflows, "publish").mockResolvedValue(definition);
    const archive = vi.spyOn(workflowService.workflows, "archive").mockResolvedValue(definition);
    vi.spyOn(workflowService.workflows, "clone").mockResolvedValue({
      ...definition,
      id: "workflow-copy",
    });
    const remove = vi.spyOn(workflowService.workflows, "delete").mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderRoute(
      "/workflow-automation/workflows",
      "/workflow-automation/workflows",
      <WorkflowListPage />
    );
    expect(await screen.findByRole("button", { name: "Purchase approval" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Publish Purchase approval" }));
    await user.click(screen.getByRole("button", { name: "Archive Purchase approval" }));
    expect(screen.getByRole("button", { name: "Clone Purchase approval" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete Purchase approval" }));
    await user.click(screen.getByRole("button", { name: "Delete draft" }));
    await waitFor(() => expect(publish).toHaveBeenCalledWith("workflow-1", expect.any(Object)));
    expect(archive).toHaveBeenCalledWith("workflow-1", expect.any(Object));
    expect(remove).toHaveBeenCalledWith("workflow-1");
  });
});
