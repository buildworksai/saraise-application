/**
 * Human Resources Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Human Resources are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Department - Organizational unit */
export type Department = {
  id: string;
  tenant_id: string;
  department_code: string;
  department_name: string;
  parent_department_id?: string;
  manager_id?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Employee - Staff member */
export type Employee = {
  id: string;
  tenant_id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  department?: string;
  position?: string;
  hire_date: string;
  employment_type: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Employee create request */
export type EmployeeCreate = {
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  department?: string;
  position?: string;
  hire_date: string;
  employment_type: string;
  is_active?: boolean;
};

/** Attendance - Employee attendance record */
export type Attendance = {
  id: string;
  tenant_id: string;
  employee: string;
  attendance_date: string;
  check_in_time?: string;
  check_out_time?: string;
  hours_worked: string;
  status: string;
  created_at: string;
  updated_at: string;
};

/** Leave Request - Employee leave request */
export type LeaveRequest = {
  id: string;
  tenant_id: string;
  employee: string;
  leave_type: 'annual' | 'sick' | 'personal' | 'maternity' | 'paternity' | 'unpaid';
  start_date: string;
  end_date: string;
  days_requested: string;
  reason?: string;
  status: 'pending' | 'approved' | 'rejected' | 'cancelled';
  approved_by?: string;
  approved_at?: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/human-resources';

export const ENDPOINTS = {
  DEPARTMENTS: {
    LIST: `${MODULE_API_PREFIX}/departments/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/departments/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/departments/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/departments/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/departments/${id}/` as const,
  },
  EMPLOYEES: {
    LIST: `${MODULE_API_PREFIX}/employees/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/employees/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/employees/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/employees/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/employees/${id}/` as const,
  },
  ATTENDANCES: {
    LIST: `${MODULE_API_PREFIX}/attendances/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/attendances/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/attendances/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/attendances/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/attendances/${id}/` as const,
  },
  LEAVE_REQUESTS: {
    LIST: `${MODULE_API_PREFIX}/leave-requests/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/leave-requests/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/leave-requests/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/leave-requests/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/leave-requests/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
