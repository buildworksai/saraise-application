/* eslint-disable max-lines-per-function -- Budget form mutation coverage keeps governed validation scenarios colocated. */
import { fireEvent, render, screen } from "@testing-library/react";
import type React from "react";
import { describe, expect, it, vi } from "vitest";
import { BudgetForm, initialBudgetValue } from "./BudgetForm";
import type { BudgetDetail } from "../contracts";

function renderBudgetForm(overrides?: Partial<React.ComponentProps<typeof BudgetForm>>) {
  const props: React.ComponentProps<typeof BudgetForm> = {
    initial: initialBudgetValue(),
    busy: false,
    submitLabel: "Create budget",
    onCancel: vi.fn(),
    onSubmit: vi.fn(),
    ...overrides,
  };
  return render(<BudgetForm {...props} />);
}

describe("BudgetForm", () => {
  it("uses native required constraints for governed budget fields", () => {
    const { container } = renderBudgetForm();

    expect(container.querySelector("form")?.noValidate).toBe(false);
    expect(screen.getByLabelText("Budget code")).toBeRequired();
    expect(screen.getByLabelText("Budget name")).toBeRequired();
    expect(screen.getByLabelText("Fiscal year")).toBeRequired();
    expect(screen.getByLabelText("Fiscal year")).toHaveAttribute("min", "1900");
    expect(screen.getByLabelText("Fiscal year")).toHaveAttribute("max", "9999");
    expect(screen.getByLabelText("Budget type")).toBeRequired();
    expect(screen.getByLabelText("Start date")).toBeRequired();
    expect(screen.getByLabelText("End date")).toBeRequired();
    expect(screen.getByLabelText("Currency")).toBeRequired();
    expect(screen.getByLabelText("Currency")).toHaveAttribute("maxLength", "3");

    fireEvent.invalid(screen.getByLabelText("Budget code"));

    expect(screen.getByText("Code is required.")).toBeInTheDocument();
    expect(screen.getByText("Name is required.")).toBeInTheDocument();
  });

  it("validates governed business rules before submit", () => {
    const onSubmit = vi.fn();
    const { container } = renderBudgetForm({ onSubmit });

    fireEvent.change(screen.getByLabelText("Fiscal year"), { target: { value: "1899" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2027-02-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2027-01-31" } });
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "US1" } });
    fireEvent.change(screen.getByLabelText("Budget ceiling (optional)"), {
      target: { value: "-0.01" },
    });
    fireEvent.submit(container.querySelector("form")!);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Enter a four-digit fiscal year.")).toBeInTheDocument();
    expect(screen.getByText("End date must not precede the start date.")).toBeInTheDocument();
    expect(screen.getByText("Use a three-letter uppercase ISO currency code.")).toBeInTheDocument();
    expect(
      screen.getByText("Enter a non-negative amount with at most two decimal places.")
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Fiscal year"), { target: { value: "10000" } });
    fireEvent.submit(container.querySelector("form")!);
    expect(screen.getByText("Enter a four-digit fiscal year.")).toBeInTheDocument();
  });

  it("requires scoped IDs for departmental and project budgets", () => {
    const onSubmit = vi.fn();
    const { container } = renderBudgetForm({ onSubmit });

    fireEvent.change(screen.getByLabelText("Budget type"), { target: { value: "departmental" } });
    expect(screen.getByLabelText("Department UUID")).toBeRequired();
    fireEvent.submit(container.querySelector("form")!);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText("Department UUID is required for a departmental budget.")
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Budget type"), { target: { value: "project" } });
    expect(screen.getByLabelText("Project UUID")).toBeRequired();
    fireEvent.submit(container.querySelector("form")!);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Project UUID is required for a project budget.")).toBeInTheDocument();
  });

  it("submits normalized project budget payloads and honors busy/cancel/server states", () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();
    const initial = {
      ...initialBudgetValue(),
      budget_code: " fy27-prj ",
      budget_name: " Project expansion ",
      fiscal_year: 2027,
      start_date: "2027-01-01",
      end_date: "2027-12-31",
      budget_type: "project" as const,
      currency: "USD",
      budget_ceiling: "1250.50",
      department_id: "department-ignored",
      project_id: "project-1",
    };
    const { container } = renderBudgetForm({
      initial,
      busy: true,
      serverErrors: { budget_name: ["Server says duplicate name."] },
      onCancel,
      onSubmit,
      submitLabel: "Save budget",
    });

    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByText("Server says duplicate name.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);

    fireEvent.submit(container.querySelector("form")!);
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        budget_code: "FY27-PRJ",
        budget_name: "Project expansion",
        currency: "USD",
        budget_ceiling: "1250.50",
        department_id: null,
        project_id: "project-1",
      })
    );
  });

  it("converts blank optional values to null for operating budgets", () => {
    const onSubmit = vi.fn();
    const { container } = renderBudgetForm({ onSubmit });

    fireEvent.change(screen.getByLabelText("Budget code"), { target: { value: "ops-27" } });
    fireEvent.change(screen.getByLabelText("Budget name"), { target: { value: "Operations" } });
    fireEvent.change(screen.getByLabelText("Budget ceiling (optional)"), {
      target: { value: "" },
    });
    fireEvent.submit(container.querySelector("form")!);

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        budget_code: "OPS-27",
        budget_ceiling: null,
        department_id: null,
        project_id: null,
      })
    );
  });

  it("covers edit initialization, boundary acceptance, and scoped field updates", () => {
    const source: BudgetDetail = {
      id: "budget-1",
      budget_code: "FY27-DEPT",
      budget_name: "Department plan",
      fiscal_year: 1900,
      start_date: "1900-01-01",
      end_date: "1900-01-01",
      budget_type: "departmental",
      currency: "USD",
      budget_ceiling: "0",
      department_id: "department-1",
      project_id: null,
      status: "draft",
      total_budget: "0",
      created_at: "2026-07-31T00:00:00Z",
      updated_at: "2026-07-31T00:00:00Z",
      created_by: "user-1",
      updated_by: "user-1",
      submitted_at: null,
      submitted_by: null,
      approved_at: null,
      approved_by: null,
      rejected_at: null,
      rejected_by: null,
      rejection_reason: "",
      lines: [],
      approvals: [],
      transitions: [],
      variance_alerts: [],
      variance_summary: null,
      allowed_commands: [],
    };
    const onSubmit = vi.fn();
    const { container } = renderBudgetForm({
      initial: initialBudgetValue(source),
      onSubmit,
    });

    expect(screen.getByLabelText("Fiscal year")).toHaveValue(1900);
    expect(screen.getByLabelText("Budget ceiling (optional)")).toHaveValue("0");
    expect(screen.getByLabelText("Department UUID")).toHaveValue("department-1");
    fireEvent.change(screen.getByLabelText("Department UUID"), {
      target: { value: "department-2" },
    });
    fireEvent.submit(container.querySelector("form")!);
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        fiscal_year: 1900,
        start_date: "1900-01-01",
        end_date: "1900-01-01",
        budget_ceiling: "0",
        department_id: "department-2",
        project_id: null,
      })
    );

    fireEvent.change(screen.getByLabelText("Fiscal year"), { target: { value: "9999" } });
    fireEvent.change(screen.getByLabelText("Budget type"), { target: { value: "project" } });
    expect(screen.queryByLabelText("Department UUID")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Project UUID")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Project UUID"), { target: { value: "project-2" } });
    fireEvent.submit(container.querySelector("form")!);
    expect(onSubmit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        fiscal_year: 9999,
        department_id: null,
        project_id: "project-2",
      })
    );
  });

  it("rejects whitespace identity, blank dates, malformed currency, and malformed ceilings", () => {
    const onSubmit = vi.fn();
    const { container } = renderBudgetForm({ onSubmit });

    fireEvent.change(screen.getByLabelText("Budget code"), { target: { value: "   " } });
    fireEvent.change(screen.getByLabelText("Budget name"), { target: { value: "   " } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USDX" } });
    fireEvent.change(screen.getByLabelText("Budget ceiling (optional)"), {
      target: { value: "100.999" },
    });
    fireEvent.submit(container.querySelector("form")!);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Code is required.")).toBeInTheDocument();
    expect(screen.getByText("Name is required.")).toBeInTheDocument();
    expect(screen.getByText("Start date is required.")).toBeInTheDocument();
    expect(screen.getByText("End date is required.")).toBeInTheDocument();
    expect(screen.getByText("Use a three-letter uppercase ISO currency code.")).toBeInTheDocument();
    expect(
      screen.getByText("Enter a non-negative amount with at most two decimal places.")
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Budget code"), { target: { value: "OPS" } });
    fireEvent.change(screen.getByLabelText("Budget name"), { target: { value: "Operations" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2027-01-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2027-01-01" } });
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "XUSD" } });
    fireEvent.change(screen.getByLabelText("Budget ceiling (optional)"), {
      target: { value: "USD100" },
    });
    fireEvent.submit(container.querySelector("form")!);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Use a three-letter uppercase ISO currency code.")).toBeInTheDocument();
    expect(
      screen.getByText("Enter a non-negative amount with at most two decimal places.")
    ).toBeInTheDocument();
  });
});
