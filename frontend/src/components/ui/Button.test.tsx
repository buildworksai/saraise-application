/**
 * Button Component Tests
 *
 * Tests for Button UI component.
 */

import { describe, expect, it, vi } from "vitest";
import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { Button } from "./Button";

const baseClasses = [
  "inline-flex",
  "items-center",
  "justify-center",
  "rounded-md",
  "font-medium",
  "transition-colors",
  "focus-visible:outline-none",
  "focus-visible:ring-2",
  "focus-visible:ring-ring",
  "focus-visible:ring-offset-2",
  "ring-offset-background",
  "disabled:opacity-50",
  "disabled:pointer-events-none",
];

const variantClasses = {
  primary: ["bg-primary", "text-primary-foreground", "hover:bg-primary/90"],
  secondary: ["bg-secondary", "text-secondary-foreground", "hover:bg-secondary/80"],
  danger: ["bg-destructive", "text-destructive-foreground", "hover:bg-destructive/90"],
  ghost: ["bg-transparent", "text-foreground", "hover:bg-accent", "hover:text-accent-foreground"],
  outline: [
    "border",
    "border-input",
    "bg-background",
    "hover:bg-accent",
    "hover:text-accent-foreground",
  ],
} as const;

const sizeClasses = {
  sm: ["px-3", "py-1.5", "text-sm"],
  md: ["px-4", "py-2", "text-sm"],
  lg: ["px-6", "py-3", "text-base"],
  icon: ["p-2"],
} as const;

type ButtonVariant = keyof typeof variantClasses;
type ButtonSize = keyof typeof sizeClasses;

function expectOnlyClassGroup(
  button: HTMLElement,
  expected: readonly string[],
  allOptions: Record<string, readonly string[]>
) {
  expect(button).toHaveClass(...expected);

  const forbiddenClasses = Object.values(allOptions)
    .flat()
    .filter((className) => !expected.includes(className));

  for (const className of forbiddenClasses) {
    expect(button).not.toHaveClass(className);
  }
}

describe("Button", () => {
  it("should render button with text", () => {
    render(<Button>Click me</Button>);
    const button = screen.getByRole("button", { name: "Click me" });

    expect(button).toBeInTheDocument();
    expect(button).toHaveClass(...baseClasses);
    expectOnlyClassGroup(button, variantClasses.primary, variantClasses);
    expectOnlyClassGroup(button, sizeClasses.md, sizeClasses);
  });

  it("should call onClick when clicked", () => {
    const handleClick = vi.fn();

    render(<Button onClick={handleClick}>Click me</Button>);

    const button = screen.getByRole("button");
    button.click();
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it("should be disabled when disabled prop is true", () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("should not call onClick when disabled", () => {
    const handleClick = vi.fn();

    render(
      <Button disabled onClick={handleClick}>
        Disabled
      </Button>
    );

    const button = screen.getByRole("button");
    button.click();
    expect(handleClick).not.toHaveBeenCalled();
  });

  it.each(
    Object.entries(variantClasses).map(([variant, expectedClasses]) => [
      variant as ButtonVariant,
      expectedClasses,
    ])
  )("should render only %s variant styles", (variant, expectedClasses) => {
    render(<Button variant={variant}>{variant}</Button>);

    expectOnlyClassGroup(
      screen.getByRole("button", { name: variant }),
      expectedClasses,
      variantClasses
    );
  });

  it.each(
    Object.entries(sizeClasses).map(([size, expectedClasses]) => [
      size as ButtonSize,
      expectedClasses,
    ])
  )("should render only %s size styles", (size, expectedClasses) => {
    render(<Button size={size}>{size}</Button>);

    expectOnlyClassGroup(screen.getByRole("button", { name: size }), expectedClasses, sizeClasses);
  });

  it("should merge custom classes after generated classes", () => {
    render(<Button className="custom-button">Configured</Button>);

    expect(screen.getByRole("button", { name: "Configured" })).toHaveClass("custom-button");
  });

  it("should forward refs to the button element", () => {
    const ref = createRef<HTMLButtonElement>();

    render(<Button ref={ref}>Referenced</Button>);

    expect(ref.current).toBe(screen.getByRole("button", { name: "Referenced" }));
  });
});
