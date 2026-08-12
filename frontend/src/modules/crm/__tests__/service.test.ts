/* eslint-disable @typescript-eslint/no-unsafe-assignment -- reviewed existing generated/cohesive surface; zero-warning gate remains enforced for unsuppressed rules. */
/* eslint-disable @typescript-eslint/unbound-method, @typescript-eslint/consistent-type-imports -- Vitest mocks intentionally reference object methods and import-original types */
/* eslint-disable max-lines-per-function -- CRM service mutation tests intentionally keep scenario matrices colocated with their request/guard fixtures. */
import { ApiError, apiClient } from "@/services/api-client";
import { CrmApiError, crmKeys, crmService } from "../services/crm-service";
import type { CrmConfiguration, CrmConfigurationExport, CrmConfigurationWrite } from "../contracts";

vi.mock("@/services/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/services/api-client")>();
  return { ...actual, apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const meta = { correlation_id: "req-crm-1", timestamp: "2026-07-22T00:00:00Z" };
const pageMeta = {
  ...meta,
  pagination: {
    page: 1,
    page_size: 25,
    total_pages: 1,
    count: 1,
    has_next: false,
    has_previous: false,
  },
};
const lead = {
  id: "11111111-1111-4111-8111-111111111111",
  tenant_id: "22222222-2222-4222-8222-222222222222",
  created_at: meta.timestamp,
  updated_at: meta.timestamp,
  created_by: null,
  updated_by: null,
  version: 3,
  is_deleted: false,
  deleted_at: null,
  metadata: {},
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.test",
  phone: "",
  company: "Analytical",
  title: "",
  score: 82,
  grade: "A",
  score_source: "rules",
  score_explanation: { source: "profile" },
  source: "referral",
  campaign_id: null,
  owner_id: null,
  status: "qualified",
  converted_at: null,
  converted_to_opportunity_id: null,
  transition_history: [],
};
const account = {
  ...lead,
  name: "Analytical Engines",
  website: "https://example.test",
  industry: "Computing",
  employees: 42,
  annual_revenue: "100000.00",
  parent_account_id: null,
  billing_street: "",
  billing_city: "",
  billing_state: "",
  billing_postal_code: "",
  billing_country: "",
  account_type: "customer",
};
const contact = {
  ...lead,
  account_id: account.id,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.test",
  mobile: "",
  department: "",
  linkedin: "",
  twitter: "",
  last_contacted_at: null,
  engagement_score: 73,
};
const opportunity = {
  ...lead,
  account_id: account.id,
  primary_contact_id: null,
  name: "Engine Expansion",
  description: "",
  amount: "125000.00",
  currency: "USD",
  probability: 45,
  stage: "proposal",
  close_date: "2026-08-31",
  product_ids: [],
  competitors: [],
  status: "open",
  closed_at: null,
  loss_reason: "",
  converted_to_order_id: null,
  last_activity_at: null,
};
const activity = {
  ...lead,
  activity_type: "task",
  related_to_type: "Lead",
  related_to_id: lead.id,
  subject: "Follow up",
  description: "",
  outcome: "",
  due_date: null,
  completed: false,
  completed_at: null,
  external_id: "",
};

const configurationDocument = {
  field_limits: {
    phone_min_digits: 7,
    phone_max_digits: 15,
    lead_name: 80,
    lead_email: 254,
    lead_phone: 40,
    lead_status: 32,
    account_name: 160,
    account_industry: 80,
    account_postal_code: 20,
    account_country: 80,
    contact_name: 80,
    contact_email: 254,
    contact_phone: 40,
    opportunity_name: 160,
    opportunity_amount_digits: 12,
    opportunity_amount_decimals: 2,
    opportunity_currency: 3,
    opportunity_stage: 40,
    opportunity_status: 20,
    activity_subject: 160,
    activity_outcome: 500,
    activity_external_id: 80,
    actor_id: 80,
    correlation_id: 80,
    async_idempotency_key: 120,
    domain_override_reason: 250,
    transition_reason: 250,
    loss_reason: 250,
    provider_id: 80,
    provider_evidence_string: 250,
  },
  lead: {
    default_score: 10,
    default_grade: "C",
    default_score_source: "rules",
    default_status: "new",
    score_min: 0,
    score_max: 100,
    grade_thresholds: { A: 85, B: 70, C: 50, D: 0 },
    qualification_threshold: 70,
    field_score_weights: {},
    source_score_weights: {},
    terminal_states: ["converted", "lost"],
    transitions: { qualify: { from: ["contacted"], to: "qualified" } },
  },
  account: {
    default_type: "prospect",
    allowed_types: ["prospect", "customer"],
    hierarchy_max_depth: 4,
  },
  contact: {
    default_engagement_score: 0,
    engagement_score_min: 0,
    engagement_score_max: 100,
    enforce_account_email_domain: true,
    engagement_lookback_days: 30,
    engagement_points_per_interaction: 5,
  },
  opportunity: {
    default_currency: "USD",
    default_probability: 10,
    default_stage: "prospecting",
    default_status: "open",
    probability_min: 0,
    probability_max: 100,
    minimum_amount: "0.00",
    closed_won_probability: 100,
    closed_lost_probability: 0,
    terminal_states: ["closed_won", "closed_lost"],
    transitions: { advance: { from: ["prospecting"], to: "qualification" } },
    stages: [{ name: "prospecting", probability: 10, semantic_token: "info" }],
  },
  activity: {
    default_type: "task",
    default_related_type: "Lead",
    require_future_task_due_date: true,
  },
  hierarchy: { max_nodes: 100, max_children: 20, page_size: 25 },
  forecast: { default_period_days: 90, minimum_period_days: 1, maximum_period_days: 365 },
  providers: {
    lead_scoring: null,
    revenue_prediction: null,
    score_min: 0,
    score_max: 100,
    confidence_min: "0.00",
    confidence_max: "1.00",
    maximum_evidence_factors: 8,
    extension_schema_version: "1",
    extension_priority_default: 10,
    extension_priority_min: 0,
    extension_priority_max: 100,
    retry_attempts: 2,
    backoff_base_seconds: "1.00",
    backoff_max_seconds: "30.00",
    backoff_jitter_seconds: "0.50",
  },
  jobs: {
    stale_deal_days: 30,
    stale_deal_min_days: 1,
    stale_deal_max_days: 365,
    iterator_chunk_size: 100,
  },
  pagination: { default_page_size: 25, maximum_page_size: 100 },
  api: { quota_cost: 1 },
  conversion: {
    create_account_by_default: true,
    close_date_offset_days: 30,
    use_current_version: true,
    transition_key_prefix: "lead-convert",
  },
  health: { cache_timeout_seconds: 2 },
  ui: {
    score_bands: [{ minimum: 85, grade: "A", semantic_token: "success" }],
    hierarchy_auto_expand_levels: 2,
    hierarchy_indentation_pixels: 16,
    minimum_pipeline_bar_percent: 5,
    saved_page_size: 25,
    dashboard_forecast_period_days: 90,
    prediction_retry_enabled: true,
    stale_deal_page_size: 20,
    pipeline_fetch_limit: 50,
  },
} satisfies CrmConfiguration["document"];
const configuration = {
  id: "cfg-1",
  environment: "development",
  version: 6,
  document: configurationDocument,
  feature_flags: { crm_v2: true },
  rollout: { enabled: true, percentage: 25, roles: ["admin"], cohorts: ["pilot"] },
  updated_at: meta.timestamp,
} satisfies CrmConfiguration;
const configurationWrite = {
  environment: configuration.environment,
  document: configuration.document,
  feature_flags: { crm_v2: true },
  rollout: configuration.rollout,
} satisfies CrmConfigurationWrite;

const envelope = <T>(data: T) => ({ data, meta });
const pageEnvelope = <T>(data: readonly T[]) => ({ data, meta: pageMeta });

describe("crmService governed decoding", () => {
  beforeEach(() => vi.resetAllMocks());

  it("publishes stable cache keys for every CRM resource family", () => {
    expect(crmKeys.all).toEqual(["crm"]);
    expect(crmKeys.leads({ status: "qualified" })).toEqual([
      "crm",
      "leads",
      { status: "qualified" },
    ]);
    expect(crmKeys.lead("lead-1")).toEqual(["crm", "lead", "lead-1"]);
    expect(crmKeys.accounts()).toEqual(["crm", "accounts", {}]);
    expect(crmKeys.account("account-1")).toEqual(["crm", "account", "account-1"]);
    expect(crmKeys.contacts()).toEqual(["crm", "contacts", {}]);
    expect(crmKeys.contact("contact-1")).toEqual(["crm", "contact", "contact-1"]);
    expect(crmKeys.opportunities()).toEqual(["crm", "opportunities", {}]);
    expect(crmKeys.opportunity("opportunity-1")).toEqual(["crm", "opportunity", "opportunity-1"]);
    expect(crmKeys.activities()).toEqual(["crm", "activities", {}]);
    expect(crmKeys.activity("activity-1")).toEqual(["crm", "activity", "activity-1"]);
    expect(crmKeys.forecast("pipeline", { period: 30 })).toEqual([
      "crm",
      "forecast",
      "pipeline",
      { period: 30 },
    ]);
    expect(crmKeys.configuration()).toEqual(["crm", "configuration"]);
    expect(crmKeys.configurationVersions()).toEqual(["crm", "configuration", "versions"]);
  });

  it("decodes page envelopes and serializes zero-valued filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(pageEnvelope([lead]));
    const result = await crmService.listLeads({ score_min: 0, search: "Ada Lovelace", page: 1 });
    expect(result.items[0]?.last_name).toBe("Lovelace");
    expect(result.correlationId).toBe("req-crm-1");
    expect(result.pagination.total_count).toBe(1);
    expect(vi.mocked(apiClient.get).mock.calls[0]?.[0]).toContain("score_min=0");
    expect(vi.mocked(apiClient.get).mock.calls[0]?.[0]).toContain("search=Ada+Lovelace");
  });

  it("omits empty filters while preserving boolean false", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(pageEnvelope([activity]));
    const filtersWithNull = {
      completed: false,
      owner_id: "",
      due_from: undefined,
      due_to: null,
    } as unknown as Parameters<typeof crmService.listActivities>[0];
    await crmService.listActivities(filtersWithNull);
    const url = vi.mocked(apiClient.get).mock.calls[0]?.[0] ?? "";
    expect(url).toContain("completed=false");
    expect(url).not.toContain("owner_id=");
    expect(url).not.toContain("due_from=");
    expect(url).not.toContain("due_to=");
  });

  it("sends optimistic concurrency in payload and If-Match", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ data: lead, meta });
    await crmService.updateLead(lead.id, { company: "Difference Engine", version: 3 });
    // Vitest asymmetric matcher factories are intentionally untyped at this boundary.
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    expect(apiClient.patch).toHaveBeenCalledWith(
      expect.stringContaining(lead.id),
      expect.objectContaining({ version: 3 }),
      {
        headers: expect.objectContaining({
          "If-Match": "3",
          "Idempotency-Key": expect.any(String),
        }),
      }
    );
  });

  it.each([
    [400, "validation"],
    [401, "authentication"],
    [403, "permission"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "validation"],
    [429, "rate_limit"],
    [503, "unavailable"],
  ] as const)("maps %s distinctly", async (status, kind) => {
    vi.mocked(apiClient.get).mockRejectedValue(
      new ApiError("governed failure", status, {}, "domain_error", "req-error")
    );
    await expect(crmService.getLead(lead.id)).rejects.toMatchObject({
      kind,
      status,
      correlationId: "req-error",
    } satisfies Partial<CrmApiError>);
  });

  it("never accepts malformed success as an entity", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { id: lead.id }, meta });
    await expect(crmService.getLead(lead.id)).rejects.toMatchObject({
      kind: "invalid_response",
      code: "invalid_response",
      message: "CRM returned an invalid lead response.",
    });
  });

  it("reports invalid pages when pagination or one row is malformed", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [lead, { id: "missing-version" }],
      meta: pageMeta,
    });
    await expect(crmService.listLeads()).rejects.toMatchObject({
      kind: "invalid_response",
      correlationId: "req-crm-1",
      code: "invalid_response",
      message: "CRM returned an invalid lead page.",
    });

    vi.mocked(apiClient.get).mockResolvedValue({ data: [lead], meta });
    await expect(crmService.listLeads()).rejects.toMatchObject({
      kind: "invalid_response",
      correlationId: "req-crm-1",
    });
  });

  it("classifies network and unexpected thrown failures without leaking internals", async () => {
    const governedFailure = new CrmApiError(
      "Already normalized.",
      "validation",
      422,
      "validation_error",
      "req-normalized"
    );
    vi.mocked(apiClient.get).mockRejectedValueOnce(governedFailure);
    await expect(crmService.getLead(lead.id)).rejects.toBe(governedFailure);

    vi.mocked(apiClient.get).mockRejectedValueOnce(new TypeError("fetch failed"));
    await expect(crmService.getLead(lead.id)).rejects.toMatchObject({
      kind: "network",
      status: null,
      code: "network_error",
      message: "CRM could not be reached. Check your connection and retry.",
    });

    vi.mocked(apiClient.get).mockRejectedValueOnce("boom");
    await expect(crmService.getLead(lead.id)).rejects.toMatchObject({
      kind: "unexpected",
      status: null,
      code: "unexpected_error",
      message: "Unexpected CRM failure.",
    });

    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error("extension exploded"));
    await expect(crmService.getLead(lead.id)).rejects.toMatchObject({
      kind: "unexpected",
      status: null,
      code: "unexpected_error",
      message: "extension exploded",
    });
  });

  it("maps unknown CRM HTTP statuses to unexpected without dropping response metadata", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(
      new ApiError("teapot", 418, { error: { detail: "short" } }, undefined, undefined)
    );
    await expect(crmService.getLead(lead.id)).rejects.toMatchObject({
      kind: "unexpected",
      status: 418,
      code: "request_failed",
      correlationId: null,
      details: { error: { detail: "short" } },
    });
  });

  it("sends mutation headers for creates, deletes, transitions, and async score", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(lead));
    await crmService.createLead({ last_name: "Lovelace", source: "referral" });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v2/crm/leads/",
      expect.objectContaining({ last_name: "Lovelace" }),
      { headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }) }
    );

    vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);
    await crmService.deleteLead(lead.id, 4);
    expect(apiClient.delete).toHaveBeenLastCalledWith(expect.stringContaining(lead.id), {
      headers: { "If-Match": "4", "Idempotency-Key": expect.any(String) },
    });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(lead));
    await crmService.transitionLead(lead.id, {
      command: "qualify",
      transition_key: "lead-qualify-1",
      expected_version: 5,
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/transition/"),
      expect.objectContaining({ command: "qualify", expected_version: 5 }),
      { headers: { "If-Match": "5", "Idempotency-Key": "lead-qualify-1" } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({
        job_id: "job-1",
        status: "queued",
        command: "score",
        created_at: meta.timestamp,
        correlation_id: meta.correlation_id,
      })
    );
    await expect(crmService.scoreLeadAsync(lead.id, "score-key-1")).resolves.toMatchObject({
      job_id: "job-1",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/score/"),
      { async_execution: true, idempotency_key: "score-key-1" },
      { headers: { "Idempotency-Key": "score-key-1" } }
    );
  });

  it("covers account CRUD request contracts and malformed page rows", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(pageEnvelope([account]));
    await crmService.listAccounts({
      search: "Analytical",
      account_type: "customer",
      page_size: 50,
    });
    expect(vi.mocked(apiClient.get).mock.calls.at(-1)?.[0]).toContain("account_type=customer");
    expect(vi.mocked(apiClient.get).mock.calls.at(-1)?.[0]).toContain("page_size=50");

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope(account));
    await expect(crmService.getAccount(account.id)).resolves.toMatchObject({ name: account.name });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(account));
    await crmService.createAccount({ name: account.name, account_type: "customer" });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v2/crm/accounts/",
      { name: account.name, account_type: "customer" },
      { headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }) }
    );

    vi.mocked(apiClient.patch).mockResolvedValueOnce(envelope(account));
    await crmService.updateAccount(account.id, { industry: "Mathematics", version: 11 });
    expect(apiClient.patch).toHaveBeenLastCalledWith(
      expect.stringContaining(account.id),
      { industry: "Mathematics", version: 11 },
      { headers: { "If-Match": "11", "Idempotency-Key": expect.any(String) } }
    );

    vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);
    await expect(crmService.deleteAccount(account.id, 12)).resolves.toBeUndefined();
    expect(apiClient.delete).toHaveBeenLastCalledWith(expect.stringContaining(account.id), {
      headers: { "If-Match": "12", "Idempotency-Key": expect.any(String) },
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(pageEnvelope([{ ...account, version: "bad" }]));
    await expect(crmService.listAccounts()).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("covers contact CRUD request contracts and strict entity guards", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(pageEnvelope([contact]));
    await crmService.listContacts({ account_id: account.id, search: "Ada" });
    const listUrl = vi.mocked(apiClient.get).mock.calls.at(-1)?.[0] ?? "";
    expect(listUrl).toContain(`account_id=${account.id}`);
    expect(listUrl).toContain("search=Ada");

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope(contact));
    await expect(crmService.getContact(contact.id)).resolves.toMatchObject({
      account_id: account.id,
    });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(contact));
    await crmService.createContact({
      account_id: account.id,
      first_name: "Ada",
      last_name: "Lovelace",
      email: "ada@example.test",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v2/crm/contacts/",
      expect.objectContaining({ account_id: account.id, email: "ada@example.test" }),
      { headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }) }
    );

    vi.mocked(apiClient.patch).mockResolvedValueOnce(envelope(contact));
    await crmService.updateContact(contact.id, { department: "Research", version: 13 });
    expect(apiClient.patch).toHaveBeenLastCalledWith(
      expect.stringContaining(contact.id),
      { department: "Research", version: 13 },
      { headers: { "If-Match": "13", "Idempotency-Key": expect.any(String) } }
    );

    vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);
    await crmService.deleteContact(contact.id, 14);
    expect(apiClient.delete).toHaveBeenLastCalledWith(expect.stringContaining(contact.id), {
      headers: { "If-Match": "14", "Idempotency-Key": expect.any(String) },
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope({ ...contact, last_name: 123 }));
    await expect(crmService.getContact(contact.id)).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("covers opportunity CRUD plus close-lost and direct transition contracts", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(pageEnvelope([opportunity]));
    await crmService.listOpportunities({ stage: "proposal", status: "open", page: 2 });
    const listUrl = vi.mocked(apiClient.get).mock.calls.at(-1)?.[0] ?? "";
    expect(listUrl).toContain("stage=proposal");
    expect(listUrl).toContain("status=open");
    expect(listUrl).toContain("page=2");

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope(opportunity));
    await expect(crmService.getOpportunity(opportunity.id)).resolves.toMatchObject({
      name: opportunity.name,
    });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(opportunity));
    await crmService.createOpportunity({
      account_id: account.id,
      name: opportunity.name,
      amount: opportunity.amount,
      currency: opportunity.currency,
      close_date: opportunity.close_date,
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v2/crm/opportunities/",
      expect.objectContaining({ account_id: account.id, name: opportunity.name }),
      { headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }) }
    );

    vi.mocked(apiClient.patch).mockResolvedValueOnce(envelope(opportunity));
    await crmService.updateOpportunity(opportunity.id, { probability: 60, version: 15 });
    expect(apiClient.patch).toHaveBeenLastCalledWith(
      expect.stringContaining(opportunity.id),
      { probability: 60, version: 15 },
      { headers: { "If-Match": "15", "Idempotency-Key": expect.any(String) } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({ ...opportunity, stage: "negotiation" })
    );
    await crmService.transitionOpportunity(opportunity.id, {
      command: "advance_to_negotiation",
      transition_key: "opp-direct-1",
      expected_version: 16,
      reason: "confirmed by buyer",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/transition/"),
      expect.objectContaining({ command: "advance_to_negotiation" }),
      { headers: { "If-Match": "16", "Idempotency-Key": "opp-direct-1" } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ ...opportunity, status: "lost" }));
    await crmService.closeOpportunityLost(opportunity.id, {
      expected_version: 17,
      transition_key: "lost-1",
      loss_reason: "budget",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/close-lost/"),
      { expected_version: 17, transition_key: "lost-1", loss_reason: "budget" },
      { headers: { "If-Match": "17", "Idempotency-Key": "lost-1" } }
    );

    vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);
    await crmService.deleteOpportunity(opportunity.id, 18);
    expect(apiClient.delete).toHaveBeenLastCalledWith(expect.stringContaining(opportunity.id), {
      headers: { "If-Match": "18", "Idempotency-Key": expect.any(String) },
    });
  });

  it("covers activity CRUD and direct completion transition contracts", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(pageEnvelope([activity]));
    await crmService.listActivities({ related_to_type: "Lead", related_to_id: lead.id });
    const listUrl = vi.mocked(apiClient.get).mock.calls.at(-1)?.[0] ?? "";
    expect(listUrl).toContain("related_to_type=Lead");
    expect(listUrl).toContain(`related_to_id=${lead.id}`);

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope(activity));
    await expect(crmService.getActivity(activity.id)).resolves.toMatchObject({
      subject: activity.subject,
    });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(activity));
    await crmService.createActivity({
      activity_type: "task",
      related_to_type: "Lead",
      related_to_id: lead.id,
      subject: "Follow up",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v2/crm/activities/",
      expect.objectContaining({ related_to_type: "Lead", subject: "Follow up" }),
      { headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }) }
    );

    vi.mocked(apiClient.patch).mockResolvedValueOnce(envelope(activity));
    await crmService.updateActivity(activity.id, { outcome: "Connected", version: 19 });
    expect(apiClient.patch).toHaveBeenLastCalledWith(
      expect.stringContaining(activity.id),
      { outcome: "Connected", version: 19 },
      { headers: { "If-Match": "19", "Idempotency-Key": expect.any(String) } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ ...activity, completed: true }));
    await crmService.completeActivity(activity.id, {
      expected_version: 20,
      transition_key: "complete-direct-1",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/complete/"),
      { expected_version: 20, transition_key: "complete-direct-1" },
      { headers: { "If-Match": "20", "Idempotency-Key": "complete-direct-1" } }
    );

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope({ ...activity, subject: 123 }));
    await expect(crmService.getActivity(activity.id)).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("normalizes lead conversion aliases and validates conversion members", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({ lead, account, contact: null, opportunity })
    );
    await crmService.convertLead(lead.id, {
      amount: "125000.00",
      currency: "USD",
      close_date: "2026-08-31",
      opportunity_name: "Engine Expansion",
      create_account: { name: "Analytical Engines" },
      transition_key: "convert-1",
      expected_version: 6,
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/convert/"),
      {
        amount: "125000.00",
        currency: "USD",
        close_date: "2026-08-31",
        name: "Engine Expansion",
        account_id: undefined,
        create_new_account: true,
        transition_key: "convert-1",
        expected_version: 6,
      },
      { headers: { "If-Match": "6", "Idempotency-Key": "convert-1" } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ lead, account, opportunity }));
    await crmService.convertLead(lead.id, {
      amount: "2500.00",
      currency: "USD",
      close_date: "2026-09-30",
      name: "Existing account conversion",
      account_id: account.id,
      create_new_account: false,
      transition_key: "convert-existing",
      expected_version: 8,
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/convert/"),
      {
        amount: "2500.00",
        currency: "USD",
        close_date: "2026-09-30",
        name: "Existing account conversion",
        account_id: account.id,
        create_new_account: false,
        transition_key: "convert-existing",
        expected_version: 8,
      },
      { headers: { "If-Match": "8", "Idempotency-Key": "convert-existing" } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({ lead, account: { id: account.id }, contact: null, opportunity })
    );
    await expect(
      crmService.convertLead(lead.id, {
        amount: "1.00",
        currency: "USD",
        close_date: "2026-08-31",
        name: "Invalid conversion",
        create_new_account: false,
        transition_key: "convert-2",
        expected_version: 7,
      })
    ).rejects.toMatchObject({ kind: "invalid_response" });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ lead, account, opportunity }));
    await crmService.convertLead(lead.id, {
      amount: "15.00",
      currency: "USD",
      close_date: "2026-10-01",
      account_id: account.id,
      create_account: { name: "Ignored because account_id wins" },
      transition_key: "convert-account-wins",
      expected_version: 9,
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/convert/"),
      expect.objectContaining({
        name: undefined,
        account_id: account.id,
        create_new_account: false,
      }),
      { headers: { "If-Match": "9", "Idempotency-Key": "convert-account-wins" } }
    );
  });

  it.each([
    ["qualification", "advance_to_qualification"],
    ["needs_analysis", "advance_to_needs_analysis"],
    ["proposal", "advance_to_proposal"],
    ["negotiation", "advance_to_negotiation"],
    ["prospecting", "reopen_to_prospecting"],
  ] as const)("maps opportunity target_stage %s to command %s", async (targetStage, command) => {
    vi.mocked(apiClient.post).mockResolvedValue(envelope(opportunity));
    await crmService.transitionOpportunity(opportunity.id, {
      target_stage: targetStage,
      transition_key: `opp-${targetStage}`,
      expected_version: 8,
      reason: "operator requested",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/transition/"),
      expect.objectContaining({ command, reason: "operator requested" }),
      { headers: { "If-Match": "8", "Idempotency-Key": `opp-${targetStage}` } }
    );
  });

  it("normalizes close-won confirmation and activity completion idempotency alias", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ ...opportunity, status: "won" }));
    await crmService.closeOpportunityWon(opportunity.id, {
      expected_version: 9,
      transition_key: "won-1",
      confirmation: true,
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/close-won/"),
      { expected_version: 9, transition_key: "won-1", confirmed: true },
      { headers: { "If-Match": "9", "Idempotency-Key": "won-1" } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ ...opportunity, status: "won" }));
    await crmService.closeOpportunityWon(opportunity.id, {
      expected_version: 11,
      transition_key: "won-direct",
      confirmed: true,
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/close-won/"),
      { expected_version: 11, transition_key: "won-direct", confirmed: true },
      { headers: { "If-Match": "11", "Idempotency-Key": "won-direct" } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ ...activity, completed: true }));
    await crmService.completeActivity(activity.id, {
      expected_version: 10,
      idempotency_key: "done-1",
    });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/complete/"),
      { expected_version: 10, transition_key: "done-1" },
      { headers: { "If-Match": "10", "Idempotency-Key": "done-1" } }
    );
  });

  it("decodes account helpers, forecast variants, predictions, and jobs with strict guards", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope({ id: account.id, children: [] }));
    await expect(crmService.getAccountHierarchy(account.id)).resolves.toMatchObject({
      id: account.id,
      children: [],
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope({ local_matches: [account], external_matches: [], enrichment_status: "available" })
    );
    await expect(crmService.findAccountDuplicates("Analytical", "")).resolves.toMatchObject({
      enrichment_status: "available",
    });
    expect(vi.mocked(apiClient.get).mock.calls.at(-1)?.[0]).not.toContain("website=");

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope({ currencies: [], period_days: 90 }));
    await expect(crmService.getPipeline({ period: 90 })).resolves.toMatchObject({
      period_days: 90,
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope({ currencies: [], period_days: 30 }));
    await crmService.getPipeline();
    expect(apiClient.get).toHaveBeenLastCalledWith("/api/v2/crm/forecasting/pipeline/");

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope({ win_rate: "0.42", won_count: 2, lost_count: 3, total_closed: 5, period_days: 90 })
    );
    await expect(crmService.getWinRate()).resolves.toMatchObject({ total_closed: 5 });

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope([
        {
          stage: "proposal",
          currency: "USD",
          total_value: "10.00",
          weighted_value: "4.50",
          opportunity_count: 1,
        },
      ])
    );
    await expect(crmService.getForecastByStage()).resolves.toHaveLength(1);

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({
        amount: "4500.00",
        currency: "USD",
        confidence: "0.83",
        factors: {},
        provider: "rules",
        model: "baseline",
        as_of: meta.timestamp,
        period_days: 30,
      })
    );
    await crmService.predictRevenue({ period: 30 });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v2/crm/forecasting/predict/",
      { period: 30 },
      { headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }) }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({
        amount: "9000.00",
        currency: "USD",
        confidence: "0.75",
        factors: {},
        provider: "rules",
        model: "baseline",
        as_of: meta.timestamp,
        period_days: 90,
      })
    );
    await crmService.getAIPrediction({ period: 90 });
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v2/crm/forecasting/predict/",
      { period: 90 },
      { headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }) }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({
        amount: "12000.00",
        currency: "USD",
        confidence: "0.80",
        factors: {},
        provider: "rules",
        model: "baseline",
        as_of: meta.timestamp,
        period_days: 30,
      })
    );
    await crmService.predictRevenue();
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v2/crm/forecasting/predict/",
      { period: undefined },
      { headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }) }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ ...lead, score: 91 }));
    await crmService.scoreLead(lead.id, 21);
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/score/"),
      {},
      { headers: { "If-Match": "21", "Idempotency-Key": expect.any(String) } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ ...lead, score: 88 }));
    await crmService.scoreLead(lead.id);
    expect(apiClient.post).toHaveBeenLastCalledWith(
      expect.stringContaining("/score/"),
      {},
      { headers: { "Idempotency-Key": expect.any(String) } }
    );
    expect(vi.mocked(apiClient.post).mock.calls.at(-1)?.[2]?.headers).not.toHaveProperty(
      "If-Match"
    );

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope({
        id: "job-2",
        command: "score",
        status: "succeeded",
        progress: 100,
        result: null,
        error: null,
        created_at: meta.timestamp,
        updated_at: meta.timestamp,
        correlation_id: meta.correlation_id,
      })
    );
    await expect(crmService.getJob("job-2")).resolves.toMatchObject({ id: "job-2" });
  });

  it("rejects malformed forecast, prediction, job, hierarchy, and duplicate responses", async () => {
    const getCases = [
      [() => crmService.getPipeline(), { currencies: "USD", period_days: 30 }],
      [() => crmService.getPipeline(), { currencies: [], period_days: "30" }],
      [() => crmService.getWinRate(), { total_closed: "5" }],
      [() => crmService.getForecastByStage(), [{ stage: "proposal", currency: 7 }]],
      [() => crmService.getJob("job-1"), { id: "job-1", status: 7 }],
      [() => crmService.getAccountHierarchy(account.id), { id: account.id, children: {} }],
      [
        () => crmService.findAccountDuplicates("Analytical"),
        { local_matches: [], external_matches: [], enrichment_status: 7 },
      ],
    ] as const;

    for (const [run, response] of getCases) {
      vi.mocked(apiClient.get).mockResolvedValueOnce(envelope(response));
      await expect(run()).rejects.toMatchObject({ kind: "invalid_response" });
    }

    for (const response of [
      { amount: 100, currency: "USD", provider: "rules" },
      { amount: "100.00", currency: 840, provider: "rules" },
      { amount: "100.00", currency: "USD", provider: null },
    ]) {
      vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(response));
      await expect(crmService.predictRevenue()).rejects.toMatchObject({
        kind: "invalid_response",
      });
    }
  });

  it("rejects malformed async operation and configuration guard edge cases", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ job_id: "job-1" }));
    await expect(crmService.scoreLeadAsync(lead.id, "score-key-2")).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({ job_id: 99, status: "queued" }));
    await expect(crmService.scoreLeadAsync(lead.id, "score-key-3")).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({ valid: true, effective: configuration, errors: {} })
    );
    await expect(crmService.previewConfiguration(configurationWrite)).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({ valid: "true", effective: configuration, errors: {}, diff: {} })
    );
    await expect(crmService.previewConfiguration(configurationWrite)).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({ valid: true, effective: null, errors: {}, diff: {} })
    );
    await expect(crmService.previewConfiguration(configurationWrite)).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope([{ id: "version-7", version: 7, document: configurationDocument }])
    );
    await expect(crmService.listConfigurationVersions()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope([{ id: 7, version: 7, document: configurationDocument, correlation_id: "req-7" }])
    );
    await expect(crmService.listConfigurationVersions()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope({ schema_version: 2, module: "crm", exported_at: meta.timestamp, configuration })
    );
    await expect(crmService.exportConfiguration()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope({ schema_version: 1, module: "sales", configuration })
    );
    await expect(crmService.exportConfiguration()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope({ ...configuration, feature_flags: [] })
    );
    await expect(crmService.getConfiguration()).rejects.toMatchObject({
      kind: "invalid_response",
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope({ ...configuration, rollout: null }));
    await expect(crmService.getConfiguration()).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("governs configuration read, write, preview, history, rollback, import, and export", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope(configuration));
    await expect(crmService.getConfiguration()).resolves.toMatchObject({ version: 6 });

    vi.mocked(apiClient.patch).mockResolvedValueOnce(envelope({ ...configuration, version: 7 }));
    await crmService.updateConfiguration(configurationWrite, 6);
    expect(apiClient.patch).toHaveBeenLastCalledWith(
      "/api/v2/crm/configuration/",
      configurationWrite,
      { headers: { "If-Match": "6", "Idempotency-Key": expect.any(String) } }
    );

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({ valid: true, effective: configuration, errors: {}, diff: { changed: true } })
    );
    await expect(crmService.previewConfiguration(configurationWrite)).resolves.toMatchObject({
      valid: true,
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(
      envelope([
        {
          id: "version-6",
          environment: "development",
          version: 6,
          document: configurationDocument,
          feature_flags: configuration.feature_flags,
          rollout: configuration.rollout,
          created_at: meta.timestamp,
          created_by: "operator",
          correlation_id: "req-version-6",
        },
      ])
    );
    await expect(crmService.listConfigurationVersions()).resolves.toHaveLength(1);

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(configuration));
    await crmService.rollbackConfiguration(5);
    expect(apiClient.post).toHaveBeenLastCalledWith(
      "/api/v2/crm/configuration/rollback/",
      { version: 5 },
      { headers: { "Idempotency-Key": expect.any(String) } }
    );

    const exported = {
      schema_version: 1,
      module: "crm",
      configuration,
    } satisfies CrmConfigurationExport;
    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(configuration));
    await crmService.importConfiguration(exported);
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v2/crm/configuration/import/", exported, {
      headers: { "Idempotency-Key": expect.any(String) },
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope(exported));
    await expect(crmService.exportConfiguration()).resolves.toMatchObject({ module: "crm" });
  });

  it("returns decoded values from every CRM service wrapper", async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce(pageEnvelope([lead]));
    await expect(crmService.listLeads()).resolves.toMatchObject({
      items: [expect.objectContaining({ id: lead.id })],
    });

    vi.mocked(apiClient.get).mockResolvedValueOnce(envelope(lead));
    await expect(crmService.getLead(lead.id)).resolves.toMatchObject({ id: lead.id });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(lead));
    await expect(
      crmService.createLead({ last_name: "Lovelace", source: "referral" })
    ).resolves.toMatchObject({
      id: lead.id,
    });

    vi.mocked(apiClient.patch).mockResolvedValueOnce(envelope(lead));
    await expect(crmService.updateLead(lead.id, { version: 3 })).resolves.toMatchObject({
      id: lead.id,
    });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(lead));
    await expect(
      crmService.transitionLead(lead.id, {
        command: "qualify",
        transition_key: "lead-return",
        expected_version: 3,
      })
    ).resolves.toMatchObject({ id: lead.id });

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({ lead, account, contact, opportunity })
    );
    await expect(
      crmService.convertLead(lead.id, {
        amount: "125000.00",
        currency: "USD",
        close_date: "2026-08-31",
        name: "Engine Expansion",
        create_new_account: true,
        transition_key: "convert-return",
        expected_version: 3,
      })
    ).resolves.toMatchObject({ lead: expect.objectContaining({ id: lead.id }) });

    vi.mocked(apiClient.post).mockResolvedValueOnce(envelope(lead));
    await expect(crmService.scoreLead(lead.id)).resolves.toMatchObject({ id: lead.id });

    vi.mocked(apiClient.post).mockResolvedValueOnce(
      envelope({ job_id: "job-return", status: "queued" })
    );
    await expect(crmService.scoreLeadAsync(lead.id, "score-return")).resolves.toMatchObject({
      job_id: "job-return",
    });

    const accountMethods = [
      [() => crmService.listAccounts(), pageEnvelope([account]), "items"],
      [() => crmService.getAccount(account.id), envelope(account), "id"],
      [() => crmService.createAccount({ name: account.name }), envelope(account), "id"],
      [() => crmService.updateAccount(account.id, { version: 3 }), envelope(account), "id"],
      [
        () => crmService.getAccountHierarchy(account.id),
        envelope({ id: account.id, children: [] }),
        "id",
      ],
      [
        () => crmService.findAccountDuplicates(account.name),
        envelope({ local_matches: [], external_matches: [], enrichment_status: "available" }),
        "enrichment_status",
      ],
    ] as const;
    for (const [run, response, expectedKey] of accountMethods) {
      vi.mocked(apiClient.get).mockReset();
      vi.mocked(apiClient.post).mockReset();
      vi.mocked(apiClient.patch).mockReset();
      vi.mocked(apiClient.get).mockResolvedValueOnce(response);
      vi.mocked(apiClient.post).mockResolvedValueOnce(response);
      vi.mocked(apiClient.patch).mockResolvedValueOnce(response);
      await expect(run()).resolves.toHaveProperty(expectedKey);
    }

    const contactMethods = [
      [() => crmService.listContacts(), pageEnvelope([contact]), "items"],
      [() => crmService.getContact(contact.id), envelope(contact), "id"],
      [
        () =>
          crmService.createContact({
            account_id: account.id,
            last_name: "Lovelace",
          }),
        envelope(contact),
        "id",
      ],
      [() => crmService.updateContact(contact.id, { version: 3 }), envelope(contact), "id"],
    ] as const;
    for (const [run, response, expectedKey] of contactMethods) {
      vi.mocked(apiClient.get).mockReset();
      vi.mocked(apiClient.post).mockReset();
      vi.mocked(apiClient.patch).mockReset();
      vi.mocked(apiClient.get).mockResolvedValueOnce(response);
      vi.mocked(apiClient.post).mockResolvedValueOnce(response);
      vi.mocked(apiClient.patch).mockResolvedValueOnce(response);
      await expect(run()).resolves.toHaveProperty(expectedKey);
    }

    const opportunityMethods = [
      [() => crmService.listOpportunities(), pageEnvelope([opportunity]), "items"],
      [() => crmService.getOpportunity(opportunity.id), envelope(opportunity), "id"],
      [
        () =>
          crmService.createOpportunity({
            account_id: account.id,
            name: opportunity.name,
            amount: opportunity.amount,
            currency: opportunity.currency,
            close_date: opportunity.close_date,
          }),
        envelope(opportunity),
        "id",
      ],
      [
        () => crmService.updateOpportunity(opportunity.id, { version: 3 }),
        envelope(opportunity),
        "id",
      ],
      [
        () =>
          crmService.transitionOpportunity(opportunity.id, {
            command: "advance_to_negotiation",
            transition_key: "opp-return",
            expected_version: 3,
          }),
        envelope(opportunity),
        "id",
      ],
      [
        () =>
          crmService.closeOpportunityWon(opportunity.id, {
            expected_version: 3,
            transition_key: "won-return",
            confirmed: true,
          }),
        envelope(opportunity),
        "id",
      ],
      [
        () =>
          crmService.closeOpportunityLost(opportunity.id, {
            expected_version: 3,
            transition_key: "lost-return",
            loss_reason: "budget",
          }),
        envelope(opportunity),
        "id",
      ],
    ] as const;
    for (const [run, response, expectedKey] of opportunityMethods) {
      vi.mocked(apiClient.get).mockReset();
      vi.mocked(apiClient.post).mockReset();
      vi.mocked(apiClient.patch).mockReset();
      vi.mocked(apiClient.get).mockResolvedValueOnce(response);
      vi.mocked(apiClient.post).mockResolvedValueOnce(response);
      vi.mocked(apiClient.patch).mockResolvedValueOnce(response);
      await expect(run()).resolves.toHaveProperty(expectedKey);
    }

    const activityMethods = [
      [() => crmService.listActivities(), pageEnvelope([activity]), "items"],
      [() => crmService.getActivity(activity.id), envelope(activity), "id"],
      [
        () =>
          crmService.createActivity({
            activity_type: "task",
            related_to_type: "Lead",
            related_to_id: lead.id,
            subject: "Follow up",
          }),
        envelope(activity),
        "id",
      ],
      [() => crmService.updateActivity(activity.id, { version: 3 }), envelope(activity), "id"],
      [
        () =>
          crmService.completeActivity(activity.id, {
            expected_version: 3,
            transition_key: "complete-return",
          }),
        envelope(activity),
        "id",
      ],
    ] as const;
    for (const [run, response, expectedKey] of activityMethods) {
      vi.mocked(apiClient.get).mockReset();
      vi.mocked(apiClient.post).mockReset();
      vi.mocked(apiClient.patch).mockReset();
      vi.mocked(apiClient.get).mockResolvedValueOnce(response);
      vi.mocked(apiClient.post).mockResolvedValueOnce(response);
      vi.mocked(apiClient.patch).mockResolvedValueOnce(response);
      await expect(run()).resolves.toHaveProperty(expectedKey);
    }

    const forecastMethods = [
      [
        () => crmService.getPipeline(),
        envelope({ currencies: [], period_days: 30 }),
        "period_days",
      ],
      [
        () => crmService.getWinRate(),
        envelope({ win_rate: null, won_count: 0, lost_count: 0, total_closed: 0, period_days: 30 }),
        "total_closed",
      ],
      [
        () => crmService.getForecastByStage(),
        envelope([
          {
            stage: "proposal",
            currency: "USD",
            total_value: "0.00",
            weighted_value: "0.00",
            opportunity_count: 0,
          },
        ]),
        "0.stage",
      ],
      [
        () => crmService.predictRevenue(),
        envelope({ amount: "0.00", currency: "USD", provider: "rules" }),
        "amount",
      ],
      [
        () => crmService.getAIPrediction({ period: 30 }),
        envelope({ amount: "1.00", currency: "USD", provider: "rules" }),
        "amount",
      ],
      [
        () => crmService.getJob("job-return"),
        envelope({ id: "job-return", status: "succeeded" }),
        "id",
      ],
    ] as const;
    for (const [run, response, expectedKey] of forecastMethods) {
      vi.mocked(apiClient.get).mockReset();
      vi.mocked(apiClient.post).mockReset();
      vi.mocked(apiClient.get).mockResolvedValueOnce(response);
      vi.mocked(apiClient.post).mockResolvedValueOnce(response);
      await expect(run()).resolves.toHaveProperty(expectedKey);
    }

    const exported = {
      schema_version: 1,
      module: "crm",
      configuration,
    } satisfies CrmConfigurationExport;
    const configurationMethods = [
      [() => crmService.getConfiguration(), envelope(configuration), "version"],
      [
        () => crmService.updateConfiguration(configurationWrite, 6),
        envelope(configuration),
        "version",
      ],
      [
        () => crmService.previewConfiguration(configurationWrite),
        envelope({ valid: true, effective: configuration, errors: {}, diff: {} }),
        "valid",
      ],
      [
        () => crmService.listConfigurationVersions(),
        envelope([
          {
            id: "version-return",
            version: 6,
            document: configurationDocument,
            correlation_id: "req-version-return",
          },
        ]),
        "0.version",
      ],
      [() => crmService.rollbackConfiguration(6), envelope(configuration), "version"],
      [() => crmService.importConfiguration(exported), envelope(configuration), "version"],
      [() => crmService.exportConfiguration(), envelope(exported), "module"],
    ] as const;
    for (const [run, response, expectedKey] of configurationMethods) {
      vi.mocked(apiClient.get).mockReset();
      vi.mocked(apiClient.post).mockReset();
      vi.mocked(apiClient.patch).mockReset();
      vi.mocked(apiClient.get).mockResolvedValueOnce(response);
      vi.mocked(apiClient.post).mockResolvedValueOnce(response);
      vi.mocked(apiClient.patch).mockResolvedValueOnce(response);
      await expect(run()).resolves.toHaveProperty(expectedKey);
    }

    vi.mocked(apiClient.delete).mockResolvedValue(undefined);
    await crmService.deleteLead(lead.id, 3);
    await crmService.deleteAccount(account.id, 3);
    await crmService.deleteContact(contact.id, 3);
    await crmService.deleteOpportunity(opportunity.id, 3);
    expect(apiClient.delete).toHaveBeenCalledTimes(4);
  });

  it("uses resource-specific invalid response messages for every CRM wrapper", async () => {
    const invalidDetail = envelope({});
    const invalidPage = { data: [{}], meta: pageMeta };
    const cases = [
      [() => crmService.listLeads(), "get", invalidPage, "lead page"],
      [() => crmService.getLead(lead.id), "get", invalidDetail, "lead response"],
      [
        () => crmService.createLead({ last_name: "Lovelace", source: "referral" }),
        "post",
        invalidDetail,
        "lead response",
      ],
      [
        () => crmService.updateLead(lead.id, { version: 3 }),
        "patch",
        invalidDetail,
        "lead response",
      ],
      [
        () =>
          crmService.transitionLead(lead.id, {
            command: "qualify",
            transition_key: "lead-invalid",
            expected_version: 3,
          }),
        "post",
        invalidDetail,
        "lead response",
      ],
      [
        () =>
          crmService.convertLead(lead.id, {
            amount: "1.00",
            currency: "USD",
            close_date: "2026-08-31",
            name: "Invalid conversion",
            create_new_account: true,
            transition_key: "convert-invalid",
            expected_version: 3,
          }),
        "post",
        invalidDetail,
        "lead conversion response",
      ],
      [() => crmService.scoreLead(lead.id), "post", invalidDetail, "lead score response"],
      [
        () => crmService.scoreLeadAsync(lead.id, "score-invalid"),
        "post",
        invalidDetail,
        "asynchronous lead score operation response",
      ],
      [() => crmService.listAccounts(), "get", invalidPage, "account page"],
      [() => crmService.getAccount(account.id), "get", invalidDetail, "account response"],
      [
        () => crmService.createAccount({ name: account.name }),
        "post",
        invalidDetail,
        "account response",
      ],
      [
        () => crmService.updateAccount(account.id, { version: 3 }),
        "patch",
        invalidDetail,
        "account response",
      ],
      [
        () => crmService.getAccountHierarchy(account.id),
        "get",
        invalidDetail,
        "account hierarchy response",
      ],
      [
        () => crmService.findAccountDuplicates(account.name),
        "get",
        invalidDetail,
        "account duplicate response",
      ],
      [() => crmService.listContacts(), "get", invalidPage, "contact page"],
      [() => crmService.getContact(contact.id), "get", invalidDetail, "contact response"],
      [
        () => crmService.createContact({ account_id: account.id, last_name: "Lovelace" }),
        "post",
        invalidDetail,
        "contact response",
      ],
      [
        () => crmService.updateContact(contact.id, { version: 3 }),
        "patch",
        invalidDetail,
        "contact response",
      ],
      [() => crmService.listOpportunities(), "get", invalidPage, "opportunity page"],
      [
        () => crmService.getOpportunity(opportunity.id),
        "get",
        invalidDetail,
        "opportunity response",
      ],
      [
        () =>
          crmService.createOpportunity({
            account_id: account.id,
            name: opportunity.name,
            amount: opportunity.amount,
            currency: opportunity.currency,
            close_date: opportunity.close_date,
          }),
        "post",
        invalidDetail,
        "opportunity response",
      ],
      [
        () => crmService.updateOpportunity(opportunity.id, { version: 3 }),
        "patch",
        invalidDetail,
        "opportunity response",
      ],
      [
        () =>
          crmService.transitionOpportunity(opportunity.id, {
            command: "advance_to_negotiation",
            transition_key: "opp-invalid",
            expected_version: 3,
          }),
        "post",
        invalidDetail,
        "opportunity response",
      ],
      [
        () =>
          crmService.closeOpportunityWon(opportunity.id, {
            expected_version: 3,
            transition_key: "won-invalid",
            confirmed: true,
          }),
        "post",
        invalidDetail,
        "opportunity response",
      ],
      [
        () =>
          crmService.closeOpportunityLost(opportunity.id, {
            expected_version: 3,
            transition_key: "lost-invalid",
            loss_reason: "budget",
          }),
        "post",
        invalidDetail,
        "opportunity response",
      ],
      [() => crmService.listActivities(), "get", invalidPage, "activity page"],
      [() => crmService.getActivity(activity.id), "get", invalidDetail, "activity response"],
      [
        () =>
          crmService.createActivity({
            activity_type: "task",
            related_to_type: "Lead",
            related_to_id: lead.id,
            subject: "Follow up",
          }),
        "post",
        invalidDetail,
        "activity response",
      ],
      [
        () => crmService.updateActivity(activity.id, { version: 3 }),
        "patch",
        invalidDetail,
        "activity response",
      ],
      [
        () =>
          crmService.completeActivity(activity.id, {
            expected_version: 3,
            transition_key: "complete-invalid",
          }),
        "post",
        invalidDetail,
        "activity response",
      ],
      [() => crmService.getPipeline(), "get", invalidDetail, "pipeline forecast response"],
      [() => crmService.getWinRate(), "get", invalidDetail, "win-rate forecast response"],
      [() => crmService.getForecastByStage(), "get", invalidDetail, "stage forecast response"],
      [() => crmService.predictRevenue(), "post", invalidDetail, "revenue prediction response"],
      [() => crmService.getJob("job-invalid"), "get", invalidDetail, "job response"],
      [() => crmService.getConfiguration(), "get", invalidDetail, "configuration response"],
      [
        () => crmService.updateConfiguration(configurationWrite, 6),
        "patch",
        invalidDetail,
        "configuration response",
      ],
      [
        () => crmService.previewConfiguration(configurationWrite),
        "post",
        invalidDetail,
        "configuration preview response",
      ],
      [
        () => crmService.listConfigurationVersions(),
        "get",
        invalidDetail,
        "configuration versions response",
      ],
      [
        () => crmService.rollbackConfiguration(6),
        "post",
        invalidDetail,
        "configuration rollback response",
      ],
      [
        () =>
          crmService.importConfiguration({
            schema_version: 1,
            module: "crm",
            configuration,
          }),
        "post",
        invalidDetail,
        "configuration import response",
      ],
      [
        () => crmService.exportConfiguration(),
        "get",
        invalidDetail,
        "configuration export response",
      ],
    ] as const;

    for (const [run, method, response, label] of cases) {
      vi.resetAllMocks();
      vi.mocked(apiClient[method]).mockResolvedValueOnce(response);
      await expect(run()).rejects.toMatchObject({
        kind: "invalid_response",
        message: `CRM returned an invalid ${label}.`,
      });
    }
  });

  it("rejects malformed configuration surfaces", async () => {
    const cases = [
      () => crmService.getConfiguration(),
      () => crmService.previewConfiguration(configurationWrite),
      () => crmService.listConfigurationVersions(),
      () => crmService.rollbackConfiguration(4),
      () =>
        crmService.importConfiguration({
          schema_version: 1,
          module: "crm",
          configuration,
        }),
      () => crmService.exportConfiguration(),
    ] as const;

    for (const run of cases) {
      vi.mocked(apiClient.get).mockResolvedValueOnce(envelope({}));
      vi.mocked(apiClient.post).mockResolvedValueOnce(envelope({}));
      await expect(run()).rejects.toMatchObject({ kind: "invalid_response" });
    }

    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: lead });
    await expect(crmService.getLead(lead.id)).rejects.toMatchObject({
      kind: "invalid_response",
      correlationId: null,
    });
  });
});
