/* eslint-disable max-lines-per-function -- page coverage exercises stateful query and mutation workflows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Account } from "../contracts";
import { accountingService } from "../services/accounting-service";
import { AccountDetailPage } from "./AccountDetailPage";
import { AccountListPage } from "./AccountListPage";
import { CreateAccountPage } from "./CreateAccountPage";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("../services/accounting-service", () => ({
  accountingService: {
    createAccount: vi.fn(),
    deleteAccount: vi.fn(),
    getAccount: vi.fn(),
    listAccounts: vi.fn(),
  },
  createIdempotencyKey: vi.fn((scope: string) => `${scope}:test-key`),
}));

const mockAccountingService = vi.mocked(accountingService);

const account: Account = {
  id: "account-1",
  tenant_id: "tenant-1",
  version: 3,
  created_by: "operator-1",
  updated_by: "operator-2",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-02T00:00:00Z",
  code: "1000",
  name: "Operating Cash",
  account_type: "asset",
  normal_balance: "debit",
  parent: null,
  is_group: false,
  is_active: true,
  currency: "USD",
  allow_multi_currency: false,
  cash_flow_category: "operating",
  description: "Primary bank ledger",
  is_deleted: false,
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}</output>;
}

function renderAccounting(route: string, element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/accounting-finance/accounts" element={element} />
          <Route path="/accounting-finance/accounts/new" element={element} />
          <Route path="/accounting-finance/accounts/:id" element={element} />
          <Route path="/accounting-finance/accounts/:id/edit" element={<LocationProbe />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("accounting finance pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAccountingService.createAccount.mockResolvedValue(account);
    mockAccountingService.deleteAccount.mockResolvedValue(undefined);
    mockAccountingService.getAccount.mockResolvedValue(account);
    mockAccountingService.listAccounts.mockResolvedValue({
      results: [account],
      pagination: {
        page: 1,
        page_size: 20,
        total_pages: 1,
        count: 1,
        has_next: false,
        has_previous: false,
      },
      meta: { correlation_id: "corr-account", timestamp: "2026-07-02T00:00:00Z" },
    });
  });

  it("renders chart rows and deletes only after operator confirmation", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderAccounting("/accounting-finance/accounts", <AccountListPage />);

    expect(await screen.findByRole("heading", { name: "Chart of Accounts" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "1000" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Operating Cash" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(confirm).toHaveBeenCalledWith("Are you sure you want to delete this account?");
    expect(mockAccountingService.deleteAccount).toHaveBeenCalledWith("account-1");
  });

  it("surfaces empty and error states with real retry behavior", async () => {
    mockAccountingService.listAccounts.mockResolvedValueOnce({
      results: [],
      pagination: {
        page: 1,
        page_size: 20,
        total_pages: 1,
        count: 0,
        has_next: false,
        has_previous: false,
      },
      meta: { correlation_id: "corr-empty", timestamp: "2026-07-02T00:00:00Z" },
    });
    const { unmount } = renderAccounting("/accounting-finance/accounts", <AccountListPage />);

    expect(await screen.findByText("No accounts yet")).toBeInTheDocument();
    expect(
      screen.getByText("Create your first account to start building your chart of accounts.")
    ).toBeInTheDocument();
    unmount();

    mockAccountingService.listAccounts
      .mockRejectedValueOnce(new Error("network unavailable"))
      .mockResolvedValueOnce({
        results: [account],
        pagination: {
          page: 1,
          page_size: 20,
          total_pages: 1,
          count: 1,
          has_next: false,
          has_previous: false,
        },
        meta: { correlation_id: "corr-retry", timestamp: "2026-07-02T00:00:00Z" },
      });
    renderAccounting("/accounting-finance/accounts", <AccountListPage />);

    expect(await screen.findByText(/Failed to load accounts/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("cell", { name: "1000" })).toBeInTheDocument();
  });

  it("creates accounts through the service boundary and navigates to the saved record", async () => {
    const user = userEvent.setup();
    renderAccounting("/accounting-finance/accounts/new", <CreateAccountPage />);

    await user.click(screen.getByRole("button", { name: "Create Account" }));
    expect(screen.getByText("Code is required")).toBeInTheDocument();
    expect(screen.getByText("Name is required")).toBeInTheDocument();
    expect(mockAccountingService.createAccount).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Code"), "2000");
    await user.type(screen.getByLabelText("Name"), "Accounts Receivable");
    await user.type(screen.getByPlaceholderText("Optional description"), "Customer invoices");
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    expect(mockAccountingService.createAccount).toHaveBeenCalledWith(
      expect.objectContaining({
        code: "2000",
        name: "Accounts Receivable",
        account_type: "asset",
        description: "Customer invoices",
      }),
      "account.create:test-key"
    );
    await waitFor(() =>
      expect(screen.getByLabelText("location")).toHaveTextContent(
        "/accounting-finance/accounts/account-1"
      )
    );
  });

  it("renders account detail actions, failed lookups, and confirmed deletes", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { unmount } = renderAccounting(
      "/accounting-finance/accounts/account-1",
      <AccountDetailPage />
    );

    expect(
      await screen.findByRole("heading", { name: "1000 - Operating Cash" })
    ).toBeInTheDocument();
    expect(screen.getByText("Primary bank ledger")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getAllByLabelText("location").at(-1)).toHaveTextContent(
      "/accounting-finance/accounts/account-1/edit"
    );
    unmount();

    mockAccountingService.getAccount.mockResolvedValueOnce(account);
    renderAccounting("/accounting-finance/accounts/account-1", <AccountDetailPage />);
    expect(
      await screen.findByRole("heading", { name: "1000 - Operating Cash" })
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(confirm).toHaveBeenCalledWith("Are you sure you want to delete this account?");
    await waitFor(() =>
      expect(mockAccountingService.deleteAccount).toHaveBeenCalledWith("account-1")
    );
  });
});
