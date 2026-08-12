/**
 * StatusBadge Component Tests
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge, type StatusType } from "./StatusBadge";

const baseClasses = ["px-2", "py-1", "text-xs", "rounded-full", "font-medium", "border"];

const statusCases: {
  status: StatusType;
  label: string;
  classes: string[];
}[] = [
  {
    status: "running",
    label: "Running",
    classes: ["bg-primary/10", "text-primary", "border-primary/20"],
  },
  {
    status: "paused",
    label: "Paused",
    classes: [
      "bg-amber-500/10",
      "text-amber-600",
      "dark:text-amber-400",
      "border-amber-500/20",
      "dark:border-amber-400/20",
    ],
  },
  {
    status: "completed",
    label: "Completed",
    classes: [
      "bg-green-500/10",
      "text-green-600",
      "dark:text-green-400",
      "border-green-500/20",
      "dark:border-green-400/20",
    ],
  },
  {
    status: "failed",
    label: "Failed",
    classes: ["bg-destructive/10", "text-destructive", "border-destructive/20"],
  },
  {
    status: "pending",
    label: "Pending",
    classes: [
      "bg-amber-500/10",
      "text-amber-600",
      "dark:text-amber-400",
      "border-amber-500/20",
      "dark:border-amber-400/20",
    ],
  },
  {
    status: "approved",
    label: "Approved",
    classes: [
      "bg-green-500/10",
      "text-green-600",
      "dark:text-green-400",
      "border-green-500/20",
      "dark:border-green-400/20",
    ],
  },
  {
    status: "rejected",
    label: "Rejected",
    classes: ["bg-destructive/10", "text-destructive", "border-destructive/20"],
  },
  {
    status: "active",
    label: "Active",
    classes: [
      "bg-green-500/10",
      "text-green-600",
      "dark:text-green-400",
      "border-green-500/20",
      "dark:border-green-400/20",
    ],
  },
  {
    status: "inactive",
    label: "Inactive",
    classes: ["bg-muted", "text-muted-foreground", "border-border"],
  },
  {
    status: "cancelled",
    label: "Cancelled",
    classes: ["bg-muted", "text-muted-foreground", "border-border"],
  },
  {
    status: "expired",
    label: "Expired",
    classes: [
      "bg-orange-500/10",
      "text-orange-600",
      "dark:text-orange-400",
      "border-orange-500/20",
      "dark:border-orange-400/20",
    ],
  },
];

describe("StatusBadge", () => {
  it.each(statusCases)("should render the $status contract", ({ status, label, classes }) => {
    render(<StatusBadge status={status} />);

    const badge = screen.getByText(label);
    expect(badge).toHaveTextContent(label);
    expect(badge).toHaveClass(...baseClasses, ...classes);
  });

  it("should apply custom className", () => {
    render(<StatusBadge status="active" className="custom-class" />);

    expect(screen.getByText("Active")).toHaveClass("custom-class");
  });
});
