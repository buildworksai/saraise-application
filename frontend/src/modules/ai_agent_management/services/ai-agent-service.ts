/**
 * AI Agent Management Service
 * 
 * Service client for AI Agent Management module API calls.
 * Uses generated TypeScript types from OpenAPI schema.
 */

import { apiClient } from '@/services/api-client';
import type { components } from '@/types/api';

// Type aliases for cleaner code
type Agent = components['schemas']['Agent'];
type AgentRequest = components['schemas']['AgentRequest'];
type PatchedAgentRequest = components['schemas']['PatchedAgentRequest'];
type AgentExecution = components['schemas']['AgentExecution'];
type ApprovalRequest = components['schemas']['ApprovalRequest'];

// Re-export types for use in components
export type { Agent, AgentRequest, PatchedAgentRequest, AgentExecution, ApprovalRequest };

// Alias for backward compatibility
export type AgentCreate = AgentRequest;
export type AgentUpdate = PatchedAgentRequest;

export const aiAgentService = {
  /**
   * List all agents
   */
  listAgents: async (): Promise<Agent[]> => {
    return apiClient.get<Agent[]>('/api/v1/ai-agents/agents/');
  },

  /**
   * Get agent by ID
   */
  getAgent: async (id: string): Promise<Agent> => {
    return apiClient.get<Agent>(`/api/v1/ai-agents/agents/${id}/`);
  },

  /**
   * Create new agent
   */
  createAgent: async (data: AgentRequest): Promise<Agent> => {
    return apiClient.post<Agent>('/api/v1/ai-agents/agents/', data);
  },

  /**
   * Update agent
   */
  updateAgent: async (id: string, data: PatchedAgentRequest): Promise<Agent> => {
    return apiClient.put<Agent>(`/api/v1/ai-agents/agents/${id}/`, data);
  },

  /**
   * Delete agent
   */
  deleteAgent: async (id: string): Promise<void> => {
    return apiClient.delete(`/api/v1/ai-agents/agents/${id}/`);
  },

  /**
   * Execute agent
   */
  executeAgent: async (
    id: string,
    taskDefinition: Record<string, unknown>,
    metadata?: Record<string, unknown>
  ): Promise<AgentExecution> => {
    return apiClient.post<AgentExecution>(`/api/v1/ai-agents/agents/${id}/execute/`, {
      task_definition: taskDefinition,
      metadata: metadata ?? {},
    });
  },

  /**
   * Pause agent execution
   */
  pauseAgent: async (id: string, executionId: string): Promise<AgentExecution> => {
    return apiClient.post<AgentExecution>(`/api/v1/ai-agents/agents/${id}/pause/`, {
      execution_id: executionId,
    });
  },

  /**
   * Resume agent execution
   */
  resumeAgent: async (id: string, executionId: string): Promise<AgentExecution> => {
    return apiClient.post<AgentExecution>(`/api/v1/ai-agents/agents/${id}/resume/`, {
      execution_id: executionId,
    });
  },

  /**
   * Terminate agent execution
   */
  terminateAgent: async (id: string, executionId: string): Promise<AgentExecution> => {
    return apiClient.post<AgentExecution>(`/api/v1/ai-agents/agents/${id}/terminate/`, {
      execution_id: executionId,
    });
  },

  /**
   * List agent executions
   */
  listExecutions: async (agentId?: string): Promise<AgentExecution[]> => {
    const params = agentId ? `?agent_id=${agentId}` : '';
    return apiClient.get<AgentExecution[]>(`/api/v1/ai-agents/executions/${params}`);
  },

  /**
   * Get execution by ID
   */
  getExecution: async (id: string): Promise<AgentExecution> => {
    return apiClient.get<AgentExecution>(`/api/v1/ai-agents/executions/${id}/`);
  },

  /**
   * List approval requests
   */
  listApprovals: async (status?: string): Promise<ApprovalRequest[]> => {
    const params = status ? `?status=${status}` : '';
    return apiClient.get<ApprovalRequest[]>(`/api/v1/ai-agents/approvals/${params}`);
  },

  /**
   * Approve request
   */
  approveRequest: async (id: string): Promise<ApprovalRequest> => {
    return apiClient.post<ApprovalRequest>(`/api/v1/ai-agents/approvals/${id}/approve/`);
  },

  /**
   * Reject request
   */
  rejectRequest: async (id: string, reason: string): Promise<ApprovalRequest> => {
    return apiClient.post<ApprovalRequest>(`/api/v1/ai-agents/approvals/${id}/reject/`, {
      reason,
    });
  },
};
