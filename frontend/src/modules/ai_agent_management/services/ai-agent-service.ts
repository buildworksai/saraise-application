/**
 * AI Agent Management Service
 * 
 * Service client for AI Agent Management module API calls.
 * 
 * MIGRATED: Now uses contracts.ts for types and endpoints.
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */

import { apiClient } from '@/services/api-client';
import type {
  Agent,
  AgentRequest,
  AgentUpdate,
  AgentExecution,
  ApprovalRequest,
  AgentCreate,
} from '../contracts';
import { ENDPOINTS } from '../contracts';

// Re-export types for use in components
export type {
  Agent,
  AgentRequest,
  AgentUpdate,
  AgentExecution,
  ApprovalRequest,
  AgentCreate,
};

export const aiAgentService = {
  /**
   * List all agents
   */
  listAgents: async (): Promise<Agent[]> => {
    return apiClient.get<Agent[]>(ENDPOINTS.AGENTS.LIST);
  },

  /**
   * Get agent by ID
   */
  getAgent: async (id: string): Promise<Agent> => {
    return apiClient.get<Agent>(ENDPOINTS.AGENTS.DETAIL(id));
  },

  /**
   * Create new agent
   */
  createAgent: async (data: AgentRequest): Promise<Agent> => {
    return apiClient.post<Agent>(ENDPOINTS.AGENTS.CREATE, data);
  },

  /**
   * Update agent
   */
  updateAgent: async (id: string, data: AgentUpdate): Promise<Agent> => {
    return apiClient.put<Agent>(ENDPOINTS.AGENTS.UPDATE(id), data);
  },

  /**
   * Delete agent
   */
  deleteAgent: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.AGENTS.DELETE(id));
  },

  /**
   * Execute agent
   */
  executeAgent: async (
    id: string,
    taskDefinition: Record<string, unknown>,
    metadata?: Record<string, unknown>
  ): Promise<AgentExecution> => {
    return apiClient.post<AgentExecution>(ENDPOINTS.AGENTS.EXECUTE(id), {
      task_definition: taskDefinition,
      metadata: metadata ?? {},
    });
  },

  /**
   * Pause agent execution
   */
  pauseAgent: async (id: string, executionId: string): Promise<AgentExecution> => {
    return apiClient.post<AgentExecution>(ENDPOINTS.AGENTS.PAUSE(id), {
      execution_id: executionId,
    });
  },

  /**
   * Resume agent execution
   */
  resumeAgent: async (id: string, executionId: string): Promise<AgentExecution> => {
    return apiClient.post<AgentExecution>(ENDPOINTS.AGENTS.RESUME(id), {
      execution_id: executionId,
    });
  },

  /**
   * Terminate agent execution
   */
  terminateAgent: async (id: string, executionId: string): Promise<AgentExecution> => {
    return apiClient.post<AgentExecution>(ENDPOINTS.AGENTS.TERMINATE(id), {
      execution_id: executionId,
    });
  },

  /**
   * List agent executions
   */
  listExecutions: async (agentId?: string): Promise<AgentExecution[]> => {
    const queryParams = new URLSearchParams();
    if (agentId) queryParams.append('agent_id', agentId);
    const queryString = queryParams.toString();
    const url = queryString ? `${ENDPOINTS.EXECUTIONS.LIST}?${queryString}` : ENDPOINTS.EXECUTIONS.LIST;
    return apiClient.get<AgentExecution[]>(url);
  },

  /**
   * Get execution by ID
   */
  getExecution: async (id: string): Promise<AgentExecution> => {
    return apiClient.get<AgentExecution>(ENDPOINTS.EXECUTIONS.DETAIL(id));
  },

  /**
   * List approval requests
   */
  listApprovals: async (status?: string): Promise<ApprovalRequest[]> => {
    const queryParams = new URLSearchParams();
    if (status) queryParams.append('status', status);
    const queryString = queryParams.toString();
    const url = queryString ? `${ENDPOINTS.APPROVALS.LIST}?${queryString}` : ENDPOINTS.APPROVALS.LIST;
    return apiClient.get<ApprovalRequest[]>(url);
  },

  /**
   * Approve request
   */
  approveRequest: async (id: string): Promise<ApprovalRequest> => {
    return apiClient.post<ApprovalRequest>(ENDPOINTS.APPROVALS.APPROVE(id));
  },

  /**
   * Reject request
   */
  rejectRequest: async (id: string, reason: string): Promise<ApprovalRequest> => {
    return apiClient.post<ApprovalRequest>(ENDPOINTS.APPROVALS.REJECT(id), {
      reason,
    });
  },
};
