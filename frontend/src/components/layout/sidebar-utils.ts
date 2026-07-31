import type { ApiManagementConfigurationSchema } from "@/modules/api_management/contracts";
import type { TenantSidebarBranch } from "@/navigation/tenant-route-registry";
import { getTenantSidebarTreeForMode } from "@/navigation/tenant-route-registry";
import type { TenantApplicationMode } from "@/navigation/tenant-route-types";
import { legacyModules, type NavItem } from "./contracts";

export interface DocumentIntelligenceNavigationOrder {
  extractions: number;
  classifications: number;
  training: number;
  templates: number;
  health: number;
  configuration: number;
}

export interface CustomizationNavigationOrder {
  readonly fields_order: number;
  readonly field_values_order: number;
  readonly forms_order: number;
  readonly rules_order: number;
  readonly executions_order: number;
  readonly configuration_order: number;
}

export interface IntegrationNavigationOrder {
  readonly base_order: number;
  readonly route_order: Readonly<Record<string, number>>;
}

export interface RenderTenantItemsOptions {
  readonly isAdmin: boolean;
  readonly documentIntelligenceNavigationOrder?: DocumentIntelligenceNavigationOrder;
  readonly apiManagementSchema?: ApiManagementConfigurationSchema;
  readonly customizationNavigation?: CustomizationNavigationOrder;
  readonly traceabilitySidebarOrder?: number;
  readonly integrationNavigation?: IntegrationNavigationOrder;
}

export function mapRegistryBranchToNavItem(branch: TenantSidebarBranch): NavItem {
  const firstLeaf = branch.children[0];
  if (!firstLeaf) {
    throw new Error(`Registered sidebar branch ${branch.id} has no routes.`);
  }
  return {
    path: firstLeaf.path,
    label: branch.label,
    icon: branch.icon,
    module: branch.module,
    order: branch.order,
    children: branch.children.map((leaf) => ({
      routeId: leaf.routeId,
      path: leaf.path,
      label: leaf.label,
      icon: leaf.icon,
      module: leaf.module,
      order: leaf.order,
      runtimeOrderKey: leaf.runtimeOrderKey,
    })),
  };
}

export function buildRegistryTenantItems(mode: TenantApplicationMode | undefined): NavItem[] {
  return getTenantSidebarTreeForMode(mode)
    .filter((branch) => !legacyModules.has(branch.module))
    .map(mapRegistryBranchToNavItem);
}

function configuredDocumentIntelligenceOrder(
  routeId: string | undefined,
  order: DocumentIntelligenceNavigationOrder
): number {
  if (!routeId) return Number.MAX_SAFE_INTEGER;
  const section = routeId.split(".")[1];
  return section && section in order
    ? order[section as keyof DocumentIntelligenceNavigationOrder]
    : Number.MAX_SAFE_INTEGER;
}

export function applyRuntimeNavigationOrder(
  items: readonly NavItem[],
  order: DocumentIntelligenceNavigationOrder | undefined
): NavItem[] {
  return items.map((item) => {
    if (item.module !== "document_intelligence" || !item.children || !order) return item;
    return {
      ...item,
      children: [...item.children].sort(
        (left, right) =>
          configuredDocumentIntelligenceOrder(left.routeId, order) -
            configuredDocumentIntelligenceOrder(right.routeId, order) ||
          left.label.localeCompare(right.label)
      ),
    };
  });
}

export function applyApiManagementNavigationOrder(
  items: readonly NavItem[],
  schema: ApiManagementConfigurationSchema | undefined
): NavItem[] {
  return items.map((item) => {
    if (item.module !== "api_management" || !item.children || !schema) return item;
    const children = item.children
      .map((child) => {
        const key = child.runtimeOrderKey;
        if (!key || !(key in schema.navigation)) return child;
        return {
          ...child,
          order:
            schema.navigation[key as keyof ApiManagementConfigurationSchema["navigation"]].order,
        };
      })
      .sort(
        (left, right) =>
          (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER) ||
          left.label.localeCompare(right.label)
      );
    return { ...item, order: children[0]?.order, children };
  });
}

export function applyCustomizationNavigationOrder(
  items: readonly NavItem[],
  order: CustomizationNavigationOrder | undefined
): NavItem[] {
  const configured = new Map<string, number>(
    order
      ? [
          ["fields", order.fields_order],
          ["field-values", order.field_values_order],
          ["forms", order.forms_order],
          ["rules", order.rules_order],
          ["executions", order.executions_order],
          ["configuration", order.configuration_order],
        ]
      : []
  );
  return items.map((item) => {
    if (item.module !== "customization_framework" || !item.children || !order) return item;
    return {
      ...item,
      children: [...item.children].sort((left, right) => {
        const leftSection = left.routeId?.split(".")[1] ?? "";
        const rightSection = right.routeId?.split(".")[1] ?? "";
        return (
          (configured.get(leftSection) ?? Number.MAX_SAFE_INTEGER) -
            (configured.get(rightSection) ?? Number.MAX_SAFE_INTEGER) ||
          left.label.localeCompare(right.label)
        );
      }),
    };
  });
}

export function applyIntegrationNavigationOrder(
  item: NavItem,
  integrationNavigation: IntegrationNavigationOrder | undefined
): NavItem {
  if (item.module !== "integration_platform" || !integrationNavigation) return item;
  return {
    ...item,
    order: integrationNavigation.base_order,
    children: item.children
      ?.map((child) => ({
        ...child,
        order: integrationNavigation.route_order[child.routeId ?? ""] ?? child.order,
      }))
      .sort(
        (left, right) =>
          (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER)
      ),
  };
}

export function renderTenantItems(
  staticItems: readonly NavItem[],
  registryItems: readonly NavItem[],
  options: RenderTenantItemsOptions
): NavItem[] {
  const runtimeRegistryItems = applyCustomizationNavigationOrder(
    applyApiManagementNavigationOrder(
      applyRuntimeNavigationOrder(registryItems, options.documentIntelligenceNavigationOrder),
      options.apiManagementSchema
    ),
    options.customizationNavigation
  );
  return [...staticItems, ...runtimeRegistryItems]
    .filter((item) => !item.adminOnly || options.isAdmin)
    .map((item) => ({
      ...item,
      children: item.children?.filter((child) => !child.adminOnly || options.isAdmin),
    }))
    .map((item) =>
      item.module === "blockchain_traceability" && options.traceabilitySidebarOrder !== undefined
        ? { ...item, order: options.traceabilitySidebarOrder }
        : applyIntegrationNavigationOrder(item, options.integrationNavigation)
    )
    .sort(
      (left, right) =>
        (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER)
    );
}
