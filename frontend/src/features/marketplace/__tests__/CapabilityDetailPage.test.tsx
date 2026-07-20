import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CapabilityDetailPage } from "../pages/CapabilityDetailPage";
import { createOfflineTrialRequest } from "../offline-trial";
import { BUILT_IN_CAPABILITIES, EMPTY_ENTITLEMENTS, resolveCapabilities } from "../catalog";
import type { MarketplaceDeployment } from "../contracts";

const ISOLATED_DEPLOYMENT: MarketplaceDeployment = {
  applicationMode: "self-hosted",
  licenseMode: "isolated",
};

describe("CapabilityDetailPage", () => {
  it("offers a real offline request journey without contacting or claiming activation", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(
      <MemoryRouter>
        <CapabilityDetailPage
          capabilityId="manufacturing-operations"
          deployment={ISOLATED_DEPLOYMENT}
        />
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Start an offline evaluation" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Download offline trial request" })).toBeEnabled();
    expect(screen.getByText(/No connection to the SARAISE platform is required/i)).toBeVisible();
    expect(screen.queryByText(/activated successfully/i)).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("builds a portable request from the capability entitlement contract", () => {
    const capability = resolveCapabilities(BUILT_IN_CAPABILITIES, EMPTY_ENTITLEMENTS).find(
      (item) => item.id === "manufacturing-operations"
    );
    expect(capability).toBeDefined();

    const request = createOfflineTrialRequest(
      capability!,
      () => new Date("2026-07-21T00:00:00.000Z")
    );

    expect(request).toEqual({
      schemaVersion: "1.0",
      requestType: "offline-trial",
      capabilityId: "manufacturing-operations",
      entitlementKey: "industry.manufacturing.operations",
      generatedAt: "2026-07-21T00:00:00.000Z",
    });
  });

  it("removes the upgrade gate only when the exact entitlement is active", () => {
    render(
      <MemoryRouter>
        <CapabilityDetailPage
          capabilityId="manufacturing-operations"
          deployment={ISOLATED_DEPLOYMENT}
          entitlements={{
            active: new Set(["industry.manufacturing.operations"]),
            trials: new Set(),
          }}
        />
      </MemoryRouter>
    );

    expect(screen.getByText("Available")).toBeVisible();
    expect(screen.queryByText("Upgrade to unlock")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Download offline trial request" })
    ).not.toBeInTheDocument();
  });
});
