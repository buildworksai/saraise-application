/**
 * Platform Sidebar
 *
 * ⚠️ ARCHITECTURAL NOTE: Platform management UI removed.
 * Platform dashboards and management MUST be in a separate platform frontend
 * (saraise-platform/frontend/), not in the application frontend.
 *
 * For platform-scoped users (platform_owner/platform_operator) in the application:
 * - Read-only tenant information access
 * - Cross-tenant module access (e.g., AI Agents)
 *
 * Platform management (settings, feature flags, dashboards) is FORBIDDEN here.
 */
import { NavLink } from 'react-router-dom';
import {
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

// ⚠️ ARCHITECTURAL ENFORCEMENT: Platform dashboards removed
// Platform management UI MUST be in saraise-platform/frontend/

const managementItems: NavItem[] = [
  { 
    path: '/tenant-management', 
    label: 'Tenant Management (Read-Only)', 
    icon: Users, 
    module: 'tenant-management' 
  },
];

// Cross-tenant modules accessible to platform owners/operators
const moduleItems: NavItem[] = [
  { path: '/ai-agents', label: 'AI Agents', icon: Bot, module: 'ai-agent-management' },
  { path: '/ai-agents/executions', label: 'Executions', icon: Zap, module: 'ai-agent-management' },
  { path: '/ai-agents/approvals', label: 'Approvals', icon: FileText, module: 'ai-agent-management' },
];

export const PlatformSidebar = ({ user }: { user: User }) => {
  // ⚠️ ARCHITECTURAL ENFORCEMENT: Platform dashboards removed
  // Platform management UI MUST be in saraise-platform/frontend/

  return (
    <nav className="bg-card text-card-foreground w-64 min-h-screen p-4 border-r border-border">
      <div className="mb-8">
        <h1 className="text-xl font-bold">SARAISE</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Application Frontend
        </p>
      </div>

      <ul className="space-y-2">

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


