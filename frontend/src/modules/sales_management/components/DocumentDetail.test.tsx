/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- document detail tests exercise broad route/query/action branches with mocked service boundaries. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type { DeliveryNote, Quotation, SalesOrder, TransitionRecord } from "../contracts";
import { DocumentDetail } from "./DocumentDetail";
import { salesService } from "../services/sales-service";

vi.mock("../services/sales-service", () => ({
  salesQueryKeys: {
    all: ["sales-management"],
    quotation: (id: string) => ["sales-management", "quotation", id],
    order: (id: string) => ["sales-management", "order", id],
    delivery: (id: string) => ["sales-management", "delivery", id],
  },
  salesService: {
    getQuotation: vi.fn(),
    getOrder: vi.fn(),
    getDeliveryNote: vi.fn(),
    quotationCommand: vi.fn(),
    orderCommand: vi.fn(),
    deliveryCommand: vi.fn(),
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
const transition: TransitionRecord = {
  command: "send",
  from_status: "draft",
  to_status: "sent",
  actor_id: "user-1",
  correlation_id: "corr-sales-transition",
  occurred_at: stamp,
  reason: "Customer requested formal quote.",
};
const quotation: Quotation = {
  ...mutable,
  id: "quote-1",
  quotation_number: "QT-00001",
  quotation_date: "2026-07-31",
  valid_until: "2026-08-30",
  customer: "customer-1",
  customer_name: "ACME Industries",
  currency: "USD",
  subtotal_amount: "100.00",
  discount_amount: "5.00",
  tax_amount: "9.50",
  total_amount: "104.50",
  status: "sent",
  revision_number: 2,
  revision_of: null,
  notes: "Expedited review",
  transition_history: [transition],
  lines: [
    {
      ...mutable,
      id: "quote-line-1",
      quotation: "quote-1",
      line_number: 1,
      item_id: null,
      item_code: "SKU-1",
      item_name: "Widget",
      description: "Widget line",
      quantity: "2",
      unit_price: "50.00",
      discount_percent: "5",
      gross_amount: "100.00",
      discount_amount: "5.00",
      tax_amount: "9.50",
      line_total: "104.50",
      lock_version: 1,
    },
  ],
  allowed_commands: ["accept", "reject", "convert"],
  capabilities: [],
  lock_version: 4,
};
const order: SalesOrder = {
  ...mutable,
  id: "order-1",
  order_number: "SO-00001",
  order_date: "2026-08-01",
  delivery_date: "2026-08-05",
  customer: "customer-1",
  customer_name: "ACME Industries",
  quotation: "quote-1",
  currency: "USD",
  subtotal_amount: "120.00",
  discount_amount: "0.00",
  tax_amount: "12.00",
  total_amount: "132.00",
  status: "confirmed",
  warehouse_id: "warehouse-1",
  external_invoice_id: null,
  notes: "",
  transition_history: [],
  lines: [
    {
      ...mutable,
      id: "order-line-1",
      sales_order: "order-1",
      source_quotation_line_id: "quote-line-1",
      line_number: 1,
      item_id: null,
      item_code: "SKU-1",
      item_name: "Widget",
      description: "",
      quantity: "3",
      unit_price: "40.00",
      discount_percent: "0",
      gross_amount: "120.00",
      discount_amount: "0.00",
      tax_amount: "12.00",
      total_price: "132.00",
      delivered_quantity: "1",
      lock_version: 1,
    },
  ],
  delivery_notes: [
    {
      ...mutable,
      id: "delivery-1",
      delivery_number: "DN-00001",
      delivery_date: "2026-08-02",
      sales_order: "order-1",
      order_number: "SO-00001",
      warehouse_id: "warehouse-1",
      carrier_name: "DHL",
      tracking_number: "TRACK-1",
      proof_document_id: null,
      status: "draft",
      notes: "",
      transition_history: [],
      lines: [],
      allowed_commands: [],
      capabilities: [],
      lock_version: 1,
    },
  ],
  allowed_commands: ["start_picking", "cancel"],
  capabilities: [],
  lock_version: 6,
};
const delivery: DeliveryNote = {
  ...mutable,
  id: "delivery-1",
  delivery_number: "DN-00001",
  delivery_date: "2026-08-02",
  sales_order: "order-1",
  order_number: "SO-00001",
  warehouse_id: "warehouse-1",
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
  allowed_commands: ["complete", "cancel"],
  capabilities: [],
  lock_version: 3,
};

function renderDetail(kind: "quotation" | "order" | "delivery", id = `${kind}-1`) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const path =
    kind === "quotation"
      ? `/sales-management/quotations/${id}`
      : kind === "order"
        ? `/sales-management/orders/${id}`
        : `/sales-management/deliveries/${id}`;
  const route =
    kind === "quotation"
      ? "/sales-management/quotations/:id"
      : kind === "order"
        ? "/sales-management/orders/:id"
        : "/sales-management/deliveries/:id";

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={<DocumentDetail kind={kind} />} />
          <Route path="/sales-management/quotations/:id/edit" element={<p>Edit quotation</p>} />
          <Route path="/sales-management/orders/:id/edit" element={<p>Edit order</p>} />
          <Route path="/sales-management/deliveries/:id/edit" element={<p>Edit delivery</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DocumentDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "idem-sales-detail") });
    vi.mocked(salesService.getQuotation).mockResolvedValue(quotation);
    vi.mocked(salesService.getOrder).mockResolvedValue(order);
    vi.mocked(salesService.getDeliveryNote).mockResolvedValue(delivery);
    vi.mocked(salesService.quotationCommand).mockResolvedValue({
      ...quotation,
      status: "accepted",
    });
    vi.mocked(salesService.orderCommand).mockResolvedValue({
      command: "start-picking",
      resource: { ...order, status: "picking" },
    });
    vi.mocked(salesService.deliveryCommand).mockResolvedValue({
      command: "complete",
      resource: { ...delivery, status: "completed" },
    });
  });

  it("renders governed loading and retryable error states", async () => {
    let rejectLookup: (error: ApiError) => void = (error: ApiError) => {
      void error;
    };
    vi.mocked(salesService.getQuotation).mockImplementation(
      () =>
        new Promise<Quotation>((_resolve, reject) => {
          rejectLookup = reject;
        })
    );
    const person = userEvent.setup();
    renderDetail("quotation", "quote-error");

    expect(screen.getByLabelText("Loading details")).toBeInTheDocument();
    rejectLookup(new ApiError("Denied", 403, undefined, "FORBIDDEN", "corr-sales-denied"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Access denied");
    expect(screen.getByRole("alert")).toHaveTextContent("corr-sales-denied");

    vi.mocked(salesService.getQuotation).mockResolvedValue(quotation);
    await person.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByText("Quotation QT-00001")).toBeInTheDocument();
  });

  it("renders quotation totals, transition evidence, and guarded command payloads", async () => {
    const person = userEvent.setup();
    renderDetail("quotation", "quote-1");

    expect(await screen.findByText("Quotation QT-00001")).toBeInTheDocument();
    expect(screen.getByText("ACME Industries")).toBeInTheDocument();
    expect(screen.getAllByText("104.50")).toHaveLength(2);
    expect(screen.getByText("draft → sent")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit draft" })).toHaveAttribute(
      "href",
      "/sales-management/quotations/quote-1/edit"
    );

    await person.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Confirm Reject?");
    await person.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(salesService.quotationCommand).toHaveBeenCalledWith("quote-1", "reject", {
        idempotency_key: "idem-sales-detail",
        reason: "Cancelled by an authorized operator.",
      });
    });
  });

  it("renders order linkage, delivery progress, and normalizes underscored commands", async () => {
    const person = userEvent.setup();
    renderDetail("order", "order-1");

    expect(await screen.findByText("Sales order SO-00001")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open quotation" })).toHaveAttribute(
      "href",
      "/sales-management/quotations/quote-1"
    );
    expect(screen.getByText("DN-00001")).toHaveAttribute(
      "href",
      "/sales-management/deliveries/delivery-1"
    );
    expect(screen.getByRole("columnheader", { name: "Delivered" })).toBeInTheDocument();
    expect(screen.getAllByText("132.00")).toHaveLength(2);

    await person.click(screen.getByRole("button", { name: "Start picking" }));
    await person.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(salesService.orderCommand).toHaveBeenCalledWith("order-1", "start-picking", {
        idempotency_key: "idem-sales-detail",
      });
    });
  });

  it("renders delivery-specific fields and executes destructive commands with a reason", async () => {
    const person = userEvent.setup();
    renderDetail("delivery", "delivery-1");

    expect(await screen.findByText("Delivery note DN-00001")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "SO-00001" })).toHaveAttribute(
      "href",
      "/sales-management/sales-orders/order-1"
    );
    expect(screen.getByText("DHL")).toBeInTheDocument();
    expect(screen.getByText("TRACK-1")).toBeInTheDocument();
    expect(screen.getByText("warehouse-1")).toBeInTheDocument();
    expect(screen.getByText("order-line-1")).toBeInTheDocument();

    await person.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Confirm Cancel?");
    await person.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(salesService.deliveryCommand).toHaveBeenCalledWith("delivery-1", "cancel", {
        idempotency_key: "idem-sales-detail",
        reason: "Cancelled by an authorized operator.",
      });
    });
  });

  it("shows terminal empty-line and no-command states without exposing actions", async () => {
    vi.mocked(salesService.getQuotation).mockResolvedValue({
      ...quotation,
      status: "converted",
      lines: [],
      allowed_commands: [],
    });

    renderDetail("quotation", "quote-1");

    expect(await screen.findByText("Quotation QT-00001")).toBeInTheDocument();
    expect(screen.getByText("No active lines.")).toBeInTheDocument();
    expect(screen.getByText("No commands are permitted in the current state.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit draft" })).toBeDisabled();
  });
});
