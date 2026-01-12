/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Tenant Dashboard (Home)
 *
 * ⚠️ ARCHITECTURAL ENFORCEMENT: Application repo is tenant-only.
 * Platform management UI MUST be in saraise-platform/frontend/.
 *
 * EUCORA-inspired design with glassmorphism effects.
 */
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Bot, FileText, Zap, LifeBuoy, CheckCircle2, ShieldCheck } from 'lucide-react';

export const TenantDashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
          <p className="text-muted-foreground">Welcome back{user?.email ? `, ${user.email}` : ''}. Manage your tenant modules and workflows.</p>
        </div>
      </div>

      {/* Stats Cards - EUCORA Style */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="glass">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">AI Agents</CardTitle>
            <Bot className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">0</div>
            <p className="text-xs text-muted-foreground">
              Active agents
            </p>
          </CardContent>
        </Card>

        <Card className="glass">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Executions</CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">0</div>
            <p className="text-xs text-muted-foreground">
              Recent executions
            </p>
          </CardContent>
        </Card>

        <Card className="glass">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Approvals</CardTitle>
            <ShieldCheck className="h-4 w-4 text-amber-500 dark:text-amber-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">0</div>
            <p className="text-xs text-muted-foreground">
              Awaiting review
            </p>
          </CardContent>
        </Card>

        <Card className="glass">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">System Health</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-500 dark:text-green-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">✓</div>
            <p className="text-xs text-muted-foreground">
              All systems operational
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card className="glass border-l-4 border-l-primary">
          <CardHeader>
            <CardTitle className="text-lg">Quick Start</CardTitle>
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

        <Card className="glass border-l-4 border-l-teal-500 dark:border-l-teal-400">
          <CardHeader>
            <CardTitle className="text-lg">Identity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Email</span>
              <span className="font-medium">{user?.email ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tenant ID</span>
              <span className="font-medium">{user?.tenant_id ? `${user.tenant_id.slice(0, 8)}...` : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Role</span>
              <span className="font-medium">{user?.tenant_role ?? '—'}</span>
            </div>
          </CardContent>
        </Card>

        <Card className="glass border-l-4 border-l-green-500 dark:border-l-green-400">
          <CardHeader>
            <CardTitle className="text-lg">Help & Support</CardTitle>
          </CardHeader>
          <CardContent className="flex items-start gap-3 text-sm text-muted-foreground">
            <LifeBuoy className="w-5 h-5 text-muted-foreground mt-0.5" />
            <div>
              Contact your platform administrator or support team for access requests, onboarding, and troubleshooting.
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="glass">
        <CardHeader>
          <CardTitle className="text-lg">Modules</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Installed modules will appear here as the foundation modules roll out. Today, AI Agent Management is available.
        </CardContent>
      </Card>
    </div>
  );
};
