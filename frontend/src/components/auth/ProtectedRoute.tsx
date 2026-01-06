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
  const { isAuthenticated, user, setUser, setLoading } = useAuthStore();
  const location = useLocation();

  useEffect(() => {
    // Verify session on mount (CRITICAL):
    // - Zustand persists auth state, but the server session cookie can expire or be cleared.
    // - We must treat the backend as source of truth and re-validate identity.
    // - Only verify if we don't have a user AND we're not authenticated (avoid unnecessary calls after login)
    const verifySession = async () => {
      // Skip verification if we already have a user AND are authenticated
      // This prevents race conditions where getCurrentUser() might fail temporarily after login
      if (user && isAuthenticated) {
        return;
      }

      setLoading(true);
      try {
        const currentUser = await authService.getCurrentUser();
        setUser(currentUser);
      } catch {
        // Session invalid, will redirect to login
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    void verifySession();
  }, [setUser, setLoading, user, isAuthenticated]);

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
