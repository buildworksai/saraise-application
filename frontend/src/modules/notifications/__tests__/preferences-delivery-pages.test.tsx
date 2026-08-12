/* eslint-disable max-lines-per-function -- focused page tests keep complete governed fixtures beside workflow assertions. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  DeliveryPreviewResult,
  NotificationDelivery,
  NotificationTemplate,
  PaginatedData,
  PaginationMeta,
  PreferenceMatrix,
  PreferenceReplaceInput,
} from "../contracts";
import { notificationService } from "../services/notification-service";
import { CreateDeliveryPage } from "../pages/CreateDeliveryPage";
import { NotificationPreferencesPage } from "../pages/NotificationPreferencesPage";

vi.mock("../services/notification-service", () => ({
  NOTIFICATION_QUERY_KEYS: {
    preferences: ["notifications", "preferences"],
    templates: (query = {}) => ["notifications", "templates", query],
  },
  notificationService: {
    preferences: { get: vi.fn(), replace: vi.fn(), reset: vi.fn() },
    templates: { list: vi.fn() },
    deliveries: { create: vi.fn(), preview: vi.fn() },
  },
}));

const pagination: PaginationMeta = {
  count: 1,
  page: 1,
  page_size: 100,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};

const preferences: PreferenceMatrix = {
  categories: ["security", "billing"],
  channels: ["email"],
  preferences: [
    {
      id: "pref-1",
      channel: "email",
      category: "security",
      enabled: true,
      digest_mode: "immediate",
      quiet_hours_start: null,
      quiet_hours_end: null,
      timezone: "UTC",
      mandatory: true,
      source: "mandatory_policy",
      updated_at: "2026-07-23T00:00:00Z",
    },
    {
      id: "pref-2",
      channel: "email",
      category: "billing",
      enabled: true,
      digest_mode: "daily",
      quiet_hours_start: "21:00",
      quiet_hours_end: "07:00",
      timezone: "UTC",
      mandatory: false,
      source: "override",
      updated_at: "2026-07-23T00:00:00Z",
    },
  ],
};

const template: NotificationTemplate = {
  id: "template-1",
  code: "invoice_due",
  name: "Invoice due",
  category: "billing",
  channel: "email",
  locale: "en-US",
  status: "active",
  active_version: null,
  latest_version: null,
  transition_history: [],
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-07-23T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
};

const templatesPage: PaginatedData<NotificationTemplate> = {
  items: [template],
  pagination,
  meta: { correlation_id: "corr-templates", timestamp: "2026-07-23T00:00:00Z" },
  capabilities: [],
};

const preview: DeliveryPreviewResult = {
  subject: "Invoice due",
  body: "Invoice body",
  content_type: "text/plain",
  recipient_display: "a***@example.com",
  effective_channel: "email",
  preference_decision: "allowed",
  diagnostics: [{ level: "info", message: "Preference permits delivery." }],
};

const delivery: NotificationDelivery = {
  id: "delivery-1",
  template_version_id: "version-1",
  job_id: "job-1",
  idempotency_key: "dispatch:00000000-0000-4000-8000-000000000001",
  recipient_type: "email",
  recipient_user_id: null,
  recipient_display: "a***@example.com",
  channel: "email",
  category: "billing",
  priority: 5,
  status: "queued",
  scheduled_at: null,
  next_attempt_at: null,
  attempt_count: 0,
  max_attempts: 3,
  provider_message_id: "",
  failure_code: "",
  failure_message: "",
  transition_history: [],
  correlation_id: "corr-delivery",
  sent_at: null,
  delivered_at: null,
  created_at: "2026-07-23T00:00:00Z",
  updated_at: "2026-07-23T00:00:00Z",
};

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="path">{location.pathname}</span>;
}

function renderWithClient(element: React.ReactElement, path = "/notifications") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/notifications"
            element={
              <>
                {element}
                <LocationProbe />
              </>
            }
          />
          <Route path="/notifications/deliveries/:id" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Notification preference and delivery pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000001");
    vi.mocked(notificationService.preferences.get).mockResolvedValue(preferences);
    vi.mocked(notificationService.preferences.replace).mockResolvedValue(preferences);
    vi.mocked(notificationService.preferences.reset).mockResolvedValue({
      ...preferences,
      preferences: preferences.preferences.map((item) => ({ ...item, timezone: "Etc/UTC" })),
    });
    vi.mocked(notificationService.templates.list).mockResolvedValue(templatesPage);
    vi.mocked(notificationService.deliveries.preview).mockResolvedValue(preview);
    vi.mocked(notificationService.deliveries.create).mockResolvedValue(delivery);
  });

  it("saves editable preferences, keeps mandatory security locked, and resets from server defaults", async () => {
    const user = userEvent.setup();
    renderWithClient(<NotificationPreferencesPage />);

    expect(
      await screen.findByRole("heading", { name: "Notification preferences" })
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Enable security email")).toBeDisabled();

    await user.click(screen.getByLabelText("Enable billing email"));
    await user.selectOptions(screen.getByLabelText("Digest for billing email"), "weekly");
    fireEvent.change(screen.getAllByLabelText("Quiet start")[1]!, { target: { value: "" } });
    await user.clear(screen.getAllByLabelText("Timezone")[1]!);
    await user.type(screen.getAllByLabelText("Timezone")[1]!, "America/New_York");
    await user.click(screen.getByRole("button", { name: "Save preferences" }));

    await waitFor(() => expect(notificationService.preferences.replace).toHaveBeenCalled());
    const replaceCall = vi.mocked(notificationService.preferences.replace).mock.calls.at(-1) as
      | [PreferenceReplaceInput]
      | undefined;
    expect(replaceCall?.[0].preferences).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          category: "billing",
          enabled: false,
          digest_mode: "weekly",
          quiet_hours_start: null,
          timezone: "America/New_York",
        }),
      ])
    );

    await user.click(screen.getByRole("button", { name: "Reset to defaults" }));
    await waitFor(() => expect(notificationService.preferences.reset).toHaveBeenCalled());
    expect(screen.getAllByLabelText("Timezone")[1]).toHaveValue("Etc/UTC");
  }, 15_000);

  it("renders a retryable preference load failure without fabricating preference rows", async () => {
    const user = userEvent.setup();
    vi.mocked(notificationService.preferences.get)
      .mockRejectedValueOnce(new Error("preferences unavailable"))
      .mockResolvedValueOnce(preferences);

    renderWithClient(<NotificationPreferencesPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load preferences");
    expect(screen.queryByText("security")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("security")).toBeInTheDocument();
  });

  it("requires a server preview before dispatch and submits an idempotent email payload", async () => {
    const user = userEvent.setup();
    renderWithClient(<CreateDeliveryPage />);

    expect(
      await screen.findByRole("heading", { name: "Dispatch notification" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Queue delivery" })).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("Active template"), "template-1");
    await user.selectOptions(screen.getByLabelText("Recipient type"), "email");
    await user.type(screen.getByLabelText("Destination"), "ap@example.com");
    await user.clear(screen.getByLabelText("Priority (1–10)"));
    await user.type(screen.getByLabelText("Priority (1–10)"), "1");
    fireEvent.change(screen.getByLabelText("Template context"), {
      target: { value: '{"amount":42}' },
    });
    await user.click(screen.getByRole("button", { name: "Dry-run preview" }));

    await waitFor(() => expect(notificationService.deliveries.preview).toHaveBeenCalled());
    expect(notificationService.deliveries.preview).toHaveBeenCalledWith(
      expect.objectContaining({
        template_id: "template-1",
        recipient: { type: "email", address: "ap@example.com" },
        context: { amount: 42 },
        priority: 1,
        idempotency_key: "dispatch:00000000-0000-4000-8000-000000000001",
      })
    );
    expect(await screen.findByText("Masked recipient: a***@example.com")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Queue delivery" }));
    await waitFor(() => expect(notificationService.deliveries.create).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("path")).toHaveTextContent("/notifications/deliveries/delivery-1")
    );
  });

  it("clears stale preview when recipient type changes and blocks malformed JSON dispatch", async () => {
    const user = userEvent.setup();
    renderWithClient(<CreateDeliveryPage />);

    await user.selectOptions(await screen.findByLabelText("Active template"), "template-1");
    await user.type(screen.getByLabelText("User UUID"), "user-1");
    await user.click(screen.getByRole("button", { name: "Dry-run preview" }));
    expect(await screen.findByText("Masked recipient: a***@example.com")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Recipient type"), "push_endpoint");
    expect(screen.getByLabelText("Endpoint UUID")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Queue delivery" })).toBeDisabled();

    await user.type(screen.getByLabelText("Endpoint UUID"), "endpoint-1");
    fireEvent.change(screen.getByLabelText("Template context"), { target: { value: "{" } });
    await user.click(screen.getByRole("button", { name: "Dry-run preview" }));
    expect(notificationService.deliveries.preview).toHaveBeenCalledTimes(1);
  });
});
