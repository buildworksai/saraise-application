import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PrivacyPolicy } from "./PrivacyPolicy";
import { Security } from "./Security";
import { Support } from "./Support";
import { TermsOfService } from "./TermsOfService";

describe("static policy pages", () => {
  it("renders the security policy disclosure channels and control commitments", () => {
    render(<Security />);

    expect(screen.getByRole("heading", { name: "Security Policy" })).toBeInTheDocument();
    expect(screen.getByText("Last Updated: January 2025")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2. Security Features" })).toBeInTheDocument();
    expect(screen.getByText("Security Architecture")).toBeInTheDocument();
    expect(screen.getByText("Encryption")).toBeInTheDocument();
    expect(screen.getByText("Access Control")).toBeInTheDocument();
    expect(screen.getByText("Vulnerability Management")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "security@buildworks.ai" })[0]).toHaveAttribute(
      "href",
      "mailto:security@buildworks.ai"
    );
    expect(screen.getByText(/Initial Response:/)).toBeInTheDocument();
    expect(screen.getByText(/SOC 2 Aligned:/)).toBeInTheDocument();
  });

  it("renders support channels with external link hygiene", () => {
    render(<Support />);

    expect(screen.getByRole("heading", { name: "Support" })).toBeInTheDocument();
    expect(screen.getByText(/Get help with SARAISE/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "info@buildworks.ai" })[0]).toHaveAttribute(
      "href",
      "mailto:info@buildworks.ai"
    );

    const discussions = screen.getByRole("link", { name: "GitHub Discussions" });
    expect(discussions).toHaveAttribute(
      "href",
      "https://github.com/buildworksai/saraise.release/discussions"
    );
    expect(discussions).toHaveAttribute("target", "_blank");
    expect(discussions).toHaveAttribute("rel", "noopener noreferrer");

    const issues = screen.getByRole("link", { name: "GitHub Issues" });
    expect(issues).toHaveAttribute(
      "href",
      "https://github.com/buildworksai/saraise.release/issues"
    );
    expect(screen.getByRole("heading", { name: "Response Times" })).toBeInTheDocument();
    expect(screen.getByText(/Commercial Support:/)).toBeInTheDocument();
  });

  it("renders privacy policy rights, self-hosted boundaries, and company contact data", () => {
    render(<PrivacyPolicy />);

    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "8. Your Rights" })).toBeInTheDocument();
    expect(screen.getByText(/We do not sell your personal information/)).toBeInTheDocument();
    expect(
      screen.getByText(/We do not access or process data from self-hosted instances/)
    ).toBeInTheDocument();
    expect(screen.getByText(/Cookies and Tracking Technologies/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "info@buildworks.ai" })[0]).toHaveAttribute(
      "href",
      "mailto:info@buildworks.ai"
    );
    expect(screen.getByText("BuildFlow Consultancy Private Limited")).toBeInTheDocument();
    expect(screen.getByText("U62099TS2025PTC201319")).toBeInTheDocument();
  });

  it("renders terms of service license, usage, and jurisdiction sections", () => {
    render(<TermsOfService />);

    expect(screen.getByRole("heading", { name: "Terms of Service" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "3. License Grant" })).toBeInTheDocument();
    expect(
      screen.getByText(/SARAISE software is licensed under the Apache License/)
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "https://www.apache.org/licenses/LICENSE-2.0" })
    ).toHaveAttribute("rel", "noopener noreferrer");
    expect(
      screen.getByText(/Use SARAISE for any illegal or unauthorized purpose/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/exclusive jurisdiction of the courts in Hyderabad/)
    ).toBeInTheDocument();

    const serviceDescription = screen.getByRole("heading", {
      name: "2. Description of Service",
    }).parentElement;
    expect(serviceDescription).not.toBeNull();
    expect(
      within(serviceDescription!).getByText("Open-source software code available on GitHub")
    ).toBeInTheDocument();
  });
});
