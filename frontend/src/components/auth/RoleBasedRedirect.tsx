/**
 * SPDX-License-Identifier: Apache-2.0
 * 
 * Role-based redirect component
 * Redirects users to appropriate dashboard based on their role
 */
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';

export const RoleBasedRedirect = () => {
  const { user } = useAuthStore();

  if (user?.platform_role === 'platform_owner') {
    return <Navigate to="/platform/dashboard" replace />;
  }

  if (user?.tenant_role) {
    return <Navigate to="/tenant/dashboard" replace />;
  }

  // Default fallback
  return <Navigate to="/ai-agents" replace />;
};

