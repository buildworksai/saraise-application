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

export interface ApiManagementResourceVersion {
  readonly version: number;
  readonly snapshot: JsonObject;
  readonly actor_id: string;
  readonly correlation_id: string;
  readonly reason: string;
  readonly source_version: number | null;
  readonly created_at: string;
}

export interface ResourceRollbackRequest {
  readonly version: number;
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

/** Environments are governed by the server registry, never a frontend allow-list. */
export type DeploymentEnvironment = string;
export type ResourceWritableField = 'name' | 'description' | 'config';
export type ResourceFilterField = 'is_active';
export type ResourceSearchField = 'name' | 'description';
export type ResourceOrderingField = 'name' | 'created_at' | 'updated_at';

export interface ApiManagementNavigationConfiguration {
  readonly resources_list: { readonly order: number };
  readonly resources_create: { readonly order: number };
  readonly resources_detail: { readonly order: number };
  readonly configuration: { readonly order: number };
}

export interface ApiManagementValidationLimits {
  readonly list_max_items: number;
  readonly list_item_max_length: number;
  readonly resource_name_minimum_floor: number;
  readonly resource_name_minimum_ceiling: number;
  readonly resource_name_maximum_floor: number;
  readonly resource_name_maximum_ceiling: number;
  readonly resource_description_max_length: number;
  readonly page_size_minimum: number;
  readonly page_size_maximum: number;
  readonly deletion_confirmation_max_length: number;
  readonly health_cache_ttl_minimum: number;
  readonly health_cache_ttl_maximum: number;
  readonly table_skeleton_rows_minimum: number;
  readonly table_skeleton_rows_maximum: number;
  readonly form_description_rows_minimum: number;
  readonly form_description_rows_maximum: number;
  readonly rollout_percentage_minimum: number;
  readonly rollout_percentage_maximum: number;
  readonly configuration_history_page_size: number;
  readonly configuration_history_max_page_size: number;
  readonly configuration_history_max_page: number;
  readonly configuration_version_reason_max_length: number;
  readonly resource_version_reason_max_length: number;
  readonly audit_target_type_max_length: number;
  readonly audit_action_max_length: number;
}

export interface ApiManagementConfigurationDocument {
  readonly environment: DeploymentEnvironment;
  readonly environment_registry: readonly DeploymentEnvironment[];
  readonly navigation: ApiManagementNavigationConfiguration;
  readonly validation_limits: ApiManagementValidationLimits;
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
  readonly rollout_strategy: string;
  readonly rollout_bucket_count: number;
  readonly quota_cost: number;
  readonly configuration_version_reasons: readonly string[];
  readonly resource_version_reasons: readonly string[];
  readonly audit_target_types: readonly string[];
  readonly audit_actions: readonly string[];
  readonly allowed_resource_config_keys: readonly string[];
}

export interface ApiManagementConfiguration {
  readonly environment: DeploymentEnvironment;
  readonly version: number;
  readonly document: ApiManagementConfigurationDocument;
  readonly updated_at: string;
}

export interface PortableApiManagementConfiguration {
  readonly module: 'api_management';
  readonly schema_version: 2;
  readonly version: number;
  readonly environment: DeploymentEnvironment;
  readonly document: ApiManagementConfigurationDocument;
}

export interface ConfigurationVersion {
  readonly environment: DeploymentEnvironment;
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

export interface ConfigurationImportRequest {
  readonly document: PortableApiManagementConfiguration;
  readonly idempotency_key: UUID;
}

export type ConfigurationFieldType =
  | 'boolean'
  | 'integer'
  | 'number'
  | 'string'
  | 'select'
  | 'multi_select'
  | 'string_list'
  | 'json_object';

export interface ConfigurationFieldSchema {
  readonly type: ConfigurationFieldType;
  readonly label: string;
  readonly help_text: string;
  readonly unit?: string;
  readonly min_value?: number;
  readonly max_value?: number;
  readonly max_length?: number;
  readonly max_items?: number;
  readonly item_max_length?: number;
  readonly options?: readonly string[];
}

export type ConfigurationDependencyOperator =
  | 'equals'
  | 'not_equals'
  | 'less_than'
  | 'less_than_or_equal'
  | 'greater_than'
  | 'greater_than_or_equal'
  | 'in';

export interface ConfigurationDependencyEffect {
  readonly kind: 'set' | 'clear' | 'disable';
  readonly value?: JsonValue;
}

export interface ConfigurationDependency {
  readonly source_field: keyof ApiManagementConfigurationDocument;
  readonly operator: ConfigurationDependencyOperator;
  readonly value: JsonValue;
  readonly target_fields: readonly (keyof ApiManagementConfigurationDocument)[];
  readonly effect: ConfigurationDependencyEffect;
}

export interface ApiManagementConfigurationSchema {
  readonly schema_version: number;
  /** Environment used to derive this schema and its runtime navigation metadata. */
  readonly environment: DeploymentEnvironment;
  readonly environments: readonly DeploymentEnvironment[];
  readonly fields: Readonly<Record<string, ConfigurationFieldSchema>>;
  readonly dependencies: readonly ConfigurationDependency[];
  readonly navigation: ApiManagementNavigationConfiguration;
  readonly platform_hard_ceilings: Readonly<Record<string, number>>;
}

export interface ConfigurationHistoryFilters {
  readonly page?: number;
  readonly page_size?: number;
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

function environmentEndpoint(endpoint: string, environment: DeploymentEnvironment): string {
  const separator = endpoint.includes('?') ? '&' : '?';
  return `${endpoint}${separator}environment=${encodeURIComponent(environment)}`;
}

function optionalEnvironmentEndpoint(endpoint: string, environment?: DeploymentEnvironment): string {
  return environment ? environmentEndpoint(endpoint, environment) : endpoint;
}

function configurationHistoryEndpoint(environment: DeploymentEnvironment, filters: ConfigurationHistoryFilters = {}): string {
  const params = new URLSearchParams({ environment });
  if (filters.page !== undefined) params.set('page', String(filters.page));
  if (filters.page_size !== undefined) params.set('page_size', String(filters.page_size));
  return `${MODULE_API_PREFIX}/configuration/history/?${params.toString()}`;
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
    VERSIONS: (id: UUID) => `${MODULE_API_PREFIX}/resources/${encodeURIComponent(id)}/versions/` as const,
    ROLLBACK: (id: UUID) => `${MODULE_API_PREFIX}/resources/${encodeURIComponent(id)}/rollback/` as const,
  },
  CONFIGURATION: {
    SCHEMA: (environment?: DeploymentEnvironment) =>
      optionalEnvironmentEndpoint(`${MODULE_API_PREFIX}/configuration/schema/`, environment),
    CURRENT: (environment: DeploymentEnvironment) => environmentEndpoint(`${MODULE_API_PREFIX}/configuration/`, environment),
    PREVIEW: (environment: DeploymentEnvironment) => environmentEndpoint(`${MODULE_API_PREFIX}/configuration/preview/`, environment),
    HISTORY: configurationHistoryEndpoint,
    ROLLBACK: (environment: DeploymentEnvironment) => environmentEndpoint(`${MODULE_API_PREFIX}/configuration/rollback/`, environment),
    IMPORT: (environment: DeploymentEnvironment) => environmentEndpoint(`${MODULE_API_PREFIX}/configuration/import/`, environment),
    EXPORT: (environment: DeploymentEnvironment) => environmentEndpoint(`${MODULE_API_PREFIX}/configuration/export/`, environment),
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
  RESOURCE_VERSIONS: (id: UUID) => ['api-management', 'resources', id, 'versions'] as const,
  CONFIGURATION_SCHEMA: (environment?: DeploymentEnvironment) => ['api-management', 'configuration', 'schema', environment ?? 'runtime'] as const,
  RUNTIME_CONFIGURATION: ['api-management', 'configuration', 'runtime'] as const,
  CONFIGURATION: (environment: DeploymentEnvironment) => ['api-management', 'configuration', environment] as const,
  CONFIGURATION_HISTORY: (environment: DeploymentEnvironment, filters: ConfigurationHistoryFilters = {}) => ['api-management', 'configuration', environment, 'history', filters] as const,
} as const;
