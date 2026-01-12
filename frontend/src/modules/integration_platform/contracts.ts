/**
 * IntegrationPlatform Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for IntegrationPlatform are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Integration entity */
export type Integration = {
  id: string;
  tenant_id: string;
  name: string;
  integration_type: 'api' | 'webhook' | 'database' | 'file' | 'message_queue';
  config: Record<string, unknown>;
  status: 'active' | 'inactive' | 'error' | 'testing';
  credentials_count?: number;
  mappings_count?: number;
  created_by: string;
  created_at: string;
  updated_at: string;
};

/** Integration create request */
export type IntegrationCreate = {
  name: string;
  integration_type: 'api' | 'webhook' | 'database' | 'file' | 'message_queue';
  config: Record<string, unknown>;
};

/** Integration update request (partial) */
export type IntegrationUpdate = Partial<IntegrationCreate>;

/** IntegrationCredential entity */
export type IntegrationCredential = {
  id: string;
  integration: string;
  integration_id?: string;
  credential_type: 'api_key' | 'oauth_token' | 'username_password' | 'certificate';
  encrypted_value: string;
  created_at: string;
  updated_at: string;
};

/** IntegrationCredential create request */
export type IntegrationCredentialCreate = {
  integration: string;
  credential_type: 'api_key' | 'oauth_token' | 'username_password' | 'certificate';
  encrypted_value: string;
};

/** IntegrationCredential update request (partial) */
export type IntegrationCredentialUpdate = Partial<IntegrationCredentialCreate>;

/** Webhook entity */
export type Webhook = {
  id: string;
  tenant_id: string;
  name: string;
  url: string;
  events: string[];
  secret: string;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
};

/** Webhook create request */
export type WebhookCreate = {
  name: string;
  url: string;
  events: string[];
  secret: string;
  is_active?: boolean;
};

/** Webhook update request (partial) */
export type WebhookUpdate = Partial<WebhookCreate>;

/** WebhookDelivery entity */
export type WebhookDelivery = {
  id: string;
  webhook: string;
  webhook_id?: string;
  event: string;
  payload: Record<string, unknown>;
  status: 'pending' | 'sent' | 'failed';
  response_status?: number;
  response_body?: string;
  attempted_at?: string;
  created_at: string;
};

/** Connector entity */
export type Connector = {
  id: string;
  name: string;
  connector_type: 'api' | 'database' | 'file' | 'message_queue';
  schema: Record<string, unknown>;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** DataMapping entity */
export type DataMapping = {
  id: string;
  tenant_id: string;
  integration: string;
  integration_id?: string;
  source_field: string;
  target_field: string;
  transform: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

/** DataMapping create request */
export type DataMappingCreate = {
  integration: string;
  source_field: string;
  target_field: string;
  transform?: Record<string, unknown>;
};

/** DataMapping update request (partial) */
export type DataMappingUpdate = Partial<DataMappingCreate>;

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * IntegrationPlatform API Endpoints
 *
 * All endpoints should be prefixed with /api/v1/integration-platform/
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS } from './contracts';
 * apiClient.get(ENDPOINTS.INTEGRATIONS.LIST);
 * apiClient.get(ENDPOINTS.INTEGRATIONS.DETAIL(id));
 * ```
 */
export const MODULE_API_PREFIX = '/api/v1/integration-platform';

export const ENDPOINTS = {
  INTEGRATIONS: {
    LIST: `${MODULE_API_PREFIX}/integrations/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/integrations/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/` as const,
    TEST: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/test/` as const,
    SYNC: (id: string) => `${MODULE_API_PREFIX}/integrations/${id}/sync/` as const,
  },
  INTEGRATION_CREDENTIALS: {
    LIST: `${MODULE_API_PREFIX}/integration-credentials/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/integration-credentials/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/integration-credentials/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/integration-credentials/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/integration-credentials/${id}/` as const,
  },
  WEBHOOKS: {
    LIST: `${MODULE_API_PREFIX}/webhooks/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/webhooks/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/webhooks/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/webhooks/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/webhooks/${id}/` as const,
    RECEIVE: (webhook_id: string) => `${MODULE_API_PREFIX}/webhooks/receive/${webhook_id}/` as const,
  },
  WEBHOOK_DELIVERIES: {
    LIST: `${MODULE_API_PREFIX}/webhook-deliveries/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/webhook-deliveries/${id}/` as const,
  },
  CONNECTORS: {
    LIST: `${MODULE_API_PREFIX}/connectors/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/connectors/${id}/` as const,
    SCHEMA: (id: string) => `${MODULE_API_PREFIX}/connectors/${id}/schema/` as const,
  },
  DATA_MAPPINGS: {
    LIST: `${MODULE_API_PREFIX}/data-mappings/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/data-mappings/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/data-mappings/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/data-mappings/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/data-mappings/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
