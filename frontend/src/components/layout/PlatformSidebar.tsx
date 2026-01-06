/**
 * Platform Sidebar
 *
 * For platform-scoped users (platform_owner/platform_operator).
 * Contains platform dashboards + platform-level management areas.
 */
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Activity,
  Server,
  TrendingUp,
  Shield,
  Building2,
  DollarSign,
  Users,
  Bot,
  Zap,
  FileText,
} from 'lucide-react';
import { useState } from 'react';
import type { User } from '@/stores/auth-store';

interface NavItem {
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  module?: string;
}

const platformItems: NavItem[] = [
  { path: '/platform/dashboard', label: 'Overview', icon: LayoutDashboard, module: 'platform-management' },
  { path: '/platform/operations', label: 'Operations', icon: Activity, module: 'platform-management' },
  { path: '/platform/infrastructure', label: 'Infrastructure', icon: Server, module: 'platform-management' },
  { path: '/platform/business', label: 'Business', icon: TrendingUp, module: 'platform-management' },
  { path: '/platform/security', label: 'Security', icon: Shield, module: 'platform-management' },
  { path: '/platform/tenant-health', label: 'Tenant Health', icon: Building2, module: 'platform-management' },
  { path: '/platform/cost', label: 'Cost', icon: DollarSign, module: 'platform-management' },
];

const managementItems: NavItem[] = [
  { path: '/tenant-management', label: 'Tenant Management', icon: Users, module: 'tenant-management' },
];

// Cross-tenant modules accessible to platform owners/operators
const moduleItems: NavItem[] = [
  { path: '/ai-agents', label: 'AI Agents', icon: Bot, module: 'ai-agent-management' },
  { path: '/ai-agents/executions', label: 'Executions', icon: Zap, module: 'ai-agent-management' },
  { path: '/ai-agents/approvals', label: 'Approvals', icon: FileText, module: 'ai-agent-management' },
];

export const PlatformSidebar = ({ user }: { user: User }) => {
  const [platformMenuOpen, setPlatformMenuOpen] = useState(true);

  // Strict: only platform_owner sees platform dashboards per current backend policy.
  const canSeePlatformDashboards = user.platform_role === 'platform_owner';

  return (
    <nav className="bg-card text-card-foreground w-64 min-h-screen p-4 border-r border-border">
      <div className="mb-8">
        <h1 className="text-xl font-bold">SARAISE</h1>
      </div>

      <ul className="space-y-2">
        {canSeePlatformDashboards && (
          <>
            <li>
              <button
                onClick={() => setPlatformMenuOpen(!platformMenuOpen)}
                className="w-full flex items-center justify-between px-4 py-2 rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <div className="flex items-center gap-3">
                  <LayoutDashboard className="w-5 h-5" />
                  <span className="font-semibold">Platform</span>
                </div>
                <span className={`transform transition-transform ${platformMenuOpen ? 'rotate-180' : ''}`}>▼</span>
              </button>

              {platformMenuOpen && (
                <ul className="ml-4 mt-2 space-y-1">
                  {platformItems.map((item) => {
                    const Icon = item.icon;
                    return (
                      <li key={item.path}>
                        <NavLink
                          to={item.path}
                          className={({ isActive }) =>
                            `flex items-center gap-3 px-4 py-2 rounded-md transition-colors ${
                              isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                            }`
                          }
                        >
                          <Icon className="w-4 h-4" />
                          <span className="text-sm">{item.label}</span>
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>

            <li className="my-2 border-t border-border"></li>
          </>
        )}

        {managementItems.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-2 rounded-md transition-colors ${
                    isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                <span>{item.label}</span>
              </NavLink>
            </li>
          );
        })}

        <li className="my-2 border-t border-border"></li>

        {moduleItems.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-2 rounded-md transition-colors ${
                    isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                <span>{item.label}</span>
              </NavLink>
            </li>
          );
        })}
      </ul>

      <div className="mt-8 pt-8 border-t border-border">
        <div className="px-4 py-2 text-sm text-muted-foreground">
          <div className="font-medium text-foreground">{user.email}</div>
          <div className="text-xs mt-1">Role: {user.platform_role}</div>
        </div>
      </div>
    </nav>
  );
};


