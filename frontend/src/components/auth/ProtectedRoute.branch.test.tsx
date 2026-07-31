/**
 * ProtectedRoute branch tests with router/store boundaries mocked directly.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProtectedRoute } from "./ProtectedRoute";
import { authService } from "../../services/auth-service";

interface ProtectedRouteAuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  setUser: ReturnType<typeof vi.fn>;
  setLoading: ReturnType<typeof vi.fn>;
}

let protectedRouteAuthState: ProtectedRouteAuthState;
const mockLocation = {
  pathname: "/tenant/reports",
  search: "",
  hash: "",
  state: null,
  key: "branch-test",
};

vi.mock("../../stores/auth-store", () => ({
  useAuthStore: () => protectedRouteAuthState,
}));

vi.mock("../../services/auth-service", () => ({
  authService: {
    getCurrentUser: vi.fn(),
  },
}));

vi.mock("react-router-dom", () => ({
  Navigate: ({ to, state, replace }: { to: string; state: unknown; replace: boolean }) => (
    <div data-testid="navigate" data-replace={String(replace)} data-state={JSON.stringify(state)}>
      {to}
    </div>
  ),
  useLocation: () => mockLocation,
}));

function authState({
  isAuthenticated,
  isLoading,
}: {
  isAuthenticated: boolean;
  isLoading: boolean;
}): ProtectedRouteAuthState {
  return {
    isAuthenticated,
    isLoading,
    setUser: vi.fn(),
    setLoading: vi.fn(),
  };
}

describe("ProtectedRoute branch rendering", () => {
  it("should render a replace redirect with the current location when unauthenticated", () => {
    protectedRouteAuthState = authState({
      isAuthenticated: false,
      isLoading: false,
    });

    render(
      <ProtectedRoute>
        <div>Protected Content</div>
      </ProtectedRoute>
    );

    const redirect = screen.getByTestId("navigate");
    expect(redirect).toHaveTextContent("/login");
    expect(redirect).toHaveAttribute("data-replace", "true");
    expect(redirect).toHaveAttribute(
      "data-state",
      JSON.stringify({
        from: mockLocation,
      })
    );
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
  });

  it("should hold protected content while authenticated state is loading", () => {
    vi.mocked(authService.getCurrentUser).mockReturnValueOnce(new Promise<never>(() => undefined));
    protectedRouteAuthState = authState({
      isAuthenticated: true,
      isLoading: true,
    });

    render(
      <ProtectedRoute>
        <div>Protected Content</div>
      </ProtectedRoute>
    );

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    expect(screen.queryByTestId("navigate")).not.toBeInTheDocument();
  });
});
