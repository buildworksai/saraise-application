/* eslint-disable @typescript-eslint/unbound-method -- mutation tests assert mocked service calls. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
/* eslint-disable max-lines-per-function -- Customer form mutation coverage keeps create/edit validation flows colocated. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{element}</MemoryRouter>
      </QueryClientProvider>
    ),
  };
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
    expect(screen.getByLabelText("Customer code")).toHaveAttribute(
      "aria-describedby",
      "customer-code-error"
    );

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

  it("blocks whitespace and malformed currency values before mutation", async () => {
    const { container } = renderForm(<CustomerForm />);

    await userEvent.type(screen.getByLabelText("Customer code"), "   ");
    await userEvent.type(screen.getByLabelText("Customer name"), "   ");
    await userEvent.clear(screen.getByLabelText("Currency"));
    await userEvent.type(screen.getByLabelText("Currency"), "u1d");

    expect(screen.getByText("Customer code is required.")).toBeInTheDocument();
    expect(screen.getByText("Customer name is required.")).toBeInTheDocument();
    expect(screen.getByText("Use a three-letter uppercase currency code.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create customer" })).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("Currency"));
    await userEvent.type(screen.getByLabelText("Currency"), "us");
    expect(screen.getByText("Use a three-letter uppercase currency code.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USDD" } });
    expect(screen.getByText("Use a three-letter uppercase currency code.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "XUSD" } });
    expect(screen.getByText("Use a three-letter uppercase currency code.")).toBeInTheDocument();
    fireEvent.submit(container.querySelector("form")!);
    expect(salesService.createCustomer).not.toHaveBeenCalled();
  });

  it("wires optional contact fields, active default, page copy, and accessible help ids", async () => {
    vi.mocked(salesService.createCustomer).mockResolvedValue({ ...customer, id: "customer-2" });
    renderForm(<CustomerForm />);

    expect(screen.getByRole("heading", { name: "Create customer" })).toBeInTheDocument();
    expect(screen.getByLabelText("Currency")).toHaveAccessibleDescription(
      "ISO 4217 currency code, for example USD."
    );
    expect(screen.getByLabelText("Active customer")).toBeChecked();

    await userEvent.type(screen.getByLabelText("Customer code"), "ACME");
    expect(screen.getByLabelText("Customer code")).toHaveAttribute(
      "aria-describedby",
      "customer-code-help"
    );
    await userEvent.type(screen.getByLabelText("Customer name"), "ACME Industries");
    await userEvent.clear(screen.getByLabelText("Currency"));
    await userEvent.type(screen.getByLabelText("Currency"), "eur");
    await userEvent.type(screen.getByLabelText("Email"), "ap@example.com");
    await userEvent.type(screen.getByLabelText("Phone"), "555-0200");
    await userEvent.type(screen.getByLabelText("Address"), "2 Main Street");
    await userEvent.click(screen.getByRole("button", { name: "Create customer" }));

    await waitFor(() =>
      expect(salesService.createCustomer).toHaveBeenCalledWith(
        expect.objectContaining({
          customer_code: "ACME",
          customer_name: "ACME Industries",
          currency: "EUR",
          email: "ap@example.com",
          phone: "555-0200",
          address: "2 Main Street",
          is_active: true,
        }),
        "idem-customer"
      )
    );
  });

  it("submits blank optional values, preserves zero credit, and invalidates the sales cache", async () => {
    vi.mocked(salesService.createCustomer).mockResolvedValue({ ...customer, id: "customer-3" });
    const { client } = renderForm(<CustomerForm />);
    const invalidate = vi.spyOn(client, "invalidateQueries");

    await userEvent.type(screen.getByLabelText("Customer code"), "ZERO");
    await userEvent.type(screen.getByLabelText("Customer name"), "Zero Credit");
    await userEvent.type(screen.getByLabelText("Credit limit"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Create customer" }));

    await waitFor(() =>
      expect(salesService.createCustomer).toHaveBeenCalledWith(
        expect.objectContaining({
          email: "",
          phone: "",
          address: "",
          credit_limit: "0",
          currency: "USD",
          is_active: true,
        }),
        "idem-customer"
      )
    );
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["sales-management"] });
  });

  it("surfaces mutation errors without navigating", async () => {
    vi.mocked(salesService.createCustomer).mockRejectedValue(new Error("network down"));
    renderForm(<CustomerForm />);

    await userEvent.type(screen.getByLabelText("Customer code"), "ACME");
    await userEvent.type(screen.getByLabelText("Customer name"), "ACME Industries");
    await userEvent.click(screen.getByRole("button", { name: "Create customer" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Sales data unavailable");
    expect(navigate).not.toHaveBeenCalled();
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

  it("guards browser unload only while dirty and clears the guard after save", async () => {
    vi.mocked(salesService.createCustomer).mockResolvedValue(customer);
    renderForm(<CustomerForm />);

    const cleanEvent = new Event("beforeunload", { cancelable: true });
    const cleanPrevent = vi.spyOn(cleanEvent, "preventDefault");
    window.dispatchEvent(cleanEvent);
    expect(cleanPrevent).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText("Customer code"), "ACME");
    const dirtyEvent = new Event("beforeunload", { cancelable: true });
    const dirtyPrevent = vi.spyOn(dirtyEvent, "preventDefault");
    window.dispatchEvent(dirtyEvent);
    expect(dirtyPrevent).toHaveBeenCalledTimes(1);

    await userEvent.type(screen.getByLabelText("Customer name"), "ACME Industries");
    await userEvent.click(screen.getByRole("button", { name: "Create customer" }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Customer created"));

    const submittedEvent = new Event("beforeunload", { cancelable: true });
    const submittedPrevent = vi.spyOn(submittedEvent, "preventDefault");
    window.dispatchEvent(submittedEvent);
    expect(submittedPrevent).not.toHaveBeenCalled();
  });

  it("does not submit invalid forms or duplicate a submit while a save is pending", async () => {
    let resolveCreate: (saved: Customer) => void = () => undefined;
    vi.mocked(salesService.createCustomer).mockImplementation(
      () =>
        new Promise<Customer>((resolve) => {
          resolveCreate = resolve;
        })
    );
    const { container } = renderForm(<CustomerForm />);
    const form = container.querySelector("form");
    if (!form) throw new Error("Customer form was not rendered.");

    await userEvent.type(screen.getByLabelText("Customer code"), "ACME");
    await userEvent.type(screen.getByLabelText("Customer name"), "ACME Industries");

    fireEvent.change(screen.getByLabelText("Credit limit"), { target: { value: "-5" } });
    fireEvent.submit(form);
    expect(salesService.createCustomer).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Credit limit"), { target: { value: "25" } });
    await userEvent.click(screen.getByRole("button", { name: "Create customer" }));
    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();

    fireEvent.submit(form);
    expect(salesService.createCustomer).toHaveBeenCalledTimes(1);

    resolveCreate(customer);
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith("/sales-management/customers/customer-1")
    );
  });

  it("updates existing customers with expected version and guards dirty cancel navigation", async () => {
    vi.mocked(salesService.updateCustomer).mockResolvedValue({
      ...customer,
      customer_name: "ACME Renewed",
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderForm(<CustomerForm customer={customer} />);

    expect(screen.getByRole("heading", { name: "Edit customer" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("buyer@example.com");
    expect(screen.getByLabelText("Phone")).toHaveValue("555-0100");
    expect(screen.getByLabelText("Address")).toHaveValue("1 Main Street");
    expect(screen.getByLabelText("Active customer")).toBeChecked();

    await userEvent.clear(screen.getByLabelText("Customer name"));
    await userEvent.type(screen.getByLabelText("Customer name"), "ACME Renewed");
    await userEvent.clear(screen.getByLabelText("Email"));
    await userEvent.type(screen.getByLabelText("Email"), "renewed@example.com");
    await userEvent.clear(screen.getByLabelText("Phone"));
    await userEvent.type(screen.getByLabelText("Phone"), "555-0101");
    await userEvent.clear(screen.getByLabelText("Address"));
    await userEvent.type(screen.getByLabelText("Address"), "2 Main Street");
    await userEvent.click(screen.getByLabelText("Active customer"));
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
        expect.objectContaining({
          customer_name: "ACME Renewed",
          email: "renewed@example.com",
          phone: "555-0101",
          address: "2 Main Street",
          is_active: false,
          expected_version: 9,
        })
      )
    );
    expect(toastSuccess).toHaveBeenCalledWith("Customer updated");
    expect(navigate).toHaveBeenCalledWith("/sales-management/customers/customer-1");
    confirm.mockRestore();
  });

  it("renders optional create fields as empty controlled values", () => {
    renderForm(<CustomerForm />);

    expect(screen.getByLabelText("Email")).toHaveValue("");
    expect(screen.getByLabelText("Phone")).toHaveValue("");
    expect(screen.getByLabelText("Address")).toHaveValue("");
    expect(screen.getByLabelText("Credit limit")).toHaveValue("");
    expect(screen.getByLabelText("Active customer")).toBeChecked();
  });
});
