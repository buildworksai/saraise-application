import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import type { LicenseInfo } from "../contracts";
import { ENDPOINTS } from "../contracts";
import { LicenseActivationForm } from "../components/LicenseActivationForm";
import { LicenseSettingsPage } from "./LicenseSettingsPage";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

function renderWithClient(element: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const view = render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
  return { ...view, client, invalidate };
}

const license: LicenseInfo = {
  organization_name: "BuildWorks",
  tier: "enterprise",
  status: "active",
  expires_at: "2026-12-31T00:00:00Z",
  days_remaining: 145,
  is_valid: true,
  features: [
    { module: "metadata_modeling", licensed: true, tier_required: "enterprise" },
    { module: "process_mining", licensed: false, tier_required: "enterprise_plus" },
  ],
};

describe("platform licensing surfaces", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders current license status and module entitlements from the status endpoint", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(license);

    renderWithClient(<LicenseSettingsPage />);

    expect(await screen.findByRole("heading", { name: "License Management" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(ENDPOINTS.LICENSING.STATUS);
    expect(screen.getAllByText("enterprise").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("145 Days")).toBeInTheDocument();
    expect(screen.getByText("metadata_modeling")).toBeInTheDocument();
    expect(screen.getByText("process_mining")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Contact Support/u })).toHaveAttribute(
      "href",
      "mailto:support@saraise.com"
    );
  });

  it("renders empty and failed status states without fabricating entitlements", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValueOnce({ ...license, features: [] })
      .mockResolvedValueOnce(null as never);

    const { unmount } = renderWithClient(<LicenseSettingsPage />);
    expect(await screen.findByText("No specific module entitlements found.")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(ENDPOINTS.LICENSING.STATUS);
    unmount();

    renderWithClient(<LicenseSettingsPage />);
    expect(await screen.findByText("Failed to load license information.")).toBeInTheDocument();
  });

  it("activates licenses, invalidates status, clears secrets, and reports failures", async () => {
    const user = userEvent.setup();
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValueOnce({ activated: true })
      .mockRejectedValueOnce(new Error("Signature verification failed"));

    const { invalidate } = renderWithClient(<LicenseActivationForm />);

    const input = screen.getByLabelText("License Key");
    expect(screen.getByRole("button", { name: "Activate License" })).toBeDisabled();
    await user.type(input, "  sk_live_test_license  ");
    await user.click(screen.getByRole("button", { name: "Activate License" }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(ENDPOINTS.LICENSING.ACTIVATE, {
        license_key: "  sk_live_test_license  ",
      })
    );
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["license-status"] });
    expect(toast.success).toHaveBeenCalledWith("License activated successfully");
    expect(input).toHaveValue("");

    await user.type(input, "sk_live_bad");
    await user.click(screen.getByRole("button", { name: "Activate License" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Signature verification failed"));
  });
});
