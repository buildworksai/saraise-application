/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- page tests assert routed service lookups and dense list/detail workflow wiring. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiV2Page, Customer, DeliveryNote, Quotation, SalesOrder } from "../contracts";
import { CreateDeliveryNotePage } from "./CreateDeliveryNotePage";
import { CreateQuotationPage } from "./CreateQuotationPage";
import { CreateSalesOrderPage } from "./CreateSalesOrderPage";
import { CustomerDetailPage } from "./CustomerDetailPage";
import { CustomerListPage } from "./CustomerListPage";
import { DeliveryNoteDetailPage } from "./DeliveryNoteDetailPage";
import { DeliveryNoteListPage } from "./DeliveryNoteListPage";
import { EditDeliveryNotePage } from "./EditDeliveryNotePage";
import { EditQuotationPage } from "./EditQuotationPage";
import { EditSalesOrderPage } from "./EditSalesOrderPage";
import { QuotationDetailPage } from "./QuotationDetailPage";
import { QuotationListPage } from "./QuotationListPage";
import { SalesOrderDetailPage } from "./SalesOrderDetailPage";
import { SalesOrderListPage } from "./SalesOrderListPage";
import { salesService } from "../services/sales-service";

vi.mock("../components/DocumentForms", () => ({
  CommercialDocumentForm: ({
    kind,
    document,
  }: {
    kind: "quotation" | "order";
    document?: { id: string };
  }) => <p>{`${document ? "edit" : "create"}-${kind}-${document?.id ?? "new"}`}</p>,
  DeliveryDocumentForm: ({ document }: { document?: { id: string } }) => (
    <p>{`${document ? "edit" : "create"}-delivery-${document?.id ?? "new"}`}</p>
  ),
}));

vi.mock("../services/sales-service", () => ({
  salesQueryKeys: {
    quotation: (id: string) => ["sales-management", "quotation", id],
    order: (id: string) => ["sales-management", "order", id],
    delivery: (id: string) => ["sales-management", "delivery", id],
    all: ["sales-management"],
    customers: (filters: unknown) => ["sales-management", "customers", filters],
    customer: (id: string) => ["sales-management", "customer", id],
    quotations: (filters: unknown) => ["sales-management", "quotations", filters],
    orders: (filters: unknown) => ["sales-management", "orders", filters],
    deliveries: (filters: unknown) => ["sales-management", "deliveries", filters],
  },
  salesService: {
    deleteCustomer: vi.fn(),
    deliveryCommand: vi.fn(),
    getCustomer: vi.fn(),
    getQuotation: vi.fn(),
    getOrder: vi.fn(),
    getDeliveryNote: vi.fn(),
    listCustomers: vi.fn(),
    listDeliveryNotes: vi.fn(),
    listOrders: vi.fn(),
    listQuotations: vi.fn(),
    orderCommand: vi.fn(),
    quotationCommand: vi.fn(),
  },
}));

const stamp = "2026-07-31T00:00:00Z";
const mutable = {
  tenant_id: "tenant-1",
  created_at: stamp,
  updated_at: stamp,
  created_by: "user-1",
  updated_by: "user-1",
  deleted_at: null,
  deleted_by: null,
};
const pageMeta = {
  correlation_id: "corr-sales-page",
  timestamp: stamp,
  pagination: {
    count: 1,
    page: 1,
    page_size: 25,
    total_pages: 1,
    has_next: false,
    has_previous: false,
  },
};
function page<T>(data: readonly T[]): ApiV2Page<T> {
  return { data: [...data], meta: { ...pageMeta, pagination: { ...pageMeta.pagination } } };
}
const customer: Customer = {
  ...mutable,
  id: "customer-1",
  customer_code: "ACME",
  customer_name: "ACME Industries",
  email: "buyer@example.com",
  phone: "+1 555 0100",
  address: "1 Market St",
  credit_limit: "5000.00",
  currency: "USD",
  is_active: true,
  lock_version: 4,
};
const quotation: Quotation = {
  ...mutable,
  id: "quote-1",
  quotation_number: "QT-1",
  quotation_date: "2026-07-31",
  valid_until: "2026-08-31",
  customer: "customer-1",
  customer_name: "ACME Industries",
  currency: "USD",
  subtotal_amount: "100.00",
  discount_amount: "0.00",
  tax_amount: "0.00",
  total_amount: "100.00",
  status: "draft",
  revision_number: 1,
  revision_of: null,
  notes: "",
  transition_history: [],
  lines: [],
  allowed_commands: [],
  capabilities: [],
  lock_version: 1,
};
const order: SalesOrder = {
  ...mutable,
  id: "order-1",
  order_number: "SO-1",
  order_date: "2026-07-31",
  delivery_date: null,
  customer: "customer-1",
  customer_name: "ACME Industries",
  quotation: null,
  currency: "USD",
  subtotal_amount: "100.00",
  discount_amount: "0.00",
  tax_amount: "0.00",
  total_amount: "100.00",
  status: "draft",
  warehouse_id: null,
  external_invoice_id: null,
  notes: "",
  transition_history: [],
  lines: [],
  delivery_notes: [],
  allowed_commands: [],
  capabilities: [],
  lock_version: 1,
};
const delivery: DeliveryNote = {
  ...mutable,
  id: "delivery-1",
  delivery_number: "DN-1",
  delivery_date: "2026-08-01",
  sales_order: "order-1",
  order_number: "SO-1",
  warehouse_id: null,
  carrier_name: "",
  tracking_number: "",
  proof_document_id: null,
  status: "draft",
  notes: "",
  transition_history: [],
  lines: [],
  allowed_commands: [],
  capabilities: [],
  lock_version: 1,
};

function renderRoute(
  element: ReactElement,
  route = "/resource/resource-1",
  path = "/resource/:id"
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={element} />
          <Route path="/sales-management/customers" element={<p>customers route</p>} />
          <Route
            path="/sales-management/quotations/:id/edit"
            element={<p>quotation edit route</p>}
          />
          <Route path="/sales-management/sales-orders/:id/edit" element={<p>order edit route</p>} />
          <Route
            path="/sales-management/deliveries/:id/edit"
            element={<p>delivery edit route</p>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("sales document pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "sales-command-key" });
    vi.mocked(salesService.listCustomers).mockResolvedValue(page([customer]));
    vi.mocked(salesService.listQuotations).mockResolvedValue(page([quotation]));
    vi.mocked(salesService.listOrders).mockResolvedValue(page([order]));
    vi.mocked(salesService.listDeliveryNotes).mockResolvedValue(page([delivery]));
    vi.mocked(salesService.getCustomer).mockResolvedValue(customer);
    vi.mocked(salesService.getQuotation).mockResolvedValue(quotation);
    vi.mocked(salesService.getOrder).mockResolvedValue(order);
    vi.mocked(salesService.getDeliveryNote).mockResolvedValue(delivery);
    vi.mocked(salesService.deleteCustomer).mockResolvedValue(undefined);
    vi.mocked(salesService.quotationCommand).mockResolvedValue(quotation);
    vi.mocked(salesService.orderCommand).mockResolvedValue({ resource: order, command: "confirm" });
    vi.mocked(salesService.deliveryCommand).mockResolvedValue({
      resource: delivery,
      command: "complete",
    });
  });

  it("wires create pages to the correct document forms", () => {
    renderRoute(
      <>
        <CreateQuotationPage />
        <CreateSalesOrderPage />
        <CreateDeliveryNotePage />
      </>
    );

    expect(screen.getByText("create-quotation-new")).toBeInTheDocument();
    expect(screen.getByText("create-order-new")).toBeInTheDocument();
    expect(screen.getByText("create-delivery-new")).toBeInTheDocument();
  });

  it("loads draft quotations before rendering edit forms", async () => {
    vi.mocked(salesService.getQuotation).mockResolvedValue(quotation);
    renderRoute(<EditQuotationPage />, `/resource/${quotation.id}`);

    expect(await screen.findByText("edit-quotation-quote-1")).toBeInTheDocument();
    expect(salesService.getQuotation).toHaveBeenCalledWith(quotation.id);
  });

  it("loads draft sales orders before rendering edit forms", async () => {
    vi.mocked(salesService.getOrder).mockResolvedValue(order);
    renderRoute(<EditSalesOrderPage />, `/resource/${order.id}`);

    expect(await screen.findByText("edit-order-order-1")).toBeInTheDocument();
    expect(salesService.getOrder).toHaveBeenCalledWith(order.id);
  });

  it("loads draft delivery notes before rendering edit forms", async () => {
    vi.mocked(salesService.getDeliveryNote).mockResolvedValue(delivery);
    renderRoute(<EditDeliveryNotePage />, `/resource/${delivery.id}`);

    expect(await screen.findByText("edit-delivery-delivery-1")).toBeInTheDocument();
    expect(salesService.getDeliveryNote).toHaveBeenCalledWith(delivery.id);
  });

  it("shows governed errors when an edit draft cannot be loaded", async () => {
    vi.mocked(salesService.getQuotation).mockRejectedValue(new Error("network down"));
    renderRoute(<EditQuotationPage />, "/resource/quote-1");

    expect(await screen.findByRole("alert")).toHaveTextContent("Sales data unavailable");
  });

  it("applies customer list filters and reports governed failures", async () => {
    const user = userEvent.setup();
    const list = renderRoute(
      <CustomerListPage />,
      "/sales-management/customers",
      "/sales-management/customers"
    );

    expect(await screen.findByText("ACME Industries")).toBeInTheDocument();
    expect(salesService.listCustomers).toHaveBeenCalledWith({ page: 1, page_size: 25 });
    fireEvent.change(screen.getByPlaceholderText("Search code or name"), {
      target: { value: "ACME" },
    });
    expect(await screen.findByText("ACME Industries")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "false" } });
    expect(await screen.findByText("ACME Industries")).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue("Code A–Z"), { target: { value: "-created_at" } });
    await waitFor(() =>
      expect(salesService.listCustomers).toHaveBeenLastCalledWith({
        is_active: false,
        ordering: "-created_at",
        page: 1,
        page_size: 25,
        search: "ACME",
      })
    );
    list.unmount();

    vi.mocked(salesService.listCustomers).mockClear();
    vi.mocked(salesService.listCustomers).mockRejectedValueOnce(new Error("tenant offline"));
    renderRoute(<CustomerListPage />, "/sales-management/customers", "/sales-management/customers");
    expect(await screen.findByRole("alert")).toHaveTextContent("Sales data unavailable");
    await user.click(screen.getByRole("button", { name: "Try Again" }));
    expect(salesService.listCustomers).toHaveBeenCalledTimes(2);
  });

  it("applies document list filters for quotations, orders, and deliveries", async () => {
    const quotationView = renderRoute(
      <QuotationListPage />,
      "/sales-management/quotations?status=sent&search=QT&page=3",
      "/sales-management/quotations"
    );
    expect(await screen.findByText("QT-1")).toBeInTheDocument();
    expect(salesService.listQuotations).toHaveBeenCalledWith({
      page: 3,
      page_size: 25,
      search: "QT",
      status: "sent",
    });
    quotationView.unmount();

    const orderView = renderRoute(
      <SalesOrderListPage />,
      "/sales-management/sales-orders?status=confirmed&ordering=delivery_date",
      "/sales-management/sales-orders"
    );
    expect(await screen.findByText("SO-1")).toBeInTheDocument();
    expect(salesService.listOrders).toHaveBeenCalledWith({
      ordering: "delivery_date",
      page: 1,
      page_size: 25,
      status: "confirmed",
    });
    orderView.unmount();

    renderRoute(
      <DeliveryNoteListPage />,
      "/sales-management/deliveries?status=completed&search=TRACK",
      "/sales-management/deliveries"
    );
    expect(await screen.findByText("DN-1")).toBeInTheDocument();
    expect(salesService.listDeliveryNotes).toHaveBeenCalledWith({
      page: 1,
      page_size: 25,
      search: "TRACK",
      status: "completed",
    });
  });

  it("archives customers with the current lock version from detail", async () => {
    const user = userEvent.setup();
    renderRoute(
      <CustomerDetailPage />,
      "/sales-management/customers/customer-1",
      "/sales-management/customers/:id"
    );

    expect(await screen.findByText("ACME · ACME Industries")).toBeInTheDocument();
    expect(screen.getByText("Record version")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Archive" }));
    const dialog = await screen.findByRole("dialog", { name: "Archive customer?" });
    await user.click(within(dialog).getByRole("button", { name: "Archive" }));

    expect(salesService.deleteCustomer).toHaveBeenCalledWith("customer-1", 4);
    await screen.findByText("customers route");
  });

  it("runs quotation, order, and delivery detail commands with idempotency evidence", async () => {
    const user = userEvent.setup();
    vi.mocked(salesService.getQuotation).mockResolvedValue({
      ...quotation,
      allowed_commands: ["send", "reject"],
    });
    const quotationView = renderRoute(
      <QuotationDetailPage />,
      "/sales-management/quotations/quote-1",
      "/sales-management/quotations/:id"
    );
    expect(await screen.findByText("Quotation QT-1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reject" }));
    await user.click(await screen.findByRole("button", { name: "Confirm" }));
    expect(salesService.quotationCommand).toHaveBeenCalledWith("quote-1", "reject", {
      idempotency_key: "sales-command-key",
      reason: "Cancelled by an authorized operator.",
    });
    quotationView.unmount();

    vi.mocked(salesService.getOrder).mockResolvedValue({ ...order, allowed_commands: ["confirm"] });
    const orderView = renderRoute(
      <SalesOrderDetailPage />,
      "/sales-management/sales-orders/order-1",
      "/sales-management/sales-orders/:id"
    );
    expect(await screen.findByText("Sales order SO-1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await user.click(await screen.findByRole("button", { name: "Confirm" }));
    expect(salesService.orderCommand).toHaveBeenCalledWith("order-1", "confirm", {
      idempotency_key: "sales-command-key",
    });
    orderView.unmount();

    vi.mocked(salesService.getDeliveryNote).mockResolvedValue({
      ...delivery,
      allowed_commands: ["complete"],
    });
    renderRoute(
      <DeliveryNoteDetailPage />,
      "/sales-management/deliveries/delivery-1",
      "/sales-management/deliveries/:id"
    );
    expect(await screen.findByText("Delivery note DN-1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Complete delivery" }));
    await user.click(await screen.findByRole("button", { name: "Confirm" }));
    expect(salesService.deliveryCommand).toHaveBeenCalledWith("delivery-1", "complete", {
      idempotency_key: "sales-command-key",
    });
  });
});
