import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Company,
  CompanyAccessGrant,
  CompanyHierarchy,
  CompanyRole,
  ConfigurationVersion,
  ConsolidationRun,
  ExtensionCatalogEntry,
  IntercompanyTransaction,
  MutableFields,
  ReconciliationRow,
  TransferPricingRule,
  UUID,
} from "../contracts";
import { multiCompanyService } from "../services/multi-company-service";
import {
  CompanyAccessPage,
  CompanyDetailPage,
  CompanyHierarchyPage,
  CompanyListPage,
  ConfigurationVersionListPage,
  ConsolidationRunListPage,
  CreateCompanyPage,
  EditCompanyPage,
  ReconciliationPage,
  TransactionListPage,
  TransferPricingRuleListPage,
} from "./workspaces";

const toast = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}));

const assign = vi.fn();

vi.mock("sonner", () => ({ toast }));

vi.mock("../services/multi-company-service", () => ({
  multiCompanyService: {
    createCompany: vi.fn(),
    deactivateCompany: vi.fn(),
    deleteCompany: vi.fn(),
    getCompany: vi.fn(),
    getHierarchy: vi.fn(),
    grantAccess: vi.fn(),
    getExtensionCatalog: vi.fn(),
    getReconciliation: vi.fn(),
    listAccessGrants: vi.fn(),
    listCompanies: vi.fn(),
    listConfigurationVersions: vi.fn(),
    listConsolidations: vi.fn(),
    listTransactions: vi.fn(),
    listTransferPricingRules: vi.fn(),
    revokeAccess: vi.fn(),
    updateCompany: vi.fn(),
  },
}));

function renderPage(
  element: React.ReactNode,
  {
    path = "/multi-company/companies",
    route = "/multi-company/companies",
  }: { path?: string; route?: string } = {}
) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={element} />
          <Route path="*" element={<div data-testid="navigated" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function page<T>(data: readonly T[], overrides = {}) {
  return {
    data,
    meta: { correlation_id: "corr-page", timestamp: "2026-07-23T00:00:00Z" },
    pagination: {
      count: data.length,
      page: 1,
      page_size: 25,
      total_pages: data.length ? 1 : 0,
      has_next: false,
      has_previous: false,
      ...overrides,
    },
  };
}

function mutable(overrides: Partial<MutableFields> = {}): MutableFields {
  return {
    id: "company-1",
    created_at: "2026-07-01T00:00:00Z",
    created_by: "controller",
    updated_at: "2026-07-02T00:00:00Z",
    updated_by: "controller",
    version: 7,
    is_deleted: false,
    deleted_at: null,
    correlation_id: "corr-company",
    ...overrides,
  };
}

function company(overrides: Partial<Company> = {}): Company {
  return {
    ...mutable(),
    allowed_commands: ["update", "deactivate"],
    denial_reasons: {},
    company_code: "ACME",
    company_name: "Acme Holding",
    legal_name: "Acme Holding LLC",
    tax_id: "TAX-123",
    currency: "USD",
    fiscal_year_start_month: 4,
    parent_company: null,
    parent_company_name: null,
    consolidation_group: "GLOBAL",
    ownership_percentage: "100.00",
    address: "1 Main Street",
    is_active: true,
    is_holding: true,
    ...overrides,
  };
}

function accessGrant(overrides: Partial<CompanyAccessGrant> = {}): CompanyAccessGrant {
  return {
    ...mutable({ id: "grant-1" }),
    allowed_commands: ["revoke"],
    denial_reasons: {},
    company: "company-1",
    company_name: "Acme Holding",
    subject_id: "user-123",
    role: "controller",
    valid_from: "2026-07-01T00:00:00Z",
    valid_until: null,
    granted_by: "admin",
    revoked_by: "",
    revoked_at: null,
    ...overrides,
  };
}

function transaction(overrides: Partial<IntercompanyTransaction> = {}): IntercompanyTransaction {
  return {
    ...mutable({ id: "txn-1", correlation_id: "corr-transaction" }),
    allowed_commands: ["update", "submit"],
    denial_reasons: {},
    reference: "ICT-001",
    source_company: "company-1",
    source_company_name: "Acme Holding",
    target_company: "company-2",
    target_company_name: "Subsidiary",
    transaction_type: "cost_allocation",
    product_category: "shared services",
    original_amount: "1000.00",
    amount: "1100.00",
    currency: "USD",
    exchange_rate: "1.10",
    target_amount: "1100.00",
    description: "Shared service recharge",
    transaction_date: "2026-07-01",
    status: "draft",
    transfer_pricing_rule: null,
    transfer_pricing_snapshot: null,
    source_journal_id: null,
    target_journal_id: null,
    posted_date: null,
    cancellation_reason: "",
    dispute_reason: "",
    failure_code: "",
    failure_detail: "",
    job_id: null,
    transition_history: [],
    approvals: [],
    ...overrides,
  };
}

function reconciliationRow(overrides: Partial<ReconciliationRow> = {}): ReconciliationRow {
  return {
    transaction_id: "txn-1",
    reference: "ICT-001",
    source_company_id: "company-1",
    target_company_id: "company-2",
    currency: "USD",
    source_amount: "1000.00",
    target_amount: null,
    variance: "1000.00",
    status: "posted",
    ...overrides,
  };
}

function consolidation(overrides: Partial<ConsolidationRun> = {}): ConsolidationRun {
  return {
    ...mutable({ id: "run-1", correlation_id: "corr-consolidation" }),
    allowed_commands: ["execute"],
    denial_reasons: {},
    name: "July close",
    consolidation_group: "GLOBAL",
    period_start: "2026-07-01",
    period_end: "2026-07-31",
    reporting_currency: "USD",
    translation_method: "current_rate",
    status: "draft",
    total_companies: 4,
    total_eliminations: 2,
    elimination_total: "500.00",
    minority_interest_total: "125.00",
    job_id: null,
    started_at: null,
    completed_at: null,
    approved_at: null,
    published_at: null,
    approved_by: "",
    published_by: "",
    failure_code: "",
    failure_step: "",
    failure_detail: "",
    report_snapshot: null,
    transition_history: [],
    ...overrides,
  };
}

function pricingRule(overrides: Partial<TransferPricingRule> = {}): TransferPricingRule {
  return {
    ...mutable({ id: "rule-1", correlation_id: "corr-pricing" }),
    allowed_commands: ["update"],
    denial_reasons: {},
    rule_key: "rule-key-1",
    rule_version: 3,
    name: "Shared services markup",
    source_company: "company-1",
    target_company: "company-2",
    product_category: "shared services",
    transaction_type: "service",
    pricing_method: "cost_plus",
    extension_key: "",
    markup_percentage: "10.00",
    margin_range_min: null,
    margin_range_max: null,
    parameters: { base_cost: "1000.00" },
    effective_from: "2026-07-01",
    effective_to: null,
    is_active: true,
    documentation: "OECD support retained",
    supersedes: null,
    ...overrides,
  };
}

function extension(overrides: Partial<ExtensionCatalogEntry> = {}): ExtensionCatalogEntry {
  return {
    key: "industry-cost-plus",
    version: "1.2.0",
    spi_version: "2026.1",
    installed: true,
    entitled: true,
    feature_enabled: true,
    access_allowed: true,
    compatible: true,
    healthy: true,
    available: true,
    locked: false,
    unavailable_reason: "",
    ...overrides,
  };
}

function configuration(overrides: Partial<ConfigurationVersion> = {}): ConfigurationVersion {
  return {
    id: "config-1",
    created_at: "2026-07-01T00:00:00Z",
    created_by: "platform-admin",
    correlation_id: "corr-configuration",
    allowed_commands: ["activate"],
    denial_reasons: {},
    environment: "development",
    version: 4,
    status: "draft",
    schema_version: "2026.7",
    settings: {
      draft_expiry_hours: 48,
      minimum_consolidation_company_count: 2,
      permitted_translation_methods: ["current_rate", "temporal"],
      permitted_transaction_types: ["sale", "service"],
      permitted_pricing_methods: ["cost_plus"],
      maximum_transaction_amount_by_currency: { USD: "100000.00" },
      approval_sides: ["source", "target"],
      transfer_pricing_tolerance_min: "0.00",
      transfer_pricing_tolerance_max: "20.00",
      allow_consolidation_overlap: false,
      rounding_mode: "ROUND_HALF_EVEN",
      money_precision: 2,
      feature_flags: { multi_company: true },
      rollout: { roles: ["controller"], cohorts: ["default"] },
      extension_enablement_keys: [],
      notification_policy: {
        approval: true,
        dispute: true,
        failure: true,
        completion: true,
      },
      job_max_retries: 3,
      job_timeout_seconds: 900,
      default_currency: "USD",
      default_fiscal_year_start_month: 1,
      ledger_accounts: {
        intercompany_receivable: "1200",
        intercompany_payable: "2100",
        intercompany_revenue: "4100",
        intercompany_expense: "5100",
      },
      elimination_accounts: { debit: "9000", credit: "9001" },
    },
    change_summary: "Tighten multi-company defaults",
    supersedes: null,
    activated_by: "",
    activated_at: null,
    ...overrides,
  };
}

describe("CompanyListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, assign },
    });
  });

  it("teaches a new tenant how to begin when the governed result is empty", async () => {
    vi.mocked(multiCompanyService.listCompanies).mockResolvedValue(page([]));

    renderPage(<CompanyListPage />);

    expect(
      await screen.findByRole("heading", { name: "Build your company structure" })
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Create company" })).toHaveLength(2);
  });

  it("renders governed company rows with fallbacks and pagination controls", async () => {
    vi.mocked(multiCompanyService.listCompanies).mockResolvedValue(
      page(
        [
          company(),
          company({
            id: "company-2",
            company_code: "SUB",
            company_name: "Subsidiary",
            consolidation_group: "",
            is_active: false,
            parent_company_name: "Acme Holding",
          }),
        ],
        { count: 55, total_pages: 3, has_next: true }
      )
    );

    renderPage(<CompanyListPage />, { route: "/multi-company/companies?page=2&search= acme " });

    expect(await screen.findByRole("link", { name: "ACME · Acme Holding" })).toHaveAttribute(
      "href",
      "/multi-company/companies/company-1"
    );
    expect(screen.getByRole("link", { name: "SUB · Subsidiary" })).toBeInTheDocument();
    expect(screen.getByText("Top level")).toBeInTheDocument();
    expect(screen.getByText("Ungrouped")).toBeInTheDocument();
    expect(screen.getByText("inactive")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 3 · 55 records")).toBeInTheDocument();
    expect(vi.mocked(multiCompanyService.listCompanies)).toHaveBeenCalledWith({
      page: 2,
      page_size: 25,
      search: " acme ",
      ordering: undefined,
    });
  });

  it("updates query parameters through search, clear, and next page actions", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.listCompanies).mockResolvedValue(
      page([company()], { count: 50, total_pages: 2, has_next: true })
    );

    renderPage(<CompanyListPage />, { route: "/multi-company/companies?search=legacy" });

    const search = await screen.findByLabelText("Search");
    await user.clear(search);
    await user.type(search, "  apex  ");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() =>
      expect(vi.mocked(multiCompanyService.listCompanies)).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 25,
        search: "apex",
        ordering: undefined,
      })
    );

    await user.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() =>
      expect(vi.mocked(multiCompanyService.listCompanies)).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 25,
        search: undefined,
        ordering: undefined,
      })
    );

    await user.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() =>
      expect(vi.mocked(multiCompanyService.listCompanies)).toHaveBeenLastCalledWith({
        page: 2,
        page_size: 25,
        search: undefined,
        ordering: undefined,
      })
    );
  });

  it("surfaces governed list failures and retries through the same service", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.listCompanies)
      .mockRejectedValueOnce(new Error("service unavailable"))
      .mockResolvedValueOnce(page([company()]));

    renderPage(<CompanyListPage />);

    expect(await screen.findByText("The request could not be completed.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /try again/i }));

    expect(await screen.findByRole("link", { name: "ACME · Acme Holding" })).toBeInTheDocument();
    expect(vi.mocked(multiCompanyService.listCompanies)).toHaveBeenCalledTimes(2);
  });
});

describe("financial workspace lists", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders transaction rows with named-company fallback behavior", async () => {
    vi.mocked(multiCompanyService.listTransactions).mockResolvedValue(
      page([
        transaction(),
        transaction({
          id: "txn-2",
          reference: "ICT-002",
          source_company_name: undefined,
          target_company_name: undefined,
          source_company: "source-raw",
          target_company: "target-raw",
          transaction_type: "sale",
          status: "posted",
        }),
      ])
    );

    renderPage(<TransactionListPage />, {
      path: "/multi-company/transactions",
      route: "/multi-company/transactions",
    });

    expect(await screen.findByRole("link", { name: "ICT-001" })).toHaveAttribute(
      "href",
      "/multi-company/transactions/txn-1"
    );
    const rows = screen.getAllByRole("row");
    expect(rows.some((row) => row.textContent?.includes("Acme Holding→Subsidiary"))).toBe(true);
    expect(rows.some((row) => row.textContent?.includes("source-raw→target-raw"))).toBe(true);
    expect(screen.getByText("cost allocation")).toBeInTheDocument();
    expect(screen.getByText("posted")).toBeInTheDocument();
  });

  it("renders reconciliation rows with pending reciprocal amounts", async () => {
    vi.mocked(multiCompanyService.getReconciliation).mockResolvedValue(
      page([
        reconciliationRow(),
        reconciliationRow({
          transaction_id: "txn-2",
          reference: "ICT-002",
          target_amount: "995.00",
          variance: "5.00",
        }),
      ])
    );

    renderPage(<ReconciliationPage />, {
      path: "/multi-company/reconciliation",
      route: "/multi-company/reconciliation",
    });

    expect(await screen.findByText("ICT-001")).toBeInTheDocument();
    expect(screen.getAllByText("company-1 ↔ company-2")).toHaveLength(2);
    expect(screen.getByText("Pending reciprocal amount")).toBeInTheDocument();
    expect(screen.getByText("USD 995.00")).toBeInTheDocument();
    expect(screen.getByText("USD 5.00")).toBeInTheDocument();
  });

  it("renders consolidation rows with group period and command status", async () => {
    vi.mocked(multiCompanyService.listConsolidations).mockResolvedValue(
      page([consolidation({ status: "queued" })])
    );

    renderPage(<ConsolidationRunListPage />, {
      path: "/multi-company/consolidations",
      route: "/multi-company/consolidations",
    });

    expect(await screen.findByRole("link", { name: "July close" })).toHaveAttribute(
      "href",
      "/multi-company/consolidations/run-1"
    );
    expect(screen.getByText("GLOBAL")).toBeInTheDocument();
    expect(screen.getByText("2026-07-01 – 2026-07-31")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("queued")).toBeInTheDocument();
  });
});

describe("financial policy lists", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders transfer pricing catalog states and rule effective-date fallbacks", async () => {
    vi.mocked(multiCompanyService.getExtensionCatalog).mockResolvedValue({
      data: [
        extension(),
        extension({
          key: "locked-provider",
          available: false,
          unavailable_reason: "license_required",
        }),
      ],
      meta: { correlation_id: "corr-extension", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.listTransferPricingRules).mockResolvedValue(
      page([
        pricingRule(),
        pricingRule({
          id: "rule-2",
          name: "Inactive resale",
          rule_version: 1,
          pricing_method: "resale_minus",
          effective_to: "2026-12-31",
          is_active: false,
        }),
      ])
    );

    renderPage(<TransferPricingRuleListPage />, {
      path: "/multi-company/transfer-pricing",
      route: "/multi-company/transfer-pricing",
    });

    expect(await screen.findByText("industry-cost-plus")).toBeInTheDocument();
    expect(screen.getByText("available")).toBeInTheDocument();
    expect(screen.getByText("locked-provider")).toBeInTheDocument();
    expect(screen.getByText("license required")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Shared services markup/ })).toHaveAttribute(
      "href",
      "/multi-company/transfer-pricing/rule-1"
    );
    expect(screen.getByText("2026-07-01 – ongoing")).toBeInTheDocument();
    expect(screen.getByText("2026-07-01 – 2026-12-31")).toBeInTheDocument();
    expect(screen.getByText("inactive")).toBeInTheDocument();
  });

  it("filters configuration versions by selected runtime environment", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.listConfigurationVersions).mockResolvedValue(
      page([configuration()])
    );

    renderPage(<ConfigurationVersionListPage />, {
      path: "/multi-company/settings",
      route: "/multi-company/settings",
    });

    expect(await screen.findByRole("link", { name: "v4" })).toHaveAttribute(
      "href",
      "/multi-company/settings/config-1"
    );
    expect(vi.mocked(multiCompanyService.listConfigurationVersions)).toHaveBeenLastCalledWith({
      environment: "development",
      ordering: undefined,
      page: 1,
      page_size: 25,
      search: undefined,
    });

    await user.selectOptions(screen.getByLabelText("Runtime environment"), "production");

    await waitFor(() =>
      expect(vi.mocked(multiCompanyService.listConfigurationVersions)).toHaveBeenLastCalledWith({
        environment: "production",
        ordering: undefined,
        page: 1,
        page_size: 25,
        search: undefined,
      })
    );
  });
});

describe("CompanyDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "transition-key" });
  });

  it("stops invalid detail routes before calling the API", () => {
    renderPage(<CompanyDetailPage />, {
      path: "/multi-company/companies",
      route: "/multi-company/companies",
    });

    expect(screen.getByRole("heading", { name: "Invalid route" })).toBeInTheDocument();
    expect(multiCompanyService.getCompany).not.toHaveBeenCalled();
  });

  it("renders command prerequisites and applies the deactivate command with version evidence", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.getCompany).mockResolvedValue({
      data: company({
        denial_reasons: { delete: "pending_transactions" },
      }),
      meta: { correlation_id: "corr-detail", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.deactivateCompany).mockResolvedValue({
      data: company({ is_active: false }),
      meta: { correlation_id: "corr-deactivate", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<CompanyDetailPage />, {
      path: "/multi-company/companies/:id",
      route: "/multi-company/companies/company-1",
    });

    expect(await screen.findByRole("heading", { name: "ACME · Acme Holding" })).toBeInTheDocument();
    expect(screen.getByText(/delete:/i)).toBeInTheDocument();
    expect(screen.getByText(/pending transactions/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    await user.click(screen.getByRole("button", { name: "Apply lifecycle change" }));

    await waitFor(() =>
      expect(multiCompanyService.deactivateCompany).toHaveBeenCalledWith("company-1", {
        expected_version: 7,
        transition_key: "transition-key",
      })
    );
    expect(toast.success).toHaveBeenCalledWith("Company lifecycle updated");
  });

  it("hides edit and lifecycle commands when the governed command set denies them", async () => {
    vi.mocked(multiCompanyService.getCompany).mockResolvedValue({
      data: company({ allowed_commands: [] }),
      meta: { correlation_id: "corr-detail", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<CompanyDetailPage />, {
      path: "/multi-company/companies/:id",
      route: "/multi-company/companies/company-1",
    });

    expect(await screen.findByRole("heading", { name: "ACME · Acme Holding" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
  });
});

describe("CompanyFormPage constraints", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "create-key" });
  });

  it("marks company identity and fiscal controls with native constraints", () => {
    renderPage(<CreateCompanyPage />, {
      path: "/multi-company/companies/new",
      route: "/multi-company/companies/new",
    });

    expect(screen.getByLabelText("Company code")).toBeRequired();
    expect(screen.getByLabelText("Company code")).toHaveAttribute(
      "pattern",
      "\\s*[A-Za-z0-9_-]+\\s*"
    );
    expect(screen.getByLabelText("Display name")).toBeRequired();
    expect(screen.getByLabelText("Legal name")).toBeRequired();
    expect(screen.getByLabelText("Functional currency")).toBeRequired();
    expect(screen.getByLabelText("Functional currency")).toHaveAttribute(
      "pattern",
      "\\s*[A-Za-z]{3}\\s*"
    );
    expect(screen.getByLabelText("Fiscal year start month")).toBeRequired();
    expect(screen.getByLabelText("Fiscal year start month")).toHaveAttribute("min", "1");
    expect(screen.getByLabelText("Fiscal year start month")).toHaveAttribute("max", "12");
    expect(screen.getByLabelText("Ownership percentage")).toHaveAttribute("min", "0");
    expect(screen.getByLabelText("Ownership percentage")).toHaveAttribute("max", "100");
  });
});

describe("CompanyFormPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "create-key" });
  });

  it("rejects invalid create input before sending a mutation", async () => {
    const user = userEvent.setup();

    renderPage(<CreateCompanyPage />, {
      path: "/multi-company/companies/new",
      route: "/multi-company/companies/new",
    });

    await user.click(screen.getByRole("button", { name: "Create company" }));
    expect(multiCompanyService.createCompany).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Functional currency"));
    await user.type(screen.getByLabelText("Functional currency"), "US");
    await user.click(screen.getByRole("button", { name: "Create company" }));

    expect(multiCompanyService.createCompany).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Functional currency")).toBeInvalid();
  });

  it("normalizes create payload values and preserves optional null boundaries", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.createCompany).mockResolvedValue({
      data: company({ id: "created-company" }),
      meta: { correlation_id: "corr-create", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<CreateCompanyPage />, {
      path: "/multi-company/companies/new",
      route: "/multi-company/companies/new",
    });

    await user.type(screen.getByLabelText("Company code"), " apex ");
    await user.type(screen.getByLabelText("Display name"), " Apex India ");
    await user.type(screen.getByLabelText("Legal name"), " Apex India Pvt Ltd ");
    await user.clear(screen.getByLabelText("Functional currency"));
    await user.type(screen.getByLabelText("Functional currency"), " inr ");
    await user.clear(screen.getByLabelText("Fiscal year start month"));
    await user.type(screen.getByLabelText("Fiscal year start month"), "4");
    await user.type(screen.getByLabelText("Consolidation group"), " APAC ");
    await user.type(screen.getByLabelText("Address"), " Bengaluru ");
    await user.click(screen.getByLabelText("Holding company"));
    await user.click(screen.getByRole("button", { name: "Create company" }));

    await waitFor(() =>
      expect(multiCompanyService.createCompany).toHaveBeenCalledWith({
        company_code: "APEX",
        company_name: "Apex India",
        legal_name: "Apex India Pvt Ltd",
        tax_id: undefined,
        currency: "INR",
        fiscal_year_start_month: 4,
        parent_company_id: null,
        consolidation_group: "APAC",
        ownership_percentage: null,
        address: "Bengaluru",
        is_holding: true,
        idempotency_key: "create-key",
      })
    );
    expect(toast.success).toHaveBeenCalledWith("Company created");
  });

  it("hydrates edit state and submits expected version for concurrency control", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.getCompany).mockResolvedValue({
      data: company({ company_name: "Existing Company", version: 11 }),
      meta: { correlation_id: "corr-edit", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.updateCompany).mockResolvedValue({
      data: company({ company_name: "Renamed Company", version: 12 }),
      meta: { correlation_id: "corr-update", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<EditCompanyPage />, {
      path: "/multi-company/companies/:id/edit",
      route: "/multi-company/companies/company-1/edit",
    });

    const name = await screen.findByLabelText("Display name");
    expect(name).toHaveValue("Existing Company");
    await user.clear(name);
    await user.type(name, "Renamed Company");
    await user.click(screen.getByRole("button", { name: "Save new version" }));

    await waitFor(() =>
      expect(multiCompanyService.updateCompany).toHaveBeenCalledWith(
        "company-1",
        expect.objectContaining({
          company_name: "Renamed Company",
          expected_version: 11,
        })
      )
    );
    expect(toast.success).toHaveBeenCalledWith("Company updated");
  });
});

describe("CompanyHierarchyPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders nested hierarchy records with active and inactive states", async () => {
    const hierarchy: CompanyHierarchy = [
      {
        id: "parent",
        company_code: "PARENT",
        company_name: "Parent Company",
        is_active: true,
        depth: 0,
        children: [
          {
            id: "child",
            company_code: "CHILD",
            company_name: "Child Company",
            is_active: false,
            depth: 1,
            children: [],
          },
        ],
      },
    ];
    vi.mocked(multiCompanyService.getHierarchy).mockResolvedValue({
      data: hierarchy,
      meta: { correlation_id: "corr-hierarchy", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<CompanyHierarchyPage />, {
      path: "/multi-company/companies/hierarchy",
      route: "/multi-company/companies/hierarchy",
    });

    expect(await screen.findByRole("link", { name: "Parent Company" })).toHaveAttribute(
      "href",
      "/multi-company/companies/parent"
    );
    expect(screen.getByRole("link", { name: "Child Company" })).toHaveAttribute(
      "href",
      "/multi-company/companies/child"
    );
    expect(screen.getByText(/CHILD · Inactive/)).toBeInTheDocument();
  });

  it("renders empty and error hierarchy states", async () => {
    const { unmount } = renderPage(<CompanyHierarchyPage />, {
      path: "/multi-company/companies/hierarchy",
      route: "/multi-company/companies/hierarchy",
    });
    vi.mocked(multiCompanyService.getHierarchy).mockResolvedValue({
      data: [],
      meta: { correlation_id: "corr-empty-hierarchy", timestamp: "2026-07-23T00:00:00Z" },
    });
    unmount();

    renderPage(<CompanyHierarchyPage />, {
      path: "/multi-company/companies/hierarchy",
      route: "/multi-company/companies/hierarchy",
    });
    expect(await screen.findByRole("heading", { name: "No hierarchy yet" })).toBeInTheDocument();

    vi.mocked(multiCompanyService.getHierarchy).mockRejectedValueOnce(new Error("boom"));
    renderPage(<CompanyHierarchyPage />, {
      path: "/multi-company/companies/hierarchy",
      route: "/multi-company/companies/hierarchy",
    });
    expect(await screen.findByText("The request could not be completed.")).toBeInTheDocument();
  });
});

describe("CompanyAccessPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requires a route id before loading access grants", () => {
    renderPage(<CompanyAccessPage />, {
      path: "/multi-company/companies/access",
      route: "/multi-company/companies/access",
    });

    expect(screen.getByRole("heading", { name: "Invalid route" })).toBeInTheDocument();
    expect(multiCompanyService.listAccessGrants).not.toHaveBeenCalled();
  });

  it("validates subject input before granting access", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.listAccessGrants).mockResolvedValue(page([]));

    renderPage(<CompanyAccessPage />, {
      path: "/multi-company/companies/:id/access",
      route: "/multi-company/companies/company-1/access",
    });

    await screen.findByRole("heading", { name: "No direct grants" });
    await user.click(screen.getByRole("button", { name: "Grant access" }));

    expect(multiCompanyService.grantAccess).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("Subject ID is required");
  });

  it("grants and revokes company access with operator-selected role", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.listAccessGrants).mockResolvedValue(page([accessGrant()]));
    vi.mocked(multiCompanyService.grantAccess).mockResolvedValue({
      data: accessGrant({ id: "grant-2", subject_id: "service-42", role: "operator" }),
      meta: { correlation_id: "corr-grant", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.revokeAccess).mockResolvedValue({
      data: accessGrant({ revoked_at: "2026-07-24T00:00:00Z" }),
      meta: { correlation_id: "corr-revoke", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<CompanyAccessPage />, {
      path: "/multi-company/companies/:id/access",
      route: "/multi-company/companies/company-1/access",
    });

    expect(await screen.findByText("user-123")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Subject identifier"), "service-42");
    await user.selectOptions(
      screen.getByLabelText("Company role"),
      "operator" satisfies CompanyRole
    );
    await user.click(screen.getByRole("button", { name: "Grant access" }));

    await waitFor(() =>
      expect(multiCompanyService.grantAccess).toHaveBeenCalledWith(
        expect.objectContaining({
          company_id: "company-1" as UUID,
          subject_id: "service-42",
          role: "operator",
        })
      )
    );
    expect(toast.success).toHaveBeenCalledWith("Company access granted");

    const grantRow = screen.getByText("user-123").closest("tr");
    expect(grantRow).not.toBeNull();
    await user.click(within(grantRow!).getByRole("button", { name: "Revoke" }));
    await user.click(screen.getByRole("button", { name: "Revoke access" }));

    await waitFor(() =>
      expect(multiCompanyService.revokeAccess).toHaveBeenCalledWith(
        "grant-1",
        "Revoked by an administrator from the company access workspace"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("Access revoked with audit evidence");
  });

  it("disables already revoked grants", async () => {
    vi.mocked(multiCompanyService.listAccessGrants).mockResolvedValue(
      page([accessGrant({ revoked_at: "2026-07-24T00:00:00Z" })])
    );

    renderPage(<CompanyAccessPage />, {
      path: "/multi-company/companies/:id/access",
      route: "/multi-company/companies/company-1/access",
    });

    expect(await screen.findByRole("button", { name: "Revoked" })).toBeDisabled();
  });
});
