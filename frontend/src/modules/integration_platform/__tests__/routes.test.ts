/* eslint-disable max-lines-per-function -- route descriptor matrix intentionally keeps expected governance metadata together. */
import { describe, expect, it } from "vitest";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "../routes";

describe("Integration Platform route descriptors", () => {
  it("registers six sidebar destinations and all contextual workflows", () => {
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
    const sidebar = tenantRoutes.filter((route) => route.navigation.type === "sidebar");
    expect(sidebar.map((route) => route.path)).toEqual([
      "/integration-platform",
      "/integration-platform/connectors",
      "/integration-platform/webhooks",
      "/integration-platform/deliveries",
      "/integration-platform/mappings",
      "/integration-platform/configuration",
    ]);
    expect(tenantRoutes).toHaveLength(21);
    expect(
      tenantRoutes.every((route) =>
        route.sourceFile.startsWith("modules/integration_platform/pages/")
      )
    ).toBe(true);
  });

  it("links every contextual page to a same-module sidebar parent", () => {
    const sidebarIds = new Set(
      tenantRoutes.filter((route) => route.navigation.type === "sidebar").map((route) => route.id)
    );
    for (const route of tenantRoutes)
      if (route.navigation.type === "contextual")
        expect(sidebarIds.has(route.navigation.parentRouteId)).toBe(true);
  });

  it("keeps every route descriptor stable for navigation and governance", () => {
    expect(
      tenantRoutes.map((route) => ({
        id: route.id,
        module: route.module,
        path: route.path,
        title: route.title,
        sourceFile: route.sourceFile,
        navigation:
          route.navigation.type === "sidebar"
            ? { type: route.navigation.type, label: route.navigation.label }
            : {
                type: route.navigation.type,
                parentRouteId: route.navigation.parentRouteId,
                label: route.navigation.label,
              },
        requiredPermission: route.requiredPermission ?? null,
      }))
    ).toEqual([
      {
        id: "integration-platform.integrations.list",
        module: "integration_platform",
        path: "/integration-platform",
        title: "Integrations",
        sourceFile: "modules/integration_platform/pages/IntegrationPages.tsx",
        navigation: { type: "sidebar", label: "Integrations" },
        requiredPermission: null,
      },
      {
        id: "integration-platform.integrations.create",
        module: "integration_platform",
        path: "/integration-platform/new",
        title: "New integration",
        sourceFile: "modules/integration_platform/pages/IntegrationPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.integrations.list",
          label: "New integration",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.integrations.detail",
        module: "integration_platform",
        path: "/integration-platform/:id",
        title: "Integration details",
        sourceFile: "modules/integration_platform/pages/IntegrationPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.integrations.list",
          label: "Integration details",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.integrations.edit",
        module: "integration_platform",
        path: "/integration-platform/:id/edit",
        title: "Edit integration",
        sourceFile: "modules/integration_platform/pages/IntegrationPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.integrations.list",
          label: "Edit integration",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.credentials.metadata",
        module: "integration_platform",
        path: "/integration-platform/:id/credentials",
        title: "Credential metadata",
        sourceFile: "modules/integration_platform/pages/IntegrationPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.integrations.list",
          label: "Credential metadata",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.credentials.create",
        module: "integration_platform",
        path: "/integration-platform/:id/credentials/new",
        title: "Add credential",
        sourceFile: "modules/integration_platform/pages/IntegrationPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.integrations.list",
          label: "Add credential",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.credentials.rotate",
        module: "integration_platform",
        path: "/integration-platform/:id/credentials/:credentialId/rotate",
        title: "Rotate credential",
        sourceFile: "modules/integration_platform/pages/IntegrationPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.integrations.list",
          label: "Rotate credential",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.connectors.list",
        module: "integration_platform",
        path: "/integration-platform/connectors",
        title: "Connector catalog",
        sourceFile: "modules/integration_platform/pages/ConnectorPages.tsx",
        navigation: { type: "sidebar", label: "Connector Catalog" },
        requiredPermission: null,
      },
      {
        id: "integration-platform.connectors.detail",
        module: "integration_platform",
        path: "/integration-platform/connectors/:id",
        title: "Connector details",
        sourceFile: "modules/integration_platform/pages/ConnectorPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.connectors.list",
          label: "Connector details",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.connectors.setup",
        module: "integration_platform",
        path: "/integration-platform/connectors/:id/setup",
        title: "Connector setup",
        sourceFile: "modules/integration_platform/pages/ConnectorPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.connectors.list",
          label: "Connector setup",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.webhooks.list",
        module: "integration_platform",
        path: "/integration-platform/webhooks",
        title: "Webhooks",
        sourceFile: "modules/integration_platform/pages/WebhookPages.tsx",
        navigation: { type: "sidebar", label: "Webhooks" },
        requiredPermission: null,
      },
      {
        id: "integration-platform.webhooks.create",
        module: "integration_platform",
        path: "/integration-platform/webhooks/new",
        title: "New webhook",
        sourceFile: "modules/integration_platform/pages/WebhookPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.webhooks.list",
          label: "New webhook",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.webhooks.detail",
        module: "integration_platform",
        path: "/integration-platform/webhooks/:id",
        title: "Webhook details",
        sourceFile: "modules/integration_platform/pages/WebhookPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.webhooks.list",
          label: "Webhook details",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.webhooks.edit",
        module: "integration_platform",
        path: "/integration-platform/webhooks/:id/edit",
        title: "Edit webhook",
        sourceFile: "modules/integration_platform/pages/WebhookPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.webhooks.list",
          label: "Edit webhook",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.deliveries.list",
        module: "integration_platform",
        path: "/integration-platform/deliveries",
        title: "Webhook deliveries",
        sourceFile: "modules/integration_platform/pages/DeliveryPages.tsx",
        navigation: { type: "sidebar", label: "Deliveries" },
        requiredPermission: null,
      },
      {
        id: "integration-platform.deliveries.detail",
        module: "integration_platform",
        path: "/integration-platform/deliveries/:id",
        title: "Delivery evidence",
        sourceFile: "modules/integration_platform/pages/DeliveryPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.deliveries.list",
          label: "Delivery evidence",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.mappings.list",
        module: "integration_platform",
        path: "/integration-platform/mappings",
        title: "Data mappings",
        sourceFile: "modules/integration_platform/pages/MappingPages.tsx",
        navigation: { type: "sidebar", label: "Data Mappings" },
        requiredPermission: null,
      },
      {
        id: "integration-platform.mappings.create",
        module: "integration_platform",
        path: "/integration-platform/mappings/new",
        title: "New data mapping",
        sourceFile: "modules/integration_platform/pages/MappingPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.mappings.list",
          label: "New data mapping",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.mappings.detail",
        module: "integration_platform",
        path: "/integration-platform/mappings/:id",
        title: "Data mapping details",
        sourceFile: "modules/integration_platform/pages/MappingPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.mappings.list",
          label: "Mapping details",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.mappings.edit",
        module: "integration_platform",
        path: "/integration-platform/mappings/:id/edit",
        title: "Edit data mapping",
        sourceFile: "modules/integration_platform/pages/MappingPages.tsx",
        navigation: {
          type: "contextual",
          parentRouteId: "integration-platform.mappings.list",
          label: "Edit mapping",
        },
        requiredPermission: null,
      },
      {
        id: "integration-platform.configuration",
        module: "integration_platform",
        path: "/integration-platform/configuration",
        title: "Integration Platform configuration",
        sourceFile: "modules/integration_platform/pages/ConfigurationPage.tsx",
        navigation: { type: "sidebar", label: "Configuration" },
        requiredPermission: "integration_platform.integration:read",
      },
    ]);
  });
});
