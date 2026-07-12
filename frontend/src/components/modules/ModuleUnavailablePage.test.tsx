import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ModuleUnavailablePage } from "./ModuleUnavailablePage";

describe("ModuleUnavailablePage", () => {
  it("states that no unverified endpoint request was sent", () => {
    render(<ModuleUnavailablePage moduleName="Process Mining" />);

    expect(screen.getByRole("heading", { name: "Process Mining is not available" })).toBeInTheDocument();
    expect(screen.getByText(/No request was sent to an unverified endpoint/)).toBeInTheDocument();
  });
});
