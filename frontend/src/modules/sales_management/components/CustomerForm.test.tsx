/* eslint-disable @typescript-eslint/unbound-method -- mutation tests assert mocked service calls. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type * as ReactRouter from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Customer } from "../contracts";
import { salesService } from "../services/sales-service";
import { CustomerForm } from "./CustomerForm";

const navigate = vi.hoisted(() => vi.fn());
const toastSuccess = vi.hoisted(() => vi.fn());

vi.mock("react-router-dom", async (importOriginal) => {
  const actual: typeof ReactRouter = await importOriginal();
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

vi.mock("sonner", () => ({
  toast: { success: toastSuccess },
}));

vi.mock("../services/sales-service", () => ({
  salesQueryKeys: { all: ["sales-management"] },
  salesService: {
    createCustomer: vi.fn(),
    updateCustomer: vi.fn(),
  },
}));

const customer: Customer = {
  id: "customer-1",
  tenant_id: "tenant-1",
  customer_code: "ACME",
  customer_name: "ACME Industries",
  email: "buyer@example.com",
  phone: "555-0100",
  address: "1 Main Street",
  credit_limit: "1000.00",
  currency: "USD",
  is_active: true,
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
  created_by: "user-1",
  updated_by: "user-1",
  deleted_at: null,
  deleted_by: null,
  lock_version: 9,
};

function renderForm(element: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CustomerForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "idem-customer") });
  });

  it("validates create input, submits normalized payload, toasts, and navigates", async () => {
    vi.mocked(salesService.createCustomer).mockResolvedValue(customer);
    renderForm(<CustomerForm />);

    expect(screen.getByRole("button", { name: "Create customer" })).toBeDisabled();
    expect(screen.getByText("Customer code is required.")).toBeInTheDocument();
    expect(screen.getByText("Customer name is required.")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Customer code"), " acme ");
    await userEvent.type(screen.getByLabelText("Customer name"), "ACME Industries");
    await userEvent.clear(screen.getByLabelText("Currency"));
    await userEvent.type(screen.getByLabelText("Currency"), "usd");
    await userEvent.type(screen.getByLabelText("Credit limit"), "-1");
    expect(screen.getByText("Credit limit cannot be negative.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create customer" })).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("Credit limit"));
    await userEvent.type(screen.getByLabelText("Credit limit"), "2500.50");
    await userEvent.type(screen.getByLabelText("Email"), "buyer@example.com");
    await userEvent.type(screen.getByLabelText("Phone"), "555-0100");
    await userEvent.type(screen.getByLabelText("Address"), "1 Main Street");
    await userEvent.click(screen.getByLabelText("Active customer"));
    await userEvent.click(screen.getByRole("button", { name: "Create customer" }));

    await waitFor(() =>
      expect(salesService.createCustomer).toHaveBeenCalledWith(
        expect.objectContaining({
          customer_code: " acme ",
          customer_name: "ACME Industries",
          currency: "USD",
          credit_limit: "2500.50",
          is_active: false,
        }),
        "idem-customer"
      )
    );
    expect(toastSuccess).toHaveBeenCalledWith("Customer created");
    expect(navigate).toHaveBeenCalledWith("/sales-management/customers/customer-1");
  });

  it("uses native form constraints for required customer identity fields", () => {
    const { container } = renderForm(<CustomerForm />);

    expect(container.querySelector("form")?.noValidate).toBe(false);
    expect(screen.getByLabelText("Customer code")).toBeRequired();
    expect(screen.getByLabelText("Customer name")).toBeRequired();
    expect(screen.getByLabelText("Currency")).toBeRequired();
    expect(screen.getByLabelText("Currency")).toHaveAttribute("maxLength", "3");
    expect(screen.getByLabelText("Credit limit")).toHaveAttribute("min", "0");
  });

  it("updates existing customers with expected version and guards dirty cancel navigation", async () => {
    vi.mocked(salesService.updateCustomer).mockResolvedValue({
      ...customer,
      customer_name: "ACME Renewed",
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderForm(<CustomerForm customer={customer} />);

    await userEvent.clear(screen.getByLabelText("Customer name"));
    await userEvent.type(screen.getByLabelText("Customer name"), "ACME Renewed");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalledWith("Discard unsaved changes?");
    expect(navigate).not.toHaveBeenCalledWith("/sales-management/customers");

    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(navigate).toHaveBeenCalledWith("/sales-management/customers");

    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(salesService.updateCustomer).toHaveBeenCalledWith(
        "customer-1",
        expect.objectContaining({ customer_name: "ACME Renewed", expected_version: 9 })
      )
    );
    expect(toastSuccess).toHaveBeenCalledWith("Customer updated");
    expect(navigate).toHaveBeenCalledWith("/sales-management/customers/customer-1");
    confirm.mockRestore();
  });
});
