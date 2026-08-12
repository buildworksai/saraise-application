import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "../../stores/auth-store";
import { useAuthStore } from "../../stores/auth-store";
import { apiClient } from "../../services/api-client";
import { ENDPOINTS as AUTH_ENDPOINTS } from "../../services/auth-contracts";
import { ProfilePage } from "./ProfilePage";
import { SettingsPage } from "./SettingsPage";

const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => {
      toastError(...args);
    },
    success: (...args: unknown[]) => {
      toastSuccess(...args);
    },
  },
}));

const user: User = {
  id: "user-1",
  email: "operator@saraise.ai",
  username: "operator",
  is_staff: false,
  is_superuser: false,
  tenant_id: "tenant-1",
  platform_role: null,
  tenant_role: "tenant_admin",
};

function resetAuth(nextUser: User | null = user) {
  act(() => {
    useAuthStore.setState({
      user: nextUser,
      isAuthenticated: Boolean(nextUser),
      isLoading: false,
    });
  });
}

describe("ProfilePage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    toastError.mockClear();
    toastSuccess.mockClear();
    resetAuth();
  });

  it("shows a loading state when no authenticated user is available", () => {
    resetAuth(null);

    render(<ProfilePage />);

    expect(screen.getByText("Loading profile...")).toBeInTheDocument();
  });

  it("renders profile identity and tenant account metadata", () => {
    render(<ProfilePage />);

    expect(screen.getByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getAllByText("operator@saraise.ai")).toHaveLength(2);
    expect(screen.getByText("Tenant Admin")).toBeInTheDocument();
    expect(screen.getByText("user-1")).toBeInTheDocument();
    expect(screen.getByText("tenant-1")).toBeInTheDocument();
  });

  it("validates required profile fields before saving", async () => {
    const person = userEvent.setup();
    const patchSpy = vi.spyOn(apiClient, "patch");
    render(<ProfilePage />);

    await person.click(screen.getByRole("button", { name: "Edit Profile" }));
    await person.clear(screen.getByPlaceholderText("Enter username"));
    await person.clear(screen.getByPlaceholderText("Enter email"));
    await person.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(await screen.findByText("Username is required")).toBeInTheDocument();
    expect(screen.getByText("Email is required")).toBeInTheDocument();
    expect(toastError).toHaveBeenCalledWith("Please fix the errors before saving");
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it("validates email format and password change dependencies", async () => {
    const person = userEvent.setup();
    render(<ProfilePage />);

    await person.click(screen.getByRole("button", { name: "Edit Profile" }));
    await person.clear(screen.getByPlaceholderText("Enter email"));
    await person.type(screen.getByPlaceholderText("Enter email"), "not-an-email");
    await person.type(
      screen.getByPlaceholderText("Enter new password (leave blank to keep current)"),
      "short"
    );
    await person.type(screen.getByPlaceholderText("Confirm new password"), "different-password");
    await person.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(await screen.findByText("Invalid email format")).toBeInTheDocument();
    expect(screen.getByText("Password must be at least 8 characters")).toBeInTheDocument();
    expect(screen.getByText("Passwords do not match")).toBeInTheDocument();
    expect(screen.getByText("Current password is required to change password")).toBeInTheDocument();
  });
});

describe("ProfilePage persistence", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    toastError.mockClear();
    toastSuccess.mockClear();
    resetAuth();
  });

  it("saves only changed profile fields and updates the auth store", async () => {
    const person = userEvent.setup();
    const updatedUser: User = { ...user, username: "controller", email: "controller@saraise.ai" };
    const patchSpy = vi.spyOn(apiClient, "patch").mockResolvedValue({ user: updatedUser });
    render(<ProfilePage />);

    await person.click(screen.getByRole("button", { name: "Edit Profile" }));
    await person.clear(screen.getByPlaceholderText("Enter username"));
    await person.type(screen.getByPlaceholderText("Enter username"), "controller");
    await person.clear(screen.getByPlaceholderText("Enter email"));
    await person.type(screen.getByPlaceholderText("Enter email"), "controller@saraise.ai");
    await person.type(screen.getByPlaceholderText("Enter current password"), "old-password");
    await person.type(
      screen.getByPlaceholderText("Enter new password (leave blank to keep current)"),
      "new-password"
    );
    await person.type(screen.getByPlaceholderText("Confirm new password"), "new-password");
    await person.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith(AUTH_ENDPOINTS.PROFILE, {
        username: "controller",
        email: "controller@saraise.ai",
        password: "new-password", // pragma: allowlist secret
        current_password: "old-password", // pragma: allowlist secret
      });
    });
    expect(useAuthStore.getState().user).toEqual(updatedUser);
    expect(toastSuccess).toHaveBeenCalledWith("Your profile has been successfully updated");
    expect(screen.getByRole("button", { name: "Edit Profile" })).toBeInTheDocument();
  });

  it("surfaces profile API failures without leaving save disabled", async () => {
    const person = userEvent.setup();
    vi.spyOn(apiClient, "patch").mockRejectedValue({
      response: { data: { error: "Email is already assigned" } },
    });
    render(<ProfilePage />);

    await person.click(screen.getByRole("button", { name: "Edit Profile" }));
    await person.clear(screen.getByPlaceholderText("Enter email"));
    await person.type(screen.getByPlaceholderText("Enter email"), "duplicate@saraise.ai");
    await person.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Email is already assigned"));
    expect(screen.getByRole("button", { name: "Save Changes" })).not.toBeDisabled();
  });

  it("cancels edits and restores the original user values", async () => {
    const person = userEvent.setup();
    render(<ProfilePage />);

    await person.click(screen.getByRole("button", { name: "Edit Profile" }));
    await person.clear(screen.getByPlaceholderText("Enter username"));
    await person.type(screen.getByPlaceholderText("Enter username"), "discarded");
    await person.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getAllByText("operator")).toHaveLength(2);
    expect(screen.queryByDisplayValue("discarded")).not.toBeInTheDocument();
  });
});

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    resetAuth();
  });

  afterEach(() => {
    act(() => {
      vi.runOnlyPendingTimers();
    });
    vi.useRealTimers();
  });

  it("shows a loading state when no authenticated user is available", () => {
    resetAuth(null);

    render(<SettingsPage />);

    expect(screen.getByText("Loading settings...")).toBeInTheDocument();
  });

  it("updates display, notification, and localization settings before persistence", () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    fireEvent.click(screen.getByRole("button", { name: "Push Notifications" }));
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "de" } });
    fireEvent.change(screen.getByLabelText("Timezone"), { target: { value: "Europe/London" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Settings" }));

    expect(screen.getByRole("button", { name: "Saving..." })).toBeDisabled();
    expect(JSON.parse(localStorage.getItem("user-settings") ?? "{}")).toEqual({
      theme: "dark",
      notifications: {
        email: true,
        push: true,
        security: true,
      },
      language: "de",
      timezone: "Europe/London",
    });

    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(screen.getByRole("button", { name: "Save Settings" })).not.toBeDisabled();
  });

  it("toggles notification preferences independently", () => {
    render(<SettingsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Email Notifications" }));
    fireEvent.click(screen.getByRole("button", { name: "Security Alerts" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Settings" }));

    expect(JSON.parse(localStorage.getItem("user-settings") ?? "{}")).toMatchObject({
      notifications: {
        email: false,
        push: false,
        security: false,
      },
    });
  });
});
