import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  MemberForm,
  MilestoneForm,
  ProjectForm,
  TaskForm,
  TimeEntryForm,
} from "./ProjectForms";

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
    expectExplicitLabel(projectCode);
    expect(screen.getByText("Uppercase letters, numbers, and hyphens.")).toHaveClass("text-xs");

    expect(screen.getByLabelText("Project name")).toBeRequired();
    expect(screen.getByLabelText("Project name")).toHaveAttribute("maxLength", "255");
    expect(screen.getByLabelText("Description")).toHaveAttribute("maxLength", "20000");
    expect(screen.getByLabelText("Budget")).toHaveAttribute("min", "0");
    expect(screen.getByLabelText("Budget")).toHaveAttribute("step", "0.01");
  });

  it("exposes task, member, time, and milestone required fields through labels", () => {
    const { unmount } = render(<TaskForm onSave={vi.fn()} />);

    expectExplicitLabel(screen.getByLabelText("Project ID"));
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Task code")).toBeRequired();
    expect(screen.getByLabelText("Task name")).toBeRequired();

    unmount();
    const member = render(<MemberForm onSave={vi.fn()} />);
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Employee ID")).toBeRequired();
    expect(screen.getByLabelText("Allocation percentage")).toBeRequired();
    expect(screen.getByLabelText("Allocation percentage")).toHaveAttribute("min", "0.01");
    expect(screen.getByLabelText("Allocation percentage")).toHaveAttribute("max", "100");

    member.unmount();
    const time = render(<TimeEntryForm onSave={vi.fn()} />);
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Employee ID")).toBeRequired();
    expect(screen.getByLabelText("Date")).toBeRequired();
    expect(screen.getByLabelText("Hours")).toBeRequired();
    expect(screen.getByLabelText("Hours")).toHaveAttribute("max", "24");

    time.unmount();
    render(<MilestoneForm onSave={vi.fn()} />);
    expect(screen.getByLabelText("Project ID")).toBeRequired();
    expect(screen.getByLabelText("Milestone name")).toBeRequired();
    expect(screen.getByLabelText("Target date")).toBeRequired();
  });
});
