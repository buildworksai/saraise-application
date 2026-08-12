/* eslint-disable max-lines-per-function -- cohesive quota branch matrix keeps mutation assertions local to this page. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Quotas } from "../../services/quota-service";
import { quotaService } from "../../services/quota-service";
import { QuotaManagementPage } from "../QuotaManagementPage";

vi.mock("../../services/quota-service", () => ({
  quotaService: { getQuotas: vi.fn() },
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotaManagementPage />
    </QueryClientProvider>
  );
}

const quotas: Quotas = {
  users: { used: 90, limit: 100 },
  storage: { used: 512.5, limit: 1000 },
  api_calls: { used: 1_500_000, limit: 2_000_000 },
};

describe("QuotaManagementPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(quotaService.getQuotas).mockResolvedValue(quotas);
  });

  it("renders a governed loading state before quota data resolves", () => {
    vi.mocked(quotaService.getQuotas).mockReturnValue(new Promise(() => undefined));
    const { container } = renderPage();

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Quota Management" })).not.toBeInTheDocument();
  });

  it("renders quota percentages, formatted counts, and high-usage warning", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Quota Management" })).toBeInTheDocument();
    expect(screen.getByText("90 / 100")).toBeInTheDocument();
    expect(screen.getByText("512.50 GB / 1000 GB")).toBeInTheDocument();
    expect(screen.getByText("1.5M / 2.0M")).toBeInTheDocument();
    expect(screen.getByText("Approaching Quota Limits")).toBeInTheDocument();
    expect(screen.getByText("90% used")).toBeVisible();
    expect(screen.getByText("51% used")).toBeVisible();
    expect(screen.getByText("75% used")).toBeVisible();
    expect(screen.getByTestId("quota-users-alert")).toBeVisible();
    expect(screen.queryByTestId("quota-storage-alert")).not.toBeInTheDocument();
    expect(screen.queryByTestId("quota-api-alert")).not.toBeInTheDocument();

    expect(screen.getByTestId("quota-users-progress")).toHaveStyle({ width: "90%" });
    expect(screen.getByTestId("quota-storage-progress")).toHaveStyle({
      width: "51.24999999999999%",
    });
    expect(screen.getByTestId("quota-api-progress")).toHaveStyle({ width: "75%" });
    expect(screen.getByTestId("quota-users-progress")).toHaveClass(
      "h-2",
      "rounded-full",
      "transition-all",
      "bg-red-500"
    );
    expect(screen.getByTestId("quota-storage-progress")).toHaveClass("bg-green-500");
    expect(screen.getByTestId("quota-storage-progress")).toHaveClass(
      "h-2",
      "rounded-full",
      "transition-all"
    );
    expect(screen.getByTestId("quota-api-progress")).toHaveClass("bg-yellow-500");
    expect(screen.getByTestId("quota-api-progress")).toHaveClass(
      "h-2",
      "rounded-full",
      "transition-all"
    );
  });

  it("enforces quota warning thresholds per resource without false positives", async () => {
    vi.mocked(quotaService.getQuotas).mockResolvedValue({
      users: { used: 89, limit: 100 },
      storage: { used: 90, limit: 100 },
      api_calls: { used: 91, limit: 100 },
    });
    renderPage();

    expect(await screen.findByText("89 / 100")).toBeInTheDocument();
    expect(screen.getByText("90.00 GB / 100 GB")).toBeInTheDocument();
    expect(screen.getByText("91 / 100")).toBeInTheDocument();
    expect(screen.queryByTestId("quota-users-alert")).not.toBeInTheDocument();
    expect(screen.getByTestId("quota-storage-alert")).toBeVisible();
    expect(screen.getByTestId("quota-api-alert")).toBeVisible();
    expect(screen.getByText("Approaching Quota Limits")).toBeVisible();
    expect(screen.getByText("89% used")).toBeVisible();
    expect(screen.getAllByText("90% used")).toHaveLength(1);
    expect(screen.getByText("91% used")).toBeVisible();
  });

  it.each([
    [
      "users",
      {
        users: { used: 90, limit: 100 },
        storage: { used: 10, limit: 100 },
        api_calls: { used: 10, limit: 100 },
      },
    ],
    [
      "storage",
      {
        users: { used: 10, limit: 100 },
        storage: { used: 90, limit: 100 },
        api_calls: { used: 10, limit: 100 },
      },
    ],
    [
      "api",
      {
        users: { used: 10, limit: 100 },
        storage: { used: 10, limit: 100 },
        api_calls: { used: 90, limit: 100 },
      },
    ],
  ] satisfies readonly [string, Quotas][])(
    "renders the high-usage warning when only %s quota is at the threshold",
    async (_resource, nextQuotas) => {
      vi.mocked(quotaService.getQuotas).mockResolvedValue(nextQuotas);
      renderPage();

      expect(await screen.findByText("Approaching Quota Limits")).toBeVisible();
    }
  );

  it("formats exact K and M API quota boundaries", async () => {
    vi.mocked(quotaService.getQuotas).mockResolvedValue({
      users: { used: 1, limit: 10 },
      storage: { used: 1, limit: 10 },
      api_calls: { used: 1_000, limit: 1_000_000 },
    });
    renderPage();

    expect(await screen.findByText("1.0K / 1.0M")).toBeInTheDocument();
    expect(screen.getByText("0% used")).toBeVisible();
  });

  it("caps over-limit progress widths at one hundred percent", async () => {
    vi.mocked(quotaService.getQuotas).mockResolvedValue({
      users: { used: 150, limit: 100 },
      storage: { used: 120, limit: 100 },
      api_calls: { used: 200, limit: 100 },
    });
    renderPage();

    expect(await screen.findByText("150 / 100")).toBeInTheDocument();
    expect(screen.getByTestId("quota-users-progress")).toHaveStyle({ width: "100%" });
    expect(screen.getByTestId("quota-storage-progress")).toHaveStyle({ width: "100%" });
    expect(screen.getByTestId("quota-api-progress")).toHaveStyle({ width: "100%" });
    expect(screen.getAllByText("100% used")).toHaveLength(3);
  });

  it("renders unlimited limits without progress bars or false high-usage warning", async () => {
    vi.mocked(quotaService.getQuotas).mockResolvedValue({
      users: { used: 1000, limit: 0 },
      storage: { used: 2048, limit: 0 },
      api_calls: { used: 250, limit: 0 },
    });
    const { container } = renderPage();

    expect(await screen.findByText("1000 / Unlimited")).toBeInTheDocument();
    expect(screen.getByText("2048.00 GB / Unlimited")).toBeInTheDocument();
    expect(screen.getByText("250 / Unlimited")).toBeInTheDocument();
    expect(screen.getAllByText("Unlimited")).toHaveLength(3);
    expect(container.querySelectorAll("[style]")).toHaveLength(0);
    expect(screen.queryByText("Approaching Quota Limits")).not.toBeInTheDocument();
  });

  it("retries after quota loading fails", async () => {
    const user = userEvent.setup();
    vi.mocked(quotaService.getQuotas)
      .mockRejectedValueOnce(new Error("quota service unavailable"))
      .mockResolvedValueOnce(quotas);

    renderPage();

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Failed to load quota information")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try Again" }));

    await waitFor(() => expect(quotaService.getQuotas).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("90 / 100")).toBeInTheDocument();
  });

  it("renders a fail-closed empty state when the governed quota payload is absent", async () => {
    vi.mocked(quotaService.getQuotas).mockResolvedValue(null as never);
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "No quota information" })
    ).toBeInTheDocument();
    expect(screen.getByText("Quota information is not available.")).toBeInTheDocument();
  });
});
