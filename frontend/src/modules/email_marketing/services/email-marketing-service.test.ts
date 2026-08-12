/* eslint-disable @typescript-eslint/unbound-method, @typescript-eslint/consistent-type-imports, max-lines-per-function -- Vitest verifies calls on mocked object methods and keeps governed service fixtures local. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/services/api-client";
import { ENDPOINTS } from "../contracts";
import {
  EMAIL_MARKETING_QUERY_KEYS,
  buildQuery,
  emailMarketingService,
  unwrapEnvelope,
  unwrapPage,
} from "./email-marketing-service";
vi.mock("@/services/api-client", async () => {
  const actual =
    await vi.importActual<typeof import("@/services/api-client")>("@/services/api-client");
  return {
    ...actual,
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});
const meta = { correlation_id: "corr-1", timestamp: "2026-07-22T00:00:00Z" };
const pagination = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
};
const campaign = {
  id: "c1",
  campaign_code: "WELCOME",
  campaign_name: "Welcome",
  campaign_type: "broadcast",
  subject: "Hello",
  status: "draft",
  template_id: null,
  scheduled_at: null,
  timezone: "UTC",
  resolved_recipient_count: 0,
  sent_count: 0,
  delivered_count: 0,
  opened_count: 0,
  clicked_count: 0,
  bounced_count: 0,
  failed_count: 0,
  created_at: meta.timestamp,
  updated_at: meta.timestamp,
};
const configurationDocument = {
  schema_version: 1,
  defaults: {},
  limits: {},
  pagination: {},
  workflows: {},
  compliance: {},
  resilience: {},
  tokens: {},
  integrations: {},
  filters: {},
  health: {},
  rate_limits: {},
  quotas: {},
  feature_flags: {},
  display: {},
};
describe("email marketing service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "uuid-idempotency") });
  });
  afterEach(() => vi.unstubAllGlobals());
  it("preserves list metadata and encodes filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [campaign], meta: { ...meta, pagination } });
    const result = await emailMarketingService.campaigns.list({
      search: "summer & sale",
      status: "draft",
      page: 2,
    });
    expect(result.correlationId).toBe("corr-1");
    expect(result.pagination.count).toBe(1);
    expect(apiClient.get).toHaveBeenCalledWith(expect.stringContaining("search=summer+%26+sale"));
    expect(apiClient.get).toHaveBeenCalledWith(expect.stringContaining("page=2"));
  });
  it("throws instead of converting malformed or legacy lists to empty", () => {
    const validUnknown = (value: unknown): value is unknown => value !== undefined;
    expect(() => unwrapPage([], validUnknown)).toThrow(ApiError);
    expect(() => unwrapPage({ results: [] }, validUnknown)).toThrow("pagination");
    expect(() => unwrapEnvelope({ data: campaign }, validUnknown)).toThrow(ApiError);
    expect(() =>
      unwrapPage({ data: [{ ...campaign, id: 42 }], meta: { ...meta, pagination } }, validUnknown)
    ).not.toThrow();
    expect(() =>
      unwrapPage(
        { data: [undefined], meta: { ...meta, pagination } },
        (value): value is typeof campaign => value === campaign
      )
    ).toThrow("malformed list data");
  });

  it("preserves correlation IDs when envelope guards reject malformed details", () => {
    const failure = (() => {
      try {
        unwrapEnvelope(
          { data: { ...campaign, transition_history: "not-array" }, meta },
          (value): value is typeof campaign & { transition_history: [] } =>
            typeof value === "object" &&
            value !== null &&
            Array.isArray((value as { transition_history?: unknown }).transition_history)
        );
        return null;
      } catch (error) {
        return error;
      }
    })();
    expect(failure).toBeInstanceOf(ApiError);
    if (!(failure instanceof ApiError)) throw new Error("Expected ApiError");
    expect(failure.correlationId).toBe("corr-1");
    expect(failure.code).toBe("MALFORMED_RESPONSE");
  });
  it("uses PATCH and explicit lifecycle endpoints", async () => {
    const detail = {
      ...campaign,
      description: "",
      preview_text: "",
      from_name: "SARAISE",
      from_email: "sender@example.com",
      reply_to_email: null,
      audience_definition: {},
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
      created_by: null,
      updated_by: null,
    };
    vi.mocked(apiClient.patch).mockResolvedValue({ data: detail, meta });
    await emailMarketingService.campaigns.update("c1", { subject: "Updated" });
    expect(apiClient.patch).toHaveBeenCalledWith(ENDPOINTS.CAMPAIGNS.UPDATE("c1"), {
      subject: "Updated",
    });
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        id: "j1",
        job_type: "email_marketing.send_campaign",
        status: "queued",
        idempotency_key: "key",
        created_at: meta.timestamp,
        correlation_id: "corr-1",
      },
      meta,
    });
    await emailMarketingService.campaigns.send("c1", {
      idempotency_key: "key",
      preflight_receipt: "signed-receipt",
    });
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.CAMPAIGNS.SEND("c1"), {
      idempotency_key: "key",
      preflight_receipt: "signed-receipt",
    });
  });

  it("adds idempotency headers only for create-style endpoints", async () => {
    const detail = {
      ...campaign,
      description: "",
      preview_text: "",
      from_name: "SARAISE",
      from_email: "sender@example.com",
      reply_to_email: null,
      audience_definition: {},
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
      created_by: null,
      updated_by: null,
    };
    vi.mocked(apiClient.post).mockResolvedValue({ data: detail, meta });
    await emailMarketingService.campaigns.create({
      campaign_code: "WELCOME",
      campaign_name: "Welcome",
      campaign_type: "broadcast",
      subject: "Hello",
      from_name: "SARAISE",
      from_email: "sender@example.com",
      audience_definition: {},
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      ENDPOINTS.CAMPAIGNS.CREATE,
      expect.objectContaining({ campaign_code: "WELCOME" }),
      { headers: { "Idempotency-Key": "uuid-idempotency" } }
    );
  });
  it("builds query strings without undefined values", () => {
    expect(buildQuery("/items/", { page: 1, search: "", status: undefined, active: false })).toBe(
      "/items/?page=1&active=false"
    );
    expect(buildQuery("/items/", { page: null, search: "a/b", active: true })).toBe(
      "/items/?search=a%2Fb&active=true"
    );
  });
  it("exports stable query keys for every governed cache family", () => {
    expect(EMAIL_MARKETING_QUERY_KEYS.all).toEqual(["email-marketing"]);
    expect(EMAIL_MARKETING_QUERY_KEYS.campaigns({ status: "draft" })).toEqual([
      "email-marketing",
      "campaigns",
      { status: "draft" },
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.campaign("campaign-id")).toEqual([
      "email-marketing",
      "campaign",
      "campaign-id",
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.analytics("campaign-id")).toEqual([
      "email-marketing",
      "analytics",
      "campaign-id",
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.templates({ category: "general" })).toEqual([
      "email-marketing",
      "templates",
      { category: "general" },
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.template("template-id")).toEqual([
      "email-marketing",
      "template",
      "template-id",
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.recipients({ campaign_id: "campaign-id" })).toEqual([
      "email-marketing",
      "recipients",
      { campaign_id: "campaign-id" },
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.recipient("recipient-id")).toEqual([
      "email-marketing",
      "recipient",
      "recipient-id",
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.deliveries({ status: "delivered" })).toEqual([
      "email-marketing",
      "deliveries",
      { status: "delivered" },
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.delivery("delivery-id")).toEqual([
      "email-marketing",
      "delivery",
      "delivery-id",
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.suppressions({ active: true })).toEqual([
      "email-marketing",
      "suppressions",
      { active: true },
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.suppression("suppression-id")).toEqual([
      "email-marketing",
      "suppression",
      "suppression-id",
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.consents({ status: "granted" })).toEqual([
      "email-marketing",
      "consents",
      { status: "granted" },
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.consent("consent-id")).toEqual([
      "email-marketing",
      "consent",
      "consent-id",
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.configuration).toEqual(["email-marketing", "configuration"]);
    expect(EMAIL_MARKETING_QUERY_KEYS.configurationHistory).toEqual([
      "email-marketing",
      "configuration",
      "history",
    ]);
    expect(EMAIL_MARKETING_QUERY_KEYS.health).toEqual(["email-marketing", "health"]);
  });
  it("accepts the minimal public unsubscribe response and exposes no browser provider-secret transport", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { suppression_id: "suppression-1", status: "unsubscribed" },
      meta,
    });
    const result = await emailMarketingService.public.unsubscribe({
      token: "signed-token",
      occurred_at: meta.timestamp,
    });
    expect(result.data).toEqual({ suppression_id: "suppression-1", status: "unsubscribed" });
    expect("providerEvents" in emailMarketingService).toBe(false);
    expect(emailMarketingService.public.openUrl("token/unsafe")).toBe(
      "/api/v2/email-marketing/t/token%2Funsafe/open.gif"
    );
    expect(emailMarketingService.public.clickUrl("token/unsafe")).toBe(
      "/api/v2/email-marketing/t/token%2Funsafe/click/"
    );
  });

  it("uses exact governed configuration endpoints", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: [
        {
          id: "version-1",
          version: 1,
          previous_version: null,
          change_type: "materialized",
          actor_id: null,
          correlation_id: "corr-version",
          previous_document: null,
          document: configurationDocument,
          created_at: meta.timestamp,
          rollback_source_version: null,
        },
      ],
      meta,
    });
    await emailMarketingService.configuration.history();
    expect(apiClient.get).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.HISTORY);

    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        id: "config-id",
        environment: "development",
        version: 2,
        document: configurationDocument,
        updated_at: meta.timestamp,
        updated_by: null,
      },
      meta,
    });
    await emailMarketingService.configuration.rollback({
      target_version: 1,
      expected_version: 2,
    });
    expect(apiClient.post).toHaveBeenCalledWith(ENDPOINTS.CONFIGURATION.ROLLBACK, {
      target_version: 1,
      expected_version: 2,
    });
  });
});
