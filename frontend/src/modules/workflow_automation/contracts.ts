export interface WorkflowStep {
  id: string;
  workflow: string;
  name: string;
  step_type: "action" | "approval" | "notification" | "decision";
  order: number;
  config: Record<string, unknown>;
}

export interface Workflow {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  status: "draft" | "published" | "archived";
  trigger_type: "manual" | "event" | "scheduled";
  steps: WorkflowStep[];
  created_at: string;
  updated_at: string;
}

export interface WorkflowInstance {
  id: string;
  tenant_id: string;
  workflow: string;
  workflow_name: string;
  current_step: string | null;
  current_step_name: string | null;
  state: "pending" | "running" | "completed" | "failed" | "cancelled";
  context_data: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
}

export interface WorkflowTask {
  id: string;
  tenant_id: string;
  instance: string;
  workflow_name: string;
  step: string;
  step_name: string;
  assignee: string | null;
  status: "pending" | "completed" | "rejected" | "cancelled";
  due_date: string | null;
  created_at: string;
  completed_at: string | null;
  meta_data: Record<string, unknown>;
}

export const MODULE_API_PREFIX = "/api/v1/workflow-automation";

export const ENDPOINTS = {
  WORKFLOWS: {
    LIST: `${MODULE_API_PREFIX}/workflows/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/workflows/${id}/`,
    CREATE: `${MODULE_API_PREFIX}/workflows/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/workflows/${id}/`,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/workflows/${id}/`,
    PUBLISH: (id: string) => `${MODULE_API_PREFIX}/workflows/${id}/publish/`,
    START: (id: string) => `${MODULE_API_PREFIX}/workflows/${id}/start/`,
  },
  INSTANCES: {
    LIST: `${MODULE_API_PREFIX}/instances/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/instances/${id}/`,
  },
  TASKS: {
    LIST: `${MODULE_API_PREFIX}/tasks/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/tasks/${id}/`,
    COMPLETE: (id: string) => `${MODULE_API_PREFIX}/tasks/${id}/complete/`,
    REJECT: (id: string) => `${MODULE_API_PREFIX}/tasks/${id}/reject/`,
  },
};
