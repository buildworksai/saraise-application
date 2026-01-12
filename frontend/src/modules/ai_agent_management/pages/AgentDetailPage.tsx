/**
 * Agent Detail Page
 *
 * Displays agent details, execution history, quota usage, and controls.
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { aiAgentService } from '../services/ai-agent-service';
import { Play, Pause, Square, Edit } from 'lucide-react';

export const AgentDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: agent, isLoading: agentLoading } = useQuery({
    queryKey: ['ai-agent', id],
    queryFn: () => aiAgentService.getAgent(id!),
    enabled: !!id,
  });

  const { data: executions, isLoading: executionsLoading } = useQuery({
    queryKey: ['ai-agent-executions', id],
    queryFn: () => aiAgentService.listExecutions(id),
    enabled: !!id,
  });

  const executeMutation = useMutation({
    mutationFn: (taskDefinition: Record<string, unknown>) =>
      aiAgentService.executeAgent(id!, taskDefinition),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-agent-executions', id] });
    },
  });

  const pauseMutation = useMutation({
    mutationFn: (executionId: string) => aiAgentService.pauseAgent(id!, executionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-agent-executions', id] });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (executionId: string) => aiAgentService.resumeAgent(id!, executionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-agent-executions', id] });
    },
  });

  const terminateMutation = useMutation({
    mutationFn: (executionId: string) => aiAgentService.terminateAgent(id!, executionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-agent-executions', id] });
    },
  });

  const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null && !Array.isArray(value);

  const handleExecute = async () => {
    const taskDefinition = prompt('Enter task definition (JSON):');
    if (taskDefinition) {
      try {
        const parsed: unknown = JSON.parse(taskDefinition);
        if (!isRecord(parsed)) {
          alert('Task definition must be a JSON object');
          return;
        }
        await executeMutation.mutateAsync(parsed);
      } catch {
        alert('Invalid JSON');
      }
    }
  };

  if (agentLoading) {
    return (
      <div className="p-8">
        <div className="text-gray-600">Loading agent...</div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="p-8">
        <div className="text-red-600">Agent not found</div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">{agent.name}</h1>
          {agent.description && (
            <p className="mt-2 text-gray-600">{agent.description}</p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              void handleExecute();
            }}
            disabled={executeMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
          >
            <Play className="w-4 h-4" />
            Execute
          </button>
          <button
            onClick={() => navigate(`/ai-agents/${id}/edit`)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            <Edit className="w-4 h-4" />
            Edit
          </button>
        </div>
      </div>

      {/* Agent Details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Agent Information</h2>
          <dl className="space-y-2">
            <div>
              <dt className="text-sm font-medium text-gray-500">Identity Type</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {agent.identity_type === 'user_bound' ? 'User-Bound' : 'System-Bound'}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Framework</dt>
              <dd className="mt-1 text-sm text-gray-900">{agent.framework}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Status</dt>
              <dd className="mt-1">
                <span
                  className={`px-2 py-1 text-xs rounded-full ${
                    agent.is_active
                      ? 'bg-green-100 text-green-800'
                      : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {agent.is_active ? 'Active' : 'Inactive'}
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-gray-500">Created</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {agent.created_at ? new Date(agent.created_at).toLocaleString() : 'N/A'}
              </dd>
            </div>
          </dl>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Configuration</h2>
          <pre className="text-xs bg-gray-50 p-4 rounded overflow-auto">
            {JSON.stringify(agent.config, null, 2)}
          </pre>
        </div>
      </div>

      {/* Execution History */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Execution History</h2>
        </div>
        {executionsLoading ? (
          <div className="p-8 text-center text-gray-600">Loading executions...</div>
        ) : executions && executions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    State
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Started
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Completed
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Error
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {executions.map((execution) => (
                  <tr key={execution.id}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`px-2 py-1 text-xs rounded-full ${
                          execution.state === 'running'
                            ? 'bg-blue-100 text-blue-800'
                            : execution.state === 'completed'
                            ? 'bg-green-100 text-green-800'
                            : execution.state === 'failed'
                            ? 'bg-red-100 text-red-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {execution.state}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {execution.started_at
                        ? new Date(execution.started_at).toLocaleString()
                        : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {execution.completed_at
                        ? new Date(execution.completed_at).toLocaleString()
                        : '-'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {execution.error_message ?? '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      {execution.state === 'running' && (
                        <>
                          <button
                            onClick={() => execution.id && pauseMutation.mutate(execution.id)}
                            className="text-yellow-600 hover:text-yellow-900 mr-4"
                            title="Pause"
                            disabled={!execution.id}
                          >
                            <Pause className="w-4 h-4 inline" />
                          </button>
                          <button
                            onClick={() => execution.id && terminateMutation.mutate(execution.id)}
                            className="text-red-600 hover:text-red-900"
                            title="Terminate"
                            disabled={!execution.id}
                          >
                            <Square className="w-4 h-4 inline" />
                          </button>
                        </>
                      )}
                      {execution.state === 'paused' && (
                        <button
                          onClick={() => execution.id && resumeMutation.mutate(execution.id)}
                          className="text-green-600 hover:text-green-900"
                          title="Resume"
                          disabled={!execution.id}
                        >
                          <Play className="w-4 h-4 inline" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-8 text-center text-gray-500">No executions yet</div>
        )}
      </div>
    </div>
  );
};
