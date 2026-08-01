import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { Component, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { formatRouteTitle } from "./route-title";

vi.mock("./components/auth/ProtectedRoute", () => ({
  ProtectedRoute: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("./components/layout/ModuleLayout", () => ({
  ModuleLayout: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}));

vi.mock("./modules/asset_management/pages/AssetListPage", () => ({
  AssetListPage: () => <h1>Registry asset register page</h1>,
}));

vi.mock("./modules/bank_reconciliation/pages/BankAccountListPage", () => ({
  BankAccountListPage: () => <h1>Registry bank accounts page</h1>,
}));

vi.mock("./modules/inventory_management/pages/InventoryPages", () => ({
  WarehouseListPage: () => <h1>Registry warehouses page</h1>,
}));

vi.mock("./modules/security_access_control/pages/RolesPage", () => ({
  RolesPage: () => <h1>Registry security roles page</h1>,
}));

vi.mock("./modules/security_access_control/pages/PermissionsPage", () => ({
  PermissionsPage: () => <h1>Registry security permissions page</h1>,
}));

vi.mock("./modules/security_access_control/pages/PermissionSetsPage", () => ({
  PermissionSetsPage: () => <h1>Registry permission sets page</h1>,
}));

vi.mock("./modules/security_access_control/pages/AuditLogPage", () => ({
  AuditLogPage: () => <h1>Registry security audit log page</h1>,
}));

vi.mock("./modules/human_resources/pages/CreateLeaveRequestPage", () => ({
  CreateLeaveRequestPage: () => <h1>Registry leave request create page</h1>,
}));

vi.mock("./modules/human_resources/pages/LeaveRequestDetailPage", () => ({
  LeaveRequestDetailPage: () => <h1>Registry leave request detail page</h1>,
}));

vi.mock("./modules/human_resources/pages/EditLeaveRequestPage", () => ({
  EditLeaveRequestPage: () => <h1>Registry leave request edit page</h1>,
}));

vi.mock("./modules/document_intelligence/pages/ExtractionDashboardPage", () => ({
  ExtractionDashboardPage: () => <h1>Registry document intelligence extractions page</h1>,
}));

class TestErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) return <div role="alert">Route render failed</div>;
    return this.props.children;
  }
}

describe("App", () => {
  afterEach(() => {
    cleanup();
    document.title = "";
    window.history.pushState(null, "", "/");
  });

  it("renders the app with router", () => {
    window.history.pushState(null, "", "/login");

    render(
      <TestErrorBoundary>
        <App />
      </TestErrorBoundary>
    );

    // App renders BrowserRouter, so check for a link or route element
    // The login page should be accessible
    expect(screen.getByRole("link", { name: /forgot password/i })).toBeInTheDocument();
  });

  it.each([
    ["Inventory", "Inventory · SARAISE"],
    ["  Inventory  ", "Inventory · SARAISE"],
    ["Already branded · SARAISE", "Already branded · SARAISE"],
    [undefined, "SARAISE · SARAISE"],
    ["   ", "SARAISE · SARAISE"],
  ])("formats route title %s", (title, expected) => {
    expect(formatRouteTitle(title)).toBe(expected);
  });

  it.each([
    ["/asset-management/assets", "Asset register · SARAISE", "Registry asset register page"],
    ["/bank-reconciliation/accounts", "Bank accounts · SARAISE", "Registry bank accounts page"],
    ["/inventory-management/warehouses", "Warehouses · SARAISE", "Registry warehouses page"],
    [
      "/security-access-control/roles",
      "Security administration · SARAISE",
      "Registry security roles page",
    ],
    [
      "/security-access-control/permissions",
      "Permissions · SARAISE",
      "Registry security permissions page",
    ],
    [
      "/security-access-control/permission-sets",
      "Permission sets · SARAISE",
      "Registry permission sets page",
    ],
    [
      "/security-access-control/audit-logs",
      "Security audit trail · SARAISE",
      "Registry security audit log page",
    ],
    [
      "/human-resources/leave-requests/new",
      "Request leave · SARAISE",
      "Registry leave request create page",
    ],
  ])(
    "renders %s through the migrated route registry title wrapper",
    async (path, title, heading) => {
      window.history.pushState(null, "", path);

      render(
        <TestErrorBoundary>
          <App />
        </TestErrorBoundary>
      );

      expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
      await waitFor(() => expect(document.title).toBe(title));
    }
  );
});

describe("App legacy redirects and fallback routes", () => {
  afterEach(() => {
    cleanup();
    document.title = "";
    window.history.pushState(null, "", "/");
  });

  it.each([
    [
      "/human-resources/leave-requests/request%2042",
      "/human-resources/leave/requests/request%2042",
      "Leave request detail · SARAISE",
      "Registry leave request detail page",
    ],
    [
      "/human-resources/leave-requests/request%2042/edit",
      "/human-resources/leave/requests/request%2042/edit",
      "Edit leave request · SARAISE",
      "Registry leave request edit page",
    ],
    [
      "/document-intelligence",
      "/document-intelligence/extractions",
      "Extraction evidence · SARAISE",
      "Registry document intelligence extractions page",
    ],
  ])(
    "redirects legacy or module root route %s into the migrated registry route",
    async (legacyPath, expectedPath, title, heading) => {
      window.history.pushState(null, "", legacyPath);

      render(
        <TestErrorBoundary>
          <App />
        </TestErrorBoundary>
      );

      expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
      await waitFor(() => expect(window.location.pathname).toBe(expectedPath));
      await waitFor(() => expect(document.title).toBe(title));
    }
  );

  it("sets a human-readable title for unmatched routes", async () => {
    window.history.pushState(null, "", "/missing-route");

    render(
      <TestErrorBoundary>
        <App />
      </TestErrorBoundary>
    );

    expect(screen.getByText("Page not found")).toBeInTheDocument();
    await waitFor(() => expect(document.title).toBe("Page not found · SARAISE"));
  });
});
