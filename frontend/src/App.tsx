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

// ⚠️ ARCHITECTURAL NOTE: Platform Management UI removed
// Platform dashboards, settings, and feature flags MUST be in a separate
// platform frontend (saraise-platform/frontend/), not in the application frontend.
// The application frontend serves tenant-scoped users only.

// Tenant Management Pages (READ-ONLY - for display only)
// Tenant lifecycle operations MUST be performed via Control Plane APIs
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

          {/* ⚠️ ARCHITECTURAL ENFORCEMENT: Platform Management UI removed
              Platform dashboards and management UI MUST be in a separate
              platform frontend (saraise-platform/frontend/), not here.
              The application frontend serves tenant-scoped users only. */}

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

          {/* ⚠️ ARCHITECTURAL ENFORCEMENT: Platform Management routes removed
              Platform settings, feature flags, health, and audit logs MUST be
              in a separate platform frontend (saraise-platform/frontend/). */}

          {/* Tenant Management routes (READ-ONLY - for display only)
              ⚠️ Tenant lifecycle operations (create, update, delete) MUST be
              performed via Control Plane APIs (saraise-platform/saraise-control-plane/) */}
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
