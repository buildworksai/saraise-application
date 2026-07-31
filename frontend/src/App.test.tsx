import { render, screen, waitFor } from "@testing-library/react";
import { Component, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

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
    ["/asset-management/assets", "Asset register · SARAISE", "Registry asset register page"],
    ["/bank-reconciliation/accounts", "Bank accounts · SARAISE", "Registry bank accounts page"],
    ["/inventory-management/warehouses", "Warehouses · SARAISE", "Registry warehouses page"],
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
