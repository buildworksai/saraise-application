/**
 * Tenant Sidebar
 *
 * For tenant-scoped users (tenant_admin/tenant_user).
 * Contains tenant modules only (no platform dashboards).
 */
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Bot, Zap, FileText } from 'lucide-react';
import type { User } from '@/stores/auth-store';

interface NavItem {
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  module?: string;
}

const tenantItems: NavItem[] = [
  { path: '/tenant/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/ai-agents', label: 'AI Agents', icon: Bot, module: 'ai-agent-management' },
  { path: '/ai-agents/executions', label: 'Executions', icon: Zap, module: 'ai-agent-management' },
  { path: '/ai-agents/approvals', label: 'Approvals', icon: FileText, module: 'ai-agent-management' },
];

export const TenantSidebar = ({ user }: { user: User }) => {
  return (
    <nav className="bg-card text-card-foreground w-64 min-h-screen p-4 border-r border-border">
      <div className="mb-8">
        <h1 className="text-xl font-bold">SARAISE</h1>
      </div>

      <ul className="space-y-2">
        {tenantItems.map((item) => {
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
          {user.tenant_id && <div className="text-xs mt-1">Tenant: {user.tenant_id.slice(0, 8)}...</div>}
          <div className="text-xs mt-1">Role: {user.tenant_role}</div>
        </div>
      </div>
    </nav>
  );
};


