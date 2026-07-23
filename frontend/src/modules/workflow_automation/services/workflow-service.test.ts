/* eslint-disable @typescript-eslint/unbound-method -- Vitest assertions intentionally reference mocks. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import { ENDPOINTS, type GovernedEnvelope, type WorkflowListDTO } from "../contracts";
import { WorkflowApiError, workflowService } from "./workflow-service";

vi.mock("@/services/api-client", () => ({ ApiError: class ApiError extends Error { constructor(message: string, readonly status: number, readonly details?: unknown, readonly code?: string, readonly correlationId?: string) { super(message); } }, apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

const workflow: WorkflowListDTO = { id: "workflow-1", key: "purchase_approval", version: 2, name: "Purchase approval", description: "Govern purchasing", workflow_type: "approval", trigger_type: "manual", trigger_config: {}, status: "published", step_count: 2, created_by_name: "Asha", published_at: "2026-07-22T00:00:00Z", created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-22T00:00:00Z", allowed_actions: ["view", "clone", "start"] };
const envelope: GovernedEnvelope<readonly WorkflowListDTO[]> = { data: [workflow], meta: { correlation_id: "corr-list", timestamp: "2026-07-22T00:00:00Z", pagination: { count: 1, page: 1, page_size: 20, total_pages: 1, has_next: false, has_previous: false } } };

describe("workflow service governed contract", () => {
  beforeEach(() => vi.clearAllMocks());
  it("unwraps list evidence and sends server-side filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope);
    const result = await workflowService.workflows.list({ status: "published", page: 2 });
    expect(result.items).toEqual([workflow]); expect(result.correlationId).toBe("corr-list");
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.WORKFLOWS.LIST}?status=published&page=2`);
  });
  it("fails explicitly when pagination evidence is missing", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: { correlation_id: "corr-bad", timestamp: "2026-07-22T00:00:00Z" } });
    await expect(workflowService.tasks.list()).rejects.toMatchObject({ code: "invalid_response", correlationId: "corr-bad" });
  });
  it("preserves stable correlation and field errors", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new ApiError("failed", 409, { error: { code: "edit_conflict", message: "Newer revision", detail: { field_errors: [{ field: "expected_updated_at", code: "stale", message: "Reload" }] }, correlation_id: "corr-conflict" } }));
    const failure = await workflowService.workflows.clone("workflow-1").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(WorkflowApiError); expect(failure).toMatchObject({ status: 409, code: "edit_conflict", correlationId: "corr-conflict" });
  });
  it("uses the governed catalog for paid extension discovery", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [], meta: envelope.meta });
    await workflowService.catalog.actions(); await workflowService.catalog.lookup("manufacturing.work-centres", "line");
    expect(apiClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.CATALOG.ACTIONS);
    expect(apiClient.get).toHaveBeenNthCalledWith(2, `${ENDPOINTS.CATALOG.LOOKUP("manufacturing.work-centres")}?search=line`);
  });
});
