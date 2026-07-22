/* eslint-disable @typescript-eslint/unbound-method -- mocked API client functions have no receiver state. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS, withQuery, type APIEnvelope, type AgentDetail } from "../contracts";
import { aiAgentService } from "./ai-agent-service";

vi.mock("@/services/api-client", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

const meta = { correlation_id: "correlation-1", timestamp: "2026-07-23T00:00:00Z" };
const agent: AgentDetail = { id: "agent-1", name: "Reconciler", description: "", identity_type: "system_bound", subject_id: "subject-1", session_id: null, runner_key: "reference_runner", provider_config_id: null, config: {}, status: "draft", transition_history: [], created_by: "actor-1", deleted_at: null, created_at: meta.timestamp, updated_at: meta.timestamp };

describe("aiAgentService", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps governed pagination and builds encoded queries", async () => {
    const envelope: APIEnvelope<readonly AgentDetail[]> = { data: [agent], meta: { ...meta, pagination: { count: 1, page: 2, page_size: 25, total_pages: 2, has_next: false, has_previous: true } } };
    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope);
    await expect(aiAgentService.listAgents({ search: "close books", page: 2 })).resolves.toMatchObject({ items: [agent], correlationId: "correlation-1" });
    expect(apiClient.get).toHaveBeenCalledWith(withQuery(ENDPOINTS.AGENTS.LIST, { search: "close books", page: 2 }));
  });

  it("rejects a malformed list envelope without pagination", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: [], meta });
    await expect(aiAgentService.listAgents()).rejects.toThrow("omitted pagination");
  });

  it("uses PATCH for partial updates and unwraps the response", async () => {
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: agent, meta });
    await expect(aiAgentService.updateAgent(agent.id, { description: "Updated" })).resolves.toEqual(agent);
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.AGENTS.UPDATE(agent.id), { description: "Updated" });
  });

  it("posts lifecycle commands to their declared action endpoint", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: agent, meta });
    const command = { transition_key: "activate-1" };
    await aiAgentService.activateAgent(agent.id, command);
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.AGENTS.ACTIVATE(agent.id), command);
  });
});
