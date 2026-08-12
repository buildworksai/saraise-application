import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type React from "react";
import { MemoryRouter } from "react-router-dom";
import { AccountForm, ActivityForm, ContactForm, LeadForm, OpportunityForm } from "../forms";
import { AIInsights } from "../components/AIInsights";
import { GovernedError } from "../components/CrmPage";
import { CrmApiError } from "../services/crm-service";
import { crmKeys } from "../services/crm-service";

function renderWithCrmConfiguration(children: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(crmKeys.configuration(), {
    document: {
      account: {
        allowed_types: ["customer", "partner"],
        default_type: "customer",
        hierarchy_max_depth: 3,
      },
      activity: {
        default_related_type: "Lead",
        default_type: "task",
        require_future_task_due_date: true,
      },
      field_limits: {
        account_country: 2,
        opportunity_currency: 3,
      },
      opportunity: {
        default_currency: "USD",
        default_probability: 10,
        minimum_amount: "1.00",
        probability_max: 100,
        probability_min: 0,
      },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CRM forms and governed states", () => {
  it("retains lead form data and reports inline validation", () => {
    const submit = vi.fn();
    render(<LeadForm pending={false} onSubmit={submit} />, { wrapper: MemoryRouter });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "not-an-email" } });
    fireEvent.click(screen.getByRole("button", { name: "Save lead" }));
    expect(screen.getByLabelText(/^Last name/u)).toBeRequired();
    expect(screen.getByLabelText(/^Last name/u)).toBeInvalid();
    expect(screen.getByLabelText("Email")).toBeInvalid();
    expect(screen.getByLabelText("Email")).toHaveValue("not-an-email");
    expect(submit).not.toHaveBeenCalled();
  });

  it("marks CRM create forms with native required constraints", () => {
    const submit = vi.fn();

    render(<LeadForm pending={false} onSubmit={submit} />, { wrapper: MemoryRouter });
    expect(screen.getByLabelText(/^Last name/u)).toBeRequired();
    cleanup();

    renderWithCrmConfiguration(<AccountForm pending={false} onSubmit={submit} />);
    expect(screen.getByLabelText(/^Account name/u)).toBeRequired();
    cleanup();

    render(<ContactForm pending={false} onSubmit={submit} />, { wrapper: MemoryRouter });
    expect(screen.getByLabelText(/^Account ID/u)).toBeRequired();
    expect(screen.getByLabelText(/^Last name/u)).toBeRequired();
    cleanup();

    renderWithCrmConfiguration(<OpportunityForm pending={false} onSubmit={submit} />);
    expect(screen.getByLabelText(/^Account ID/u)).toBeRequired();
    expect(screen.getByLabelText(/^Opportunity name/u)).toBeRequired();
    expect(screen.getByLabelText(/^Amount/u)).toBeRequired();
    expect(screen.getByLabelText(/^Currency/u)).toBeRequired();
    expect(screen.getByLabelText(/^Currency/u)).toHaveAttribute("pattern", "[A-Z]{3}");
    expect(screen.getByLabelText(/^Expected close date/u)).toBeRequired();
    cleanup();

    renderWithCrmConfiguration(<ActivityForm pending={false} onSubmit={submit} />);
    expect(screen.getByLabelText(/^Related record ID/u)).toBeRequired();
    expect(screen.getByLabelText(/^Subject/u)).toBeRequired();
  });

  it("renders permission and correlation details without leaking a generic zero state", () => {
    render(
      <GovernedError
        subject="Lead"
        error={new CrmApiError("Denied", "permission", 403, "permission_denied", "req-denied")}
      />
    );
    expect(screen.getByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText(/req-denied/u)).toBeInTheDocument();
  });

  it("renders invalid CRM detail identifiers as not found instead of access denial", () => {
    render(
      <GovernedError
        subject="Lead"
        error={new CrmApiError("Lead was not found", "not_found", 404, "not_found", "req-missing")}
      />
    );
    expect(screen.getByText("Lead not found")).toBeInTheDocument();
    expect(screen.queryByText("Access denied")).not.toBeInTheDocument();
    expect(screen.getByText(/req-missing/u)).toBeInTheDocument();
  });

  it("shows prediction unavailable instead of fabricated insights", () => {
    render(<AIInsights prediction={null} />);
    expect(screen.getByText("Provider prediction unavailable")).toBeInTheDocument();
    expect(screen.getByText(/never presented as AI output/u)).toBeInTheDocument();
  });
});
