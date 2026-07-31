/* eslint-disable max-lines-per-function -- persistence fallback tests are intentionally cohesive. */
/**
 * Auth Store Tests
 *
 * Tests for authentication store (Zustand).
 */

import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { createAuthActions, createAuthMemoryStorage, useAuthStore } from "./auth-store";
import type { User } from "./auth-store";

const mockUser: User = {
  id: "1",
  email: "test@example.com",
  username: "testuser",
  is_staff: false,
  is_superuser: false,
  tenant_id: "tenant-123",
  platform_role: null,
  tenant_role: "tenant_admin",
};

function makeStorage(initialValues: Record<string, string> = {}): Storage {
  const values = new Map(Object.entries(initialValues));
  return {
    get length() {
      return values.size;
    },
    clear: vi.fn(() => values.clear()),
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    key: vi.fn((index: number) => Array.from(values.keys())[index] ?? null),
    removeItem: vi.fn((key: string) => {
      values.delete(key);
    }),
    setItem: vi.fn((key: string, value: string) => {
      values.set(key, value);
    }),
  };
}

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("should initialize with null user and not authenticated", () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(false);
  });

  it("should expose the initial state before any test reset runs", async () => {
    vi.resetModules();
    const { useAuthStore: isolatedAuthStore } = await import("./auth-store");

    expect(isolatedAuthStore.getState()).toMatchObject({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it("should login user and set authenticated", () => {
    useAuthStore.getState().login(mockUser);

    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
  });

  it("should logout user and clear authenticated", () => {
    useAuthStore.getState().login(mockUser);
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it("should set user and update authenticated status", () => {
    useAuthStore.getState().setUser(mockUser);

    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
  });

  it("should set user to null and clear authenticated", () => {
    useAuthStore.getState().setUser(mockUser);
    useAuthStore.getState().setUser(null);

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it("should set loading state", () => {
    useAuthStore.getState().setLoading(true);
    expect(useAuthStore.getState().isLoading).toBe(true);

    useAuthStore.getState().setLoading(false);
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it("should set authenticated state directly", () => {
    useAuthStore.getState().setAuthenticated(true);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);

    useAuthStore.getState().setAuthenticated(false);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("should provide working in-memory auth storage semantics", async () => {
    const storage = createAuthMemoryStorage();

    expect(await storage.getItem("auth-storage")).toBeNull();

    await storage.setItem("auth-storage", "first-session");
    expect(await storage.getItem("auth-storage")).toBe("first-session");

    await storage.setItem("auth-storage", "rotated-session");
    expect(await storage.getItem("auth-storage")).toBe("rotated-session");

    await storage.removeItem("auth-storage");
    expect(await storage.getItem("auth-storage")).toBeNull();
  });

  it("should create action handlers that emit the expected state patches", () => {
    const setState = vi.fn();
    const actions = createAuthActions(setState);

    actions.login(mockUser);
    actions.logout();
    actions.setUser(mockUser);
    actions.setUser(null);
    actions.setAuthenticated(true);
    actions.setAuthenticated(false);
    actions.setLoading(true);
    actions.setLoading(false);

    expect(setState).toHaveBeenNthCalledWith(1, {
      user: mockUser,
      isAuthenticated: true,
    });
    expect(setState).toHaveBeenNthCalledWith(2, {
      user: null,
      isAuthenticated: false,
    });
    expect(setState).toHaveBeenNthCalledWith(3, {
      user: mockUser,
      isAuthenticated: true,
    });
    expect(setState).toHaveBeenNthCalledWith(4, {
      user: null,
      isAuthenticated: false,
    });
    expect(setState).toHaveBeenNthCalledWith(5, { isAuthenticated: true });
    expect(setState).toHaveBeenNthCalledWith(6, { isAuthenticated: false });
    expect(setState).toHaveBeenNthCalledWith(7, { isLoading: true });
    expect(setState).toHaveBeenNthCalledWith(8, { isLoading: false });
  });

  it("should persist only durable auth state and exclude transient loading state", () => {
    const storage = makeStorage();
    vi.resetModules();
    vi.stubGlobal("localStorage", storage);

    return import("./auth-store").then(({ useAuthStore: isolatedAuthStore }) => {
      isolatedAuthStore.getState().setLoading(true);
      isolatedAuthStore.getState().login(mockUser);

      const rawPersistedState = storage.getItem("auth-storage");
      expect(rawPersistedState).not.toBeNull();
      const persistedState = JSON.parse(rawPersistedState ?? "{}") as {
        state?: Record<string, unknown>;
      };

      expect(Object.keys(persistedState.state ?? {}).sort()).toEqual(["isAuthenticated", "user"]);
      expect(persistedState.state).toMatchObject({
        user: mockUser,
        isAuthenticated: true,
      });
      expect(persistedState.state).not.toHaveProperty("isLoading");
    });
  });

  it("should fall back to in-memory storage when localStorage is unavailable", async () => {
    const unavailableStorage = {
      getItem: vi.fn(() => {
        throw new Error("localStorage unavailable");
      }),
      setItem: vi.fn(() => {
        throw new Error("localStorage unavailable");
      }),
      removeItem: vi.fn(() => {
        throw new Error("localStorage unavailable");
      }),
      clear: vi.fn(),
      key: vi.fn(),
      length: 0,
    } satisfies Storage;

    vi.resetModules();
    vi.stubGlobal("localStorage", unavailableStorage);
    const { useAuthStore: isolatedAuthStore } = await import("./auth-store");

    isolatedAuthStore.getState().login(mockUser);

    expect(unavailableStorage.setItem).toHaveBeenCalledWith(
      "auth-storage:probe",
      "auth-storage:probe"
    );
    expect(isolatedAuthStore.getState().user).toEqual(mockUser);
    expect(isolatedAuthStore.getState().isAuthenticated).toBe(true);
  });
});
