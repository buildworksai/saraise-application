import { beforeEach, describe, expect, it, vi } from "vitest";
import { ENDPOINTS } from "../contracts";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@/services/api-client", async (original) => ({ ...(await original<object>()), apiClient: api }));

import { createIdempotencyKey, inventoryQueryKeys, inventoryService } from "./inventory-service";

const meta = { correlation_id: "corr-42", timestamp: "2026-07-23T00:00:00Z" };

describe("inventory service governance", () => {
  beforeEach(() => vi.clearAllMocks());

  it("preserves correlation and validates governed pagination", async () => {
    api.get.mockResolvedValue({ data: [], meta: { ...meta, pagination: { page: 1, page_size: 25, total_count: 0, total_pages: 0, next: null, previous: null } } });
    const result = await inventoryService.listWarehouses({ search: "central", page: 1 });
    expect(api.get).toHaveBeenCalledWith(`${ENDPOINTS.WAREHOUSES.LIST}?search=central&page=1`);
    expect(result.correlationId).toBe("corr-42");
    expect(result.pagination.total_count).toBe(0);
  });

  it("never converts a malformed list envelope into an empty success", async () => {
    api.get.mockResolvedValue({ data: [] });
    await expect(inventoryService.listWarehouses()).rejects.toMatchObject({ status: 502, code: "malformed_pagination" });
  });

  it("uses the caller's stable idempotency key across retries", async () => {
    const key = createIdempotencyKey("warehouse-create");
    const warehouse = { id: "w-1", warehouse_name: "Central" };
    api.post.mockResolvedValue({ data: warehouse, meta });
    const body = { warehouse_code: "CENTRAL", warehouse_name: "Central", warehouse_type: "distribution_center" as const, country_code: "IN", timezone: "Asia/Kolkata" };
    await inventoryService.createWarehouse(body, key);
    await inventoryService.createWarehouse(body, key);
    expect(api.post).toHaveBeenNthCalledWith(1, ENDPOINTS.WAREHOUSES.CREATE, body, { headers: { "Idempotency-Key": key } });
    expect(api.post).toHaveBeenNthCalledWith(2, ENDPOINTS.WAREHOUSES.CREATE, body, { headers: { "Idempotency-Key": key } });
  });

  it("sends optimistic version preconditions", async () => {
    api.patch.mockResolvedValue({ data: { id: "w-1" }, meta });
    await inventoryService.updateWarehouse("w-1", { warehouse_name: "North" }, 7);
    expect(api.patch).toHaveBeenCalledWith(ENDPOINTS.WAREHOUSES.UPDATE("w-1"), { warehouse_name: "North" }, { headers: { "If-Match": "7" } });
  });

  it("roots every query key in the tenant", () => {
    expect(inventoryQueryKeys.detail("tenant-a", "warehouses", "w-1")).toEqual(["inventory-management", "tenant-a", "warehouses", "detail", "w-1"]);
    expect(inventoryQueryKeys.dashboard("tenant-b")).toEqual(["inventory-management", "tenant-b", "dashboard"]);
  });
});
