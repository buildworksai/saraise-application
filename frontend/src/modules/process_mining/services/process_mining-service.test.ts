/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- Test cases are fixture-heavy and assert mock method calls directly. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type * as ApiClientModule from "@/services/api-client";
import { ApiError, apiClient } from "@/services/api-client";
import type {
  ApiEnvelope,
  PaginatedEnvelope,
  ProcessMiningConfiguration,
  ProcessMiningConfigurationDocument,
  ProcessModelVersion,
  ProcessOverview,
} from "../contracts";
import { ENDPOINTS } from "../contracts";
import { ProcessMiningApiError, processMiningService as service } from "./process_mining-service";

vi.mock("@/services/api-client", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/services/api-client");
  return {
    ...actual,
    apiClient: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
    },
  };
});

const documentValue: ProcessMiningConfigurationDocument = {
  environment: "development",
  max_batch_events: 1000,
  max_export_events: 1000,
  max_export_bytes: 100000,
  max_conformance_events: 1000,
  text_max_length: 255,
  attributes_max_bytes: 4096,
  forbidden_attribute_keys: ["password"],
  source_module_max_length: 64,
  max_event_age_days: 365,
  future_clock_skew_seconds: 60,
  bulk_insert_batch_size: 100,
  event_query_max_days: 90,
  retention_days: 30,
  retention_min_days: 7,
  export_projection_bytes_per_event: 128,
  export_iterator_chunk_size: 500,
  checksum_chunk_bytes: 1024,
  export_expiry_days: 7,
  discovery_min_events: 10,
  discovery_min_cases: 2,
  alpha_max_activities: 50,
  heuristic_default_threshold: 0.8,
  inductive_default_threshold: 0.8,
  default_discovery_algorithm: "heuristic_miner",
  algorithm_threshold_step: 0.05,
  algorithm_threshold_min: 0.1,
  algorithm_threshold_max: 1,
  low_fitness_threshold: 0.6,
  bottleneck_reuse_minutes: 30,
  bottleneck_min_cases: 5,
  bottleneck_critical_ratio: 0.9,
  bottleneck_high_ratio: 0.7,
  bottleneck_medium_ratio: 0.5,
  tail_duration_percentile: 0.95,
  resource_concentration_threshold: 0.6,
  variant_grouping_percentage: 0.05,
  outbox_freshness_seconds: 60,
  analysis_transitions: { queued: ["running"], running: ["completed", "failed"] },
  analysis_terminal_states: ["completed", "failed", "cancelled", "timed_out"],
  export_transitions: { queued: ["running"], running: ["completed", "failed"] },
  export_terminal_states: ["completed", "failed", "cancelled", "timed_out", "expired"],
  default_time_window_days: 30,
  list_page_size: 25,
  detail_page_size: 50,
  polling_interval_ms: 5000,
  visual_zoom_min: 0.5,
  visual_zoom_max: 2,
  visual_zoom_step: 0.1,
  visual_edge_width_min: 1,
  visual_edge_width_max: 8,
  visual_frequency_divisor: 10,
  visual_duration_divisor: 60,
  visual_canvas_width: 1200,
  visual_canvas_height: 800,
  visual_node_width: 160,
  visual_node_height: 80,
  visual_layout_columns: 4,
  visual_horizontal_gap: 120,
  visual_vertical_gap: 90,
  visual_layout_padding: 40,
  download_timeout_ms: 1000,
  download_retry_attempts: 0,
  download_retry_base_ms: 1,
  download_circuit_failure_threshold: 1,
  download_circuit_reset_ms: 60000,
  enabled: true,
  rollout_roles: ["process-admin"],
  rollout_cohorts: ["all"],
};

const configuration: ProcessMiningConfiguration = {
  id: "config-1",
  version: 3,
  document: documentValue,
  limits: {},
  updated_at: "2026-07-21T00:00:00Z",
};

function envelope<T>(data: T): ApiEnvelope<T> {
  return { data, meta: { correlation_id: "corr-process", timestamp: "2026-07-21T00:00:00Z" } };
}

function paginated<T>(data: T[]): PaginatedEnvelope<T> {
  return {
    data,
    meta: {
      correlation_id: "corr-page",
      timestamp: "2026-07-21T00:00:00Z",
      pagination: {
        count: data.length,
        page: 1,
        page_size: 25,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
    },
  };
}

describe("processMiningService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn());
  });

  it("unwraps paginated responses and governed API errors with correlation evidence", async () => {
    const process: ProcessOverview = {
      process_name: "order-to-cash",
      event_count: 10,
      case_count: 2,
      last_activity: "2026-07-21T00:00:00Z",
      has_reference: false,
      model_id: null,
      last_discovery: null,
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(paginated([process]));
    await expect(service.listProcesses({ search: "order", page: 1 })).resolves.toEqual({
      items: [process],
      pagination: paginated([process]).meta.pagination,
      correlationId: "corr-page",
    });
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.PROCESSES.LIST}?search=order&page=1`);

    vi.mocked(apiClient.get).mockRejectedValueOnce(
      new ApiError("Request failed", 429, {
        error: {
          code: "QUOTA_EXCEEDED",
          message: "Quota reached",
          correlation_id: "corr-quota",
          detail: { quota: { resource: "exports", remaining: 0, reset_at: null } },
        },
      })
    );
    await expect(service.getProcess("order-to-cash")).rejects.toMatchObject({
      name: "ProcessMiningApiError",
      status: 429,
      code: "QUOTA_EXCEEDED",
      correlationId: "corr-quota",
      message: "Quota reached",
    });
  });

  it("caches configuration for export downloads and opens the circuit after configured failures", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope(configuration));
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response("export-body", { status: 200, statusText: "OK" })
    );

    await service.getConfiguration();
    const blob = await service.downloadExport("export-1");
    expect(blob.size).toBe("export-body".length);
    const firstDownloadCall = vi.mocked(fetch).mock.calls[0];
    expect(firstDownloadCall?.[0]).toBe(ENDPOINTS.EXPORTS.DOWNLOAD("export-1"));
    const requestInit = firstDownloadCall?.[1];
    expect(requestInit?.credentials).toBe("include");
    expect(requestInit?.signal).toBeInstanceOf(AbortSignal);

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 503, statusText: "Unavailable" })
    );
    await expect(service.downloadExport("export-2")).rejects.toBeInstanceOf(ProcessMiningApiError);
    await expect(service.downloadExport("export-3")).rejects.toMatchObject({
      code: "CIRCUIT_OPEN",
      status: 503,
    });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("updates cached configuration through update, rollback, import, and export routes", async () => {
    vi.mocked(apiClient.put).mockResolvedValue(envelope(configuration));
    vi.mocked(apiClient.post).mockResolvedValue(envelope(configuration));
    vi.mocked(apiClient.get).mockResolvedValue(
      envelope({
        schema_version: "1.0",
        module: "process_mining",
        version: 3,
        document: documentValue,
      })
    );

    await service.updateConfiguration(documentValue);
    await service.previewConfiguration(documentValue);
    await service.rollbackConfiguration(2);
    await service.importConfiguration({
      schema_version: "1.0",
      module: "process_mining",
      version: 2,
      document: documentValue,
    });
    await service.exportConfiguration();

    expect(apiClient.put).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.UPDATE, {
      document: documentValue,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.CONFIGURATION.PREVIEW, {
      document: documentValue,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.CONFIGURATION.ROLLBACK, {
      version: 2,
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.CONFIGURATION.IMPORT, {
      configuration: {
        schema_version: "1.0",
        module: "process_mining",
        version: 2,
        document: documentValue,
      },
    });
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.EXPORT);
  });

  it("routes mutable process mining commands through their governed endpoints", async () => {
    const event = {
      id: "event-1",
      process_name: "Order to Cash",
      source_module: "sales",
      source_event_id: "SO-1",
      case_id: "case-1",
      activity: "Create order",
      occurred_at: "2026-07-21T10:00:00Z",
      resource: null,
      ingested_at: "2026-07-21T10:01:00Z",
      created_at: "2026-07-21T10:01:00Z",
    };
    const exportItem = {
      id: "export-1",
      process_name: "Order to Cash",
      format: "csv",
      status: "queued",
      row_count: null,
      byte_size: null,
      sha256: "",
      expires_at: null,
      completed_at: null,
      error_code: "",
      created_at: "2026-07-21T10:00:00Z",
      updated_at: "2026-07-21T10:00:00Z",
    };
    const discovery = {
      id: "discovery-1",
      process_name: "Order to Cash",
      algorithm: "heuristic_miner",
      status: "queued",
      event_count: 10,
      case_count: 2,
      activity_count: 3,
      started_at: null,
      completed_at: null,
      error_code: "",
      created_at: "2026-07-21T10:00:00Z",
      updated_at: "2026-07-21T10:00:00Z",
    };
    const model = {
      id: "model-1",
      name: "Order model",
      process_name: "Order to Cash",
      description: "",
      source_kind: "imported",
      current_version_number: 1,
      reference_version_number: null,
      created_at: "2026-07-21T10:00:00Z",
      updated_at: "2026-07-21T10:00:00Z",
    };
    const version: ProcessModelVersion = {
      id: "version-1",
      process_model: "model-1",
      version: 1,
      algorithm: "heuristic_miner",
      parameters: {},
      model_data: {
        schema_version: "1.0" as const,
        nodes: [{ id: "start", label: "Start", type: "start" as const, frequency: 1 }],
        edges: [],
      },
      event_count: 1,
      case_count: 1,
      activity_count: 1,
      avg_case_duration_seconds: null,
      is_reference: false,
      published_at: "2026-07-21T10:00:00Z",
      created_at: "2026-07-21T10:00:00Z",
    };
    const conformance = {
      id: "conformance-1",
      process_model_version: "version-1",
      status: "queued",
      fitness: null,
      precision: null,
      generalization: null,
      total_cases: null,
      conformant_cases: null,
      deviating_cases: null,
      started_at: null,
      completed_at: null,
      error_code: "",
      created_at: "2026-07-21T10:00:00Z",
      updated_at: "2026-07-21T10:00:00Z",
    };
    const bottleneck = {
      id: "bottleneck-1",
      process_name: "Order to Cash",
      time_range_start: "2026-07-20T00:00:00Z",
      time_range_end: "2026-07-21T00:00:00Z",
      status: "queued",
      total_cases: 0,
      total_variants: 0,
      avg_case_duration_seconds: null,
      started_at: null,
      completed_at: null,
      error_code: "",
      created_at: "2026-07-21T10:00:00Z",
      updated_at: "2026-07-21T10:00:00Z",
    };
    vi.mocked(apiClient.get).mockResolvedValue(paginated([event]));
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce(envelope({ accepted: 1, rejected: 0, duplicates: 0, rows: [] }))
      .mockResolvedValueOnce(envelope(exportItem))
      .mockResolvedValueOnce(envelope(exportItem))
      .mockResolvedValueOnce(envelope(exportItem))
      .mockResolvedValueOnce(envelope(discovery))
      .mockResolvedValueOnce(envelope(discovery))
      .mockResolvedValueOnce(envelope(discovery))
      .mockResolvedValueOnce(envelope(model))
      .mockResolvedValueOnce(envelope(version))
      .mockResolvedValueOnce(envelope(conformance))
      .mockResolvedValueOnce(envelope(conformance))
      .mockResolvedValueOnce(envelope(conformance))
      .mockResolvedValueOnce(envelope(bottleneck))
      .mockResolvedValueOnce(envelope(bottleneck))
      .mockResolvedValueOnce(envelope(bottleneck));
    vi.mocked(apiClient.patch).mockResolvedValueOnce(envelope(model));
    vi.mocked(apiClient.delete).mockResolvedValue(undefined);

    await service.listEvents({ process_name: "Order to Cash", activity: "Create order" });
    await service.ingestEvents({
      process_name: "Order to Cash",
      source_module: "sales",
      events: [
        { case_id: "case-1", activity: "Create order", occurred_at: "2026-07-21T10:00:00Z" },
      ],
    });
    await service.createExport({
      process_name: "Order to Cash",
      format: "csv",
      event_filter: { process_name: "Order to Cash" },
      idempotency_key: "export-key",
    });
    await service.cancelExport("export-1", { transition_key: "cancel-export" });
    await service.retryExport("export-1", { transition_key: "retry-export" });
    await service.createDiscovery({
      process_name: "Order to Cash",
      algorithm: "heuristic_miner",
      parameters: { dependency_threshold: 0.8 },
      idempotency_key: "discovery-key",
    });
    await service.cancelDiscovery("discovery-1", { transition_key: "cancel-discovery" });
    await service.retryDiscovery("discovery-1", { transition_key: "retry-discovery" });
    await service.createModel({
      name: "Order model",
      process_name: "Order to Cash",
      description: "",
      model_data: version.model_data,
    });
    await service.updateModel("model-1", { name: "Order model v2", description: "Updated" });
    await service.setReference("model-1", { version_id: "version-1", transition_key: "reference" });
    await service.createConformance({
      process_model_version_id: "version-1",
      event_filter: { process_name: "Order to Cash" },
      idempotency_key: "conformance-key",
    });
    await service.cancelConformance("conformance-1", { transition_key: "cancel-conformance" });
    await service.retryConformance("conformance-1", { transition_key: "retry-conformance" });
    await service.createBottleneck({
      process_name: "Order to Cash",
      time_range_start: "2026-07-20T00:00:00Z",
      time_range_end: "2026-07-21T00:00:00Z",
      idempotency_key: "bottleneck-key",
    });
    await service.cancelBottleneck("bottleneck-1", { transition_key: "cancel-bottleneck" });
    await service.retryBottleneck("bottleneck-1", { transition_key: "retry-bottleneck" });
    await service.deleteExport("export-1");
    await service.deleteDiscovery("discovery-1");
    await service.deleteModel("model-1");
    await service.deleteConformance("conformance-1");
    await service.deleteBottleneck("bottleneck-1");

    expect(apiClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.EVENTS.LIST}?process_name=Order+to+Cash&activity=Create+order`
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.EXPORTS.CREATE, {
      process_name: "Order to Cash",
      format: "csv",
      event_filter: { process_name: "Order to Cash" },
      idempotency_key: "export-key",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(3, ENDPOINTS.EXPORTS.CANCEL("export-1"), {
      transition_key: "cancel-export",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(8, ENDPOINTS.MODELS.CREATE, {
      name: "Order model",
      process_name: "Order to Cash",
      description: "",
      model_data: version.model_data,
    });
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.MODELS.DETAIL("model-1"), {
      name: "Order model v2",
      description: "Updated",
    });
    expect(apiClient.post).toHaveBeenNthCalledWith(
      10,
      ENDPOINTS.CONFORMANCE.CREATE,
      expect.objectContaining({ idempotency_key: "conformance-key" })
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      13,
      ENDPOINTS.BOTTLENECKS.CREATE,
      expect.objectContaining({ idempotency_key: "bottleneck-key" })
    );
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.EXPORTS.DETAIL("export-1"));
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.DISCOVERIES.DETAIL("discovery-1"));
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.MODELS.DETAIL("model-1"));
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.CONFORMANCE.DETAIL("conformance-1"));
    expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.BOTTLENECKS.DETAIL("bottleneck-1"));
  });
});
