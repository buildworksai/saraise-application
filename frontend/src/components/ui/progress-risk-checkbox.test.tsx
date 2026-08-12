import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Checkbox } from "./checkbox";
import { RingProgressIndicator } from "./RingProgressIndicator";
import { RiskScoreBadge } from "./RiskScoreBadge";

describe("shared low-coverage UI components", () => {
  it("renders every ring status, success rate, custom class, and completed connector", () => {
    const { container } = render(
      <RingProgressIndicator
        className="custom-progress"
        rings={[
          { name: "Queued", status: "pending" },
          { name: "Running", status: "in_progress", successRate: 72.25 },
          { name: "Verified", status: "completed", successRate: 100 },
          { name: "Rollback", status: "failed" },
        ]}
      />
    );

    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("72.3% success")).toBeInTheDocument();
    expect(screen.getByText("100.0% success")).toBeInTheDocument();
    expect(screen.getByText("Rollback")).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("custom-progress");
    expect(container.querySelector(".bg-green-500.dark\\:bg-green-400")).toBeInTheDocument();
  });

  it.each([
    { score: null, label: "Not Scored", className: "text-muted-foreground" },
    { score: 30, label: "30 - Low Risk", className: "text-green-600" },
    { score: 50, label: "50 - Medium Risk", className: "text-amber-600" },
    { score: 51, label: "51 - High Risk", className: "text-destructive" },
  ])("renders risk score boundary $label", ({ score, label, className }) => {
    render(<RiskScoreBadge score={score} className="extra-risk-class" />);

    const badge = screen.getByText(label);
    expect(badge).toHaveClass(className);
    expect(badge).toHaveClass("extra-risk-class");
  });

  it("forwards checkbox state, disabled guard, custom class, and ref", async () => {
    const user = userEvent.setup();
    const onCheckedChange = vi.fn();
    const ref = { current: null as HTMLButtonElement | null };

    render(
      <>
        <Checkbox
          ref={ref}
          aria-label="Governed option"
          className="custom-checkbox"
          onCheckedChange={onCheckedChange}
        />
        <Checkbox aria-label="Locked option" disabled />
      </>
    );

    const checkbox = screen.getByRole("checkbox", { name: "Governed option" });
    expect(ref.current).toBe(checkbox);
    expect(checkbox).toHaveClass("custom-checkbox");

    await user.click(checkbox);
    expect(onCheckedChange).toHaveBeenCalledWith(true);

    await user.click(screen.getByRole("checkbox", { name: "Locked option" }));
    expect(screen.getByRole("checkbox", { name: "Locked option" })).toBeDisabled();
    expect(onCheckedChange).toHaveBeenCalledTimes(1);
  });
});
