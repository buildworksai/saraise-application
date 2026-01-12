/**
 * AiProviderConfiguration Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for AiProviderConfiguration are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

// Note: These types may not exist in the generated API schema yet.
// If they don't exist, we define fallback types based on the backend models.

/** AIProvider entity */
export type AIProvider = {
  id: string;
  name: string;
  provider_type: 'openai' | 'anthropic' | 'google' | 'azure' | 'custom';
  base_url?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** AIProviderCredential entity */
export type AIProviderCredential = {
  id: string;
  tenant_id: string;
  provider: string;
  provider_id?: string;
  created_at: string;
  updated_at: string;
};

/** AIProviderCredential create request */
export type AIProviderCredentialCreate = {
  provider: string;
  api_key: string;
};

/** AIProviderCredential update request (partial) */
export type AIProviderCredentialUpdate = Partial<AIProviderCredentialCreate>;

/** AIModel entity */
export type AIModel = {
  id: string;
  name: string;
  provider: string;
  provider_id?: string;
  model_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** AIModelDeployment entity */
export type AIModelDeployment = {
  id: string;
  tenant_id: string;
  model: string;
  model_id?: string;
  deployment_name: string;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** AIModelDeployment create request */
export type AIModelDeploymentCreate = {
  model: string;
  deployment_name: string;
  config?: Record<string, unknown>;
  is_active?: boolean;
};

/** AIModelDeployment update request (partial) */
export type AIModelDeploymentUpdate = Partial<AIModelDeploymentCreate>;

/** AIUsageLog entity */
export type AIUsageLog = {
  id: string;
  tenant_id: string;
  deployment: string;
  deployment_id?: string;
  model: string;
  model_id?: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * AiProviderConfiguration API Endpoints
 *
 * All endpoints should be prefixed with /api/v1/ai-provider-configuration/
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS } from './contracts';
 * apiClient.get(ENDPOINTS.PROVIDERS.LIST);
 * apiClient.get(ENDPOINTS.DEPLOYMENTS.DETAIL(id));
 * ```
 */
export const MODULE_API_PREFIX = '/api/v1/ai-provider-configuration';

export const ENDPOINTS = {
  PROVIDERS: {
    LIST: `${MODULE_API_PREFIX}/providers/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/providers/${id}/` as const,
  },
  CREDENTIALS: {
    LIST: `${MODULE_API_PREFIX}/credentials/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/credentials/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/credentials/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/credentials/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/credentials/${id}/` as const,
  },
  MODELS: {
    LIST: `${MODULE_API_PREFIX}/models/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/models/${id}/` as const,
  },
  DEPLOYMENTS: {
    LIST: `${MODULE_API_PREFIX}/deployments/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/deployments/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/deployments/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/deployments/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/deployments/${id}/` as const,
  },
  USAGE_LOGS: {
    LIST: `${MODULE_API_PREFIX}/usage-logs/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/usage-logs/${id}/` as const,
  },
  SECRETS: {
    LIST: `${MODULE_API_PREFIX}/credentials/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/credentials/${id}/` as const,
    ROTATE_KEY: `${MODULE_API_PREFIX}/secrets/rotate-key/`,
    RE_ENCRYPT: `${MODULE_API_PREFIX}/secrets/re-encrypt/`,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
