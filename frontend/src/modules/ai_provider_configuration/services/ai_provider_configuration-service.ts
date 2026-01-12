/**
 * AiProviderConfiguration Service
 * 
 * Service client for AiProviderConfiguration module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type AIProvider, type AIProviderCredential, type AIProviderCredentialCreate, type AIProviderCredentialUpdate, type AIModel, type AIModelDeployment, type AIModelDeploymentCreate, type AIModelDeploymentUpdate, type AIUsageLog } from '../contracts';

export const ai_provider_configurationService = {
  /**
   * List all AI providers (platform-level)
   */
  listProviders: async (): Promise<AIProvider[]> => {
    return apiClient.get<AIProvider[]>(ENDPOINTS.PROVIDERS.LIST);
  },

  /**
   * Get provider by ID
   */
  getProvider: async (id: string): Promise<AIProvider> => {
    return apiClient.get<AIProvider>(ENDPOINTS.PROVIDERS.DETAIL(id));
  },

  /**
   * List all credentials
   */
  listCredentials: async (): Promise<AIProviderCredential[]> => {
    return apiClient.get<AIProviderCredential[]>(ENDPOINTS.CREDENTIALS.LIST);
  },

  /**
   * Get credential by ID
   */
  getCredential: async (id: string): Promise<AIProviderCredential> => {
    return apiClient.get<AIProviderCredential>(ENDPOINTS.CREDENTIALS.DETAIL(id));
  },

  /**
   * Create new credential
   */
  createCredential: async (data: AIProviderCredentialCreate): Promise<AIProviderCredential> => {
    return apiClient.post<AIProviderCredential>(ENDPOINTS.CREDENTIALS.CREATE, data);
  },

  /**
   * Update credential
   */
  updateCredential: async (id: string, data: AIProviderCredentialUpdate): Promise<AIProviderCredential> => {
    return apiClient.put<AIProviderCredential>(ENDPOINTS.CREDENTIALS.UPDATE(id), data);
  },

  /**
   * Delete credential
   */
  deleteCredential: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.CREDENTIALS.DELETE(id));
  },

  /**
   * List all models (platform-level)
   */
  listModels: async (): Promise<AIModel[]> => {
    return apiClient.get<AIModel[]>(ENDPOINTS.MODELS.LIST);
  },

  /**
   * Get model by ID
   */
  getModel: async (id: string): Promise<AIModel> => {
    return apiClient.get<AIModel>(ENDPOINTS.MODELS.DETAIL(id));
  },

  /**
   * List all deployments
   */
  listDeployments: async (): Promise<AIModelDeployment[]> => {
    return apiClient.get<AIModelDeployment[]>(ENDPOINTS.DEPLOYMENTS.LIST);
  },

  /**
   * Get deployment by ID
   */
  getDeployment: async (id: string): Promise<AIModelDeployment> => {
    return apiClient.get<AIModelDeployment>(ENDPOINTS.DEPLOYMENTS.DETAIL(id));
  },

  /**
   * Create new deployment
   */
  createDeployment: async (data: AIModelDeploymentCreate): Promise<AIModelDeployment> => {
    return apiClient.post<AIModelDeployment>(ENDPOINTS.DEPLOYMENTS.CREATE, data);
  },

  /**
   * Update deployment
   */
  updateDeployment: async (id: string, data: AIModelDeploymentUpdate): Promise<AIModelDeployment> => {
    return apiClient.put<AIModelDeployment>(ENDPOINTS.DEPLOYMENTS.UPDATE(id), data);
  },

  /**
   * Delete deployment
   */
  deleteDeployment: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.DEPLOYMENTS.DELETE(id));
  },

  /**
   * List all usage logs
   */
  listUsageLogs: async (): Promise<AIUsageLog[]> => {
    return apiClient.get<AIUsageLog[]>(ENDPOINTS.USAGE_LOGS.LIST);
  },

  /**
   * Get usage log by ID
   */
  getUsageLog: async (id: string): Promise<AIUsageLog> => {
    return apiClient.get<AIUsageLog>(ENDPOINTS.USAGE_LOGS.DETAIL(id));
  },

  // Legacy methods for backward compatibility (deprecated - use specific methods above)
  /**
   * @deprecated Use listCredentials() instead
   */
  listResources: async (): Promise<AIProviderCredential[]> => {
    return apiClient.get<AIProviderCredential[]>(ENDPOINTS.CREDENTIALS.LIST);
  },

  /**
   * @deprecated Use getCredential() instead
   */
  getResource: async (id: string): Promise<AIProviderCredential> => {
    return apiClient.get<AIProviderCredential>(ENDPOINTS.CREDENTIALS.DETAIL(id));
  },

  /**
   * @deprecated Use createCredential() instead
   */
  createResource: async (data: AIProviderCredentialCreate): Promise<AIProviderCredential> => {
    return apiClient.post<AIProviderCredential>(ENDPOINTS.CREDENTIALS.CREATE, data);
  },

  /**
   * @deprecated Use updateCredential() instead
   */
  updateResource: async (id: string, data: AIProviderCredentialUpdate): Promise<AIProviderCredential> => {
    return apiClient.put<AIProviderCredential>(ENDPOINTS.CREDENTIALS.UPDATE(id), data);
  },

  /**
   * @deprecated Use deleteCredential() instead
   */
  deleteResource: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.CREDENTIALS.DELETE(id));
  },
};
