/* eslint-disable max-lines-per-function -- Project form mutation coverage keeps related governed form payloads together. */
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemberForm, MilestoneForm, ProjectForm, TaskForm, TimeEntryForm } from "./ProjectForms";

const expectedFieldClass =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

function expectExplicitLabel(control: HTMLElement) {
  const id = control.getAttribute("id");
  expect(id).toBeTruthy();
  expect(document.querySelector(`label[for="${id}"]`)).not.toBeNull();
}

describe("project management forms", () => {
  it("exposes project form controls through explicit labels and governed constraints", () => {
    const { container } = render(<ProjectForm onSave={vi.fn()} />);

    expect(container.querySelector("form")?.noValidate).toBe(true);
    const projectCode = screen.getByLabelText("Project code");
    expect(projectCode).toBeRequired();
    expect(projectCode).toHaveAttribute("maxLength", "50");
    expect(projectCode).toHaveClass("border-border");
    expect(projectCode.getAttribute("class")).toBe(expectedFieldClass);
    expectExplicitLabel(projectCode);
    expect(screen.getByText("Uppercase letters, numbers, and hyphens.")).toHaveClass("text-xs");
    expect(
      screen.getByText(/Define the governed project record, budget guardrails/)
    ).toBeInTheDocument();

    expect(screen.getByLabelText("Project name")).toBeRequired();
    expect(screen.getByLabelText("Project name")).toHaveAttribute("maxLength", "255");
    expect(screen.getByLabelText("Description")).toHaveAttribute("maxLength", "20000");
    expect(screen.getByLabelText("Budget")).toHaveAttribute("min", "0");
    expect(screen.getByLabelText("Budget")).toHaveAttribute("step", "0.01");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("shows governed member validation when saving empty identifiers", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();

    render(<MemberForm onSave={onSave} />);

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(screen.getByText("Project ID is required")).toBeInTheDocument();
    expect(screen.getByText("Employee ID is required")).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("guards browser unload only after a form becomes dirty and unregisters on unmount", async () => {
    const user = userEvent.setup();
    const addListener = vi.spyOn(window, "addEventListener");
    const removeListener = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<ProjectForm onSave={vi.fn()} />);

    const cleanEvent = new Event("beforeunload", { cancelable: true });
    const cleanPrevent = vi.spyOn(cleanEvent, "preventDefault");
    window.dispatchEvent(cleanEvent);
    expect(cleanPrevent).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Project code"), "erp");
    const dirtyEvent = new Event("beforeunload", { cancelable: true });
    const dirtyPrevent = vi.spyOn(dirtyEvent, "preventDefault");
    window.dispatchEvent(dirtyEvent);
    expect(dirtyPrevent).toHaveBeenCalledTimes(1);
    expect(dirtyEvent.returnValue).toBe(false);
    expect(addListener).toHaveBeenCalledWith("beforeunload", expect.any(Function));

    unmount();
    expect(removeListener).toHaveBeenCalledWith("beforeunload", expect.any(Function));
    addListener.mockRestore();
    removeListener.mockRestore();
  });

  it("submits project edits with typed values and renders pending and server error states", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const { container } = render(
      <ProjectForm
        initial={{
          project_code: "legacy",
          project_name: "Legacy project",
          description: "Existing description",
          start_date: "2027-01-01",
          end_date: "2027-09-30",
          project_manager_id: "manager-0",
          budget: "100.00",
        }}
        pending
        error="Project code already exists."
        onSave={onSave}
      />
    );

    expect(screen.getByRole("heading", { name: "Edit project" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Project code already exists.");
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByLabelText("Project code")).toHaveValue("legacy");
    expect(screen.getByLabelText("Project name")).toHaveValue("Legacy project");
    expect(screen.getByLabelText("Description")).toHaveValue("Existing description");
    expect(screen.getByLabelText("End date")).toHaveValue("2027-09-30");
    expect(screen.getByLabelText("Manager ID")).toHaveValue("manager-0");
    expect(screen.getByLabelText("Budget")).toHaveValue(100);
    expect(screen.getByLabelText("End date")).toHaveAttribute("min", "2027-01-01");

    await user.clear(screen.getByLabelText("Project code"));
    await user.type(screen.getByLabelText("Project code"), "erp-27");
    await user.clear(screen.getByLabelText("Project name"));
    await user.type(screen.getByLabelText("Project name"), "ERP rollout");
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Replace legacy workflows" },
    });
    await user.clear(screen.getByLabelText("Start date"));
    await user.type(screen.getByLabelText("Start date"), "2027-02-01");
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2027-10-31" } });
    fireEvent.change(screen.getByLabelText("Manager ID"), { target: { value: "manager-1" } });
    await user.clear(screen.getByLabelText("Budget"));
    await user.type(screen.getByLabelText("Budget"), "2500.75");

    container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        project_code: "ERP-27",
        project_name: "ERP rollout",
        description: "Replace legacy workflows",
        start_date: "2027-02-01",
        end_date: "2027-10-31",
        project_manager_id: "manager-1",
        budget: "2500.75",
        currency: "USD",
      })
    );
  });

  it("submits null optional project fields from blank controls", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const { container } = render(<ProjectForm onSave={onSave} />);

    expect(screen.getByRole("heading", { name: "Create project" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project code")).toHaveValue("");
    expect(screen.getByLabelText("Project name")).toHaveValue("");
    expect(screen.getByLabelText("Description")).toHaveValue("");
    expect(screen.getByLabelText("Start date")).toHaveValue("");
    expect(screen.getByLabelText("End date")).toHaveValue("");
    expect(screen.getByLabelText("Manager ID")).toHaveValue("");
    expect(screen.getByLabelText("Budget")).toHaveValue(null);
    expect(screen.getByLabelText("Start date")).not.toHaveDisplayValue(/Stryker/u);
    expect(screen.getByLabelText("End date")).not.toHaveDisplayValue(/Stryker/u);
    expect(screen.getByLabelText("Budget")).not.toHaveDisplayValue(/Stryker/u);
    await user.type(screen.getByLabelText("Project code"), "ops");
    await user.type(screen.getByLabelText("Project name"), "Operations");
    await user.type(screen.getByLabelText("Start date"), "2027-03-01");
    await user.clear(screen.getByLabelText("Start date"));
    await user.type(screen.getByLabelText("Budget"), "15");
    await user.clear(screen.getByLabelText("Budget"));

    container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    expect(onSave).toHaveBeenCalledWith({
      project_code: "OPS",
      project_name: "Operations",
      description: "",
      start_date: null,
      end_date: null,
      project_manager_id: null,
      budget: null,
      currency: "USD",
    });
  });

  it("exposes task, member, time, and milestone required fields through labels", () => {
    const { unmount } = render(<TaskForm onSave={vi.fn()} />);

    expectExplicitLabel(screen.getByLabelText("Project ID"));
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Project ID")).toHaveValue("");
    expect(screen.getByLabelText("Task code")).toBeRequired();
    expect(screen.getByLabelText("Task code")).toHaveValue("");
    expect(screen.getByLabelText("Task name")).toBeRequired();
    expect(screen.getByLabelText("Task name")).toHaveValue("");
    expect(screen.getByText(/stable task code, priority/)).toBeInTheDocument();
    expect(screen.getByText(/Stored uppercase for audit-stable lookup/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();

    unmount();
    const member = render(<MemberForm onSave={vi.fn()} />);
    expect(screen.getByLabelText("Project ID")).toHaveValue("");
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Employee ID")).toBeRequired();
    expect(screen.getByLabelText("Allocation percentage")).toBeRequired();
    expect(screen.getByLabelText("Allocation percentage")).toHaveValue(100);
    expect(screen.getByLabelText("Allocation percentage")).toHaveAttribute("min", "0.01");
    expect(screen.getByLabelText("Allocation percentage")).toHaveAttribute("max", "100");
    expect(screen.getByLabelText("Employee ID")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();

    member.unmount();
    const time = render(<TimeEntryForm onSave={vi.fn()} />);
    expect(screen.getByLabelText("Project ID")).toHaveValue("");
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Employee ID")).toBeRequired();
    expect(screen.getByLabelText("Date")).toBeRequired();
    expect(screen.getByLabelText("Hours")).toBeRequired();
    expect(screen.getByLabelText("Hours")).toHaveValue(null);
    expect(screen.getByLabelText("Hours")).not.toHaveDisplayValue(/Stryker/u);
    expect(screen.getByLabelText("Work description")).toHaveValue("");
    expect(screen.getByLabelText("Work description")).not.toHaveDisplayValue(/Stryker/u);
    expect(screen.getByLabelText("Hours")).toHaveAttribute("max", "24");
    expect(screen.getByText(/daily hour limits/)).toBeInTheDocument();
    expect(screen.getByText(/quarter-hour increments/)).toBeInTheDocument();
    expect(screen.getByLabelText("Employee ID")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();

    time.unmount();
    render(<MilestoneForm onSave={vi.fn()} />);
    expect(screen.getByLabelText("Project ID")).toHaveValue("");
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Milestone name")).toBeRequired();
    expect(screen.getByLabelText("Milestone name")).toHaveValue("");
    expect(screen.getByLabelText("Target date")).toBeRequired();
    expect(screen.getByLabelText("Target date")).toHaveValue("");
    expect(screen.getByLabelText("Target date")).not.toHaveDisplayValue(/Stryker/u);
    expect(screen.getByText(/progress, risk, and governance reporting/)).toBeInTheDocument();
    expect(screen.getByText(/schedule variance can be calculated/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("renders pending state consistently on related project forms", () => {
    const task = render(<TaskForm pending onSave={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();

    task.unmount();
    const member = render(<MemberForm pending onSave={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();

    member.unmount();
    const time = render(<TimeEntryForm pending onSave={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();

    time.unmount();
    render(<MilestoneForm pending onSave={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  });

  it("submits task, member, time entry, and milestone payloads from governed controls", () => {
    const onTaskSave = vi.fn();
    const task = render(<TaskForm projectId="project-1" onSave={onTaskSave} />);
    fireEvent.change(screen.getByLabelText("Project ID"), { target: { value: "project-2" } });
    fireEvent.change(screen.getByLabelText("Task code"), { target: { value: "task-1" } });
    fireEvent.change(screen.getByLabelText("Task name"), {
      target: { value: "Configure workflows" },
    });
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2027-04-30" } });
    task.container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(onTaskSave).toHaveBeenCalledWith(
      expect.objectContaining({
        project: "project-2",
        task_code: "TASK-1",
        task_name: "Configure workflows",
        due_date: "2027-04-30",
        priority: "medium",
      })
    );
    task.unmount();

    const onMemberSave = vi.fn();
    const member = render(<MemberForm projectId="project-1" onSave={onMemberSave} />);
    fireEvent.change(screen.getByLabelText("Project ID"), { target: { value: "project-2" } });
    fireEvent.change(screen.getByLabelText("Employee ID"), { target: { value: "employee-1" } });
    fireEvent.change(screen.getByLabelText("Allocation percentage"), {
      target: { value: "55.50" },
    });
    member.container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(onMemberSave).toHaveBeenCalledWith(
      expect.objectContaining({
        project: "project-2",
        employee_id: "employee-1",
        role: "member",
        allocation_percentage: "55.50",
      })
    );
    member.unmount();

    const onTimeSave = vi.fn();
    const time = render(<TimeEntryForm projectId="project-1" onSave={onTimeSave} />);
    expect(screen.getByLabelText("Date")).toHaveValue(new Date().toISOString().slice(0, 10));
    expect(screen.getByLabelText("Hours")).toHaveValue(null);
    fireEvent.change(screen.getByLabelText("Project ID"), { target: { value: "project-2" } });
    fireEvent.change(screen.getByLabelText("Employee ID"), { target: { value: "employee-1" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2027-05-15" } });
    fireEvent.change(screen.getByLabelText("Hours"), { target: { value: "6.25" } });
    fireEvent.change(screen.getByLabelText("Work description"), {
      target: { value: "Mapped ERP process variants" },
    });
    expect(screen.getByLabelText("Work description")).toHaveValue("Mapped ERP process variants");
    time.container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(onTimeSave).toHaveBeenCalledWith(
      expect.objectContaining({
        project: "project-2",
        employee_id: "employee-1",
        entry_date: "2027-05-15",
        hours_worked: "6.25",
        description: "Mapped ERP process variants",
      })
    );
    time.unmount();

    const onMilestoneSave = vi.fn();
    const milestone = render(<MilestoneForm projectId="project-1" onSave={onMilestoneSave} />);
    expect(screen.getByLabelText("Project ID")).toHaveValue("project-1");
    expect(screen.getByLabelText("Project ID")).toHaveClass("focus-visible:ring-ring");
    expect(screen.getByLabelText("Target date")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Project ID"), { target: { value: "project-2" } });
    fireEvent.change(screen.getByLabelText("Milestone name"), {
      target: { value: "Pilot complete" },
    });
    fireEvent.change(screen.getByLabelText("Target date"), { target: { value: "2027-06-30" } });
    milestone.container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(onMilestoneSave).toHaveBeenCalledWith(
      expect.objectContaining({
        project: "project-2",
        milestone_name: "Pilot complete",
        target_date: "2027-06-30",
      })
    );
  });
});
