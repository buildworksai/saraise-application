import type { ComponentType, LazyExoticComponent } from "react";

/** Runtime modes in which a tenant route may be made available. */
export type TenantApplicationMode = "development" | "self-hosted" | "saas";

/** Icon contract shared with the tenant sidebar without coupling modules to it. */
export type TenantRouteIcon = ComponentType<{ className?: string }>;

/** A route that is directly discoverable in tenant navigation. */
export interface TenantSidebarNavigation {
  type: "sidebar";
  label: string;
  icon: TenantRouteIcon;
  order: number;
}

/** A detail, create, or edit route reached from a registered parent route. */
export interface TenantContextualNavigation {
  type: "contextual";
  parentRouteId: string;
}

export type TenantRouteNavigation = TenantSidebarNavigation | TenantContextualNavigation;

/**
 * Module-owned tenant route descriptor.
 *
 * `sourceFile` is explicit so validation failures and future diagnostics identify
 * the owning extension without relying on bundler-specific module metadata.
 */
export interface TenantRoute {
  id: string;
  module: string;
  path: string;
  sourceFile: string;
  Page: LazyExoticComponent<ComponentType>;
  modes?: readonly TenantApplicationMode[];
  navigation: TenantRouteNavigation;
}

/** Export shape discovered from each module's `routes.ts` file. */
export interface TenantRouteModule {
  default?: readonly TenantRoute[];
  tenantRoutes?: readonly TenantRoute[];
}
