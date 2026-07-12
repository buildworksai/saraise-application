/**
 * Authentication Store (Zustand)
 *
 * Manages authentication state and session management.
 * Sessions establish identity only - no authorization state cached.
 */
import { create } from 'zustand';

export interface User {
  id: string;
  email: string;
  username: string;
  is_staff: boolean;
  is_superuser: boolean;
  tenant_id: string | null;
  platform_role: string | null;
  tenant_role: string | null;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (user: User) => void;
  logout: () => void;
  setUser: (user: User | null) => void;
  setLoading: (loading: boolean) => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: (user) => set({ user, isAuthenticated: true }),
      logout: () => set({ user: null, isAuthenticated: false }),
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      setLoading: (isLoading) => set({ isLoading }),
}));
