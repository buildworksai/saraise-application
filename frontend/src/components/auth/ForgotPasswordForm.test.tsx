import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ForgotPasswordForm } from "./ForgotPasswordForm";
import { ApiError } from "@/services/api-client";
import { authService } from "@/services/auth-service";

vi.mock("@/services/auth-service");

vi.mock("@/components/ui/logo-video", () => ({
  LogoVideo: ({
    autoplay,
    background,
    loop,
    showText = false,
    width,
  }: {
    autoplay?: boolean;
    background?: boolean;
    loop?: boolean;
    showText?: boolean;
    width?: number | string;
  }) => (
    <div
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

beforeEach(() => {
  vi.clearAllMocks();
});

const renderForm = () =>
  render(
    <BrowserRouter>
      <ForgotPasswordForm />
    </BrowserRouter>
  );

describe("ForgotPasswordForm rendering and validation", () => {
  it("renders password reset affordances", () => {
    renderForm();

    expect(screen.getByRole("heading", { name: "Forgot password?" })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toHaveAttribute("aria-invalid", "false");
    expect(
      screen.getByText("Reset links expire after 15 minutes.", { exact: false })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Email me a reset link" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to sign in" })).toHaveAttribute(
      "href",
      "/login"
    );
    expect(screen.getByTestId("desktop-logo-video")).toHaveAttribute("data-background", "true");
    expect(screen.getByTestId("desktop-logo-video")).toHaveAttribute("data-autoplay", "true");
    expect(screen.getByTestId("desktop-logo-video")).toHaveAttribute("data-loop", "true");
    expect(screen.getByTestId("mobile-logo-video")).toHaveAttribute("data-show-text", "true");
    expect(screen.getByTestId("mobile-logo-video")).toHaveAttribute("data-width", "180");
    expect(screen.getByText("SARAISE")).toBeInTheDocument();
    expect(screen.getByTestId("forgot-password-background-pattern")).toHaveClass(
      "bg-[radial-gradient(circle_at_2px_2px,rgba(255,255,255,0.3)_1px,transparent_0)]",
      "bg-[length:60px_60px]"
    );
  });

  it("requires an email before sending reset requests", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole("button", { name: "Email me a reset link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email is required");
    expect(screen.getByLabelText(/email address/i)).toHaveAttribute("aria-invalid", "true");
    expect(authService.forgotPassword).not.toHaveBeenCalled();
  });

  it("treats whitespace-only email as missing", async () => {
    const user = userEvent.setup();
    renderForm();

    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "   " } });
    await user.click(screen.getByRole("button", { name: "Email me a reset link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email is required");
    expect(authService.forgotPassword).not.toHaveBeenCalled();
  });
});

describe("ForgotPasswordForm request handling", () => {
  it("submits the trimmed email and renders enumeration-safe success copy", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.forgotPassword).mockResolvedValueOnce(undefined);
    renderForm();

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: " uat.user@example.com " },
    });
    await user.click(screen.getByRole("button", { name: "Email me a reset link" }));

    await waitFor(() => expect(authService.forgotPassword).toHaveBeenCalledTimes(1));
    expect(authService.forgotPassword).toHaveBeenCalledWith({ email: "uat.user@example.com" });
    expect(authService.forgotPassword).not.toHaveBeenCalledWith({
      email: " uat.user@example.com ",
    });
    const successCopy = await screen.findByText(
      "If an account exists for uat.user@example.com, a reset link is on its way.",
      { exact: false }
    );
    expect(successCopy).toBeInTheDocument();
    expect(successCopy).not.toHaveTextContent(" uat.user@example.com ");
  });

  it("hides raw server errors from the reset request alert", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.forgotPassword).mockRejectedValueOnce(
      new ApiError("Internal Server Error", 500, "Internal Server Error")
    );
    renderForm();

    await user.type(screen.getByLabelText(/email address/i), "uat.user@example.com");
    await user.click(screen.getByRole("button", { name: "Email me a reset link" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Password reset service is temporarily unavailable. Try again later."
    );
    expect(alert).not.toHaveTextContent("Internal Server Error");
  });

  it("uses the generic reset failure copy for client and unknown failures", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.forgotPassword).mockRejectedValueOnce(new ApiError("Bad request", 400));
    renderForm();

    await user.type(screen.getByLabelText(/email address/i), "uat.user@example.com");
    await user.click(screen.getByRole("button", { name: "Email me a reset link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to process your request right now."
    );
    expect(screen.getByLabelText(/email address/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("uses the generic reset failure copy for non-error failures", async () => {
    const user = userEvent.setup();
    vi.mocked(authService.forgotPassword).mockRejectedValueOnce("denied");
    renderForm();

    await user.type(screen.getByLabelText(/email address/i), "uat.user@example.com");
    await user.click(screen.getByRole("button", { name: "Email me a reset link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to process your request right now."
    );
  });

  it("re-enables the submit button after a rejected reset request", async () => {
    const user = userEvent.setup();
    let rejectReset: ((error: Error) => void) | undefined;
    const resetPromise = new Promise<void>((_, reject) => {
      rejectReset = reject;
    });
    vi.mocked(authService.forgotPassword).mockReturnValueOnce(resetPromise);
    renderForm();

    await user.type(screen.getByLabelText(/email address/i), "uat.user@example.com");
    await user.click(screen.getByRole("button", { name: "Email me a reset link" }));

    expect(screen.getByRole("button", { name: "Sending link..." })).toBeDisabled();

    await act(async () => {
      rejectReset?.(new Error("network failure"));
      await resetPromise.catch(() => undefined);
    });

    expect(await screen.findByRole("button", { name: "Email me a reset link" })).toBeEnabled();
  });

  it("keeps the submit button disabled only while the reset request is pending", async () => {
    const user = userEvent.setup();
    let resolveReset: (() => void) | undefined;
    const resetPromise = new Promise<void>((resolve) => {
      resolveReset = resolve;
    });
    vi.mocked(authService.forgotPassword).mockReturnValueOnce(resetPromise);
    renderForm();

    await user.type(screen.getByLabelText(/email address/i), "uat.user@example.com");
    await user.click(screen.getByRole("button", { name: "Email me a reset link" }));

    expect(screen.getByRole("button", { name: "Sending link..." })).toBeDisabled();

    await act(async () => {
      resolveReset?.();
      await resetPromise;
    });

    expect(await screen.findByRole("link", { name: "Back to login" })).toBeInTheDocument();
  });
});
