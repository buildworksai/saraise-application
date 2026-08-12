/* eslint-disable max-lines-per-function -- page workflows keep complete fixtures near payload assertions. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ConfigurationHistoryItem,
  DeliveryCancelInput,
  DeliveryRetryInput,
  EndpointQuery,
  Notification,
  NotificationConfiguration,
  NotificationConfigurationDocument,
  NotificationDelivery,
  NotificationDeliveryAttempt,
  NotificationEndpoint,
  NotificationTemplate,
  NotificationTemplateVersion,
  PaginatedData,
  PaginationMeta,
  TemplateRollbackInput,
  TemplateTransitionInput,
} from "../contracts";
import { ConfigurationHistoryPage } from "../pages/ConfigurationHistoryPage";
import { CreateEndpointPage } from "../pages/CreateEndpointPage";
import { DeliveryDetailPage } from "../pages/DeliveryDetailPage";
import { DeliveryListPage } from "../pages/DeliveryListPage";
import { EditEndpointPage } from "../pages/EditEndpointPage";
import { EndpointListPage } from "../pages/EndpointListPage";
import { NotificationHealthPage } from "../pages/NotificationHealthPage";
import { NotificationCenterPage } from "../pages/NotificationCenterPage";
import { NotificationDetailPage } from "../pages/NotificationDetailPage";
import { TemplateDetailPage } from "../pages/TemplateDetailPage";
import { TemplateListPage } from "../pages/TemplateListPage";
import { notificationService } from "../services/notification-service";

vi.mock("../services/notification-service", () => ({
  NOTIFICATION_QUERY_KEYS: {
    inbox: (query = {}) => ["notifications", "inbox", query],
    inboxItem: (id: string) => ["notifications", "inbox", id],
    unread: ["notifications", "unread-count"],
    templates: (query = {}) => ["notifications", "templates", query],
    template: (id: string) => ["notifications", "template", id],
    deliveries: (query = {}) => ["notifications", "deliveries", query],
    delivery: (id: string) => ["notifications", "delivery", id],
    endpoints: (query = {}) => ["notifications", "endpoints", query],
    endpoint: (id: string) => ["notifications", "endpoint", id],
    health: ["notifications", "health"],
    configuration: (environment: string) => ["notifications", "configuration", environment],
    configurationHistory: (environment: string, page: number) => [
      "notifications",
      "configuration",
      environment,
      "history",
      page,
    ],
  },
  notificationService: {
    inbox: {
      archive: vi.fn(),
      get: vi.fn(),
      list: vi.fn(),
      markAllRead: vi.fn(),
      markRead: vi.fn(),
      markUnread: vi.fn(),
      unreadCount: vi.fn(),
    },
    templates: {
      activate: vi.fn(),
      archive: vi.fn(),
      create: vi.fn(),
      get: vi.fn(),
      list: vi.fn(),
      preview: vi.fn(),
      rollback: vi.fn(),
      versions: vi.fn(),
    },
    deliveries: {
      attempts: vi.fn(),
      cancel: vi.fn(),
      get: vi.fn(),
      list: vi.fn(),
      retry: vi.fn(),
    },
    endpoints: {
      get: vi.fn(),
      list: vi.fn(),
      register: vi.fn(),
      revoke: vi.fn(),
      update: vi.fn(),
      verify: vi.fn(),
    },
    health: {
      live: vi.fn(),
      ready: vi.fn(),
    },
    configuration: {
      get: vi.fn(),
      history: vi.fn(),
      rollback: vi.fn(),
    },
  },
}));

const pagination: PaginationMeta = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 2,
  has_next: true,
  has_previous: false,
};

const pageMeta = { correlation_id: "corr-page", timestamp: "2026-07-24T00:00:00Z" };

const versionOne: NotificationTemplateVersion = {
  id: "version-1",
  version: 1,
  subject_template: "Receipt",
  body_template: "Paid {{ amount }}",
  variables_schema: { amount: { type: "number", required: true, example: 42 } },
  content_type: "text/plain",
  created_by: "operator-1",
  correlation_id: "corr-version-1",
  created_at: "2026-07-23T00:00:00Z",
};

const versionTwo: NotificationTemplateVersion = {
  ...versionOne,
  id: "version-2",
  version: 2,
  body_template: "Paid {{ amount }} to {{ vendor }}",
  correlation_id: "corr-version-2",
};

const template: NotificationTemplate = {
  id: "template-1",
  code: "billing.receipt",
  name: "Billing receipt",
  category: "billing",
  channel: "email",
  locale: "en-US",
  status: "active",
  active_version: versionTwo,
  latest_version: versionTwo,
  transition_history: [],
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-23T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
};

const notification: Notification = {
  id: "notification-1",
  delivery_id: "delivery-1",
  notification_type: "approval",
  category: "billing",
  title: "Invoice approval required",
  message: "Approve invoice INV-100 before the cutoff.",
  status: "unread",
  read_at: null,
  action_url: "https://evil.example.com/phish",
  metadata: { invoice: "INV-100" },
  expires_at: null,
  transition_history: [
    {
      action: "created",
      from_state: "none",
      to_state: "unread",
      actor_id: "system",
      transition_key: "created:fixture",
      correlation_id: "corr-notification",
      at: "2026-07-24T00:00:00Z",
    },
  ],
  created_at: "2026-07-24T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
};

const delivery: NotificationDelivery = {
  id: "delivery-1",
  template_version_id: "version-2",
  job_id: "job-1",
  idempotency_key: "dispatch:fixture",
  recipient_type: "email",
  recipient_user_id: null,
  recipient_display: "a***@example.com",
  channel: "email",
  category: "billing",
  priority: 7,
  status: "failed",
  scheduled_at: null,
  next_attempt_at: "2026-07-24T01:00:00Z",
  attempt_count: 2,
  max_attempts: 3,
  provider_message_id: "",
  failure_code: "smtp_timeout",
  failure_message: "Provider did not accept the message before timeout.",
  transition_history: [],
  correlation_id: "corr-delivery",
  sent_at: null,
  delivered_at: null,
  created_at: "2026-07-24T00:00:00Z",
  updated_at: "2026-07-24T00:05:00Z",
};

const deliveryAttempt: NotificationDeliveryAttempt = {
  id: "attempt-1",
  attempt_number: 2,
  adapter_key: "smtp",
  outcome: "timeout",
  provider_message_id: "",
  error_code: "smtp_timeout",
  latency_ms: 30_000,
  started_at: "2026-07-24T00:01:00Z",
  completed_at: "2026-07-24T00:01:30Z",
  correlation_id: "corr-attempt",
};

const endpoint: NotificationEndpoint = {
  id: "endpoint-1",
  user_id: "user-1",
  kind: "webhook",
  device_type: "",
  address_display: "https://hooks.example.com/***",
  display_name: "Finance webhook",
  secret_ref: "vault://notifications/webhook", // pragma: allowlist secret
  is_active: true,
  health: "degraded",
  last_verified_at: "2026-07-23T00:00:00Z",
  last_used_at: null,
  created_by: "operator-1",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
};

const channelConfiguration = {
  enabled: true,
  adapter_key: "smtp",
  credential_ref: "secret://smtp",
  sender_ref: "noreply@saraise.com",
  timeout_seconds: 30,
  retry: { max_attempts: 3, base_seconds: 2, maximum_seconds: 120 },
  circuit: { failure_threshold: 5, reset_seconds: 60 },
  rate_limit_per_minute: 120,
};

const configurationDocument: NotificationConfigurationDocument = {
  schema_version: 2,
  channels: {
    in_app: { ...channelConfiguration, adapter_key: "in-app" },
    email: channelConfiguration,
    sms: { ...channelConfiguration, adapter_key: "twilio" },
    push: { ...channelConfiguration, adapter_key: "web-push" },
    webhook: { ...channelConfiguration, adapter_key: "signed-webhook" },
  },
  preferences: { default_enabled: true, mandatory_categories: ["security"] },
  batch_size: 100,
  max_attempts: 3,
  backoff: { base_seconds: 2, maximum_seconds: 120 },
  retention: { delivery_days: 90, inbox_days: 30 },
  limits: { context_bytes: 32_768, metadata_bytes: 8_192 },
  allowed_action_url_hosts: ["app.saraise.com"],
  allowed_webhook_hosts: ["hooks.saraise.com"],
  feature_flags: { digest: { enabled: true, tenant_ids: [], roles: [], cohorts: [] } },
  digest_schedules: { hourly_minute: 15, daily_time: "09:00", weekly_day: 1 },
  quiet_hours: { start: "22:00", end: "07:00", timezone: "UTC" },
  provider_callbacks: { timestamp_tolerance_seconds: 300 },
};

const configuration: NotificationConfiguration = {
  id: "configuration-1",
  environment: "development",
  active_version: 4,
  document: configurationDocument,
  checksum: "checksum-4",
  created_by: "operator-1",
  updated_by: "operator-1",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
};

const historyItem: ConfigurationHistoryItem = {
  version: {
    version: 3,
    document: configurationDocument,
    checksum: "checksum-3",
    created_by: "operator-1",
    correlation_id: "corr-history",
    change_summary: "Previous provider limits",
    created_at: "2026-07-23T00:00:00Z",
  },
  audit: {
    id: "audit-3",
    version: 3,
    actor_id: "operator-1",
    correlation_id: "corr-history",
    action: "update",
    before_checksum: "checksum-2",
    after_checksum: "checksum-3",
    changed_paths: ["channels.email.timeout_seconds"],
    created_at: "2026-07-23T00:00:00Z",
  },
};

function paginated<T>(items: readonly T[], capabilities: readonly string[] = []): PaginatedData<T> {
  return { items, pagination, meta: pageMeta, capabilities };
}

function renderRoute(route: string, element: React.ReactElement, path = route) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const inboxApi = vi.mocked(notificationService.inbox);
const templateApi = vi.mocked(notificationService.templates);
const deliveryApi = vi.mocked(notificationService.deliveries);
const endpointApi = vi.mocked(notificationService.endpoints);
const healthApi = vi.mocked(notificationService.health);
const configurationApi = vi.mocked(notificationService.configuration);

describe("notification page coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000002");
    inboxApi.list.mockResolvedValue(paginated([notification], ["notifications.inbox:update"]));
    inboxApi.unreadCount.mockResolvedValue({ count: 3 });
    inboxApi.get.mockResolvedValue(notification);
    inboxApi.markAllRead.mockResolvedValue({ affected_count: 3 });
    inboxApi.markRead.mockResolvedValue({
      ...notification,
      status: "read",
      read_at: "2026-07-24T01:00:00Z",
    });
    inboxApi.markUnread.mockResolvedValue(notification);
    inboxApi.archive.mockResolvedValue({ ...notification, status: "archived" });
    templateApi.list.mockResolvedValue(
      paginated([template], ["notifications.template:create", "notifications.template:archive"])
    );
    templateApi.get.mockResolvedValue(template);
    templateApi.create.mockResolvedValue({ ...template, id: "template-copy" });
    templateApi.archive.mockResolvedValue({ ...template, status: "archived" });
    templateApi.versions.mockResolvedValue(paginated([versionOne, versionTwo]));
    templateApi.preview.mockResolvedValue({
      subject: "Receipt",
      body: "Paid 42 to SARAISE",
      content_type: "text/plain",
      diagnostics: [],
    });
    templateApi.activate.mockResolvedValue(template);
    templateApi.rollback.mockResolvedValue({ ...template, active_version: versionOne });
    deliveryApi.list.mockResolvedValue(paginated([delivery], ["notifications.delivery:dispatch"]));
    deliveryApi.get.mockResolvedValue(delivery);
    deliveryApi.attempts.mockResolvedValue(paginated([deliveryAttempt]));
    deliveryApi.retry.mockResolvedValue({ ...delivery, status: "queued" });
    deliveryApi.cancel.mockResolvedValue({ ...delivery, status: "cancelled" });
    endpointApi.list.mockResolvedValue(
      paginated(
        [endpoint],
        [
          "notifications.endpoint:create",
          "notifications.endpoint:verify",
          "notifications.endpoint:delete",
        ]
      )
    );
    endpointApi.verify.mockResolvedValue({
      verified: true,
      health: "healthy",
      verified_at: "2026-07-24T01:00:00Z",
      endpoint: { ...endpoint, health: "healthy" },
    });
    endpointApi.register.mockResolvedValue({ ...endpoint, display_name: "Finance webhook" });
    endpointApi.get.mockResolvedValue(endpoint);
    endpointApi.update.mockResolvedValue({ ...endpoint, display_name: "Finance endpoint 2026" });
    endpointApi.revoke.mockResolvedValue({ ...endpoint, is_active: false, health: "revoked" });
    healthApi.live.mockResolvedValue({ module: "notifications", status: "live", live: true });
    healthApi.ready.mockResolvedValue({
      module: "notifications",
      status: "ready",
      ready: true,
      code: "notifications_ready",
      components: {
        outbox: {
          status: "ready",
          code: "outbox_ready",
          details: { pending: 2, oldest_age_seconds: 45 },
        },
        adapters: { status: "ready", code: "adapters_ready", details: { active: "email" } },
      },
    });
    configurationApi.get.mockResolvedValue(configuration);
    configurationApi.history.mockResolvedValue(paginated([historyItem]));
    configurationApi.rollback.mockResolvedValue({
      ...configuration,
      active_version: 5,
      updated_at: "2026-07-24T02:00:00Z",
    });
  });

  it("persists inbox filters and marks all unread notifications with a transition key", async () => {
    const user = userEvent.setup();
    renderRoute("/notifications", <NotificationCenterPage />);

    expect(await screen.findByRole("heading", { name: "Notification inbox" })).toBeInTheDocument();
    expect(screen.getByText("3 unread across your full inbox")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search title or message"), {
      target: { value: "invoice" },
    });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Status" }), "unread");
    fireEvent.change(await screen.findByLabelText("Category"), { target: { value: "billing" } });

    await waitFor(() =>
      expect(inboxApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({
          search: "invoice",
          status: "unread",
          category: "billing",
        }),
        expect.any(AbortSignal)
      )
    );
    expect(JSON.parse(sessionStorage.getItem("notifications.inbox.filters") ?? "{}")).toEqual(
      expect.objectContaining({ search: "invoice", status: "unread", category: "billing" })
    );

    await user.click(screen.getByRole("button", { name: "Mark all read" }));
    await waitFor(() => expect(inboxApi.markAllRead).toHaveBeenCalled());
    expect(inboxApi.markAllRead).toHaveBeenCalledWith({
      transition_key: "mark-all-read:00000000-0000-4000-8000-000000000002",
    });
  });

  it("hides unsafe notification links and sends governed inbox transitions", async () => {
    const user = userEvent.setup();
    renderRoute("/notifications/:id", <NotificationDetailPage />, "/notifications/notification-1");

    expect(
      await screen.findByRole("heading", { name: "Invoice approval required" })
    ).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(
      "The related link was hidden because it is not a safe internal destination."
    );
    expect(screen.queryByRole("link", { name: /open related record/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Mark read" }));
    await waitFor(() => expect(inboxApi.markRead).toHaveBeenCalled());
    expect(inboxApi.markRead).toHaveBeenCalledWith("notification-1", {
      transition_key: "read:00000000-0000-4000-8000-000000000002",
    });
  });

  it("filters templates, clones from the latest immutable version, and archives with evidence", async () => {
    const user = userEvent.setup();
    vi.spyOn(Date, "now").mockReturnValue(1_800_000_000_000);
    renderRoute("/notifications/templates", <TemplateListPage />);

    expect(
      await screen.findByRole("heading", { name: "Notification templates" })
    ).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Search code or name"), {
      target: { value: "receipt" },
    });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Template status" }),
      "active"
    );
    await waitFor(() =>
      expect(templateApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "receipt", status: "active" }),
        expect.any(AbortSignal)
      )
    );

    await user.click(screen.getByRole("button", { name: "Clone" }));
    await waitFor(() => expect(templateApi.create).toHaveBeenCalled());
    const clonePayload = templateApi.create.mock.calls.at(-1)?.[0];
    expect(clonePayload).toEqual(
      expect.objectContaining({
        code: "billing.receipt.copy.1800000000000",
        body_template: versionTwo.body_template,
        variables_schema: versionTwo.variables_schema,
      })
    );

    await user.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(templateApi.archive).toHaveBeenCalled());
    expect(templateApi.archive).toHaveBeenCalledWith("template-1", {
      transition_key: "archive:00000000-0000-4000-8000-000000000002",
    });
  });

  it("renders template previews and sends activate plus rollback version payloads", async () => {
    const user = userEvent.setup();
    renderRoute(
      "/notifications/templates/:id",
      <TemplateDetailPage />,
      "/notifications/templates/template-1"
    );

    expect(await screen.findByRole("heading", { name: "Billing receipt" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Example context"), {
      target: { value: '{"amount":42,"vendor":"SARAISE"}' },
    });
    await user.click(screen.getByRole("button", { name: "Render preview" }));
    expect(await screen.findByText("Paid 42 to SARAISE")).toBeInTheDocument();
    expect(templateApi.preview).toHaveBeenCalledWith("template-1", {
      context: { amount: 42, vendor: "SARAISE" },
    });

    await user.click(screen.getAllByRole("button", { name: "Activate" })[0]!);
    await waitFor(() => expect(templateApi.activate).toHaveBeenCalled());
    expect(templateApi.activate).toHaveBeenCalledWith("template-1", {
      version: 1,
      transition_key: "activate:00000000-0000-4000-8000-000000000002",
    } satisfies TemplateTransitionInput);

    await user.click(screen.getByRole("button", { name: "Rollback" }));
    await waitFor(() => expect(templateApi.rollback).toHaveBeenCalled());
    expect(templateApi.rollback).toHaveBeenCalledWith("template-1", {
      version: 1,
      transition_key: "rollback:00000000-0000-4000-8000-000000000002",
    } satisfies TemplateRollbackInput);
  });

  it("filters durable deliveries and exposes dispatch only when the backend grants it", async () => {
    const user = userEvent.setup();
    renderRoute("/notifications/deliveries", <DeliveryListPage />);

    expect(
      await screen.findByRole("heading", { name: "Notification deliveries" })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dispatch notification" })).toHaveAttribute(
      "href",
      "/notifications/deliveries/new"
    );
    fireEvent.change(screen.getByPlaceholderText("Search recipient or failure code"), {
      target: { value: "smtp" },
    });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Delivery status" }),
      "failed"
    );
    await user.selectOptions(await screen.findByRole("combobox", { name: "Channel" }), "email");

    await waitFor(() =>
      expect(deliveryApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "smtp", status: "failed", channel: "email" }),
        expect.any(AbortSignal)
      )
    );
    expect(screen.getByText("smtp_timeout")).toBeInTheDocument();
  });

  it("retries and cancels failed deliveries with idempotency and transition payloads", async () => {
    const user = userEvent.setup();
    renderRoute(
      "/notifications/deliveries/:id",
      <DeliveryDetailPage />,
      "/notifications/deliveries/delivery-1"
    );

    expect(await screen.findByRole("heading", { name: "Delivery evidence" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("smtp timeout");
    expect(
      screen.getByText("Provider did not accept the message before timeout.")
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(deliveryApi.retry).toHaveBeenCalled());
    expect(deliveryApi.retry).toHaveBeenCalledWith("delivery-1", {
      idempotency_key: "retry:delivery-1:00000000-0000-4000-8000-000000000002",
    } satisfies DeliveryRetryInput);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(deliveryApi.cancel).toHaveBeenCalled());
    expect(deliveryApi.cancel).toHaveBeenCalledWith("delivery-1", {
      transition_key: "cancel:00000000-0000-4000-8000-000000000002",
    } satisfies DeliveryCancelInput);
  });

  it("filters endpoints and protects verify/revoke actions behind backend capabilities", async () => {
    const user = userEvent.setup();
    renderRoute("/notifications/endpoints", <EndpointListPage />);

    expect(
      await screen.findByRole("heading", { name: "Notification endpoints" })
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "Endpoint kind" }), "webhook");
    await user.selectOptions(screen.getByRole("combobox", { name: "Endpoint activity" }), "true");
    await waitFor(() =>
      expect(endpointApi.list).toHaveBeenLastCalledWith(
        { page: 1, page_size: 25, kind: "webhook", active: true } satisfies EndpointQuery,
        expect.any(AbortSignal)
      )
    );

    await user.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(endpointApi.verify).toHaveBeenCalledWith("endpoint-1"));
    await user.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(endpointApi.revoke).toHaveBeenCalledWith("endpoint-1"));
  });

  it("validates endpoint registration and submits only approved secret references", async () => {
    const user = userEvent.setup();
    renderRoute("/notifications/endpoints/new", <CreateEndpointPage />);

    expect(
      await screen.findByRole("heading", { name: "Register notification endpoint" })
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("A display name is required.");
    await user.type(screen.getByLabelText("Display name"), "Finance webhook");
    await user.selectOptions(screen.getByLabelText("Kind"), "webhook");
    const webhookUrl = screen.getByRole("textbox", { name: /webhook https url/i });
    await user.type(webhookUrl, "http://hooks.example.com");
    expect(screen.getByRole("status")).toHaveTextContent("Webhooks require HTTPS.");
    await user.clear(webhookUrl);
    await user.type(webhookUrl, "https://hooks.example.com/notify");
    await user.type(screen.getByLabelText("Signing secret reference"), "plain-secret");
    expect(screen.getByRole("status")).toHaveTextContent("approved vault");
    await user.clear(screen.getByLabelText("Signing secret reference"));
    await user.type(
      screen.getByLabelText("Signing secret reference"),
      "vault://notifications/webhook"
    );
    await user.click(screen.getByRole("button", { name: "Register endpoint" }));

    await waitFor(() =>
      expect(endpointApi.register).toHaveBeenCalledWith({
        kind: "webhook",
        device_type: "",
        address: "https://hooks.example.com/notify",
        display_name: "Finance webhook",
        secret_ref: "vault://notifications/webhook", // pragma: allowlist secret
      })
    );
  });

  it("edits endpoints, verifies active destinations, and disables verification when inactive", async () => {
    const user = userEvent.setup();
    renderRoute(
      "/notifications/endpoints/:id/edit",
      <EditEndpointPage />,
      "/notifications/endpoints/endpoint-1/edit"
    );

    expect(await screen.findByRole("heading", { name: "Finance webhook" })).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Display name"));
    await user.type(screen.getByLabelText("Display name"), "Finance endpoint 2026");
    const secretReference = screen.getByRole("textbox", { name: /signing secret reference/i });
    await user.clear(secretReference);
    await user.type(secretReference, "vault://notifications/webhook-2026");
    await user.click(screen.getByRole("button", { name: "Save endpoint" }));
    await waitFor(() =>
      expect(endpointApi.update).toHaveBeenCalledWith("endpoint-1", {
        display_name: "Finance endpoint 2026",
        secret_ref: "vault://notifications/webhook-2026", // pragma: allowlist secret
        is_active: true,
      })
    );
    await user.click(screen.getByRole("button", { name: "Verify now" }));
    await waitFor(() => expect(endpointApi.verify).toHaveBeenCalledWith("endpoint-1"));

    await user.click(screen.getByLabelText(/endpoint enabled/i));
    expect(screen.getByRole("button", { name: "Verify now" })).toBeDisabled();
  });

  it("renders notification readiness evidence and fail-closed retry", async () => {
    const user = userEvent.setup();
    healthApi.ready
      .mockRejectedValueOnce(new Error("readiness unavailable"))
      .mockResolvedValueOnce({
        module: "notifications",
        status: "ready",
        ready: true,
        code: "notifications_ready",
        components: {
          outbox: {
            status: "ready",
            code: "outbox_ready",
            details: { pending: 2, oldest_age_seconds: 45 },
          },
        },
      });
    renderRoute("/notifications/health", <NotificationHealthPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load notification health"
    );
    await user.click(screen.getByRole("button", { name: /retry/iu }));
    expect(await screen.findByRole("heading", { name: "Notification health" })).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("45 seconds")).toBeInTheDocument();
    expect(screen.getByText("outbox_ready")).toBeInTheDocument();
  });

  it("rolls configuration history forward with expected active version and audit summary", async () => {
    const user = userEvent.setup();
    renderRoute("/notifications/configuration/history", <ConfigurationHistoryPage />);

    expect(
      await screen.findByRole("heading", { name: "Configuration history" })
    ).toBeInTheDocument();
    expect(screen.getByText("Previous provider limits")).toBeInTheDocument();
    expect(screen.getByText("channels.email.timeout_seconds")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Environment"), "production");
    await waitFor(() =>
      expect(configurationApi.history).toHaveBeenLastCalledWith(
        "production",
        { page: 1, page_size: 25 },
        expect.any(AbortSignal)
      )
    );

    await user.click(screen.getByRole("button", { name: "Rollback" }));
    await waitFor(() => expect(configurationApi.rollback).toHaveBeenCalled());
    expect(configurationApi.rollback).toHaveBeenCalledWith("production", {
      target_version: 3,
      expected_version: 4,
      change_summary: "Rollback to version 3",
    });
  });
});
