import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WorkflowApiError } from "../services/workflow-service";
import { PageHeader, PageSkeleton, Pagination, StatusPill, WorkflowProblem } from "./WorkflowUI";

describe("WorkflowUI primitives", () => {
  it("renders optional header actions, unknown status, and bounded skeleton rows", () => {
    render(
      <>
        <PageHeader
          eyebrow="Governed workflows"
          title="Evidence"
          description="Operator-visible state"
          actions={<button type="button">Act</button>}
        />
        <StatusPill status="custom_state" />
        <PageSkeleton rows={2} />
      </>
    );
    expect(screen.getByText("Governed workflows")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Act" })).toBeInTheDocument();
    expect(screen.getByText("custom state")).toBeInTheDocument();
    expect(screen.getByLabelText("Loading workflow data")).toHaveAttribute("aria-busy", "true");
  });

  it("classifies denied, missing, degraded, and generic failures with retry evidence", async () => {
    const retry = vi.fn();
    const { rerender } = render(
      <WorkflowProblem
        error={new WorkflowApiError("Forbidden", 403, "denied", "corr-denied", [], false)}
        retry={retry}
      />
    );
    expect(screen.getByText("Permission required")).toBeInTheDocument();
    rerender(
      <WorkflowProblem
        error={new WorkflowApiError("Missing", 404, "missing", "corr-missing", [], false)}
        retry={retry}
      />
    );
    expect(screen.getByText("Workflow record not found")).toBeInTheDocument();
    rerender(
      <WorkflowProblem
        error={new WorkflowApiError("Unavailable", 503, "degraded", "corr-degraded", [], true)}
        retry={retry}
      />
    );
    expect(screen.getByText("Workflow capability unavailable")).toBeInTheDocument();
    rerender(<WorkflowProblem error={new Error("plain failure")} retry={retry} />);
    expect(screen.getByText("plain failure")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("moves pagination inside valid bounds only", async () => {
    const onPage = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<Pagination page={1} totalPages={3} onPage={onPage} />);
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(onPage).toHaveBeenCalledWith(2);
    rerender(<Pagination page={3} totalPages={3} onPage={onPage} />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(onPage).toHaveBeenCalledWith(2);
  });
});
