/* eslint-disable max-lines-per-function -- page fixtures intentionally exercise multiple compliance UI branches. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ComplianceAssessment,
  ComplianceFramework,
  ComplianceRequirement,
  DashboardSummaryDTO,
  PaginatedEnvelope,
} from "../contracts";
import { complianceService } from "../services/compliance-service";
import {
  ComplianceDashboardPage,
  FrameworkDetailPage,
  FrameworkListPage,
  RequirementDetailPage,
  RequirementListPage,
} from "./CompliancePages";

const storage = (() => {
  let values = new Map<string, string>();
  return {
    clear: () => {
      values = new Map();
    },
    getItem: (key: string) => values.get(key) ?? null,
    removeItem: (key: string) => {
      values.delete(key);
    },
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
})();

Object.defineProperty(globalThis, "localStorage", {
  value: storage,
  configurable: true,
});

const page = <T,>(data: readonly T[]): PaginatedEnvelope<T> => ({
  data,
  meta: {
    correlation_id: "corr-page",
    timestamp: "2026-07-31T00:00:00Z",
    pagination: {
      page: 1,
      page_size: 25,
      count: data.length,
      total_pages: data.length ? 2 : 0,
      has_next: Boolean(data.length),
      has_previous: false,
    },
  },
});

const audit = {
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-15T00:00:00Z",
  created_by: "actor-1",
  updated_by: null,
  deleted_at: null,
  deleted_by: null,
};

const framework: ComplianceFramework = {
  ...audit,
  id: "framework-1",
  code: "SOC2",
  name: "SOC 2",
  version: "2026",
  category: "security",
  description: "Trust services criteria",
  source_kind: "custom",
  source_package: "",
  source_version: "",
  status: "draft",
  requirement_count: 2,
  allowed_actions: ["update", "activate"],
};

const requirement: ComplianceRequirement = {
  ...audit,
  id: "requirement-1",
  framework: "framework-1",
  framework_code: "SOC2",
  code: "CC1.1",
  title: "Governance responsibilities",
  description: "Board oversight is documented.",
  section: "CC1",
  guidance: "Review board minutes.",
  applicability: "applicable",
  applicability_rationale: "",
  status: "active",
  sort_order: 1,
  tags: ["governance", "board"],
  mapping_count: 0,
  evidence_count: 0,
  gap_status: undefined,
  allowed_actions: ["update"],
};

const assessment: ComplianceAssessment = {
  id: "assessment-1",
  requirement: "requirement-1",
  requirement_code: "CC1.1",
  mapping: null,
  status: "partial",
  notes: "",
  assessor: "assessor-1",
  assessed_at: "2026-07-20T00:00:00Z",
  due_date: null,
  source: "manual",
  created_at: "2026-07-20T00:00:00Z",
};

function renderPage(ui: React.ReactElement, initialEntry = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("compliance management pages", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("renders dashboard loading, guided incomplete steps, and a clear assessment queue", async () => {
    const summary: DashboardSummaryDTO = {
      frameworks: 1,
      requirements: 4,
      unassessed_requirements: 0,
      gaps: 1,
      review_queue: 2,
      expiring_evidence: 3,
    };
    vi.spyOn(complianceService, "dashboard").mockResolvedValue(summary);

    renderPage(<ComplianceDashboardPage />);

    expect(screen.getByLabelText("Loading compliance workspace")).toHaveAttribute(
      "aria-busy",
      "true"
    );
    expect(await screen.findByText("Compliance workspace")).toBeVisible();
    expect(screen.getByText("Requirements")).toBeVisible();
    expect(screen.getByText("4")).toBeVisible();
    expect(screen.getByText("Queue is clear")).toBeVisible();
    expect(screen.getByText("Author policies")).toBeVisible();
  });

  it("saves, restores, filters, and paginates framework list state", async () => {
    const user = userEvent.setup();
    vi.spyOn(complianceService.frameworks, "list").mockResolvedValue(page([framework]));

    renderPage(<FrameworkListPage />);

    expect(await screen.findByRole("link", { name: "SOC 2" })).toBeVisible();
    await user.type(screen.getByLabelText("Search"), "soc{Enter}");
    await user.click(screen.getByRole("button", { name: "Save filter" }));
    expect(localStorage.getItem("compliance-filter:frameworks")).toContain("search=soc");
    await user.selectOptions(screen.getByLabelText("Framework status"), "active");
    await waitFor(() =>
      expect(complianceService.frameworks.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "soc", status: "active" })
      )
    );
    await user.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() =>
      expect(complianceService.frameworks.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "soc", status: undefined })
      )
    );
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(complianceService.frameworks.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 })
      )
    );
  });

  it("renders framework detail readiness and hides forbidden actions", async () => {
    vi.spyOn(complianceService.frameworks, "get").mockResolvedValue({
      ...framework,
      status: "active",
      allowed_actions: [],
      description: "",
    });
    vi.spyOn(complianceService.frameworks, "status").mockResolvedValue({
      framework,
      readiness: {
        framework_id: "framework-1",
        score: 75,
        earned_points: 3,
        possible_points: 4,
        formula: "earned / possible",
        requirements: [
          { requirement_id: "requirement-1", code: "CC1.1", status: "partial", points: 1 },
          {
            requirement_id: "requirement-2",
            code: "CC1.2",
            status: "not_assessed",
            points: 0,
          },
        ],
      },
      gaps: { framework_id: "framework-1", total: 2, gap_count: 1, gaps: [] },
    });

    renderPage(
      <Routes>
        <Route path="/frameworks/:id" element={<FrameworkDetailPage />} />
      </Routes>,
      "/frameworks/framework-1"
    );

    expect(await screen.findByText("SOC 2")).toBeVisible();
    expect(screen.getByText("75.0%")).toBeVisible();
    expect(screen.getByText("No description provided.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Activate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("renders requirement grouped list filters and empty create action", async () => {
    const user = userEvent.setup();
    const list = vi.spyOn(complianceService.requirements, "list");
    list.mockResolvedValueOnce(page([requirement])).mockResolvedValue(page([]));

    renderPage(<RequirementListPage />);

    expect(await screen.findByRole("link", { name: "Governance responsibilities" })).toBeVisible();
    expect(screen.getByText("0 policies · 0 evidence")).toBeVisible();
    await user.type(screen.getByLabelText("Framework UUID"), "framework-1");
    await user.tab();
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ framework_id: "framework-1" }))
    );
    expect(await screen.findByText("No requirements")).toBeVisible();
    expect(screen.getByRole("button", { name: "Create requirement" })).toBeEnabled();
  });

  it("renders requirement detail gap, assessment, mappings, and evidence branches", async () => {
    vi.spyOn(complianceService.requirements, "get").mockResolvedValue(requirement);
    vi.spyOn(complianceService.assessments, "list").mockResolvedValue(page([assessment]));
    vi.spyOn(complianceService.mappings, "list").mockResolvedValue(page([]));
    vi.spyOn(complianceService.evidence, "list").mockResolvedValue(page([]));

    renderPage(
      <Routes>
        <Route path="/requirements/:id" element={<RequirementDetailPage />} />
      </Routes>,
      "/requirements/requirement-1"
    );

    expect(await screen.findByText("Governance responsibilities")).toBeVisible();
    expect(screen.getByText("unmapped")).toBeVisible();
    expect(screen.getByText("No notes.")).toBeVisible();
    expect(screen.getByText(/explainable gap/i)).toBeVisible();
    expect(screen.getByText("No evidence is attached.")).toBeVisible();
  });
});
