/* eslint-disable max-lines-per-function -- Navigation composition tests assert full ordering contracts across module-specific runtime configuration. */
import { describe, expect, it } from "vitest";
import type { ApiManagementConfigurationSchema } from "@/modules/api_management/contracts";
import type { TenantSidebarBranch } from "@/navigation/tenant-route-registry";
import type { NavItem } from "./contracts";
import {
  applyApiManagementNavigationOrder,
  applyCustomizationNavigationOrder,
  applyIntegrationNavigationOrder,
  applyRuntimeNavigationOrder,
  buildRegistryTenantItems,
  mapRegistryBranchToNavItem,
  renderTenantItems,
} from "./sidebar-utils";

const Icon = () => null;

function labels(items: readonly NavItem[]): string[] {
  return items.map((item) => item.label);
}

function childLabels(item: NavItem | undefined): string[] {
  if (!item?.children) throw new Error("Expected item children to be present.");
  return labels(item.children);
}

const registryBranch: TenantSidebarBranch = {
  id: "branch-1",
  module: "module_a",
  label: "Module A",
  icon: Icon,
  order: 25,
  children: [
    {
      id: "leaf-1",
      routeId: "module_a.list",
      module: "module_a",
      path: "/module-a",
      label: "List",
      icon: Icon,
      order: 25,
      runtimeOrderKey: "resources_list",
    },
  ],
};

describe("sidebar utilities", () => {
  it("maps registry branches into tenant nav groups and rejects empty branches", () => {
    expect(mapRegistryBranchToNavItem(registryBranch)).toEqual({
      path: "/module-a",
      label: "Module A",
      icon: Icon,
      module: "module_a",
      order: 25,
      children: [
        {
          routeId: "module_a.list",
          path: "/module-a",
          label: "List",
          icon: Icon,
          module: "module_a",
          order: 25,
          runtimeOrderKey: "resources_list",
        },
      ],
    });
    expect(() =>
      mapRegistryBranchToNavItem({ ...registryBranch, id: "empty", children: [] })
    ).toThrow("Registered sidebar branch empty has no routes.");
  });

  it("builds registry tenant items while excluding legacy static modules", () => {
    const items = buildRegistryTenantItems(undefined);

    expect(items.map((item) => item.module)).toContain("api_management");
    expect(items.map((item) => item.module)).toContain("integration_platform");
    expect(items.map((item) => item.module)).not.toContain("workflow_automation");
    expect(items.every((item) => item.path.startsWith("/"))).toBe(true);
  });

  it("orders document intelligence children by runtime section order with label fallback", () => {
    const [item] = applyRuntimeNavigationOrder(
      [
        {
          path: "/di",
          label: "Document Intelligence",
          icon: Icon,
          module: "document_intelligence",
          children: [
            {
              path: "/di/extractions",
              label: "Extractions",
              icon: Icon,
              routeId: "di.extractions",
            },
            { path: "/di/templates", label: "Templates", icon: Icon, routeId: "di.templates" },
            { path: "/di/other-b", label: "Other B", icon: Icon, routeId: "di.other_b" },
            { path: "/di/other-a", label: "Other A", icon: Icon, routeId: undefined },
          ],
        },
      ],
      {
        classifications: 10,
        templates: 20,
        extractions: 30,
        training: 40,
        health: 50,
        configuration: 60,
      }
    );

    expect(childLabels(item)).toEqual(["Templates", "Extractions", "Other A", "Other B"]);
  });

  it("returns non-target runtime items unchanged when configuration is absent", () => {
    const item: NavItem = { path: "/x", label: "X", icon: Icon, module: "other" };
    const documentWithoutChildren: NavItem = {
      path: "/di",
      label: "Document Intelligence",
      icon: Icon,
      module: "document_intelligence",
    };
    const apiWithoutChildren: NavItem = {
      path: "/api",
      label: "API",
      icon: Icon,
      module: "api_management",
    };
    const customizationWithoutChildren: NavItem = {
      path: "/custom",
      label: "Customization",
      icon: Icon,
      module: "customization_framework",
    };

    expect(applyRuntimeNavigationOrder([item], undefined)).toEqual([item]);
    expect(applyApiManagementNavigationOrder([item], undefined)).toEqual([item]);
    expect(applyCustomizationNavigationOrder([item], undefined)).toEqual([item]);
    expect(applyIntegrationNavigationOrder(item, undefined)).toEqual(item);
    expect(
      applyRuntimeNavigationOrder([documentWithoutChildren], {
        classifications: 1,
        templates: 2,
        extractions: 3,
        training: 4,
        health: 5,
        configuration: 6,
      })
    ).toEqual([documentWithoutChildren]);
    expect(
      applyApiManagementNavigationOrder([apiWithoutChildren], {
        schema_version: 1,
        environment: "production",
        environments: ["production"],
        fields: {},
        dependencies: [],
        navigation: {
          resources_list: { order: 1 },
          resources_create: { order: 2 },
          resources_detail: { order: 3 },
          configuration: { order: 4 },
        },
        platform_hard_ceilings: {},
      } satisfies ApiManagementConfigurationSchema)
    ).toEqual([apiWithoutChildren]);
    expect(
      applyCustomizationNavigationOrder([customizationWithoutChildren], {
        fields_order: 1,
        field_values_order: 2,
        forms_order: 3,
        rules_order: 4,
        executions_order: 5,
        configuration_order: 6,
      })
    ).toEqual([customizationWithoutChildren]);
  });

  it("orders api management children from schema keys and preserves missing runtime keys", () => {
    const [api] = applyApiManagementNavigationOrder(
      [
        {
          path: "/api",
          label: "API",
          icon: Icon,
          module: "api_management",
          children: [
            {
              path: "/api",
              label: "Resources",
              icon: Icon,
              runtimeOrderKey: "resources_list",
              order: 50,
            },
            {
              path: "/api/create",
              label: "Create",
              icon: Icon,
              runtimeOrderKey: "resources_create",
              order: 60,
            },
            {
              path: "/api/unknown",
              label: "Unknown",
              icon: Icon,
              runtimeOrderKey: "missing",
              order: 10,
            },
          ],
        },
      ],
      {
        schema_version: 1,
        environment: "production",
        environments: ["production"],
        fields: {},
        dependencies: [],
        navigation: {
          resources_list: { order: 30 },
          resources_create: { order: 20 },
          resources_detail: { order: 40 },
          configuration: { order: 50 },
        },
        platform_hard_ceilings: {},
      } satisfies ApiManagementConfigurationSchema
    );

    expect(api?.order).toBe(10);
    expect(childLabels(api)).toEqual(["Unknown", "Create", "Resources"]);
  });

  it("orders customization and integration children from module runtime configuration", () => {
    const [customization] = applyCustomizationNavigationOrder(
      [
        {
          path: "/custom",
          label: "Customization",
          icon: Icon,
          module: "customization_framework",
          children: [
            {
              path: "/custom/fields",
              label: "Fields",
              icon: Icon,
              routeId: "customization_framework.fields",
            },
            {
              path: "/custom/field-values",
              label: "Field Values",
              icon: Icon,
              routeId: "customization_framework.field-values",
            },
            {
              path: "/custom/forms",
              label: "Forms",
              icon: Icon,
              routeId: "customization_framework.forms",
            },
            {
              path: "/custom/rules",
              label: "Rules",
              icon: Icon,
              routeId: "customization_framework.rules",
            },
            {
              path: "/custom/executions",
              label: "Executions",
              icon: Icon,
              routeId: "customization_framework.executions",
            },
            {
              path: "/custom/configuration",
              label: "Configuration",
              icon: Icon,
              routeId: "customization_framework.configuration",
            },
            { path: "/custom/zz", label: "ZZ Unknown", icon: Icon },
          ],
        },
      ],
      {
        fields_order: 30,
        field_values_order: 20,
        forms_order: 10,
        rules_order: 40,
        executions_order: 50,
        configuration_order: 60,
      }
    );
    expect(childLabels(customization)).toEqual([
      "Forms",
      "Field Values",
      "Fields",
      "Rules",
      "Executions",
      "Configuration",
      "ZZ Unknown",
    ]);

    const integration = applyIntegrationNavigationOrder(
      {
        path: "/integration",
        label: "Integration",
        icon: Icon,
        module: "integration_platform",
        children: [
          {
            path: "/integration/integrations",
            label: "Integrations",
            icon: Icon,
            routeId: "integration.integrations",
          },
          {
            path: "/integration/webhooks",
            label: "Webhooks",
            icon: Icon,
            routeId: "integration.webhooks",
          },
        ],
      },
      {
        base_order: 5,
        route_order: { "integration.webhooks": 1 },
      }
    );
    expect(integration.order).toBe(5);
    expect(childLabels(integration)).toEqual(["Webhooks", "Integrations"]);
    expect(
      applyIntegrationNavigationOrder(
        { path: "/integration", label: "Integration", icon: Icon, module: "integration_platform" },
        { base_order: 5, route_order: {} }
      )
    ).toEqual({
      path: "/integration",
      label: "Integration",
      icon: Icon,
      module: "integration_platform",
      order: 5,
      children: undefined,
    });
  });

  it("renders final tenant items with admin filtering and top-level order adjustments", () => {
    const staticItems: NavItem[] = [
      { path: "/dashboard", label: "Dashboard", icon: Icon },
      { path: "/admin", label: "Admin", icon: Icon, adminOnly: true },
    ];
    const registryItems: NavItem[] = [
      {
        path: "/trace",
        label: "Traceability",
        icon: Icon,
        module: "blockchain_traceability",
        order: 70,
      },
      {
        path: "/integration",
        label: "Integration",
        icon: Icon,
        module: "integration_platform",
        order: 80,
        children: [
          {
            path: "/integration/a",
            label: "A",
            icon: Icon,
            routeId: "integration.a",
            adminOnly: true,
          },
          { path: "/integration/b", label: "B", icon: Icon, routeId: "integration.b" },
        ],
      },
    ];

    expect(
      labels(
        renderTenantItems(staticItems, registryItems, {
          isAdmin: false,
          traceabilitySidebarOrder: 1,
          integrationNavigation: { base_order: 2, route_order: { "integration.b": 1 } },
        })
      )
    ).toEqual(["Traceability", "Integration", "Dashboard"]);
    expect(
      childLabels(
        renderTenantItems(staticItems, registryItems, {
          isAdmin: false,
          integrationNavigation: { base_order: 2, route_order: { "integration.b": 1 } },
        }).find((item) => item.module === "integration_platform")
      )
    ).toEqual(["B"]);
    expect(labels(renderTenantItems(staticItems, registryItems, { isAdmin: true }))).toContain(
      "Admin"
    );
    expect(
      labels(
        renderTenantItems(staticItems, registryItems, {
          isAdmin: false,
          traceabilitySidebarOrder: undefined,
        })
      )
    ).toEqual(["Traceability", "Integration", "Dashboard"]);
  });
});
