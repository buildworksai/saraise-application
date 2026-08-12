/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-argument, @typescript-eslint/no-unused-vars, max-lines-per-function -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
/**
 * LoginForm Component Tests
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { LoginForm } from "./LoginForm";
import { ApiError } from "@/services/api-client";
import { authService } from "@/services/auth-service";
import { useAuthStore } from "@/stores/auth-store";

const authStoreSpies = vi.hoisted(() => ({
  setAuthenticated: vi.fn(),
  setUser: vi.fn(),
}));

// Mock dependencies
vi.mock("@/services/auth-service");
vi.mock("@/stores/auth-store", () => ({
  useAuthStore: {
    getState: vi.fn(() => ({
      setUser: authStoreSpies.setUser,
      setAuthenticated: authStoreSpies.setAuthenticated,
    })),
  },
}));

vi.mock("@/components/ui/logo-video", () => ({
  LogoVideo: ({
    autoplay,
    background,
    className,
    loop,
    showText = false,
    width,
  }: {
    autoplay?: boolean;
    background?: boolean;
    className?: string;
    loop?: boolean;
    showText?: boolean;
    width?: number | string;
  }) => (
    <div
      className={className}
      data-autoplay={String(Boolean(autoplay))}
      data-background={String(Boolean(background))}
      data-loop={String(Boolean(loop))}
      data-show-text={String(showText)}
      data-testid={background ? "desktop-logo-video" : "mobile-logo-video"}
      data-width={String(width ?? "")}
    >
      {showText ? "SARAISE" : null}
    </div>
  ),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("LoginForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderLogin = () =>
    render(
      <BrowserRouter>
        <LoginForm />
      </BrowserRouter>
    );

  it("should render login form", () => {
    renderLogin();

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toHaveAttribute("aria-invalid", "false");
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByText("AI Symphony Control Tower")).toBeInTheDocument();
    expect(screen.getByText("AI-native orchestration across ERP workflows")).toBeInTheDocument();
    expect(screen.getByText("SOC 2-ready controls and tenant isolation")).toBeInTheDocument();
    expect(screen.getByText("Trusted by global operators & disruptive MSMEs")).toBeInTheDocument();
    expect(screen.getByText("Use your work email to sign in.")).toHaveClass(
      "text-muted-foreground"
    );
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /forgot password/i })).toHaveAttribute(
      "href",
      "/forgot-password"
    );
    expect(screen.getByRole("link", { name: /create an organization/i })).toHaveAttribute(
      "href",
      "/register"
    );
    expect(screen.getByTestId("desktop-logo-video")).toHaveAttribute("data-background", "true");
    expect(screen.getByTestId("mobile-logo-video")).toHaveAttribute("data-show-text", "true");
    expect(screen.getByTestId("mobile-logo-video")).toHaveAttribute("data-width", "180");

    expect(screen.getByTestId("login-background-pattern")).toHaveClass(
      "bg-[radial-gradient(circle_at_2px_2px,rgba(255,255,255,0.3)_1px,transparent_0)]",
      "bg-[length:60px_60px]"
    );
    expect(
      screen.getByText("New to SARAISE? Don't have an access?", { exact: false }).textContent
    ).toContain("access? Create an Organization");
  });

  it("should show validation error for empty email", async () => {
    const user = userEvent.setup();
    renderLogin();

    const submitButton = screen.getByRole("button", { name: /sign in/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/email is required/i)).toHaveAttribute("role", "alert");
    });
    expect(screen.getByLabelText(/email address/i)).toHaveFocus();
    expect(authService.login).not.toHaveBeenCalled();
  });

  it("should show validation error for invalid email", async () => {
    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    await user.type(emailInput, "invalid-email");

    const submitButton = screen.getByRole("button", { name: /sign in/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/valid email address/i)).toBeInTheDocument();
    });
    expect(emailInput).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByText("Use your work email to sign in.")).not.toBeInTheDocument();
    expect(authService.login).not.toHaveBeenCalled();
  });

  it("should show validation error for empty password", async () => {
    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    await user.type(emailInput, "test@example.com");

    const submitButton = screen.getByRole("button", { name: /sign in/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/password is required/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/^password$/i)).toHaveFocus();
    expect(authService.login).not.toHaveBeenCalled();
  });

  it("validates touched fields during editing and keyboard navigation", async () => {
    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password$/i);

    await user.click(emailInput);
    await user.tab();
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    await user.type(emailInput, " user@example.com ");
    await waitFor(() => expect(screen.queryByText(/email is required/i)).not.toBeInTheDocument());
    await user.keyboard("{Enter}");
    await waitFor(() => expect(passwordInput).toHaveFocus());

    await user.tab();
    expect(await screen.findByText(/password is required/i)).toBeInTheDocument();
    await user.type(passwordInput, "secret");
    await waitFor(() =>
      expect(screen.queryByText(/password is required/i)).not.toBeInTheDocument()
    );
  });

  it("does not show field validation while fields are edited before first blur", async () => {
    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);

    await user.type(emailInput, "invalid-email");
    expect(screen.queryByText(/valid email address/i)).not.toBeInTheDocument();
    expect(emailInput).toHaveAttribute("aria-invalid", "false");
    expect(screen.getByText("Use your work email to sign in.")).toBeInTheDocument();
    fireEvent.change(emailInput, { target: { value: "bad test@example.com" } });
    expect(emailInput).toHaveAttribute("aria-invalid", "false");
    expect(screen.getByText("Use your work email to sign in.")).toBeInTheDocument();
    await user.tab();
    expect(await screen.findByText(/valid email address/i)).toBeInTheDocument();

    await user.clear(emailInput);
    await user.type(emailInput, "test@example.com trailing");
    expect(await screen.findByText(/valid email address/i)).toBeInTheDocument();
  });

  it("does not show password validation while password is edited before first blur", async () => {
    const user = userEvent.setup();
    renderLogin();

    const passwordInput = screen.getByLabelText(/^password$/i);

    await user.type(passwordInput, "secret");
    await user.clear(passwordInput);
    expect(screen.queryByText(/password is required/i)).not.toBeInTheDocument();
    expect(passwordInput).toHaveAttribute("aria-invalid", "false");
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
    await user.tab();
    expect(await screen.findByText(/password is required/i)).toBeInTheDocument();
  });

  it("treats whitespace-only email as missing and trims email before validation", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockResolvedValueOnce({
      user: {
        id: "1",
        email: "padded@example.com",
        username: "padded",
        is_staff: false,
        is_superuser: false,
        tenant_id: "tenant-123",
        platform_role: null,
        tenant_role: "tenant_user",
      },
      session_id: "session-123",
    });
    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password$/i);

    act(() => {
      fireEvent.change(emailInput, { target: { value: "   " } });
    });
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    expect(authService.login).not.toHaveBeenCalled();

    fireEvent.change(emailInput, { target: { value: " padded@example.com " } });
    await user.type(passwordInput, "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(authService.login).toHaveBeenCalledWith({
        email: "padded@example.com",
        password: "password123",
      });
    });
    expect(authService.login).toHaveBeenCalledTimes(1);
    expect(authService.login).not.toHaveBeenCalledWith({
      email: " padded@example.com ",
      password: "password123",
    });
  });

  it("keeps focus guards null-safe when target elements are unavailable", async () => {
    const user = userEvent.setup();
    const getElementById = document.getElementById.bind(document);
    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password$/i);
    const getElementByIdSpy = vi.spyOn(document, "getElementById");

    getElementByIdSpy.mockImplementation((id) =>
      id === emailInput.id ? null : getElementById(id)
    );
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/email is required/i)).toBeInTheDocument();

    getElementByIdSpy.mockImplementation((id) =>
      id === passwordInput.id ? null : getElementById(id)
    );
    fireEvent.change(emailInput, { target: { value: "test@example.com" } });
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/password is required/i)).toBeInTheDocument();

    getElementByIdSpy.mockRestore();
  });

  it("should submit form with valid credentials", async () => {
    const user = userEvent.setup();
    const mockUser = {
      id: "1",
      email: "test@example.com",
      username: "testuser",
      is_staff: false,
      is_superuser: false,
      tenant_id: "tenant-123",
      platform_role: null,
      tenant_role: "tenant_admin",
    };

    vi.mocked(authService.login).mockResolvedValueOnce({
      user: mockUser,
      session_id: "session-123",
    });

    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password$/i);
    const submitButton = screen.getByRole("button", { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: " test@example.com " } });
    await user.type(passwordInput, "password123");
    await user.click(submitButton);

    await waitFor(() => {
      expect(authService.login).toHaveBeenCalledWith({
        email: "test@example.com",
        password: "password123",
      });
    });
    expect(authService.login).toHaveBeenCalledTimes(1);
    expect(authService.login).not.toHaveBeenCalledWith({
      email: " test@example.com ",
      password: "password123",
    });
    expect(authStoreSpies.setUser).toHaveBeenCalledWith(mockUser);
    expect(authStoreSpies.setAuthenticated).toHaveBeenCalledWith(true);
    expect(mockNavigate).toHaveBeenCalledWith("/tenant/dashboard", { replace: true });
  });

  it.each([
    [{ platform_role: "platform_owner" as const, tenant_role: "tenant_admin" as const }, "/"],
    [{ platform_role: null, tenant_role: null }, "/"],
  ])("routes non-tenant login result %# through role redirect", async (roles, destination) => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockResolvedValueOnce({
      user: {
        id: "1",
        email: "owner@example.com",
        username: "owner",
        is_staff: false,
        is_superuser: false,
        tenant_id: "tenant-123",
        ...roles,
      },
      session_id: "session-123",
    });
    renderLogin();

    await user.type(screen.getByLabelText(/email address/i), "owner@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(destination, { replace: true });
    });
  });

  it("should display safe authentication copy on credential failure", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockRejectedValueOnce(
      new ApiError("Invalid credentials", 401, { error: "Invalid credentials" })
    );

    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password$/i);
    const submitButton = screen.getByRole("button", { name: /sign in/i });

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "wrongpassword");
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText("Invalid email or password")).toHaveAttribute(
        "aria-live",
        "assertive"
      );
    });
    await waitFor(() => expect(passwordInput).toHaveFocus());
  });

  it("uses the same safe authentication copy for malformed credential requests", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockRejectedValueOnce(new ApiError("Bad request", 400));

    renderLogin();

    await user.type(screen.getByLabelText(/email address/i), "test@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
  });

  it("hides raw server errors from the login failure alert", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockRejectedValueOnce(
      new ApiError("Internal Server Error", 500, "Internal Server Error")
    );

    renderLogin();

    await user.type(screen.getByLabelText(/email address/i), "test@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Sign-in service is temporarily unavailable. Try again later.");
    expect(alert).not.toHaveTextContent("Internal Server Error");
  });

  it("does not crash when the password field is missing before post-failure focus", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockRejectedValueOnce(new ApiError("Forbidden", 403));
    const getElementById = document.getElementById.bind(document);
    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password$/i);
    const getElementByIdSpy = vi
      .spyOn(document, "getElementById")
      .mockImplementation((id) => (id === passwordInput.id ? null : getElementById(id)));

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "wrongpassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument();
    getElementByIdSpy.mockRestore();
  });

  it("uses the generic authentication error for non-error failures", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockRejectedValueOnce("denied");
    renderLogin();

    await user.type(screen.getByLabelText(/email address/i), "test@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to sign in right now. Try again later."
    );
  });

  it("does not trust status-shaped non-ApiError failures", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockRejectedValueOnce({ status: 500, message: "Gateway down" });
    renderLogin();

    await user.type(screen.getByLabelText(/email address/i), "test@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to sign in right now. Try again later."
    );
  });

  it("uses generic authentication copy for non-auth ApiError responses", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockRejectedValueOnce(new ApiError("Teapot", 418));
    renderLogin();

    await user.type(screen.getByLabelText(/email address/i), "test@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to sign in right now. Try again later."
    );
  });

  it("should show loading state during submission", async () => {
    const user = userEvent.setup();
    let resolveLogin: (value: any) => void;
    const loginPromise = new Promise((resolve) => {
      resolveLogin = resolve;
    });

    vi.mocked(authService.login).mockReturnValueOnce(loginPromise as any);

    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password$/i);
    const submitButton = screen.getByRole("button", { name: /sign in/i });

    await user.type(emailInput, "test@example.com");
    await user.type(passwordInput, "password123");
    await user.click(submitButton);

    // Button should be disabled during loading
    await waitFor(() => {
      expect(submitButton).toBeDisabled();
    });

    // Resolve the promise
    await act(async () => {
      resolveLogin!({
        user: {
          id: "1",
          email: "test@example.com",
          username: "test",
          is_staff: false,
          is_superuser: false,
          tenant_id: "tenant-123",
        },
        session_id: "session-123",
      });
      await loginPromise;
    });
    await waitFor(() => {
      expect(submitButton).toBeEnabled();
    });
  });

  it("submits with Enter from the password field when credentials are valid", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.login).mockResolvedValueOnce({
      user: {
        id: "1",
        email: "enter@example.com",
        username: "enter",
        is_staff: false,
        is_superuser: false,
        tenant_id: "tenant-123",
        platform_role: null,
        tenant_role: "tenant_user",
      },
      session_id: "session-123",
    });
    renderLogin();

    await user.type(screen.getByLabelText(/email address/i), "enter@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "password123");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(authService.login).toHaveBeenCalledTimes(1));
  });

  it("uses Enter on the email field only as valid-email keyboard navigation", async () => {
    const user = userEvent.setup();
    renderLogin();

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password$/i);

    act(() => {
      fireEvent.keyDown(emailInput, { key: "Escape" });
    });
    expect(passwordInput).not.toHaveFocus();

    act(() => {
      fireEvent.change(emailInput, { target: { value: "   " } });
    });
    act(() => {
      fireEvent.keyDown(emailInput, { key: "Enter" });
    });
    expect(passwordInput).not.toHaveFocus();

    act(() => {
      fireEvent.change(emailInput, { target: { value: "invalid-before-blur" } });
    });
    act(() => {
      fireEvent.keyDown(emailInput, { key: "Enter" });
    });
    expect(passwordInput).not.toHaveFocus();

    act(() => {
      fireEvent.change(emailInput, { target: { value: "invalid-email" } });
      fireEvent.blur(emailInput);
    });
    expect(await screen.findByText(/valid email address/i)).toBeInTheDocument();
    act(() => {
      emailInput.focus();
      fireEvent.keyDown(emailInput, { key: "Enter" });
    });
    expect(passwordInput).not.toHaveFocus();

    act(() => {
      fireEvent.change(emailInput, { target: { value: "valid@example.com" } });
    });
    act(() => {
      fireEvent.keyDown(emailInput, { key: "Enter" });
    });
    expect(passwordInput).toHaveFocus();

    act(() => {
      emailInput.focus();
    });
    const getElementById = document.getElementById.bind(document);
    const getElementByIdSpy = vi
      .spyOn(document, "getElementById")
      .mockImplementation((id) => (id === passwordInput.id ? null : getElementById(id)));
    act(() => {
      fireEvent.keyDown(emailInput, { key: "Enter" });
    });
    getElementByIdSpy.mockRestore();
  });
});
