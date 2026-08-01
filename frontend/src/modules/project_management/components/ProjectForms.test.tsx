/* eslint-disable max-lines-per-function -- Project form mutation coverage keeps related governed form payloads together. */
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemberForm, MilestoneForm, ProjectForm, TaskForm, TimeEntryForm } from "./ProjectForms";

function expectExplicitLabel(control: HTMLElement) {
  const id = control.getAttribute("id");
  expect(id).toBeTruthy();
  expect(document.querySelector(`label[for="${id}"]`)).not.toBeNull();
}

describe("project management forms", () => {
  it("exposes project form controls through explicit labels and native constraints", () => {
    const { container } = render(<ProjectForm onSave={vi.fn()} />);

    expect(container.querySelector("form")?.noValidate).toBe(false);
    const projectCode = screen.getByLabelText("Project code");
    expect(projectCode).toBeRequired();
    expect(projectCode).toHaveAttribute("maxLength", "50");
    expect(projectCode).toHaveClass("border-border");
    expectExplicitLabel(projectCode);
    expect(screen.getByText("Uppercase letters, numbers, and hyphens.")).toHaveClass("text-xs");

    expect(screen.getByLabelText("Project name")).toBeRequired();
    expect(screen.getByLabelText("Project name")).toHaveAttribute("maxLength", "255");
    expect(screen.getByLabelText("Description")).toHaveAttribute("maxLength", "20000");
    expect(screen.getByLabelText("Budget")).toHaveAttribute("min", "0");
    expect(screen.getByLabelText("Budget")).toHaveAttribute("step", "0.01");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
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
    await user.type(screen.getByLabelText("Project code"), "ops");
    await user.type(screen.getByLabelText("Project name"), "Operations");
    await user.type(screen.getByLabelText("Start date"), "2027-03-01");
    await user.clear(screen.getByLabelText("Start date"));
    await user.type(screen.getByLabelText("Budget"), "15");
    await user.clear(screen.getByLabelText("Budget"));

    container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        project_code: "OPS",
        start_date: null,
        end_date: null,
        project_manager_id: null,
        budget: null,
      })
    );
  });

  it("exposes task, member, time, and milestone required fields through labels", () => {
    const { unmount } = render(<TaskForm onSave={vi.fn()} />);

    expectExplicitLabel(screen.getByLabelText("Project ID"));
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Project ID")).toHaveValue("");
    expect(screen.getByLabelText("Task code")).toBeRequired();
    expect(screen.getByLabelText("Task name")).toBeRequired();
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

    member.unmount();
    const time = render(<TimeEntryForm onSave={vi.fn()} />);
    expect(screen.getByLabelText("Project ID")).toHaveValue("");
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Employee ID")).toBeRequired();
    expect(screen.getByLabelText("Date")).toBeRequired();
    expect(screen.getByLabelText("Hours")).toBeRequired();
    expect(screen.getByLabelText("Hours")).toHaveValue(null);
    expect(screen.getByLabelText("Work description")).toHaveValue("");
    expect(screen.getByLabelText("Hours")).toHaveAttribute("max", "24");

    time.unmount();
    render(<MilestoneForm onSave={vi.fn()} />);
    expect(screen.getByLabelText("Project ID")).toHaveValue("");
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Milestone name")).toBeRequired();
    expect(screen.getByLabelText("Milestone name")).toHaveValue("");
    expect(screen.getByLabelText("Target date")).toBeRequired();
    expect(screen.getByLabelText("Target date")).toHaveValue("");
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

  it("submits task, member, time entry, and milestone payloads from governed controls", async () => {
    const user = userEvent.setup();
    const onTaskSave = vi.fn();
    const task = render(<TaskForm projectId="project-1" onSave={onTaskSave} />);
    await user.clear(screen.getByLabelText("Project ID"));
    await user.type(screen.getByLabelText("Project ID"), "project-2");
    await user.type(screen.getByLabelText("Task code"), "task-1");
    await user.type(screen.getByLabelText("Task name"), "Configure workflows");
    await user.type(screen.getByLabelText("Due date"), "2027-04-30");
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
    await user.clear(screen.getByLabelText("Project ID"));
    await user.type(screen.getByLabelText("Project ID"), "project-2");
    await user.type(screen.getByLabelText("Employee ID"), "employee-1");
    await user.clear(screen.getByLabelText("Allocation percentage"));
    await user.type(screen.getByLabelText("Allocation percentage"), "55.50");
    member.container
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(onMemberSave).toHaveBeenCalledWith(
      expect.objectContaining({
        project: "project-2",
        employee_id: "employee-1",
        role: "member",
        allocation_percentage: "55.5",
      })
    );
    member.unmount();

    const onTimeSave = vi.fn();
    const time = render(<TimeEntryForm projectId="project-1" onSave={onTimeSave} />);
    expect(screen.getByLabelText("Date")).toHaveValue(new Date().toISOString().slice(0, 10));
    expect(screen.getByLabelText("Hours")).toHaveValue(null);
    await user.clear(screen.getByLabelText("Project ID"));
    await user.type(screen.getByLabelText("Project ID"), "project-2");
    await user.type(screen.getByLabelText("Employee ID"), "employee-1");
    await user.clear(screen.getByLabelText("Date"));
    await user.type(screen.getByLabelText("Date"), "2027-05-15");
    await user.type(screen.getByLabelText("Hours"), "6.25");
    await user.type(screen.getByLabelText("Work description"), "Mapped ERP process variants");
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
    expect(screen.getByLabelText("Target date")).toHaveValue("");
    await user.clear(screen.getByLabelText("Project ID"));
    await user.type(screen.getByLabelText("Project ID"), "project-2");
    await user.type(screen.getByLabelText("Milestone name"), "Pilot complete");
    await user.type(screen.getByLabelText("Target date"), "2027-06-30");
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
