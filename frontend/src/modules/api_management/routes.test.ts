import { describe, expect, it } from 'vitest';
import { ROUTES } from './contracts';
import { tenantRoutes } from './routes';

describe('API Management tenant routes', () => {
  it('registers every page as an explicit sidebar NavItem', () => {
    expect(tenantRoutes.map((route) => route.id)).toEqual([
      'api-management.resources.list',
      'api-management.resources.create',
      'api-management.resources.detail',
      'api-management.configuration',
    ]);
    expect(tenantRoutes.every((route) => route.navigation.type === 'sidebar')).toBe(true);
  });

  it('uses a parameter-safe navigation target for the resource detail page', () => {
    const detail = tenantRoutes.find((route) => route.id === 'api-management.resources.detail');
    expect(detail?.path).toBe(ROUTES.RESOURCE_DETAIL_PATTERN);
    expect(detail?.navigation.type).toBe('sidebar');
    if (detail?.navigation.type !== 'sidebar') return;
    expect(detail.navigation.path).toBe(ROUTES.RESOURCES);
    expect(detail.navigation.path).not.toContain(':');
  });

  it('does not embed tenant ordering values in route descriptors', () => {
    const navigation = tenantRoutes.flatMap((route) =>
      route.navigation.type === 'sidebar' ? [route.navigation] : [],
    );
    expect(navigation.every((item) => !('order' in item))).toBe(true);
    expect(navigation.map((item) => item.runtimeOrderKey)).toEqual([
      'resources_list',
      'resources_create',
      'resources_detail',
      'configuration',
    ]);
  });
});
