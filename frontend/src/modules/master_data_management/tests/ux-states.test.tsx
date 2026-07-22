import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api-client";
import { EmptyState, GovernedError, PageSkeleton } from "../components/MdmUI";
import { SchemaFields } from "../components/SchemaFields";

describe("master data governed UX", () => {
  it.each([[403, "Access denied"], [404, "Record not found"], [503, "Capability unavailable"]] as const)("renders distinct %s state", (status, label) => {
    render(<GovernedError error={new ApiError("request failed", status, undefined, "CODE", "corr-1")}/>);
    expect(screen.getByRole("alert")).toHaveTextContent(label);
    expect(screen.getByText(/corr-1/u)).toBeInTheDocument();
  });

  it("announces geometry-matched loading and an actionable empty state", () => {
    const { rerender } = render(<PageSkeleton label="Loading MDM queue"/>);
    expect(screen.getByLabelText("Loading MDM queue")).toHaveAttribute("aria-busy", "true");
    rerender(<EmptyState title="Queue is clear" description="Nothing requires stewardship." action={<button>Run scan</button>}/>);
    expect(screen.getByRole("button", { name: "Run scan" })).toBeInTheDocument();
  });

  it("renders schema fields as accessible controls instead of a raw JSON editor", () => {
    const change = vi.fn();
    render(<SchemaFields schema={{ type: "object", properties: { email: { type: "string", title: "Email", format: "email" }, active: { type: "boolean", title: "Active" } }, required: ["email"] }} value={{}} onChange={change}/>);
    expect(screen.getByLabelText(/Email/u)).toHaveAttribute("type", "email");
    expect(screen.getByLabelText(/Active/u)).toHaveAttribute("type", "checkbox");
    expect(screen.queryByRole("textbox", { name: /JSON/u })).not.toBeInTheDocument();
  });
});
