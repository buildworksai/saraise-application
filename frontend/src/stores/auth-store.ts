/**
 * Authentication Store (Zustand)
 *
 * Manages authentication state and session management.
 * Sessions establish identity only - no authorization state cached.
 */
import { create } from "zustand";
import { persist, createJSONStorage, type StateStorage } from "zustand/middleware";

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
  setAuthenticated: (authenticated: boolean) => void;
  setLoading: (loading: boolean) => void;
}

type PersistedAuthState = Pick<AuthState, "user" | "isAuthenticated">;
type AuthActions = Pick<
  AuthState,
  "login" | "logout" | "setUser" | "setAuthenticated" | "setLoading"
>;
type AuthStatePatch = Partial<Pick<AuthState, "user" | "isAuthenticated" | "isLoading">>;
type AuthSet = (state: AuthStatePatch) => void;

export const createAuthMemoryStorage = (): StateStorage => {
  const values = new Map<string, string>();
  return {
    getItem: (name) => values.get(name) ?? null,
    setItem: (name, value) => {
      values.set(name, value);
    },
    removeItem: (name) => {
      values.delete(name);
    },
  };
};

const authStorage = (() => {
  const fallback = createAuthMemoryStorage();
  return createJSONStorage<PersistedAuthState>(() => {
    try {
      const storage = globalThis.localStorage;
      const probeKey = "auth-storage:probe";
      storage.setItem(probeKey, probeKey);
      storage.removeItem(probeKey);
      return storage;
    } catch {
      return fallback;
    }
  });
})();

export const createAuthActions = (set: AuthSet): AuthActions => ({
  login: (user) => set({ user, isAuthenticated: true }),
  logout: () => set({ user: null, isAuthenticated: false }),
  setUser: (user) => set({ user, isAuthenticated: !!user }),
  setAuthenticated: (isAuthenticated) => set({ isAuthenticated }),
  setLoading: (isLoading) => set({ isLoading }),
});

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      ...createAuthActions(set),
    }),
    {
      name: "auth-storage",
      storage: authStorage,
      partialize: (state) => ({ user: state.user, isAuthenticated: state.isAuthenticated }),
    }
  )
);
