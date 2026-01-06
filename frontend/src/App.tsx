import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { AnimatePresence } from 'framer-motion';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { ModuleLayout } from './components/layout/ModuleLayout';
import { RoleBasedRedirect } from './components/auth/RoleBasedRedirect';
import { LoginForm } from './components/auth/LoginForm';
import { RegisterForm } from './components/auth/RegisterForm';
import { ForgotPasswordForm } from './components/auth/ForgotPasswordForm';
import { ResetPasswordForm } from './components/auth/ResetPasswordForm';

// Lazy load pages for code splitting
const AgentListPage = lazy(() =>
  import('./modules/ai_agent_management/pages/AgentListPage').then((m) => ({
    default: m.AgentListPage,
  }))
);

const AgentDetailPage = lazy(() =>
  import('./modules/ai_agent_management/pages/AgentDetailPage').then((m) => ({
    default: m.AgentDetailPage,
  }))
);

const CreateAgentPage = lazy(() =>
  import('./modules/ai_agent_management/pages/CreateAgentPage').then((m) => ({
    default: m.CreateAgentPage,
  }))
);

const ExecutionMonitorPage = lazy(() =>
  import('./modules/ai_agent_management/pages/ExecutionMonitorPage').then((m) => ({
    default: m.ExecutionMonitorPage,
  }))
);

const ApprovalQueuePage = lazy(() =>
  import('./modules/ai_agent_management/pages/ApprovalQueuePage').then((m) => ({
    default: m.ApprovalQueuePage,
  }))
);

const PlatformDashboard = lazy(() =>
  import('./pages/platform/PlatformDashboard').then((m) => ({
    default: m.PlatformDashboard,
  }))
);

// Platform Management Dashboards
const OperationsDashboard = lazy(() =>
  import('./modules/platform_management/pages/OperationsDashboard').then((m) => ({
    default: m.OperationsDashboard,
  }))
);

const InfrastructureDashboard = lazy(() =>
  import('./modules/platform_management/pages/InfrastructureDashboard').then((m) => ({
    default: m.InfrastructureDashboard,
  }))
);

const BusinessDashboard = lazy(() =>
  import('./modules/platform_management/pages/BusinessDashboard').then((m) => ({
    default: m.BusinessDashboard,
  }))
);

const SecurityDashboard = lazy(() =>
  import('./modules/platform_management/pages/SecurityDashboard').then((m) => ({
    default: m.SecurityDashboard,
  }))
);

const TenantHealthDashboard = lazy(() =>
  import('./modules/platform_management/pages/TenantHealthDashboard').then((m) => ({
    default: m.TenantHealthDashboard,
  }))
);

const CostDashboard = lazy(() =>
  import('./modules/platform_management/pages/CostDashboard').then((m) => ({
    default: m.CostDashboard,
  }))
);

// Platform Management Pages
const SettingsPage = lazy(() =>
  import('./modules/platform_management/pages/SettingsPage').then((m) => ({
    default: m.SettingsPage,
  }))
);

const FeatureFlagsPage = lazy(() =>
  import('./modules/platform_management/pages/FeatureFlagsPage').then((m) => ({
    default: m.FeatureFlagsPage,
  }))
);

const HealthPage = lazy(() =>
  import('./modules/platform_management/pages/HealthPage').then((m) => ({
    default: m.HealthPage,
  }))
);

const AuditLogPage = lazy(() =>
  import('./modules/platform_management/pages/AuditLogPage').then((m) => ({
    default: m.AuditLogPage,
  }))
);

// Tenant Management Pages
const TenantListPage = lazy(() =>
  import('./modules/tenant_management/pages/TenantListPage').then((m) => ({
    default: m.TenantListPage,
  }))
);

const TenantDetailPage = lazy(() =>
  import('./modules/tenant_management/pages/TenantDetailPage').then((m) => ({
    default: m.TenantDetailPage,
  }))
);

const TenantCreatePage = lazy(() =>
  import('./modules/tenant_management/pages/TenantCreatePage').then((m) => ({
    default: m.TenantCreatePage,
  }))
);

// Security & Access Control Pages
const RolesPage = lazy(() =>
  import('./modules/security_access_control/pages/RolesPage').then((m) => ({
    default: m.RolesPage,
  }))
);

const PermissionsPage = lazy(() =>
  import('./modules/security_access_control/pages/PermissionsPage').then((m) => ({
    default: m.PermissionsPage,
  }))
);

const PermissionSetsPage = lazy(() =>
  import('./modules/security_access_control/pages/PermissionSetsPage').then((m) => ({
    default: m.PermissionSetsPage,
  }))
);

const SecurityAuditLogPage = lazy(() =>
  import('./modules/security_access_control/pages/AuditLogPage').then((m) => ({
    default: m.AuditLogPage,
  }))
);

// Tenant Dashboard (Home)
const TenantDashboard = lazy(() =>
  import('./pages/tenant/TenantDashboard').then((m) => ({
    default: m.TenantDashboard,
  }))
);

function LoadingFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-muted-foreground">Loading...</div>
    </div>
  );
}

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <>
      {/* Skip to main content link for accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-md"
      >
        Skip to main content
      </a>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          {/* Public routes */}
          <Route path="/login" element={<LoginForm />} />
          <Route path="/register" element={<RegisterForm />} />
          <Route path="/forgot-password" element={<ForgotPasswordForm />} />
          <Route path="/reset-password" element={<ResetPasswordForm />} />

          {/* Platform Management Dashboards (for platform owners) */}
          <Route
            path="/platform/dashboard"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <PlatformDashboard />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/platform/operations"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <OperationsDashboard />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/platform/infrastructure"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <InfrastructureDashboard />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/platform/business"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <BusinessDashboard />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/platform/security"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SecurityDashboard />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/platform/tenant-health"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <TenantHealthDashboard />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/platform/cost"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CostDashboard />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Protected routes with ModuleLayout */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RoleBasedRedirect />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Tenant Dashboard (tenant-scoped users) */}
          <Route
            path="/tenant/dashboard"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <TenantDashboard />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* AI Agent Management routes */}
          <Route
            path="/ai-agents"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AgentListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <CreateAgentPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AgentDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/:id/edit"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <div className="p-8">
                    <p>Edit page coming soon</p>
                  </div>
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/executions"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ExecutionMonitorPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/ai-agents/approvals"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <ApprovalQueuePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Platform Management routes */}
          <Route
            path="/platform/settings"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SettingsPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/platform/feature-flags"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <FeatureFlagsPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/platform/health"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <HealthPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/platform/audit-log"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <AuditLogPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Tenant Management routes */}
          <Route
            path="/tenant-management"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <TenantListPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/tenant-management/create"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <TenantCreatePage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/tenant-management/:id"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <TenantDetailPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* Security & Access Control routes */}
          <Route
            path="/security-access-control/roles"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <RolesPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/security-access-control/permissions"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <PermissionsPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/security-access-control/permission-sets"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <PermissionSetsPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/security-access-control/audit-logs"
            element={
              <ProtectedRoute>
                <ModuleLayout>
                  <SecurityAuditLogPage />
                </ModuleLayout>
              </ProtectedRoute>
            }
          />

          {/* 404 */}
          <Route path="*" element={<div className="p-8">Page not found</div>} />
        </Routes>
      </AnimatePresence>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<LoadingFallback />}>
        <AnimatedRoutes />
      </Suspense>
    </BrowserRouter>
  );
}
