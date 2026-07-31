/**
 * Protected Route Component
 *
 * Wraps routes that require authentication.
 * Redirects to login if user is not authenticated.
 */
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../../stores/auth-store";
import { authService } from "../../services/auth-service";
import { isProtectedContentBlocked } from "./protected-route-utils";

interface ProtectedRouteProps {
  children: ReactNode;
}

export const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  const { isAuthenticated, isLoading, setUser, setLoading } = useAuthStore();
  const location = useLocation();
  const [isSessionVerified, setIsSessionVerified] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const verifySession = async () => {
      if (!isAuthenticated) {
        setIsSessionVerified(false);
        return;
      }

      setIsSessionVerified(false);
      setLoading(true);
      try {
        const currentUser = await authService.getCurrentUser();
        if (!cancelled) setUser(currentUser);
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) {
          setIsSessionVerified(true);
          setLoading(false);
        }
      }
    };

    void verifySession();
    return () => {
      cancelled = true;
    };
  }, [setUser, setLoading, isAuthenticated, location.pathname]);

  if (isProtectedContentBlocked(isAuthenticated, isLoading, isSessionVerified)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};
