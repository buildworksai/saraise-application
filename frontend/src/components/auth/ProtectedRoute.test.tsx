/* eslint-disable max-lines-per-function, @typescript-eslint/require-await -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
/**
 * ProtectedRoute Component Tests
 *
 * Tests for authentication-protected route component.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ProtectedRoute } from "./ProtectedRoute";
import { isProtectedContentBlocked } from "./protected-route-utils";
import { useAuthStore } from "../../stores/auth-store";
import { authService } from "../../services/auth-service";

// Mock auth service
vi.mock("../../services/auth-service", () => ({
  authService: {
    getCurrentUser: vi.fn(),
  },
}));

const mockUser = {
  id: "1",
  email: "test@example.com",
  username: "test",
  is_staff: false,
  is_superuser: false,
  tenant_id: null,
  platform_role: null,
  tenant_role: null,
};

function NavigationControl() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/tenant/dashboard")}>Go dashboard</button>;
}

function LoginPage() {
  const location = useLocation();
  const state = location.state as { from?: { pathname?: string } } | null;
  return (
    <div>
      <span>Login Page</span>
      <span>Return to {state?.from?.pathname ?? "missing"}</span>
    </div>
  );
}

const renderProtectedRoute = (initialEntry = "/protected") =>
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <NavigationControl />
      <Routes>
        <Route
          path="/protected"
          element={
            <ProtectedRoute>
              <div>Protected Content</div>
            </ProtectedRoute>
          }
        />
        <Route
          path="/tenant/dashboard"
          element={<ProtectedRoute>Protected Content</ProtectedRoute>}
        />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </MemoryRouter>
  );

describe("ProtectedRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset store state
    act(() => {
      useAuthStore.getState().logout();
      useAuthStore.getState().setLoading(false);
    });
  });

  it("should render children after authenticated session is verified", async () => {
    vi.mocked(authService.getCurrentUser).mockResolvedValueOnce(mockUser);

    act(() => {
      useAuthStore.getState().login(mockUser);
    });

    renderProtectedRoute();

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Protected Content")).toBeInTheDocument());
    expect(authService.getCurrentUser).toHaveBeenCalledOnce();
  });

  it("should redirect to login when not authenticated", () => {
    act(() => {
      useAuthStore.getState().logout();
    });

    renderProtectedRoute();

    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    expect(screen.getByText("Login Page")).toBeInTheDocument();
    expect(screen.getByText("Return to /protected")).toBeInTheDocument();
  });

  it("should show loading when verifying session without relying on pre-set loading state", () => {
    vi.mocked(authService.getCurrentUser).mockReturnValue(
      new Promise<never>((resolve) => {
        void resolve;
      })
    );

    act(() => {
      useAuthStore.getState().login({
        ...mockUser,
      });
    });

    renderProtectedRoute();

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    expect(useAuthStore.getState().isLoading).toBe(true);
  });

  it("should revalidate the session when the protected route path changes", async () => {
    vi.mocked(authService.getCurrentUser)
      .mockResolvedValueOnce(mockUser)
      .mockResolvedValueOnce({ ...mockUser, username: "refreshed" });

    act(() => {
      useAuthStore.getState().login(mockUser);
    });

    renderProtectedRoute();

    await waitFor(() => expect(screen.getByText("Protected Content")).toBeInTheDocument());
    expect(authService.getCurrentUser).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /go dashboard/i }));

    await waitFor(() => expect(authService.getCurrentUser).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      expect(useAuthStore.getState().user?.username).toBe("refreshed");
    });
  });

  it("should ignore a stale verification result after route change cancellation", async () => {
    let resolveStaleSession: (user: typeof mockUser) => void = () => undefined;
    const staleSession = new Promise<typeof mockUser>((resolve) => {
      resolveStaleSession = resolve;
    });
    vi.mocked(authService.getCurrentUser)
      .mockReturnValueOnce(staleSession)
      .mockResolvedValueOnce({ ...mockUser, username: "refreshed" });

    act(() => {
      useAuthStore.getState().login(mockUser);
    });

    renderProtectedRoute();

    await waitFor(() => expect(authService.getCurrentUser).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /go dashboard/i }));

    await waitFor(() => expect(authService.getCurrentUser).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      expect(useAuthStore.getState().user?.username).toBe("refreshed");
    });

    await act(async () => {
      resolveStaleSession({ ...mockUser, username: "stale" });
      await staleSession;
    });

    expect(useAuthStore.getState().user?.username).toBe("refreshed");
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it("should keep loading when a stale verification resolves while the replacement is pending", async () => {
    let resolveStaleSession: (user: typeof mockUser) => void = () => undefined;
    const staleSession = new Promise<typeof mockUser>((resolve) => {
      resolveStaleSession = resolve;
    });
    const replacementSession = new Promise<typeof mockUser>(() => undefined);
    vi.mocked(authService.getCurrentUser)
      .mockReturnValueOnce(staleSession)
      .mockReturnValueOnce(replacementSession);

    act(() => {
      useAuthStore.getState().login(mockUser);
    });

    renderProtectedRoute();

    await waitFor(() => expect(authService.getCurrentUser).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /go dashboard/i }));

    await waitFor(() => expect(authService.getCurrentUser).toHaveBeenCalledTimes(2));

    await act(async () => {
      resolveStaleSession({ ...mockUser, username: "stale" });
      await staleSession;
    });

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    expect(useAuthStore.getState().isLoading).toBe(true);
  });

  it("should not call the identity endpoint when no auth state exists", () => {
    act(() => {
      useAuthStore.getState().logout();
    });

    renderProtectedRoute();

    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    expect(authService.getCurrentUser).not.toHaveBeenCalled();
  });

  it("should clear stale persisted auth before rendering protected content", async () => {
    const staleUser = {
      id: "1",
      email: "stale@example.com",
      username: "stale",
      is_staff: false,
      is_superuser: false,
      tenant_id: null,
      platform_role: null,
      tenant_role: null,
    };

    vi.mocked(authService.getCurrentUser).mockRejectedValueOnce(new Error("Forbidden"));

    act(() => {
      useAuthStore.getState().login(staleUser);
    });

    renderProtectedRoute("/tenant/dashboard");

    expect(screen.getByText("Loading...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
      expect(screen.getByText("Login Page")).toBeInTheDocument();
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });
  });

  it("should ignore a rejected stale verification after route cancellation", async () => {
    let rejectStaleSession: (error: Error) => void = () => undefined;
    const staleSession = new Promise<typeof mockUser>((_resolve, reject) => {
      rejectStaleSession = reject;
    });
    vi.mocked(authService.getCurrentUser)
      .mockReturnValueOnce(staleSession)
      .mockResolvedValueOnce({ ...mockUser, username: "refreshed" });

    act(() => {
      useAuthStore.getState().login(mockUser);
    });

    renderProtectedRoute();

    await waitFor(() => expect(authService.getCurrentUser).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /go dashboard/i }));

    await waitFor(() => expect(authService.getCurrentUser).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      expect(useAuthStore.getState().user?.username).toBe("refreshed");
    });

    await act(async () => {
      rejectStaleSession(new Error("stale rejection"));
      await expect(staleSession).rejects.toThrow("stale rejection");
    });

    expect(useAuthStore.getState().user?.username).toBe("refreshed");
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().isLoading).toBe(false);
  });
});

describe("isProtectedContentBlocked", () => {
  it.each([
    {
      isAuthenticated: true,
      isLoading: true,
      isSessionVerified: true,
      expected: true,
    },
    {
      isAuthenticated: true,
      isLoading: false,
      isSessionVerified: false,
      expected: true,
    },
    {
      isAuthenticated: true,
      isLoading: false,
      isSessionVerified: true,
      expected: false,
    },
    {
      isAuthenticated: false,
      isLoading: true,
      isSessionVerified: false,
      expected: false,
    },
  ])(
    "returns $expected for auth=$isAuthenticated loading=$isLoading verified=$isSessionVerified",
    ({ isAuthenticated, isLoading, isSessionVerified, expected }) => {
      expect(isProtectedContentBlocked(isAuthenticated, isLoading, isSessionVerified)).toBe(
        expected
      );
    }
  );
});
