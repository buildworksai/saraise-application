/**
 * Regional module contracts.
 *
 * This file is the single frontend source of truth for Regional routes, API
 * endpoints, request payloads, and response representations.
 */

export type RegionalResourceConfiguration = {
  country_code?: string;
  jurisdiction_type?: string;
  compliance_tags?: string[];
};

export type RegionalResource = {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  config: RegionalResourceConfiguration;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
};

export type RegionalResourceCreate = {
  name: string;
  description?: string;
  config?: RegionalResourceConfiguration;
};

export type RegionalResourceUpdate = Partial<RegionalResourceCreate>;

export type PaginatedRegionalResources = {
  count: number;
  next: string | null;
  previous: string | null;
  results: RegionalResource[];
};

export type RegionalResourceRules = {
  name_min_length: number;
  name_max_length: number;
  name_default: string;
  description_default: string;
  description_max_length: number;
  default_active: boolean;
  default_config: RegionalResourceConfiguration;
  allowed_config_keys: string[];
  allowed_jurisdiction_types: string[];
  max_compliance_tags: number;
  max_config_bytes: number;
  search_fields: Array<'name' | 'description'>;
};

export type RegionalWorkflowRules = {
  activation_state: boolean;
  deactivation_state: boolean;
  require_delete_confirmation: boolean;
};

export type RegionalApiRules = {
  default_page_size: number;
  max_page_size: number;
  allowed_filters: Array<'is_active' | 'name'>;
  allowed_ordering: Array<
    'name' | '-name' | 'created_at' | '-created_at' | 'updated_at' | '-updated_at'
  >;
};

export type RegionalHealthRules = {
  cache_probe_ttl_seconds: number;
};

export type RegionalRolloutRules = {
  enabled: boolean;
  roles: string[];
  cohorts: string[];
};

export type RegionalConfigurationDocument = {
  resource: RegionalResourceRules;
  workflow: RegionalWorkflowRules;
  api: RegionalApiRules;
  health: RegionalHealthRules;
  rollout: RegionalRolloutRules;
};

export type RegionalConfigurationEnvironment = 'development' | 'self-hosted' | 'saas';

export type RegionalConfiguration = {
  environment: RegionalConfigurationEnvironment;
  version: number;
  document: RegionalConfigurationDocument;
  updated_at: string;
};

export type RegionalConfigurationWrite = {
  environment?: RegionalConfigurationEnvironment;
  document: RegionalConfigurationDocument;
};

export type RegionalConfigurationPreview = {
  valid: boolean;
  document: RegionalConfigurationDocument;
  changes: Array<{
    path: string;
    before: unknown;
    after: unknown;
  }>;
};

export type RegionalConfigurationHistoryItem = {
  id: string;
  environment: RegionalConfigurationEnvironment;
  version: number;
  document: RegionalConfigurationDocument;
  operation: string;
  actor_id: string;
  correlation_id: string;
  previous_version: number | null;
  created_at: string;
};

export type RegionalConfigurationExport = {
  schema_version: '1.0';
  environment: RegionalConfigurationEnvironment;
  version: number;
  document: RegionalConfigurationDocument;
  exported_at: string;
};

export const ROUTES = {
  ROOT: '/regional',
  CREATE: '/regional/create',
  CONFIGURATION: '/regional/configuration',
  DETAIL_PATTERN: '/regional/:id',
  EDIT_PATTERN: '/regional/:id/edit',
  DETAIL: (id: string) => `/regional/${encodeURIComponent(id)}` as const,
  EDIT: (id: string) => `/regional/${encodeURIComponent(id)}/edit` as const,
} as const;

export const MODULE_API_PREFIX = '/api/v1/regional';

export const ENDPOINTS = {
  RESOURCES: {
    LIST: `${MODULE_API_PREFIX}/resources/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/resources/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/` as const,
    RESTORE: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/restore/` as const,
    ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/activate/` as const,
    DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/resources/${id}/deactivate/` as const,
  },
  CONFIGURATION: {
    ROOT: `${MODULE_API_PREFIX}/configuration/`,
    CURRENT: `${MODULE_API_PREFIX}/configuration/current/`,
    PREVIEW: `${MODULE_API_PREFIX}/configuration/preview/`,
    HISTORY: `${MODULE_API_PREFIX}/configuration/history/`,
    ROLLBACK: `${MODULE_API_PREFIX}/configuration/rollback/`,
    IMPORT: `${MODULE_API_PREFIX}/configuration/import_document/`,
    EXPORT: `${MODULE_API_PREFIX}/configuration/export_document/`,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const REGIONAL_QUERY_KEYS = {
  resources: ['regional', 'resources'] as const,
  resource: (id: string) => ['regional', 'resources', id] as const,
  configuration: (environment: string) =>
    ['regional', 'configuration', environment] as const,
  configurationHistory: (environment: string) =>
    ['regional', 'configuration', environment, 'history'] as const,
} as const;
