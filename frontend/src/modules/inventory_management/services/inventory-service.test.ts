/* eslint-disable max-lines-per-function -- mutation-focused service boundary matrices are intentionally local to this test file. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ENDPOINTS } from "../contracts";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@/services/api-client", async (original) => ({
  ...(await original<object>()),
  apiClient: api,
}));

import { createIdempotencyKey, inventoryQueryKeys, inventoryService } from "./inventory-service";

const meta = { correlation_id: "corr-42", timestamp: "2026-07-23T00:00:00Z" };
const configurationDocument = {
  default_valuation_method: "fifo" as const,
  allow_negative_stock: false,
  require_stock_entry_approval: true,
  enforce_creator_approver_separation: true,
  max_lines_per_entry: 100,
  reservation_ttl_minutes: 60,
  expiry_warning_days: 30,
  auto_expire_batches: true,
  enabled_capabilities: {
    barcode_scanning: true,
    bulk_import: true,
    batch_tracking: true,
    serial_tracking: true,
    cycle_counting: true,
  },
  rollout_rules: {
    enabled: true,
    percentage: 100,
    tenant_cohort: "all",
    allowed_role_ids: [],
  },
  change_reason: "",
};
const detailEnvelope = (data: unknown = { id: "resource-1" }) => ({ data, meta });
const pageEnvelope = () => ({
  data: [],
  meta: {
    ...meta,
    pagination: {
      page: 1,
      page_size: 25,
      total_count: 0,
      total_pages: 0,
      next: null,
      previous: null,
    },
  },
});
const body = { name: "value" };
const commandBody = { transition_key: "transition-1", reason: "approved" };
const key = "inventory:test:key";
const version = 7;

afterEach(() => {
  vi.unstubAllGlobals();
});

const listCases = [
  ["locations", () => inventoryService.listLocations(), ENDPOINTS.LOCATIONS.LIST],
  ["batches", () => inventoryService.listBatches(), ENDPOINTS.BATCHES.LIST],
  ["serials", () => inventoryService.listSerials(), ENDPOINTS.SERIALS.LIST],
  ["stock entries", () => inventoryService.listStockEntries(), ENDPOINTS.STOCK_ENTRIES.LIST],
  ["balances", () => inventoryService.listBalances(), ENDPOINTS.STOCK_BALANCES.LIST],
  ["ledger", () => inventoryService.listLedger(), ENDPOINTS.STOCK_LEDGER.LIST],
  ["reservations", () => inventoryService.listReservations(), ENDPOINTS.RESERVATIONS.LIST],
  ["cycle counts", () => inventoryService.listCycleCounts(), ENDPOINTS.CYCLE_COUNTS.LIST],
  ["configurations", () => inventoryService.listConfigurations(), ENDPOINTS.CONFIGURATIONS.LIST],
  [
    "configuration history",
    () => inventoryService.configurationHistory("development"),
    ENDPOINTS.CONFIGURATIONS.HISTORY("development"),
  ],
] satisfies [string, () => Promise<unknown>, string][];

const getCases = [
  ["location", () => inventoryService.getLocation("loc-1"), ENDPOINTS.LOCATIONS.DETAIL("loc-1")],
  ["item", () => inventoryService.getItem("item-1"), ENDPOINTS.ITEMS.DETAIL("item-1")],
  ["batch", () => inventoryService.getBatch("batch-1"), ENDPOINTS.BATCHES.DETAIL("batch-1")],
  ["batch trace", () => inventoryService.traceBatch("batch-1"), ENDPOINTS.BATCHES.TRACE("batch-1")],
  ["serial", () => inventoryService.getSerial("serial-1"), ENDPOINTS.SERIALS.DETAIL("serial-1")],
  [
    "serial trace",
    () => inventoryService.traceSerial("serial-1"),
    ENDPOINTS.SERIALS.TRACE("serial-1"),
  ],
  [
    "stock entry",
    () => inventoryService.getStockEntry("entry-1"),
    ENDPOINTS.STOCK_ENTRIES.DETAIL("entry-1"),
  ],
  [
    "stock entry preview",
    () => inventoryService.previewStockEntry("entry-1"),
    ENDPOINTS.STOCK_ENTRIES.PREVIEW("entry-1"),
  ],
  [
    "balance",
    () => inventoryService.getBalance("balance-1"),
    ENDPOINTS.STOCK_BALANCES.DETAIL("balance-1"),
  ],
  [
    "ledger entry",
    () => inventoryService.getLedgerEntry("ledger-1"),
    ENDPOINTS.STOCK_LEDGER.DETAIL("ledger-1"),
  ],
  [
    "reservation",
    () => inventoryService.getReservation("reservation-1"),
    ENDPOINTS.RESERVATIONS.DETAIL("reservation-1"),
  ],
  [
    "cycle count",
    () => inventoryService.getCycleCount("cycle-1"),
    ENDPOINTS.CYCLE_COUNTS.DETAIL("cycle-1"),
  ],
  [
    "configuration",
    () => inventoryService.getConfiguration("development"),
    ENDPOINTS.CONFIGURATIONS.DETAIL("development"),
  ],
  [
    "configuration export",
    () => inventoryService.exportConfiguration("development"),
    ENDPOINTS.CONFIGURATIONS.EXPORT("development"),
  ],
  ["dashboard", () => inventoryService.dashboard(), ENDPOINTS.DASHBOARD],
  ["health", () => inventoryService.health(), ENDPOINTS.HEALTH],
] satisfies [string, () => Promise<unknown>, string][];

const createCases = [
  [
    "location",
    () => inventoryService.createLocation(body as never, key),
    ENDPOINTS.LOCATIONS.CREATE,
  ],
  ["item", () => inventoryService.createItem(body as never, key), ENDPOINTS.ITEMS.CREATE],
  ["batch", () => inventoryService.createBatch(body as never, key), ENDPOINTS.BATCHES.CREATE],
  ["serial", () => inventoryService.createSerial(body as never, key), ENDPOINTS.SERIALS.CREATE],
  [
    "stock entry",
    () => inventoryService.createStockEntry(body as never, key),
    ENDPOINTS.STOCK_ENTRIES.CREATE,
  ],
  [
    "reservation",
    () => inventoryService.createReservation(body as never, key),
    ENDPOINTS.RESERVATIONS.CREATE,
  ],
  [
    "cycle count",
    () => inventoryService.createCycleCount(body as never, key),
    ENDPOINTS.CYCLE_COUNTS.CREATE,
  ],
  [
    "activate configuration",
    () => inventoryService.activateConfiguration("development", body as never, key),
    ENDPOINTS.CONFIGURATIONS.ACTIVATE("development"),
  ],
  [
    "rollback configuration",
    () => inventoryService.rollbackConfiguration("development", body as never, key),
    ENDPOINTS.CONFIGURATIONS.ROLLBACK("development"),
  ],
  [
    "import configuration",
    () => inventoryService.importConfiguration("development", body as never, key),
    ENDPOINTS.CONFIGURATIONS.IMPORT("development"),
  ],
  ["enqueue import", () => inventoryService.enqueueImport(body as never, key), ENDPOINTS.IMPORTS],
] satisfies [string, () => Promise<unknown>, string][];

const updateCases = [
  [
    "location",
    () => inventoryService.updateLocation("loc-1", body as never, version),
    ENDPOINTS.LOCATIONS.UPDATE("loc-1"),
  ],
  [
    "item",
    () => inventoryService.updateItem("item-1", body as never, version),
    ENDPOINTS.ITEMS.UPDATE("item-1"),
  ],
  [
    "batch",
    () => inventoryService.updateBatch("batch-1", body as never, version),
    ENDPOINTS.BATCHES.UPDATE("batch-1"),
  ],
  [
    "serial",
    () => inventoryService.updateSerial("serial-1", body as never, version),
    ENDPOINTS.SERIALS.UPDATE("serial-1"),
  ],
  [
    "stock entry",
    () => inventoryService.updateStockEntry("entry-1", body as never, version),
    ENDPOINTS.STOCK_ENTRIES.UPDATE("entry-1"),
  ],
  [
    "reservation",
    () => inventoryService.updateReservation("reservation-1", body as never, version),
    ENDPOINTS.RESERVATIONS.UPDATE("reservation-1"),
  ],
  [
    "cycle count",
    () => inventoryService.updateCycleCount("cycle-1", body as never, version),
    ENDPOINTS.CYCLE_COUNTS.UPDATE("cycle-1"),
  ],
  [
    "configuration revision",
    () =>
      inventoryService.createConfigurationRevision("development", configurationDocument, version),
    ENDPOINTS.CONFIGURATIONS.UPDATE("development"),
  ],
] satisfies [string, () => Promise<unknown>, string][];

const deleteCases = [
  [
    "warehouse",
    () => inventoryService.archiveWarehouse("warehouse-1", version),
    ENDPOINTS.WAREHOUSES.ARCHIVE("warehouse-1"),
  ],
  [
    "location",
    () => inventoryService.archiveLocation("loc-1", version),
    ENDPOINTS.LOCATIONS.ARCHIVE("loc-1"),
  ],
  [
    "item",
    () => inventoryService.archiveItem("item-1", version),
    ENDPOINTS.ITEMS.ARCHIVE("item-1"),
  ],
  [
    "stock entry draft",
    () => inventoryService.deleteStockEntryDraft("entry-1", version),
    ENDPOINTS.STOCK_ENTRIES.DELETE_DRAFT("entry-1"),
  ],
] satisfies [string, () => Promise<unknown>, string][];

const commandCases = [
  [
    "set default warehouse",
    () => inventoryService.setDefaultWarehouse("warehouse-1", key),
    ENDPOINTS.WAREHOUSES.SET_DEFAULT("warehouse-1"),
    { transition_key: key },
  ],
  [
    "batch",
    () => inventoryService.commandBatch("batch-1", "activate", commandBody, key),
    ENDPOINTS.BATCHES.COMMAND("batch-1", "activate"),
    commandBody,
  ],
  [
    "stock entry",
    () => inventoryService.commandStockEntry("entry-1", "submit", commandBody, key),
    ENDPOINTS.STOCK_ENTRIES.COMMAND("entry-1", "submit"),
    commandBody,
  ],
  [
    "reservation",
    () => inventoryService.commandReservation("reservation-1", "release", commandBody, key),
    ENDPOINTS.RESERVATIONS.COMMAND("reservation-1", "release"),
    commandBody,
  ],
  [
    "cycle count",
    () => inventoryService.commandCycleCount("cycle-1", "start", commandBody, key),
    ENDPOINTS.CYCLE_COUNTS.COMMAND("cycle-1", "start"),
    commandBody,
  ],
] satisfies [string, () => Promise<unknown>, string, object][];

describe("inventory service governance", () => {
  beforeEach(() => vi.clearAllMocks());

  it("preserves correlation and validates governed pagination", async () => {
    api.get.mockResolvedValue({
      data: [],
      meta: {
        ...meta,
        pagination: {
          page: 1,
          page_size: 25,
          total_count: 0,
          total_pages: 0,
          next: null,
          previous: null,
        },
      },
    });
    const result = await inventoryService.listWarehouses({ search: "central", page: 1 });
    expect(api.get).toHaveBeenCalledWith(`${ENDPOINTS.WAREHOUSES.LIST}?search=central&page=1`);
    expect(result.correlationId).toBe("corr-42");
    expect(result.pagination.total_count).toBe(0);
  });

  it("normalizes shared governed pagination metadata from the backend wire contract", async () => {
    api.get.mockResolvedValue({
      data: [],
      meta: {
        ...meta,
        pagination: {
          page: 2,
          page_size: 25,
          count: 50,
          total_pages: 4,
          has_next: true,
          has_previous: true,
        },
      },
    });

    const result = await inventoryService.listItems({ page: 2 });

    expect(api.get).toHaveBeenCalledWith(`${ENDPOINTS.ITEMS.LIST}?page=2`);
    expect(result.pagination).toEqual({
      page: 2,
      page_size: 25,
      total_count: 50,
      total_pages: 4,
      next: "3",
      previous: "1",
    });
  });

  it("keeps false backend pagination flags as absent cursors", async () => {
    api.get.mockResolvedValue({
      data: [],
      meta: {
        ...meta,
        pagination: {
          page: 2,
          page_size: 25,
          count: 50,
          total_pages: 4,
          has_next: false,
          has_previous: false,
        },
      },
    });

    const result = await inventoryService.listItems({ page: 2 });

    expect(result.pagination.next).toBeNull();
    expect(result.pagination.previous).toBeNull();
  });

  it("rejects pagination envelopes whose data payload is not a list", async () => {
    api.get.mockResolvedValue({
      data: { id: "not-a-list" },
      meta: {
        ...meta,
        pagination: {
          page: 1,
          page_size: 25,
          total_count: 1,
          total_pages: 1,
          next: null,
          previous: null,
        },
      },
    });

    await expect(inventoryService.listWarehouses()).rejects.toMatchObject({
      status: 502,
      code: "malformed_pagination",
      message: "Inventory API returned malformed pagination metadata.",
    });
  });

  it("rejects pagination envelopes with non-integer counters", async () => {
    api.get.mockResolvedValue({
      data: [],
      meta: {
        ...meta,
        pagination: {
          page: "1",
          page_size: 25,
          total_count: 0,
          total_pages: 1,
          next: null,
          previous: null,
        },
      },
    });

    await expect(inventoryService.listWarehouses()).rejects.toMatchObject({
      status: 502,
      code: "malformed_pagination",
      message: "Inventory pagination counters are invalid.",
    });
  });

  it("never converts a malformed list envelope into an empty success", async () => {
    api.get.mockResolvedValue({ data: [] });
    await expect(inventoryService.listWarehouses()).rejects.toMatchObject({
      status: 502,
      code: "malformed_pagination",
    });
  });

  it("rejects null detail envelopes as malformed API results", async () => {
    api.get.mockResolvedValue(null);

    await expect(inventoryService.getWarehouse("w-1")).rejects.toMatchObject({
      status: 502,
      code: "malformed_envelope",
      message: "Inventory API returned a malformed success envelope.",
    });
  });

  it("rejects detail envelopes without a data member even when metadata is valid", async () => {
    api.get.mockResolvedValue({ meta });

    await expect(inventoryService.getWarehouse("w-1")).rejects.toMatchObject({
      status: 502,
      code: "malformed_envelope",
    });
  });

  it("rejects detail envelopes with missing correlation evidence", async () => {
    api.get.mockResolvedValue({ data: { id: "w-1" }, meta: { timestamp: meta.timestamp } });

    await expect(inventoryService.getWarehouse("w-1")).rejects.toMatchObject({
      status: 502,
      code: "malformed_envelope",
    });
  });

  it("rejects detail envelopes with missing timestamp evidence", async () => {
    api.get.mockResolvedValue({
      data: { id: "w-1" },
      meta: { correlation_id: meta.correlation_id },
    });

    await expect(inventoryService.getWarehouse("w-1")).rejects.toMatchObject({
      status: 502,
      code: "malformed_envelope",
    });
  });

  it("omits empty query filter values without dropping false boolean filters", async () => {
    api.get.mockResolvedValue(pageEnvelope());

    await inventoryService.listWarehouses({
      search: "",
      page: undefined,
      country_code: null,
      is_default: false,
    } as never);

    expect(api.get).toHaveBeenCalledWith(`${ENDPOINTS.WAREHOUSES.LIST}?is_default=false`);
  });

  it("rejects malformed detail envelopes before callers use missing metadata", async () => {
    api.get.mockResolvedValue({ data: { id: "w-1" } });

    await expect(inventoryService.getWarehouse("w-1")).rejects.toMatchObject({
      status: 502,
      code: "malformed_envelope",
    });
  });
});

describe("inventory service read endpoints", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each(listCases)("lists %s through the governed page endpoint", async (_name, invoke, url) => {
    api.get.mockResolvedValue(pageEnvelope());

    const result = await invoke();

    expect(result).toMatchObject({ correlationId: "corr-42", pagination: { total_count: 0 } });
    expect(api.get).toHaveBeenCalledWith(url);
  });

  it.each(getCases)("gets %s through the governed detail endpoint", async (_name, invoke, url) => {
    api.get.mockResolvedValue(detailEnvelope());

    const result = await invoke();

    expect(result).toMatchObject({ correlationId: "corr-42" });
    expect(api.get).toHaveBeenCalledWith(url);
  });
});

describe("inventory service write endpoints", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each(createCases)("creates %s with idempotency", async (_name, invoke, url) => {
    api.post.mockResolvedValue(detailEnvelope());

    const result = await invoke();

    expect(result).toMatchObject({ correlationId: "corr-42" });
    expect(api.post).toHaveBeenCalledWith(url, body, {
      headers: { "Idempotency-Key": key },
    });
  });

  it.each(updateCases)("updates %s with optimistic locking", async (_name, invoke, url) => {
    api.patch.mockResolvedValue(detailEnvelope());

    const result = await invoke();

    expect(result).toMatchObject({ correlationId: "corr-42" });
    expect(api.patch).toHaveBeenCalledWith(url, expect.any(Object), {
      headers: { "If-Match": String(version) },
    });
  });

  it.each(deleteCases)("deletes %s with optimistic locking", async (_name, invoke, url) => {
    api.delete.mockResolvedValue(detailEnvelope());

    const result = await invoke();

    expect(result).toMatchObject({ correlationId: "corr-42" });
    expect(api.delete).toHaveBeenCalledWith(url, {
      headers: { "If-Match": String(version) },
    });
  });

  it.each(commandCases)(
    "commands %s with idempotency",
    async (_name, invoke, url, expectedBody) => {
      api.post.mockResolvedValue(detailEnvelope());

      const result = await invoke();

      expect(result).toMatchObject({ correlationId: "corr-42" });
      expect(api.post).toHaveBeenCalledWith(url, expectedBody, {
        headers: { "Idempotency-Key": key },
      });
    }
  );
});

describe("inventory service commands", () => {
  beforeEach(() => vi.clearAllMocks());

  it("uses the caller's stable idempotency key across retries", async () => {
    const key = createIdempotencyKey("warehouse-create");
    const warehouse = { id: "w-1", warehouse_name: "Central" };
    api.post.mockResolvedValue({ data: warehouse, meta });
    const body = {
      warehouse_code: "CENTRAL",
      warehouse_name: "Central",
      warehouse_type: "distribution_center" as const,
      country_code: "IN",
      timezone: "Asia/Kolkata",
    };
    await inventoryService.createWarehouse(body, key);
    await inventoryService.createWarehouse(body, key);
    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.WAREHOUSES.CREATE, body, {
      headers: { "Idempotency-Key": key },
    });
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.WAREHOUSES.CREATE, body, {
      headers: { "Idempotency-Key": key },
    });
  });

  it("rejects blank idempotency keys before making mutation requests", async () => {
    await expect(
      inventoryService.createWarehouse(
        {
          warehouse_code: "CENTRAL",
          warehouse_name: "Central",
          warehouse_type: "distribution_center",
          country_code: "IN",
          timezone: "Asia/Kolkata",
        },
        " "
      )
    ).rejects.toThrow("An idempotency key is required.");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("sends optimistic version preconditions", async () => {
    api.patch.mockResolvedValue({ data: { id: "w-1" }, meta });
    await inventoryService.updateWarehouse("w-1", { warehouse_name: "North" }, 7);
    expect(api.patch).toHaveBeenCalledWith(
      ENDPOINTS.WAREHOUSES.UPDATE("w-1"),
      { warehouse_name: "North" },
      { headers: { "If-Match": "7" } }
    );
  });

  it("falls back to timestamp and random entropy when Web Crypto UUIDs are unavailable", () => {
    const dateNow = vi.spyOn(Date, "now").mockReturnValue(123);
    const random = vi.spyOn(Math, "random").mockReturnValue(0.5);
    vi.stubGlobal("crypto", undefined);

    try {
      expect(createIdempotencyKey("fallback")).toBe("inventory:fallback:123-i");
    } finally {
      dateNow.mockRestore();
      random.mockRestore();
    }
  });

  it("uses Web Crypto UUIDs when available", () => {
    const randomUUID = vi.fn(() => "uuid-42");
    vi.stubGlobal("crypto", { randomUUID });

    expect(createIdempotencyKey("warehouse-create")).toBe("inventory:warehouse-create:uuid-42");
    expect(randomUUID).toHaveBeenCalledOnce();
  });

  it("falls back when a crypto object exists without randomUUID support", () => {
    const dateNow = vi.spyOn(Date, "now").mockReturnValue(456);
    const random = vi.spyOn(Math, "random").mockReturnValue(0.25);
    vi.stubGlobal("crypto", {});

    try {
      expect(createIdempotencyKey("legacy-browser")).toBe("inventory:legacy-browser:456-9");
    } finally {
      dateNow.mockRestore();
      random.mockRestore();
    }
  });
});

describe("inventory configuration preview service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("wraps configuration preview documents for the backend preview contract", async () => {
    const expectedDocument = { ...configurationDocument };
    delete (expectedDocument as Partial<typeof configurationDocument>).change_reason;
    api.post.mockResolvedValue({
      data: {
        valid: true,
        changes: [{ field: "max_lines_per_entry", before: 500, after: 100 }],
        affected_behaviors: ["posting"],
      },
      meta,
    });

    const result = await inventoryService.previewConfiguration(
      "development",
      configurationDocument
    );

    expect(api.post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATIONS.PREVIEW("development"), {
      document: expectedDocument,
    });
    expect(result.data).toEqual({
      valid: true,
      diff: [
        {
          field: "max_lines_per_entry",
          previous: 500,
          proposed: 100,
          behavior_impact: "posting",
        },
      ],
      affected_behaviors: ["posting"],
      warnings: [],
    });
  });
});

describe("inventory configuration preview normalization", () => {
  beforeEach(() => vi.clearAllMocks());

  it("passes through backend preview diffs and filters malformed optional arrays", async () => {
    api.post.mockResolvedValue({
      data: {
        valid: true,
        diff: [
          {
            field: "reservation_ttl_minutes",
            previous: 60,
            proposed: 90,
            behavior_impact: "reservations",
          },
          { field: 7, previous: "bad", proposed: "bad", behavior_impact: "bad" },
        ],
        affected_behaviors: ["reservations", 42],
        warnings: ["Review TTL", false],
      },
      meta,
    });

    const result = await inventoryService.previewConfiguration(
      "development",
      configurationDocument
    );

    expect(result.data).toEqual({
      valid: true,
      diff: [
        {
          field: "reservation_ttl_minutes",
          previous: 60,
          proposed: 90,
          behavior_impact: "reservations",
        },
      ],
      affected_behaviors: ["reservations"],
      warnings: ["Review TTL"],
    });
  });

  it("normalizes backend preview changes for every behavior class", async () => {
    api.post.mockResolvedValue({
      data: {
        valid: true,
        changes: [
          { field: "reservation_ttl_minutes", before: undefined, after: null },
          { field: "expiry_warning_days", before: 30, after: 45 },
          { field: "enabled_capabilities", before: { bulk_import: true }, after: "locked" },
          { field: "auto_expire_batches", before: true, after: false },
        ],
      },
      meta,
    });

    const result = await inventoryService.previewConfiguration(
      "development",
      configurationDocument
    );

    expect(result.data.diff).toEqual([
      {
        field: "reservation_ttl_minutes",
        previous: null,
        proposed: null,
        behavior_impact: "reservations",
      },
      {
        field: "expiry_warning_days",
        previous: 30,
        proposed: 45,
        behavior_impact: "batch_monitoring",
      },
      {
        field: "enabled_capabilities",
        previous: JSON.stringify({ bulk_import: true }),
        proposed: "locked",
        behavior_impact: "capability_rollout",
      },
      {
        field: "auto_expire_batches",
        previous: true,
        proposed: false,
        behavior_impact: "batch_monitoring",
      },
    ]);
  });

  it("normalizes malformed preview payloads to fail closed defaults", async () => {
    api.post.mockResolvedValue({
      data: {
        valid: false,
        changes: "not-a-list",
        affected_behaviors: "posting",
        warnings: undefined,
      },
      meta,
    });

    const result = await inventoryService.previewConfiguration(
      "development",
      configurationDocument
    );

    expect(result.data).toEqual({
      valid: false,
      diff: [],
      affected_behaviors: [],
      warnings: [],
    });
  });

  it("does not fabricate preview diff rows when backend changes are malformed", async () => {
    api.post.mockResolvedValue({
      data: {
        valid: true,
        changes: "malformed-change-list",
      },
      meta,
    });

    const result = await inventoryService.previewConfiguration(
      "development",
      configurationDocument
    );

    expect(result.data).toEqual({
      valid: true,
      diff: [],
      affected_behaviors: [],
      warnings: [],
    });
  });

  it("filters malformed preview changes and assigns unknown field impact deterministically", async () => {
    api.post.mockResolvedValue({
      data: {
        valid: false,
        changes: [
          "not-an-object",
          { field: 42, before: "before", after: "after" },
          { before: false, after: true },
        ],
      },
      meta,
    });

    const result = await inventoryService.previewConfiguration(
      "development",
      configurationDocument
    );

    expect(result.data.diff).toEqual([
      {
        field: "unknown",
        previous: "before",
        proposed: "after",
        behavior_impact: "capability_rollout",
      },
      {
        field: "unknown",
        previous: false,
        proposed: true,
        behavior_impact: "capability_rollout",
      },
    ]);
  });

  it.each([
    ["allow_negative_stock", false, true],
    ["require_stock_entry_approval", true, false],
    ["default_valuation_method", "fifo", "weighted_average"],
  ])("maps %s preview changes to posting behavior", async (field, before, after) => {
    api.post.mockResolvedValue({
      data: {
        valid: true,
        changes: [{ field, before, after }],
      },
      meta,
    });

    const result = await inventoryService.previewConfiguration(
      "development",
      configurationDocument
    );

    expect(result.data.diff).toEqual([
      {
        field,
        previous: before,
        proposed: after,
        behavior_impact: "posting",
      },
    ]);
  });

  it("drops backend preview diff rows without behavior impact evidence", async () => {
    api.post.mockResolvedValue({
      data: {
        valid: true,
        diff: [
          {
            field: "reservation_ttl_minutes",
            previous: 60,
            proposed: 90,
            behavior_impact: 42,
          },
          {
            field: "expiry_warning_days",
            previous: 30,
            proposed: 45,
            behavior_impact: "batch_monitoring",
          },
        ],
      },
      meta,
    });

    const result = await inventoryService.previewConfiguration(
      "development",
      configurationDocument
    );

    expect(result.data.diff).toEqual([
      {
        field: "expiry_warning_days",
        previous: 30,
        proposed: 45,
        behavior_impact: "batch_monitoring",
      },
    ]);
  });
});

describe("inventory query keys", () => {
  beforeEach(() => vi.clearAllMocks());

  it("roots every query key in the tenant", () => {
    const filters = { page: 2, search: "north" };

    expect(inventoryQueryKeys.root("tenant-a")).toEqual(["inventory-management", "tenant-a"]);
    expect(inventoryQueryKeys.resource("tenant-a", "warehouses")).toEqual([
      "inventory-management",
      "tenant-a",
      "warehouses",
    ]);
    expect(inventoryQueryKeys.list("tenant-a", "warehouses", filters)).toEqual([
      "inventory-management",
      "tenant-a",
      "warehouses",
      "list",
      filters,
    ]);
    expect(inventoryQueryKeys.detail("tenant-a", "warehouses", "w-1")).toEqual([
      "inventory-management",
      "tenant-a",
      "warehouses",
      "detail",
      "w-1",
    ]);
    expect(inventoryQueryKeys.dashboard("tenant-b")).toEqual([
      "inventory-management",
      "tenant-b",
      "dashboard",
    ]);
  });
});
