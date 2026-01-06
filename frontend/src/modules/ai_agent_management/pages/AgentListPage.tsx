/**
 * Agent List Page
 * 
 * Displays all AI agents with filtering, search, and CRUD operations.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { aiAgentService } from '../services/ai-agent-service';
import { Plus, Search, Bot } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const AgentListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const [filterType, setFilterType] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');

  const { data: agents, isLoading, error, refetch } = useQuery({
    queryKey: ['ai-agents', deferredSearchTerm],
    queryFn: aiAgentService.listAgents,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => aiAgentService.deleteAgent(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-agents'] });
      toast.success('Agent deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete agent. Please try again.');
    },
  });

  const filteredAgents = agents?.filter((agent) => {
    const matchesSearch = deferredSearchTerm === '' || 
      agent.name.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      agent.description?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
    
    const matchesType = filterType === 'all' || agent.identity_type === filterType;
    const matchesStatus = filterStatus === 'all'
      ? true
      : filterStatus === 'active'
      ? agent.is_active
      : filterStatus === 'inactive'
      ? !agent.is_active
      : false;

    return matchesSearch && matchesType && matchesStatus;
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this agent?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={6} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load agents. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredAgents || filteredAgents.length === 0) {
    if (agents?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-3xl font-bold text-foreground">AI Agents</h1>
            <Button onClick={() => navigate('/ai-agents/create')}>
              <Plus className="w-4 h-4 mr-2" />
              Create Agent
            </Button>
          </div>
          <EmptyState
            icon={Bot}
            title="No AI agents yet"
            description="Create your first AI agent to automate workflows, execute tasks, and orchestrate business processes."
            action={{
              label: "Create Agent",
              onClick: () => navigate('/ai-agents/create')
            }}
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">AI Agents</h1>
        <Button onClick={() => navigate('/ai-agents/create')}>
          <Plus className="w-4 h-4" />
          Create Agent
        </Button>
      </div>

      {/* Filters */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search agents..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>

        <Select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          options={[
            { value: 'all', label: 'All Types' },
            { value: 'user_bound', label: 'User-Bound' },
            { value: 'system_bound', label: 'System-Bound' },
          ]}
        />

        <Select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          options={[
            { value: 'all', label: 'All Status' },
            { value: 'active', label: 'Active' },
            { value: 'inactive', label: 'Inactive' },
          ]}
        />
      </div>

      {/* Agents Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Framework
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredAgents?.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">
                  No agents found matching your filters
                </td>
              </tr>
            ) : (
              filteredAgents?.map((agent) => (
                <tr key={agent.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{agent.name}</div>
                    {agent.description && (
                      <div className="text-sm text-muted-foreground">{agent.description}</div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={agent.identity_type === 'user_bound' ? 'active' : 'inactive'} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {agent.framework}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={agent.is_active ? 'active' : 'inactive'} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {agent.created_at ? new Date(agent.created_at).toLocaleDateString() : 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => agent.id && navigate(`/ai-agents/${agent.id}`)}
                      className="text-primary hover:opacity-80 mr-4"
                      disabled={!agent.id}
                    >
                      View
                    </button>
                    <button
                      onClick={() => agent.id && navigate(`/ai-agents/${agent.id}/edit`)}
                      className="text-primary hover:opacity-80 mr-4"
                      disabled={!agent.id}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => {
                        if (agent.id) {
                          void handleDelete(agent.id);
                        }
                      }}
                      className="text-destructive hover:opacity-80"
                      disabled={!agent.id}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
};
