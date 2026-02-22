/**
 * Project Management Service
 *
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import type { Project, ProjectCreate } from '../contracts';
import { ENDPOINTS } from '../contracts';

export const projectService = {
  listProjects: async (): Promise<Project[]> => {
    const response = await apiClient.get<Project[] | { results: Project[] }>(
      ENDPOINTS.PROJECTS.LIST
    );
    return Array.isArray(response) ? response : response.results ?? [];
  },

  getProject: async (id: string): Promise<Project> => {
    return apiClient.get<Project>(ENDPOINTS.PROJECTS.DETAIL(id));
  },

  createProject: async (data: ProjectCreate): Promise<Project> => {
    return apiClient.post<Project>(ENDPOINTS.PROJECTS.CREATE, data);
  },

  updateProject: async (id: string, data: Partial<ProjectCreate>): Promise<Project> => {
    return apiClient.patch<Project>(ENDPOINTS.PROJECTS.UPDATE(id), data);
  },

  deleteProject: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.PROJECTS.DELETE(id));
  },
};
