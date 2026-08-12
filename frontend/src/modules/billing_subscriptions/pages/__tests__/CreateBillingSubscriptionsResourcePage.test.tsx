/* eslint-disable @typescript-eslint/consistent-type-imports -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
/**
 * CreateBillingSubscriptionsResourcePage Component Tests
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import type { Subscription } from "../../contracts";
import { billing_subscriptionsService } from "../../services/billing_subscriptions-service";
import { CreateBillingSubscriptionsResourcePage } from "../CreateBillingSubscriptionsResourcePage";

const { navigateMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
}));

vi.mock("../../services/billing_subscriptions-service");
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const createdSubscription: Subscription = {
  id: "subscription-new",
  tenant_id: "tenant-1",
  plan: "enterprise-plan",
  plan_id: "plan-1",
  status: "pending",
  current_period_start: "2026-07-26T00:00:00Z",
  current_period_end: "2027-07-26T00:00:00Z",
  created_at: "2026-07-26T00:00:00Z",
  updated_at: "2026-07-26T00:00:00Z",
};

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

const renderPage = (queryClient: QueryClient) =>
  render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <CreateBillingSubscriptionsResourcePage />
      </BrowserRouter>
    </QueryClientProvider>
  );

describe("CreateBillingSubscriptionsResourcePage", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  it("renders the real subscription form fields and default billing cycle", () => {
    renderPage(queryClient);

    expect(
      screen.getByRole("heading", { name: "Create BillingSubscriptions Resource" })
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Plan ID *")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Billing Cycle" })).toHaveValue("monthly");
    expect(screen.getByRole("option", { name: "Monthly" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Yearly" })).toBeInTheDocument();
  });

  it("validates that a plan is required before submitting", async () => {
    const user = userEvent.setup();
    renderPage(queryClient);

    await user.click(screen.getByRole("button", { name: "Create Resource" }));

    expect(await screen.findByText("Plan is required")).toBeInTheDocument();
    expect(billing_subscriptionsService.createSubscription).not.toHaveBeenCalled();
  });

  it("submits the selected plan and billing cycle through createSubscription", async () => {
    vi.mocked(billing_subscriptionsService.createSubscription).mockResolvedValue(
      createdSubscription
    );
    const user = userEvent.setup();
    renderPage(queryClient);

    await user.type(screen.getByLabelText("Plan ID *"), "enterprise-plan");
    await user.selectOptions(screen.getByRole("combobox", { name: "Billing Cycle" }), "yearly");
    await user.click(screen.getByRole("button", { name: "Create Resource" }));

    expect(billing_subscriptionsService.createSubscription).toHaveBeenCalledWith({
      plan: "enterprise-plan",
      billing_cycle: "yearly",
    });
    expect(await screen.findByRole("button", { name: "Create Resource" })).toBeEnabled();
    expect(toast.success).toHaveBeenCalledWith("Subscription created successfully");
    expect(navigateMock).toHaveBeenCalledWith("/billing-subscriptions");
  });
});
