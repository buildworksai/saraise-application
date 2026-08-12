/* eslint-disable max-lines-per-function -- page-level CRM workflows keep fixtures close to assertions. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EntityList } from "../components/EntityList";
import { AccountHierarchyTree } from "../components/AccountHierarchyTree";
import { LeadScoreIndicator } from "../components/LeadScoreIndicator";
import { AccountDetailPage } from "../pages/AccountDetailPage";
import { AccountListPage } from "../pages/AccountListPage";
import { ActivityListPage } from "../pages/ActivityListPage";
import { ActivityDetailPage } from "../pages/ActivityDetailPage";
import { ContactDetailPage } from "../pages/ContactDetailPage";
import { ContactListPage } from "../pages/ContactListPage";
import { LeadDetailPage } from "../pages/LeadDetailPage";
import { LeadListPage } from "../pages/LeadListPage";
import { OpportunityListPage } from "../pages/OpportunityListPage";
import { OpportunityDetailPage } from "../pages/OpportunityDetailPage";
import { OpportunityKanbanPage } from "../pages/OpportunityKanbanPage";
import { SalesDashboardPage } from "../pages/SalesDashboardPage";
import { crmKeys, crmService, type PageResult } from "../services/crm-service";
import type {
  CrmConfiguration,
  Account,
  AccountHierarchyNode,
  Activity,
  Contact,
  Lead,
  Opportunity,
  PaginationMeta,
} from "../contracts";

const pagination: PaginationMeta & { total_count: number } = {
  count: 1,
  page: 1,
  page_size: 25,
  total_pages: 1,
  has_next: false,
  has_previous: false,
  total_count: 1,
};
const emptyPage = <T,>(): PageResult<T> => ({
  items: [],
  pagination: { ...pagination, count: 0, total_count: 0 },
  correlationId: "req-page",
});
const page = <T,>(items: readonly T[]): PageResult<T> => ({
  items,
  pagination: { ...pagination, count: items.length, total_count: items.length },
  correlationId: "req-page",
});
const lead: Lead = {
  id: "11111111-1111-4111-8111-111111111111",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  version: 3,
  first_name: "Ada",
  last_name: "Lovelace",
  email: "ada@example.test",
  phone: "",
  company: "Analytical",
  title: "Founder",
  score: 82,
  grade: "B",
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
const opportunity: Opportunity = {
  ...lead,
  account_id: "33333333-3333-4333-8333-333333333333",
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
const account: Account = {
  id: "33333333-3333-4333-8333-333333333333",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  version: 5,
  name: "Analytical",
  website: "https://analytical.example.test",
  industry: "Manufacturing",
  employees: 1200,
  annual_revenue: "45000000.00",
  parent_account_id: null,
  billing_street: "1 Engine Way",
  billing_city: "London",
  billing_state: "Greater London",
  billing_postal_code: "NW1",
  billing_country: "GB",
  owner_id: "owner-1",
  account_type: "customer",
};
const accountHierarchy: AccountHierarchyNode = {
  id: account.id,
  name: account.name,
  account_type: "customer",
  children: [
    {
      id: "44444444-4444-4444-8444-444444444444",
      name: "Analytical Services",
      account_type: "partner",
      children: [],
    },
  ],
};
const contact: Contact = {
  id: "66666666-6666-4666-8666-666666666666",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  version: 4,
  account_id: account.id,
  first_name: "Grace",
  last_name: "Hopper",
  email: "grace@example.test",
  phone: "+15550100",
  mobile: "+15550101",
  title: "Operations sponsor",
  department: "Operations",
  linkedin: "https://linkedin.example.test/grace",
  twitter: "",
  last_contacted_at: "2026-07-21T08:00:00Z",
  engagement_score: 76,
  owner_id: "owner-1",
};
const activity: Activity = {
  id: "55555555-5555-4555-8555-555555555555",
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
  version: 2,
  activity_type: "task",
  related_to_type: "Opportunity",
  related_to_id: opportunity.id,
  subject: "Send technical proposal",
  description: "Prepare ERP scope",
  outcome: "",
  due_date: "2026-01-01T08:00:00Z",
  completed: false,
  completed_at: null,
  owner_id: "owner-1",
  external_id: "crm-task-1",
};
const configuration: CrmConfiguration = {
  id: "cfg-1",
  environment: "test",
  version: 6,
  document: {
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
      transitions: {},
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
      minimum_amount: "1.00",
      closed_won_probability: 100,
      closed_lost_probability: 0,
      terminal_states: ["closed_won", "closed_lost"],
      transitions: {},
      stages: [
        { name: "prospecting", probability: 10, semantic_token: "info" },
        { name: "qualification", probability: 30, semantic_token: "warning" },
        { name: "proposal", probability: 60, semantic_token: "accent" },
      ],
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
      prediction_retry_enabled: false,
      stale_deal_page_size: 20,
      pipeline_fetch_limit: 50,
    },
  },
  feature_flags: {
    async_lead_scoring: false,
    revenue_prediction: false,
    stale_deal_detection: true,
  },
  rollout: { enabled: true, percentage: 100, roles: ["admin"], cohorts: ["pilot"] },
  updated_at: "2026-07-22T00:00:00Z",
};

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location-search">{location.search}</output>;
}

function clientWithConfiguration(value: CrmConfiguration = configuration) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(crmKeys.configuration(), value);
  return client;
}

function renderRoute(path: string, routePath: string, element: React.ReactElement) {
  return render(
    <QueryClientProvider client={clientWithConfiguration()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={element} />
          <Route path="*" element={null} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderWithClient(
  element: React.ReactElement,
  initial = "/",
  client = clientWithConfiguration()
) {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        {element}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CRM detail, dashboard, kanban, and list pages", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    vi.spyOn(crmService, "getConfiguration").mockResolvedValue(configuration);
    vi.spyOn(crmService, "getLead").mockResolvedValue(lead);
    vi.spyOn(crmService, "listActivities").mockResolvedValue(emptyPage());
    vi.spyOn(crmService, "getAccount").mockResolvedValue(account);
    vi.spyOn(crmService, "getAccountHierarchy").mockResolvedValue(accountHierarchy);
    vi.spyOn(crmService, "listContacts").mockResolvedValue(emptyPage());
    vi.spyOn(crmService, "getContact").mockResolvedValue(contact);
    vi.spyOn(crmService, "deleteContact").mockResolvedValue(undefined);
    vi.spyOn(crmService, "listLeads").mockResolvedValue(page([lead]));
    vi.spyOn(crmService, "listAccounts").mockResolvedValue(page([account]));
    vi.spyOn(crmService, "getActivity").mockResolvedValue(activity);
    vi.spyOn(crmService, "completeActivity").mockResolvedValue({
      ...activity,
      completed: true,
      completed_at: "2026-07-22T08:00:00Z",
      version: 3,
    });
    vi.spyOn(crmService, "deleteAccount").mockResolvedValue(undefined);
    vi.spyOn(crmService, "convertLead").mockResolvedValue({
      lead: { ...lead, status: "converted", converted_to_opportunity_id: opportunity.id },
      contact: null,
      account: {
        ...lead,
        id: opportunity.account_id,
        name: "Analytical",
        website: "",
        industry: "",
        employees: null,
        annual_revenue: null,
        parent_account_id: null,
        billing_street: "",
        billing_city: "",
        billing_state: "",
        billing_postal_code: "",
        billing_country: "",
        account_type: "customer",
      },
      opportunity,
    });
    vi.spyOn(crmService, "deleteLead").mockResolvedValue(undefined);
    vi.spyOn(crmService, "getOpportunity").mockResolvedValue(opportunity);
    vi.spyOn(crmService, "closeOpportunityWon").mockResolvedValue({
      ...opportunity,
      status: "won",
    });
    vi.spyOn(crmService, "closeOpportunityLost").mockResolvedValue({
      ...opportunity,
      status: "lost",
      loss_reason: "Budget paused",
    });
    vi.spyOn(crmService, "deleteOpportunity").mockResolvedValue(undefined);
    vi.spyOn(crmService, "listOpportunities").mockResolvedValue(page([opportunity]));
    vi.spyOn(crmService, "transitionOpportunity").mockResolvedValue({
      ...opportunity,
      stage: "qualification",
    });
    vi.spyOn(crmService, "getPipeline").mockResolvedValue({
      period_days: 90,
      currencies: [
        {
          currency: "USD",
          opportunity_count: 1,
          total_pipeline_value: "125000.00",
          weighted_pipeline_value: "56250.00",
        },
      ],
    });
    vi.spyOn(crmService, "getWinRate").mockResolvedValue({
      period_days: 90,
      won_count: 2,
      lost_count: 1,
      total_closed: 3,
      win_rate: "66.7",
    });
    vi.spyOn(crmService, "predictRevenue").mockResolvedValue({
      amount: "90000.00",
      currency: "USD",
      confidence: "0.80",
      provider: "forecast-provider",
      model: "v1",
      as_of: "2026-07-22T00:00:00Z",
      period_days: 90,
      factors: {},
    });
  });

  it("converts a qualified lead with version, uppercase currency, and auditable transition key", async () => {
    const user = userEvent.setup();
    renderRoute(`/crm/leads/${lead.id}`, "/crm/leads/:id", <LeadDetailPage />);

    expect(await screen.findByRole("heading", { name: "Ada Lovelace" })).toBeInTheDocument();
    expect(
      screen.getByText("Asynchronous lead scoring is disabled by tenant configuration.")
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Convert" }));
    await screen.findByText("Convert qualified lead");
    const amount = document.querySelector<HTMLInputElement>("#amount");
    const currency = document.querySelector<HTMLInputElement>("#currency");
    expect(amount).not.toBeNull();
    expect(currency).not.toBeNull();
    fireEvent.change(amount!, { target: { value: "25000" } });
    fireEvent.change(currency!, { target: { value: "usd" } });
    await user.click(screen.getByRole("button", { name: "Review and convert" }));

    await waitFor(() => expect(crmService.convertLead).toHaveBeenCalled());
    const conversionCall = vi.mocked(crmService.convertLead).mock.calls[0];
    expect(conversionCall?.[0]).toBe(lead.id);
    expect(conversionCall?.[1]).toMatchObject({
      amount: "25000",
      currency: "USD",
      opportunity_name: "Analytical opportunity",
      account_id: undefined,
      create_account: { name: "Analytical" },
      contact_decision: "create",
      expected_version: 3,
    });
    expect(typeof conversionCall?.[1].close_date).toBe("string");
    expect(conversionCall?.[1].transition_key).toMatch(/^lead-convert-/u);
  });

  it("closes opportunity detail workflows with guarded mutation payloads", async () => {
    const user = userEvent.setup();
    renderRoute(
      `/crm/opportunities/${opportunity.id}`,
      "/crm/opportunities/:id",
      <OpportunityDetailPage />
    );

    expect(await screen.findByRole("heading", { name: "Engine Expansion" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close lost" }));
    await screen.findByText("Close opportunity as lost");
    await user.type(screen.getByRole("textbox"), "Budget paused");
    await user.click(screen.getByRole("button", { name: "Confirm lost" }));
    const closeLostCall = vi.mocked(crmService.closeOpportunityLost).mock.calls[0];
    expect(closeLostCall?.[0]).toBe(opportunity.id);
    expect(closeLostCall?.[1].expected_version).toBe(3);
    expect(closeLostCall?.[1].transition_key).toMatch(/^close-lost-/u);
    expect(closeLostCall?.[1].loss_reason).toBe("Budget paused");
  });

  it("uses dashboard configuration for service calls and does not fabricate disabled predictions", async () => {
    const oldDeal = {
      ...opportunity,
      id: "old",
      name: "Dormant expansion",
      last_activity_at: null,
    };
    vi.mocked(crmService.listOpportunities).mockResolvedValue(page([oldDeal]));
    renderWithClient(<SalesDashboardPage />);

    expect(await screen.findByRole("heading", { name: "Sales dashboard" })).toBeInTheDocument();
    expect(crmService.getPipeline).toHaveBeenCalledWith({ period: 90 });
    expect(crmService.getWinRate).toHaveBeenCalledWith({ period: 90 });
    expect(crmService.listOpportunities).toHaveBeenCalledWith({
      status: "open",
      ordering: "last_activity_at",
      page_size: 20,
    });
    expect(crmService.predictRevenue).not.toHaveBeenCalled();
    expect(screen.getByText("Dormant expansion")).toBeInTheDocument();
    expect(screen.getByText("Revenue prediction disabled")).toBeInTheDocument();
  });

  it("moves kanban cards by keyboard only after explicit confirmation", async () => {
    const user = userEvent.setup();
    renderWithClient(<OpportunityKanbanPage />);

    expect(await screen.findByLabelText("Opportunity pipeline board")).toBeInTheDocument();
    screen.getByText("Engine Expansion").closest("article")?.focus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByText(/Move .+ to qualification/u)).toBeInTheDocument();
    expect(crmService.transitionOpportunity).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirm move" }));

    const transitionCall = vi.mocked(crmService.transitionOpportunity).mock.calls[0];
    expect(transitionCall?.[0]).toBe(opportunity.id);
    expect(transitionCall?.[1]).toMatchObject({
      target_stage: "qualification",
      expected_version: 3,
      reason: "Pipeline board movement",
    });
    expect(transitionCall?.[1].transition_key).toMatch(/^pipeline-/u);
  });

  it("renders account detail relationship evidence and deletes with the current version", async () => {
    const user = userEvent.setup();
    vi.mocked(crmService.listActivities).mockResolvedValue(page([activity]));
    vi.mocked(crmService.listOpportunities).mockResolvedValue(page([opportunity]));
    renderRoute(`/crm/accounts/${account.id}`, "/crm/accounts/:id", <AccountDetailPage />);

    expect(await screen.findByRole("heading", { name: "Analytical" })).toBeInTheDocument();
    expect(screen.getByText("Manufacturing")).toBeInTheDocument();
    expect(screen.getByText("https://analytical.example.test")).toHaveAttribute(
      "href",
      "https://analytical.example.test"
    );
    expect(screen.getByText("1 Engine Way, London, Greater London, NW1, GB")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Analytical Services" })).toHaveAttribute(
      "href",
      `/crm/accounts/${accountHierarchy.children[0]?.id}`
    );
    expect(screen.getByText("Opportunities")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(await screen.findByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(crmService.deleteAccount).toHaveBeenCalledWith(account.id, 5));
  });

  it("passes opportunity URL filters to the governed service and renders currency totals", async () => {
    renderRoute(
      "/crm/opportunities?search=engine&stage=proposal&account_id=33333333-3333-4333-8333-333333333333&page=2&ordering=-amount",
      "/crm/opportunities",
      <OpportunityListPage />
    );

    expect(await screen.findByRole("heading", { name: "Opportunities" })).toBeInTheDocument();
    await waitFor(() =>
      expect(crmService.listOpportunities).toHaveBeenCalledWith({
        search: "engine",
        status: undefined,
        stage: "proposal",
        account_id: account.id,
        close_date_from: undefined,
        close_date_to: undefined,
        page: 2,
        page_size: 25,
        ordering: "-amount",
      })
    );
    expect(screen.getByRole("link", { name: "Engine Expansion" })).toHaveAttribute(
      "href",
      `/crm/opportunities/${opportunity.id}`
    );
    expect(screen.getByText("Page total: $125,000.00")).toBeInTheDocument();
    expect(screen.getByText("45%")).toBeInTheDocument();
  });

  it("passes activity list filters and highlights overdue open work without fabricating completion", async () => {
    vi.mocked(crmService.listActivities).mockResolvedValue(page([activity]));
    renderRoute(
      `/crm/activities?related_to_type=Opportunity&related_to_id=${opportunity.id}&activity_type=task&completed=false&owner_id=owner-1`,
      "/crm/activities",
      <ActivityListPage />
    );

    expect(await screen.findByRole("heading", { name: "Activities" })).toBeInTheDocument();
    await waitFor(() =>
      expect(crmService.listActivities).toHaveBeenCalledWith({
        related_to_type: "Opportunity",
        related_to_id: opportunity.id,
        activity_type: "task",
        owner_id: "owner-1",
        completed: false,
        due_from: undefined,
        due_to: undefined,
        page: 1,
        page_size: 25,
        ordering: undefined,
      })
    );
    expect(screen.getByRole("link", { name: "Send technical proposal" })).toHaveAttribute(
      "href",
      `/crm/activities/${activity.id}`
    );
    const activityRow = screen.getByRole("row", { name: /Send technical proposal/u });
    expect(within(activityRow).getByText(/Overdue/u)).toBeInTheDocument();
    expect(within(activityRow).getByText("Open")).toBeInTheDocument();
  });

  it("passes lead, account, and contact list URL filters to governed services", async () => {
    const leadRender = renderRoute(
      "/crm/leads?search=ada&status=qualified&source=referral&score_min=85&page=2&ordering=-score",
      "/crm/leads",
      <LeadListPage />
    );

    expect(await screen.findByRole("heading", { name: "Leads" })).toBeInTheDocument();
    await waitFor(() =>
      expect(crmService.listLeads).toHaveBeenCalledWith({
        search: "ada",
        status: "qualified",
        source: "referral",
        score_min: 85,
        page: 2,
        page_size: 25,
        ordering: "-score",
      })
    );
    expect(screen.getByRole("link", { name: "Ada Lovelace" })).toHaveAttribute(
      "href",
      `/crm/leads/${lead.id}`
    );
    leadRender.unmount();

    const accountRender = renderRoute(
      "/crm/accounts?search=analytical&account_type=customer&parent_account_id=root&industry=Manufacturing&page=3&ordering=name",
      "/crm/accounts",
      <AccountListPage />
    );

    expect(await screen.findByRole("heading", { name: "Accounts" })).toBeInTheDocument();
    await waitFor(() =>
      expect(crmService.listAccounts).toHaveBeenCalledWith({
        search: "analytical",
        account_type: "customer",
        parent_account_id: "root",
        industry: "Manufacturing",
        page: 3,
        page_size: 25,
        ordering: "name",
      })
    );
    expect(screen.getByRole("link", { name: "Analytical" })).toHaveAttribute(
      "href",
      `/crm/accounts/${account.id}`
    );
    accountRender.unmount();

    vi.mocked(crmService.listContacts).mockResolvedValue(page([contact]));
    renderRoute(
      `/crm/contacts?search=grace&account_id=${account.id}&owner_id=owner-1&engagement_min=70&page=4&ordering=-engagement_score`,
      "/crm/contacts",
      <ContactListPage />
    );

    expect(await screen.findByRole("heading", { name: "Contacts" })).toBeInTheDocument();
    await waitFor(() =>
      expect(crmService.listContacts).toHaveBeenCalledWith({
        search: "grace",
        account_id: account.id,
        owner_id: "owner-1",
        engagement_min: 70,
        page: 4,
        page_size: 25,
        ordering: "-engagement_score",
      })
    );
    expect(screen.getByRole("link", { name: "Grace Hopper" })).toHaveAttribute(
      "href",
      `/crm/contacts/${contact.id}`
    );
  });

  it("renders contact and activity detail wrappers with versioned mutations", async () => {
    const user = userEvent.setup();
    vi.mocked(crmService.listActivities).mockResolvedValue(page([activity]));
    renderRoute(`/crm/contacts/${contact.id}`, "/crm/contacts/:id", <ContactDetailPage />);

    expect(await screen.findByRole("heading", { name: "Grace Hopper" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open account" })).toHaveAttribute(
      "href",
      `/crm/accounts/${account.id}`
    );
    expect(screen.getByRole("link", { name: "grace@example.test" })).toHaveAttribute(
      "href",
      "mailto:grace@example.test"
    );
    expect(screen.getByRole("link", { name: "Log activity" })).toHaveAttribute(
      "href",
      `/crm/activities/new?related_to_type=Contact&related_to_id=${contact.id}`
    );
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(await screen.findByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(crmService.deleteContact).toHaveBeenCalledWith(contact.id, 4));
    cleanup();

    renderRoute(`/crm/activities/${activity.id}`, "/crm/activities/:id", <ActivityDetailPage />);
    expect(
      await screen.findByRole("heading", { name: "Send technical proposal" })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Opportunity" })).toHaveAttribute(
      "href",
      `/crm/opportunitys/${opportunity.id}`
    );
    await user.click(screen.getByRole("button", { name: "Mark complete" }));
    await waitFor(() => expect(crmService.completeActivity).toHaveBeenCalled());
    const completeCall = vi.mocked(crmService.completeActivity).mock.calls[0];
    expect(completeCall?.[0]).toBe(activity.id);
    expect(completeCall?.[1].expected_version).toBe(2);
    expect("idempotency_key" in (completeCall?.[1] ?? {})).toBe(true);
    expect((completeCall?.[1] as { idempotency_key: string } | undefined)?.idempotency_key).toMatch(
      /^activity-complete-/u
    );
  });

  it("renders configuration-driven score bands and collapsible account hierarchy", async () => {
    const user = userEvent.setup();
    renderWithClient(
      <>
        <LeadScoreIndicator lead={{ ...lead, score: 90, grade: "A" }} showTrend />
        <AccountHierarchyTree hierarchy={accountHierarchy} />
      </>
    );

    expect(screen.getByText("90")).toBeInTheDocument();
    expect(screen.getByText("Grade A")).toBeInTheDocument();
    expect(screen.getByText("Account Hierarchy")).toBeInTheDocument();
    expect(screen.getByText("1 child account(s)")).toBeInTheDocument();
    expect(screen.getByText("Analytical Services")).toBeInTheDocument();
    await user.click(screen.getByText("Analytical"));
    expect(screen.queryByText("Analytical Services")).not.toBeInTheDocument();
  });

  it("drives EntityList URL filters, ordering, empty reset, and page-local selection", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    renderWithClient(
      <EntityList
        title="Leads"
        description="Qualified lead list"
        createPath="/crm/leads/new"
        emptyTitle="No leads yet"
        emptyDescription="Create a governed lead."
        selectable
        filters={[
          { key: "status", label: "Status", choices: [{ value: "qualified", label: "Qualified" }] },
        ]}
        columns={[
          {
            key: "last_name",
            label: "Last name",
            sortable: true,
            render: (item: Lead) => item.last_name,
          },
          { key: "email", label: "Email", render: (item: Lead) => item.email },
        ]}
        query={page([lead])}
        isLoading={false}
        error={null}
        refetch={refetch}
      />
    );

    await user.type(screen.getByPlaceholderText("Search leads…"), "ada");
    await waitFor(() =>
      expect(screen.getByLabelText("location-search")).toHaveTextContent("search=ada")
    );
    await user.selectOptions(screen.getByLabelText("Status"), "qualified");
    expect(screen.getByLabelText("location-search")).toHaveTextContent("status=qualified");
    await user.click(screen.getByRole("button", { name: "Last name" }));
    expect(screen.getByLabelText("location-search")).toHaveTextContent("ordering=last_name");
    await user.click(screen.getByLabelText("Select all on this page"));
    expect(screen.getByText(/1 selected/u)).toBeInTheDocument();
  });
});
