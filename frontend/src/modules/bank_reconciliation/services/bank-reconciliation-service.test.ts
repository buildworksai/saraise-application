/* eslint-disable @typescript-eslint/unbound-method -- assertions intentionally inspect mocked client methods. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import { bankReconciliationService } from "./bank-reconciliation-service";

vi.mock("@/services/api-client", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public details?: object,
      public code?: string,
      public correlationId?: string
    ) {
      super(message);
    }
  },
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const mockedClient = vi.mocked(apiClient);

describe("bank reconciliation service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("unwraps only the governed collection envelope and preserves metadata", async () => {
    vi.mocked(mockedClient.get).mockResolvedValue({
      data: [],
      meta: {
        correlation_id: "req-1",
        timestamp: "2026-07-23T00:00:00Z",
        pagination: {
          page: 2,
          page_size: 25,
          total_pages: 3,
          count: 55,
          has_next: true,
          has_previous: true,
        },
      },
    });
    const result = await bankReconciliationService.listBankAccounts({
      page: 2,
      search: "operating",
    });
    expect(mockedClient.get).toHaveBeenCalledWith(
      `${ENDPOINTS.ACCOUNTS.LIST}?page=2&search=operating`
    );
    expect(result.items).toEqual([]);
    expect(result.correlationId).toBe("req-1");
    expect(result.pagination.page).toBe(2);
    expect(result.pagination.count).toBe(55);
  });

  it("uses archive DELETE semantics rather than physical-delete language or PUT", async () => {
    vi.mocked(mockedClient.delete).mockResolvedValue(undefined);
    await bankReconciliationService.archiveBankAccount("account-1");
    expect(mockedClient.delete).toHaveBeenCalledWith(ENDPOINTS.ACCOUNTS.ARCHIVE("account-1"));
  });
});
