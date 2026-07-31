/* eslint-disable @typescript-eslint/unbound-method, max-lines-per-function -- service adapter tests verify mocked transport calls across the governed sales API surface. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import { salesQueryKeys, salesService, SalesGatewayError } from "./sales-service";

vi.mock("@/services/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const mockedClient = vi.mocked(apiClient);
const meta = { correlation_id: "corr-sales", timestamp: "2026-07-31T00:00:00Z" };
const pagination = {
  page: 1,
  page_size: 25,
  count: 1,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};
const envelope = <T>(data: T) => ({ data, meta });
const page = <T>(data: T[]) => ({ data, meta: { ...meta, pagination } });
const entity = { id: "entity-1", lock_version: 7 };
const command = {
  command: "confirm",
  resource: entity,
  transition: {
    command: "confirm",
    from_status: "draft",
    to_status: "confirmed",
    actor_id: "user-1",
    correlation_id: "corr-command",
    occurred_at: meta.timestamp,
  },
};
const configuration = {
  id: "configuration-1",
  default_currency: "USD",
  currency_decimal_places: 2,
  rounding_mode: "ROUND_HALF_UP",
  quotation_validity_days: 30,
  credit_check_enabled: true,
  inventory_confirmation_required: false,
  maximum_manual_discount_percent: "15.00",
  manual_tax_enabled: true,
  quotation_prefix: "QT",
  order_prefix: "SO",
  delivery_prefix: "DN",
  sequence_padding: 5,
  manual_discount_enabled: true,
  version: 3,
};
const configurationValues = {
  default_currency: "USD",
  currency_decimal_places: 2,
  rounding_mode: "ROUND_HALF_UP" as const,
  quotation_validity_days: 30,
  credit_check_enabled: true,
  inventory_confirmation_required: false,
  manual_discount_enabled: true,
  maximum_manual_discount_percent: "15.00",
  manual_tax_enabled: true,
  quotation_prefix: "QT",
  order_prefix: "SO",
  delivery_prefix: "DN",
  sequence_padding: 5,
};
const configurationExport = {
  schema_version: 1 as const,
  environment: "development",
  exported_at: meta.timestamp,
  values: configurationValues,
};

describe("sales service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("serializes list filters, preserves pagination metadata, and rejects malformed pages", async () => {
    vi.mocked(mockedClient.get).mockResolvedValueOnce(page([entity]));

    const result = await salesService.listCustomers({
      search: "ACME & Sons",
      is_active: true,
      currency: "",
      page: 1,
    });

    expect(mockedClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.CUSTOMERS.LIST}?search=ACME+%26+Sons&is_active=true&page=1`
    );
    expect(result.data).toEqual([entity]);
    expect(result.meta.pagination.count).toBe(1);

    vi.mocked(mockedClient.get).mockResolvedValueOnce({ data: [entity], meta });
    await expect(salesService.listOrders()).rejects.toBeInstanceOf(SalesGatewayError);

    vi.mocked(mockedClient.get).mockResolvedValueOnce({
      data: [{ lock_version: 1 }],
      meta: { ...meta, pagination },
    });
    await expect(salesService.listDeliveryNotes()).rejects.toMatchObject({
      correlationId: "corr-sales",
    });
  });

  it("routes customer, quotation, order, and delivery CRUD through governed endpoints", async () => {
    vi.mocked(mockedClient.get).mockResolvedValue(envelope(entity));
    vi.mocked(mockedClient.post).mockResolvedValue(envelope(entity));
    vi.mocked(mockedClient.patch).mockResolvedValue(envelope(entity));
    vi.mocked(mockedClient.delete).mockResolvedValue(envelope(entity));

    await expect(salesService.getCustomer("customer/1")).resolves.toBe(entity);
    await expect(salesService.createCustomer(
      { customer_code: "ACME", customer_name: "ACME", currency: "USD" },
      "idem-customer"
    )).resolves.toBe(entity);
    await expect(salesService.updateCustomer("customer/1", {
      customer_name: "ACME Inc",
      expected_version: 7,
    })).resolves.toBe(entity);
    await expect(salesService.deleteCustomer("customer/1", 7)).resolves.toBeUndefined();

    await expect(salesService.getQuotation("quote/1")).resolves.toBe(entity);
    await expect(salesService.createQuotation(
      {
        quotation_date: "2026-07-31",
        valid_until: "2026-08-31",
        customer: "customer-1",
        currency: "USD",
        lines: [],
      },
      "idem-quote"
    )).resolves.toBe(entity);
    await expect(salesService.updateQuotation("quote/1", { expected_version: 7 })).resolves.toBe(entity);
    await expect(salesService.deleteQuotation("quote/1", 7)).resolves.toBeUndefined();

    await expect(salesService.getOrder("order/1")).resolves.toBe(entity);
    await expect(salesService.createOrder(
      {
        order_date: "2026-07-31",
        customer: "customer-1",
        currency: "USD",
        lines: [],
      },
      "idem-order"
    )).resolves.toBe(entity);
    await expect(salesService.updateOrder("order/1", { expected_version: 7 })).resolves.toBe(entity);
    await expect(salesService.deleteOrder("order/1", 7)).resolves.toBeUndefined();

    await expect(salesService.getDeliveryNote("delivery/1")).resolves.toBe(entity);
    await expect(salesService.createDeliveryNote(
      {
        delivery_date: "2026-07-31",
        sales_order: "order-1",
        lines: [],
      },
      "idem-delivery"
    )).resolves.toBe(entity);
    await expect(salesService.updateDeliveryNote("delivery/1", { expected_version: 7 })).resolves.toBe(entity);
    await expect(salesService.deleteDeliveryNote("delivery/1", 7)).resolves.toBeUndefined();

    expect(mockedClient.get).toHaveBeenCalledWith(ENDPOINTS.CUSTOMERS.DETAIL("customer/1"));
    expect(mockedClient.post).toHaveBeenCalledWith(
      ENDPOINTS.CUSTOMERS.CREATE,
      expect.objectContaining({ customer_code: "ACME" }),
      { headers: { "Idempotency-Key": "idem-customer" } }
    );
    expect(mockedClient.patch).toHaveBeenCalledWith(
      ENDPOINTS.QUOTATIONS.UPDATE("quote/1"),
      expect.objectContaining({ expected_version: 7 })
    );
    expect(mockedClient.delete).toHaveBeenCalledWith(ENDPOINTS.SALES_ORDERS.DELETE("order/1"), {
      headers: { "If-Match": "7" },
    });
    expect(mockedClient.post).toHaveBeenCalledWith(
      ENDPOINTS.DELIVERY_NOTES.CREATE,
      expect.objectContaining({ sales_order: "order-1" }),
      { headers: { "Idempotency-Key": "idem-delivery" } }
    );
  });

  it("keeps commands idempotent and validates command envelopes", async () => {
    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope(command));

    await expect(
      salesService.confirmOrder("order/1", {
        idempotency_key: "idem-command",
        reason: "Customer approved",
      })
    ).resolves.toMatchObject({ command: "confirm", resource: entity });

    expect(mockedClient.post).toHaveBeenCalledWith(
      ENDPOINTS.SALES_ORDERS.COMMAND("order/1", "confirm"),
      { reason: "Customer approved" },
      { headers: { "Idempotency-Key": "idem-command" } }
    );

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope(entity));
    await expect(
      salesService.cancelDeliveryNote("delivery-1", { idempotency_key: "idem-cancel" })
    ).rejects.toBeInstanceOf(SalesGatewayError);

    vi.mocked(mockedClient.post).mockResolvedValue(envelope(entity));
    await expect(salesService.quotationCommand("quote-1", "send", { idempotency_key: "idem-generic" })).resolves.toBe(entity);
    await expect(salesService.sendQuotation("quote-1", { idempotency_key: "idem-send" })).resolves.toBe(entity);
    await expect(salesService.acceptQuotation("quote-1", { idempotency_key: "idem-accept" })).resolves.toBe(entity);
    await expect(salesService.rejectQuotation("quote-1", { idempotency_key: "idem-reject" })).resolves.toBe(entity);
    await expect(salesService.expireQuotation("quote-1", { idempotency_key: "idem-expire" })).resolves.toBe(entity);
    await expect(salesService.reviseQuotation("quote-1", { idempotency_key: "idem-revise" })).resolves.toBe(entity);
    await expect(salesService.convertQuotation("quote-1", { idempotency_key: "idem-convert" })).resolves.toBe(entity);
    vi.mocked(mockedClient.post).mockResolvedValue(envelope(command));
    await expect(salesService.orderCommand("order-1", "confirm", { idempotency_key: "idem-order-command" })).resolves.toMatchObject(command);
    await expect(salesService.startOrderPicking("order-1", { idempotency_key: "idem-picking" })).resolves.toMatchObject(command);
    await expect(salesService.startOrderPacking("order-1", { idempotency_key: "idem-packing" })).resolves.toMatchObject(command);
    await expect(salesService.markOrderReady("order-1", { idempotency_key: "idem-ready" })).resolves.toMatchObject(command);
    await expect(salesService.shipOrder("order-1", { idempotency_key: "idem-ship" })).resolves.toMatchObject(command);
    await expect(salesService.deliverOrder("order-1", { idempotency_key: "idem-deliver" })).resolves.toMatchObject(command);
    await expect(salesService.markOrderInvoiced("order-1", { idempotency_key: "idem-invoiced" })).resolves.toMatchObject(command);
    await expect(salesService.cancelOrder("order-1", { idempotency_key: "idem-cancel-order" })).resolves.toMatchObject(command);
    await expect(salesService.deliveryCommand("delivery-1", "complete", { idempotency_key: "idem-delivery-command" })).resolves.toMatchObject(command);
    await expect(salesService.completeDeliveryNote("delivery-1", { idempotency_key: "idem-complete-delivery" })).resolves.toMatchObject(command);
    expect(mockedClient.post).toHaveBeenCalledWith(
      ENDPOINTS.QUOTATIONS.COMMAND("quote-1", "convert"),
      {},
      { headers: { "Idempotency-Key": "idem-convert" } }
    );
    expect(mockedClient.post).toHaveBeenCalledWith(
      ENDPOINTS.SALES_ORDERS.COMMAND("order-1", "mark-invoiced"),
      {},
      { headers: { "Idempotency-Key": "idem-invoiced" } }
    );
    expect(mockedClient.post).toHaveBeenCalledWith(
      ENDPOINTS.DELIVERY_NOTES.COMMAND("delivery-1", "complete"),
      {},
      { headers: { "Idempotency-Key": "idem-complete-delivery" } }
    );
  });

  it("validates summary, capability, preview, configuration, import, export, and health envelopes", async () => {
    vi.mocked(mockedClient.get).mockResolvedValueOnce(
      envelope({
        open_quotations: 2,
        confirmed_orders: 3,
        fulfillment_stages: { picking: 1 },
        recent_deliveries: [
          {
            id: "delivery-1",
            delivery_number: "DN-1",
            delivery_date: "2026-07-31",
            status: "completed",
          },
        ],
      })
    );
    await expect(salesService.getSummary()).resolves.toMatchObject({ open_quotations: 2 });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(
      envelope([{ capability: "pricing", status: "available", reason_code: "ok" }])
    );
    await expect(salesService.getCapabilities()).resolves.toHaveLength(1);

    vi.mocked(mockedClient.post).mockResolvedValueOnce(
      envelope({
        subtotal_amount: "10.00",
        discount_amount: "0.00",
        tax_amount: "0.00",
        total_amount: "10.00",
        lines: [],
      })
    );
    await expect(
      salesService.previewQuotation({
        quotation_date: "2026-07-31",
        valid_until: "2026-08-31",
        customer: "customer-1",
        currency: "USD",
        lines: [],
      })
    ).resolves.toMatchObject({ total_amount: "10.00" });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(envelope(configuration));
    await expect(salesService.getConfiguration()).resolves.toBe(configuration);

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope({ valid: true, diff: [] }));
    await expect(salesService.previewConfiguration({ default_currency: "USD" })).resolves.toEqual({
      valid: true,
      diff: [],
    });

    vi.mocked(mockedClient.put).mockResolvedValueOnce(envelope(configuration));
    await salesService.applyConfiguration({
      values: { default_currency: "USD" },
      expected_version: 2,
      reason: "Kaizen",
    });
    expect(mockedClient.put).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.CURRENT, {
      default_currency: "USD",
      expected_version: 2,
      reason: "Kaizen",
    });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(page([{ id: "version-1", version: 1 }]));
    await salesService.listConfigurationVersions(2);
    expect(mockedClient.get).toHaveBeenCalledWith(`${ENDPOINTS.CONFIGURATION.VERSIONS}?page=2`);

    vi.mocked(mockedClient.get).mockResolvedValueOnce(envelope({ id: "version-2", version: 2 }));
    await salesService.getConfigurationVersion(2);
    expect(mockedClient.get).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.VERSION(2));

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope(configuration));
    await salesService.rollbackConfiguration({
      target_version: 1,
      expected_version: 2,
      reason: "Rollback failed rollout",
      idempotency_key: "idem-rollback",
    });
    expect(mockedClient.post).toHaveBeenCalledWith(
      ENDPOINTS.CONFIGURATION.ROLLBACK,
      { target_version: 1, expected_version: 2, reason: "Rollback failed rollout" },
      { headers: { "Idempotency-Key": "idem-rollback" } }
    );

    vi.mocked(mockedClient.get).mockResolvedValueOnce(
      envelope(configurationExport)
    );
    await expect(salesService.exportConfiguration()).resolves.toMatchObject({ schema_version: 1 });

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope({ valid: false, diff: [] }));
    await expect(
      salesService.importConfiguration({
        expected_version: 2,
        document: configurationExport,
        dry_run: true,
        reason: "Preview import",
      })
    ).resolves.toMatchObject({ valid: false });

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope(configuration));
    await expect(
      salesService.importConfiguration({
        expected_version: 2,
        document: configurationExport,
        dry_run: false,
        reason: "Apply import",
      })
    ).resolves.toBe(configuration);

    vi.mocked(mockedClient.get).mockResolvedValueOnce(envelope({ status: "degraded" }));
    await expect(salesService.getHealth()).resolves.toEqual({ status: "degraded" });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(envelope({ status: "unknown" }));
    await expect(salesService.getHealth()).rejects.toBeInstanceOf(SalesGatewayError);
  });

  it("keeps query keys stable for cache invalidation", () => {
    const gatewayError = new SalesGatewayError("corr-name");
    expect(gatewayError.name).toBe("SalesGatewayError");
    expect(gatewayError.message).toBe("The sales service returned a malformed governed response.");
    expect(gatewayError.code).toBe("MALFORMED_GATEWAY_RESPONSE");
    expect(salesQueryKeys.customer("customer-1")).toEqual([
      "sales-management",
      "customer",
      "customer-1",
    ]);
    expect(salesQueryKeys.dashboard()).toEqual(["sales-management", "dashboard"]);
    expect(salesQueryKeys.customers()).toEqual(["sales-management", "customers", {}]);
    expect(salesQueryKeys.quotations({ status: "sent" })).toEqual([
      "sales-management",
      "quotations",
      { status: "sent" },
    ]);
    expect(salesQueryKeys.quotation("quote-1")).toEqual(["sales-management", "quotation", "quote-1"]);
    expect(salesQueryKeys.orders({ status: "draft" })).toEqual([
      "sales-management",
      "orders",
      { status: "draft" },
    ]);
    expect(salesQueryKeys.order("order-1")).toEqual(["sales-management", "order", "order-1"]);
    expect(salesQueryKeys.deliveries({ status: "completed" })).toEqual([
      "sales-management",
      "deliveries",
      { status: "completed" },
    ]);
    expect(salesQueryKeys.delivery("delivery-1")).toEqual([
      "sales-management",
      "delivery",
      "delivery-1",
    ]);
    expect(salesQueryKeys.configuration()).toEqual(["sales-management", "configuration"]);
    expect(salesQueryKeys.configurationVersions()).toEqual([
      "sales-management",
      "configuration-versions",
      1,
    ]);
    expect(salesQueryKeys.configurationVersion(3)).toEqual([
      "sales-management",
      "configuration-version",
      3,
    ]);
  });

  it("rejects malformed sales envelopes and preserves filter boundaries", async () => {
    vi.mocked(mockedClient.get).mockResolvedValueOnce({
      data: entity,
      meta: { correlation_id: "corr-sales", timestamp: 123 },
    });
    await expect(salesService.getCustomer("customer-1")).rejects.toBeInstanceOf(SalesGatewayError);

    vi.mocked(mockedClient.get).mockResolvedValueOnce({
      data: [entity],
      meta: { ...meta, pagination: { ...pagination, has_next: "false" } },
    });
    await expect(salesService.listCustomers()).rejects.toMatchObject({
      correlationId: "corr-sales",
    });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(page([entity]));
    await salesService.listCustomers({
      search: "   ",
      is_active: false,
      currency: null,
      page: undefined,
    } as never);
    expect(mockedClient.get).toHaveBeenLastCalledWith(`${ENDPOINTS.CUSTOMERS.LIST}?is_active=false`);

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope({ command: 42, resource: entity }));
    await expect(
      salesService.confirmOrder("order-1", { idempotency_key: "idem-bad-command" })
    ).rejects.toBeInstanceOf(SalesGatewayError);
  });

  it("routes every list adapter through its own governed collection endpoint", async () => {
    vi.mocked(mockedClient.get).mockResolvedValue(page([entity]));

    await expect(salesService.listCustomers()).resolves.toMatchObject({ data: [entity] });
    await expect(salesService.listQuotations({ status: "draft" })).resolves.toMatchObject({
      data: [entity],
    });
    await expect(salesService.listOrders({ status: "confirmed", page: 3 })).resolves.toMatchObject({
      data: [entity],
    });
    await expect(salesService.listDeliveryNotes({ status: "completed" })).resolves.toMatchObject({
      data: [entity],
    });

    expect(mockedClient.get).toHaveBeenNthCalledWith(1, ENDPOINTS.CUSTOMERS.LIST);
    expect(mockedClient.get).toHaveBeenNthCalledWith(
      2,
      `${ENDPOINTS.QUOTATIONS.LIST}?status=draft`
    );
    expect(mockedClient.get).toHaveBeenNthCalledWith(
      3,
      `${ENDPOINTS.SALES_ORDERS.LIST}?status=confirmed&page=3`
    );
    expect(mockedClient.get).toHaveBeenNthCalledWith(
      4,
      `${ENDPOINTS.DELIVERY_NOTES.LIST}?status=completed`
    );
  });

  it("routes every delete adapter with the required optimistic version header", async () => {
    vi.mocked(mockedClient.delete).mockResolvedValue(envelope(entity));

    await expect(salesService.deleteCustomer("customer-1", 7)).resolves.toBeUndefined();
    await expect(salesService.deleteQuotation("quote-1", 8)).resolves.toBeUndefined();
    await expect(salesService.deleteOrder("order-1", 9)).resolves.toBeUndefined();
    await expect(salesService.deleteDeliveryNote("delivery-1", 10)).resolves.toBeUndefined();

    expect(mockedClient.delete).toHaveBeenCalledTimes(4);
    expect(mockedClient.delete).toHaveBeenNthCalledWith(1, ENDPOINTS.CUSTOMERS.DELETE("customer-1"), {
      headers: { "If-Match": "7" },
    });
    expect(mockedClient.delete).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.QUOTATIONS.DELETE("quote-1"),
      { headers: { "If-Match": "8" } }
    );
    expect(mockedClient.delete).toHaveBeenNthCalledWith(3, ENDPOINTS.SALES_ORDERS.DELETE("order-1"), {
      headers: { "If-Match": "9" },
    });
    expect(mockedClient.delete).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.DELIVERY_NOTES.DELETE("delivery-1"),
      { headers: { "If-Match": "10" } }
    );
  });

  it("routes each quotation command helper with stripped idempotency payloads", async () => {
    vi.mocked(mockedClient.post).mockResolvedValue(envelope(entity));

    const payload = { idempotency_key: "quote-key", reason: "customer requested" };

    await expect(salesService.sendQuotation("quote-1", payload)).resolves.toBe(entity);
    await expect(salesService.acceptQuotation("quote-1", payload)).resolves.toBe(entity);
    await expect(salesService.rejectQuotation("quote-1", payload)).resolves.toBe(entity);
    await expect(salesService.expireQuotation("quote-1", payload)).resolves.toBe(entity);
    await expect(salesService.reviseQuotation("quote-1", payload)).resolves.toBe(entity);
    await expect(salesService.convertQuotation("quote-1", payload)).resolves.toBe(entity);

    const expectedOptions = { headers: { "Idempotency-Key": "quote-key" } };
    expect(mockedClient.post).toHaveBeenNthCalledWith(
      1,
      ENDPOINTS.QUOTATIONS.COMMAND("quote-1", "send"),
      { reason: "customer requested" },
      expectedOptions
    );
    expect(mockedClient.post).toHaveBeenNthCalledWith(
      2,
      ENDPOINTS.QUOTATIONS.COMMAND("quote-1", "accept"),
      { reason: "customer requested" },
      expectedOptions
    );
    expect(mockedClient.post).toHaveBeenNthCalledWith(
      3,
      ENDPOINTS.QUOTATIONS.COMMAND("quote-1", "reject"),
      { reason: "customer requested" },
      expectedOptions
    );
    expect(mockedClient.post).toHaveBeenNthCalledWith(
      4,
      ENDPOINTS.QUOTATIONS.COMMAND("quote-1", "expire"),
      { reason: "customer requested" },
      expectedOptions
    );
    expect(mockedClient.post).toHaveBeenNthCalledWith(
      5,
      ENDPOINTS.QUOTATIONS.COMMAND("quote-1", "revise"),
      { reason: "customer requested" },
      expectedOptions
    );
    expect(mockedClient.post).toHaveBeenNthCalledWith(
      6,
      ENDPOINTS.QUOTATIONS.COMMAND("quote-1", "convert"),
      { reason: "customer requested" },
      expectedOptions
    );
  });

  it("routes every order and delivery command helper to the exact lifecycle endpoint", async () => {
    vi.mocked(mockedClient.post).mockResolvedValue(envelope(command));
    const payload = { idempotency_key: "order-key", reason: "warehouse update" };

    await salesService.orderCommand("order-1", "confirm", payload);
    await salesService.confirmOrder("order-1", payload);
    await salesService.startOrderPicking("order-1", payload);
    await salesService.startOrderPacking("order-1", payload);
    await salesService.markOrderReady("order-1", payload);
    await salesService.shipOrder("order-1", payload);
    await salesService.deliverOrder("order-1", payload);
    await salesService.markOrderInvoiced("order-1", payload);
    await salesService.cancelOrder("order-1", payload);
    await salesService.deliveryCommand("delivery-1", "cancel", payload);
    await salesService.completeDeliveryNote("delivery-1", payload);
    await salesService.cancelDeliveryNote("delivery-1", payload);

    const expectedBody = { reason: "warehouse update" };
    const expectedOptions = { headers: { "Idempotency-Key": "order-key" } };
    const expectedOrderCommands = [
      "confirm",
      "confirm",
      "start-picking",
      "start-packing",
      "mark-ready",
      "ship",
      "deliver",
      "mark-invoiced",
      "cancel",
    ] as const;
    expectedOrderCommands.forEach((lifecycleCommand, index) => {
      expect(mockedClient.post).toHaveBeenNthCalledWith(
        index + 1,
        ENDPOINTS.SALES_ORDERS.COMMAND("order-1", lifecycleCommand),
        expectedBody,
        expectedOptions
      );
    });
    expect(mockedClient.post).toHaveBeenNthCalledWith(
      10,
      ENDPOINTS.DELIVERY_NOTES.COMMAND("delivery-1", "cancel"),
      expectedBody,
      expectedOptions
    );
    expect(mockedClient.post).toHaveBeenNthCalledWith(
      11,
      ENDPOINTS.DELIVERY_NOTES.COMMAND("delivery-1", "complete"),
      expectedBody,
      expectedOptions
    );
    expect(mockedClient.post).toHaveBeenNthCalledWith(
      12,
      ENDPOINTS.DELIVERY_NOTES.COMMAND("delivery-1", "cancel"),
      expectedBody,
      expectedOptions
    );
  });

  it("rejects malformed governed specialty envelopes with the response correlation id", async () => {
    vi.mocked(mockedClient.get).mockResolvedValueOnce(envelope({ ...configuration, id: null }));
    await expect(salesService.getConfiguration()).rejects.toMatchObject({
      correlationId: "corr-sales",
    });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(envelope([{ capability: "pricing" }]));
    await expect(salesService.getCapabilities()).rejects.toMatchObject({
      correlationId: "corr-sales",
    });

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope({ total_amount: "10.00" }));
    await expect(
      salesService.previewQuotation({
        quotation_date: "2026-07-31",
        valid_until: "2026-08-31",
        customer: "customer-1",
        currency: "USD",
        lines: [],
      })
    ).rejects.toMatchObject({ correlationId: "corr-sales" });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(envelope({ schema_version: 2, values: {} }));
    await expect(salesService.exportConfiguration()).rejects.toMatchObject({
      correlationId: "corr-sales",
    });
  });

  it("rejects malformed summary, capability, preview, import, and health variants", async () => {
    vi.mocked(mockedClient.get).mockResolvedValueOnce(
      envelope({
        open_quotations: "2",
        confirmed_orders: 3,
        fulfillment_stages: { picking: 1 },
        recent_deliveries: [],
      })
    );
    await expect(salesService.getSummary()).rejects.toMatchObject({ correlationId: "corr-sales" });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(
      envelope({
        open_quotations: 2,
        confirmed_orders: 3,
        fulfillment_stages: { picking: 1 },
        recent_deliveries: [
          {
            id: "delivery-1",
            delivery_number: "DN-1",
            delivery_date: "2026-07-31",
            status: "completed",
          },
          { id: "delivery-2", delivery_number: "DN-2", delivery_date: 20260731, status: "draft" },
        ],
      })
    );
    await expect(salesService.getSummary()).rejects.toMatchObject({ correlationId: "corr-sales" });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(
      envelope([
        { capability: "pricing", status: "available", reason_code: "ok" },
        { capability: "tax", status: "degraded" },
      ])
    );
    await expect(salesService.getCapabilities()).rejects.toMatchObject({
      correlationId: "corr-sales",
    });

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope({ valid: true }));
    await expect(salesService.previewConfiguration({ default_currency: "USD" })).rejects.toMatchObject({
      correlationId: "corr-sales",
    });

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope({ valid: false }));
    await expect(
      salesService.importConfiguration({
        expected_version: 2,
        document: configurationExport,
        dry_run: true,
        reason: "Preview import",
      })
    ).rejects.toMatchObject({ correlationId: "corr-sales" });

    vi.mocked(mockedClient.post).mockResolvedValueOnce(envelope(null));
    await expect(
      salesService.importConfiguration({
        expected_version: 2,
        document: configurationExport,
        dry_run: false,
        reason: "Apply import",
      })
    ).rejects.toMatchObject({ correlationId: "corr-sales" });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(envelope({ status: "available" }));
    await expect(salesService.getHealth()).resolves.toEqual({ status: "available" });

    vi.mocked(mockedClient.get).mockResolvedValueOnce(envelope({ status: "unavailable" }));
    await expect(salesService.getHealth()).resolves.toEqual({ status: "unavailable" });
  });
});
