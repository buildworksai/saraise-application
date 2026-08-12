/**
 * Dialog Component Tests
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dialog, ConfirmDialog } from "./Dialog";

describe("Dialog", () => {
  it("should render when open", () => {
    render(
      <Dialog open={true} onOpenChange={vi.fn()}>
        <div>Dialog Content</div>
      </Dialog>
    );
    expect(screen.getByText("Dialog Content")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveClass("fixed", "left-1/2", "bg-popover", "max-w-md");
    expect(screen.getByText("Dialog")).toHaveClass("sr-only");
    expect(screen.getByText("Modal dialog")).toHaveClass("sr-only");
  });

  it("should not render when closed", () => {
    render(
      <Dialog open={false} onOpenChange={vi.fn()}>
        <div>Dialog Content</div>
      </Dialog>
    );
    expect(screen.queryByText("Dialog Content")).not.toBeInTheDocument();
  });

  it("should render title when provided", () => {
    render(
      <Dialog open={true} onOpenChange={vi.fn()} title="Test Dialog">
        <div>Content</div>
      </Dialog>
    );
    expect(screen.getByText("Test Dialog")).toHaveClass("text-lg", "font-semibold");
    expect(screen.getByText("Modal dialog")).toHaveClass("sr-only");
  });

  it("should render description when provided", () => {
    render(
      <Dialog open={true} onOpenChange={vi.fn()} description="Test description">
        <div>Content</div>
      </Dialog>
    );
    expect(screen.getByText("Dialog")).toHaveClass("sr-only");
    expect(screen.getByText("Test description")).toHaveClass("mt-2", "text-muted-foreground");
  });

  it.each([
    ["sm", "max-w-sm", ["max-w-md", "max-w-lg", "max-w-xl"]],
    ["md", "max-w-md", ["max-w-sm", "max-w-lg", "max-w-xl"]],
    ["lg", "max-w-lg", ["max-w-sm", "max-w-md", "max-w-xl"]],
    ["xl", "max-w-xl", ["max-w-sm", "max-w-md", "max-w-lg"]],
  ] as const)("should apply only %s dialog width", (size, expectedClass, rejectedClasses) => {
    render(
      <Dialog open={true} onOpenChange={vi.fn()} size={size}>
        <div>Content</div>
      </Dialog>
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveClass(expectedClass);
    rejectedClasses.forEach((className) => expect(dialog).not.toHaveClass(className));
  });

  it("should call onOpenChange when close button is clicked", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <Dialog open={true} onOpenChange={onOpenChange}>
        <div>Content</div>
      </Dialog>
    );

    const closeButton = screen.getByRole("button");
    await user.click(closeButton);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe("ConfirmDialog", () => {
  it("should render title and description", () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Confirm Action"
        description="Are you sure?"
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByText("Confirm Action")).toBeInTheDocument();
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
  });

  it("should call onConfirm when confirm button is clicked", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={onOpenChange}
        title="Confirm"
        description="Are you sure?"
        onConfirm={onConfirm}
      />
    );

    const confirmButton = screen.getByRole("button", { name: /confirm/i });
    await user.click(confirmButton);
    expect(onConfirm).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("should call onOpenChange(false) when cancel is clicked", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={onOpenChange}
        title="Confirm"
        description="Are you sure?"
        onConfirm={vi.fn()}
      />
    );

    const cancelButton = screen.getByRole("button", { name: /cancel/i });
    await user.click(cancelButton);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("should use custom button labels", () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Confirm"
        description="Are you sure?"
        confirmLabel="Yes, delete"
        cancelLabel="No, keep"
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "Yes, delete" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "No, keep" })).toBeInTheDocument();
  });

  it("should render danger confirmation actions with danger styling", () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Delete project"
        description="This cannot be undone."
        confirmLabel="Delete"
        variant="danger"
        onConfirm={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: "Delete" })).toHaveClass("bg-destructive");
  });

  it("should render default confirmation actions with primary styling", () => {
    render(
      <ConfirmDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Save workflow"
        description="Apply these changes."
        confirmLabel="Save"
        onConfirm={vi.fn()}
      />
    );

    const confirmButton = screen.getByRole("button", { name: "Save" });
    expect(confirmButton).toHaveClass("bg-primary");
    expect(confirmButton).not.toHaveClass("bg-destructive");
  });
});
