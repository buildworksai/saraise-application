/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- Test cases are fixture-heavy and assert mock method calls directly. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import type {
  APIEnvelope,
  ConfigurationPreviewDTO,
  DefinitionListDTO,
  OrchestrationConfigurationDTO,
} from "../../contracts";
import { ENDPOINTS } from "../../contracts";
import { automationOrchestrationService as service } from "../../services/automation-orchestration-service";

vi.mock("@/services/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const definition: DefinitionListDTO = {
  id: "00000000-0000-4000-8000-000000000001",
  tenant_id: "00000000-0000-4000-8000-000000000002",
  key: "daily-close",
  version: 1,
  name: "Daily close",
  description: "Close daily ledgers",
  status: "published",
  is_current: true,
  graph_revision: 2,
  node_count: 3,
  schedule_count: 1,
  last_run_at: null,
  success_rate: null,
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const listEnvelope: APIEnvelope<readonly DefinitionListDTO[]> = {
  data: [definition],
  meta: {
    correlation_id: "corr-1",
    timestamp: "2026-07-21T00:00:00Z",
    pagination: {
      count: 1,
      page: 1,
      page_size: 25,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
  },
};

describe("automation orchestration service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps governed paginated list envelopes and preserves metadata", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(listEnvelope);
    const result = await service.listDefinitions({ status: "published", page: 1 });
    expect(result.items).toEqual([definition]);
    expect(result.pagination.count).toBe(1);
    expect(result.correlationId).toBe("corr-1");
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.DEFINITIONS.LIST}?status=published&page=1`
    );
  });

  it("fails explicitly when a list omits governed pagination", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [],
      meta: { correlation_id: "corr-2", timestamp: "2026-07-21T00:00:00Z" },
    });
    await expect(service.listDefinitions()).rejects.toThrow("without pagination metadata");
  });

  it("uses PATCH for draft updates and POST for graph validation", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ data: definition, meta: listEnvelope.meta });
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { valid: true, validated_revision: 2, issues: [] },
      meta: listEnvelope.meta,
    });
    await service.updateDefinition(definition.id, { name: "Close", expected_revision: 2 });
    await service.validateDefinition(definition.id);
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.DEFINITIONS.UPDATE(definition.id), {
      name: "Close",
      expected_revision: 2,
    });
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.DEFINITIONS.VALIDATE(definition.id), {});
  });

  it("delegates deletion without fabricating a response", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);
    await expect(service.deleteNode("node-id")).resolves.toBeUndefined();
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.NODES.DELETE("node-id"));
  });

  it("queries configuration by environment and cohort while dropping blank filters", async () => {
    const configuration = {
      environment: "saas",
      cohort: "risk",
      version: 3,
      enabled: true,
      rollout_percentage: 50,
      allowed_roles: ["automation-admin"],
      document: { limits: {}, defaults: {} },
    } as unknown as OrchestrationConfigurationDTO;
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: configuration, meta: listEnvelope.meta })
      .mockResolvedValueOnce(listEnvelope);

    await expect(service.getConfiguration("saas", "risk")).resolves.toBe(configuration);
    await expect(service.listRuns({ status: "failed", search: "", page: 2 })).resolves.toEqual({
      items: [definition],
      pagination: listEnvelope.meta.pagination,
      correlationId: "corr-1",
      receivedAt: "2026-07-21T00:00:00Z",
    });

    expect(apiClient.get).toHaveBeenNthCalledWith(
      1,
      `${ENDPOINTS.CONFIGURATION.DETAIL}?environment=saas&cohort=risk`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(2, `${ENDPOINTS.RUNS.LIST}?status=failed&page=2`);
  });

  it("routes configuration preview, import, export, rollback, and transition actions", async () => {
    const request = {
      environment: "development",
      cohort: "all",
      document: { limits: {}, defaults: {} },
      enabled: true,
      rollout_percentage: 100,
      allowed_roles: [],
    } as unknown as Parameters<typeof service.updateConfiguration>[0];
    const preview: ConfigurationPreviewDTO = {
      valid: true,
      changed_sections: ["limits"],
      before: {} as ConfigurationPreviewDTO["before"],
      after: {} as ConfigurationPreviewDTO["after"],
    };
    vi.mocked(apiClient.post).mockResolvedValue({ data: preview, meta: listEnvelope.meta });
    vi.mocked(apiClient.get).mockResolvedValue({ data: request, meta: listEnvelope.meta });

    await service.previewConfiguration(request);
    await service.importConfiguration(request);
    await service.exportConfiguration("development", "all");
    await service.rollbackConfiguration("development", "all", 2);
    await service.reconcileTaskRun("task-1", "compensate");

    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.CONFIGURATION.PREVIEW, request);
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.CONFIGURATION.IMPORT, request);
    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATION.EXPORT}?environment=development&cohort=all`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.CONFIGURATION.ROLLBACK, {
      environment: "development",
      cohort: "all",
      version: 2,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(4, ENDPOINTS.TASK_RUNS.RECONCILE("task-1"), {
      action: "compensate",
      evidence: {},
    });
  });

  it("routes definition lifecycle, node, and edge operations without mutating guarded payloads", async () => {
    const detail = {
      ...definition,
      max_parallel_tasks: 4,
      default_timeout_seconds: 120,
      default_max_attempts: 3,
      input_schema: {},
      output_schema: {},
      output_mapping: {},
      labels: {},
      contract_snapshot: {},
      transition_history: [],
      is_deleted: false,
      created_by: "user-1",
      updated_by: "user-1",
      deleted_at: null,
      nodes: [],
      edges: [],
    };
    const node = {
      id: "node-1",
      tenant_id: definition.tenant_id,
      definition_id: definition.id,
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
      created_by: "user-1",
      updated_by: "user-1",
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-21T00:00:00Z",
    };
    const edge = {
      id: "edge-1",
      tenant_id: definition.tenant_id,
      definition_id: definition.id,
      upstream_node_id: "node-1",
      downstream_node_id: "node-2",
      condition: "on_success",
      priority: 1,
      is_deleted: false,
      created_by: "user-1",
      updated_by: "user-1",
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-21T00:00:00Z",
    };
    vi.mocked(apiClient.post).mockResolvedValue({ data: detail, meta: listEnvelope.meta });
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: detail, meta: listEnvelope.meta })
      .mockResolvedValueOnce({ data: detail, meta: listEnvelope.meta })
      .mockResolvedValueOnce({ data: [node], meta: listEnvelope.meta })
      .mockResolvedValueOnce({ data: node, meta: listEnvelope.meta })
      .mockResolvedValueOnce({ data: [edge], meta: listEnvelope.meta })
      .mockResolvedValueOnce({ data: edge, meta: listEnvelope.meta });
    vi.mocked(apiClient.patch)
      .mockResolvedValueOnce({ data: node, meta: listEnvelope.meta })
      .mockResolvedValueOnce({ data: edge, meta: listEnvelope.meta });

    await service.createDefinition({ key: "close", name: "Close", input_schema: {} });
    await service.publishDefinition(definition.id, "transition-publish");
    await service.cloneDefinition(definition.id);
    await service.retireDefinition(definition.id, "transition-retire");
    await service.getDefinition(definition.id);
    await service.getDefinitionSnapshot(definition.id);
    await service.listNodes(definition.id);
    await service.getNode("node-1");
    await service.updateNode("node-1", { timeout_seconds: 90, config: { guarded: true } });
    await service.listEdges(definition.id);
    await service.getEdge("edge-1");
    await service.updateEdge("edge-1", { condition: "always", priority: 2 });

    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.DEFINITIONS.CREATE, {
      key: "close",
      name: "Close",
      input_schema: {},
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.DEFINITIONS.PUBLISH(definition.id),
      {
        transition_key: "transition-publish",
      }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.DEFINITIONS.CLONE(definition.id),
      {}
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(4, ENDPOINTS.DEFINITIONS.RETIRE(definition.id), {
      transition_key: "transition-retire",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.DEFINITIONS.DETAIL(definition.id));
    expect(apiClient.get).toHaveBeenNthCalledWith(2, ENDPOINTS.DEFINITIONS.SNAPSHOT(definition.id));
    expect(apiClient.get).toHaveBeenNthCalledWith(3, ENDPOINTS.DEFINITIONS.NODES(definition.id));
    expect(apiClient.get).toHaveBeenNthCalledWith(4, ENDPOINTS.NODES.DETAIL("node-1"));
    expect(apiClient.patch).toHaveBeenNthCalledWith(1, ENDPOINTS.NODES.UPDATE("node-1"), {
      timeout_seconds: 90,
      config: { guarded: true },
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(5, ENDPOINTS.DEFINITIONS.EDGES(definition.id));
    expect(apiClient.get).toHaveBeenNthCalledWith(6, ENDPOINTS.EDGES.DETAIL("edge-1"));
    expect(apiClient.patch).toHaveBeenNthCalledWith(2, ENDPOINTS.EDGES.UPDATE("edge-1"), {
      condition: "always",
      priority: 2,
    });
  });

  it("routes schedules, runs, task evidence, node catalog, and health checks", async () => {
    const schedule = {
      id: "schedule-1",
      tenant_id: definition.tenant_id,
      definition_id: definition.id,
      name: "Hourly close",
      cron_expression: "0 * * * *",
      timezone: "UTC",
      status: "active",
      misfire_policy: "skip",
      concurrency_policy: "forbid",
      input: {},
      next_run_at: "2026-07-21T01:00:00Z",
      last_enqueued_at: null,
      transition_history: [],
      is_deleted: false,
      deleted_at: null,
      created_by: "user-1",
      updated_by: "user-1",
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-21T00:00:00Z",
    };
    const run = {
      id: "run-1",
      tenant_id: definition.tenant_id,
      definition_id: definition.id,
      definition_name: definition.name,
      definition_key: definition.key,
      definition_version: definition.version,
      schedule_id: schedule.id,
      parent_run_id: null,
      trigger_type: "schedule",
      status: "running",
      input: {},
      output: null,
      requested_by: "user-1",
      idempotency_key: "idem-1",
      correlation_id: "corr-run",
      task_count: 1,
      completed_task_count: 0,
      failed_task_count: 0,
      error_code: "",
      error_message: "",
      transition_history: [],
      started_at: "2026-07-21T00:00:00Z",
      completed_at: null,
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-21T00:00:00Z",
    };
    vi.mocked(apiClient.post).mockResolvedValue({ data: schedule, meta: listEnvelope.meta });
    vi.mocked(apiClient.patch).mockResolvedValue({ data: schedule, meta: listEnvelope.meta });
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: schedule, meta: listEnvelope.meta })
      .mockResolvedValueOnce({ data: run, meta: listEnvelope.meta })
      .mockResolvedValueOnce(listEnvelope)
      .mockResolvedValueOnce({ data: run, meta: listEnvelope.meta })
      .mockResolvedValueOnce(listEnvelope)
      .mockResolvedValueOnce({ data: run, meta: listEnvelope.meta })
      .mockResolvedValueOnce(listEnvelope)
      .mockResolvedValueOnce(listEnvelope)
      .mockResolvedValueOnce({
        data: { status: "ready", checks: { scheduler: "ok" } },
        meta: listEnvelope.meta,
      });

    await service.createSchedule({
      definition_id: definition.id,
      name: "Hourly close",
      cron_expression: "0 * * * *",
      timezone: "UTC",
      misfire_policy: "skip",
      concurrency_policy: "forbid",
      input: {},
    });
    await service.updateSchedule("schedule-1", { name: "Hourly close v2", input: {} });
    await service.pauseSchedule("schedule-1", "pause-key");
    await service.resumeSchedule("schedule-1", "resume-key");
    await service.retireSchedule("schedule-1", "retire-key");
    await service.getSchedule("schedule-1");
    await service.startRun({
      definition_id: definition.id,
      input: {},
      idempotency_key: "idem-1",
      trigger_type: "manual",
    });
    await service.listSchedules({ status: "active", search: "", page_size: 25 });
    await service.getRun("run-1");
    await service.pauseRun("run-1", { transition_key: "pause-run" });
    await service.resumeRun("run-1", { transition_key: "resume-run" });
    await service.cancelRun("run-1", { transition_key: "cancel-run" });
    await service.retryRun("run-1", { idempotency_key: "retry-run" });
    await service.listTaskRuns("run-1", { status: "failed", page: 2 });
    await service.getTaskRun("task-1");
    await service.retryTaskRun("task-1", { idempotency_key: "retry-task" });
    await service.listEvents("run-1");
    await service.listNodeTypes(50);
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);
    await service.getHealth();
    await service.deleteSchedule("schedule-1");
    await service.deleteEdge("edge-1");

    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.SCHEDULES.CREATE, {
      definition_id: definition.id,
      name: "Hourly close",
      cron_expression: "0 * * * *",
      timezone: "UTC",
      misfire_policy: "skip",
      concurrency_policy: "forbid",
      input: {},
    });
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.SCHEDULES.UPDATE("schedule-1"), {
      name: "Hourly close v2",
      input: {},
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.SCHEDULES.PAUSE("schedule-1"), {
      transition_key: "pause-key",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(5, ENDPOINTS.RUNS.START, {
      definition_id: definition.id,
      input: {},
      idempotency_key: "idem-1",
      trigger_type: "manual",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.SCHEDULES.LIST}?status=active&page_size=25`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(6, ENDPOINTS.RUNS.PAUSE("run-1"), {
      transition_key: "pause-run",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(10, ENDPOINTS.TASK_RUNS.RETRY("task-1"), {
      idempotency_key: "retry-task",
    });
    expect(apiClient.get).toHaveBeenNthCalledWith(
      4,
      `${ENDPOINTS.RUNS.TASK_RUNS("run-1")}?status=failed&page=2`
    );
    expect(apiClient.get).toHaveBeenNthCalledWith(7, `${ENDPOINTS.NODE_TYPES}?page_size=50`);
    expect(apiClient.get).toHaveBeenNthCalledWith(8, ENDPOINTS.HEALTH);
    expect(apiClient.delete).toHaveBeenNthCalledWith(1, ENDPOINTS.SCHEDULES.DELETE("schedule-1"));
    expect(apiClient.delete).toHaveBeenNthCalledWith(2, ENDPOINTS.EDGES.DELETE("edge-1"));
  });
});
