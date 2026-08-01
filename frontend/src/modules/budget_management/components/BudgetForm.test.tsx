import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BudgetForm, initialBudgetValue } from "./BudgetForm";

function renderBudgetForm() {
  return render(
    <BudgetForm
      initial={initialBudgetValue()}
      busy={false}
      submitLabel="Create budget"
      onCancel={vi.fn()}
      onSubmit={vi.fn()}
    />
  );
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
});
