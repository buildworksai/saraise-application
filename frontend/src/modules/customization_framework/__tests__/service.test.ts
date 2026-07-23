/* eslint-disable @typescript-eslint/unbound-method -- assertions intentionally reference mocked client methods. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import { ENDPOINTS, type ApiV2Envelope, type CustomFieldDefinition } from "../contracts";
import { customizationFrameworkService as service } from "../services/customization-framework-service";

vi.mock("@/services/api-client", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

const field: CustomFieldDefinition = {
  id: "00000000-0000-4000-8000-000000000001", tenant_id: "00000000-0000-4000-8000-000000000002", key: "delivery-note", label: "Delivery note", description: "", owner_module: "sales_management", target_resource: "sales_order", target_contract_version: "1.0", data_type: "text", required: false, searchable: true, default_value: null, validation_schema: { maxLength: 160 }, presentation_schema: { label: "Delivery note" }, status: "active", activated_at: "2026-07-22T00:00:00Z", deprecated_at: null, retired_at: null, transition_history: [], dependency_count: 2, value_count: 5, capability_state: "available", created_by: "00000000-0000-4000-8000-000000000003", updated_by: "00000000-0000-4000-8000-000000000003", created_at: "2026-07-22T00:00:00Z", updated_at: "2026-07-22T00:00:00Z", deleted_at: null, deleted_by: null, lock_version: 3,
};
const envelope: ApiV2Envelope<readonly CustomFieldDefinition[]> = { data: [field], meta: { correlation_id: "00000000-0000-4000-8000-000000000004", timestamp: "2026-07-22T00:00:00Z", pagination: { count: 1, page: 2, page_size: 25, total_pages: 2, has_next: false, has_previous: true } } };

describe("customization framework service", () => {
  beforeEach(() => vi.clearAllMocks());

  it("preserves governed envelopes and emits typed server query state", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(envelope);
    await expect(service.listFields({ status: "active", search: "delivery", ordering: "label", page: 2 })).resolves.toEqual(envelope);
    expect(apiClient.get).toHaveBeenCalledWith(`${ENDPOINTS.FIELD_DEFINITIONS.LIST}?status=active&search=delivery&ordering=label&page=2`);
  });

  it("uses PATCH with optimistic-lock payloads", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ data: field, meta: envelope.meta });
    await service.updateField(field.id, { label: "Dispatch note", expected_lock_version: 3 });
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.FIELD_DEFINITIONS.UPDATE(field.id), { label: "Dispatch note", expected_lock_version: 3 }, expect.objectContaining({ headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }) }));
  });

  it("targets exact lifecycle and non-persisting validation endpoints", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: field, meta: envelope.meta });
    await service.transitionField(field.id, "deprecate", { transition_key: "transition-1" });
    await service.validateValue(field.id, { value: "safe" });
    expect(apiClient.post).toHaveBeenNthCalledWith(1, ENDPOINTS.FIELD_DEFINITIONS.DEPRECATE(field.id), { transition_key: "transition-1" }, expect.any(Object));
    expect(apiClient.post).toHaveBeenNthCalledWith(2, ENDPOINTS.FIELD_DEFINITIONS.VALIDATE_VALUE(field.id), { value: "safe" });
  });

  it("does not fabricate execution deletion or mutation methods", () => {
    expect("deleteExecution" in service).toBe(false);
    expect("updateExecution" in service).toBe(false);
  });
});
