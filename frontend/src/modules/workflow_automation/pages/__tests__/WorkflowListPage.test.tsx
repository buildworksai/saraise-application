/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method -- Vitest spies intentionally reference service methods. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type * as ReactRouter from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  PaginatedResult,
  WorkflowConfigurationDTO,
  WorkflowDetailDTO,
  WorkflowListDTO,
} from "../../contracts";
import { WorkflowApiError, workflowService } from "../../services/workflow-service";
import { WorkflowListPage } from "../WorkflowListPage";

const navigateSpy = vi.hoisted(() => vi.fn());

vi.mock("react-router-dom", async (importOriginal) => {
  const actual: typeof ReactRouter = await importOriginal();
  return {
    ...actual,
    useNavigate: () => navigateSpy,
  };
});

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
function detail(overrides: Partial<WorkflowDetailDTO> = {}): WorkflowDetailDTO {
  const { step_count: discardedStepCount, ...workflowDetailBase } = workflow;
  void discardedStepCount;
  return {
    ...workflowDetailBase,
    required_context_schema: {},
    transition_history: [],
    steps: [],
    versions: [],
    execution_statistics: {
      total: 0,
      active: 0,
      completed: 0,
      failed: 0,
      completion_rate: null,
    },
    handler_health: [],
    ...overrides,
  };
}
function result(items: readonly WorkflowListDTO[]): PaginatedResult<WorkflowListDTO> {
  return {
    items,
    correlationId: "corr-list",
    receivedAt: "2026-07-22T00:00:00Z",
    pagination: {
      count: items.length,
      page: 1,
      page_size: 20,
      total_pages: items.length ? 1 : 0,
      has_next: false,
      has_previous: false,
    },
  };
}
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <WorkflowListPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { client, ...view };
}

describe("WorkflowListPage states", () => {
  afterEach(() => {
    navigateSpy.mockClear();
    vi.restoreAllMocks();
  });
  it("renders the accessible loading skeleton", async () => {
    vi.spyOn(workflowService.configuration, "get").mockResolvedValue(configuration);
    vi.spyOn(workflowService.workflows, "list").mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(await screen.findByLabelText("Loading workflow definitions")).toHaveAttribute(
      "aria-busy",
      "true"
    );
  });
  it("renders first-use and filtered-empty actions", async () => {
    vi.spyOn(workflowService.configuration, "get").mockResolvedValue(configuration);
    vi.spyOn(workflowService.workflows, "list").mockResolvedValue(result([]));
    renderPage();
    expect(await screen.findByText("Create your first governed workflow")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Build, validate, and publish a real approval or business process without scripts or raw JSON."
      )
    ).toBeInTheDocument();
    const createButtons = screen.getAllByRole("button", { name: "Create workflow" });
    expect(createButtons).toHaveLength(2);
    const [headerCreate, emptyCreate] = createButtons as [HTMLElement, HTMLElement];
    await userEvent.click(headerCreate);
    await userEvent.click(emptyCreate);
    expect(navigateSpy).toHaveBeenCalledTimes(2);
    expect(navigateSpy).toHaveBeenNthCalledWith(1, "/workflow-automation/workflows/new");
    expect(navigateSpy).toHaveBeenNthCalledWith(2, "/workflow-automation/workflows/new");
    navigateSpy.mockClear();

    fireEvent.change(screen.getByLabelText("Search workflows"), { target: { value: "missing" } });
    expect(await screen.findByText("No workflows match these filters")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Filter status"), "published");
    await userEvent.selectOptions(screen.getByLabelText("Filter workflow type"), "approval");
    await userEvent.selectOptions(screen.getByLabelText("Order workflows"), "name");

    await waitFor(() =>
      expect(workflowService.workflows.list).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 20,
        search: "missing",
        status: "published",
        workflow_type: "approval",
        ordering: "name",
      })
    );

    expect(screen.getByRole("option", { name: "approval" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "state_machine" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "sequential" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "parallel" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "conditional" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => {
      expect(screen.getByLabelText("Search workflows")).toHaveValue("");
      expect(screen.getByLabelText("Filter status")).toHaveValue("");
      expect(screen.getByLabelText("Filter workflow type")).toHaveValue("");
      expect(screen.getByLabelText("Order workflows")).toHaveValue("-updated_at");
    });

    await userEvent.selectOptions(screen.getByLabelText("Order workflows"), "name");
    expect(await screen.findByText("No workflows match these filters")).toBeInTheDocument();
    expect(
      screen.getByText("Clear the filters to restore the full definition inventory.")
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Order workflows")).toHaveValue("-updated_at")
    );
  });
  it("renders a governed correlation ID and retry", async () => {
    vi.spyOn(workflowService.configuration, "get").mockResolvedValue(configuration);
    vi.spyOn(workflowService.workflows, "list")
      .mockRejectedValueOnce(
        new WorkflowApiError("Unavailable", 503, "handler_unavailable", "corr-handler", [], true)
      )
      .mockResolvedValueOnce(result([]));
    renderPage();
    expect(await screen.findByText(/corr-handler/u)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(workflowService.workflows.list).toHaveBeenCalledTimes(2));
  });
  it("renders successful rows and hides unauthorized lifecycle actions", async () => {
    vi.spyOn(workflowService.configuration, "get").mockResolvedValue(configuration);
    vi.spyOn(workflowService.workflows, "list").mockResolvedValue(result([workflow]));
    renderPage();
    expect(await screen.findByRole("button", { name: "Purchase approval" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Edit Purchase approval" })
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clone Purchase approval" })).toBeInTheDocument();
  });
  it("executes filter, navigation, lifecycle, clone, and delete row actions", async () => {
    const actionableWorkflow: WorkflowListDTO = {
      ...workflow,
      description: "",
      status: "draft",
      allowed_actions: ["view", "edit", "publish", "clone", "archive", "delete"],
    };
    vi.spyOn(workflowService.configuration, "get").mockResolvedValue(configuration);
    vi.spyOn(workflowService.workflows, "list").mockResolvedValue(result([actionableWorkflow]));
    const publish = vi.spyOn(workflowService.workflows, "publish").mockResolvedValue(
      detail({
        ...actionableWorkflow,
        status: "published",
      })
    );
    const archive = vi.spyOn(workflowService.workflows, "archive").mockResolvedValue(
      detail({
        ...actionableWorkflow,
        status: "archived",
      })
    );
    const clone = vi.spyOn(workflowService.workflows, "clone").mockResolvedValue(
      detail({
        ...actionableWorkflow,
        id: "workflow-copy",
        name: "Purchase approval copy",
      })
    );
    const remove = vi.spyOn(workflowService.workflows, "delete").mockResolvedValue(undefined);

    const { client } = renderPage();
    const invalidate = vi.spyOn(client, "invalidateQueries");

    expect(await screen.findByText("purchase_approval · No description")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Purchase approval" }));
    expect(navigateSpy).toHaveBeenCalledWith("/workflow-automation/workflows/workflow-1");
    navigateSpy.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "View Purchase approval" }));
    expect(navigateSpy).toHaveBeenCalledWith("/workflow-automation/workflows/workflow-1");
    navigateSpy.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Edit Purchase approval" }));
    expect(navigateSpy).toHaveBeenCalledWith("/workflow-automation/workflows/workflow-1/edit");
    navigateSpy.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Publish Purchase approval" }));
    await waitFor(() => expect(publish).toHaveBeenCalledWith("workflow-1", expect.any(Object)));
    expect(publish.mock.calls[0]?.[1]?.transition_key).toMatch(/^publish:/u);
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["workflow-definitions"] })
    );

    await userEvent.click(screen.getByRole("button", { name: "Archive Purchase approval" }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith("workflow-1", expect.any(Object)));
    expect(archive.mock.calls[0]?.[1]?.transition_key).toMatch(/^archive:/u);
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["workflow-definitions"] })
    );

    await userEvent.click(screen.getByRole("button", { name: "Clone Purchase approval" }));
    await waitFor(() => expect(clone).toHaveBeenCalledWith("workflow-1"));
    await waitFor(() =>
      expect(navigateSpy).toHaveBeenCalledWith("/workflow-automation/workflows/workflow-copy/edit")
    );

    await userEvent.click(screen.getByRole("button", { name: "Delete Purchase approval" }));
    expect(screen.getByText("Delete Purchase approval?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Delete Purchase approval?")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete Purchase approval" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete draft" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("workflow-1"));
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["workflow-definitions"] })
    );
  });
});
