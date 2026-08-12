import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authService } from "@/services/auth-service";
import { ResetPasswordForm } from "./ResetPasswordForm";

vi.mock("@/services/auth-service", () => ({
  authService: { resetPassword: vi.fn() },
}));
vi.mock("@/components/ui/logo-video", () => ({
  LogoVideo: () => <span data-testid="logo-video" />,
}));

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="path">{location.pathname}</span>;
}

function renderForm(path = "/reset-password?token=reset-token") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/reset-password"
          element={
            <>
              <ResetPasswordForm />
              <LocationProbe />
            </>
          }
        />
        <Route path="/login" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ResetPasswordForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(authService.resetPassword).mockResolvedValue(undefined);
  });

  it("fails closed when the token is missing and does not call reset", async () => {
    const user = userEvent.setup();
    renderForm("/reset-password");

    expect(screen.getByRole("alert")).toHaveTextContent("Reset link is missing or invalid.");
    expect(screen.getByLabelText("New password")).toBeDisabled();
    expect(screen.getByLabelText("Confirm password")).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /update password/i }));
    expect(authService.resetPassword).not.toHaveBeenCalled();
  });

  it("validates password length and confirmation before submission", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText("New password"), "short");
    await user.tab();
    expect(screen.getByText("Password must be at least 8 characters long")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("New password"));
    await user.type(screen.getByLabelText("New password"), "long-enough");
    await user.type(screen.getByLabelText("Confirm password"), "different");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    expect(screen.getByText("Passwords do not match")).toBeInTheDocument();
    expect(authService.resetPassword).not.toHaveBeenCalled();
  });

  it("submits the token and new password, then returns to login after success", async () => {
    const user = userEvent.setup();
    renderForm("/reset-password?token=encoded%20token");

    await user.type(screen.getByLabelText("New password"), "new-secure-password");
    await user.type(screen.getByLabelText("Confirm password"), "new-secure-password");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() =>
      expect(authService.resetPassword).toHaveBeenCalledWith({
        token: "encoded token",
        new_password: "new-secure-password", // pragma: allowlist secret
      })
    );
    expect(
      await screen.findByText("Your password has been updated successfully.")
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Return to login" }));
    expect(screen.getByTestId("path")).toHaveTextContent("/login");
  });

  it("renders a safe fallback error for non-error failures", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.resetPassword).mockRejectedValue("offline");
    renderForm();

    await user.type(screen.getByLabelText("New password"), "new-secure-password");
    await user.type(screen.getByLabelText("Confirm password"), "new-secure-password");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to reset password at this time."
    );
  }, 15_000);
});
