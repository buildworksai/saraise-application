/**
 * Execution Monitor Page
 * 
 * Real-time monitoring of agent executions with logs and tool invocations.
 */
import { useQuery } from '@tanstack/react-query';
import { aiAgentService } from '../services/ai-agent-service';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge, type StatusType } from '@/components/ui/StatusBadge';

export const ExecutionMonitorPage = () => {
  const { data: executions, isLoading, refetch } = useQuery({
    queryKey: ['ai-agent-executions'],
    queryFn: () => aiAgentService.listExecutions(),
    refetchInterval: 5000, // Poll every 5 seconds for real-time updates
  });

  const runningExecutions = executions?.filter((e) => e.state === 'running') ?? [];
  const recentExecutions = executions?.slice(0, 20) ?? [];

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Execution Monitor</h1>
        <Button
          onClick={() => {
            void refetch();
          }}
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </Button>
      </div>

      {/* Active Executions */}
      {runningExecutions.length > 0 && (
        <div className="mb-6 bg-amber-500/10 border border-amber-500/20 rounded-lg p-4">
          <h2 className="text-lg font-semibold text-foreground mb-2">
            Active Executions ({runningExecutions.length})
          </h2>
          <div className="space-y-2">
            {runningExecutions.map((execution) => (
              <div key={execution.id} className="bg-card text-card-foreground rounded p-3 border border-border">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium">{execution.agent_name}</span>
                    <span className="text-sm text-muted-foreground ml-2">
                      Started: {execution.started_at ? new Date(execution.started_at).toLocaleString() : '-'}
                    </span>
                  </div>
                  <StatusBadge status="running" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Executions */}
      <Card className="overflow-hidden">
        <div className="px-6 py-4 border-b border-border">
          <h2 className="text-lg font-semibold text-foreground">Recent Executions</h2>
        </div>
        {isLoading ? (
          <div className="p-8 text-center text-muted-foreground">Loading...</div>
        ) : recentExecutions.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">No executions found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead className="bg-muted">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                    Agent
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                    State
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                    Started
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                    Duration
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                    Error
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {recentExecutions.map((execution) => {
                  const duration =
                    execution.started_at && execution.completed_at
                      ? Math.round(
                          (new Date(execution.completed_at).getTime() -
                            new Date(execution.started_at).getTime()) /
                            1000
                        )
                      : null;

                  return (
                    <tr key={execution.id} className="hover:bg-muted/50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium">{execution.agent_name}</div>
                        <div className="text-sm text-muted-foreground">{execution.id}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <StatusBadge status={(execution.state as StatusType) ?? 'inactive'} />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                        {execution.started_at
                          ? new Date(execution.started_at).toLocaleString()
                          : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                        {duration !== null ? `${duration}s` : '-'}
                      </td>
                      <td className="px-6 py-4 text-sm text-muted-foreground">
                        {execution.error_message ? (
                          <span className="text-destructive">{execution.error_message}</span>
                        ) : (
                          '-'
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
