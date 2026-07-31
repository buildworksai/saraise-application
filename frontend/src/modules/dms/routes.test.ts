import {
  FilePenLine,
  FilePlus2,
  FileText,
  FolderCog,
  FolderPlus,
  FolderTree,
  Settings2,
} from "lucide-react";
import { getTenantRouteValidationIssues } from "@/navigation/tenant-route-registry";
import { tenantRoutes } from "./routes";

const expectedRoutes = [
  [
    "dms.documents.list",
    "/dms/documents",
    "Documents",
    "Documents",
    "sidebar",
    45,
    undefined,
    undefined,
    FolderTree,
    "modules/dms/pages/DocumentBrowserPage.tsx",
  ],
  [
    "dms.documents.create",
    "/dms/documents/new",
    "Upload document",
    "Upload document",
    "contextual",
    45.01,
    "dms.documents.list",
    undefined,
    FilePlus2,
    "modules/dms/pages/UploadDocumentPage.tsx",
  ],
  [
    "dms.documents.detail",
    "/dms/documents/:id",
    "Document details",
    "Document details",
    "contextual",
    45.02,
    "dms.documents.list",
    undefined,
    FileText,
    "modules/dms/pages/DocumentDetailPage.tsx",
  ],
  [
    "dms.documents.edit",
    "/dms/documents/:id/edit",
    "Edit document",
    "Edit document",
    "contextual",
    45.03,
    "dms.documents.list",
    undefined,
    FilePenLine,
    "modules/dms/pages/EditDocumentPage.tsx",
  ],
  [
    "dms.folders.detail",
    "/dms/folders/:id",
    "Folder details",
    "Folder details",
    "contextual",
    45.04,
    "dms.documents.list",
    undefined,
    FolderTree,
    "modules/dms/pages/FolderDetailPage.tsx",
  ],
  [
    "dms.folders.create",
    "/dms/folders/new",
    "Create folder",
    "Create folder",
    "contextual",
    45.05,
    "dms.documents.list",
    undefined,
    FolderPlus,
    "modules/dms/pages/CreateFolderPage.tsx",
  ],
  [
    "dms.folders.edit",
    "/dms/folders/:id/edit",
    "Edit folder",
    "Edit folder",
    "contextual",
    45.06,
    "dms.documents.list",
    undefined,
    FolderCog,
    "modules/dms/pages/EditFolderPage.tsx",
  ],
  [
    "dms.configuration",
    "/dms/configuration",
    "DMS configuration",
    "Configuration",
    "sidebar",
    45.1,
    undefined,
    "dms.configuration:read",
    Settings2,
    "modules/dms/pages/DmsConfigurationPage.tsx",
  ],
] as const;

describe("DMS tenant route registry", () => {
  it("publishes all eight required unique, titled, and structurally valid routes", () => {
    expect(
      tenantRoutes.map((route) => [
        route.id,
        route.path,
        route.title,
        route.navigation.label,
        route.navigation.type,
        route.navigation.order,
        route.navigation.type === "contextual" ? route.navigation.parentRouteId : undefined,
        route.requiredPermission,
        route.navigation.icon,
        route.sourceFile,
      ])
    ).toEqual(expectedRoutes);
    expect(new Set(tenantRoutes.map((route) => route.id)).size).toBe(tenantRoutes.length);
    expect(new Set(tenantRoutes.map((route) => route.path)).size).toBe(tenantRoutes.length);
    expect(getTenantRouteValidationIssues(tenantRoutes)).toEqual([]);
  });

  it("links every contextual page to the primary document browser", () => {
    const sidebar = tenantRoutes.find((route) => route.navigation.type === "sidebar");
    expect(sidebar?.id).toBe("dms.documents.list");
    for (const route of tenantRoutes)
      if (route.navigation.type === "contextual")
        expect(route.navigation.parentRouteId).toBe(sidebar?.id);
  });

  it("publishes configuration as a governed sidebar destination", () => {
    const configuration = tenantRoutes.find((route) => route.id === "dms.configuration");
    expect(configuration?.path).toBe("/dms/configuration");
    expect(configuration?.requiredPermission).toBe("dms.configuration:read");
    expect(configuration?.navigation.type).toBe("sidebar");
    expect(configuration?.navigation.order).toBe(45.1);
  });
});
