/* eslint-disable max-lines-per-function -- access-control panel behavior requires local fixtures for grant/update/revoke flows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PrincipalDirectoryPort } from "./PermissionPanel";
import { PermissionDialog, PermissionPanel } from "./PermissionPanel";
import { dmsConfiguration, dmsPagination, permissionFixture } from "../__tests__/fixtures";
import { dmsService } from "../services/dms-service";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("PermissionPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders existing grants read-only when manage access is absent", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listPermissions").mockResolvedValue({
      items: [permissionFixture],
      pagination: dmsPagination,
      correlation_id: "corr-permissions",
    });

    renderWithQuery(<PermissionPanel documentId="document-1" canManage={false} />);

    expect(await screen.findByText("Avery Reviewer")).toBeInTheDocument();
    expect(screen.getByText("read")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Grant access" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Permission for Avery Reviewer")).not.toBeInTheDocument();
  });

  it("updates and revokes governed grants behind explicit controls", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listPermissions").mockResolvedValue({
      items: [permissionFixture],
      pagination: dmsPagination,
      correlation_id: "corr-permissions",
    });
    const update = vi.spyOn(dmsService, "updatePermission").mockResolvedValue({
      ...permissionFixture,
      permission: "manage",
    });
    const revoke = vi.spyOn(dmsService, "revokePermission").mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);

    renderWithQuery(<PermissionPanel documentId="document-1" canManage />);

    const permission = await screen.findByLabelText("Permission for Avery Reviewer");
    await userEvent.selectOptions(permission, "manage");
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("permission-1", { permission: "manage" })
    );

    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    expect(revoke).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith("permission-1"));
  });

  it("searches verified principals before granting document access", async () => {
    vi.spyOn(dmsService, "getConfiguration").mockResolvedValue(dmsConfiguration());
    vi.spyOn(dmsService, "listPermissions").mockResolvedValue({
      items: [],
      pagination: { ...dmsPagination, count: 0, total_pages: 0 },
      correlation_id: "corr-permissions",
    });
    const grant = vi.spyOn(dmsService, "createPermission").mockResolvedValue({
      ...permissionFixture,
      permission: "share",
    });
    const searchPrincipals = vi.fn().mockResolvedValue([
      {
        id: "principal-1",
        type: "user",
        display_name: "Avery Reviewer",
        secondary_text: "avery@example.com",
      },
    ]);
    const directory: PrincipalDirectoryPort = {
      search: searchPrincipals,
    };

    renderWithQuery(<PermissionPanel documentId="document-1" canManage directory={directory} />);

    await userEvent.click(await screen.findByRole("button", { name: "Grant first access" }));
    await userEvent.type(screen.getByLabelText("Search tenant directory"), "av");
    await waitFor(() => expect(searchPrincipals).toHaveBeenCalledWith("av", "user"));
    await userEvent.click(await screen.findByRole("button", { name: /Avery Reviewer/u }));
    await userEvent.selectOptions(screen.getByLabelText("Permission"), "share");
    expect(screen.getByText("Read plus create governed share links.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Grant access" }));

    await waitFor(() =>
      expect(grant).toHaveBeenCalledWith({
        document_id: "document-1",
        principal_type: "user",
        principal_id: "principal-1",
        permission: "share",
      })
    );
  });

  it("keeps grants fail-closed when no directory adapter is supplied to the dialog", () => {
    const grant = vi.fn();
    renderWithQuery(
      <PermissionDialog
        open
        onOpenChange={() => undefined}
        documentId="document-1"
        minimumQueryLength={2}
        maximumQueryLength={80}
        onGrant={grant}
      />
    );

    expect(screen.getByRole("status")).toHaveTextContent("Tenant directory search is unavailable");
    expect(screen.getByRole("button", { name: "Grant access" })).toBeDisabled();
    expect(grant).not.toHaveBeenCalled();
  });
});
