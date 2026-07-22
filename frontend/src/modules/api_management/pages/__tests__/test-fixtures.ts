import type { ApiManagementConfiguration, ApiManagementResource, PaginatedResponse } from '../../contracts';

export const configuration = {
  version: 1,
  updated_at: '2026-07-23T10:00:00Z',
  document: {
    environment: 'development',
    resource_name_min_length: 1,
    resource_name_max_length: 255,
    resource_description_default: '',
    resource_config_default: {},
    resource_initially_active: true,
    writable_fields: ['name', 'description', 'config'],
    filter_fields: ['is_active'],
    search_fields: ['name', 'description'],
    ordering_fields: ['name', 'created_at', 'updated_at'],
    default_ordering: '-created_at',
    page_size: 25,
    max_page_size: 100,
    deletion_confirmation_message: 'Archive this API management resource?',
    activation_enabled: true,
    deactivation_enabled: true,
    health_cache_ttl_seconds: 10,
    table_skeleton_rows: 5,
    form_description_rows: 4,
    feature_enabled: true,
    rollout_percentage: 100,
    rollout_roles: [],
    rollout_cohorts: [],
    allowed_resource_config_keys: [],
  },
} satisfies ApiManagementConfiguration;

export function resource(overrides: Partial<ApiManagementResource> = {}): ApiManagementResource {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    name: 'Resource',
    description: 'Description',
    is_active: true,
    config: {},
    version: 1,
    created_at: '2026-07-23T10:00:00Z',
    updated_at: '2026-07-23T10:00:00Z',
    ...overrides,
  };
}

export function page(items: readonly ApiManagementResource[]): PaginatedResponse<ApiManagementResource> {
  return { count: items.length, next: null, previous: null, results: items };
}
