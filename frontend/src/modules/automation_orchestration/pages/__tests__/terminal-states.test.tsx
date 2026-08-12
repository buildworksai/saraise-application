/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- Route-state tests assert service spies directly and keep full governed page fixtures local. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScheduleEditor } from "../../components/ScheduleEditor";
import type { DefinitionListDTO, OrchestrationConfigurationDTO, PageResult } from "../../contracts";
import { automationOrchestrationService as service } from "../../services/automation-orchestration-service";
import { DefinitionDetailPage } from "../DefinitionDetailPage";
import { DefinitionEditPage } from "../DefinitionEditPage";
import { RunDetailPage } from "../RunDetailPage";

vi.mock("../../services/automation-orchestration-service", () => ({
  automationOrchestrationService: {
    getConfiguration: vi.fn(),
    getDefinition: vi.fn(),
    listSchedules: vi.fn(),
    listRuns: vi.fn(),
    listNodeTypes: vi.fn(),
    getSchedule: vi.fn(),
    listDefinitions: vi.fn(),
    getRun: vi.fn(),
    listTaskRuns: vi.fn(),
    listEvents: vi.fn(),
    validateDefinition: vi.fn(),
    publishDefinition: vi.fn(),
    cloneDefinition: vi.fn(),
    retireDefinition: vi.fn(),
    startRun: vi.fn(),
  },
}));

function renderRoute(element: React.ReactElement, pattern: string, path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={pattern} element={element} />
          <Route path="/automation-orchestration/runs/:runId" element={<span>run route</span>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("automation orchestration terminal route states", () => {
  const configuration = {
    environment: "development",
    cohort: "all",
    version: 1,
    enabled: true,
    rollout_percentage: 100,
    allowed_roles: [],
    document: {
      ui: {
        definition_detail_page_size: 5,
        published_definition_page_size: 10,
        skeleton_rows: 4,
        duration_seconds_threshold_ms: 60_000,
        task_run_page_size: 25,
        run_detail_poll_interval_ms: 5_000,
        event_poll_interval_ms: 5_000,
      },
    },
  } as unknown as OrchestrationConfigurationDTO;
  const emptyDefinitions = {
    items: [],
    correlationId: "corr-test",
    receivedAt: "2026-07-29T00:00:00Z",
    pagination: {
      count: 0,
      page: 1,
      page_size: 10,
      total_pages: 0,
      has_next: false,
      has_previous: false,
    },
  } satisfies PageResult<DefinitionListDTO>;

  afterEach(() => vi.clearAllMocks());

  beforeEach(() => {
    const mockedService = vi.mocked(service);
    mockedService.getConfiguration.mockResolvedValue(configuration);
    mockedService.listDefinitions.mockResolvedValue(emptyDefinitions);
    mockedService.listSchedules.mockResolvedValue({
      items: [],
      correlationId: "corr-schedules",
      receivedAt: "2026-07-29T00:00:00Z",
      pagination: { ...emptyDefinitions.pagination, page_size: 5 },
    });
    mockedService.listRuns.mockResolvedValue({
      items: [],
      correlationId: "corr-runs",
      receivedAt: "2026-07-29T00:00:00Z",
      pagination: { ...emptyDefinitions.pagination, page_size: 5 },
    });
  });

  it.each([
    [
      "definition detail",
      <DefinitionDetailPage />,
      "/automation-orchestration/definitions/:id",
      "/automation-orchestration/definitions/not-a-uuid",
      "getDefinition",
    ],
    [
      "definition edit",
      <DefinitionEditPage />,
      "/automation-orchestration/definitions/:id/edit",
      "/automation-orchestration/definitions/not-a-uuid/edit",
      "getDefinition",
    ],
    [
      "schedule edit",
      <ScheduleEditor scheduleId="not-a-uuid" />,
      "/automation-orchestration/schedules/:id/edit",
      "/automation-orchestration/schedules/not-a-uuid/edit",
      "getSchedule",
    ],
    [
      "run detail",
      <RunDetailPage />,
      "/automation-orchestration/runs/:runId",
      "/automation-orchestration/runs/not-a-uuid",
      "getRun",
    ],
  ] as const)(
    "renders record not found for invalid %s route IDs",
    async (_name, page, pattern, path, method) => {
      const blockedRequest = service[method];
      renderRoute(page, pattern, path);

      expect(await screen.findByText("Record not found")).toBeInTheDocument();
      expect(blockedRequest).not.toHaveBeenCalled();
    }
  );

  it("requires confirmation for published definition commands and carries run idempotency", async () => {
    const definitionId = "00000000-0000-4000-8000-000000000001";
    const runId = "00000000-0000-4000-8000-000000000077";
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000999");
    vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    vi.mocked(service.getDefinition).mockResolvedValue({
      id: definitionId,
      tenant_id: "00000000-0000-4000-8000-000000000002",
      key: "daily-close",
      version: 3,
      name: "Daily close",
      description: "Close ledgers",
      status: "published",
      is_current: true,
      max_parallel_tasks: 2,
      default_timeout_seconds: 120,
      default_max_attempts: 3,
      input_schema: {},
      output_schema: {},
      output_mapping: {},
      labels: {},
      graph_revision: 5,
      contract_snapshot: {},
      transition_history: [
        {
          transition: "publish",
          from: "draft",
          to: "published",
          actor_id: "operator-1",
          occurred_at: "2026-07-29T00:00:00Z",
          correlation_id: "corr-publish",
        },
      ],
      is_deleted: false,
      created_by: "operator-1",
      updated_by: "operator-1",
      created_at: "2026-07-28T00:00:00Z",
      updated_at: "2026-07-29T00:00:00Z",
      deleted_at: null,
      nodes: [
        {
          id: "node-1",
          tenant_id: "00000000-0000-4000-8000-000000000002",
          definition_id: definitionId,
          key: "extract",
          name: "Extract",
          description: "",
          node_type: "internal",
          handler_key: "extract",
          config: {},
          input_mapping: {},
          timeout_seconds: null,
          max_attempts: null,
          retry_initial_delay_seconds: 5,
          retry_backoff_multiplier: "2",
          retry_max_delay_seconds: 300,
          priority: 1,
          is_deleted: false,
          created_by: "operator-1",
          updated_by: "operator-1",
          created_at: "2026-07-28T00:00:00Z",
          updated_at: "2026-07-29T00:00:00Z",
        },
      ],
      edges: [],
    });
    vi.mocked(service.startRun).mockResolvedValue({
      id: runId,
      tenant_id: "00000000-0000-4000-8000-000000000002",
      definition_id: definitionId,
      definition_name: "Daily close",
      definition_key: "daily-close",
      definition_version: 3,
      schedule_id: null,
      parent_run_id: null,
      trigger_type: "manual",
      status: "queued",
      idempotency_key: "00000000-0000-4000-8000-000000000999",
      input: {},
      output: null,
      requested_by: "operator-1",
      correlation_id: "corr-run",
      task_count: 0,
      completed_task_count: 0,
      failed_task_count: 0,
      error_code: "",
      error_message: "",
      transition_history: [],
      started_at: null,
      completed_at: null,
      created_at: "2026-07-29T00:00:00Z",
      updated_at: "2026-07-29T00:00:00Z",
    });
    vi.mocked(service.retireDefinition).mockResolvedValue(
      {} as Awaited<ReturnType<typeof service.retireDefinition>>
    );
    const user = userEvent.setup();

    renderRoute(
      <DefinitionDetailPage />,
      "/automation-orchestration/definitions/:id",
      `/automation-orchestration/definitions/${definitionId}`
    );

    expect(await screen.findByRole("heading", { name: "Daily close" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retire" }));
    expect(service.retireDefinition).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Retire" }));
    await waitFor(() =>
      expect(service.retireDefinition).toHaveBeenCalledWith(
        definitionId,
        "00000000-0000-4000-8000-000000000999"
      )
    );

    await user.click(screen.getByRole("button", { name: "Execute" }));
    await user.clear(screen.getByLabelText("Idempotency key"));
    expect(screen.getByRole("button", { name: "Start durable run" })).toBeDisabled();
    await user.type(screen.getByLabelText("Idempotency key"), "manual-run-key");
    await user.click(screen.getByRole("button", { name: "Start durable run" }));

    await waitFor(() =>
      expect(service.startRun).toHaveBeenCalledWith({
        definition_id: definitionId,
        input: {},
        idempotency_key: "manual-run-key",
        trigger_type: "manual",
      })
    );
  });
});
