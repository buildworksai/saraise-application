import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScheduleEditor } from "../../components/ScheduleEditor";
import type {
  DefinitionListDTO,
  OrchestrationConfigurationDTO,
  PageResult,
} from "../../contracts";
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
  ] as const)("renders record not found for invalid %s route IDs", async (_name, page, pattern, path, method) => {
    const blockedRequest = service[method];
    renderRoute(page, pattern, path);

    expect(await screen.findByText("Record not found")).toBeInTheDocument();
    expect(blockedRequest).not.toHaveBeenCalled();
  });
});
