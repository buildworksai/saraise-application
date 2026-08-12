/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- document form tests exercise broad governed form behavior through mocked sales services. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type * as ReactRouter from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Customer,
  DeliveryNote,
  Quotation,
  SalesConfiguration,
  SalesOrder,
} from "../contracts";
import { salesService } from "../services/sales-service";
import { CommercialDocumentForm, DeliveryDocumentForm } from "./DocumentForms";

const navigate = vi.hoisted(() => vi.fn());

vi.mock("react-router-dom", async (importOriginal) => {
  const actual: typeof ReactRouter = await importOriginal();
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

vi.mock("../services/sales-service", () => ({
  salesQueryKeys: {
    all: ["sales-management"],
    configuration: () => ["sales-management", "configuration"],
    customers: (filters = {}) => ["sales-management", "customers", filters],
    quotations: () => ["sales-management", "quotations"],
    orders: (filters = {}) => ["sales-management", "orders", filters],
    order: (id: string) => ["sales-management", "order", id],
    deliveries: () => ["sales-management", "deliveries"],
  },
  salesService: {
    getConfiguration: vi.fn(),
    listCustomers: vi.fn(),
    listOrders: vi.fn(),
    getOrder: vi.fn(),
    previewQuotation: vi.fn(),
    createQuotation: vi.fn(),
    updateQuotation: vi.fn(),
    createOrder: vi.fn(),
    updateOrder: vi.fn(),
    createDeliveryNote: vi.fn(),
    updateDeliveryNote: vi.fn(),
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
const configuration: SalesConfiguration = {
  ...mutable,
  id: "config-1",
  environment: "development",
  default_currency: "USD",
  currency_decimal_places: 2,
  rounding_mode: "ROUND_HALF_UP",
  quotation_validity_days: 30,
  credit_check_enabled: true,
  inventory_confirmation_required: false,
  manual_discount_enabled: false,
  maximum_manual_discount_percent: "10",
  manual_tax_enabled: false,
  quotation_prefix: "QT",
  order_prefix: "SO",
  delivery_prefix: "DN",
  sequence_padding: 5,
  version: 2,
  lock_version: 2,
};
const customer: Customer = {
  ...mutable,
  id: "customer-1",
  customer_code: "ACME",
  customer_name: "ACME Industries",
  email: "buyer@example.com",
  phone: "555-0100",
  address: "1 Main Street",
  credit_limit: "1000.00",
  currency: "USD",
  is_active: true,
  lock_version: 1,
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
  lines: [
    {
      ...mutable,
      id: "quote-line-1",
      quotation: "quote-1",
      line_number: 1,
      item_id: null,
      item_code: "SKU-1",
      item_name: "Widget",
      description: "",
      quantity: "1",
      unit_price: "100",
      discount_percent: "0",
      gross_amount: "100.00",
      discount_amount: "0.00",
      tax_amount: "0.00",
      line_total: "100.00",
      lock_version: 1,
    },
  ],
  allowed_commands: ["send"],
  capabilities: [],
  lock_version: 4,
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
  lines: [
    {
      ...mutable,
      id: "order-line-1",
      sales_order: "order-1",
      source_quotation_line_id: null,
      line_number: 1,
      item_id: null,
      item_code: "SKU-1",
      item_name: "Widget",
      description: "",
      quantity: "1",
      unit_price: "100",
      discount_percent: "0",
      gross_amount: "100.00",
      discount_amount: "0.00",
      tax_amount: "0.00",
      total_price: "100.00",
      delivered_quantity: "0",
      lock_version: 1,
    },
  ],
  delivery_notes: [],
  allowed_commands: ["confirm"],
  capabilities: [],
  lock_version: 6,
};
const deliveryOrder: SalesOrder = { ...order, status: "confirmed" };
const deliveryNote: DeliveryNote = {
  ...mutable,
  id: "delivery-1",
  delivery_number: "DN-1",
  delivery_date: "2026-08-01",
  sales_order: "order-1",
  order_number: "SO-1",
  warehouse_id: null,
  carrier_name: "DHL",
  tracking_number: "TRACK-1",
  proof_document_id: null,
  status: "draft",
  notes: "",
  transition_history: [],
  lines: [
    {
      ...mutable,
      id: "delivery-line-1",
      delivery_note: "delivery-1",
      sales_order_line: "order-line-1",
      line_number: 1,
      item_id: null,
      quantity_delivered: "1",
      batch_number: "",
      serial_number: "",
      lock_version: 1,
    },
  ],
  allowed_commands: ["complete"],
  capabilities: [],
  lock_version: 1,
};

function page<T>(data: T[]) {
  return {
    data,
    meta: {
      correlation_id: "corr-sales-documents",
      timestamp: stamp,
      pagination: {
        page: 1,
        page_size: 25,
        count: data.length,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
    },
  };
}

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

describe("CommercialDocumentForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "idem-document") });
    vi.mocked(salesService.getConfiguration).mockResolvedValue(configuration);
    vi.mocked(salesService.listCustomers).mockResolvedValue(page([customer]));
    vi.mocked(salesService.listOrders).mockResolvedValue(page([deliveryOrder]));
    vi.mocked(salesService.getOrder).mockResolvedValue(deliveryOrder);
  });

  it("validates quotations, previews server totals, and creates an idempotent draft", async () => {
    vi.mocked(salesService.previewQuotation).mockResolvedValue({
      subtotal_amount: "100.00",
      discount_amount: "0.00",
      tax_amount: "0.00",
      total_amount: "100.00",
      lines: [
        {
          line_number: 1,
          gross_amount: "100.00",
          discount_amount: "0.00",
          tax_amount: "0.00",
          line_total: "100.00",
        },
      ],
    });
    vi.mocked(salesService.createQuotation).mockResolvedValue(quotation);
    renderForm(<CommercialDocumentForm kind="quotation" />);

    expect(await screen.findByText(/Manual discounts are disabled/u)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create draft" })).toBeDisabled();
    expect(screen.getByText("Select a customer.")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Customer"), "customer-1");
    await userEvent.clear(screen.getByLabelText("Valid until"));
    await userEvent.type(screen.getByLabelText("Valid until"), "2026-08-31");
    await userEvent.type(screen.getByLabelText("Item code"), "SKU-1");
    await userEvent.type(screen.getByLabelText("Item name"), "Widget");
    await userEvent.clear(screen.getByLabelText("Unit price"));
    await userEvent.type(screen.getByLabelText("Unit price"), "100");
    expect(screen.getByLabelText("Discount %")).toBeDisabled();
    expect(screen.getByLabelText("Tax amount")).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Preview totals" }));
    expect(await screen.findAllByText("USD 100.00")).toHaveLength(2);
    expect(salesService.previewQuotation).toHaveBeenCalledWith(
      expect.objectContaining({
        customer: "customer-1",
        valid_until: "2026-08-31",
        lines: [expect.objectContaining({ item_code: "SKU-1", line_number: 1 })],
      })
    );

    await userEvent.click(screen.getByRole("button", { name: "Add line" }));
    expect(screen.getByRole("button", { name: "Create draft" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Remove line 2" }));
    await userEvent.click(screen.getByRole("button", { name: "Create draft" }));

    await waitFor(() =>
      expect(salesService.createQuotation).toHaveBeenCalledWith(
        expect.objectContaining({
          customer: "customer-1",
          currency: "USD",
          lines: [expect.objectContaining({ item_name: "Widget" })],
        }),
        "idem-document"
      )
    );
    expect(navigate).toHaveBeenCalledWith("/sales-management/quotations/quote-1");
  });

  it("updates sales order drafts with expected version and guarded cancel navigation", async () => {
    vi.mocked(salesService.updateOrder).mockResolvedValue(order);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderForm(<CommercialDocumentForm kind="order" document={order} />);

    expect(await screen.findByDisplayValue("Widget")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Warehouse reference"), "warehouse-1");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalledWith("Discard unsaved changes?");
    expect(navigate).not.toHaveBeenCalledWith("/sales-management/sales-orders");

    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(navigate).toHaveBeenCalledWith("/sales-management/sales-orders");

    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() =>
      expect(salesService.updateOrder).toHaveBeenCalledWith(
        "order-1",
        expect.objectContaining({
          expected_version: 6,
          warehouse_id: "warehouse-1",
          lines: [expect.objectContaining({ item_code: "SKU-1" })],
        })
      )
    );
    expect(navigate).toHaveBeenCalledWith("/sales-management/sales-orders/order-1");
    confirm.mockRestore();
  });

  it("creates delivery drafts from eligible order lines with over-delivery guardrails", async () => {
    vi.mocked(salesService.createDeliveryNote).mockResolvedValue(deliveryNote);
    renderForm(<DeliveryDocumentForm />);

    expect(
      await screen.findByText("Select an order to load real remaining quantities.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save delivery draft" })).toBeDisabled();

    await userEvent.selectOptions(screen.getByLabelText("Sales order"), "order-1");
    expect(await screen.findByText("SKU-1 · Widget")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Select Widget"));
    await userEvent.clear(screen.getByLabelText("Deliver"));
    await userEvent.type(screen.getByLabelText("Deliver"), "2");
    expect(
      screen.getByText("Quantity for Widget exceeds the remaining deliverable amount.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save delivery draft" })).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("Deliver"));
    await userEvent.type(screen.getByLabelText("Deliver"), "1");
    await userEvent.type(screen.getByLabelText("Tracking number"), "TRACK-1");
    expect(
      screen.getByText("Carrier name is required when a tracking number is supplied.")
    ).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Carrier"), "DHL");
    await userEvent.click(screen.getByRole("button", { name: "Save delivery draft" }));
    await waitFor(() =>
      expect(salesService.createDeliveryNote).toHaveBeenCalledWith(
        expect.objectContaining({
          sales_order: "order-1",
          carrier_name: "DHL",
          tracking_number: "TRACK-1",
          lines: [
            expect.objectContaining({
              sales_order_line: "order-line-1",
              quantity_delivered: "1",
              line_number: 1,
            }),
          ],
        }),
        "idem-document"
      )
    );
    expect(navigate).toHaveBeenCalledWith("/sales-management/deliveries/delivery-1");
  });
});
