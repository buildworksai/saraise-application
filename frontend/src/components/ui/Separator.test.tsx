/**
 * Separator Component Tests
 */

import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Separator } from "./Separator";

describe("Separator", () => {
  it("should render separator element", () => {
    const { container } = render(<Separator />);
    const separator = container.querySelector('[data-orientation="horizontal"]');
    expect(separator).toBeInTheDocument();
  });

  it("should apply custom className", () => {
    const { container } = render(<Separator className="custom-class" />);
    const separator = container.querySelector(".custom-class");
    expect(separator).toBeInTheDocument();
  });

  it("should render with orientation prop", () => {
    const { container: horizontal } = render(<Separator orientation="horizontal" />);
    const { container: vertical } = render(<Separator orientation="vertical" />);

    expect(horizontal.querySelector('[data-orientation="horizontal"]')).toBeInTheDocument();
    expect(vertical.querySelector('[data-orientation="vertical"]')).toBeInTheDocument();
  });
});
