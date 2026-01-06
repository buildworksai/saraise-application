/**
 * Protected Route Component
 * 
 * Wraps routes that require authentication.
 * Redirects to login if user is not authenticated.
 */
import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/auth-store';
import { authService } from '../../services/auth-service';

interface ProtectedRouteProps {
  children: ReactNode;
}

export const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  const { isAuthenticated, setUser, setLoading } = useAuthStore();
  const location = useLocation();

  useEffect(() => {
    // Verify session on mount (CRITICAL):
    // - Zustand persists auth state, but the server session cookie can expire or be cleared.
    // - We must treat the backend as source of truth and re-validate identity.
    const verifySession = async () => {
      setLoading(true);
      try {
        const user = await authService.getCurrentUser();
        setUser(user);
      } catch {
        // Session invalid, will redirect to login
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    void verifySession();
  }, [setUser, setLoading]);

  const { isLoading } = useAuthStore();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Redirect to login with return URL
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};
