/* eslint-disable max-lines-per-function -- component contract tests intentionally cover all shared accounting UI states. */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import { AccountingApiError } from "../services/accounting-service";
import {
  AccountingFailure,
  AccountingPageSkeleton,
  ActionDialog,
  EmptyPanel,
  PageHeader,
  Pagination,
  StatusPill,
  formatMoney,
  useAccountingAccess,
} from "./AccountingUI";

function AccessProbe() {
  const access = useAccountingAccess();
  return <pre>{JSON.stringify(access)}</pre>;
}

describe("AccountingUI", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it("renders loading skeleton rows and page headers with optional actions", () => {
    const { container } = render(
      <>
        <AccountingPageSkeleton rows={3} />
        <PageHeader title="Accounting" description="Governed ledger" actions={<button>Act</button>} />
      </>
    );

    expect(screen.getByLabelText("Loading accounting information")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(5);
    expect(screen.getByRole("heading", { name: "Accounting" })).toBeInTheDocument();
    expect(screen.getByText("Governed ledger")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Act" })).toBeInTheDocument();
  });

  it("renders empty panels with optional action content", () => {
    render(
      <EmptyPanel
        title="No accounts"
        description="Create the first account before posting journals."
        action={<button>Create account</button>}
      />
    );

    expect(screen.getByRole("heading", { name: "No accounts" })).toBeInTheDocument();
    expect(screen.getByText("Create the first account before posting journals.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("normalizes failure copy, retry eligibility, detail, and correlation evidence", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    const { rerender } = render(
      <AccountingFailure
        error={
          new AccountingApiError(
            "Ledger unavailable",
            503,
            "CAPABILITY_UNAVAILABLE",
            "corr-ledger",
            "The ledger service timed out."
          )
        }
        onRetry={retry}
      />
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Accounting dependency unavailable");
    expect(screen.getByText("Ledger unavailable")).toBeInTheDocument();
    expect(screen.getByText("The ledger service timed out.")).toBeInTheDocument();
    expect(screen.getByText("Reference corr-ledger")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledOnce();

    rerender(<AccountingFailure error={new AccountingApiError("Missing", 404, "NOT_FOUND", null, null)} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Record not found");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();

    rerender(<AccountingFailure error={new AccountingApiError("Denied", 403, "DENIED", null, null)} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Access denied");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();

    rerender(<AccountingFailure error={new Error("raw")} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Connection interrupted");
    expect(screen.getByText("An unexpected accounting error occurred.")).toBeInTheDocument();
  });

  it("pages forward and backward only when pagination permits it", async () => {
    const user = userEvent.setup();
    const onPage = vi.fn();
    const { rerender } = render(
      <Pagination
        page={2}
        pagination={{ count: 51, total_pages: 3, has_previous: true, has_next: true }}
        onPage={onPage}
      />
    );

    expect(screen.getByText("51 records · page 2 of 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Previous" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(onPage).toHaveBeenNthCalledWith(1, 1);
    expect(onPage).toHaveBeenNthCalledWith(2, 3);

    rerender(
      <Pagination
        page={1}
        pagination={{ count: 0, total_pages: 0, has_previous: false, has_next: false }}
        onPage={onPage}
      />
    );
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.getByText("0 records · page 1 of 1")).toBeInTheDocument();
  });

  it("confirms actions with optional reason and supports cancel", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onConfirm = vi.fn();
    const { rerender } = render(
      <ActionDialog
        open
        onOpenChange={onOpenChange}
        title="Close period?"
        consequence="Closing blocks further posting."
        confirmLabel="Close period"
        pending={false}
        reasonRequired
        onConfirm={onConfirm}
      />
    );

    await user.type(screen.getByLabelText("Reason"), "Month complete");
    await user.click(screen.getByRole("button", { name: "Close period" }));
    expect(onConfirm).toHaveBeenCalledWith("Month complete");

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);

    rerender(
      <ActionDialog
        open
        onOpenChange={onOpenChange}
        title="Delete account?"
        consequence="Delete only unused accounts."
        confirmLabel="Delete"
        pending
        onConfirm={onConfirm}
      />
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();

    rerender(
      <ActionDialog
        open
        onOpenChange={onOpenChange}
        title="Delete account?"
        consequence="Delete only unused accounts."
        confirmLabel="Delete"
        pending={false}
        onConfirm={onConfirm}
      />
    );
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenLastCalledWith("");
  });

  it("formats money, status text, and access capabilities", () => {
    expect(formatMoney("12.5", "USD")).toMatch("$12.50");
    expect(formatMoney("not-a-number", "USD")).toBe("USD not-a-number");

    const { rerender } = render(<AccessProbe />);
    expect(screen.getByText(/"canRead":false/)).toHaveTextContent('"canDraft":false');
    expect(screen.getByText(/"canRead":false/)).toHaveTextContent('"canOperate":false');
    expect(screen.getByText(/"canRead":false/)).toHaveTextContent('"canAdminister":false');

    act(() => {
      useAuthStore.getState().setUser({
        id: "user-1",
        email: "admin@example.com",
        username: "admin",
        is_staff: false,
        is_superuser: false,
        tenant_id: "tenant-1",
        platform_role: null,
        tenant_role: "tenant_admin",
      });
    });

    rerender(
      <>
        <StatusPill status="partially_paid" />
        <AccessProbe />
      </>
    );

    expect(screen.getByText("partially paid")).toBeInTheDocument();
    expect(screen.getByText(/"canRead":true/)).toHaveTextContent('"canAdminister":true');

    act(() => {
      useAuthStore.getState().setUser({
        id: "user-2",
        email: "operator@example.com",
        username: "operator",
        is_staff: false,
        is_superuser: false,
        tenant_id: "tenant-1",
        platform_role: null,
        tenant_role: "operator",
      });
    });
    rerender(<AccessProbe />);
    expect(screen.getByText(/"canRead":true/)).toHaveTextContent('"canDraft":true');
    expect(screen.getByText(/"canRead":true/)).toHaveTextContent('"canOperate":true');
    expect(screen.getByText(/"canRead":true/)).toHaveTextContent('"canAdminister":false');

    act(() => {
      useAuthStore.getState().setUser({
        id: "user-3",
        email: "user@example.com",
        username: "user",
        is_staff: false,
        is_superuser: false,
        tenant_id: "tenant-1",
        platform_role: null,
        tenant_role: "tenant_user",
      });
    });
    rerender(<AccessProbe />);
    expect(screen.getByText(/"canRead":true/)).toHaveTextContent('"canDraft":true');
    expect(screen.getByText(/"canRead":true/)).toHaveTextContent('"canOperate":false');
    expect(screen.getByText(/"canRead":true/)).toHaveTextContent('"canAdminister":false');
  });
});
