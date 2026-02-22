/**
 * Human Resources Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Employee, EmployeeCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const hrService = {
  listEmployees: async (): Promise<Employee[]> => {
    const response = await apiClient.get<Employee[] | { results: Employee[] }>(
      ENDPOINTS.EMPLOYEES.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getEmployee: async (id: string): Promise<Employee> => {
    return apiClient.get<Employee>(ENDPOINTS.EMPLOYEES.DETAIL(id));
  },

  createEmployee: async (data: EmployeeCreate): Promise<Employee> => {
    return apiClient.post<Employee>(ENDPOINTS.EMPLOYEES.CREATE, data);
  },

  updateEmployee: async (id: string, data: Partial<EmployeeCreate>): Promise<Employee> => {
    return apiClient.patch<Employee>(ENDPOINTS.EMPLOYEES.UPDATE(id), data);
  },

  deleteEmployee: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.EMPLOYEES.DELETE(id));
  },
};
