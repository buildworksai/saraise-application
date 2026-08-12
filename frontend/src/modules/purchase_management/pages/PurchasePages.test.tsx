/* eslint-disable max-lines-per-function -- page coverage exercises workspace, configuration, and import workflows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ConfigurationDocument,
  ConfigurationPreview,
  MutationContext,
  ProcurementConfiguration,
  PurchaseOrder,
  Supplier,
} from "../contracts";
import { purchaseService } from "../services/purchase-service";
import { ConfigurationImportPage } from "./ConfigurationImportPage";
import { ConfigurationVersionDetailPage } from "./ConfigurationVersionDetailPage";
import { CreateSupplierPage } from "./CreateSupplierPage";
import { ProcurementSettingsPage } from "./ProcurementSettingsPage";
import { ResourceDetailPage, ResourceFormPage, ResourceListPage } from "./ResourceWorkspace";
import { SupplierDetailPage } from "./SupplierDetailPage";
import { SupplierListPage } from "./SupplierListPage";

vi.mock("../services/purchase-service", () => ({
  purchaseService: {
    activateConfiguration: vi.fn(),
    createConfigurationDraft: vi.fn(),
    createSupplier: vi.fn(),
    exportConfiguration: vi.fn(),
    getActiveConfiguration: vi.fn(),
    getConfigurationVersion: vi.fn(),
    getSupplier: vi.fn(),
    getPurchaseOrder: vi.fn(),
    importConfiguration: vi.fn(),
    listConfigurationVersions: vi.fn(),
    listPurchaseOrders: vi.fn(),
    listSuppliers: vi.fn(),
    previewConfiguration: vi.fn(),
    rollbackConfiguration: vi.fn(),
    updatePurchaseOrder: vi.fn(),
    updateSupplier: vi.fn(),
  },
}));

const service = vi.mocked(purchaseService);

const pagination = {
  count: 1,
  page: 1,
  page_size: 20,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};
const supplier: Supplier = {
  id: "supplier-1",
  lock_version: 5,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  created_by: "operator-1",
  updated_by: "operator-2",
  supplier_code: "SUP-100",
  supplier_name: "Acme Materials",
  email: "ops@example.com",
  phone: "555-0100",
  address: "100 Industrial Way",
  payment_terms: "Net 30",
  currency: "USD",
  status: "active",
  archived_at: null,
  archived_by: null,
};
const configuration: ProcurementConfiguration = {
  id: "config-1",
  lock_version: 9,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  created_by: "operator-1",
  updated_by: "operator-2",
  environment: "development",
  version: 3,
  status: "draft",
  activated_at: null,
  activated_by: null,
  default_currency: "USD",
  default_payment_terms: "Net 30",
  supplier_code_prefix: "SUP",
  requisition_prefix: "REQ",
  rfq_prefix: "RFQ",
  po_prefix: "PO",
  receipt_prefix: "GRN",
  approval_rules: [],
  receipt_tolerance_percent: "0.00",
  minimum_rfq_suppliers: 2,
  quote_scoring_weights: { price: 60, delivery: 20, quality: 10, service: 10 },
  inventory_integration_enabled: false,
  accounting_integration_enabled: false,
  supplier_delivery_enabled: false,
  rollout: { roles: ["buyer"], cohorts: [], percentage: 100 },
};
const preview: ConfigurationPreview = {
  valid: true,
  diff: [{ field: "minimum_rfq_suppliers", before: 2, after: 3 }],
  affected_workflows: ["rfq"],
  simulations: [{ input: { amount: "10000.00" }, approval_required: false, matched_rules: [] }],
  restart_required: false,
};
const document: ConfigurationDocument = {
  schema: "saraise.purchase.configuration.v1",
  configuration: { default_currency: "USD" },
  checksum: "sha256:abc123",
};
const purchaseOrder: PurchaseOrder = {
  id: "po-1",
  lock_version: 7,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  created_by: "operator-1",
  updated_by: "operator-2",
  po_number: "PO-100",
  po_date: "2026-08-01",
  supplier: "supplier-1",
  supplier_name: "Acme Materials",
  expected_delivery_date: "2026-08-10",
  total_amount: "250.00",
  currency: "USD",
  status: "draft",
  requisition: null,
  rfq: null,
  accepted_quote: null,
  payment_terms: "Net 30",
  delivery_terms: "Dock delivery",
  shipping_address: { line1: "100 Industrial Way", city: "Austin" },
  notes: "Stage materials before receipt.",
  dispatch_status: "not_requested",
  dispatch_job_id: null,
  acknowledged_at: null,
  lines: [
    {
      id: "po-line-1",
      lock_version: 1,
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-02T00:00:00Z",
      created_by: "operator-1",
      updated_by: "operator-2",
      line_number: 1,
      item_id: null,
      item_code: "MAT-1",
      item_name: "Material one",
      quantity: "5.00",
      unit_price: "50.00",
      tax_amount: "0.00",
      total_price: "250.00",
      received_quantity: "0.00",
      cancelled_quantity: "0.00",
    },
  ],
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}</output>;
}

function renderPurchase(route: string, element: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/purchase-management/suppliers" element={element} />
          <Route path="/purchase-management/suppliers/new" element={element} />
          <Route path="/purchase-management/suppliers/:id" element={element} />
          <Route path="/purchase-management/purchase-orders" element={element} />
          <Route path="/purchase-management/purchase-orders/:id" element={element} />
          <Route path="/purchase-management/purchase-orders/:id/edit" element={element} />
          <Route path="/purchase-management/settings" element={element} />
          <Route path="/purchase-management/settings/import" element={element} />
          <Route path="/purchase-management/settings/versions/:id" element={element} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("purchase management pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    service.activateConfiguration.mockResolvedValue(configuration);
    service.createConfigurationDraft.mockResolvedValue(configuration);
    service.createSupplier.mockResolvedValue(supplier);
    service.exportConfiguration.mockResolvedValue(document);
    service.getActiveConfiguration.mockResolvedValue(configuration);
    service.getConfigurationVersion.mockResolvedValue(configuration);
    service.getSupplier.mockResolvedValue(supplier);
    service.getPurchaseOrder.mockResolvedValue(purchaseOrder);
    service.importConfiguration.mockResolvedValue(configuration);
    service.listConfigurationVersions.mockResolvedValue({
      items: [configuration],
      meta: { correlation_id: "corr-config", timestamp: "2026-08-02T00:00:00Z", pagination },
    });
    service.listSuppliers.mockResolvedValue({
      items: [supplier],
      meta: { correlation_id: "corr-supplier", timestamp: "2026-08-02T00:00:00Z", pagination },
    });
    service.listPurchaseOrders.mockResolvedValue({
      items: [purchaseOrder],
      meta: { correlation_id: "corr-po", timestamp: "2026-08-02T00:00:00Z", pagination },
    });
    service.previewConfiguration.mockResolvedValue(preview);
    service.rollbackConfiguration.mockResolvedValue(configuration);
    service.updatePurchaseOrder.mockResolvedValue({
      ...purchaseOrder,
      lock_version: 8,
      updated_at: "2026-08-03T00:00:00Z",
      total_amount: "300.00",
      expected_delivery_date: "2026-08-12",
      lines: [],
    });
    service.updateSupplier.mockResolvedValue(supplier);
  });

  it("renders supplier list results, applies filters, resets an empty filtered state, and retries errors", async () => {
    const user = userEvent.setup();
    renderPurchase("/purchase-management/suppliers", <SupplierListPage />);

    expect(await screen.findAllByText("Acme Materials")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Suppliers" })).toBeInTheDocument();

    service.listSuppliers.mockResolvedValueOnce({
      items: [],
      meta: {
        correlation_id: "corr-empty",
        timestamp: "2026-08-02T00:00:00Z",
        pagination: { ...pagination, count: 0 },
      },
    });
    fireEvent.change(screen.getByPlaceholderText("Search suppliers"), {
      target: { value: "missing" },
    });
    expect(await screen.findByText("No records match these filters")).toBeInTheDocument();
    expect(service.listSuppliers).toHaveBeenLastCalledWith(
      expect.objectContaining({
        search: "missing",
        status: "",
        page: 1,
        ordering: "supplier_name",
      })
    );

    service.listSuppliers.mockResolvedValueOnce({
      items: [supplier],
      meta: { correlation_id: "corr-reset", timestamp: "2026-08-02T00:00:00Z", pagination },
    });
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(await screen.findAllByText("Acme Materials")).toHaveLength(2);

    service.listSuppliers
      .mockRejectedValueOnce(new Error("supplier service unavailable"))
      .mockResolvedValueOnce({
        items: [supplier],
        meta: {
          correlation_id: "corr-retry",
          timestamp: "2026-08-02T00:00:00Z",
          pagination,
        },
      });
    await user.selectOptions(screen.getByLabelText("Status filter"), "archived");
    expect(await screen.findByRole("alert")).toHaveTextContent("supplier service unavailable");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findAllByText("Acme Materials")).toHaveLength(2);
  });

  it("shows supplier detail evidence and hides edit for non-draft statuses", async () => {
    renderPurchase("/purchase-management/suppliers/supplier-1", <SupplierDetailPage />);

    expect(await screen.findByRole("heading", { name: "Acme Materials" })).toBeInTheDocument();
    expect(screen.getAllByText("SUP-100")).toHaveLength(2);
    expect(screen.getByText("Immutable activity")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("validates supplier JSON before submit and sends idempotent create requests", async () => {
    const user = userEvent.setup();
    renderPurchase("/purchase-management/suppliers/new", <CreateSupplierPage />);

    const editor = await screen.findByLabelText("Fields and itemized lines (JSON)");
    fireEvent.change(editor, { target: { value: "{" } });
    await user.click(screen.getByRole("button", { name: "Validate and save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Expected property name");
    expect(service.createSupplier).not.toHaveBeenCalled();

    fireEvent.change(editor, {
      target: {
        value: JSON.stringify({
          supplier_code: "SUP-200",
          supplier_name: "BuildCo",
          payment_terms: "Net 45",
          currency: "USD",
        }),
      },
    });
    await user.click(screen.getByRole("button", { name: "Validate and save" }));

    await waitFor(() => expect(service.createSupplier).toHaveBeenCalledOnce());
    const [supplierPayload, supplierContext] = service.createSupplier.mock.calls[0]!;
    expect(supplierPayload).toEqual(
      expect.objectContaining({ supplier_code: "SUP-200", supplier_name: "BuildCo" })
    );
    expect(typeof supplierContext.idempotencyKey).toBe("string");
    await waitFor(() =>
      expect(screen.getByLabelText("location")).toHaveTextContent(
        "/purchase-management/suppliers/supplier-1"
      )
    );
  });

  it("previews, exports, and drafts procurement settings changes", async () => {
    const user = userEvent.setup();
    renderPurchase("/purchase-management/settings", <ProcurementSettingsPage />);

    const editor = await screen.findByLabelText("Configuration document");
    expect((editor as HTMLTextAreaElement).value).toContain('"supplier_code_prefix": "SUP"');

    await user.click(screen.getByRole("button", { name: "Preview and simulate" }));
    await waitFor(() => {
      expect(service.previewConfiguration).toHaveBeenCalledWith(
        "development",
        expect.objectContaining({ default_currency: "USD" }),
        [{ amount: "10000.00", category: "general" }]
      );
    });
    expect(
      screen.getAllByText(
        (_, element) =>
          element?.tagName === "PRE" &&
          Boolean(element.textContent?.includes("minimum_rfq_suppliers"))
      )
    ).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Save immutable draft version" }));
    await waitFor(() => expect(service.createConfigurationDraft).toHaveBeenCalledOnce());
    const [draftEnvironment, draftPayload, draftContext] =
      service.createConfigurationDraft.mock.calls[0]!;
    expect(draftEnvironment).toBe("development");
    expect(draftPayload).toEqual(expect.objectContaining({ default_payment_terms: "Net 30" }));
    expect(typeof draftContext.idempotencyKey).toBe("string");
    await user.click(screen.getByRole("button", { name: "Export" }));
    expect(service.exportConfiguration).toHaveBeenCalledWith("development");
  });

  it("imports only checksummed configuration documents and supports version activation and rollback", async () => {
    const user = userEvent.setup();
    const { unmount } = renderPurchase(
      "/purchase-management/settings/import",
      <ConfigurationImportPage />
    );

    fireEvent.change(screen.getByLabelText("Configuration import document"), {
      target: { value: "{}" },
    });
    await user.click(screen.getByRole("button", { name: "Validate and create draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A supported schema and checksum are required."
    );

    fireEvent.change(screen.getByLabelText("Configuration import document"), {
      target: { value: JSON.stringify(document) },
    });
    await user.click(screen.getByRole("button", { name: "Validate and create draft" }));
    await waitFor(() => expect(service.importConfiguration).toHaveBeenCalledOnce());
    const [importedDocument, importContext] = service.importConfiguration.mock.calls[0] as [
      ConfigurationDocument,
      MutationContext,
    ];
    expect(importedDocument).toEqual(document);
    expect(typeof importContext.idempotencyKey).toBe("string");
    await waitFor(() =>
      expect(screen.getAllByLabelText("location").at(-1)).toHaveTextContent(
        "/purchase-management/settings/versions/config-1"
      )
    );
    unmount();

    renderPurchase(
      "/purchase-management/settings/versions/config-1",
      <ConfigurationVersionDetailPage />
    );
    expect(await screen.findByText("Version 3 · draft")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Activate after review" }));
    await user.click(screen.getByRole("button", { name: "Create rollback version" }));

    const [activateId, activateReason, activateContext] = service.activateConfiguration.mock
      .calls[0] as [string, string, MutationContext];
    expect(activateId).toBe("config-1");
    expect(activateReason).toBe("Reviewed and approved in configuration console");
    expect(activateContext.lockVersion).toBe(9);
    expect(typeof activateContext.idempotencyKey).toBe("string");

    const [rollbackId, rollbackReason, rollbackContext] = service.rollbackConfiguration.mock
      .calls[0] as [string, string, MutationContext];
    expect(rollbackId).toBe("config-1");
    expect(rollbackReason).toBe("Operator rollback to selected evidence version");
    expect(typeof rollbackContext.idempotencyKey).toBe("string");
  });

  it("exercises the shared ResourceWorkspace list, detail evidence, and edit payloads", async () => {
    const user = userEvent.setup();
    const rendered = renderPurchase(
      "/purchase-management/purchase-orders",
      <ResourceListPage kind="orders" />
    );

    expect(await screen.findByRole("heading", { name: "Purchase orders" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Acme Materials" })).toHaveAttribute(
      "href",
      "/purchase-management/purchase-orders/po-1"
    );
    expect(screen.getByText("250.00")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Search purchase orders"), {
      target: { value: "PO-100" },
    });
    await user.selectOptions(screen.getByLabelText("Status filter"), "draft");
    await waitFor(() =>
      expect(service.listPurchaseOrders).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "PO-100", status: "draft", page: 1 })
      )
    );
    rendered.unmount();

    const detail = renderPurchase(
      "/purchase-management/purchase-orders/po-1",
      <ResourceDetailPage kind="orders" />
    );
    expect(await screen.findByRole("heading", { name: "Acme Materials" })).toBeInTheDocument();
    expect(screen.getByText("PO-100")).toBeInTheDocument();
    expect(screen.getByText("Summary and line evidence")).toBeInTheDocument();
    expect(screen.getByText(/MAT-1/u)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit" })).toHaveAttribute(
      "href",
      "/purchase-management/purchase-orders/po-1/edit"
    );
    detail.unmount();

    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000888");
    renderPurchase(
      "/purchase-management/purchase-orders/po-1/edit",
      <ResourceFormPage kind="orders" edit />
    );
    const editor = await screen.findByLabelText("Fields and itemized lines (JSON)");
    fireEvent.change(editor, { target: { value: "[]" } });
    await user.click(screen.getByRole("button", { name: "Validate and save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The document must be a JSON object."
    );
    expect(service.updatePurchaseOrder).not.toHaveBeenCalled();

    fireEvent.change(editor, {
      target: {
        value: JSON.stringify({
          po_number: "PO-100",
          supplier_id: "supplier-1",
          currency: "USD",
          total_amount: "300.00",
          expected_delivery_date: "2026-08-12",
          lines: [],
        }),
      },
    });
    await user.click(screen.getByRole("button", { name: "Validate and save" }));
    await waitFor(() => expect(service.updatePurchaseOrder).toHaveBeenCalledOnce());
    const [id, payload, context] = service.updatePurchaseOrder.mock.calls[0]!;
    expect(id).toBe("po-1");
    expect(payload).toEqual(expect.objectContaining({ total_amount: "300.00" }));
    expect(context).toEqual({
      idempotencyKey: "00000000-0000-4000-8000-000000000888",
      lockVersion: 7,
    });
  });
});
