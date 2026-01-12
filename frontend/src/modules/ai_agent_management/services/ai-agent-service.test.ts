/**
 * AI Agent Service Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { aiAgentService } from './ai-agent-service';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';

// Mock apiClient
vi.mock('@/services/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('aiAgentService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listAgents', () => {
    it('should fetch list of agents', async () => {
      const mockAgents = [
        { id: '1', name: 'Agent 1', identity_type: 'user_bound' as const, subject_id: 'user-1', framework: 'langgraph', is_active: true },
        { id: '2', name: 'Agent 2', identity_type: 'system_bound' as const, subject_id: 'role-1', framework: 'crewai', is_active: false },
      ];

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockAgents);

      const result = await aiAgentService.listAgents();

      expect(result).toEqual(mockAgents);
      expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.AGENTS.LIST);
    });
  });

  describe('getAgent', () => {
    it('should fetch single agent', async () => {
      const mockAgent = { id: '1', name: 'Agent 1', identity_type: 'user_bound' as const, subject_id: 'user-1', framework: 'langgraph', is_active: true };

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockAgent);

      const result = await aiAgentService.getAgent('1');

      expect(result).toEqual(mockAgent);
      expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.AGENTS.DETAIL('1'));
    });
  });

  describe('createAgent', () => {
    it('should create new agent', async () => {
      const agentData = {
        name: 'New Agent',
        description: 'Test agent',
        identity_type: 'user_bound' as const,
        subject_id: 'user-123',
        framework: 'langgraph',
      };
      const mockAgent = { id: '1', ...agentData, is_active: true };

      vi.mocked(apiClient.post).mockResolvedValueOnce(mockAgent);

      const result = await aiAgentService.createAgent(agentData);

      expect(result).toEqual(mockAgent);
      expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.AGENTS.CREATE, agentData);
    });
  });

  describe('updateAgent', () => {
    it('should update agent', async () => {
      const updateData = { name: 'Updated Agent' };
      const mockAgent = { id: '1', name: 'Updated Agent', identity_type: 'user_bound' as const, subject_id: 'user-1', framework: 'langgraph', is_active: true };

      vi.mocked(apiClient.put).mockResolvedValueOnce(mockAgent);

      const result = await aiAgentService.updateAgent('1', updateData);

      expect(result).toEqual(mockAgent);
      expect(apiClient.put).toHaveBeenCalledWith(ENDPOINTS.AGENTS.UPDATE('1'), updateData);
    });
  });

  describe('deleteAgent', () => {
    it('should delete agent', async () => {
      vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);

      await aiAgentService.deleteAgent('1');

      expect(apiClient.delete).toHaveBeenCalledWith(ENDPOINTS.AGENTS.DELETE('1'));
    });
  });
});
