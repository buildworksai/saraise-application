import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as RouterDom from "react-router-dom";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "../stores/auth-store";
import { useAuthStore } from "../stores/auth-store";
import { authService } from "../services/auth-service";
import { RoleBasedRedirect } from "../components/auth/RoleBasedRedirect";
import { ModuleLayout } from "../components/layout/ModuleLayout";
import { ThemeProvider } from "../lib/theme-provider";
import { LoginPage } from "./auth/LoginPage";
import { TenantDashboard } from "./tenant/TenantDashboard";

vi.mock("../components/layout/Navigation", () => ({
  Navigation: () => <nav aria-label="tenant navigation">Tenant navigation</nav>,
}));

const navigateSpy = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof RouterDom>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateSpy,
  };
});

const tenantAdmin: User = {
  id: "user-1",
  email: "operator@saraise.ai",
  username: "operator",
  is_staff: false,
  is_superuser: false,
  tenant_id: "tenant-123456789",
  platform_role: null,
  tenant_role: "tenant_admin",
};

function setAuth(user: User | null = tenantAdmin) {
  act(() => {
    useAuthStore.setState({
      user,
      isAuthenticated: Boolean(user),
      isLoading: false,
    });
  });
}

function getLoginFields() {
  const email = document.querySelector<HTMLInputElement>('input[name="email"]');
  const password = document.querySelector<HTMLInputElement>('input[name="password"]');
  const mfa = document.querySelector<HTMLInputElement>('input[name="mfa_token"]');
  if (!email || !password) throw new Error("Login fields did not render.");
  return { email, password, mfa };
}

function renderModuleLayout() {
  return render(
    <ThemeProvider defaultTheme="system" storageKey="saraise-app-shell-test-theme">
      <MemoryRouter>
        <ModuleLayout>
          <section>Workspace content</section>
        </ModuleLayout>
      </MemoryRouter>
    </ThemeProvider>
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    navigateSpy.mockClear();
    setAuth(null);
  });

  it("requires MFA after a credential challenge and submits the governed token on retry", async () => {
    const person = userEvent.setup();
    const loginSpy = vi
      .spyOn(authService, "login")
      .mockRejectedValueOnce({ status: 401, message: "MFA challenge" })
      .mockResolvedValueOnce({ user: tenantAdmin, session_id: "session-1" });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    const fields = getLoginFields();
    await person.type(fields.email, "operator@saraise.ai");
    await person.type(fields.password, "correct-password");
    await person.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("MFA token required")).toBeInTheDocument();
    const mfa = document.querySelector<HTMLInputElement>('input[name="mfa_token"]');
    if (!mfa) throw new Error("MFA field did not render.");
    await person.type(mfa, "123456");
    await person.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(loginSpy).toHaveBeenLastCalledWith({
        email: "operator@saraise.ai",
        password: "correct-password", // pragma: allowlist secret
        mfa_token: "123456",
      });
    });
    expect(useAuthStore.getState().user).toEqual(tenantAdmin);
    expect(navigateSpy).toHaveBeenCalledWith("/");
  });

  it("surfaces validation and unexpected authentication failures without mutating session state", async () => {
    const person = userEvent.setup();
    vi.spyOn(authService, "login").mockRejectedValue(new Error("network down"));

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    await person.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Invalid email address")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();

    const fields = getLoginFields();
    await person.type(fields.email, "operator@saraise.ai");
    await person.type(fields.password, "correct-password");
    await person.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("An unexpected error occurred")).toBeInTheDocument();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});

describe("TenantDashboard", () => {
  beforeEach(() => {
    navigateSpy.mockClear();
    setAuth(tenantAdmin);
  });

  it("renders tenant identity evidence and routes quick actions through tenant application paths", async () => {
    const person = userEvent.setup();
    render(
      <MemoryRouter>
        <TenantDashboard />
      </MemoryRouter>
    );

    expect(screen.getByText(/Welcome back, operator@saraise.ai/)).toBeInTheDocument();
    expect(screen.getByText("tenant-1...")).toBeInTheDocument();
    expect(screen.getByText("tenant_admin")).toBeInTheDocument();
    expect(screen.getByText("All systems operational")).toBeInTheDocument();

    await person.click(screen.getByRole("button", { name: /View AI Agents/i }));
    await person.click(screen.getByRole("button", { name: /Create Agent/i }));
    await person.click(screen.getByRole("button", { name: /Approval Queue/i }));

    expect(navigateSpy.mock.calls).toEqual([
      ["/ai-agents"],
      ["/ai-agents/create"],
      ["/ai-agents/approvals"],
    ]);
  });

  it("uses placeholders when tenant identity is not hydrated yet", () => {
    setAuth(null);
    render(
      <MemoryRouter>
        <TenantDashboard />
      </MemoryRouter>
    );

    expect(
      screen.getByText("Welcome back. Manage your tenant modules and workflows.")
    ).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(3);
  });
});

describe("ModuleLayout", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    navigateSpy.mockClear();
    setAuth(tenantAdmin);
  });

  it("opens user actions, routes profile/settings, and clears local session when logout succeeds", async () => {
    const person = userEvent.setup();
    const logoutSpy = vi.spyOn(authService, "logout").mockResolvedValue(undefined);

    renderModuleLayout();

    expect(screen.getByLabelText("tenant navigation")).toBeInTheDocument();
    await person.click(screen.getByRole("button", { name: /operator/i }));
    await person.click(screen.getByRole("button", { name: "Profile" }));
    await person.click(screen.getByRole("button", { name: /operator/i }));
    await person.click(screen.getByRole("button", { name: "Settings" }));
    await person.click(screen.getByRole("button", { name: /operator/i }));
    await person.click(screen.getByRole("button", { name: "Logout" }));

    await waitFor(() => {
      expect(logoutSpy).toHaveBeenCalled();
    });
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(navigateSpy.mock.calls).toEqual([["/profile"], ["/settings"], ["/login"]]);
  });

  it("still fails closed locally when the logout endpoint is unavailable", async () => {
    const person = userEvent.setup();
    vi.spyOn(authService, "logout").mockRejectedValue(new Error("logout unavailable"));

    renderModuleLayout();

    await person.click(screen.getByRole("button", { name: /operator/i }));
    await person.click(screen.getByRole("button", { name: "Logout" }));

    await waitFor(() => {
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });
    expect(navigateSpy).toHaveBeenCalledWith("/login");
  });

  it("toggles the mobile sidebar overlay without dropping child content", () => {
    renderModuleLayout();

    const sidebarToggle = screen.getByRole("button", { name: "Toggle sidebar" });
    fireEvent.click(sidebarToggle);
    expect(screen.getByText("Workspace content")).toBeInTheDocument();
    fireEvent.click(sidebarToggle);
    expect(screen.getByText("Workspace content")).toBeInTheDocument();
  });
});

describe("RoleBasedRedirect", () => {
  beforeEach(() => {
    setAuth(tenantAdmin);
  });

  it("redirects tenant users to the tenant dashboard and anonymous users to tenant app fallback", () => {
    const first = render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<RoleBasedRedirect />} />
          <Route path="/tenant/dashboard" element={<div>Tenant destination</div>} />
          <Route path="/ai-agents" element={<div>AI agents destination</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("Tenant destination")).toBeInTheDocument();
    first.unmount();

    setAuth(null);
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<RoleBasedRedirect />} />
          <Route path="/tenant/dashboard" element={<div>Tenant destination</div>} />
          <Route path="/ai-agents" element={<div>AI agents destination</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("AI agents destination")).toBeInTheDocument();
  });
});
