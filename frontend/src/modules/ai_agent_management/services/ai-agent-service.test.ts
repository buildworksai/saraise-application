/**
 * AI Agent Service Tests
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { aiAgentService } from './ai-agent-service';
import { apiClient } from '@/services/api-client';

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
        { id: '1', name: 'Agent 1', identity_type: 'assistant', is_active: true },
        { id: '2', name: 'Agent 2', identity_type: 'assistant', is_active: false },
      ];

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockAgents);

      const result = await aiAgentService.listAgents();

      expect(result).toEqual(mockAgents);
      expect(apiClient.get).toHaveBeenCalled();
      const callArgs = apiClient.get.mock.calls[0];
      expect(callArgs[0]).toContain('/api/v1/ai-agents/agents/');
    });
  });

  describe('getAgent', () => {
    it('should fetch single agent', async () => {
      const mockAgent = { id: '1', name: 'Agent 1', identity_type: 'assistant', is_active: true };

      vi.mocked(apiClient.get).mockResolvedValueOnce(mockAgent);

      const result = await aiAgentService.getAgent('1');

      expect(result).toEqual(mockAgent);
      expect(apiClient.get).toHaveBeenCalled();
      const callArgs = apiClient.get.mock.calls[0];
      expect(callArgs[0]).toContain('/api/v1/ai-agents/agents/1/');
    });
  });

  describe('createAgent', () => {
    it('should create new agent', async () => {
      const agentData = {
        name: 'New Agent',
        description: 'Test agent',
        identity_type: 'assistant' as const,
      };
      const mockAgent = { id: '1', ...agentData, is_active: true };

      vi.mocked(apiClient.post).mockResolvedValueOnce(mockAgent);

      const result = await aiAgentService.createAgent(agentData);

      expect(result).toEqual(mockAgent);
      expect(apiClient.post).toHaveBeenCalled();
      const callArgs = apiClient.post.mock.calls[0];
      expect(callArgs[0]).toContain('/api/v1/ai-agents/agents/');
    });
  });

  describe('updateAgent', () => {
    it('should update agent', async () => {
      const updateData = { name: 'Updated Agent' };
      const mockAgent = { id: '1', name: 'Updated Agent', identity_type: 'assistant', is_active: true };

      vi.mocked(apiClient.put).mockResolvedValueOnce(mockAgent);

      const result = await aiAgentService.updateAgent('1', updateData);

      expect(result).toEqual(mockAgent);
      expect(apiClient.put).toHaveBeenCalled();
      const callArgs = apiClient.put.mock.calls[0];
      expect(callArgs[0]).toContain('/api/v1/ai-agents/agents/1/');
    });
  });

  describe('deleteAgent', () => {
    it('should delete agent', async () => {
      vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);

      await aiAgentService.deleteAgent('1');

      expect(apiClient.delete).toHaveBeenCalled();
      const callArgs = apiClient.delete.mock.calls[0];
      expect(callArgs[0]).toContain('/api/v1/ai-agents/agents/1/');
    });
  });
});

