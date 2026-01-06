/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Tenant Dashboard (Home)
 *
 * IMPORTANT:
 * - No mock data. This page only displays identity-derived info (email, tenant_id, roles)
 *   that we already have from the backend session (/api/v1/auth/me/).
 * - Tenant-scoped users must not see platform dashboards or platform management.
 */
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Bot, FileText, Zap, LifeBuoy } from 'lucide-react';

export const TenantDashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-foreground mb-2">Tenant Dashboard</h1>
        <p className="text-muted-foreground">
          Welcome back{user?.email ? `, ${user.email}` : ''}. Manage your tenant modules and workflows.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Identity</CardTitle>
            <CardDescription>Session-backed identity (source of truth: backend)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Email</span>
              <span className="font-medium">{user?.email ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tenant ID</span>
              <span className="font-medium">{user?.tenant_id ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Role</span>
              <span className="font-medium">{user?.tenant_role ?? '—'}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Help & Support</CardTitle>
            <CardDescription>Need assistance?</CardDescription>
          </CardHeader>
          <CardContent className="flex items-start gap-3 text-sm text-muted-foreground">
            <LifeBuoy className="w-5 h-5 text-muted-foreground mt-0.5" />
            <div>
              Contact your platform administrator or support team for access requests, onboarding, and troubleshooting.
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Quick Start</CardTitle>
            <CardDescription>Common actions</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button className="w-full justify-start" onClick={() => navigate('/ai-agents')}>
              <Bot className="w-4 h-4 mr-2" />
              View AI Agents
            </Button>
            <Button className="w-full justify-start" variant="secondary" onClick={() => navigate('/ai-agents/create')}>
              <Zap className="w-4 h-4 mr-2" />
              Create Agent
            </Button>
            <Button className="w-full justify-start" variant="secondary" onClick={() => navigate('/ai-agents/approvals')}>
              <FileText className="w-4 h-4 mr-2" />
              Approval Queue
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Modules</CardTitle>
          <CardDescription>Installed modules will appear here as the foundation modules roll out.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Today, AI Agent Management is available. Tenant-scoped Tenant Management is intentionally not exposed (platform-only).
        </CardContent>
      </Card>
    </div>
  );
};


