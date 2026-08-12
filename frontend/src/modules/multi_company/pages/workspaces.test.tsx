/* eslint-disable max-lines-per-function -- multi-company workspace coverage matrix intentionally keeps related governed flows in one file. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  Company,
  CompanyAccessGrant,
  CompanyHierarchy,
  CompanyRole,
  ConfigurationCreateRequest,
  ConfigurationUpdateRequest,
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
  ConfigurationVersionDetailPage,
  CreateConfigurationVersionPage,
  CreateConsolidationRunPage,
  EditConfigurationVersionPage,
  ConsolidationRunListPage,
  ConsolidationRunDetailPage,
  CreateManualEliminationPage,
  CreateTransactionPage,
  CreateCompanyPage,
  EliminationDetailPage,
  EliminationListPage,
  EditCompanyPage,
  ReconciliationPage,
  TransactionDetailPage,
  TransactionListPage,
  CreateTransferPricingRulePage,
  TransferPricingSimulatorPage,
  TransferPricingRuleDetailPage,
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
    getTransaction: vi.fn(),
    submitTransaction: vi.fn(),
    postTransaction: vi.fn(),
    cancelTransaction: vi.fn(),
    createTransaction: vi.fn(),
    updateTransaction: vi.fn(),
    getConsolidation: vi.fn(),
    executeConsolidation: vi.fn(),
    approveConsolidation: vi.fn(),
    publishConsolidation: vi.fn(),
    createConsolidation: vi.fn(),
    updateConsolidation: vi.fn(),
    listEliminations: vi.fn(),
    getElimination: vi.fn(),
    createElimination: vi.fn(),
    getTransferPricingRule: vi.fn(),
    createTransferPricingRule: vi.fn(),
    updateTransferPricingRule: vi.fn(),
    previewTransferPrices: vi.fn(),
    importConfiguration: vi.fn(),
    getConfigurationVersion: vi.fn(),
    previewConfiguration: vi.fn(),
    activateConfiguration: vi.fn(),
    rollbackConfiguration: vi.fn(),
    exportConfiguration: vi.fn(),
    createConfigurationVersion: vi.fn(),
    updateConfigurationVersion: vi.fn(),
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

function elimination(overrides: Record<string, unknown> = {}) {
  return {
    id: "elim-1",
    consolidation_run: "run-1",
    sequence: 4,
    elimination_type: "intercompany_balance",
    source_company: "company-1",
    target_company: "company-2",
    debit_account: "9000",
    credit_account: "9001",
    amount: "250.00",
    currency: "USD",
    source_transaction: "txn-1",
    rule_key: "rule-key-1",
    is_auto_generated: false,
    description: "Manual true-up",
    created_by: "controller",
    created_at: "2026-07-21T00:00:00Z",
    correlation_id: "corr-elimination",
    ...overrides,
  } as never;
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

describe("transaction, consolidation, pricing, and configuration workspaces", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => "mc-key" });
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, assign },
    });
  });

  it("executes transaction detail commands with versioned transition and posting idempotency keys", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.getTransaction).mockResolvedValue({
      data: transaction({
        allowed_commands: ["update", "submit", "post", "cancel"],
        approvals: [
          {
            id: "approval-1",
            transaction: "txn-1",
            side: "source",
            attempt: 1,
            approver_id: "controller",
            decision: "approved",
            reason: "Within policy",
            workflow_reference: "wf-1",
            decided_at: "2026-07-02T00:00:00Z",
            created_at: "2026-07-02T00:00:00Z",
            correlation_id: "corr-approval",
          },
        ],
        transition_history: [
          {
            command: "submit",
            from_status: "draft",
            to_status: "submitted",
            actor_id: "controller",
            occurred_at: "2026-07-02T00:00:00Z",
            correlation_id: "corr-step",
          },
        ],
        failure_code: "JOURNAL_TIMEOUT",
        failure_detail: "target ledger unavailable",
      }),
      meta: { correlation_id: "corr-detail", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.postTransaction).mockResolvedValue({
      data: {
        id: "job-post",
        command: "post",
        status: "queued",
        attempts: 0,
        result: null,
        error_message: "",
        correlation_id: "corr-job",
        started_at: null,
        completed_at: null,
        created_at: "2026-07-23T00:00:00Z",
        updated_at: "2026-07-23T00:00:00Z",
      },
      meta: { correlation_id: "corr-post", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<TransactionDetailPage />, {
      path: "/multi-company/transactions/:id",
      route: "/multi-company/transactions/txn-1",
    });

    expect(await screen.findByRole("heading", { name: "ICT-001" })).toBeInTheDocument();
    expect(screen.getByText("JOURNAL_TIMEOUT")).toBeInTheDocument();
    expect(screen.getByText(/target ledger unavailable/u)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Post to ledgers" }));
    await user.click(screen.getByRole("button", { name: "Confirm command" }));

    await waitFor(() =>
      expect(multiCompanyService.postTransaction).toHaveBeenCalledWith(
        "txn-1",
        { expected_version: 7, transition_key: "mc-key" },
        "mc-key"
      )
    );
    expect(toast.success).toHaveBeenCalledWith("Transaction command accepted");
  });

  it("validates and creates transaction drafts without posting journals", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.createTransaction).mockResolvedValue({
      data: transaction({ id: "new-txn" }),
      meta: { correlation_id: "corr-create", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<CreateTransactionPage />, {
      path: "/multi-company/transactions/new",
      route: "/multi-company/transactions/new",
    });

    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(multiCompanyService.createTransaction).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(
      "Reference, different companies, and a positive amount are required."
    );

    await user.type(screen.getByLabelText("Reference"), "ICT-NEW");
    await user.type(screen.getByLabelText("Source company UUID"), "company-1");
    await user.type(screen.getByLabelText("Target company UUID"), "company-2");
    await user.type(screen.getByLabelText("Product category"), "services");
    await user.type(screen.getByLabelText("Original amount"), "1000");
    await user.type(screen.getByLabelText("Priced amount"), "1100");
    await user.type(screen.getByLabelText("Description"), "Shared services");
    await user.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() =>
      expect(multiCompanyService.createTransaction).toHaveBeenCalledWith(
        expect.objectContaining({
          reference: "ICT-NEW",
          source_company_id: "company-1",
          target_company_id: "company-2",
          amount: "1100",
          idempotency_key: "mc-key",
        })
      )
    );
  });

  it("executes consolidation commands and exposes generated elimination evidence", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.getConsolidation).mockResolvedValue({
      data: consolidation({
        allowed_commands: ["execute", "approve", "publish"],
        status: "draft",
        failure_code: "FX_MISSING",
        failure_step: "translation",
        failure_detail: "missing INR rate",
        report_snapshot: {
          schema_version: "2026.7",
          run_id: "run-1",
          reporting_currency: "USD",
          period_start: "2026-07-01",
          period_end: "2026-07-31",
          companies: ["company-1", "company-2"],
          trial_balance: [],
          elimination_total: "500.00",
          minority_interest_total: "125.00",
        },
      }),
      meta: { correlation_id: "corr-run", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.executeConsolidation).mockResolvedValue({
      data: {
        id: "job-consolidation",
        command: "execute",
        status: "queued",
        attempts: 0,
        result: null,
        error_message: "",
        correlation_id: "corr-job",
        started_at: null,
        completed_at: null,
        created_at: "2026-07-23T00:00:00Z",
        updated_at: "2026-07-23T00:00:00Z",
      },
      meta: { correlation_id: "corr-execute", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<ConsolidationRunDetailPage />, {
      path: "/multi-company/consolidations/:id",
      route: "/multi-company/consolidations/run-1",
    });

    expect(await screen.findByRole("heading", { name: "July close" })).toBeInTheDocument();
    expect(screen.getByText("FX_MISSING")).toBeInTheDocument();
    expect(screen.getByText("USD 500.00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Execute" }));
    await user.click(screen.getByRole("button", { name: "Confirm command" }));

    await waitFor(() =>
      expect(multiCompanyService.executeConsolidation).toHaveBeenCalledWith(
        "run-1",
        { expected_version: 7, transition_key: "mc-key" },
        "mc-key"
      )
    );
  });

  it("validates and creates consolidation drafts with configured reporting boundaries", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "consolidation-key" });
    vi.mocked(multiCompanyService.createConsolidation).mockResolvedValue({
      data: consolidation({ id: "run-created", name: "August close" }),
      meta: { correlation_id: "corr-consolidation-create", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<CreateConsolidationRunPage />, {
      path: "/multi-company/consolidations/new",
      route: "/multi-company/consolidations/new",
    });

    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(toast.error).toHaveBeenCalledWith("Name, group, and a valid period are required.");
    expect(multiCompanyService.createConsolidation).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Run name"), "August close");
    await user.type(screen.getByLabelText("Consolidation group"), "GLOBAL");
    fireEvent.change(screen.getByLabelText("Period start"), { target: { value: "2026-08-31" } });
    fireEvent.change(screen.getByLabelText("Period end"), { target: { value: "2026-08-01" } });
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(toast.error).toHaveBeenCalledWith("Name, group, and a valid period are required.");

    fireEvent.change(screen.getByLabelText("Period start"), { target: { value: "2026-08-01" } });
    fireEvent.change(screen.getByLabelText("Period end"), { target: { value: "2026-08-31" } });
    await user.clear(screen.getByLabelText("Reporting currency"));
    await user.type(screen.getByLabelText("Reporting currency"), "eur");
    await user.selectOptions(screen.getByLabelText("Translation method"), "temporal");
    await user.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() =>
      expect(multiCompanyService.createConsolidation).toHaveBeenCalledWith({
        name: "August close",
        consolidation_group: "GLOBAL",
        period_start: "2026-08-01",
        period_end: "2026-08-31",
        reporting_currency: "EUR",
        translation_method: "temporal",
        idempotency_key: "consolidation-key",
      })
    );
  });

  it("lists, opens, and creates manual eliminations with guarded financial inputs", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.listEliminations).mockResolvedValue(page([elimination()]));
    vi.mocked(multiCompanyService.getElimination).mockResolvedValue({
      data: elimination(),
      meta: { correlation_id: "corr-elimination", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.createElimination).mockResolvedValue({
      data: elimination({ id: "elim-new" }),
      meta: { correlation_id: "corr-create-elim", timestamp: "2026-07-23T00:00:00Z" },
    });

    const list = renderPage(<EliminationListPage />, {
      path: "/multi-company/consolidations/:id/eliminations",
      route: "/multi-company/consolidations/run-1/eliminations",
    });

    expect(await screen.findByRole("link", { name: "#4" })).toHaveAttribute(
      "href",
      "/multi-company/eliminations/elim-1"
    );
    list.unmount();

    const detail = renderPage(<EliminationDetailPage />, {
      path: "/multi-company/eliminations/:id",
      route: "/multi-company/eliminations/elim-1",
    });

    expect(await screen.findByRole("heading", { name: "Elimination #4" })).toBeInTheDocument();
    expect(screen.getByText("corr-elimination")).toBeInTheDocument();
    detail.unmount();

    renderPage(<CreateManualEliminationPage />, {
      path: "/multi-company/consolidations/:id/eliminations/new",
      route: "/multi-company/consolidations/run-1/eliminations/new",
    });

    await user.click(screen.getByRole("button", { name: "Record elimination" }));
    expect(multiCompanyService.createElimination).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(
      "Companies and accounts must differ, and amount must be positive."
    );
    await user.type(screen.getByLabelText("Source company UUID"), "company-1");
    await user.type(screen.getByLabelText("Target company UUID"), "company-2");
    await user.type(screen.getByLabelText("Debit account"), "9000");
    await user.type(screen.getByLabelText("Credit account"), "9001");
    await user.type(screen.getByLabelText("Amount"), "250");
    await user.type(screen.getByLabelText("Description"), "Manual true-up");
    await user.click(screen.getByRole("button", { name: "Record elimination" }));

    await waitFor(() =>
      expect(multiCompanyService.createElimination).toHaveBeenCalledWith(
        "run-1",
        expect.objectContaining({
          source_company_id: "company-1",
          target_company_id: "company-2",
          idempotency_key: "mc-key",
        })
      )
    );
  });

  it("runs the transfer-pricing simulator without mutating transaction state", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.previewTransferPrices).mockResolvedValue({
      data: [
        {
          pricing_method: "cost_plus",
          amount: "1100.00",
          formula: "1000 + 10%",
          rule_version: 3,
          rounding_mode: "ROUND_HALF_EVEN",
          precision: 2,
          rule_id: "rule-1",
          evidence: { source: "configured-rule" },
        },
      ],
      meta: { correlation_id: "corr-preview", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<TransferPricingSimulatorPage />, {
      path: "/multi-company/transfer-pricing/simulator",
      route: "/multi-company/transfer-pricing/simulator",
    });

    await user.type(screen.getByLabelText("source company"), "company-1");
    await user.type(screen.getByLabelText("target company"), "company-2");
    await user.type(screen.getByLabelText("product category"), "services");
    await user.type(screen.getByLabelText("amount"), "1000");
    await user.click(screen.getByRole("button", { name: /Compare methods/u }));

    await waitFor(() =>
      expect(multiCompanyService.previewTransferPrices).toHaveBeenCalledWith(
        expect.objectContaining({
          source_company_id: "company-1",
          target_company_id: "company-2",
          scenarios: [{ method: "cost_plus", amount: "1000", parameters: {} }],
        })
      )
    );
    expect(await screen.findByText("1000 + 10%")).toBeInTheDocument();
  });

  it("previews, exports, activates, and rolls back configuration versions with audit evidence", async () => {
    const user = userEvent.setup();
    const createObjectUrl = vi.fn(() => "blob:config-export");
    const revokeObjectUrl = vi.fn();
    const anchor = document.createElement("a");
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    const createElement = vi.spyOn(document, "createElement").mockImplementation((tag) => {
      if (tag === "a") return anchor;
      return Document.prototype.createElement.call(document, tag);
    });
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: createObjectUrl,
      revokeObjectURL: revokeObjectUrl,
    });
    vi.mocked(multiCompanyService.getConfigurationVersion).mockResolvedValue({
      data: configuration({ allowed_commands: ["activate", "rollback", "update"] }),
      meta: { correlation_id: "corr-config", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.previewConfiguration).mockResolvedValue({
      data: {
        valid: true,
        affected_companies: 3,
        affected_draft_transactions: 5,
        changed_keys: ["job_timeout_seconds"],
        warnings: ["Production activation requires approval"],
      },
      meta: { correlation_id: "corr-preview", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.exportConfiguration).mockResolvedValue({
      data: {
        format: "saraise.multi-company.configuration",
        format_version: "1.0",
        environment: "development",
        schema_version: "2026.7",
        source_version: 4,
        settings: configuration().settings,
        change_summary: "Tighten multi-company defaults",
        signature: "sig-1",
      },
      meta: { correlation_id: "corr-export", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.activateConfiguration).mockResolvedValue({
      data: configuration({ status: "active" }),
      meta: { correlation_id: "corr-activate", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.rollbackConfiguration).mockResolvedValue({
      data: configuration({ version: 5 }),
      meta: { correlation_id: "corr-rollback", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<ConfigurationVersionDetailPage />, {
      path: "/multi-company/settings/:id",
      route: "/multi-company/settings/config-1",
    });

    expect(
      await screen.findByRole("heading", { name: "development configuration · v4" })
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Preview impact" }));
    expect(await screen.findByText("Production activation requires approval")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Export signed JSON" }));
    await waitFor(() =>
      expect(multiCompanyService.exportConfiguration).toHaveBeenCalledWith("development", 4)
    );
    expect(click).toHaveBeenCalledOnce();
    expect(anchor.download).toBe("multi-company-development-v4.json");

    await user.click(screen.getByRole("button", { name: "Activate" }));
    await user.click(screen.getByRole("button", { name: "Confirm configuration change" }));
    await waitFor(() =>
      expect(multiCompanyService.activateConfiguration).toHaveBeenCalledWith("config-1", "mc-key")
    );

    await user.click(screen.getByRole("button", { name: "Rollback to this version" }));
    await user.click(screen.getByRole("button", { name: "Confirm configuration change" }));
    await waitFor(() =>
      expect(multiCompanyService.rollbackConfiguration).toHaveBeenCalledWith("config-1", {
        transition_key: "mc-key",
        change_summary: "Rollback created from configuration history workspace",
      })
    );
    createElement.mockRestore();
  });

  it("shows transfer-pricing detail fallbacks and creates extension-backed rules with idempotency", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.getTransferPricingRule).mockResolvedValue({
      data: pricingRule({
        pricing_method: "extension",
        extension_key: "industry-cost-plus",
        markup_percentage: null,
        margin_range_min: "4.00",
        margin_range_max: "9.00",
        effective_to: null,
        supersedes: null,
        documentation: "",
      }),
      meta: { correlation_id: "corr-rule-detail", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.createTransferPricingRule).mockResolvedValue({
      data: pricingRule({ id: "rule-new", pricing_method: "extension" }),
      meta: { correlation_id: "corr-rule-create", timestamp: "2026-07-23T00:00:00Z" },
    });

    const detail = renderPage(<TransferPricingRuleDetailPage />, {
      path: "/multi-company/transfer-pricing/:id",
      route: "/multi-company/transfer-pricing/rule-1",
    });

    expect(
      await screen.findByRole("heading", { name: "Shared services markup · v3" })
    ).toBeInTheDocument();
    expect(screen.getByText("Method-specific")).toBeInTheDocument();
    expect(screen.getByText("4.00 to 9.00")).toBeInTheDocument();
    expect(screen.getByText("Initial version")).toBeInTheDocument();
    expect(screen.getByText("No additional documentation")).toBeInTheDocument();
    detail.unmount();

    renderPage(<CreateTransferPricingRulePage />, {
      path: "/multi-company/transfer-pricing/new",
      route: "/multi-company/transfer-pricing/new",
    });

    await user.click(screen.getByRole("button", { name: "Save rule version" }));
    expect(multiCompanyService.createTransferPricingRule).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(
      "Name, different companies, and method-specific inputs are required."
    );

    await user.type(screen.getByLabelText("Rule name"), "India distribution margin");
    await user.type(screen.getByLabelText("Product category"), "distribution");
    await user.type(screen.getByLabelText("Source company UUID"), "company-1");
    await user.type(screen.getByLabelText("Target company UUID"), "company-2");
    await user.selectOptions(screen.getByLabelText("Pricing method"), "extension");
    await user.type(screen.getByLabelText("Governed extension key"), "industry-cost-plus");
    await user.type(screen.getByLabelText("Minimum margin"), "4");
    await user.type(screen.getByLabelText("Maximum margin"), "9");
    await user.type(screen.getByLabelText("Documentation"), "Benchmark study retained.");
    await user.click(screen.getByRole("button", { name: "Save rule version" }));

    await waitFor(() =>
      expect(multiCompanyService.createTransferPricingRule).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "India distribution margin",
          product_category: "distribution",
          pricing_method: "extension",
          extension_key: "industry-cost-plus",
          markup_percentage: null,
          margin_range_min: "4",
          margin_range_max: "9",
          source_company_id: "company-1",
          target_company_id: "company-2",
          idempotency_key: "mc-key",
        })
      )
    );
    expect(toast.success).toHaveBeenCalledWith("Pricing rule created");
  });

  it("rejects unsafe configuration bounds and saves normalized runtime policy drafts", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.createConfigurationVersion).mockResolvedValue({
      data: configuration({ id: "config-new", environment: "production", version: 8 }),
      meta: { correlation_id: "corr-config-create", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<CreateConfigurationVersionPage />, {
      path: "/multi-company/settings/new",
      route: "/multi-company/settings/new",
    });

    await user.clear(screen.getByLabelText("Minimum consolidation companies"));
    await user.type(screen.getByLabelText("Minimum consolidation companies"), "1");
    await user.type(screen.getByLabelText("Change summary"), "unsafe lower bound");
    await user.click(screen.getByRole("button", { name: "Save configuration draft" }));

    expect(multiCompanyService.createConfigurationVersion).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(
      "Review safe bounds, tolerance order, and change summary."
    );

    await user.selectOptions(screen.getByLabelText("Environment"), "production");
    await user.clear(screen.getByLabelText("Schema version"));
    await user.type(screen.getByLabelText("Schema version"), "2026.8");
    await user.clear(screen.getByLabelText("Minimum consolidation companies"));
    await user.type(screen.getByLabelText("Minimum consolidation companies"), "4");
    await user.clear(screen.getByLabelText("Job retry limit"));
    await user.type(screen.getByLabelText("Job retry limit"), "5");
    await user.clear(screen.getByLabelText("Job timeout (seconds)"));
    await user.type(screen.getByLabelText("Job timeout (seconds)"), "1200");
    await user.click(screen.getByLabelText("Allow consolidation period overlap"));
    await user.click(screen.getByLabelText("Enable operational notifications"));
    await user.clear(screen.getByLabelText("Change summary"));
    await user.type(screen.getByLabelText("Change summary"), "Enable production close policy");
    await user.click(screen.getByRole("button", { name: "Save configuration draft" }));

    await waitFor(() => expect(multiCompanyService.createConfigurationVersion).toHaveBeenCalled());
    const [request] = vi.mocked(multiCompanyService.createConfigurationVersion).mock.calls[0] as [
      ConfigurationCreateRequest,
    ];
    expect(request.environment).toBe("production");
    expect(request.schema_version).toBe("2026.8");
    expect(request.change_summary).toBe("Enable production close policy");
    expect(request.settings).toMatchObject({
      minimum_consolidation_company_count: 4,
      allow_consolidation_overlap: true,
      job_max_retries: 5,
      job_timeout_seconds: 1200,
      notification_policy: {
        approval: false,
        dispute: false,
        failure: false,
        completion: false,
      },
    });
  });

  it("surfaces malformed and server-rejected configuration imports without activating them", async () => {
    const rejected = new Error("signature rejected");
    vi.mocked(multiCompanyService.listConfigurationVersions).mockResolvedValue(page([]));
    vi.mocked(multiCompanyService.importConfiguration).mockRejectedValue(rejected);

    renderPage(<ConfigurationVersionListPage />, {
      path: "/multi-company/settings",
      route: "/multi-company/settings",
    });

    expect(await screen.findByRole("heading", { name: "Create operational policy" })).toBeVisible();
    const malformed = new File(["{}"], "settings.json", { type: "application/json" });
    Object.defineProperty(malformed, "text", {
      value: () => Promise.resolve(JSON.stringify({ schema: "wrong" })),
    });
    fireEvent.change(screen.getByLabelText("Signed JSON document"), {
      target: { files: [malformed] },
    });

    await waitFor(() => expect(multiCompanyService.importConfiguration).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByText("The document was rejected. Verify its signature and schema version.")
    ).toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalledWith("Configuration imported as an inactive draft");
  });

  it("refuses unsafe configuration drafts before mutation and preserves edit version boundaries", async () => {
    const user = userEvent.setup();
    vi.mocked(multiCompanyService.getConfigurationVersion).mockResolvedValue({
      data: configuration({
        id: "config-edit",
        version: 9,
        change_summary: "Existing safe policy",
        settings: {
          ...configuration().settings,
          job_max_retries: 2,
          job_timeout_seconds: 600,
          transfer_pricing_tolerance_min: "5.00",
          transfer_pricing_tolerance_max: "10.00",
        },
      }),
      meta: { correlation_id: "corr-edit-config", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.updateConfigurationVersion).mockResolvedValue({
      data: configuration({ id: "config-edit", version: 10 }),
      meta: { correlation_id: "corr-update-config", timestamp: "2026-07-23T00:00:00Z" },
    });

    renderPage(<EditConfigurationVersionPage />, {
      path: "/multi-company/settings/:id/edit",
      route: "/multi-company/settings/config-edit/edit",
    });

    const retryLimit = await screen.findByLabelText("Job retry limit");
    const toleranceMin = screen.getByLabelText("Pricing tolerance minimum");
    const toleranceMax = screen.getByLabelText("Pricing tolerance maximum");
    await user.clear(retryLimit);
    await user.type(retryLimit, "11");
    await user.clear(toleranceMin);
    await user.type(toleranceMin, "15");
    await user.clear(toleranceMax);
    await user.type(toleranceMax, "10");
    await user.click(screen.getByRole("button", { name: "Save configuration draft" }));

    expect(multiCompanyService.updateConfigurationVersion).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(
      "Review safe bounds, tolerance order, and change summary."
    );

    await user.clear(retryLimit);
    await user.type(retryLimit, "4");
    await user.clear(toleranceMin);
    await user.type(toleranceMin, "3.00");
    await user.clear(toleranceMax);
    await user.type(toleranceMax, "12.00");
    await user.clear(screen.getByLabelText("Change summary"));
    await user.type(screen.getByLabelText("Change summary"), "Adjust retry and tolerance policy");
    await user.click(screen.getByRole("button", { name: "Save configuration draft" }));

    await waitFor(() =>
      expect(multiCompanyService.updateConfigurationVersion).toHaveBeenCalledOnce()
    );
    const updateCall = vi.mocked(multiCompanyService.updateConfigurationVersion).mock.calls[0]!;
    expect(updateCall[0]).toBe("config-edit");
    const request: ConfigurationUpdateRequest = updateCall[1];
    expect(request.expected_version).toBe(9);
    expect(request.change_summary).toBe("Adjust retry and tolerance policy");
    const { settings } = request;
    expect(settings).toBeDefined();
    if (!settings) throw new Error("Configuration update settings were omitted.");
    expect(settings.job_max_retries).toBe(4);
    expect(settings.transfer_pricing_tolerance_min).toBe("3");
    expect(settings.transfer_pricing_tolerance_max).toBe("12");
  });

  it("previews, exports, and fail-closes rejected configuration commands with audit keys", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => "blob:mc-config");
    const revokeObjectURL = vi.fn();
    const anchor = document.createElement("a");
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    const createElement = vi.spyOn(document, "createElement").mockImplementation((tag) => {
      if (tag === "a") return anchor;
      return Document.prototype.createElement.call(document, tag);
    });
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    vi.stubGlobal("crypto", { randomUUID: () => "config-command-key" });
    vi.mocked(multiCompanyService.getConfigurationVersion).mockResolvedValue({
      data: configuration({
        allowed_commands: ["activate", "rollback", "update"],
        status: "draft",
      }),
      meta: { correlation_id: "corr-detail-config", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.previewConfiguration).mockResolvedValue({
      data: {
        affected_companies: 3,
        affected_draft_transactions: 5,
        changed_keys: ["job_max_retries", "notification_policy"],
        valid: true,
        warnings: ["Production activation requires a second approver."],
      },
      meta: { correlation_id: "corr-preview-config", timestamp: "2026-07-23T00:00:00Z" },
    });
    vi.mocked(multiCompanyService.exportConfiguration).mockResolvedValue({
      data: { signed: true, version: 4 },
      meta: { correlation_id: "corr-export-config", timestamp: "2026-07-23T00:00:00Z" },
    } as never);
    vi.mocked(multiCompanyService.rollbackConfiguration).mockRejectedValue(
      new Error("separation of duties")
    );

    renderPage(<ConfigurationVersionDetailPage />, {
      path: "/multi-company/settings/:id",
      route: "/multi-company/settings/config-1",
    });

    expect(
      await screen.findByRole("heading", { name: "development configuration · v4" })
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Preview impact" }));
    expect(
      await screen.findByText("Production activation requires a second approver.")
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Export signed JSON" }));

    await waitFor(() =>
      expect(multiCompanyService.exportConfiguration).toHaveBeenCalledWith("development", 4)
    );
    expect(anchor.download).toBe("multi-company-development-v4.json");
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mc-config");

    await user.click(screen.getByRole("button", { name: "Rollback to this version" }));
    await user.click(screen.getByRole("button", { name: "Confirm configuration change" }));

    await waitFor(() =>
      expect(multiCompanyService.rollbackConfiguration).toHaveBeenCalledWith("config-1", {
        transition_key: "config-command-key",
        change_summary: "Rollback created from configuration history workspace",
      })
    );
    expect(toast.error).toHaveBeenCalledWith("The configuration command was not applied.");
    expect(toast.success).not.toHaveBeenCalledWith(
      "Configuration command applied with audit evidence"
    );
    createElement.mockRestore();
  });
});
