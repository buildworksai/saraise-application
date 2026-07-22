/**
 * API Management module contracts.
 *
 * This is the only source for module API endpoints, UI routes, and wire types.
 */

export type UUID = string;
export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | readonly JsonValue[];
export interface JsonObject { readonly [key: string]: JsonValue }

export interface ApiManagementResource {
  readonly id: UUID;
  readonly name: string;
  readonly description: string;
  readonly is_active: boolean;
  readonly config: JsonObject;
  readonly version: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ApiManagementResourceCreate {
  readonly name: string;
  readonly description?: string;
  readonly config?: JsonObject;
  readonly idempotency_key: UUID;
}

export interface ApiManagementResourceUpdate {
  readonly name?: string;
  readonly description?: string;
  readonly config?: JsonObject;
  readonly idempotency_key: UUID;
}

export interface ResourceListFilters {
  readonly search?: string;
  readonly is_active?: boolean;
  readonly ordering?: string;
  readonly page?: number;
  readonly page_size?: number;
}

export interface PaginatedResponse<T> {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly T[];
}

export type DeploymentEnvironment = 'development' | 'staging' | 'production';
export type ResourceWritableField = 'name' | 'description' | 'config';
export type ResourceFilterField = 'is_active';
export type ResourceSearchField = 'name' | 'description';
export type ResourceOrderingField = 'name' | 'created_at' | 'updated_at';

export interface ApiManagementConfigurationDocument {
  readonly environment: DeploymentEnvironment;
  readonly resource_name_min_length: number;
  readonly resource_name_max_length: number;
  readonly resource_description_default: string;
  readonly resource_config_default: JsonObject;
  readonly resource_initially_active: boolean;
  readonly writable_fields: readonly ResourceWritableField[];
  readonly filter_fields: readonly ResourceFilterField[];
  readonly search_fields: readonly ResourceSearchField[];
  readonly ordering_fields: readonly ResourceOrderingField[];
  readonly default_ordering: string;
  readonly page_size: number;
  readonly max_page_size: number;
  readonly deletion_confirmation_message: string;
  readonly activation_enabled: boolean;
  readonly deactivation_enabled: boolean;
  readonly health_cache_ttl_seconds: number;
  readonly table_skeleton_rows: number;
  readonly form_description_rows: number;
  readonly feature_enabled: boolean;
  readonly rollout_percentage: number;
  readonly rollout_roles: readonly string[];
  readonly rollout_cohorts: readonly string[];
  readonly allowed_resource_config_keys?: readonly string[];
}

export interface ApiManagementConfiguration {
  readonly version: number;
  readonly document: ApiManagementConfigurationDocument;
  readonly updated_at: string;
}

export interface PortableApiManagementConfiguration {
  readonly module: 'api_management';
  readonly schema_version: 1;
  readonly version: number;
  readonly document: ApiManagementConfigurationDocument;
}

export interface ConfigurationVersion {
  readonly version: number;
  readonly document: ApiManagementConfigurationDocument;
  readonly actor_id: string;
  readonly correlation_id: string;
  readonly created_at: string;
}

export interface ConfigurationChange {
  readonly field: string;
  readonly before: JsonValue | undefined;
  readonly after: JsonValue | undefined;
}

export interface ConfigurationPreview {
  readonly valid: boolean;
  readonly normalized_document: ApiManagementConfigurationDocument;
  readonly changes: readonly ConfigurationChange[];
  readonly errors?: Readonly<Record<string, readonly string[]>>;
}

export interface ConfigurationWriteRequest {
  readonly document: ApiManagementConfigurationDocument;
  readonly idempotency_key: UUID;
}

export interface ConfigurationPreviewRequest { readonly document: unknown }
export interface ConfigurationRollbackRequest { readonly version: number; readonly idempotency_key: UUID }

export const MODULE_API_PREFIX = '/api/v1/api-management';

function resourceListEndpoint(filters: ResourceListFilters = {}): string {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.is_active !== undefined) params.set('is_active', String(filters.is_active));
  if (filters.ordering) params.set('ordering', filters.ordering);
  if (filters.page !== undefined) params.set('page', String(filters.page));
  if (filters.page_size !== undefined) params.set('page_size', String(filters.page_size));
  const query = params.toString();
  return `${MODULE_API_PREFIX}/resources/${query ? `?${query}` : ''}`;
}

export const ENDPOINTS = {
  RESOURCES: {
    LIST: resourceListEndpoint,
    DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/resources/${encodeURIComponent(id)}/` as const,
    CREATE: `${MODULE_API_PREFIX}/resources/`,
    UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/resources/${encodeURIComponent(id)}/` as const,
    DELETE: (id: UUID) => `${MODULE_API_PREFIX}/resources/${encodeURIComponent(id)}/` as const,
    RESTORE: (id: UUID) => `${MODULE_API_PREFIX}/resources/${encodeURIComponent(id)}/restore/` as const,
    ACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/resources/${encodeURIComponent(id)}/activate/` as const,
    DEACTIVATE: (id: UUID) => `${MODULE_API_PREFIX}/resources/${encodeURIComponent(id)}/deactivate/` as const,
  },
  CONFIGURATION: {
    CURRENT: `${MODULE_API_PREFIX}/configuration/`,
    PREVIEW: `${MODULE_API_PREFIX}/configuration/preview/`,
    HISTORY: `${MODULE_API_PREFIX}/configuration/history/`,
    ROLLBACK: `${MODULE_API_PREFIX}/configuration/rollback/`,
    IMPORT: `${MODULE_API_PREFIX}/configuration/import/`,
    EXPORT: `${MODULE_API_PREFIX}/configuration/export/`,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTES = {
  RESOURCES: '/api-management',
  RESOURCE_CREATE: '/api-management/create',
  RESOURCE_DETAIL_PATTERN: '/api-management/:id',
  RESOURCE_DETAIL: (id: UUID) => `/api-management/${encodeURIComponent(id)}` as const,
  CONFIGURATION: '/api-management/configuration',
} as const;

export const QUERY_KEYS = {
  ROOT: ['api-management'] as const,
  RESOURCES: (filters: ResourceListFilters = {}) => ['api-management', 'resources', filters] as const,
  RESOURCE: (id: UUID) => ['api-management', 'resources', id] as const,
  CONFIGURATION: ['api-management', 'configuration'] as const,
  CONFIGURATION_HISTORY: ['api-management', 'configuration', 'history'] as const,
} as const;
