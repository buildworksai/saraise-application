/* eslint-disable max-lines-per-function, @typescript-eslint/unbound-method -- transport adapter coverage intentionally walks many service methods and asserts Vitest API-client spies. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type * as ApiClientModule from "@/services/api-client";
import { ApiError, apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import { purchaseService } from "./purchase-service";

vi.mock("@/services/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiClientModule>();
  return {
    ...actual,
    apiClient: {
      get: vi.fn(),
      post: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
    },
  };
});

const client = vi.mocked(apiClient);
const context = { idempotencyKey: "idem-purchase", lockVersion: 7 };
const stamp = "2026-08-04T00:00:00Z";
const data = { id: "resource-1", lock_version: 7 };

function envelope<T>(value: T) {
  return { data: value, meta: { correlation_id: "corr-purchase", timestamp: stamp } };
}

function page<T>(items: T[]) {
  return {
    data: items,
    meta: {
      correlation_id: "corr-purchase",
      timestamp: stamp,
      pagination: {
        count: items.length,
        page: 1,
        page_size: 25,
        total_pages: 1,
        has_next: false,
        has_previous: false,
      },
    },
  };
}

describe("purchaseService transport adapter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    client.get.mockResolvedValue(envelope(data));
    client.post.mockResolvedValue(envelope(data));
    client.patch.mockResolvedValue(envelope(data));
    client.delete.mockResolvedValue(envelope(data));
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000777");
  });

  it("normalizes list filters into query strings and unwraps paginated envelopes", async () => {
    client.get.mockResolvedValueOnce(page([{ id: "supplier-1" }]));

    const result = await purchaseService.listSuppliers({
      search: "acme",
      status: "active",
      page: 2,
      page_size: 50,
      ordering: "",
    });

    expect(client.get).toHaveBeenCalledWith(
      `${ENDPOINTS.SUPPLIERS.LIST}?search=acme&status=active&page=2&page_size=50`
    );
    expect(result.items).toEqual([{ id: "supplier-1" }]);
    expect(result.meta.correlation_id).toBe("corr-purchase");
  });

  it("sends mutation headers, lock versions, and delete reasons through the shared client", async () => {
    await purchaseService.createSupplier(
      { supplier_code: "SUP-1", supplier_name: "Acme", payment_terms: "Net 30", currency: "USD" },
      context
    );
    expect(client.post).toHaveBeenLastCalledWith(
      ENDPOINTS.SUPPLIERS.CREATE,
      { supplier_code: "SUP-1", supplier_name: "Acme", payment_terms: "Net 30", currency: "USD" },
      { headers: { "Idempotency-Key": "idem-purchase", "If-Match": "7" } }
    );

    await purchaseService.updateSupplier("supplier-1", { supplier_name: "Acme Updated" }, context);
    expect(client.patch).toHaveBeenLastCalledWith(
      ENDPOINTS.SUPPLIERS.UPDATE("supplier-1"),
      { supplier_name: "Acme Updated" },
      { headers: { "Idempotency-Key": "idem-purchase", "If-Match": "7" } }
    );

    await purchaseService.archiveSupplier("supplier-1", "duplicate", context);
    expect(client.delete).toHaveBeenLastCalledWith(ENDPOINTS.SUPPLIERS.DELETE("supplier-1"), {
      headers: { "Idempotency-Key": "idem-purchase", "If-Match": "7" },
      body: JSON.stringify({ reason: "duplicate" }),
    });
  });

  it("covers governed requisition, RFQ, quote, order, receipt, configuration, job, and health endpoints", async () => {
    client.get.mockResolvedValue(page([data]));
    const line = [
      {
        item_code: "ITM-1",
        item_name: "Bolt",
        description: "Bolt",
        quantity: "2.00",
        unit_price: "3.00",
      },
    ];

    await purchaseService.getSupplier("supplier-1");
    await purchaseService.activateSupplier("supplier-1", "restored", context);
    await purchaseService.deactivateSupplier("supplier-1", "risk", context);
    await purchaseService.listRequisitions({ status: "draft" });
    await purchaseService.getRequisition("req-1");
    await purchaseService.createRequisition(
      {
        requisition_date: "2026-08-04",
        required_date: "2026-08-10",
        purpose: "stock",
        currency: "USD",
        lines: [
          {
            item_code: "ITM-1",
            description: "Bolt",
            quantity: "2.00",
            estimated_unit_price: "3.00",
          },
        ],
      },
      context
    );
    await purchaseService.updateRequisition("req-1", { purpose: "critical stock" }, context);
    await purchaseService.deleteRequisition("req-1", "obsolete", context);
    await purchaseService.submitRequisition("req-1", context);
    await purchaseService.approveRequisition("req-1", context);
    await purchaseService.rejectRequisition("req-1", "over budget", context);
    await purchaseService.reviseRequisition("req-1", context);
    await purchaseService.cancelRequisition("req-1", context);
    await purchaseService.convertRequisition("req-1", "supplier-1", line, context);
    await purchaseService.listRFQs({ status: "open" });
    await purchaseService.getRFQ("rfq-1");
    await purchaseService.createRFQ(
      {
        title: "Fasteners",
        issue_date: "2026-08-04",
        submission_deadline: "2026-08-08",
        currency: "USD",
        lines: [
          {
            item_code: "ITM-1",
            description: "Bolt",
            quantity: "2.00",
            required_date: "2026-08-10",
          },
        ],
      },
      context
    );
    await purchaseService.updateRFQ("rfq-1", { title: "Fasteners updated" }, context);
    await purchaseService.deleteRFQ("rfq-1", "duplicate", context);
    await purchaseService.publishRFQ("rfq-1", ["supplier-1"], context);
    await purchaseService.closeRFQ("rfq-1", context);
    await purchaseService.cancelRFQ("rfq-1", context);
    await purchaseService.compareQuotes("rfq-1");
    await purchaseService.awardQuote("rfq-1", "quote-1", true, context);
    await purchaseService.listQuotes({ status: "submitted" });
    await purchaseService.getQuote("quote-1");
    await purchaseService.createQuote(
      {
        rfq_id: "rfq-1",
        supplier_id: "supplier-1",
        valid_until: "2026-08-30",
        currency: "USD",
        payment_terms: "Net 30",
        lines: [{ rfq_line_id: "rfq-line-1", quantity: "2.00", unit_price: "3.00" }],
      },
      context
    );
    await purchaseService.updateQuote("quote-1", { supplier_notes: "expedited" }, context);
    await purchaseService.deleteQuote("quote-1", "duplicate", context);
    await purchaseService.submitQuote("quote-1", context);
    await purchaseService.withdrawQuote("quote-1", context);
    await purchaseService.listPurchaseOrders({ status: "sent" });
    await purchaseService.getPurchaseOrder("po-1");
    await purchaseService.createPurchaseOrder(
      {
        po_date: "2026-08-04",
        supplier_id: "supplier-1",
        currency: "USD",
        payment_terms: "Net 30",
        lines: line,
      },
      context
    );
    await purchaseService.updatePurchaseOrder(
      "po-1",
      { expected_delivery_date: "2026-08-12" },
      context
    );
    await purchaseService.deletePurchaseOrder("po-1", "cancelled", context);
    await purchaseService.submitPurchaseOrder("po-1", context);
    await purchaseService.approvePurchaseOrder("po-1", context);
    await purchaseService.rejectPurchaseOrder("po-1", context);
    await purchaseService.dispatchPurchaseOrder("po-1", context);
    await purchaseService.acknowledgePurchaseOrder("po-1", context);
    await purchaseService.cancelPurchaseOrder("po-1", context);
    await purchaseService.listReceipts({ status: "draft" });
    await purchaseService.getReceipt("receipt-1");
    await purchaseService.createReceipt(
      {
        receipt_date: "2026-08-04",
        purchase_order_id: "po-1",
        warehouse_id: "warehouse-1",
        lines: [
          { purchase_order_line_id: "po-line-1", quantity_received: "2.00", condition: "accepted" },
        ],
      },
      context
    );
    await purchaseService.updateReceipt("receipt-1", { warehouse_id: "warehouse-2" }, context);
    await purchaseService.deleteReceipt("receipt-1", "duplicate", context);
    await purchaseService.completeReceipt("receipt-1", context);
    await purchaseService.cancelReceipt("receipt-1", context);
    await purchaseService.getActiveConfiguration("development");
    await purchaseService.listConfigurationVersions("staging", { page: 2 });
    await purchaseService.getConfigurationVersion("config-1");
    const configurationWrite = {
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
    await purchaseService.createConfigurationDraft("development", configurationWrite, context);
    await purchaseService.updateConfigurationDraft(
      "config-1",
      { default_currency: "EUR" },
      context
    );
    await purchaseService.previewConfiguration("production", configurationWrite, [{ amount: 10 }]);
    await purchaseService.activateConfiguration("config-1", "approved", context);
    await purchaseService.rollbackConfiguration("config-1", "incident", context);
    await purchaseService.exportConfiguration("production", 3);
    await purchaseService.importConfiguration(
      { schema: "saraise.purchase.configuration.v1", configuration: {}, checksum: "sha256:abc" },
      context
    );
    await purchaseService.getJob("job-1");
    await purchaseService.getHealth();

    expect(client.post).toHaveBeenCalledWith(
      ENDPOINTS.REQUISITIONS.CONVERT("req-1"),
      { supplier_id: "supplier-1", line_selections: line },
      expect.any(Object)
    );
    expect(client.post).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATIONS.PREVIEW,
      expect.objectContaining({
        environment: "production",
        default_currency: "USD",
        simulations: [{ amount: 10 }],
      }),
      { headers: { "Idempotency-Key": "00000000-0000-4000-8000-000000000777" } }
    );
    expect(client.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CONFIGURATIONS.EXPORT}?environment=production&version=3`
    );
  });

  it("fails closed on malformed API envelopes", async () => {
    client.get.mockResolvedValueOnce({ data: data, meta: {} });
    await expect(purchaseService.getHealth()).rejects.toThrow(ApiError);

    client.get.mockResolvedValueOnce(envelope([data]));
    await expect(purchaseService.listSuppliers()).rejects.toThrow(
      "Malformed paginated API v2 response"
    );
  });
});
