/**
 * Project Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Project Management are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Project - Project container */
export type Project = {
  id: string;
  tenant_id: string;
  project_code: string;
  project_name: string;
  description?: string;
  start_date?: string;
  end_date?: string;
  status: 'planning' | 'active' | 'on_hold' | 'completed' | 'cancelled';
  project_manager_id?: string;
  budget?: string;
  currency: string;
  created_at: string;
  updated_at: string;
};

/** Project create request */
export type ProjectCreate = {
  project_code: string;
  project_name: string;
  description?: string;
  start_date?: string;
  end_date?: string;
  status?: 'planning' | 'active' | 'on_hold' | 'completed' | 'cancelled';
  project_manager_id?: string;
  budget?: string;
  currency: string;
};

/** Task - Individual task within a project */
export type Task = {
  id: string;
  tenant_id: string;
  project: string;
  task_code: string;
  task_name: string;
  description?: string;
  assigned_to_id?: string;
  due_date?: string;
  estimated_hours?: string;
  actual_hours: string;
  status: 'todo' | 'in_progress' | 'review' | 'done' | 'blocked' | 'cancelled';
  parent_task_id?: string;
  created_at: string;
  updated_at: string;
};

/** Project Member - Team member assigned to project */
export type ProjectMember = {
  id: string;
  tenant_id: string;
  project: string;
  employee_id: string;
  role: string;
  allocation_percentage: string;
  created_at: string;
  updated_at: string;
};

/** Time Entry - Time logged on tasks */
export type TimeEntry = {
  id: string;
  tenant_id: string;
  project: string;
  task?: string;
  employee_id: string;
  entry_date: string;
  hours_worked: string;
  description?: string;
  created_at: string;
  updated_at: string;
};

/** Project Milestone - Key project milestone */
export type ProjectMilestone = {
  id: string;
  tenant_id: string;
  project: string;
  milestone_name: string;
  target_date: string;
  achieved_date?: string;
  description?: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/project-management';

export const ENDPOINTS = {
  PROJECTS: {
    LIST: `${MODULE_API_PREFIX}/projects/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/projects/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/projects/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/projects/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/projects/${id}/` as const,
  },
  TASKS: {
    LIST: `${MODULE_API_PREFIX}/tasks/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/tasks/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/tasks/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/tasks/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/tasks/${id}/` as const,
  },
  MEMBERS: {
    LIST: `${MODULE_API_PREFIX}/members/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/members/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/members/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/members/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/members/${id}/` as const,
  },
  TIME_ENTRIES: {
    LIST: `${MODULE_API_PREFIX}/time-entries/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/time-entries/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/time-entries/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/time-entries/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/time-entries/${id}/` as const,
  },
  MILESTONES: {
    LIST: `${MODULE_API_PREFIX}/milestones/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/milestones/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/milestones/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/milestones/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/milestones/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
