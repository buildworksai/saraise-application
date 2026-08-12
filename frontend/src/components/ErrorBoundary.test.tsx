import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

function ExplodingChild(): ReactElement {
  throw new Error("render failed");
}

describe("ErrorBoundary", () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it("renders children while healthy", () => {
    render(
      <ErrorBoundary>
        <div>Healthy app</div>
      </ErrorBoundary>
    );

    expect(screen.getByText("Healthy app")).toBeInTheDocument();
  });

  it("renders the governed fallback when a child throws", () => {
    render(
      <ErrorBoundary>
        <ExplodingChild />
      </ErrorBoundary>
    );

    expect(screen.getByRole("heading", { name: "Application Error" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "An unexpected error occurred. Please refresh the page or contact support if the problem persists."
      )
    ).toBeInTheDocument();
  });
});
