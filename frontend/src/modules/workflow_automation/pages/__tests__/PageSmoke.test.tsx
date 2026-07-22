/* eslint-disable @typescript-eslint/unbound-method -- Vitest spies intentionally reference service methods. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { HandlerDescriptorDTO, PaginatedResult, WorkflowDetailDTO, WorkflowInstanceDetailDTO, WorkflowInstanceListDTO, WorkflowTaskDetailDTO, WorkflowTaskListDTO } from "../../contracts";
import { workflowService } from "../../services/workflow-service";
import { TaskInboxPage } from "../TaskInboxPage";
import { WorkflowCreatePage } from "../WorkflowCreatePage";
import { WorkflowDetailPage } from "../WorkflowDetailPage";
import { WorkflowEditPage } from "../WorkflowEditPage";
import { WorkflowInstanceDetailPage } from "../WorkflowInstanceDetailPage";
import { WorkflowInstanceListPage } from "../WorkflowInstanceListPage";
import { WorkflowTaskDetailPage } from "../WorkflowTaskDetailPage";

const pagination = { count: 1, page: 1, page_size: 20, total_pages: 1, has_next: false, has_previous: false } as const;
const transition = { transition_key: "transition-1", command: "publish", from_state: "draft", to_state: "published", actor_id: "user-1", occurred_at: "2026-07-22T00:00:00Z", correlation_id: "corr-1" } as const;
const step = { id: "step-1", key: "approve", name: "Manager approval", step_type: "approval", order: 1, config: { assignment_kind: "role", assignee_id: "role-1", due_in_seconds: 86400, rejection_behavior: "fail", reject_step_key: null }, timeout_seconds: 86400, timeout_action: "fail", is_terminal: true, created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-22T00:00:00Z" } as const;
const definition: WorkflowDetailDTO = { id: "workflow-1", key: "purchase_approval", version: 2, name: "Purchase approval", description: "Govern purchasing", workflow_type: "approval", trigger_type: "manual", status: "draft", created_by_name: "Asha", published_at: null, created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-22T00:00:00Z", allowed_actions: ["view", "edit", "publish", "delete"], required_context_schema: {}, transition_history: [transition], steps: [step], versions: [{ id: "workflow-1", version: 2, status: "draft", updated_at: "2026-07-22T00:00:00Z" }], execution_statistics: { total: 4, active: 1, completed: 2, failed: 1, completion_rate: 0.5 }, handler_health: [] };
const task: WorkflowTaskDetailDTO = { id: "task-1", instance_id: "instance-1", workflow_id: "workflow-1", workflow_name: "Purchase approval", workflow_version: 2, step_id: "step-1", step_name: "Manager approval", assignment_kind: "role", assignment_label: "Purchasing managers", subject: "PO-1042", status: "pending", due_date: "2026-07-23T00:00:00Z", created_at: "2026-07-22T00:00:00Z", completed_at: null, correlation_id: "corr-task", allowed_actions: ["view", "complete", "reject"], safe_context: { amount: 1250, supplier: "Acme" }, meta_data: {}, transition_history: [], completed_by_name: null };
const instance: WorkflowInstanceDetailDTO = { id: "instance-1", workflow_id: "workflow-1", workflow_name: "Purchase approval", workflow_version: 2, state: "waiting", current_step_name: "Manager approval", entity_type: "purchase_order", entity_id: "entity-1", subject: "PO-1042", priority: 7, correlation_id: "corr-instance", started_by_name: "Asha", started_at: "2026-07-22T00:00:00Z", completed_at: null, created_at: "2026-07-22T00:00:00Z", failure_code: "", failure_message: "", allowed_actions: ["view", "cancel"], context_data: { amount: 1250 }, result_data: {}, current_step: step, transition_history: [transition], tasks: [task] };
const descriptor: HandlerDescriptorDTO = { key: "core.context_projection.v1", display_name: "Project context", description: "Safely projects context", category: "Core", owning_module: "workflow_automation", schema_version: "1.0", descriptor_fingerprint: "sha256:test", required_permission: "workflow_automation.workflow:create", required_entitlement: "module.workflow_automation", availability: "available", reason: null, ui_schema: [{ kind: "text", key: "path", label: "Context path", required: true }], input_schema: {}, output_schema: {}, idempotent: true, network_access: false };
function page<T>(items: readonly T[]): PaginatedResult<T> { return { items, pagination: { ...pagination, count: items.length, total_pages: items.length ? 1 : 0 }, correlationId: "corr-list", receivedAt: "2026-07-22T00:00:00Z" }; }
function renderRoute(path: string, route: string, pageElement: React.ReactElement) { const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path={route} element={pageElement}/></Routes></MemoryRouter></QueryClientProvider>); }

describe("workflow contextual pages", () => {
  beforeEach(() => {
    vi.spyOn(workflowService.workflows, "get").mockResolvedValue(definition);
    vi.spyOn(workflowService.catalog, "actions").mockResolvedValue([descriptor]);
    vi.spyOn(workflowService.catalog, "conditions").mockResolvedValue([]);
    vi.spyOn(workflowService.catalog, "assignees").mockResolvedValue([{ id: "role-1", label: "Purchasing managers", description: null, kind: "role" }]);
    vi.spyOn(workflowService.instances, "list").mockResolvedValue(page<WorkflowInstanceListDTO>([instance]));
    vi.spyOn(workflowService.instances, "get").mockResolvedValue(instance);
    vi.spyOn(workflowService.tasks, "list").mockResolvedValue(page<WorkflowTaskListDTO>([task]));
    vi.spyOn(workflowService.tasks, "get").mockResolvedValue(task);
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders workflow definition evidence and lifecycle actions", async () => { renderRoute("/workflow-automation/workflows/workflow-1", "/workflow-automation/workflows/:id", <WorkflowDetailPage/>); expect(await screen.findByText("Purchase approval")).toBeInTheDocument(); expect(screen.getByText("Step graph")).toBeInTheDocument(); expect(screen.getByRole("button", { name: /Publish/u })).toBeInTheDocument(); });
  it("renders the schema-driven create designer without raw identifiers", async () => { renderRoute("/workflow-automation/workflows/new", "/workflow-automation/workflows/new", <WorkflowCreatePage/>); expect(await screen.findByText("Step palette")).toBeInTheDocument(); expect(screen.queryByText(/UUID/u)).not.toBeInTheDocument(); expect(screen.getByRole("button", { name: "Add approval" })).toBeInTheDocument(); });
  it("initializes the edit designer from a draft", async () => { renderRoute("/workflow-automation/workflows/workflow-1/edit", "/workflow-automation/workflows/:id/edit", <WorkflowEditPage/>); expect(await screen.findByDisplayValue("Purchase approval")).toBeInTheDocument(); expect(screen.getByDisplayValue("Manager approval")).toBeInTheDocument(); });
  it("renders server-paginated execution monitoring", async () => { renderRoute("/workflow-automation/instances", "/workflow-automation/instances", <WorkflowInstanceListPage/>); expect(await screen.findByRole("button", { name: "Purchase approval · v2" })).toBeInTheDocument(); expect(screen.getAllByText("waiting")).toHaveLength(2); });
  it("renders live execution evidence, tasks, and correlation", async () => { renderRoute("/workflow-automation/instances/instance-1", "/workflow-automation/instances/:id", <WorkflowInstanceDetailPage/>); expect(await screen.findByText("Immutable transition timeline")).toBeInTheDocument(); expect(screen.getByText("corr-instance")).toBeInTheDocument(); expect(screen.getByRole("button", { name: /Cancel execution/u })).toBeInTheDocument(); });
  it("renders the personal task inbox with safe decision actions", async () => { renderRoute("/workflow-automation/tasks", "/workflow-automation/tasks", <TaskInboxPage/>); expect(await screen.findByRole("button", { name: "Manager approval" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: /Reject/u })).toBeInTheDocument(); });
  it("renders only permitted task context and immutable history", async () => { renderRoute("/workflow-automation/tasks/task-1", "/workflow-automation/tasks/:id", <WorkflowTaskDetailPage/>); expect(await screen.findByText("Permitted business context")).toBeInTheDocument(); expect(screen.getByText("Acme")).toBeInTheDocument(); expect(screen.getByText("corr-task")).toBeInTheDocument(); });
});
