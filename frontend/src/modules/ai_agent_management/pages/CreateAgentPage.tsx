/**
 * Create Agent Page
 * 
 * Form for creating a new AI agent with validation.
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { aiAgentService, type AgentCreate } from '../services/ai-agent-service';

const agentSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  identity_type: z.enum(['user_bound', 'system_bound']),
  subject_id: z.string().min(1, 'Subject ID is required'),
  session_id: z.string().optional(),
  framework: z.string().min(1, 'Framework is required'),
  config: z.record(z.unknown()).optional(),
}).refine(
  (data) => {
    // User-bound agents must have session_id
    if (data.identity_type === 'user_bound' && !data.session_id) {
      return false;
    }
    return true;
  },
  {
    message: 'User-bound agents must have a session ID',
    path: ['session_id'],
  }
);

type AgentFormData = z.infer<typeof agentSchema>;

export const CreateAgentPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useForm<AgentFormData>({
    resolver: zodResolver(agentSchema),
    defaultValues: {
      name: '',
      description: '',
      identity_type: 'user_bound',
      subject_id: '',
      session_id: '',
      framework: 'langgraph',
      config: {},
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: AgentCreate) => aiAgentService.createAgent(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-agents'] });
      toast.success('Agent created successfully');
      navigate('/ai-agents');
    },
    onError: () => {
      toast.error('Failed to create agent. Please try again.');
    },
  });

  const onSubmit = async (data: AgentFormData) => {
    try {
      await createMutation.mutateAsync({
        name: data.name,
        description: data.description,
        identity_type: data.identity_type,
        subject_id: data.subject_id,
        session_id: data.session_id,
        framework: data.framework,
        config: data.config ?? {},
      });
    } catch (err) {
      // Error handling is done by mutation
      console.error('Failed to create agent:', err);
    }
  };

  const parseConfig = (value: string): Record<string, unknown> => {
    if (!value.trim()) {
      return {};
    }
    try {
      const parsed: unknown = JSON.parse(value);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return {};
    }
    return {};
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Create AI Agent</h1>

      <form
        onSubmit={(event) => {
          void form.handleSubmit(onSubmit)(event);
        }}
        className="space-y-6"
      >
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700">
              Name *
            </label>
            <input
              {...form.register('name')}
              type="text"
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
            {form.formState.errors.name && (
              <p className="mt-1 text-sm text-red-600">{form.formState.errors.name.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700">
              Description
            </label>
            <textarea
              {...form.register('description')}
              rows={3}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label htmlFor="identity_type" className="block text-sm font-medium text-gray-700">
              Identity Type *
            </label>
            <select
              {...form.register('identity_type')}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="user_bound">User-Bound Agent</option>
              <option value="system_bound">System-Bound Agent</option>
            </select>
            {form.formState.errors.identity_type && (
              <p className="mt-1 text-sm text-red-600">
                {form.formState.errors.identity_type.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="subject_id" className="block text-sm font-medium text-gray-700">
              Subject ID *
            </label>
            <input
              {...form.register('subject_id')}
              type="text"
              placeholder="User ID or system role ID"
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
            {form.formState.errors.subject_id && (
              <p className="mt-1 text-sm text-red-600">
                {form.formState.errors.subject_id.message}
              </p>
            )}
          </div>

          {form.watch('identity_type') === 'user_bound' && (
            <div>
              <label htmlFor="session_id" className="block text-sm font-medium text-gray-700">
                Session ID *
              </label>
              <input
                {...form.register('session_id')}
                type="text"
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              />
              {form.formState.errors.session_id && (
                <p className="mt-1 text-sm text-red-600">
                  {form.formState.errors.session_id.message}
                </p>
              )}
            </div>
          )}

          <div>
            <label htmlFor="framework" className="block text-sm font-medium text-gray-700">
              Framework *
            </label>
            <select
              {...form.register('framework')}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="langgraph">LangGraph</option>
              <option value="crewai">CrewAI</option>
              <option value="autogen">AutoGen</option>
              <option value="custom">Custom</option>
            </select>
            {form.formState.errors.framework && (
              <p className="mt-1 text-sm text-red-600">
                {form.formState.errors.framework.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="config" className="block text-sm font-medium text-gray-700">
              Configuration (JSON)
            </label>
            <textarea
              {...form.register('config', {
                setValueAs: (value) => {
                  return parseConfig(String(value));
                },
              })}
              rows={6}
              placeholder='{"key": "value"}'
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm font-mono text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>

        <div className="flex justify-end gap-4">
          <button
            type="button"
            onClick={() => navigate('/ai-agents')}
            className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {createMutation.isPending ? 'Creating...' : 'Create Agent'}
          </button>
        </div>

        {createMutation.isError && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            Failed to create agent. Please try again.
          </div>
        )}
      </form>
    </div>
  );
};
