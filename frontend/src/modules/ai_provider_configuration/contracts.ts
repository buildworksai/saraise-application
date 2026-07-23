/** Public frontend contract for the tenant AI provider configuration API. */

export type UUID = string;
export type ISODateTime = string;
export type DecimalString = string;

export type ProviderType =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'groq'
  | 'mistral'
  | 'huggingface'
  | 'azure'
  | 'custom'
  | (string & {});

export type DeploymentStatus = 'active' | 'inactive' | 'error';
export type CredentialStatus = 'unverified' | 'valid' | 'invalid';

export interface AIProvider {
  id: UUID;
  name: string;
  provider_type: ProviderType;
  is_active: boolean;
  models_count: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

/** Credential responses contain metadata only. Secret material is write-only. */
export interface AIProviderCredential {
  id: UUID;
  tenant_id: UUID;
  provider: UUID;
  provider_name: string;
  provider_type: ProviderType;
  label: string;
  status: CredentialStatus;
  secret_hint: string;
  has_secret: boolean;
  last_verified_at: ISODateTime | null;
  last_error_code: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface AIProviderCredentialCreate {
  provider: UUID;
  label: string;
  api_key: string;
}

export interface AIProviderCredentialUpdate {
  label?: string;
  api_key?: string;
}

export interface AIModelPricing {
  input_cost_per_token?: number | DecimalString;
  output_cost_per_token?: number | DecimalString;
  input_cost_per_million_tokens?: number | DecimalString;
  output_cost_per_million_tokens?: number | DecimalString;
  currency?: string;
  [key: string]: unknown;
}

export interface AIModel {
  id: UUID;
  provider: UUID;
  provider_name: string;
  provider_type: ProviderType;
  model_id: string;
  display_name: string;
  capabilities: string[];
  pricing: AIModelPricing;
  max_tokens: number | null;
  is_active: boolean;
  deployments_count: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface AIModelDeploymentConfig {
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  timeout_seconds?: number;
  [key: string]: unknown;
}

export interface AIModelDeployment {
  id: UUID;
  tenant_id: UUID;
  model: UUID;
  credential: UUID | null;
  deployment_name: string;
  model_name: string;
  model_id: string;
  provider_name: string;
  config: AIModelDeploymentConfig;
  status: DeploymentStatus;
  created_by: UUID;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface AIModelDeploymentCreate {
  model: UUID;
  credential?: UUID | null;
  deployment_name: string;
  config: AIModelDeploymentConfig;
}

export type AIModelDeploymentUpdate = Partial<Pick<AIModelDeployment, 'credential' | 'deployment_name' | 'config'>>;

export interface AIUsageLog {
  id: UUID;
  tenant_id: UUID;
  deployment: UUID;
  deployment_name: string;
  model_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost: DecimalString;
  currency: string;
  provider_request_id: string;
  created_at: ISODateTime;
}

export interface ModuleHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  module?: string;
  message?: string;
  timestamp?: ISODateTime;
}

export interface RotateKeyResponse {
  new_key: string;
  message: string;
}

export interface ReEncryptRequest {
  old_key: string;
  new_key: string;
}

export interface ReEncryptResponse {
  success: boolean;
  re_encrypted_count: number;
  message: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type ListResponse<T> = T[] | PaginatedResponse<T>;

export interface ListFilters {
  search?: string;
  provider_id?: UUID;
  model_id?: UUID;
  deployment_id?: UUID;
  status?: DeploymentStatus;
}

export interface AIProviderConfigurationResource {
  id: UUID;
  tenant_id: UUID;
  name: string;
  description: string;
  is_active: boolean;
  config: Record<string, unknown>;
  created_by: UUID;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export type RuntimeConfigurationValues = Record<string, unknown>;

export interface AIProviderRuntimeConfiguration {
  id: UUID;
  tenant_id: UUID;
  environment: string;
  values: RuntimeConfigurationValues;
  version: number;
  updated_by: UUID;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface AIProviderRuntimeConfigurationVersion {
  id: UUID;
  tenant_id: UUID;
  configuration: UUID;
  version: number;
  environment: string;
  values: RuntimeConfigurationValues;
  created_by: UUID;
  correlation_id: UUID;
  rollback_of: number | null;
  created_at: ISODateTime;
}

export interface AIProviderRuntimeConfigurationAudit {
  id: UUID;
  tenant_id: UUID;
  configuration: UUID;
  action: string;
  actor_id: UUID;
  correlation_id: UUID;
  from_version: number | null;
  to_version: number;
  before: RuntimeConfigurationValues;
  after: RuntimeConfigurationValues;
  rollback_of: number | null;
  created_at: ISODateTime;
}

export interface RuntimeConfigurationPreview {
  environment: string;
  current_version: number;
  would_create_version: number;
  changes: Record<string, { before: unknown; after: unknown }>;
}

export interface RuntimeConfigurationDocument {
  module: 'ai_provider_configuration';
  environment: string;
  version: number;
  values: RuntimeConfigurationValues;
}

export const MODULE_API_PREFIX = '/api/v1/ai-provider-configuration';

export const ENDPOINTS = {
  PROVIDERS: {
    LIST: `${MODULE_API_PREFIX}/providers/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/providers/${id}/` as const,
  },
  RESOURCES: {
    LIST: `${MODULE_API_PREFIX}/resources/`,
    CREATE: `${MODULE_API_PREFIX}/resources/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/resources/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/resources/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/resources/${id}/` as const,
    RESTORE: (id: UUID) => `${MODULE_API_PREFIX}/resources/${id}/restore/` as const,
  },
  CREDENTIALS: {
    LIST: `${MODULE_API_PREFIX}/credentials/`,
    CREATE: `${MODULE_API_PREFIX}/credentials/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/credentials/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/credentials/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/credentials/${id}/` as const,
  },
  MODELS: {
    LIST: `${MODULE_API_PREFIX}/models/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/models/${id}/` as const,
  },
  DEPLOYMENTS: {
    LIST: `${MODULE_API_PREFIX}/deployments/`,
    CREATE: `${MODULE_API_PREFIX}/deployments/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/deployments/${id}/` as const,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/deployments/${id}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/deployments/${id}/` as const,
    ACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/deployments/${id}/activate/` as const,
    DEACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/deployments/${id}/deactivate/` as const,
  },
  USAGE_LOGS: {
    LIST: `${MODULE_API_PREFIX}/usage-logs/`,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/usage-logs/${id}/` as const,
  },
  SECRETS: {
    ROTATE_KEY: `${MODULE_API_PREFIX}/secrets/rotate-key/`,
    RE_ENCRYPT: `${MODULE_API_PREFIX}/secrets/re-encrypt/`,
  },
  RUNTIME_CONFIGURATION: {
    CURRENT: `${MODULE_API_PREFIX}/runtime-configuration/current/`,
    PREVIEW: `${MODULE_API_PREFIX}/runtime-configuration/preview/`,
    VERSIONS: `${MODULE_API_PREFIX}/runtime-configuration/versions/`,
    AUDIT: `${MODULE_API_PREFIX}/runtime-configuration/audit/`,
    ROLLBACK: `${MODULE_API_PREFIX}/runtime-configuration/rollback/`,
    EXPORT: `${MODULE_API_PREFIX}/runtime-configuration/export/`,
    IMPORT: `${MODULE_API_PREFIX}/runtime-configuration/import/`,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

/** Application paths live beside the API contract to keep navigation consistent. */
export const AI_PROVIDER_ROUTES = {
  HOME: '/ai-provider-configuration',
  CONNECT: '/ai-provider-configuration/create',
  CONFIGURATION: '/ai-provider-configuration/runtime-configuration',
  PROVIDER: (id: UUID) => `/ai-provider-configuration/${id}` as const,
  SECRETS: '/ai-providers/secrets',
} as const;
