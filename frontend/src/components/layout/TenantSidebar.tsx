/**
 * Tenant Sidebar
 *
 * ⚠️ ARCHITECTURAL ENFORCEMENT: Application repo is tenant-only.
 * Platform management UI MUST be in saraise-platform/frontend/.
 *
 * Design with glassmorphism effects.
 */
import { NavLink, useLocation } from "react-router-dom";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  Shield,
  Users,
  Database,
  Workflow,
  FolderTree,
  Key,
  Bot,
  BarChart3,
  TrendingUp,
  Building2,
  Briefcase,
  CheckSquare,
  Globe2,
  Plus,
  Settings,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getTenantSidebarTreeForMode } from "@/navigation/tenant-route-registry";
import { useDocumentIntelligenceConfiguration } from "@/modules/document_intelligence/hooks/use-document-intelligence-configuration";
import { useTraceabilityCapabilities } from "@/modules/blockchain_traceability/hooks/use-traceability-configuration";
import { QUERY_KEYS, type ApiManagementConfigurationSchema } from "@/modules/api_management/contracts";
import { api_managementService } from "@/modules/api_management/services/api_management-service";
import { ROUTES as REGIONAL_ROUTES } from "@/modules/regional/contracts";
import { useRuntimeConfiguration } from "@/modules/customization_framework/components/useRuntimeConfiguration";
import { integrationPlatformService } from "@/modules/integration_platform/services/integration-platform-service";
import type { User } from "@/stores/auth-store";

interface NavItem {
  routeId?: string;
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  module?: string;
  order?: number;
  runtimeOrderKey?: string;
  children?: NavItem[];
  adminOnly?: boolean;
}

const tenantItems: NavItem[] = [
  { path: "/tenant/dashboard", label: "Dashboard", icon: LayoutDashboard },
  // Phase 8 & 9 Modules
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
    path: "/dms",
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
        path: "/ai-providers/secrets",
        label: "Secret Operations",
        icon: Key,
      },
    ],
  },
];

const legacyModules = new Set(
  tenantItems
    .map((item) => item.module)
    .filter((moduleName): moduleName is string => moduleName !== undefined),
);

const registryTenantItems: NavItem[] = getTenantSidebarTreeForMode(
  import.meta.env.VITE_SARAISE_MODE,
)
  .filter((branch) => !legacyModules.has(branch.module))
  .map((branch) => {
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
  });

interface DocumentIntelligenceNavigationOrder {
  extractions: number;
  classifications: number;
  training: number;
  templates: number;
  health: number;
  configuration: number;
}

function configuredDocumentIntelligenceOrder(
  routeId: string | undefined,
  order: DocumentIntelligenceNavigationOrder,
): number {
  if (!routeId) return Number.MAX_SAFE_INTEGER;
  const section = routeId.split(".")[1];
  return section && section in order
    ? order[section as keyof DocumentIntelligenceNavigationOrder]
    : Number.MAX_SAFE_INTEGER;
}

function applyRuntimeNavigationOrder(
  items: readonly NavItem[],
  order: DocumentIntelligenceNavigationOrder | undefined,
): NavItem[] {
  return items.map((item) => {
    if (item.module !== "document_intelligence" || !item.children || !order) return item;
    return {
      ...item,
      children: [...item.children].sort(
        (left, right) =>
          configuredDocumentIntelligenceOrder(left.routeId, order) -
            configuredDocumentIntelligenceOrder(right.routeId, order) ||
          left.label.localeCompare(right.label),
      ),
    };
  });
}

function applyApiManagementNavigationOrder(
  items: readonly NavItem[],
  schema: ApiManagementConfigurationSchema | undefined,
): NavItem[] {
  return items.map((item) => {
    if (item.module !== "api_management" || !item.children || !schema) return item;
    const children = item.children.map((child) => {
      const key = child.runtimeOrderKey;
      if (!key || !(key in schema.navigation)) return child;
      return {
        ...child,
        order: schema.navigation[key as keyof ApiManagementConfigurationSchema["navigation"]].order,
      };
    }).sort((left, right) => (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER) || left.label.localeCompare(right.label));
    return { ...item, order: children[0]?.order, children };
  });
}

function applyCustomizationNavigationOrder(
  items: readonly NavItem[],
  order: {
    readonly fields_order: number;
    readonly field_values_order: number;
    readonly forms_order: number;
    readonly rules_order: number;
    readonly executions_order: number;
    readonly configuration_order: number;
  } | undefined,
): NavItem[] {
  const configured = new Map<string, number>(order ? [
    ["fields", order.fields_order],
    ["field-values", order.field_values_order],
    ["forms", order.forms_order],
    ["rules", order.rules_order],
    ["executions", order.executions_order],
    ["configuration", order.configuration_order],
  ] : []);
  return items.map((item) => {
    if (item.module !== "customization_framework" || !item.children || !order) return item;
    return {
      ...item,
      children: [...item.children].sort((left, right) => {
        const leftSection = left.routeId?.split(".")[1] ?? "";
        const rightSection = right.routeId?.split(".")[1] ?? "";
        return (configured.get(leftSection) ?? Number.MAX_SAFE_INTEGER) - (configured.get(rightSection) ?? Number.MAX_SAFE_INTEGER) || left.label.localeCompare(right.label);
      }),
    };
  });
}

const NavGroup = ({ item, user }: { item: NavItem; user: User }) => {
  const location = useLocation();
  const [isOpen, setIsOpen] = useState(() => {
    // Auto-expand if current route matches any child
    return item.children?.some((child) =>
      location.pathname.startsWith(child.path)
    ) ?? false;
  });

  const isActive = location.pathname.startsWith(item.path);
  const Icon = item.icon;

  return (
    <div className="space-y-1">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex w-full items-center gap-3 px-3 py-3 rounded-xl transition-all duration-200 group relative overflow-hidden",
          isActive
            ? "bg-deepBlue text-white shadow-md shadow-deepBlue/25 font-medium translate-x-1"
            : "text-muted-foreground hover:bg-white/10 hover:text-foreground hover:translate-x-1"
        )}
      >
        <Icon className="w-5 h-5 transition-transform group-hover:scale-110" />
        <span className="flex-1 text-left transition-opacity duration-300">
          {item.label}
        </span>
        {isOpen ? (
          <ChevronDown className="w-4 h-4 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 flex-shrink-0" />
        )}
        <div className="absolute inset-0 rounded-xl bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity" />
      </button>

      {isOpen && item.children && (
        <div className="ml-6 space-y-1">
          {item.children.map((child) => {
            if (child.children && child.children.length > 0) {
              return <NavGroup key={child.path} item={child} user={user} />;
            }
            return <NavItem key={child.routeId ?? child.path} item={child} />;
          })}
        </div>
      )}
    </div>
  );
};

const NavItem = ({ item }: { item: NavItem }) => {
  const Icon = item.icon;
  const isParentRoute = item.path === "/ai-agents" || item.path === "/tenant/dashboard";

  return (
    <NavLink
      to={item.path}
      end={isParentRoute}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-200 group relative overflow-hidden",
          isActive
            ? "bg-deepBlue/50 text-white font-medium"
            : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
        )
      }
    >
      {Icon && <Icon className="w-4 h-4 transition-transform group-hover:scale-110" />}
      <span className="text-sm">{item.label}</span>
    </NavLink>
  );
};

export const TenantSidebar = ({ user }: { user: User }) => {
  const isAdmin = user.tenant_role === "tenant_admin";
  const documentIntelligenceConfiguration = useDocumentIntelligenceConfiguration();
  const customizationConfiguration = useRuntimeConfiguration();
  const traceabilityCapabilities = useTraceabilityCapabilities();
  const apiManagementSchema = useQuery({
    queryKey: QUERY_KEYS.CONFIGURATION_SCHEMA(),
    queryFn: () => api_managementService.getConfigurationSchema(),
  });
  const integrationPlatformConfiguration = useQuery({
    queryKey: ["integration-platform", "configuration"],
    queryFn: () => integrationPlatformService.getConfiguration(),
  });
  const runtimeRegistryItems = applyCustomizationNavigationOrder(
    applyApiManagementNavigationOrder(
      applyRuntimeNavigationOrder(
        registryTenantItems,
        documentIntelligenceConfiguration.data?.document.ui.navigation_order,
      ),
      apiManagementSchema.data,
    ),
    customizationConfiguration.data?.document.navigation,
  );
  const renderedTenantItems = [...tenantItems, ...runtimeRegistryItems]
    .filter((item) => !item.adminOnly || isAdmin)
    .map((item) => ({
      ...item,
      children: item.children?.filter((child) => !child.adminOnly || isAdmin),
    }))
    .map((item) => item.module === "blockchain_traceability" && traceabilityCapabilities.data
      ? { ...item, order: traceabilityCapabilities.data.document.ui.sidebar_order }
      : item.module === "integration_platform" && integrationPlatformConfiguration.data
        ? {
            ...item,
            order: integrationPlatformConfiguration.data.document.navigation.base_order,
            children: item.children
              ?.map((child) => ({
                ...child,
                order: integrationPlatformConfiguration.data!.document.navigation.route_order[child.routeId ?? ""] ?? child.order,
              }))
              .sort((left, right) => left.order - right.order),
          }
      : item)
    .sort((left, right) => (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER));

  return (
    <div className="h-full flex flex-col py-6 bg-gradient-to-b from-white/5 to-transparent">
      {/* Brand */}
      <div className="w-full px-6 mb-8 flex items-center gap-3">
        <div className="p-2 rounded-xl bg-deepBlue shadow-lg shadow-deepBlue/40">
          <div className="w-8 h-8 flex items-center justify-center text-white font-bold text-lg">
            S
          </div>
        </div>
        <div className="font-bold text-xl tracking-tight transition-all duration-300">
          SARAISE
        </div>
      </div>

      {/* Navigation */}
      <nav className="w-full flex-1 px-3 space-y-1 overflow-y-auto">
        {renderedTenantItems.map((item) => {
          if (item.children && item.children.length > 0) {
            return <NavGroup key={item.path} item={item} user={user} />;
          }
          return <NavItem key={item.path} item={item} />;
        })}
      </nav>

      {/* Footer Status */}
      <div className="mt-auto px-6 w-full">
        <div className="p-4 rounded-xl bg-white/5 border border-white/5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-muted-foreground uppercase">
              System Status
            </span>
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          </div>
          <div className="text-xs text-muted-foreground">
            <div className="flex justify-between">
              <span>API</span>
              <span className="text-green-500">Operational</span>
            </div>
            <div className="flex justify-between mt-1">
              <span>Services</span>
              <span className="text-green-500">Healthy</span>
            </div>
          </div>
        </div>

        {/* User Role Indicator */}
        <div className="mt-3 p-3 rounded-lg bg-white/5">
          <div className="flex items-center gap-2 text-xs">
            {isAdmin ? (
              <>
                <Shield className="w-4 h-4 text-gold" />
                <span className="text-gold">Admin Access</span>
              </>
            ) : (
              <>
                <Users className="w-4 h-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {user.tenant_role ?? "User"}
                </span>
              </>
            )}
          </div>
          <div className="text-xs text-muted-foreground mt-1 truncate">
            {user.email}
          </div>
        </div>
      </div>
    </div>
  );
};
