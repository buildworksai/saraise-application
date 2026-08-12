import type { ComponentType } from "react";
import {
  Bot,
  Database,
  FolderTree,
  Globe2,
  Key,
  LayoutDashboard,
  Plus,
  Settings,
  Workflow,
} from "lucide-react";
import { ROUTES as REGIONAL_ROUTES } from "@/modules/regional/contracts";

export interface NavItem {
  routeId?: string;
  path: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  module?: string;
  order?: number;
  runtimeOrderKey?: string;
  children?: NavItem[];
  adminOnly?: boolean;
}

export const tenantItems: NavItem[] = [
  { path: "/tenant/dashboard", label: "Dashboard", icon: LayoutDashboard },
  {
    path: REGIONAL_ROUTES.ROOT,
    label: "Regional",
    icon: Globe2,
    module: "regional",
    children: [
      { path: REGIONAL_ROUTES.ROOT, label: "Resources", icon: Globe2 },
      { path: REGIONAL_ROUTES.CREATE, label: "Create resource", icon: Plus },
      {
        path: REGIONAL_ROUTES.CONFIGURATION,
        label: "Configuration",
        icon: Settings,
        adminOnly: true,
      },
    ],
  },
  {
    path: "/workflow-automation/workflows",
    label: "Workflow Automation",
    icon: Workflow,
    module: "workflow_automation",
  },
  {
    path: "/dms/documents",
    label: "Document Management",
    icon: FolderTree,
    module: "dms",
  },
  {
    path: "/ai-provider-configuration",
    label: "AI Providers",
    icon: Bot,
    module: "ai_provider_configuration",
    children: [
      {
        path: "/ai-provider-configuration",
        label: "Provider Console",
        icon: Database,
      },
      {
        path: "/ai-provider-configuration/create",
        label: "Connect Credential",
        icon: Plus,
      },
      {
        path: "/ai-provider-configuration/runtime-configuration",
        label: "Runtime Configuration",
        icon: Settings,
        adminOnly: true,
      },
      {
        path: "/ai-providers/secrets",
        label: "Secret Operations",
        icon: Key,
      },
    ],
  },
];

export const legacyModules = new Set(
  tenantItems
    .map((item) => item.module)
    .filter((moduleName): moduleName is string => moduleName !== undefined)
);
