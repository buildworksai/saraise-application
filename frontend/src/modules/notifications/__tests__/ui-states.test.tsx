import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ApiError } from "@/services/api-client";
import { EmptyPanel, GovernedError, MutationError, PageSkeleton, StatusPill } from "../components/NotificationUI";

describe("notification UX states", () => {
  it("announces its loading skeleton", () => {
    render(<PageSkeleton/>);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(screen.getByLabelText("Loading notifications")).toHaveAttribute("aria-busy", "true");
  });

  it("renders an explicit permission-denied deep-link state", () => {
    render(<GovernedError error={new ApiError("Denied", 403, undefined, "permission_denied", "corr-403")}/>);
    expect(screen.getByRole("alert")).toHaveTextContent("Permission denied");
    expect(screen.getByRole("alert")).toHaveTextContent("corr-403");
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("does not fabricate mutation success", () => {
    render(<MutationError error={new ApiError("Adapter offline", 503, undefined, "adapter_unavailable", "corr-503")}/>);
    expect(screen.getByRole("alert")).toHaveTextContent("Change not saved");
    expect(screen.getByRole("alert")).toHaveTextContent("Adapter offline");
  });

  it("provides accessible empty and semantic status states with theme tokens", () => {
    render(<MemoryRouter><EmptyPanel title="No deliveries found" description="No durable evidence matches." action={{ label: "Dispatch", to: "/notifications/deliveries/new" }}/><StatusPill value="retry_wait"/></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Dispatch" })).toHaveAttribute("href", "/notifications/deliveries/new");
    expect(screen.getByRole("status")).toHaveTextContent("retry wait");
    expect(screen.getByRole("status").className).toContain("bg-muted");
  });
});
