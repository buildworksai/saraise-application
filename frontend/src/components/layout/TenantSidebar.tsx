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
import {
  LayoutDashboard,
  Bot,
  Zap,
  FileText,
  Shield,
  Users,
  Database,
  Workflow,
  DatabaseZap,
  FolderTree,
  Plug,
  Key,
  Bell,
  BarChart3,
  TrendingUp,
  Building2,
  Briefcase,
  CheckSquare,
  Settings,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { User } from "@/stores/auth-store";

interface NavItem {
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  module?: string;
  children?: NavItem[];
}

const tenantItems: NavItem[] = [
  { path: "/tenant/dashboard", label: "Dashboard", icon: LayoutDashboard },
  {
    path: "/ai-agents",
    label: "AI Agents",
    icon: Bot,
    module: "ai-agent-management",
  },
  {
    path: "/ai-agents/executions",
    label: "Executions",
    icon: Zap,
    module: "ai-agent-management",
  },
  {
    path: "/ai-agents/approvals",
    label: "Approvals",
    icon: FileText,
    module: "ai-agent-management",
  },
  {
    path: "/metadata",
    label: "Metadata Modeling",
    icon: Database,
    module: "metadata_modeling",
  },
  // Phase 8 & 9 Modules
  {
    path: "/workflow-automation/workflows",
    label: "Workflow Automation",
    icon: Workflow,
    module: "workflow_automation",
  },
  {
    path: "/data-migration",
    label: "Data Migration",
    icon: DatabaseZap,
    module: "data_migration",
  },
  {
    path: "/dms",
    label: "Document Management",
    icon: FolderTree,
    module: "dms",
  },
  {
    path: "/integration-platform",
    label: "Integration Platform",
    icon: Plug,
    module: "integration_platform",
  },
  {
    path: "/ai-providers/secrets",
    label: "Secret Management",
    icon: Key,
    module: "ai_provider_configuration",
  },
  {
    path: "/notifications",
    label: "Notifications",
    icon: Bell,
    module: "notifications",
  },
  // CRM Module - Collapsible Group
  {
    path: "/crm",
    label: "CRM",
    icon: BarChart3,
    module: "crm",
    children: [
      { path: "/crm/dashboard", label: "Dashboard", icon: LayoutDashboard },
      {
        path: "/crm/leads",
        label: "Leads",
        icon: TrendingUp,
        children: [
          { path: "/crm/leads", label: "All Leads", icon: TrendingUp },
          { path: "/crm/leads/new", label: "New Leads", icon: TrendingUp },
          { path: "/crm/leads/qualified", label: "Qualified Leads", icon: TrendingUp },
          { path: "/crm/leads/converted", label: "Converted Leads", icon: TrendingUp },
        ],
      },
      { path: "/crm/contacts", label: "Contacts", icon: Users },
      {
        path: "/crm/accounts",
        label: "Accounts",
        icon: Building2,
        children: [
          { path: "/crm/accounts", label: "All Accounts", icon: Building2 },
          { path: "/crm/accounts/customers", label: "Customers", icon: Building2 },
          { path: "/crm/accounts/prospects", label: "Prospects", icon: Building2 },
          { path: "/crm/accounts/hierarchy", label: "Account Hierarchy", icon: Building2 },
        ],
      },
      {
        path: "/crm/opportunities",
        label: "Opportunities",
        icon: Briefcase,
        children: [
          { path: "/crm/opportunities/pipeline", label: "Pipeline View", icon: Briefcase },
          { path: "/crm/opportunities", label: "All Opportunities", icon: Briefcase },
          { path: "/crm/opportunities/my", label: "My Opportunities", icon: Briefcase },
          { path: "/crm/opportunities/closed", label: "Closed Opportunities", icon: Briefcase },
        ],
      },
      {
        path: "/crm/activities",
        label: "Activities",
        icon: CheckSquare,
        children: [
          { path: "/crm/activities/tasks", label: "My Tasks", icon: CheckSquare },
          { path: "/crm/activities", label: "Activity Log", icon: CheckSquare },
        ],
      },
    ],
  },
];

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
            return <NavItem key={child.path} item={child} />;
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
        {tenantItems.map((item) => {
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
