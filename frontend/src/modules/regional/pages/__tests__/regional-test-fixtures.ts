import type {
  PaginatedRegionalResources,
  RegionalConfiguration,
  RegionalResource,
} from '../../contracts';

export const configurationFixture = (): RegionalConfiguration => ({
  environment: 'development',
  version: 1,
  updated_at: '2026-07-23T10:00:00Z',
  document: {
    resource: {
      name_min_length: 1,
      name_max_length: 255,
      name_default: 'Regional resource',
      description_default: '',
      description_max_length: 2000,
      default_active: true,
      default_config: {},
      allowed_config_keys: ['country_code', 'jurisdiction_type', 'compliance_tags'],
      allowed_jurisdiction_types: ['country', 'state', 'province', 'economic_zone'],
      max_compliance_tags: 20,
      max_config_bytes: 4096,
      search_fields: ['name', 'description'],
    },
    workflow: {
      activation_state: true,
      deactivation_state: false,
      require_delete_confirmation: true,
    },
    api: {
      default_page_size: 25,
      max_page_size: 100,
      allowed_filters: ['is_active', 'name'],
      allowed_ordering: [
        'name',
        '-name',
        'created_at',
        '-created_at',
        'updated_at',
        '-updated_at',
      ],
    },
    health: { cache_probe_ttl_seconds: 10 },
    rollout: { enabled: true, roles: ['tenant_admin'], cohorts: ['all'] },
  },
});

export const resourceFixture = (
  overrides: Partial<RegionalResource> = {},
): RegionalResource => ({
  id: 'regional-resource-id',
  name: 'Regional resource',
  description: 'Governed regional resource',
  is_active: true,
  config: {
    country_code: 'IN',
    jurisdiction_type: 'country',
    compliance_tags: ['gst'],
  },
  created_at: '2026-07-23T10:00:00Z',
  updated_at: '2026-07-23T10:00:00Z',
  deleted_at: null,
  ...overrides,
});

export const resourcePageFixture = (
  resources: RegionalResource[],
): PaginatedRegionalResources => ({
  count: resources.length,
  next: null,
  previous: null,
  results: resources,
});
