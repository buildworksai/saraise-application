/* eslint-disable max-lines-per-function -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import type { EmailMarketingConfigurationDocument } from "../contracts";
import { CampaignForm } from "../components/CampaignForm";
import { GovernedError, PreflightPanel } from "../components/EmailMarketingUI";
import { emailMarketingService } from "../services/email-marketing-service";
import { EmailCampaignListPage } from "./EmailCampaignListPage";
import { EmailTemplateListPage } from "./EmailTemplateListPage";
import { AudienceDeliveryListPage } from "./AudienceDeliveryListPage";
import { SuppressionListPage } from "./SuppressionListPage";
import { ConsentListPage } from "./ConsentListPage";
import { EmailCampaignDetailPage } from "./EmailCampaignDetailPage";
import { EmailMarketingConfigurationPage } from "./EmailMarketingConfigurationPage";
import { EmailTemplateDetailPage } from "./EmailTemplateDetailPage";
import { CreateSuppressionPage } from "./CreateSuppressionPage";
import { RecordConsentPage } from "./RecordConsentPage";
import { ConsentDetailPage } from "./ConsentDetailPage";
import { CreateEmailTemplatePage } from "./CreateEmailTemplatePage";
import { EditEmailTemplatePage } from "./EditEmailTemplatePage";
import { EmailRecipientDetailPage } from "./EmailRecipientDetailPage";
import { SuppressionDetailPage } from "./SuppressionDetailPage";
import { EmailDeliveryDetailPage } from "./EmailDeliveryDetailPage";

vi.mock("../services/email-marketing-service", () => {
  const fn = () => vi.fn();
  return {
    EMAIL_MARKETING_QUERY_KEYS: {
      all: ["email-marketing"],
      campaigns: (f = {}) => ["email-marketing", "campaigns", f],
      campaign: (id: string) => ["email-marketing", "campaign", id],
      analytics: (id: string) => ["email-marketing", "analytics", id],
      templates: (f = {}) => ["email-marketing", "templates", f],
      template: (id: string) => ["email-marketing", "template", id],
      recipients: (f = {}) => ["email-marketing", "recipients", f],
      recipient: (id: string) => ["email-marketing", "recipient", id],
      deliveries: (f = {}) => ["email-marketing", "deliveries", f],
      delivery: (id: string) => ["email-marketing", "delivery", id],
      suppressions: (f = {}) => ["email-marketing", "suppressions", f],
      suppression: (id: string) => ["email-marketing", "suppression", id],
      consents: (f = {}) => ["email-marketing", "consents", f],
      consent: (id: string) => ["email-marketing", "consent", id],
      configuration: ["email-marketing", "configuration"],
      configurationHistory: ["email-marketing", "configuration", "history"],
      health: ["email-marketing", "health"],
    },
    emailMarketingService: {
      campaigns: {
        list: fn(),
        get: fn(),
        create: fn(),
        update: fn(),
        delete: fn(),
        resolveAudience: fn(),
        schedule: fn(),
        unschedule: fn(),
        send: fn(),
        pause: fn(),
        resume: fn(),
        cancel: fn(),
        analytics: fn(),
      },
      templates: {
        list: fn(),
        get: fn(),
        create: fn(),
        update: fn(),
        delete: fn(),
        activate: fn(),
        archive: fn(),
        clone: fn(),
        preview: fn(),
      },
      recipients: { list: fn(), get: fn(), retry: fn() },
      deliveries: { list: fn(), get: fn() },
      suppressions: { list: fn(), get: fn(), create: fn(), deactivate: fn() },
      consents: { list: fn(), get: fn(), create: fn(), revoke: fn() },
      configuration: {
        current: fn(),
        update: fn(),
        preview: fn(),
        history: fn(),
        rollback: fn(),
        importDocument: fn(),
        exportDocument: fn(),
      },
      health: fn(),
    },
  };
});

const pagination = {
  count: 0,
  page: 1,
  page_size: 25,
  total_pages: 0,
  has_next: false,
  has_previous: false,
};
const empty = {
  items: [],
  pagination,
  correlationId: "corr-list",
  timestamp: "2026-07-22T00:00:00Z",
};
const configurationDocument: EmailMarketingConfigurationDocument = {
  schema_version: 1,
  defaults: {
    template_category: "general",
    campaign_type: "broadcast",
    audience_resolver: "manual",
    delivery_gateway: "django",
    timezone: "UTC",
    audience_schema_version: 1,
    consent_purpose: "marketing",
  },
  limits: {
    json_max_depth: 8,
    json_max_keys: 128,
    evidence_json_max_bytes: 16384,
    evidence_json_max_depth: 6,
    evidence_json_max_keys: 96,
    template_design_max_bytes: 131072,
    audience_definition_max_bytes: 32768,
    consent_evidence_max_bytes: 32768,
    personalization_max_bytes: 65536,
    serializer_json_max_bytes: 32768,
    serializer_json_max_depth: 8,
    serializer_json_max_keys: 100,
    json_key_max_length: 128,
    personalization_max_keys: 100,
    recipient_count_max: 100000,
    max_recipients: 100000,
    recipient_key_max_length: 255,
    display_name_max_length: 255,
    subject_max_length: 500,
    preview_text_max_length: 255,
    search_max_length: 100,
  },
  pagination: { default_page_size: 25, max_page_size: 100, page_size_options: [25, 50, 100] },
  workflows: {
    campaign_types: ["broadcast"],
    audience_resolver_keys: ["manual", "inline"],
    audience_schema_versions: [1],
    campaign_editable_states: ["draft"],
    campaign_archivable_states: ["draft", "failed"],
    campaign_physical_delete_protected_states: ["sent", "cancelled"],
    campaign_archive_blocking_recipient_states: ["queued", "sending", "accepted"],
    template_editable_states: ["draft"],
    recipient_initial_states: ["resolved", "suppressed"],
    terminal_recipient_states: ["delivered", "bounced", "complained", "unsubscribed"],
    preflight_blocking_codes: ["CONTENT_INVALID", "SENDER_INVALID"],
    provider_acknowledgement_mapping: {
      accepted: "accepted",
      delivered: "delivered",
      failed: "failed",
      bounced: "bounced",
    },
    provider_event_recipient_mapping: {
      accepted: "accepted",
      delivered: "delivered",
      bounced: "bounced",
      complained: "complained",
      unsubscribed: "unsubscribed",
    },
    provider_event_command_mapping: {
      accepted: "accepted",
      delivered: "delivered",
      bounced: "bounce",
      complained: "complain",
      unsubscribed: "unsubscribe",
    },
    transitions: {
      campaign: ["schedule:draft:scheduled"],
      template: ["activate:draft:active"],
      recipient: ["queue:resolved:queued"],
    },
  },
  compliance: {
    suppression_scopes: ["marketing", "all"],
    suppression_reasons: ["unsubscribe", "hard_bounce", "complaint", "manual", "legal"],
    suppression_sources: ["user", "provider_event", "administrator", "migration"],
    permanent_suppression_reasons: ["unsubscribe", "complaint", "legal"],
    protected_overwrite_reasons: ["hard_bounce", "complaint"],
    automatic_suppression_events: ["bounced", "complained", "unsubscribed"],
    automatic_suppression_reasons: {
      bounced: "hard_bounce",
      complained: "complaint",
      unsubscribed: "unsubscribe",
    },
    consent_sources: ["form", "import", "api", "crm_event", "administrator", "unsubscribe"],
    consent_lawful_bases: ["consent", "legitimate_interest", "contractual"],
    consent_required_status: "granted",
    suppression_scopes_by_purpose: { marketing: ["all", "marketing"], default: ["all"] },
  },
  resilience: {
    delivery_timeout_seconds: 10,
    circuit_failure_threshold: 3,
    circuit_reset_seconds: 60,
    retry_max_attempts: 3,
    retry_base_delay_seconds: 0.25,
    retry_max_delay_seconds: 4,
    retry_jitter_seconds: 0.25,
    webhook_replay_window_seconds: 300,
  },
  tokens: { preflight_receipt_seconds: 900, tracking_token_days: 90, unsubscribe_token_days: 365 },
  integrations: {
    allowed_delivery_backends: ["django.core.mail.backends.smtp.EmailBackend"],
    simulated_delivery_backends: ["django.core.mail.backends.locmem.EmailBackend"],
    gateway_keys: ["django"],
  },
  filters: {
    default_ordering_by_resource: {
      campaigns: "-created_at",
      templates: "-updated_at",
      recipients: "-created_at",
      deliveries: "-created_at",
      suppressions: "-suppressed_at",
      consents: "-captured_at",
    },
    search_fields_by_resource: {
      campaigns: ["campaign_code"],
      templates: ["template_code"],
      recipients: ["email"],
      deliveries: ["error_code"],
      suppressions: ["email"],
      consents: ["email"],
    },
  },
  health: { outbox_freshness_seconds: 300, probe_staleness_seconds: 30 },
  rate_limits: { public_per_minute: 30 },
  quotas: {
    api_reads: 100000,
    api_writes: 10000,
    audience_resolutions: 1000,
    monthly_recipients: 10000,
  },
  feature_flags: { enabled: true, roles: [], cohorts: [], rollout_percentage: 100 },
  display: {
    status_semantics: {
      delivered: "success",
      accepted: "success",
      active: "success",
      failed: "error",
      bounced: "error",
      cancelled: "error",
      paused: "warning",
      draft: "neutral",
    },
  },
};
function renderPage(element: React.ReactElement, path = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}
function renderRoutedPage(element: React.ReactElement, path: string, route: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
          <Route path="*" element={<div>navigated</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("email marketing page families", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(emailMarketingService.configuration.current).mockResolvedValue({
      data: {
        id: "config-id",
        environment: "development",
        version: 1,
        document: configurationDocument,
        updated_at: "2026-07-22T00:00:00Z",
        updated_by: null,
      },
      correlationId: "corr-config",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.campaigns.list).mockResolvedValue(empty);
    vi.mocked(emailMarketingService.templates.list).mockResolvedValue(empty);
    vi.mocked(emailMarketingService.recipients.list).mockResolvedValue(empty);
    vi.mocked(emailMarketingService.deliveries.list).mockResolvedValue(empty);
    vi.mocked(emailMarketingService.suppressions.list).mockResolvedValue(empty);
    vi.mocked(emailMarketingService.consents.list).mockResolvedValue(empty);
    vi.mocked(emailMarketingService.configuration.history).mockResolvedValue({
      data: [
        {
          id: "version-1",
          version: 1,
          previous_version: null,
          change_type: "materialized",
          actor_id: null,
          correlation_id: "corr-version-1",
          previous_document: null,
          document: configurationDocument,
          created_at: "2026-07-21T00:00:00Z",
          rollback_source_version: null,
        },
      ],
      correlationId: "corr-history",
      timestamp: "2026-07-22T00:00:00Z",
    });
  });
  it("renders an accessible skeleton then the campaign first-use empty state", async () => {
    renderPage(<EmailCampaignListPage />);
    expect(screen.getByLabelText("Loading campaign configuration")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    expect(await screen.findByText("No campaigns yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /create campaign/iu })).toHaveLength(2);
  });
  it("keeps URL filters distinct from first-use empty", async () => {
    renderPage(<EmailCampaignListPage />, "/email-marketing/campaigns?search=missing");
    expect(await screen.findByText("No campaigns match these filters")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByLabelText("Search campaigns")).toHaveValue("");
  });
  it("applies campaign filters, pagination, and row navigation through governed query params", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.campaigns.list).mockResolvedValue({
      items: [
        {
          id: "campaign-1",
          campaign_code: "WELCOME",
          campaign_name: "Welcome campaign",
          campaign_type: "broadcast",
          subject: "Hello",
          status: "scheduled",
          template_id: "template-1",
          scheduled_at: "2026-08-10T10:00:00Z",
          timezone: "UTC",
          resolved_recipient_count: 250,
          sent_count: 10,
          delivered_count: 8,
          opened_count: 3,
          clicked_count: 1,
          bounced_count: 1,
          failed_count: 1,
          created_at: "2026-07-22T00:00:00Z",
          updated_at: "2026-07-22T00:00:00Z",
        },
      ],
      pagination: {
        ...pagination,
        count: 26,
        total_pages: 2,
        has_next: true,
      },
      correlationId: "corr-campaign-filtered",
      timestamp: "2026-07-22T00:00:00Z",
    });

    renderRoutedPage(
      <EmailCampaignListPage />,
      "/email-marketing/campaigns?search=welcome&status=scheduled&campaign_type=broadcast&page=2&page_size=50&ordering=status",
      "/email-marketing/campaigns"
    );

    expect(await screen.findByText("Welcome campaign")).toBeInTheDocument();
    expect(emailMarketingService.campaigns.list).toHaveBeenLastCalledWith({
      search: "welcome",
      status: "scheduled",
      campaign_type: "broadcast",
      ordering: "status",
      page: 2,
      page_size: 50,
    });

    fireEvent.change(screen.getByLabelText("Search campaigns"), {
      target: { value: "renewal" },
    });
    await waitFor(() =>
      expect(emailMarketingService.campaigns.list).toHaveBeenLastCalledWith(
        expect.objectContaining({
          search: "renewal",
          page: 1,
        })
      )
    );

    await user.click(screen.getByRole("link", { name: "Welcome campaign" }));
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });
  it("renders template, delivery, suppression, and consent empty states without fabricated rows", async () => {
    const cases = [
      [<EmailTemplateListPage />, "No templates yet"],
      [<AudienceDeliveryListPage />, "No recipients yet"],
      [<SuppressionListPage />, "No suppressions yet"],
      [<ConsentListPage />, "No consent records yet"],
    ] as const;
    for (const [page, text] of cases) {
      const rendered = renderPage(page);
      expect(await screen.findByText(text)).toBeInTheDocument();
      rendered.unmount();
    }
  });
  it("applies audience delivery filters to recipient and gateway delivery queries", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.recipients.list).mockResolvedValue({
      items: [
        {
          id: "recipient-1",
          campaign_id: "campaign-1",
          recipient_key: "buyer-1",
          email: "buyer@example.com",
          display_name: "Buyer Example",
          status: "failed",
          suppression_reason: "",
          created_at: "2026-07-22T00:00:00Z",
        },
      ],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-recipients",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.deliveries.list).mockResolvedValue({
      items: [
        {
          id: "attempt-1",
          recipient_id: "recipient-1",
          attempt_number: 2,
          status: "failed",
          error_code: "SMTP_TIMEOUT",
          started_at: null,
          accepted_at: null,
          created_at: "2026-07-22T00:00:00Z",
          completed_at: "2026-07-22T00:01:00Z",
        },
      ],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-deliveries",
      timestamp: "2026-07-22T00:00:00Z",
    });

    renderPage(
      <AudienceDeliveryListPage />,
      "/email-marketing/delivery?campaign_id=campaign-1&status=failed&email=buyer@example.com"
    );

    expect(await screen.findByText("Buyer Example")).toBeInTheDocument();
    expect(emailMarketingService.recipients.list).toHaveBeenLastCalledWith({
      campaign_id: "campaign-1",
      status: "failed",
      email: "buyer@example.com",
      ordering: "-created_at",
      page: 1,
      page_size: 25,
    });

    await user.click(screen.getByRole("tab", { name: "Delivery attempts" }));
    await user.selectOptions(await screen.findByLabelText("Filter gateway"), "django");
    await waitFor(() =>
      expect(emailMarketingService.deliveries.list).toHaveBeenLastCalledWith({
        campaign_id: undefined,
        status: undefined,
        gateway_key: "django",
        ordering: "-created_at",
        page: 1,
        page_size: 25,
      })
    );
    expect(await screen.findByText("SMTP_TIMEOUT")).toBeInTheDocument();
  });

  it("renders delivery evidence, redacts provider identifiers, and navigates to the recipient", async () => {
    vi.mocked(emailMarketingService.deliveries.get).mockResolvedValue({
      data: {
        id: "attempt-1",
        recipient_id: "recipient-1",
        attempt_number: 3,
        status: "delivered",
        error_code: "",
        started_at: "2026-07-22T00:00:00Z",
        accepted_at: "2026-07-22T00:00:05Z",
        completed_at: "2026-07-22T00:01:00Z",
        created_at: "2026-07-22T00:00:00Z",
        updated_at: "2026-07-22T00:01:00Z",
        events: [
          {
            id: "event-1",
            recipient_id: "recipient-1",
            attempt_id: "attempt-1",
            gateway_key: "django",
            provider_event_id: "provider-secret-1",
            event_type: "delivered",
            occurred_at: "2026-07-22T00:01:00Z",
            link_url_hash: "",
            bounce_class: "",
            metadata: { provider_message_id: "hidden-message" },
            correlation_id: "corr-delivered",
            created_at: "2026-07-22T00:01:00Z",
          },
        ],
      },
      correlationId: "corr-delivery-detail",
      timestamp: "2026-07-22T00:01:00Z",
    });

    renderRoutedPage(
      <EmailDeliveryDetailPage />,
      "/email-marketing/delivery/attempts/attempt-1",
      "/email-marketing/delivery/attempts/:id"
    );

    expect(await screen.findByRole("heading", { name: "Delivery attempt 3" })).toBeInTheDocument();
    expect(screen.getByText("correlation corr-delivered")).toBeInTheDocument();
    expect(screen.queryByText("provider-secret-1")).not.toBeInTheDocument();
    expect(screen.queryByText("hidden-message")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("link", { name: "recipient-1" }));
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });

  it("fails closed when delivery detail evidence cannot be loaded", async () => {
    vi.mocked(emailMarketingService.deliveries.get).mockRejectedValue(
      new ApiError("Delivery evidence unavailable", 503, undefined, "SMTP_DOWN", "corr-smtp-down")
    );

    renderRoutedPage(
      <EmailDeliveryDetailPage />,
      "/email-marketing/delivery/attempts/attempt-1",
      "/email-marketing/delivery/attempts/:id"
    );

    expect(await screen.findByText("Delivery dependency unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-smtp-down/iu)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "recipient-1" })).not.toBeInTheDocument();
  });

  it("applies suppression filters from URL and controls, then navigates from governed rows", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.suppressions.list).mockResolvedValue({
      items: [
        {
          id: "suppression-1",
          email: "blocked@example.com",
          scope: "marketing",
          reason: "manual",
          source: "administrator",
          active: true,
          suppressed_at: "2026-07-22T00:00:00Z",
          expires_at: null,
        },
      ],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-suppressions",
      timestamp: "2026-07-22T00:00:00Z",
    });

    renderRoutedPage(
      <SuppressionListPage />,
      "/email-marketing/suppressions?email=blocked@example.com&active=true&scope=marketing&reason=manual&page_size=50&ordering=email",
      "/email-marketing/suppressions"
    );

    expect(await screen.findByText("blocked@example.com")).toBeInTheDocument();
    expect(emailMarketingService.suppressions.list).toHaveBeenLastCalledWith({
      email: "blocked@example.com",
      active: true,
      scope: "marketing",
      reason: "manual",
      ordering: "email",
      page: 1,
      page_size: 50,
    });

    await user.selectOptions(screen.getByLabelText("Filter suppression active"), "false");
    await waitFor(() =>
      expect(emailMarketingService.suppressions.list).toHaveBeenLastCalledWith(
        expect.objectContaining({
          active: false,
          page: 1,
        })
      )
    );

    await user.click(screen.getByRole("link", { name: "blocked@example.com" }));
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });

  it("applies consent filters from URL and controls, then navigates from governed rows", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.consents.list).mockResolvedValue({
      items: [
        {
          id: "consent-1",
          email: "buyer@example.com",
          purpose: "marketing",
          status: "granted",
          lawful_basis: "consent",
          source: "form",
          notice_version: "notice-v1",
          captured_at: "2026-07-22T00:00:00Z",
          created_at: "2026-07-22T00:00:00Z",
        },
      ],
      pagination: { ...pagination, count: 1, total_pages: 1 },
      correlationId: "corr-consents",
      timestamp: "2026-07-22T00:00:00Z",
    });

    renderRoutedPage(
      <ConsentListPage />,
      "/email-marketing/consents?email=buyer@example.com&status=granted&purpose=marketing&source=form&page_size=50&ordering=email",
      "/email-marketing/consents"
    );

    expect(await screen.findByText("buyer@example.com")).toBeInTheDocument();
    expect(emailMarketingService.consents.list).toHaveBeenLastCalledWith({
      email: "buyer@example.com",
      status: "granted",
      purpose: "marketing",
      source: "form",
      ordering: "email",
      page: 1,
      page_size: 50,
    });

    await user.selectOptions(screen.getByLabelText("Filter consent status"), "revoked");
    await waitFor(() =>
      expect(emailMarketingService.consents.list).toHaveBeenLastCalledWith(
        expect.objectContaining({
          status: "revoked",
          page: 1,
        })
      )
    );

    await user.click(screen.getByRole("link", { name: "buyer@example.com" }));
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });

  it("validates template form JSON, creates uppercase codes, and blocks immutable template edits", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.templates.create).mockResolvedValue({
      data: {
        id: "template-new",
        template_code: "WELCOME",
        template_name: "Welcome",
        category: "general",
        subject: "Hello",
        status: "draft",
        version: 1,
        usage_count: 0,
        updated_at: "2026-07-22T00:00:00Z",
        created_at: "2026-07-22T00:00:00Z",
        created_by: null,
        updated_by: null,
        description: "",
        preview_text: "",
        body_html: "<p>Hello</p>",
        body_text: "",
        design_json: { version: 1 },
        last_used_at: null,
        is_active: false,
        is_deleted: false,
      },
      correlationId: "corr-template-create",
      timestamp: "2026-07-22T00:00:00Z",
    });

    const created = renderRoutedPage(
      <CreateEmailTemplatePage />,
      "/email-marketing/templates/new",
      "/email-marketing/templates/new"
    );
    await user.type(await screen.findByLabelText("Template code"), "welcome");
    await user.type(screen.getByLabelText("Template name"), "Welcome");
    await user.type(screen.getByLabelText("Template subject"), "Hello");
    await user.type(screen.getByLabelText("HTML body"), "<p>Hello</p>");
    await user.clear(screen.getByLabelText("Design JSON"));
    fireEvent.change(screen.getByLabelText("Design JSON"), { target: { value: "{" } });
    await user.click(screen.getByRole("button", { name: "Create template" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Design JSON is invalid.");
    expect(emailMarketingService.templates.create).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Design JSON"), {
      target: { value: JSON.stringify({ version: 1, blocks: [] }) },
    });
    await user.click(screen.getByRole("button", { name: "Create template" }));
    await waitFor(() =>
      expect(emailMarketingService.templates.create).toHaveBeenCalledWith(
        expect.objectContaining({
          template_code: "WELCOME",
          template_name: "Welcome",
          subject: "Hello",
          design_json: { version: 1, blocks: [] },
        })
      )
    );
    created.unmount();

    vi.mocked(emailMarketingService.templates.get).mockResolvedValue({
      data: {
        id: "template-active",
        template_code: "ACTIVE",
        template_name: "Active template",
        category: "general",
        subject: "Active",
        status: "active",
        version: 2,
        usage_count: 3,
        updated_at: "2026-07-22T00:00:00Z",
        created_at: "2026-07-22T00:00:00Z",
        created_by: null,
        updated_by: null,
        description: "",
        preview_text: "",
        body_html: "<p>Active</p>",
        body_text: "",
        design_json: { version: 1 },
        last_used_at: null,
        is_active: true,
        is_deleted: false,
      },
      correlationId: "corr-active-template",
      timestamp: "2026-07-22T00:00:00Z",
    });
    renderRoutedPage(
      <EditEmailTemplatePage />,
      "/email-marketing/templates/template-active/edit",
      "/email-marketing/templates/:id/edit"
    );
    expect(
      await screen.findByRole("heading", { name: "Template is immutable" })
    ).toBeInTheDocument();
    expect(emailMarketingService.templates.update).not.toHaveBeenCalled();
  });
  it("retains campaign form values after validation and prevents invalid submit", async () => {
    const submit = vi.fn();
    renderPage(<CampaignForm pending={false} serverError={null} onSubmit={submit} />);
    await userEvent.type(await screen.findByLabelText("Campaign code"), "WELCOME");
    await userEvent.type(screen.getByLabelText("Campaign name"), "Welcome");
    await userEvent.type(screen.getByLabelText("Subject"), "Hello");
    await userEvent.type(screen.getByLabelText("From name"), "SARAISE");
    await userEvent.type(screen.getByLabelText("From email"), "sender@example.com");
    await userEvent.clear(screen.getByLabelText("Audience definition"));
    await userEvent.type(screen.getByLabelText("Audience definition"), "not-json");
    await userEvent.click(screen.getByRole("button", { name: "Create draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Audience definition must be valid JSON."
    );
    expect(screen.getByLabelText("Campaign code")).toHaveValue("WELCOME");
    expect(submit).not.toHaveBeenCalled();
  });
  it("explains the exact preflight send consequence", () => {
    renderPage(
      <PreflightPanel
        campaignStatus="draft"
        value={{
          content_valid: true,
          receipt: "preflight-receipt",
          rendered: true,
          resolved_count: 10,
          eligible_count: 8,
          suppressed_count: 2,
          consent_failure_count: 1,
          suppression_failure_count: 1,
          sender_healthy: true,
          sender_detail: "Verified sender",
          quota_required: 8,
          quota_remaining: 100,
          scheduled_at: null,
          timezone: "UTC",
          blocking_reasons: ["Resolve consent failures"],
        }}
      />
    );
    expect(screen.getByText(/8 eligible · 2 suppressed/iu)).toBeInTheDocument();
    expect(screen.getByText(/durably queues eligible recipients/iu)).toBeInTheDocument();
    expect(screen.getByText("Resolve consent failures")).toBeInTheDocument();
  });
  it("distinguishes permission, conflict, quota, and dependency failures with correlation evidence", () => {
    const errors = [
      [403, "Access or entitlement denied"],
      [409, "State conflict"],
      [429, "Quota or rate limit reached"],
      [503, "Delivery dependency unavailable"],
    ] as const;
    for (const [status, title] of errors) {
      const rendered = renderPage(
        <GovernedError error={new ApiError("failed", status, undefined, "DENIED", "corr-test")} />
      );
      expect(screen.getByText(title)).toBeInTheDocument();
      expect(screen.getByText(/corr-test/iu)).toBeInTheDocument();
      rendered.unmount();
    }
  });

  it("previews, applies, exports, and rolls back tenant configuration from real controls", async () => {
    const createObjectURL = vi.fn(() => "blob:email-config");
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(emailMarketingService.configuration.current).mockResolvedValue({
      data: {
        id: "config-id",
        environment: "development",
        version: 2,
        document: configurationDocument,
        updated_at: "2026-07-22T00:00:00Z",
        updated_by: null,
      },
      correlationId: "corr-config",
      timestamp: "2026-07-22T00:00:00Z",
    });
    const normalized = {
      ...configurationDocument,
      defaults: { ...configurationDocument.defaults, template_category: "promotional" },
    };
    vi.mocked(emailMarketingService.configuration.preview).mockResolvedValue({
      data: {
        valid: true,
        normalized_document: normalized,
        changes: [{ path: "defaults.template_category", before: "general", after: "promotional" }],
        warnings: ["Gateway policy will be revalidated server-side."],
      },
      correlationId: "corr-preview",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.configuration.update).mockResolvedValue({
      data: {
        id: "config-id",
        environment: "development",
        version: 2,
        document: normalized,
        updated_at: "2026-07-22T00:00:00Z",
        updated_by: null,
      },
      correlationId: "corr-update",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.configuration.rollback).mockResolvedValue({
      data: {
        id: "config-id",
        environment: "development",
        version: 3,
        document: configurationDocument,
        updated_at: "2026-07-22T00:00:00Z",
        updated_by: null,
      },
      correlationId: "corr-rollback",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.configuration.exportDocument).mockResolvedValue({
      data: {
        id: "config-id",
        environment: "development",
        version: 1,
        document: configurationDocument,
        updated_at: "2026-07-22T00:00:00Z",
        updated_by: null,
      },
      correlationId: "corr-export",
      timestamp: "2026-07-22T00:00:00Z",
    });

    renderPage(<EmailMarketingConfigurationPage />);
    await userEvent.clear(await screen.findByLabelText(/Template category/iu));
    await userEvent.type(screen.getByLabelText(/Template category/iu), "promotional");
    await userEvent.click(screen.getByRole("button", { name: "Preview server diff" }));
    expect(await screen.findByText("Server preview")).toBeInTheDocument();
    expect(screen.getByText("defaults.template_category")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Apply reviewed configuration" }));
    expect(emailMarketingService.configuration.update).toHaveBeenCalledWith({
      document: normalized,
      expected_version: 2,
    });

    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    expect(createObjectURL).toHaveBeenCalled();
    await userEvent.click(await screen.findByRole("button", { name: "Rollback to v1" }));
    expect(emailMarketingService.configuration.rollback).toHaveBeenCalledWith({
      target_version: 1,
      expected_version: 2,
    });
  });

  it("rejects malformed imports and imports reviewed configuration only after preview", async () => {
    const user = userEvent.setup();
    const imported = {
      ...configurationDocument,
      defaults: { ...configurationDocument.defaults, timezone: "Asia/Kolkata" },
    };
    vi.mocked(emailMarketingService.configuration.preview).mockResolvedValue({
      data: {
        valid: true,
        normalized_document: imported,
        changes: [{ path: "defaults.timezone", before: "UTC", after: "Asia/Kolkata" }],
        warnings: [],
      },
      correlationId: "corr-preview-import",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.configuration.importDocument).mockResolvedValue({
      data: {
        id: "config-id",
        environment: "development",
        version: 2,
        document: imported,
        updated_at: "2026-07-22T00:00:00Z",
        updated_by: null,
      },
      correlationId: "corr-import",
      timestamp: "2026-07-22T00:00:00Z",
    });

    const rendered = renderPage(<EmailMarketingConfigurationPage />);
    await screen.findByRole("heading", { name: "Email marketing configuration" });
    const input = rendered.container.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement))
      throw new Error("Configuration import input missing.");

    await user.upload(
      input,
      new File([JSON.stringify({ incomplete: true })], "invalid.json", {
        type: "application/json",
      })
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "complete email marketing configuration"
    );

    await user.upload(
      input,
      new File([JSON.stringify(imported)], "email-marketing-config.json", {
        type: "application/json",
      })
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Imported document staged");

    await user.click(screen.getByRole("button", { name: "Preview server diff" }));
    expect(await screen.findByText("defaults.timezone")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Import reviewed document" }));

    await waitFor(() =>
      expect(emailMarketingService.configuration.importDocument).toHaveBeenCalledWith({
        document: imported,
        expected_version: 1,
      })
    );
  });

  it("does not stage or mutate malformed configuration imports", async () => {
    const user = userEvent.setup();
    const rendered = renderPage(<EmailMarketingConfigurationPage />);
    await screen.findByRole("heading", { name: "Email marketing configuration" });
    const input = rendered.container.querySelector('input[type="file"]');
    if (!(input instanceof HTMLInputElement))
      throw new Error("Configuration import input missing.");

    await user.upload(
      input,
      new File([JSON.stringify({ defaults: configurationDocument.defaults })], "partial.json", {
        type: "application/json",
      })
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "complete email marketing configuration"
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply reviewed configuration" })).toBeDisabled();
    expect(emailMarketingService.configuration.preview).not.toHaveBeenCalled();
    expect(emailMarketingService.configuration.importDocument).not.toHaveBeenCalled();
    expect(emailMarketingService.configuration.update).not.toHaveBeenCalled();
  });

  it("fails closed when configuration loading fails and leaves mutation endpoints idle", async () => {
    vi.mocked(emailMarketingService.configuration.current).mockRejectedValue(
      new ApiError("Configuration unavailable", 503, undefined, "CONFIG_DOWN", "corr-config-down")
    );

    renderPage(<EmailMarketingConfigurationPage />);

    expect(await screen.findByText("Delivery dependency unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-config-down/iu)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview server diff" })).not.toBeInTheDocument();
    expect(emailMarketingService.configuration.preview).not.toHaveBeenCalled();
    expect(emailMarketingService.configuration.update).not.toHaveBeenCalled();
    expect(emailMarketingService.configuration.importDocument).not.toHaveBeenCalled();
  });

  it("keeps reviewed apply disabled after a rejected server preview", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.configuration.preview).mockRejectedValue(
      new ApiError(
        "Rollout policy rejected",
        409,
        undefined,
        "ROLLOUT_REJECTED",
        "corr-preview-denied"
      )
    );

    renderPage(<EmailMarketingConfigurationPage />);
    await screen.findByRole("heading", { name: "Email marketing configuration" });
    fireEvent.change(screen.getByLabelText(/Rollout percentage/iu), {
      target: { value: "101" },
    });
    await user.click(screen.getByRole("button", { name: "Preview server diff" }));

    expect(await screen.findByText("State conflict")).toBeInTheDocument();
    expect(screen.getByText(/corr-preview-denied/iu)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply reviewed configuration" })).toBeDisabled();
    expect(emailMarketingService.configuration.update).not.toHaveBeenCalled();
  });

  it("previews the complete edited runtime policy instead of relying on hard-coded defaults", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.configuration.preview).mockImplementation((input) =>
      Promise.resolve({
        data: {
          valid: true,
          normalized_document: input.document,
          changes: [
            {
              path: "runtime-policy",
              before: configurationDocument.defaults,
              after: input.document.defaults,
            },
          ],
          warnings: [],
        },
        correlationId: "corr-preview-runtime-policy",
        timestamp: "2026-07-22T00:00:00Z",
      })
    );

    renderPage(<EmailMarketingConfigurationPage />);
    await screen.findByRole("heading", { name: "Email marketing configuration" });

    const setLabeledValue = (label: RegExp, value: string, index = 0) => {
      const control = screen.getAllByLabelText(label)[index];
      if (!control) throw new Error(`Missing control for ${String(label)}`);
      fireEvent.change(control, { target: { value } });
    };

    setLabeledValue(/Configuration schema version/iu, "2");
    setLabeledValue(/Delivery gateway/iu, "ses");
    setLabeledValue(/Default page size/iu, "50");
    setLabeledValue(/Page-size options/iu, "25, 50");
    setLabeledValue(/json max depth/iu, "9");
    setLabeledValue(/Campaign types/iu, "broadcast, lifecycle");
    setLabeledValue(/Audience schema versions/iu, "1, 2");
    fireEvent.change(screen.getByLabelText(/Provider event command mapping/iu), {
      target: {
        value: JSON.stringify({
          accepted: "accepted",
          delivered: "delivered",
          bounced: "bounce",
          unsubscribed: "unsubscribe",
          deferred: "retry",
        }),
      },
    });
    fireEvent.change(screen.getByLabelText(/Transition graphs/iu), {
      target: {
        value: JSON.stringify({
          campaign: ["schedule:draft:scheduled", "pause:scheduled:paused"],
          template: ["activate:draft:active"],
          recipient: ["queue:resolved:queued"],
        }),
      },
    });
    setLabeledValue(/Suppression sources/iu, "user, administrator");
    fireEvent.change(screen.getByLabelText(/Scopes by consent purpose/iu), {
      target: { value: JSON.stringify({ marketing: ["marketing"], transactional: ["all"] }) },
    });
    setLabeledValue(/retry jitter seconds/iu, "0.5");
    setLabeledValue(/preflight receipt seconds/iu, "1200");
    setLabeledValue(/outbox freshness seconds/iu, "600");
    setLabeledValue(/public per minute/iu, "60");
    setLabeledValue(/monthly recipients/iu, "20000");
    setLabeledValue(/Gateway keys/iu, "django, ses");
    fireEvent.change(screen.getByLabelText(/Default ordering by resource/iu), {
      target: {
        value: JSON.stringify({
          ...configurationDocument.filters.default_ordering_by_resource,
          campaigns: "campaign_code",
        }),
      },
    });
    fireEvent.change(screen.getByLabelText(/Search fields by resource/iu), {
      target: {
        value: JSON.stringify({
          ...configurationDocument.filters.search_fields_by_resource,
          campaigns: ["campaign_code", "subject"],
        }),
      },
    });
    await user.click(screen.getByLabelText(/Module capability enabled/iu));
    setLabeledValue(/Rollout percentage/iu, "45");
    setLabeledValue(/Allowed roles/iu, "email-admin, compliance-reviewer");
    setLabeledValue(/Cohorts/iu, "beta-erp");
    fireEvent.change(screen.getByLabelText(/Status semantics/iu), {
      target: {
        value: JSON.stringify({
          ...configurationDocument.display.status_semantics,
          deferred: "warning",
        }),
      },
    });

    await user.click(screen.getByRole("button", { name: "Preview server diff" }));
    await waitFor(() => expect(emailMarketingService.configuration.preview).toHaveBeenCalled());
    const previewed = vi.mocked(emailMarketingService.configuration.preview).mock.calls[0]?.[0]
      .document;
    expect(previewed).toMatchObject({
      schema_version: 2,
      defaults: { delivery_gateway: "ses" },
      pagination: { default_page_size: 50, page_size_options: [25, 50] },
      limits: { json_max_depth: 9 },
      resilience: { retry_jitter_seconds: 0.5 },
      tokens: { preflight_receipt_seconds: 1200 },
      health: { outbox_freshness_seconds: 600 },
      rate_limits: { public_per_minute: 60 },
      quotas: { monthly_recipients: 20000 },
      integrations: { gateway_keys: ["django", "ses"] },
      feature_flags: {
        enabled: false,
        rollout_percentage: 45,
        roles: ["email-admin", "compliance-reviewer"],
        cohorts: ["beta-erp"],
      },
    });
    expect(previewed?.workflows.campaign_types).toEqual(["broadcast", "lifecycle"]);
    expect(previewed?.workflows.audience_schema_versions).toEqual([1, 2]);
    expect(previewed?.workflows.provider_event_command_mapping.deferred).toBe("retry");
    expect(previewed?.workflows.transitions.campaign).toContain("pause:scheduled:paused");
    expect(previewed?.compliance.suppression_sources).toEqual(["user", "administrator"]);
    expect(previewed?.compliance.suppression_scopes_by_purpose.transactional).toEqual(["all"]);
    expect(previewed?.filters.default_ordering_by_resource.campaigns).toBe("campaign_code");
    expect(previewed?.filters.search_fields_by_resource.campaigns).toEqual([
      "campaign_code",
      "subject",
    ]);
    expect(previewed?.display.status_semantics.deferred).toBe("warning");
  });

  it("renders no-change previews and empty immutable history without rollback actions", async () => {
    vi.mocked(emailMarketingService.configuration.history).mockResolvedValue({
      data: [],
      correlationId: "corr-history-empty",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.configuration.preview).mockImplementation((input) =>
      Promise.resolve({
        data: {
          valid: true,
          normalized_document: input.document,
          changes: [],
          warnings: [],
        },
        correlationId: "corr-preview-noop",
        timestamp: "2026-07-22T00:00:00Z",
      })
    );

    renderPage(<EmailMarketingConfigurationPage />);

    await screen.findByRole("heading", { name: "Email marketing configuration" });
    fireEvent.change(screen.getByLabelText(/Template category/iu), {
      target: { value: "promotional" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Preview server diff" }));

    expect(await screen.findByText("No effective changes.")).toBeInTheDocument();
    expect(screen.getByText("No immutable version records were returned.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Rollback to v/iu })).not.toBeInTheDocument();
  });

  it("previews edits for the remaining workflow and compliance allow-list controls", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.configuration.preview).mockImplementation((input) =>
      Promise.resolve({
        data: {
          valid: true,
          normalized_document: input.document,
          changes: [{ path: "remaining-policy", before: {}, after: input.document.workflows }],
          warnings: [],
        },
        correlationId: "corr-preview-remaining-policy",
        timestamp: "2026-07-22T00:00:00Z",
      })
    );

    renderPage(<EmailMarketingConfigurationPage />);
    await screen.findByRole("heading", { name: "Email marketing configuration" });

    const setLabeledValue = (label: RegExp | string, value: string) => {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    };

    fireEvent.change(screen.getAllByLabelText(/Audience schema version/iu)[0]!, {
      target: { value: "2" },
    });
    setLabeledValue(/Audience resolvers/iu, "manual, segment");
    setLabeledValue(/Editable campaign states/iu, "draft, paused");
    setLabeledValue(/Editable template states/iu, "draft, active");
    setLabeledValue(/Archivable campaign states/iu, "failed, cancelled");
    setLabeledValue(/Physical-delete protected campaign states/iu, "sent, cancelled, archived");
    setLabeledValue(/Archive-blocking recipient states/iu, "queued, sending, accepted, deferred");
    setLabeledValue(/Initial recipient states/iu, "resolved, suppressed, queued");
    setLabeledValue(/Terminal recipient states/iu, "delivered, bounced, complained");
    setLabeledValue(
      /Preflight blocking codes/iu,
      "CONTENT_INVALID, SENDER_INVALID, QUOTA_EXCEEDED"
    );
    fireEvent.change(screen.getByLabelText(/Provider acknowledgement mapping/iu), {
      target: {
        value: JSON.stringify({ accepted: "accepted", failed: "failed", deferred: "queued" }),
      },
    });
    fireEvent.change(screen.getByLabelText(/Provider event mapping/iu), {
      target: {
        value: JSON.stringify({
          accepted: "accepted",
          delivered: "delivered",
          deferred: "queued",
        }),
      },
    });
    fireEvent.change(screen.getAllByLabelText(/Suppression scopes/iu)[0]!, {
      target: { value: "marketing, transactional, all" },
    });
    fireEvent.change(screen.getAllByLabelText(/Suppression reasons/iu)[0]!, {
      target: { value: "unsubscribe, hard_bounce, legal" },
    });
    setLabeledValue(/Permanent reasons/iu, "unsubscribe, legal");
    setLabeledValue(/Protected overwrite reasons/iu, "complaint, legal");
    setLabeledValue(/Automatic suppression events/iu, "bounced, complained");
    fireEvent.change(screen.getByLabelText(/Automatic suppression reasons/iu), {
      target: { value: JSON.stringify({ bounced: "hard_bounce", complained: "complaint" }) },
    });
    setLabeledValue(/Consent sources/iu, "form, api");
    setLabeledValue(/Consent lawful bases/iu, "consent, contractual");
    setLabeledValue(/Required consent status/iu, "verified");
    setLabeledValue(/Allowed delivery backends/iu, "smtp.EmailBackend, ses.EmailBackend");
    setLabeledValue(/Simulated delivery backends/iu, "locmem.EmailBackend");

    await user.click(screen.getByRole("button", { name: "Preview server diff" }));
    await waitFor(() => expect(emailMarketingService.configuration.preview).toHaveBeenCalled());
    const previewed = vi.mocked(emailMarketingService.configuration.preview).mock.calls[0]?.[0]
      .document;

    expect(previewed).toMatchObject({
      defaults: { audience_schema_version: 2 },
      workflows: {
        audience_resolver_keys: ["manual", "segment"],
        campaign_editable_states: ["draft", "paused"],
        template_editable_states: ["draft", "active"],
        campaign_archivable_states: ["failed", "cancelled"],
        campaign_physical_delete_protected_states: ["sent", "cancelled", "archived"],
        campaign_archive_blocking_recipient_states: ["queued", "sending", "accepted", "deferred"],
        recipient_initial_states: ["resolved", "suppressed", "queued"],
        terminal_recipient_states: ["delivered", "bounced", "complained"],
        preflight_blocking_codes: ["CONTENT_INVALID", "SENDER_INVALID", "QUOTA_EXCEEDED"],
        provider_acknowledgement_mapping: {
          accepted: "accepted",
          failed: "failed",
          deferred: "queued",
        },
        provider_event_recipient_mapping: {
          accepted: "accepted",
          delivered: "delivered",
          deferred: "queued",
        },
      },
      compliance: {
        suppression_scopes: ["marketing", "transactional", "all"],
        suppression_reasons: ["unsubscribe", "hard_bounce", "legal"],
        permanent_suppression_reasons: ["unsubscribe", "legal"],
        protected_overwrite_reasons: ["complaint", "legal"],
        automatic_suppression_events: ["bounced", "complained"],
        automatic_suppression_reasons: { bounced: "hard_bounce", complained: "complaint" },
        consent_sources: ["form", "api"],
        consent_lawful_bases: ["consent", "contractual"],
        consent_required_status: "verified",
      },
      integrations: {
        allowed_delivery_backends: ["smtp.EmailBackend", "ses.EmailBackend"],
        simulated_delivery_backends: ["locmem.EmailBackend"],
      },
    });
  });

  it("blocks preview until JSON object configuration fields are valid", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.configuration.current).mockResolvedValue({
      data: {
        id: "config-id",
        environment: "development",
        version: 2,
        document: configurationDocument,
        updated_at: "2026-07-22T00:00:00Z",
        updated_by: null,
      },
      correlationId: "corr-config-v2",
      timestamp: "2026-07-22T00:00:00Z",
    });
    renderPage(<EmailMarketingConfigurationPage />);
    await screen.findByRole("heading", { name: "Email marketing configuration" });

    fireEvent.change(screen.getByLabelText(/Provider acknowledgement mapping/iu), {
      target: { value: "[" },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter valid JSON");

    fireEvent.change(screen.getByLabelText(/Provider acknowledgement mapping/iu), {
      target: { value: "[]" },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a JSON object.");

    await user.click(screen.getByRole("button", { name: "Preview server diff" }));
    expect(emailMarketingService.configuration.preview).not.toHaveBeenCalled();
  });

  it("surfaces save, export, rollback, and history failures without mutating the wrong endpoint", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    vi.mocked(emailMarketingService.configuration.preview).mockImplementation((input) =>
      Promise.resolve({
        data: {
          valid: true,
          normalized_document: input.document,
          changes: [
            { path: "defaults.template_category", before: "general", after: "operational" },
          ],
          warnings: [],
        },
        correlationId: "corr-preview-save-failure",
        timestamp: "2026-07-22T00:00:00Z",
      })
    );
    vi.mocked(emailMarketingService.configuration.update).mockRejectedValue(
      new ApiError("Configuration conflict", 409, undefined, "CONFIG_CONFLICT", "corr-save-failed")
    );
    vi.mocked(emailMarketingService.configuration.exportDocument).mockRejectedValue(
      new ApiError("Export unavailable", 503, undefined, "EXPORT_DOWN", "corr-export-failed")
    );
    vi.mocked(emailMarketingService.configuration.rollback).mockRejectedValue(
      new ApiError("Rollback denied", 403, undefined, "ROLLBACK_DENIED", "corr-rollback-failed")
    );

    const saveFailure = renderPage(<EmailMarketingConfigurationPage />);
    await user.clear(await screen.findByLabelText(/Template category/iu));
    await user.type(screen.getByLabelText(/Template category/iu), "operational");
    await user.click(screen.getByRole("button", { name: "Preview server diff" }));
    await user.click(await screen.findByRole("button", { name: "Apply reviewed configuration" }));

    expect(await screen.findByText("State conflict")).toBeInTheDocument();
    expect(screen.getByText(/corr-save-failed/iu)).toBeInTheDocument();
    expect(emailMarketingService.configuration.importDocument).not.toHaveBeenCalled();
    saveFailure.unmount();

    const exportFailure = renderPage(<EmailMarketingConfigurationPage />);
    await screen.findByRole("heading", { name: "Email marketing configuration" });
    await user.click(screen.getByRole("button", { name: "Export" }));
    expect(await screen.findByText("Delivery dependency unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-export-failed/iu)).toBeInTheDocument();
    exportFailure.unmount();

    vi.mocked(emailMarketingService.configuration.current).mockResolvedValue({
      data: {
        id: "config-id",
        environment: "development",
        version: 2,
        document: configurationDocument,
        updated_at: "2026-07-22T00:00:00Z",
        updated_by: null,
      },
      correlationId: "corr-config-v2",
      timestamp: "2026-07-22T00:00:00Z",
    });
    renderPage(<EmailMarketingConfigurationPage />);
    await screen.findByRole("heading", { name: "Email marketing configuration" });
    await user.click(screen.getByRole("button", { name: "Rollback to v1" }));
    expect(emailMarketingService.configuration.rollback).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Rollback to v1" }));
    expect(await screen.findByText("Access or entitlement denied")).toBeInTheDocument();
    expect(screen.getByText(/corr-rollback-failed/iu)).toBeInTheDocument();
  });

  it("renders governed version-history loading and failure states", async () => {
    vi.mocked(emailMarketingService.configuration.history).mockReturnValue(
      new Promise(() => undefined)
    );
    const loading = renderPage(<EmailMarketingConfigurationPage />);
    expect(await screen.findByText("Loading version history…")).toBeInTheDocument();
    loading.unmount();

    vi.mocked(emailMarketingService.configuration.history).mockRejectedValue(
      new ApiError("History unavailable", 503, undefined, "HISTORY_DOWN", "corr-history-down")
    );
    renderPage(<EmailMarketingConfigurationPage />);

    expect(await screen.findByText("Delivery dependency unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-history-down/iu)).toBeInTheDocument();
  });

  it("fails closed when suppression and consent allow-lists are empty", async () => {
    const emptyCompliance = {
      ...configurationDocument,
      compliance: {
        ...configurationDocument.compliance,
        suppression_scopes: [],
        suppression_reasons: [],
        suppression_sources: [],
        consent_sources: [],
        consent_lawful_bases: [],
      },
    };
    vi.mocked(emailMarketingService.configuration.current).mockResolvedValue({
      data: {
        id: "config-id",
        environment: "development",
        version: 1,
        document: emptyCompliance,
        updated_at: "2026-07-22T00:00:00Z",
        updated_by: null,
      },
      correlationId: "corr-config",
      timestamp: "2026-07-22T00:00:00Z",
    });

    const suppression = renderPage(<CreateSuppressionPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Suppression allow-lists are empty");
    expect(emailMarketingService.suppressions.create).not.toHaveBeenCalled();
    suppression.unmount();

    renderPage(<RecordConsentPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Consent allow-lists are empty");
    expect(emailMarketingService.consents.create).not.toHaveBeenCalled();
  });

  it("records suppression evidence with configured scopes, expiry rules, and exact payload", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.suppressions.create).mockResolvedValue({
      data: {
        id: "suppression-id",
        email: "blocked@example.com",
        scope: "marketing",
        reason: "manual",
        source: "administrator",
        active: true,
        notes: "Legal hold lifted on renewal path.",
        evidence_event_id: null,
        suppressed_at: "2026-07-22T00:00:00Z",
        expires_at: "2026-08-10T03:45:00.000Z",
        deactivated_at: null,
        deactivated_by: null,
        created_at: "2026-07-22T00:00:00Z",
        updated_at: "2026-07-22T00:00:00Z",
        created_by: "admin-1",
        updated_by: null,
      },
      correlationId: "corr-suppression-create",
      timestamp: "2026-07-22T00:00:00Z",
    });

    const rendered = renderRoutedPage(
      <CreateSuppressionPage />,
      "/email-marketing/suppressions/new",
      "/email-marketing/suppressions/new"
    );

    await screen.findByRole("button", { name: "Record suppression" });
    const form = rendered.container.querySelector("form");
    if (!form) throw new Error("Suppression form was not rendered.");
    fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a valid email address.");
    expect(emailMarketingService.suppressions.create).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Suppressed email"), "blocked@example.com");
    expect(screen.getByLabelText("Suppression expiry")).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Suppression reason"), "manual");
    expect(screen.getByLabelText("Suppression expiry")).toBeEnabled();
    await user.selectOptions(screen.getByLabelText("Suppression source"), "administrator");
    await user.type(screen.getByLabelText("Suppression expiry"), "2026-08-10T09:15");
    await user.type(
      screen.getByLabelText("Suppression notes"),
      "Legal hold lifted on renewal path."
    );
    await user.click(screen.getByRole("button", { name: "Record suppression" }));

    await waitFor(() => expect(emailMarketingService.suppressions.create).toHaveBeenCalled());
    expect(emailMarketingService.suppressions.create).toHaveBeenCalledWith({
      email: "blocked@example.com",
      scope: "marketing",
      reason: "manual",
      source: "administrator",
      expires_at: new Date("2026-08-10T09:15").toISOString(),
      notes: "Legal hold lifted on renewal path.",
    });
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });

  it("records consent evidence without browser-supplied network audit fields", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.consents.create).mockResolvedValue({
      data: {
        id: "consent-id",
        email: "buyer@example.com",
        purpose: "marketing",
        status: "revoked",
        lawful_basis: "contractual",
        source: "crm_event",
        notice_version: "notice-2026-07",
        captured_at: "2026-07-22T00:00:00Z",
        actor_id: "admin-1",
        supersedes_id: null,
        created_at: "2026-07-22T00:00:00Z",
      },
      correlationId: "corr-consent-create",
      timestamp: "2026-07-22T00:00:00Z",
    });

    const rendered = renderRoutedPage(
      <RecordConsentPage />,
      "/email-marketing/consents/new",
      "/email-marketing/consents/new"
    );

    await screen.findByRole("button", { name: "Append consent event" });
    const form = rendered.container.querySelector("form");
    if (!form) throw new Error("Consent form was not rendered.");
    fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email, purpose, and notice version are required."
    );
    expect(emailMarketingService.consents.create).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Consent email"), "buyer@example.com");
    await user.selectOptions(screen.getByLabelText("Consent status"), "revoked");
    await user.selectOptions(screen.getByLabelText("Lawful basis"), "contractual");
    await user.selectOptions(screen.getByLabelText("Consent source"), "crm_event");
    await user.type(screen.getByLabelText("Notice version"), "notice-2026-07");
    await user.click(screen.getByRole("button", { name: "Append consent event" }));

    await waitFor(() => expect(emailMarketingService.consents.create).toHaveBeenCalled());
    expect(emailMarketingService.consents.create).toHaveBeenCalledWith({
      email: "buyer@example.com",
      purpose: "marketing",
      status: "revoked",
      lawful_basis: "contractual",
      source: "crm_event",
      notice_version: "notice-2026-07",
    });
    expect(await screen.findByText("navigated")).toBeInTheDocument();
  });

  it("revokes consent through the configured source and navigates to the appended evidence", async () => {
    const user = userEvent.setup();
    vi.mocked(emailMarketingService.consents.get).mockResolvedValue({
      data: {
        id: "consent-1",
        email: "buyer@example.com",
        purpose: "marketing",
        status: "granted",
        lawful_basis: "consent",
        source: "form",
        notice_version: "notice-v1",
        captured_at: "2026-07-22T00:00:00Z",
        created_at: "2026-07-22T00:00:00Z",
        actor_id: "operator-1",
        supersedes_id: null,
      },
      correlationId: "corr-consent",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.consents.revoke).mockResolvedValue({
      data: {
        id: "consent-2",
        email: "buyer@example.com",
        purpose: "marketing",
        status: "revoked",
        lawful_basis: "consent",
        source: "unsubscribe",
        notice_version: "notice-v1",
        captured_at: "2026-07-22T00:10:00Z",
        created_at: "2026-07-22T00:10:00Z",
        actor_id: "operator-1",
        supersedes_id: "consent-1",
      },
      correlationId: "corr-revoke",
      timestamp: "2026-07-22T00:10:00Z",
    });

    renderRoutedPage(
      <ConsentDetailPage />,
      "/email-marketing/consents/consent-1",
      "/email-marketing/consents/:id"
    );

    await user.click(await screen.findByRole("button", { name: "Revoke consent" }));
    await user.selectOptions(screen.getByLabelText("Revocation source"), "unsubscribe");
    await user.click(screen.getByRole("button", { name: "Append revocation" }));

    await waitFor(() =>
      expect(emailMarketingService.consents.revoke).toHaveBeenCalledWith({
        email: "buyer@example.com",
        purpose: "marketing",
        source: "unsubscribe",
        notice_version: "notice-v1",
      })
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Revoke marketing consent" })
      ).not.toBeInTheDocument()
    );
  });

  it("shows recipient retry and suppression deactivation guarded by evidence requirements", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "recipient-retry-id") });
    vi.mocked(emailMarketingService.recipients.get).mockResolvedValue({
      data: {
        id: "recipient-1",
        campaign_id: "campaign-1",
        recipient_key: "buyer-1",
        email: "buyer@example.com",
        display_name: "Buyer Example",
        status: "failed",
        suppression_reason: "",
        created_at: "2026-07-22T00:00:00Z",
        personalization_data: { first_name: "Buyer" },
        consent_record_id: "consent-1",
        resolved_at: "2026-07-22T00:00:00Z",
        queued_at: null,
        accepted_at: null,
        delivered_at: null,
        failed_at: "2026-07-22T00:01:00Z",
        last_error_code: "SMTP_TIMEOUT",
        transition_history: [],
        delivery_attempts: [],
        events: [],
      },
      correlationId: "corr-recipient",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.recipients.retry).mockResolvedValue({
      data: {
        id: "job-1",
        job_type: "retry",
        status: "queued",
        idempotency_key: "retry",
        created_at: "2026-07-22T00:00:00Z",
        correlation_id: "corr-retry",
      },
      correlationId: "corr-retry",
      timestamp: "2026-07-22T00:00:00Z",
    });

    const recipient = renderRoutedPage(
      <EmailRecipientDetailPage />,
      "/email-marketing/recipients/recipient-1",
      "/email-marketing/recipients/:id"
    );
    await user.click(await screen.findByRole("button", { name: "Retry recipient" }));
    await user.click(screen.getByRole("button", { name: "Confirm retry recipient" }));
    expect(emailMarketingService.recipients.retry).toHaveBeenCalledWith("recipient-1", {
      idempotency_key: "retry-recipient-retry-id",
    });
    recipient.unmount();

    vi.mocked(emailMarketingService.suppressions.get).mockResolvedValue({
      data: {
        id: "suppression-1",
        email: "blocked@example.com",
        scope: "marketing",
        reason: "manual",
        source: "administrator",
        active: true,
        suppressed_at: "2026-07-22T00:00:00Z",
        expires_at: null,
        created_at: "2026-07-22T00:00:00Z",
        updated_at: "2026-07-22T00:00:00Z",
        created_by: "operator-1",
        updated_by: null,
        evidence_event_id: null,
        notes: "Manual suppression",
        deactivated_at: null,
        deactivated_by: null,
      },
      correlationId: "corr-suppression",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.suppressions.deactivate).mockResolvedValue({
      data: {
        id: "suppression-1",
        email: "blocked@example.com",
        scope: "marketing",
        reason: "manual",
        source: "administrator",
        active: false,
        suppressed_at: "2026-07-22T00:00:00Z",
        expires_at: null,
        created_at: "2026-07-22T00:00:00Z",
        updated_at: "2026-07-22T00:00:00Z",
        created_by: "operator-1",
        updated_by: null,
        evidence_event_id: null,
        notes: "Manual suppression",
        deactivated_at: "2026-07-23T00:00:00Z",
        deactivated_by: "operator-1",
      },
      correlationId: "corr-suppression-deactivate",
      timestamp: "2026-07-23T00:00:00Z",
    });
    renderRoutedPage(
      <SuppressionDetailPage />,
      "/email-marketing/suppressions/suppression-1",
      "/email-marketing/suppressions/:id"
    );
    await user.click(await screen.findByRole("button", { name: "Deactivate" }));
    expect(screen.getByRole("button", { name: "Confirm deactivation" })).toBeDisabled();
    await user.type(screen.getByLabelText("Deactivation reason"), "Manual review complete");
    await user.click(screen.getByRole("button", { name: "Confirm deactivation" }));
    expect(emailMarketingService.suppressions.deactivate).toHaveBeenCalledWith("suppression-1", {
      reason: "Manual review complete",
    });
  });

  it("renders inactive suppression detail fallbacks and fail-closed load errors", async () => {
    vi.mocked(emailMarketingService.suppressions.get).mockResolvedValue({
      data: {
        id: "suppression-closed",
        email: "restored@example.com",
        scope: "all",
        reason: "legal",
        source: "administrator",
        active: false,
        suppressed_at: "2026-07-22T00:00:00Z",
        expires_at: null,
        created_at: "2026-07-22T00:00:00Z",
        updated_at: "2026-07-23T00:00:00Z",
        created_by: null,
        updated_by: null,
        evidence_event_id: null,
        notes: "",
        deactivated_at: "2026-07-23T00:00:00Z",
        deactivated_by: "operator-2",
      },
      correlationId: "corr-suppression-inactive",
      timestamp: "2026-07-23T00:00:00Z",
    });

    const inactive = renderRoutedPage(
      <SuppressionDetailPage />,
      "/email-marketing/suppressions/suppression-closed",
      "/email-marketing/suppressions/:id"
    );

    expect(
      await screen.findByRole("heading", { name: "restored@example.com" })
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
    expect(screen.getByText("No notes recorded.")).toBeInTheDocument();
    expect(screen.getByText("Manual evidence")).toBeInTheDocument();
    inactive.unmount();

    vi.mocked(emailMarketingService.suppressions.get).mockRejectedValue(
      new ApiError("Suppression unavailable", 503, undefined, "SUPPRESSION_DOWN", "corr-supp-down")
    );
    renderRoutedPage(
      <SuppressionDetailPage />,
      "/email-marketing/suppressions/suppression-down",
      "/email-marketing/suppressions/:id"
    );

    expect(await screen.findByText("Delivery dependency unavailable")).toBeInTheDocument();
    expect(screen.getByText(/corr-supp-down/iu)).toBeInTheDocument();
  });

  it("activates, archives, clones, deletes, and renders template previews with governed payloads", async () => {
    const template = {
      id: "template-id",
      template_code: "WELCOME",
      template_name: "Welcome template",
      category: "general",
      subject: "Hello {{ first_name }}",
      status: "draft",
      version: 3,
      usage_count: 0,
      updated_at: "2026-07-22T00:00:00Z",
      created_at: "2026-07-21T00:00:00Z",
      created_by: null,
      updated_by: null,
      description: "Reusable welcome copy",
      preview_text: "Welcome",
      body_html: "<p>Hello Sam</p>",
      body_text: "Hello Sam",
      design_json: { blocks: [] },
      last_used_at: null,
      is_active: false,
      is_deleted: false,
    } as const;
    vi.mocked(emailMarketingService.templates.get).mockResolvedValue({
      data: template,
      correlationId: "corr-template",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.templates.preview).mockResolvedValue({
      data: {
        subject: "Hello Sam",
        html: "<p>Hello Sam</p>",
        text: "Hello Sam",
        warnings: ["Unused variable last_name"],
      },
      correlationId: "corr-render",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.templates.clone).mockResolvedValue({
      data: { ...template, id: "template-copy", template_code: "WELCOME_COPY" },
      correlationId: "corr-clone",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.templates.activate).mockResolvedValue({
      data: { ...template, status: "active", is_active: true },
      correlationId: "corr-activate",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.templates.archive).mockResolvedValue({
      data: { ...template, status: "archived" },
      correlationId: "corr-archive",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.templates.delete).mockResolvedValue(undefined);

    renderRoutedPage(
      <EmailTemplateDetailPage />,
      "/email-marketing/templates/template-id",
      "/email-marketing/templates/:id"
    );

    expect(await screen.findByRole("heading", { name: "Welcome template" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Activate" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm activate" }));
    const activateCall = vi.mocked(emailMarketingService.templates.activate).mock.calls[0];
    expect(activateCall?.[0]).toBe("template-id");
    expect(activateCall?.[1].idempotency_key).toMatch(/^activate-/u);

    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
    const archiveCall = vi.mocked(emailMarketingService.templates.archive).mock.calls[0];
    expect(archiveCall?.[0]).toBe("template-id");
    expect(archiveCall?.[1].idempotency_key).toMatch(/^archive-/u);

    await userEvent.click(screen.getByRole("button", { name: "Clone to draft" }));
    await userEvent.clear(screen.getByLabelText("New template code"));
    await userEvent.type(screen.getByLabelText("New template code"), "welcome_copy");
    await userEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(emailMarketingService.templates.clone).toHaveBeenCalledWith("template-id", {
        new_code: "WELCOME_COPY",
      })
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Clone template" })).not.toBeInTheDocument()
    );

    await userEvent.click(screen.getByRole("button", { name: "Render preview" }));
    await userEvent.click(screen.getByRole("button", { name: "Render" }));
    expect(emailMarketingService.templates.preview).toHaveBeenCalledWith("template-copy", {
      sample_data: { first_name: "Sam" },
    });
    expect(await screen.findByText("Unused variable last_name")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Preview sample data"), { target: { value: "{" } });
    await userEvent.click(screen.getByRole("button", { name: "Render" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sample data must be valid JSON.");

    const closeButtons = screen.getAllByRole("button", { name: "" });
    const previewClose = closeButtons.at(-1);
    if (!previewClose) throw new Error("Preview dialog close button was not rendered.");
    await userEvent.click(previewClose);
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(emailMarketingService.templates.delete).toHaveBeenCalledWith("template-copy");
  });

  it("queues campaign lifecycle actions with preflight receipt, schedule, and delete confirmation", async () => {
    const campaign = {
      id: "campaign-id",
      campaign_code: "WELCOME",
      campaign_name: "Welcome",
      campaign_type: "broadcast",
      subject: "Hello",
      status: "draft",
      template_id: null,
      scheduled_at: null,
      timezone: "UTC",
      resolved_recipient_count: 10,
      sent_count: 0,
      delivered_count: 0,
      opened_count: 0,
      clicked_count: 0,
      bounced_count: 0,
      failed_count: 0,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:00:00Z",
      created_by: null,
      updated_by: null,
      description: "Lifecycle test",
      preview_text: "Hi",
      from_name: "SARAISE",
      from_email: "sender@example.com",
      reply_to_email: null,
      audience_definition: { segment: "all" },
      audience_snapshot_at: null,
      queue_started_at: null,
      send_started_at: null,
      completed_at: null,
      content_snapshot_subject: "",
      content_snapshot_html: "",
      content_snapshot_text: "",
      template_version_snapshot: null,
      unique_opened_count: 0,
      unique_clicked_count: 0,
      unsubscribed_count: 0,
      complaint_count: 0,
      transition_history: [],
      last_error_code: "",
      last_error_detail: "",
      is_deleted: false,
    } as const;
    vi.mocked(emailMarketingService.campaigns.get).mockResolvedValue({
      data: campaign,
      correlationId: "corr-campaign",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.campaigns.analytics).mockResolvedValue({
      data: {
        campaign_id: "campaign-id",
        resolved: 10,
        eligible: 9,
        sent: 0,
        delivered: 0,
        unique_opened: 0,
        unique_clicked: 0,
        bounced: 0,
        failed: 0,
        unsubscribed: 0,
        complained: 0,
        delivery_rate: 0,
        unique_open_rate: 0,
        unique_click_rate: 0,
        bounce_rate: 0,
        counter_drift: { delivered: 0 },
        preflight: {
          content_valid: true,
          receipt: "receipt-send",
          rendered: true,
          resolved_count: 10,
          eligible_count: 9,
          suppressed_count: 1,
          consent_failure_count: 0,
          suppression_failure_count: 1,
          sender_healthy: true,
          sender_detail: "ready",
          quota_required: 9,
          quota_remaining: 100,
          scheduled_at: null,
          timezone: "UTC",
          blocking_reasons: [],
        },
      },
      correlationId: "corr-analytics",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.campaigns.resolveAudience).mockResolvedValue({
      data: {
        id: "job-resolve",
        job_type: "resolve",
        status: "queued",
        idempotency_key: "idem",
        created_at: "2026-07-22T00:00:00Z",
        correlation_id: "corr-resolve",
      },
      correlationId: "corr-resolve",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.campaigns.send).mockResolvedValue({
      data: {
        id: "job-send",
        job_type: "send",
        status: "queued",
        idempotency_key: "idem",
        created_at: "2026-07-22T00:00:00Z",
        correlation_id: "corr-send",
      },
      correlationId: "corr-send",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.campaigns.schedule).mockResolvedValue({
      data: campaign,
      correlationId: "corr-schedule",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.campaigns.cancel).mockResolvedValue({
      data: campaign,
      correlationId: "corr-cancel",
      timestamp: "2026-07-22T00:00:00Z",
    });
    vi.mocked(emailMarketingService.campaigns.delete).mockResolvedValue(undefined);

    renderRoutedPage(
      <EmailCampaignDetailPage />,
      "/email-marketing/campaigns/campaign-id",
      "/email-marketing/campaigns/:id"
    );
    await userEvent.click(await screen.findByRole("button", { name: "Resolve audience" }));
    expect(
      await screen.findByText(/resolve accepted · correlation corr-resolve/iu)
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Queue send" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm queue send" }));
    expect(emailMarketingService.campaigns.send).toHaveBeenCalledWith(
      "campaign-id",
      expect.objectContaining({ preflight_receipt: "receipt-send" })
    );

    await userEvent.type(screen.getByLabelText("Campaign schedule"), "2026-08-03T09:30");
    await userEvent.click(screen.getByRole("button", { name: "Schedule" }));
    expect(emailMarketingService.campaigns.schedule).toHaveBeenCalledWith(
      "campaign-id",
      expect.objectContaining({ timezone: "UTC" })
    );

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    expect(emailMarketingService.campaigns.cancel).toHaveBeenCalledWith(
      "campaign-id",
      expect.objectContaining({ reason: "Cancelled by operator" })
    );

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(emailMarketingService.campaigns.delete).toHaveBeenCalledWith("campaign-id");
  });
});
