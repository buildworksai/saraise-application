/* eslint-disable max-lines-per-function -- page coverage exercises query, navigation, settings, and form workflows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  PortfolioSummary,
  Project,
  ProjectActivity,
  ProjectConfiguration,
  ProjectMember,
  ProjectMilestone,
  ProjectSummary,
  Task,
  TimeEntry,
} from "../contracts";
import { activityService } from "../services/activity-service";
import { configurationService } from "../services/configuration-service";
import { memberService } from "../services/member-service";
import { milestoneService } from "../services/milestone-service";
import { projectService } from "../services/project-service";
import { taskService } from "../services/task-service";
import { timeEntryService } from "../services/time-entry-service";
import {
  ConfigurationHistoryPage,
  CreateMilestonePage,
  CreateProjectMemberPage,
  CreateProjectPage,
  CreateTaskPage,
  CreateTimeEntryPage,
  EditMilestonePage,
  EditProjectMemberPage,
  EditProjectPage,
  EditTaskPage,
  EditTimeEntryPage,
  MilestoneDetailPage,
  ProjectDashboardPage,
  ProjectDetailPage,
  ProjectMemberDetailPage,
  ProjectMemberListPage,
  ProjectListPage,
  ProjectManagementSettingsPage,
  MilestoneListPage,
  MyWorkPage,
  TaskDetailPage,
  TaskListPage,
  TimeEntryDetailPage,
  TimeEntryListPage,
} from "./ModulePages";

vi.mock("../services/project-service", () => ({
  createIdempotencyKey: vi.fn((scope: string) => `${scope}:test-key`),
  projectService: {
    create: vi.fn(),
    dashboard: vi.fn(),
    get: vi.fn(),
    list: vi.fn(),
    summary: vi.fn(),
    update: vi.fn(),
  },
}));
vi.mock("../services/task-service", () => ({
  taskService: { create: vi.fn(), get: vi.fn(), list: vi.fn(), update: vi.fn() },
}));
vi.mock("../services/member-service", () => ({
  memberService: { create: vi.fn(), get: vi.fn(), list: vi.fn(), update: vi.fn() },
}));
vi.mock("../services/time-entry-service", () => ({
  timeEntryService: { create: vi.fn(), get: vi.fn(), list: vi.fn(), update: vi.fn() },
}));
vi.mock("../services/milestone-service", () => ({
  milestoneService: { create: vi.fn(), get: vi.fn(), list: vi.fn(), update: vi.fn() },
}));
vi.mock("../services/activity-service", () => ({
  activityService: { listForProject: vi.fn() },
}));
vi.mock("../services/configuration-service", () => ({
  configurationService: { active: vi.fn(), draft: vi.fn(), versions: vi.fn() },
}));

const projects = vi.mocked(projectService);
const tasks = vi.mocked(taskService);
const members = vi.mocked(memberService);
const timeEntries = vi.mocked(timeEntryService);
const milestones = vi.mocked(milestoneService);
const activities = vi.mocked(activityService);
const configuration = vi.mocked(configurationService);

const page = <T,>(items: readonly T[]) => ({
  items,
  pagination: {
    count: items.length,
    page: 1,
    page_size: 20,
    total_pages: 1,
    has_next: false,
    has_previous: false,
  },
  correlationId: "corr-project",
});

const project: Project = {
  id: "project-1",
  project_code: "PRJ-100",
  project_name: "Hospital expansion",
  description: "Critical path renovation",
  start_date: "2026-08-01",
  end_date: "2026-12-31",
  status: "active",
  project_manager_id: "employee-1",
  budget: "100000.00",
  currency: "USD",
  transition_history: [],
  version: 7,
  archived_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  allowed_actions: ["update"],
};
const task: Task = {
  id: "task-1",
  project: "project-1",
  project_code: "PRJ-100",
  task_code: "TASK-1",
  task_name: "Pour slab",
  description: "Concrete work",
  assigned_to_id: null,
  parent_task: null,
  start_date: null,
  due_date: "2026-08-30",
  priority: "high",
  estimated_hours: "40.00",
  actual_hours: "12.00",
  percent_complete: "30.00",
  status: "in_progress",
  position: 1,
  transition_history: [],
  version: 1,
  archived_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  allowed_actions: ["update"],
};
const summary: ProjectSummary = {
  project_id: "project-1",
  task_count: 3,
  completed_task_count: 1,
  blocked_task_count: 0,
  progress_percentage: "33.33",
  milestone_count: 1,
  achieved_milestone_count: 0,
  time_hours: "12.00",
  next_due_date: "2026-08-30",
};
const dashboard: PortfolioSummary = {
  project_count: 4,
  active_project_count: 2,
  task_count: 9,
  overdue_task_count: 1,
  blocked_task_count: 0,
  upcoming_milestone_count: 3,
  budget_by_currency: [{ currency: "USD", amount: "100000.00" }],
};
const activeConfiguration: ProjectConfiguration = {
  id: "config-1",
  environment: "development",
  version: 4,
  state: "active",
  default_currency: "USD",
  project_code_pattern: "PRJ-[0-9]+",
  task_code_pattern: "TASK-[0-9]+",
  max_daily_hours: "8.00",
  max_allocation_percentage: "100.00",
  enforce_project_date_bounds: true,
  allow_future_time_entries: false,
  require_time_description: true,
  default_billable: true,
  enabled_views: ["list", "board"],
  paid_extension_rollout: { roles: ["pm"], percentage: "100" },
  change_summary: "Current policy",
  created_by_id: "operator-1",
  created_at: "2026-08-01T00:00:00Z",
};
const activity: ProjectActivity = {
  id: "activity-1",
  project: "project-1",
  entity_type: "project",
  entity_id: "project-1",
  action: "update",
  actor_id: "operator-1",
  correlation_id: "corr-activity",
  before: {},
  after: {},
  metadata: {},
  created_at: "2026-08-02T00:00:00Z",
};

const member: ProjectMember = {
  id: "member-1",
  project: "project-1",
  project_code: "PRJ-100",
  employee_id: "employee-1",
  role: "project_manager" as const,
  allocation_percentage: "75.00",
  joined_at: "2026-08-01T00:00:00Z",
  left_at: null,
  archived_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  allowed_actions: ["update"],
};

const timeEntry: TimeEntry = {
  id: "time-1",
  project: "project-1",
  project_code: "PRJ-100",
  task: "task-1",
  task_code: "TASK-1",
  employee_id: "employee-1",
  entry_date: "2026-08-03",
  hours_worked: "6.50",
  description: "Foundation review",
  billable: true,
  version: 3,
  archived_at: null,
  created_at: "2026-08-03T00:00:00Z",
  updated_at: "2026-08-03T00:00:00Z",
  allowed_actions: ["update"],
};

const milestone: ProjectMilestone = {
  id: "milestone-1",
  project: "project-1",
  project_code: "PRJ-100",
  milestone_name: "Foundation complete",
  target_date: "2026-09-01",
  achieved_date: null,
  cancelled_at: null,
  description: "Foundation delivery gate",
  version: 4,
  archived_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  allowed_actions: ["update"],
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}</output>;
}

function renderProject(route: string, element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/project-management/projects" element={element} />
          <Route path="/project-management/projects/new" element={element} />
          <Route path="/project-management/projects/:id" element={element} />
          <Route path="/project-management/projects/:id/edit" element={element} />
          <Route path="/project-management/tasks" element={element} />
          <Route path="/project-management/tasks/new" element={element} />
          <Route path="/project-management/tasks/:id" element={element} />
          <Route path="/project-management/tasks/:id/edit" element={element} />
          <Route path="/project-management/members" element={element} />
          <Route path="/project-management/members/new" element={element} />
          <Route path="/project-management/members/:id" element={element} />
          <Route path="/project-management/members/:id/edit" element={element} />
          <Route path="/project-management/time-entries" element={element} />
          <Route path="/project-management/time-entries/new" element={element} />
          <Route path="/project-management/time-entries/:id" element={element} />
          <Route path="/project-management/time-entries/:id/edit" element={element} />
          <Route path="/project-management/milestones" element={element} />
          <Route path="/project-management/milestones/new" element={element} />
          <Route path="/project-management/milestones/:id" element={element} />
          <Route path="/project-management/milestones/:id/edit" element={element} />
          <Route path="/project-management/settings" element={element} />
          <Route path="/project-management/settings/history" element={element} />
          <Route path="/project-management/my-work" element={element} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("project management module pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    projects.create.mockResolvedValue(project);
    projects.dashboard.mockResolvedValue(dashboard);
    projects.get.mockResolvedValue(project);
    projects.list.mockResolvedValue(page([project]));
    projects.summary.mockResolvedValue(summary);
    tasks.create.mockResolvedValue(task);
    tasks.get.mockResolvedValue(task);
    tasks.list.mockResolvedValue(page([task]));
    tasks.update.mockResolvedValue({ ...task, task_name: "Updated slab" });
    members.create.mockResolvedValue(member);
    members.get.mockResolvedValue(member);
    members.list.mockResolvedValue(page([]));
    members.update.mockResolvedValue({ ...member, allocation_percentage: "80.00" });
    timeEntries.create.mockResolvedValue(timeEntry);
    timeEntries.get.mockResolvedValue(timeEntry);
    timeEntries.list.mockResolvedValue(page([]));
    timeEntries.update.mockResolvedValue({ ...timeEntry, description: "Updated review" });
    milestones.create.mockResolvedValue(milestone);
    milestones.get.mockResolvedValue(milestone);
    milestones.list.mockResolvedValue(page([]));
    milestones.update.mockResolvedValue({ ...milestone, milestone_name: "Updated milestone" });
    activities.listForProject.mockResolvedValue(page([activity]));
    configuration.active.mockResolvedValue(activeConfiguration);
    configuration.draft.mockResolvedValue({
      ...activeConfiguration,
      id: "draft-1",
      state: "draft",
    });
    configuration.versions.mockResolvedValue(page([activeConfiguration]));
  });

  it("lists projects, commits search filters, and renders the empty state through the real page", async () => {
    const user = userEvent.setup();
    renderProject("/project-management/projects", <ProjectListPage />);

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByText("PRJ-100 · Hospital expansion")).toBeInTheDocument();

    projects.list.mockResolvedValueOnce(page([]));
    await user.type(screen.getByLabelText("Search"), "blocked");
    fireEvent.keyDown(screen.getByLabelText("Search"), { key: "Enter" });

    await waitFor(() =>
      expect(projects.list).toHaveBeenLastCalledWith({
        page: 1,
        search: "blocked",
        ordering: undefined,
      })
    );
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
  });

  it("renders project workspace summary, switches related tabs, and shows activity correlation evidence", async () => {
    const user = userEvent.setup();
    renderProject("/project-management/projects/project-1", <ProjectDetailPage />);

    expect(await screen.findByRole("heading", { name: "Hospital expansion" })).toBeInTheDocument();
    expect(screen.getByText("33.33%")).toBeInTheDocument();
    expect(screen.getByText("Pour slab")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "activity" }));

    expect(await screen.findByText("update · corr-activity")).toBeInTheDocument();
  });

  it("surfaces dashboard load errors with retry", async () => {
    projects.dashboard
      .mockRejectedValueOnce(new Error("dashboard unavailable"))
      .mockResolvedValueOnce(dashboard);
    projects.list.mockResolvedValue(page([project]));
    renderProject("/project-management/projects", <ProjectDashboardPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("dashboard unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Hospital expansion")).toBeInTheDocument();
  });

  it("creates a task through the real form and navigates to the saved task", async () => {
    const user = userEvent.setup();
    renderProject("/project-management/tasks/new", <CreateTaskPage />);

    await user.type(screen.getByLabelText("Project ID"), "project-1");
    await user.type(screen.getByLabelText("Task code"), "task-1");
    await user.type(screen.getByLabelText("Task name"), "Pour slab");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(tasks.create).toHaveBeenCalledWith(
      expect.objectContaining({
        project: "project-1",
        task_code: "TASK-1",
        task_name: "Pour slab",
      }),
      "task:test-key"
    );
    await waitFor(() => {
      expect(screen.getAllByLabelText("location").at(-1)).toHaveTextContent(
        "/project-management/tasks/task-1"
      );
    });
  });

  it("renders each operational list with the service-specific title, route, and subtitle", async () => {
    members.list.mockResolvedValue(
      page([
        {
          id: "member-1",
          project: "project-1",
          project_code: "PRJ-100",
          employee_id: "employee-1",
          role: "project_manager",
          allocation_percentage: "75.00",
          joined_at: "2026-08-01T00:00:00Z",
          left_at: null,
          archived_at: "2026-08-03T00:00:00Z",
          created_at: "2026-08-01T00:00:00Z",
          updated_at: "2026-08-02T00:00:00Z",
          allowed_actions: ["update"],
        },
      ])
    );
    timeEntries.list.mockResolvedValue(
      page([
        {
          id: "time-1",
          project: "project-1",
          project_code: "PRJ-100",
          task: "task-1",
          task_code: "TASK-1",
          employee_id: "employee-1",
          entry_date: "2026-08-03",
          hours_worked: "6.50",
          description: "Foundation review",
          billable: true,
          version: 1,
          archived_at: null,
          created_at: "2026-08-03T00:00:00Z",
          updated_at: "2026-08-03T00:00:00Z",
          allowed_actions: ["update"],
        },
      ])
    );
    milestones.list.mockResolvedValue(
      page([
        {
          id: "milestone-1",
          project: "project-1",
          project_code: "PRJ-100",
          milestone_name: "Foundation complete",
          description: "Foundation delivery gate",
          target_date: "2026-09-01",
          achieved_date: null,
          cancelled_at: null,
          version: 1,
          archived_at: null,
          created_at: "2026-08-01T00:00:00Z",
          updated_at: "2026-08-02T00:00:00Z",
          allowed_actions: ["update"],
        },
      ])
    );

    const cases = [
      {
        path: "/project-management/tasks",
        element: <TaskListPage />,
        heading: "Tasks",
        content: "TASK-1 · Pour slab",
      },
      {
        path: "/project-management/members",
        element: <ProjectMemberListPage />,
        heading: "Project team",
        content: "employee-1",
      },
      {
        path: "/project-management/time-entries",
        element: <TimeEntryListPage />,
        heading: "Time entries",
        content: "2026-08-03 · 6.50 hours",
      },
      {
        path: "/project-management/milestones",
        element: <MilestoneListPage />,
        heading: "Milestones",
        content: "Foundation complete",
      },
    ] as const;

    for (const entry of cases) {
      const rendered = renderProject(entry.path, entry.element);
      expect(await screen.findByRole("heading", { name: entry.heading })).toBeInTheDocument();
      expect(screen.getByText(entry.content)).toBeInTheDocument();
      rendered.unmount();
    }

    expect(screen.queryByText("Foundation complete")).not.toBeInTheDocument();
  });

  it("drafts settings changes and renders version history", async () => {
    const user = userEvent.setup();
    const { unmount } = renderProject(
      "/project-management/settings",
      <ProjectManagementSettingsPage />
    );

    expect(await screen.findByText("Maximum daily hours")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Change summary"));
    await user.type(screen.getByLabelText("Change summary"), "Tighten time controls");
    await user.click(screen.getByRole("button", { name: "Create draft and preview" }));

    await waitFor(() =>
      expect(configuration.draft).toHaveBeenCalledWith(
        expect.objectContaining({
          environment: "development",
          change_summary: "Tighten time controls",
        })
      )
    );
    expect(await screen.findByRole("link", { name: "Review version history" })).toBeInTheDocument();
    unmount();

    renderProject("/project-management/settings/history", <ConfigurationHistoryPage />);
    expect(await screen.findByText("Version 4")).toBeInTheDocument();
    expect(screen.getByText("Current policy")).toBeInTheDocument();
  });

  it("creates project, member, time entry, and milestone wrappers with scoped idempotency keys", async () => {
    const user = userEvent.setup();
    const createCases = [
      {
        path: "/project-management/projects/new",
        element: <CreateProjectPage />,
        fill: async () => {
          await user.type(screen.getByLabelText("Project code"), "prj-200");
          await user.type(screen.getByLabelText("Project name"), "Warehouse refit");
        },
        assert: () =>
          expect(projects.create).toHaveBeenCalledWith(
            expect.objectContaining({
              project_code: "PRJ-200",
              project_name: "Warehouse refit",
              currency: "USD",
            }),
            "project:test-key"
          ),
      },
      {
        path: "/project-management/members/new",
        element: <CreateProjectMemberPage />,
        fill: async () => {
          await user.type(screen.getByLabelText("Project ID"), "project-1");
          await user.type(screen.getByLabelText("Employee ID"), "employee-2");
        },
        assert: () =>
          expect(members.create).toHaveBeenCalledWith(
            expect.objectContaining({ project: "project-1", employee_id: "employee-2" }),
            "member:test-key"
          ),
      },
      {
        path: "/project-management/time-entries/new",
        element: <CreateTimeEntryPage />,
        fill: async () => {
          await user.type(screen.getByLabelText("Project ID"), "project-1");
          await user.type(screen.getByLabelText("Employee ID"), "employee-2");
          await user.clear(screen.getByLabelText("Hours"));
          await user.type(screen.getByLabelText("Hours"), "2.25");
        },
        assert: () =>
          expect(timeEntries.create).toHaveBeenCalledWith(
            expect.objectContaining({
              project: "project-1",
              employee_id: "employee-2",
              hours_worked: "2.25",
            }),
            "time:test-key"
          ),
      },
      {
        path: "/project-management/milestones/new",
        element: <CreateMilestonePage />,
        fill: async () => {
          await user.type(screen.getByLabelText("Project ID"), "project-1");
          await user.type(screen.getByLabelText("Milestone name"), "Commissioning");
          await user.type(screen.getByLabelText("Target date"), "2026-09-30");
        },
        assert: () =>
          expect(milestones.create).toHaveBeenCalledWith(
            expect.objectContaining({
              project: "project-1",
              milestone_name: "Commissioning",
              target_date: "2026-09-30",
            }),
            "milestone:test-key"
          ),
      },
    ] as const;

    for (const entry of createCases) {
      const rendered = renderProject(entry.path, entry.element);
      await entry.fill();
      await user.click(screen.getByRole("button", { name: "Save" }));
      await waitFor(entry.assert);
      rendered.unmount();
    }
  });

  it("renders detail wrappers for task, member, time entry, milestone, and the fail-closed my-work page", async () => {
    const cases = [
      {
        path: "/project-management/tasks/task-1",
        element: <TaskDetailPage />,
        heading: "TASK-1 · Pour slab",
        content: "Actual hours",
      },
      {
        path: "/project-management/members/member-1",
        element: <ProjectMemberDetailPage />,
        heading: "Team member",
        content: "75.00%",
      },
      {
        path: "/project-management/time-entries/time-1",
        element: <TimeEntryDetailPage />,
        heading: "6.50 hours on 2026-08-03",
        content: "Foundation review",
      },
      {
        path: "/project-management/milestones/milestone-1",
        element: <MilestoneDetailPage />,
        heading: "Foundation complete",
        content: "Foundation delivery gate",
      },
      {
        path: "/project-management/my-work",
        element: <MyWorkPage />,
        heading: "My work",
        content: "Employee identity is not linked",
      },
    ] as const;

    for (const entry of cases) {
      const rendered = renderProject(entry.path, entry.element);
      expect(await screen.findByRole("heading", { name: entry.heading })).toBeInTheDocument();
      expect(screen.getByText(entry.content)).toBeInTheDocument();
      rendered.unmount();
    }
  });

  it("updates edit wrappers with persisted version and idempotency evidence", async () => {
    const user = userEvent.setup();
    const editCases = [
      {
        path: "/project-management/projects/project-1/edit",
        element: <EditProjectPage />,
        label: "Project name",
        value: "Hospital expansion phase two",
        button: "Save",
        assert: () =>
          expect(projects.update).toHaveBeenCalledWith(
            "project-1",
            expect.objectContaining({
              project_name: "Hospital expansion phase two",
              version: 7,
              idempotency_key: "project-update:test-key",
            })
          ),
      },
      {
        path: "/project-management/tasks/task-1/edit",
        element: <EditTaskPage />,
        label: "Value",
        value: "Updated slab",
        button: "Save changes",
        assert: () =>
          expect(tasks.update).toHaveBeenCalledWith("task-1", {
            task_name: "Updated slab",
            version: 1,
            idempotency_key: "task-update:test-key",
          }),
      },
      {
        path: "/project-management/members/member-1/edit",
        element: <EditProjectMemberPage />,
        label: "Value",
        value: "80.00",
        button: "Save changes",
        assert: () =>
          expect(members.update).toHaveBeenCalledWith("member-1", {
            allocation_percentage: "80.00",
            idempotency_key: "member-update:test-key",
          }),
      },
      {
        path: "/project-management/time-entries/time-1/edit",
        element: <EditTimeEntryPage />,
        label: "Value",
        value: "Updated review",
        button: "Save changes",
        assert: () =>
          expect(timeEntries.update).toHaveBeenCalledWith("time-1", {
            description: "Updated review",
            version: 3,
            idempotency_key: "time-update:test-key",
          }),
      },
      {
        path: "/project-management/milestones/milestone-1/edit",
        element: <EditMilestonePage />,
        label: "Value",
        value: "Updated milestone",
        button: "Save changes",
        assert: () =>
          expect(milestones.update).toHaveBeenCalledWith("milestone-1", {
            milestone_name: "Updated milestone",
            version: 4,
            idempotency_key: "milestone-update:test-key",
          }),
      },
    ] as const;

    for (const entry of editCases) {
      const rendered = renderProject(entry.path, entry.element);
      const input = await screen.findByLabelText(entry.label);
      await user.clear(input);
      await user.type(input, entry.value);
      await user.click(screen.getByRole("button", { name: entry.button }));
      await waitFor(entry.assert);
      rendered.unmount();
    }
  });

  it("surfaces settings and history errors with retryable operator evidence", async () => {
    configuration.active
      .mockRejectedValueOnce(new Error("configuration unavailable"))
      .mockResolvedValueOnce(activeConfiguration);
    const { unmount } = renderProject(
      "/project-management/settings",
      <ProjectManagementSettingsPage />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("configuration unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Maximum daily hours")).toBeInTheDocument();
    unmount();

    configuration.versions
      .mockRejectedValueOnce(new Error("history unavailable"))
      .mockResolvedValueOnce(page([activeConfiguration]));
    renderProject("/project-management/settings/history", <ConfigurationHistoryPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("history unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Version 4")).toBeInTheDocument();
  });
});
