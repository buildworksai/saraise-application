/* eslint-disable max-lines-per-function -- mutation-focused service boundary tests intentionally keep endpoint matrices local. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiError, apiClient as ApiClient } from "@/services/api-client";
import type {
  ChannelConfiguration,
  ENDPOINTS as NotificationEndpoints,
  NotificationConfigurationDocument,
} from "../contracts";
import type * as NotificationServiceModule from "../services/notification-service";

let apiClient: typeof ApiClient;
let ENDPOINTS: typeof NotificationEndpoints;
let notificationModule: typeof NotificationServiceModule;

const meta = {
  correlation_id: "00000000-0000-4000-8000-000000000001",
  timestamp: "2026-01-01T00:00:00Z",
};

const governed = <T>(data: T) => ({ data, meta });
const governedPage = <T>(data: readonly T[] = []) => ({
  data,
  meta: {
    ...meta,
    pagination: {
      count: data.length,
      page: 1,
      page_size: 25,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
  },
  capabilities: ["notifications.template:create"],
});

const transition = { transition_key: "transition-key" };
const retry = { idempotency_key: "retry-key" };
const channelConfiguration = (adapterKey: string): ChannelConfiguration => ({
  enabled: true,
  adapter_key: adapterKey,
  credential_ref: `${adapterKey}-credential`,
  sender_ref: `${adapterKey}-sender`,
  timeout_seconds: 10,
  retry: { max_attempts: 3, base_seconds: 1, maximum_seconds: 30 },
  circuit: { failure_threshold: 5, reset_seconds: 60 },
  rate_limit_per_minute: 120,
});
const configurationDocument = (): NotificationConfigurationDocument => ({
  schema_version: 1,
  channels: {
    in_app: channelConfiguration("in-app"),
    email: channelConfiguration("email"),
    sms: channelConfiguration("sms"),
    push: channelConfiguration("push"),
    webhook: channelConfiguration("webhook"),
  },
  preferences: { default_enabled: true, mandatory_categories: [] },
  batch_size: 10,
  max_attempts: 3,
  backoff: { base_seconds: 1, maximum_seconds: 30 },
  retention: { delivery_days: 30, inbox_days: 30 },
  limits: { context_bytes: 1024, metadata_bytes: 1024 },
  allowed_action_url_hosts: [],
  allowed_webhook_hosts: [],
  feature_flags: {},
  digest_schedules: { hourly_minute: 0, daily_time: "09:00", weekly_day: 1 },
  quiet_hours: { start: null, end: null, timezone: "UTC" },
  provider_callbacks: { timestamp_tolerance_seconds: 300 },
});

describe("notification service", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    vi.resetModules();
    ({ apiClient } = await import("@/services/api-client"));
    ({ ENDPOINTS } = await import("../contracts"));
    notificationModule = await import("../services/notification-service");
  });

  it("publishes stable query keys for every governed cache family", () => {
    const { NOTIFICATION_QUERY_KEYS } = notificationModule;
    expect(NOTIFICATION_QUERY_KEYS.all).toEqual(["notifications"]);
    expect(NOTIFICATION_QUERY_KEYS.inbox({ page: 2 })).toEqual([
      "notifications",
      "inbox",
      { page: 2 },
    ]);
    expect(NOTIFICATION_QUERY_KEYS.inboxItem("inbox id")).toEqual([
      "notifications",
      "inbox",
      "inbox id",
    ]);
    expect(NOTIFICATION_QUERY_KEYS.unread).toEqual(["notifications", "unread-count"]);
    expect(NOTIFICATION_QUERY_KEYS.preferences).toEqual(["notifications", "preferences"]);
    expect(NOTIFICATION_QUERY_KEYS.templates({ status: "draft" })).toEqual([
      "notifications",
      "templates",
      { status: "draft" },
    ]);
    expect(NOTIFICATION_QUERY_KEYS.template("template id")).toEqual([
      "notifications",
      "template",
      "template id",
    ]);
    expect(NOTIFICATION_QUERY_KEYS.deliveries({ status: "failed" })).toEqual([
      "notifications",
      "deliveries",
      { status: "failed" },
    ]);
    expect(NOTIFICATION_QUERY_KEYS.delivery("delivery id")).toEqual([
      "notifications",
      "delivery",
      "delivery id",
    ]);
    expect(NOTIFICATION_QUERY_KEYS.endpoints({ active: false })).toEqual([
      "notifications",
      "endpoints",
      { active: false },
    ]);
    expect(NOTIFICATION_QUERY_KEYS.endpoint("endpoint id")).toEqual([
      "notifications",
      "endpoint",
      "endpoint id",
    ]);
    expect(NOTIFICATION_QUERY_KEYS.configuration("production")).toEqual([
      "notifications",
      "configuration",
      "production",
    ]);
    expect(NOTIFICATION_QUERY_KEYS.configurationHistory("staging", 3)).toEqual([
      "notifications",
      "configuration",
      "staging",
      "history",
      3,
    ]);
    expect(NOTIFICATION_QUERY_KEYS.health).toEqual(["notifications", "health"]);
  });
  it("serializes governed filters without unsupported RequestInit params", () => {
    const { notificationQuery } = notificationModule;
    expect(
      notificationQuery("/inbox/", {
        page: 2,
        search: "pay roll",
        status: undefined,
        unset: null,
        empty: "",
        archived: false,
        count: 0,
      })
    ).toBe("/inbox/?page=2&search=pay+roll&archived=false&count=0");
  });
  it("unwraps pages, exposes capabilities, and forwards cancellation", async () => {
    const { notificationService } = notificationModule;
    const controller = new AbortController();
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(governedPage());
    const result = await notificationService.templates.list(
      { search: "security" },
      controller.signal
    );
    expect(result.capabilities).toEqual(["notifications.template:create"]);
    expect(result.meta).toEqual({
      correlation_id: meta.correlation_id,
      timestamp: meta.timestamp,
    });
    expect(get).toHaveBeenCalledWith(
      expect.stringContaining("search=security"),
      expect.objectContaining({ signal: controller.signal })
    );
  });
  it("defaults missing collection capabilities to an empty list", async () => {
    const { notificationService } = notificationModule;
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [],
      meta: governedPage().meta,
    });
    await expect(notificationService.inbox.list()).resolves.toMatchObject({
      capabilities: [],
    });
  });
  it("propagates idempotency keys in payload and header", async () => {
    const { notificationService } = notificationModule;
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: "delivery" }, meta });
    const input = {
      template_id: "template",
      recipient: { type: "user" as const, user_id: "user" },
      context: {},
      priority: 5,
      idempotency_key: "dispatch-key",
    };
    await notificationService.deliveries.create(input);
    expect(post).toHaveBeenCalledWith(
      expect.stringContaining("/deliveries/"),
      input,
      expect.objectContaining({ headers: { "X-Idempotency-Key": "dispatch-key" } })
    );
  });
  it("generates an idempotency header for template creation", async () => {
    const { notificationService } = notificationModule;
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: { id: "template" }, meta });
    await notificationService.templates.create({
      code: "security.alert",
      name: "Security alert",
      category: "security_alerts",
      channel: "in_app",
      locale: "en",
      subject_template: "",
      body_template: "{{ message }}",
      variables_schema: { message: { type: "string", required: true } },
      content_type: "text/plain",
    });
    expect(post.mock.calls[0]?.[0]).toContain("/templates/");
    expect(post.mock.calls[0]?.[1]).toMatchObject({ code: "security.alert" });
    const init = post.mock.calls[0]?.[2];
    expect(
      typeof (init?.headers as Record<string, string> | undefined)?.["X-Idempotency-Key"]
    ).toBe("string");
  });
  it("fails explicitly on legacy or fabricated collection responses", async () => {
    const { notificationService } = notificationModule;
    vi.spyOn(apiClient, "get").mockResolvedValue([]);
    await expect(notificationService.inbox.list()).rejects.toMatchObject({
      message: "Notifications returned a malformed collection response.",
      status: 502,
      code: "MALFORMED_RESPONSE",
    } satisfies Partial<ApiError>);
  });
  it("fails explicitly when governed singleton responses omit metadata", async () => {
    const { notificationService } = notificationModule;
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { count: 1 }, meta: {} });
    await expect(notificationService.inbox.unreadCount()).rejects.toMatchObject({
      message: "Notifications returned a malformed governed response.",
      status: 502,
      code: "MALFORMED_RESPONSE",
    } satisfies Partial<ApiError>);
  });
  it.each(["legacy", null, [], { meta }, { data: { count: 1 }, meta: { correlation_id: 7 } }])(
    "fails explicitly for malformed singleton variant %#",
    async (response) => {
      const { notificationService } = notificationModule;
      vi.spyOn(apiClient, "get").mockResolvedValue(response);
      await expect(notificationService.inbox.unreadCount()).rejects.toMatchObject({
        message: "Notifications returned a malformed governed response.",
        status: 502,
        code: "MALFORMED_RESPONSE",
      } satisfies Partial<ApiError>);
    }
  );
  it("fails explicitly when governed collections omit pagination metadata", async () => {
    const { notificationService } = notificationModule;
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: [], meta });
    await expect(notificationService.templates.list()).rejects.toMatchObject({
      message: "Notifications omitted governed pagination metadata.",
      status: 502,
      code: "MALFORMED_RESPONSE",
      correlationId: meta.correlation_id,
    } satisfies Partial<ApiError>);
  });
  it.each([
    null,
    "legacy",
    [],
    { data: {}, meta },
    { data: [], meta: { pagination: governedPage().meta.pagination } },
    { data: [], meta: { correlation_id: 7 } },
    { data: [], meta: { ...meta, pagination: { ...governedPage().meta.pagination, page: "1" } } },
    { data: [], meta: { ...meta, pagination: { ...governedPage().meta.pagination, count: "0" } } },
    {
      data: [],
      meta: { ...meta, pagination: { ...governedPage().meta.pagination, has_next: "false" } },
    },
    {
      data: [],
      meta: { ...meta, pagination: { ...governedPage().meta.pagination, has_previous: "false" } },
    },
  ])("fails explicitly for malformed collection variant %#", async (response) => {
    const { notificationService } = notificationModule;
    vi.spyOn(apiClient, "get").mockResolvedValue(response);
    await expect(notificationService.templates.list()).rejects.toMatchObject({
      status: 502,
      code: "MALFORMED_RESPONSE",
    } satisfies Partial<ApiError>);
  });
  it("uses governed GET endpoints for singleton and paginated reads", async () => {
    const { notificationService } = notificationModule;
    const get = vi.spyOn(apiClient, "get").mockImplementation((path: string) => {
      if (path.includes("?") || path.endsWith("/attempts/") || path.endsWith("/history/")) {
        return Promise.resolve(governedPage());
      }
      return Promise.resolve(governed({ id: "resource", count: 7, ready: true, live: true }));
    });

    expect(await notificationService.getUnreadCount()).toBe(7);
    await notificationService.inbox.list({ status: "unread" });
    await notificationService.inbox.get("inbox id");
    await notificationService.inbox.unreadCount();
    await notificationService.templates.list({ status: "draft" });
    await notificationService.templates.get("template id");
    await notificationService.templates.versions("template id", { page: 2 });
    await notificationService.deliveries.list({ status: "failed" });
    await notificationService.deliveries.get("delivery id");
    await notificationService.deliveries.attempts("delivery id", { page_size: 10 });
    await notificationService.preferences.get();
    await notificationService.endpoints.list({ active: false });
    await notificationService.endpoints.get("endpoint id");
    await notificationService.configuration.get("production");
    await notificationService.configuration.history("staging", { page: 3 });
    await notificationService.configuration.exportDocument("development");
    await notificationService.health.live();
    await notificationService.health.ready();

    expect(get).toHaveBeenCalledTimes(18);
    expect(get.mock.calls.map(([path]) => path)).toEqual([
      ENDPOINTS.INBOX.UNREAD_COUNT,
      `${ENDPOINTS.INBOX.LIST}?status=unread`,
      ENDPOINTS.INBOX.DETAIL("inbox id"),
      ENDPOINTS.INBOX.UNREAD_COUNT,
      `${ENDPOINTS.TEMPLATES.LIST}?status=draft`,
      ENDPOINTS.TEMPLATES.DETAIL("template id"),
      `${ENDPOINTS.TEMPLATES.VERSIONS("template id")}?page=2`,
      `${ENDPOINTS.DELIVERIES.LIST}?status=failed`,
      ENDPOINTS.DELIVERIES.DETAIL("delivery id"),
      `${ENDPOINTS.DELIVERIES.ATTEMPTS("delivery id")}?page_size=10`,
      ENDPOINTS.PREFERENCES.ME,
      `${ENDPOINTS.ENDPOINTS.LIST}?active=false`,
      ENDPOINTS.ENDPOINTS.DETAIL("endpoint id"),
      ENDPOINTS.CONFIGURATION.DETAIL("production"),
      `${ENDPOINTS.CONFIGURATION.HISTORY("staging")}?page=3`,
      ENDPOINTS.CONFIGURATION.EXPORT("development"),
      ENDPOINTS.HEALTH.LIVE,
      ENDPOINTS.HEALTH.READY,
    ]);
  });
  it("uses governed POST endpoints with required transition and idempotency headers", async () => {
    const { notificationService } = notificationModule;
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(governed({ id: "resource" }));
    const deliveryInput = {
      template_id: "template",
      recipient: { type: "user" as const, user_id: "user" },
      context: {},
      priority: 1,
      idempotency_key: "dispatch-key",
    };

    await notificationService.inbox.markRead("inbox id", transition);
    await notificationService.inbox.markUnread("inbox id", transition);
    await notificationService.inbox.archive("inbox id", transition);
    await notificationService.inbox.markAllRead(transition);
    await notificationService.templates.create({
      code: "security.alert",
      name: "Security alert",
      category: "security_alerts",
      channel: "in_app",
      locale: "en",
      subject_template: "",
      body_template: "{{ message }}",
      variables_schema: { message: { type: "string", required: true } },
      content_type: "text/plain",
    });
    await notificationService.templates.createVersion("template id", {
      subject_template: "",
      body_template: "{{ message }}",
      variables_schema: { message: { type: "string", required: true } },
      content_type: "text/plain",
    });
    await notificationService.templates.previewDraft({ context: {} });
    await notificationService.templates.preview("template id", { context: {} });
    await notificationService.templates.activate("template id", transition);
    await notificationService.templates.restore("template id", transition);
    await notificationService.templates.rollback("template id", {
      version: 2,
      transition_key: "transition-key",
    });
    await notificationService.deliveries.create(deliveryInput);
    await notificationService.deliveries.bulk({
      deliveries: [deliveryInput],
      idempotency_key: "bulk-key",
    });
    await notificationService.deliveries.preview(deliveryInput);
    await notificationService.deliveries.retry("delivery id", retry);
    await notificationService.deliveries.cancel("delivery id", transition);
    await notificationService.preferences.reset();
    await notificationService.endpoints.register({
      kind: "webhook",
      device_type: "",
      address: "https://hooks.example.test",
      display_name: "Webhook",
    });
    await notificationService.endpoints.verify("endpoint id");
    await notificationService.configuration.simulate("production", {
      document: configurationDocument(),
      scenario: { channel: "in_app", category: "security", priority: 5 },
    });
    await notificationService.configuration.rollback("production", {
      target_version: 1,
      expected_version: 2,
      change_summary: "Rollback",
    });
    await notificationService.configuration.importDocument("production", {
      document: configurationDocument(),
      expected_version: 2,
      dry_run: true,
      change_summary: "Import",
    });

    expect(post).toHaveBeenCalledTimes(22);
    const calls = post.mock.calls.map(([path, , init]) => ({
      path,
      headers: init?.headers,
    }));
    expect(calls).toEqual(
      expect.arrayContaining([
        {
          path: ENDPOINTS.INBOX.MARK_READ("inbox id"),
          headers: { "X-Transition-Key": "transition-key" },
        },
        {
          path: ENDPOINTS.INBOX.MARK_UNREAD("inbox id"),
          headers: { "X-Transition-Key": "transition-key" },
        },
        {
          path: ENDPOINTS.INBOX.ARCHIVE("inbox id"),
          headers: { "X-Transition-Key": "transition-key" },
        },
        {
          path: ENDPOINTS.INBOX.MARK_ALL_READ,
          headers: { "X-Transition-Key": "transition-key" },
        },
        {
          path: ENDPOINTS.DELIVERIES.URGENT,
          headers: { "X-Idempotency-Key": "dispatch-key" },
        },
        { path: ENDPOINTS.DELIVERIES.BULK, headers: { "X-Idempotency-Key": "bulk-key" } },
        {
          path: ENDPOINTS.DELIVERIES.RETRY("delivery id"),
          headers: { "X-Idempotency-Key": "retry-key" },
        },
        {
          path: ENDPOINTS.DELIVERIES.CANCEL("delivery id"),
          headers: { "X-Transition-Key": "transition-key" },
        },
        {
          path: ENDPOINTS.TEMPLATES.ACTIVATE("template id"),
          headers: { "X-Transition-Key": "transition-key" },
        },
        {
          path: ENDPOINTS.TEMPLATES.RESTORE("template id"),
          headers: { "X-Transition-Key": "transition-key" },
        },
        {
          path: ENDPOINTS.TEMPLATES.ROLLBACK("template id"),
          headers: { "X-Transition-Key": "transition-key" },
        },
      ])
    );
    expect(calls.map((call) => call.path)).toEqual(
      expect.arrayContaining([
        ENDPOINTS.TEMPLATES.LIST,
        ENDPOINTS.TEMPLATES.VERSIONS("template id"),
        ENDPOINTS.TEMPLATES.PREVIEW_DRAFT,
        ENDPOINTS.TEMPLATES.PREVIEW("template id"),
        ENDPOINTS.DELIVERIES.PREVIEW,
        ENDPOINTS.PREFERENCES.RESET,
        ENDPOINTS.ENDPOINTS.LIST,
        ENDPOINTS.ENDPOINTS.VERIFY("endpoint id"),
        ENDPOINTS.CONFIGURATION.SIMULATE("production"),
        ENDPOINTS.CONFIGURATION.ROLLBACK("production"),
        ENDPOINTS.CONFIGURATION.IMPORT("production"),
      ])
    );
  });
  it("uses governed write verbs for updates, archives, replaces, revokes, and configuration writes", async () => {
    const { notificationService } = notificationModule;
    const patch = vi.spyOn(apiClient, "patch").mockResolvedValue(governed({ id: "resource" }));
    const put = vi.spyOn(apiClient, "put").mockResolvedValue(governed({ preferences: [] }));
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue(governed({ id: "resource" }));

    await notificationService.templates.update("template id", {
      subject_template: "",
      body_template: "{{ message }}",
      variables_schema: { message: { type: "string", required: true } },
      content_type: "text/plain",
    });
    await notificationService.templates.archive("template id", transition);
    await notificationService.preferences.replace({ preferences: [] });
    await notificationService.endpoints.update("endpoint id", { display_name: "Updated" });
    await notificationService.endpoints.revoke("endpoint id");
    await notificationService.configuration.update("production", {
      expected_version: 1,
      change_summary: "Update",
      document: configurationDocument(),
    });

    expect(patch).toHaveBeenCalledTimes(3);
    expect(put).toHaveBeenCalledTimes(1);
    expect(del).toHaveBeenCalledTimes(2);
    expect(patch.mock.calls.map(([path]) => path)).toEqual([
      ENDPOINTS.TEMPLATES.DETAIL("template id"),
      ENDPOINTS.ENDPOINTS.DETAIL("endpoint id"),
      ENDPOINTS.CONFIGURATION.DETAIL("production"),
    ]);
    expect(put).toHaveBeenCalledWith(
      ENDPOINTS.PREFERENCES.ME,
      { preferences: [] },
      expect.any(Object)
    );
    expect(del).toHaveBeenCalledWith(
      ENDPOINTS.TEMPLATES.DETAIL("template id"),
      expect.objectContaining({ headers: { "X-Transition-Key": "transition-key" } })
    );
    expect(del).toHaveBeenCalledWith(ENDPOINTS.ENDPOINTS.DETAIL("endpoint id"), expect.any(Object));
  });
  it("preserves undefined revoke responses for 204-style endpoint revocation", async () => {
    const { notificationService } = notificationModule;
    vi.spyOn(apiClient, "delete").mockResolvedValue(undefined);
    await expect(notificationService.endpoints.revoke("endpoint id")).resolves.toBeUndefined();
  });
});
