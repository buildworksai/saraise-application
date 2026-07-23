import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/services/api-client";
import type { ApiError } from "@/services/api-client";
import { notificationQuery, notificationService } from "../services/notification-service";

const meta = { correlation_id: "00000000-0000-4000-8000-000000000001", timestamp: "2026-01-01T00:00:00Z" };
describe("notification service", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("serializes governed filters without unsupported RequestInit params", () => {
    expect(notificationQuery("/inbox/", { page: 2, search: "pay roll", status: undefined })).toBe("/inbox/?page=2&search=pay+roll");
  });
  it("unwraps pages, exposes capabilities, and forwards cancellation", async () => {
    const controller = new AbortController();
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: [], meta: { ...meta, pagination: { count: 0, page: 1, page_size: 25, total_pages: 1, has_next: false, has_previous: false } }, capabilities: ["notifications.template:create"] });
    const result = await notificationService.templates.list({ search: "security" }, controller.signal);
    expect(result.capabilities).toEqual(["notifications.template:create"]);
    expect(get).toHaveBeenCalledWith(expect.stringContaining("search=security"), expect.objectContaining({ signal: controller.signal }));
  });
  it("propagates idempotency keys in payload and header", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: "delivery" }, meta });
    const input = { template_id: "template", recipient: { type: "user" as const, user_id: "user" }, context: {}, priority: 5, idempotency_key: "dispatch-key" };
    await notificationService.deliveries.create(input);
    expect(post).toHaveBeenCalledWith(expect.stringContaining("/deliveries/"), input, expect.objectContaining({ headers: { "X-Idempotency-Key": "dispatch-key" } }));
  });
  it("generates an idempotency header for template creation", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: "template" }, meta });
    await notificationService.templates.create({ code: "security.alert", name: "Security alert", category: "security_alerts", channel: "in_app", locale: "en", subject_template: "", body_template: "{{ message }}", variables_schema: { message: { type: "string", required: true } }, content_type: "text/plain" });
    expect(post.mock.calls[0]?.[0]).toContain("/templates/");
    expect(post.mock.calls[0]?.[1]).toMatchObject({ code: "security.alert" });
    const init = post.mock.calls[0]?.[2];
    expect(typeof (init?.headers as Record<string, string> | undefined)?.["X-Idempotency-Key"]).toBe("string");
  });
  it("fails explicitly on legacy or fabricated collection responses", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue([]);
    await expect(notificationService.inbox.list()).rejects.toMatchObject({ status: 502, code: "MALFORMED_RESPONSE" } satisfies Partial<ApiError>);
  });
});
