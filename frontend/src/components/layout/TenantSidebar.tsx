/* eslint-disable @typescript-eslint/no-unused-vars, max-lines-per-function -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
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
import { Shield, Users, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDocumentIntelligenceConfiguration } from "@/modules/document_intelligence/hooks/use-document-intelligence-configuration";
import { useTraceabilityCapabilities } from "@/modules/blockchain_traceability/hooks/use-traceability-configuration";
import { QUERY_KEYS } from "@/modules/api_management/contracts";
import { api_managementService } from "@/modules/api_management/services/api_management-service";
import { useRuntimeConfiguration } from "@/modules/customization_framework/components/useRuntimeConfiguration";
import { integrationPlatformService } from "@/modules/integration_platform/services/integration-platform-service";
import type { User } from "@/stores/auth-store";
import { type NavItem, tenantItems } from "./contracts";
import { buildRegistryTenantItems, renderTenantItems } from "./sidebar-utils";

type NavGroupItem = NavItem & { children: NavItem[] };

const registryTenantItems = buildRegistryTenantItems(import.meta.env.VITE_SARAISE_MODE);

const NavGroup = ({ item, user }: { item: NavGroupItem; user: User }) => {
  const location = useLocation();
  const [isOpen, setIsOpen] = useState(() => {
    // Auto-expand if current route matches any child
    return item.children.some((child) => location.pathname.startsWith(child.path));
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
        <span className="flex-1 text-left transition-opacity duration-300">{item.label}</span>
        {isOpen ? (
          <ChevronDown className="w-4 h-4 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 flex-shrink-0" />
        )}
        <div className="absolute inset-0 rounded-xl bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity" />
      </button>

      {isOpen && (
        <div className="ml-6 space-y-1">
          {item.children.map((child) => {
            if (child.children && child.children.length > 0) {
              return (
                <NavGroup
                  key={child.path}
                  item={{ ...child, children: child.children }}
                  user={user}
                />
              );
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
  const documentIntelligenceNavigationOrder =
    documentIntelligenceConfiguration.data?.document?.ui?.navigation_order;
  const traceabilitySidebarOrder = traceabilityCapabilities.data?.document?.ui?.sidebar_order;
  const integrationNavigation = integrationPlatformConfiguration.data?.document?.navigation;
  const customizationNavigation = customizationConfiguration.data?.document?.navigation;
  const renderedTenantItems = renderTenantItems(tenantItems, registryTenantItems, {
    isAdmin,
    documentIntelligenceNavigationOrder,
    apiManagementSchema: apiManagementSchema.data,
    customizationNavigation,
    traceabilitySidebarOrder,
    integrationNavigation,
  });

  return (
    <div className="h-full flex flex-col py-6 bg-gradient-to-b from-white/5 to-transparent">
      {/* Brand */}
      <div className="w-full px-6 mb-8 flex items-center gap-3">
        <div className="p-2 rounded-xl bg-deepBlue shadow-lg shadow-deepBlue/40">
          <div className="w-8 h-8 flex items-center justify-center text-white font-bold text-lg">
            S
          </div>
        </div>
        <div className="font-bold text-xl tracking-tight transition-all duration-300">SARAISE</div>
      </div>

      {/* Navigation */}
      <nav className="w-full flex-1 px-3 space-y-1 overflow-y-auto">
        {renderedTenantItems.map((item) => {
          if (item.children && item.children.length > 0) {
            return (
              <NavGroup key={item.path} item={{ ...item, children: item.children }} user={user} />
            );
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
                <span className="text-muted-foreground">{user.tenant_role ?? "User"}</span>
              </>
            )}
          </div>
          <div className="text-xs text-muted-foreground mt-1 truncate">{user.email}</div>
        </div>
      </div>
    </div>
  );
};
