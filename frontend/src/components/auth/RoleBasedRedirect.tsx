/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Role-based redirect component
 *
 * ⚠️ ARCHITECTURAL ENFORCEMENT: Application repo is tenant-only.
 * Platform management UI MUST be in saraise-platform/frontend/.
 */
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';

export const RoleBasedRedirect = () => {
  const { user } = useAuthStore();

  // Application repo is tenant-only - always redirect to tenant dashboard
  if (user?.tenant_role) {
    return <Navigate to="/tenant/dashboard" replace />;
  }

  // Default fallback
  return <Navigate to="/ai-agents" replace />;
};
