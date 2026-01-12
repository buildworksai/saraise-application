import { apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  Workflow,
  WorkflowInstance,
  WorkflowTask,
} from "../contracts";

export const workflowService = {
  workflows: {
    list: async () => {
      return apiClient.get<Workflow[]>(ENDPOINTS.WORKFLOWS.LIST);
    },
    get: async (id: string) => {
      return apiClient.get<Workflow>(ENDPOINTS.WORKFLOWS.DETAIL(id));
    },
    create: async (data: Partial<Workflow>) => {
      return apiClient.post<Workflow>(ENDPOINTS.WORKFLOWS.CREATE, data);
    },
    update: async (id: string, data: Partial<Workflow>) => {
      return apiClient.put<Workflow>(ENDPOINTS.WORKFLOWS.UPDATE(id), data);
    },
    delete: async (id: string) => {
      return apiClient.delete(ENDPOINTS.WORKFLOWS.DELETE(id));
    },
    publish: async (id: string) => {
      return apiClient.post(ENDPOINTS.WORKFLOWS.PUBLISH(id));
    },
    start: async (id: string, context: Record<string, unknown> = {}) => {
      return apiClient.post<WorkflowInstance>(ENDPOINTS.WORKFLOWS.START(id), {
        context,
      });
    },
  },
  instances: {
    list: async () => {
      return apiClient.get<WorkflowInstance[]>(ENDPOINTS.INSTANCES.LIST);
    },
    get: async (id: string) => {
      return apiClient.get<WorkflowInstance>(ENDPOINTS.INSTANCES.DETAIL(id));
    },
  },
  tasks: {
    list: async () => {
      return apiClient.get<WorkflowTask[]>(ENDPOINTS.TASKS.LIST);
    },
    complete: async (id: string, meta_data: Record<string, unknown> = {}) => {
      return apiClient.post<WorkflowTask>(ENDPOINTS.TASKS.COMPLETE(id), {
        meta_data,
      });
    },
    reject: async (id: string, meta_data: Record<string, unknown> = {}) => {
      return apiClient.post<WorkflowTask>(ENDPOINTS.TASKS.REJECT(id), {
        meta_data,
      });
    },
  },
};
